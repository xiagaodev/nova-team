"""
Mailbox Service - Agent 交互式输入/输出处理

负责：
1. 监听 agent 进程的输出
2. 检测 agent 是否需要用户输入
3. 将 agent 输出提交给 leader 进行决策
4. 将 leader 的决策输入回 agent 进程
5. 维护交互历史记录
"""

import os
import json
import time
import threading
from pathlib import Path
from typing import Optional, Dict, List, Callable
from datetime import datetime
from enum import Enum

from nova_platform.services import agent_process_service, agent_session_service


class AgentState(Enum):
    """Agent 运行状态"""
    RUNNING = "running"           # 正常运行中
    WAITING_INPUT = "waiting"     # 等待用户输入
    COMPLETED = "completed"       # 任务完成
    FAILED = "failed"             # 执行失败
    IDLE = "idle"                 # 空闲（无活动）


class MailboxMessage:
    """邮箱消息"""

    def __init__(self, sender: str, content: str, timestamp: datetime = None):
        self.sender = sender          # sender: "agent" or "leader"
        self.content = content
        self.timestamp = timestamp or datetime.utcnow()

    def to_dict(self) -> dict:
        return {
            "sender": self.sender,
            "content": self.content,
            "timestamp": self.timestamp.isoformat()
        }


class AgentMailbox:
    """Agent 邮箱 - 管理单个 agent 会话的交互"""

    def __init__(self, session_id: str, project_id: str, agent_id: str):
        self.session_id = session_id
        self.project_id = project_id
        self.agent_id = agent_id
        self.messages: List[MailboxMessage] = []
        self.state = AgentState.RUNNING
        self.created_at = datetime.utcnow()
        self.last_activity = datetime.utcnow()

    def add_message(self, sender: str, content: str):
        """添加消息"""
        self.messages.append(MailboxMessage(sender, content))
        self.last_activity = datetime.utcnow()

    def get_recent_messages(self, count: int = 10) -> List[dict]:
        """获取最近的几条消息"""
        return [msg.to_dict() for msg in self.messages[-count:]]

    def get_context_for_leader(self) -> str:
        """获取给 leader 的上下文"""
        context = f"Agent {self.agent_id} 在项目 {self.project_id} 中的状态:\n\n"

        # 状态
        context += f"当前状态: {self.state.value}\n"

        # 最近的交互
        if self.messages:
            context += "\n最近的交互:\n"
            for msg in self.messages[-5:]:
                context += f"[{msg.timestamp.strftime('%H:%M:%S')}] {msg.sender}: {msg.content[:200]}\n"

        return context


# ============================================================================
# 全局邮箱管理
# ============================================================================

# 格式: {session_id: AgentMailbox}
_active_mailboxes: Dict[str, AgentMailbox] = {}

_mailbox_lock = threading.RLock()


def get_or_create_mailbox(session_id: str, project_id: str, agent_id: str) -> AgentMailbox:
    """获取或创建邮箱"""
    with _mailbox_lock:
        if session_id not in _active_mailboxes:
            _active_mailboxes[session_id] = AgentMailbox(session_id, project_id, agent_id)
        return _active_mailboxes[session_id]


def get_mailbox(session_id: str) -> Optional[AgentMailbox]:
    """获取邮箱"""
    with _mailbox_lock:
        return _active_mailboxes.get(session_id)


def remove_mailbox(session_id: str):
    """移除邮箱"""
    with _mailbox_lock:
        if session_id in _active_mailboxes:
            del _active_mailboxes[session_id]


# ============================================================================
# Agent 输出监听
# ============================================================================

def monitor_agent_output(session_id: str, callback: Callable[[str], None] = None) -> Dict:
    """
    监听 agent 输出并检测状态

    Args:
        session_id: 会话ID
        callback: 输出回调函数

    Returns:
        {"state": AgentState, "output": str, "needs_input": bool}
    """
    # 获取进程状态
    proc_status = agent_process_service.get_process_status(session_id)

    if not proc_status.get("running"):
        # 进程已结束
        output = agent_process_service.read_process_output(session_id)
        mailbox = get_mailbox(session_id)

        if mailbox:
            returncode = proc_status.get("returncode", 1)
            if returncode == 0:
                mailbox.state = AgentState.COMPLETED
            else:
                mailbox.state = AgentState.FAILED

        return {
            "state": AgentState.COMPLETED if proc_status.get("returncode") == 0 else AgentState.FAILED,
            "output": output,
            "needs_input": False
        }

    # 检查是否等待输入
    needs_input = agent_process_service.is_process_waiting_for_input(session_id)
    output = agent_process_service.read_process_output(session_id, max_bytes=4096)

    # 更新邮箱状态
    mailbox = get_mailbox(session_id)
    if mailbox:
        if needs_input:
            mailbox.state = AgentState.WAITING_INPUT
        else:
            mailbox.state = AgentState.RUNNING

        # 将输出存入邮箱
        if output and output.strip():
            mailbox.add_message("agent", output)

    if callback and output:
        callback(output)

    return {
        "state": AgentState.WAITING_INPUT if needs_input else AgentState.RUNNING,
        "output": output,
        "needs_input": needs_input
    }


# ============================================================================
# Leader 决策处理
# ============================================================================

def consult_leader(session, project_id: str, agent_session_id: str, agent_output: str) -> Dict:
    """
    咨询 leader 如何处理 agent 的输出/请求

    Args:
        session: 数据库会话
        project_id: 项目ID
        agent_session_id: Agent 会话ID
        agent_output: Agent 输出内容

    Returns:
        {"action": str, "input": str, "notes": str}
        action: "continue", "terminate", "retry", "wait"
    """
    from nova_platform.services import project_member_service, agent_service
    from nova_platform.services.agent_process_service import get_process_status

    # 获取项目的 leader
    leaders = project_member_service.get_project_members_by_role(session, project_id, "leader")
    if not leaders:
        return {"action": "terminate", "input": "", "notes": "No leader found"}

    leader = leaders[0]

    # 如果 leader 是人类，无法自动处理
    if leader.type == "human":
        return {
            "action": "wait",
            "input": "",
            "notes": "Leader is human, requires manual intervention"
        }

    # 获取邮箱上下文
    mailbox = get_mailbox(agent_session_id)
    context = mailbox.get_context_for_leader() if mailbox else ""

    # 构建 leader 请求
    prompt = f"""Agent {agent_session_id} 需要处理：

Agent 输出：
{agent_output[:1000]}

{context}

请分析并决定如何处理：

选项：
1. continue - 提供输入让 agent 继续（在 input 字段中输入内容）
2. terminate - 终止 agent 任务
3. retry - 重试当前任务
4. wait - 等待更多信息

请以 JSON 格式回复：
{{"action": "continue|terminate|retry|wait", "input": "输入内容", "notes": "说明"}}"""

    try:
        # 调用 leader agent
        proc_status = get_process_status(agent_session_id)
        result = agent_service.dispatch_task(
            session=session,
            employee_id=leader.id,
            task=prompt,
            project_id=project_id
        )

        if result.get("success") and result.get("output"):
            leader_output = result["output"]

            # 尝试解析 JSON 响应
            try:
                # 提取 JSON 部分
                import re
                json_match = re.search(r'\{[^{}]*"action"[^{}]*\}', leader_output, re.DOTALL)
                if json_match:
                    decision = json.loads(json_match.group())
                    return decision
            except json.JSONDecodeError:
                pass

            # 如果无法解析 JSON，根据输出内容推断
            output_lower = leader_output.lower()
            if "continue" in output_lower or "继续" in output_lower or "go on" in output_lower:
                return {"action": "continue", "input": leader_output, "notes": "Leader decided to continue"}
            elif "terminate" in output_lower or "stop" in output_lower or "终止" in output_lower:
                return {"action": "terminate", "input": "", "notes": "Leader decided to terminate"}
            elif "retry" in output_lower or "重试" in output_lower:
                return {"action": "retry", "input": "", "notes": "Leader decided to retry"}
            else:
                return {"action": "wait", "input": "", "notes": "Leader requested to wait"}

        return {"action": "wait", "input": "", "notes": "Failed to consult leader"}

    except Exception as e:
        return {"action": "terminate", "input": "", "notes": f"Error: {str(e)}"}


def handle_agent_waiting(session, session_id: str, project_id: str) -> Dict:
    """
    处理 agent 等待输入的情况

    Args:
        session: 数据库会话
        session_id: Agent 会话ID
        project_id: 项目ID

    Returns:
        处理结果
    """
    # 读取 agent 输出
    output = agent_process_service.read_process_output(session_id)

    # 咨询 leader
    decision = consult_leader(session, project_id, session_id, output)

    # 根据 leader 决策行动
    action = decision.get("action", "wait")

    if action == "continue":
        # 发送输入到 agent
        input_text = decision.get("input", "y")
        success = agent_process_service.send_input_to_process(session_id, input_text)

        # 记录到邮箱
        mailbox = get_mailbox(session_id)
        if mailbox:
            mailbox.add_message("leader", input_text)
            mailbox.state = AgentState.RUNNING

        return {
            "action_taken": "continue",
            "input_sent": input_text,
            "success": success
        }

    elif action == "terminate":
        # 终止进程
        agent_process_service.terminate_process(session_id)
        remove_mailbox(session_id)

        return {
            "action_taken": "terminate",
            "reason": decision.get("notes", "Leader decided to terminate")
        }

    elif action == "retry":
        # 重试 - 终止当前进程，重新启动
        agent_process_service.terminate_process(session_id)

        return {
            "action_taken": "retry",
            "notes": "Process terminated, needs restart"
        }

    else:  # wait
        return {
            "action_taken": "wait",
            "notes": decision.get("notes", "Waiting for more information")
        }


# ============================================================================
# 交互循环
# ============================================================================

def run_interaction_loop(session, project_id: str, session_id: str, timeout: int = 300) -> Dict:
    """
    运行 agent 交互循环

    持续监听 agent 输出，当需要输入时咨询 leader

    Args:
        session: 数据库会话
        project_id: 项目ID
        session_id: Agent 会话ID
        timeout: 超时时间（秒）

    Returns:
        最终状态
    """
    start_time = time.time()
    interactions = 0

    while time.time() - start_time < timeout:
        # 检查进程状态
        status = monitor_agent_output(session_id)

        if status["state"] == AgentState.COMPLETED:
            return {
                "success": True,
                "state": "completed",
                "output": status["output"],
                "interactions": interactions
            }

        elif status["state"] == AgentState.FAILED:
            return {
                "success": False,
                "state": "failed",
                "output": status["output"],
                "interactions": interactions
            }

        elif status["state"] == AgentState.WAITING_INPUT:
            # 处理等待输入
            result = handle_agent_waiting(session, session_id, project_id)
            interactions += 1

            action_taken = result.get("action_taken")

            if action_taken == "terminate":
                return {
                    "success": False,
                    "state": "terminated",
                    "reason": result.get("reason"),
                    "interactions": interactions
                }

            elif action_taken == "retry":
                return {
                    "success": False,
                    "state": "retry",
                    "interactions": interactions
                }

            elif action_taken == "wait":
                # 等待一段时间再检查
                time.sleep(5)

        # 短暂休眠避免占用 CPU
        time.sleep(2)

    # 超时
    return {
        "success": False,
        "state": "timeout",
        "interactions": interactions
    }


# ============================================================================
# 清理和维护
# ============================================================================

def cleanup_project_mailboxes(project_id: str):
    """清理项目的所有邮箱"""
    with _mailbox_lock:
        to_remove = []

        for session_id, mailbox in _active_mailboxes.items():
            if mailbox.project_id == project_id:
                to_remove.append(session_id)

        for session_id in to_remove:
            del _active_mailboxes[session_id]


def get_mailbox_summary(project_id: str = None) -> List[dict]:
    """获取邮箱摘要"""
    with _mailbox_lock:
        result = []

        for session_id, mailbox in _active_mailboxes.items():
            if project_id is None or mailbox.project_id == project_id:
                result.append({
                    "session_id": session_id,
                    "project_id": mailbox.project_id,
                    "agent_id": mailbox.agent_id,
                    "state": mailbox.state.value,
                    "message_count": len(mailbox.messages),
                    "created_at": mailbox.created_at.isoformat(),
                    "last_activity": mailbox.last_activity.isoformat()
                })

        return result
