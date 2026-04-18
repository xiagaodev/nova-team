"""
Agent Process Service - Agent 进程管理服务

负责：
1. 存储和管理运行中的 agent 进程
2. 会话复用 - 同一项目同一 agent 使用同一会话
3. 进程输出监控 - 检测完成或等待输入状态
4. 进程终止和清理
"""

import os
import signal
import subprocess
import threading
import queue
import time
from pathlib import Path
from typing import Optional, Dict, Tuple
from datetime import datetime

from nova_platform.services import agent_session_service, project_service
from nova_platform.models import Employee


# ============================================================================
# 进程存储 - 存储运行中的进程对象
# ============================================================================

# 格式: {session_id: {"process": Popen, "agent_id": str, "project_id": str, "output_queue": Queue, "started_at": datetime}}
_running_processes: Dict[str, Dict] = {}

# 线程锁，用于进程操作
_process_lock = threading.RLock()


# ============================================================================
# 会话管理
# ============================================================================

def get_session_id(project_id: str, agent_id: str) -> str:
    """
    生成会话ID，确保同一项目同一agent使用相同session

    Args:
        project_id: 项目ID
        agent_id: Agent ID

    Returns:
        会话ID (格式: {project_id}#{agent_id})
    """
    return f"{project_id}#{agent_id}"


def get_or_create_process(project_id: str, employee: Employee, task: str, session) -> Tuple[Optional[subprocess.Popen], Optional[str]]:
    """
    获取或创建 agent 进程

    如果会话已存在且进程正在运行，复用该进程
    否则创建新进程并存储

    Args:
        project_id: 项目ID
        employee: 员工对象
        task: 任务描述
        session: 数据库会话

    Returns:
        (进程对象, 会话ID) 或 (None, None) 如果失败
    """
    agent_id = employee.agent_id
    session_id = get_session_id(project_id, agent_id)

    with _process_lock:
        # 检查是否已有运行中的进程
        if session_id in _running_processes:
            proc_info = _running_processes[session_id]
            proc = proc_info["process"]

            # 检查进程是否仍在运行
            if proc.poll() is None:
                # 进程仍在运行，复用
                return proc, session_id
            else:
                # 进程已结束，清理
                _remove_process(session_id)

        # 创建新进程
        return _create_new_process(project_id, employee, task, session_id, session)


def _create_new_process(project_id: str, employee: Employee, task: str, session_id: str, session) -> Tuple[Optional[subprocess.Popen], Optional[str]]:
    """
    创建新的 agent 进程

    Args:
        project_id: 项目ID
        employee: 员工对象
        task: 任务描述
        session_id: 会话ID
        session: 数据库会话

    Returns:
        (进程对象, 会话ID) 或 (None, None) 如果失败
    """
    import json
    from nova_platform.services import project_service

    agent_type = employee.type
    agent_id = employee.agent_id
    agent_config = json.loads(employee.agent_config) if employee.agent_config else {}

    # 获取工作空间
    workspace_path = project_service.get_project_workspace(session, project_id)
    cwd = workspace_path if workspace_path else os.getcwd()

    # 准备会话目录
    if agent_type == "openclaw":
        session_info = agent_session_service.prepare_openclaw_session(project_id, agent_id)
        cmd = ["openclaw", "agent", "--agent", agent_id, "--message", task, "--local", "--json"]
        work_dir = session_info.get("session_dir", cwd)

    elif agent_type == "hermes":
        session_info = agent_session_service.prepare_hermes_session(project_id, agent_id)
        enhanced_task = f"[Project: {project_id}] {task}"
        cmd = ["hermes", "--profile", agent_id, "chat", "-q", enhanced_task]
        work_dir = session_info.get("session_dir", cwd)

    elif agent_type == "claude-code":
        session_info = agent_session_service.prepare_claude_code_session(project_id, agent_id)
        enhanced_task = f"[Project: {project_id}] {task}"
        max_turns = agent_config.get("max_turns", 10)
        cmd = ["claude", "-p", enhanced_task, f"--max-turns={max_turns}"]

        model = agent_config.get("model")
        if model:
            cmd.insert(1, f"--model={model}")

        # 设置环境变量
        env = os.environ.copy()
        env["HOME"] = session_info.get("claude_dir", cwd)
        work_dir = cwd

    else:
        return None, None

    # 输出文件路径
    output_file = os.path.join(work_dir, f"task_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.output")

    try:
        # 创建进程
        with open(output_file, "w") as f:
            proc = subprocess.Popen(
                cmd,
                stdout=f,
                stderr=subprocess.STDOUT,
                cwd=work_dir,
                env=env if agent_type == "claude-code" else None,
                preexec_fn=os.setsid if os.name != 'nt' else None
            )

        # 创建输出队列（用于实时读取）
        output_queue = queue.Queue()

        # 存储进程信息
        _running_processes[session_id] = {
            "process": proc,
            "agent_id": agent_id,
            "project_id": project_id,
            "agent_type": agent_type,
            "output_queue": output_queue,
            "output_file": output_file,
            "started_at": datetime.utcnow(),
            "last_activity": datetime.utcnow()
        }

        return proc, session_id

    except Exception as e:
        return None, None


def _remove_process(session_id: str):
    """从运行中进程列表移除"""
    with _process_lock:
        if session_id in _running_processes:
            del _running_processes[session_id]


# ============================================================================
# 进程状态查询
# ============================================================================

def get_process_status(session_id: str) -> Dict:
    """
    获取进程状态

    Args:
        session_id: 会话ID

    Returns:
        状态信息 {"running": bool, "pid": int, "output": str, ...}
    """
    with _process_lock:
        if session_id not in _running_processes:
            return {"running": False, "error": "Process not found"}

        proc_info = _running_processes[session_id]
        proc = proc_info["process"]

        # 检查进程状态
        returncode = proc.poll()

        if returncode is None:
            # 进程仍在运行
            return {
                "running": True,
                "pid": proc.pid,
                "session_id": session_id,
                "agent_id": proc_info["agent_id"],
                "project_id": proc_info["project_id"],
                "started_at": proc_info["started_at"].isoformat(),
                "last_activity": proc_info["last_activity"].isoformat()
            }
        else:
            # 进程已结束
            return {
                "running": False,
                "pid": proc.pid,
                "returncode": returncode,
                "session_id": session_id,
                "agent_id": proc_info["agent_id"],
                "ended": True
            }


def get_process_by_pid(pid: int) -> Optional[Dict]:
    """通过 PID 查找进程信息"""
    with _process_lock:
        for session_id, proc_info in _running_processes.items():
            if proc_info["process"].pid == pid:
                return {
                    "session_id": session_id,
                    "running": proc_info["process"].poll() is None,
                    **proc_info
                }
        return None


def read_process_output(session_id: str, max_bytes: int = 8192) -> str:
    """
    读取进程输出（从文件）

    Args:
        session_id: 会话ID
        max_bytes: 最大读取字节数

    Returns:
        输出内容
    """
    with _process_lock:
        if session_id not in _running_processes:
            return ""

        proc_info = _running_processes[session_id]
        output_file = proc_info.get("output_file")

        if not output_file or not os.path.exists(output_file):
            return ""

        try:
            with open(output_file, "r") as f:
                # 读取最后的 max_bytes 字节
                f.seek(0, 2)  # 移到文件末尾
                size = f.tell()
                f.seek(max(0, size - max_bytes))
                return f.read()
        except Exception:
            return ""


def is_process_waiting_for_input(session_id: str) -> bool:
    """
    检查进程是否在等待输入

    通过检查输出文件中是否有提示符模式来判断

    Args:
        session_id: 会话ID

    Returns:
        是否在等待输入
    """
    output = read_process_output(session_id, max_bytes=1024)

    # 检查常见的等待输入模式
    waiting_patterns = [
        ">>>",  # Python
        "$ ",   # Shell
        "? ",   # Prompt
        "Input:", "Enter:", "Continue?", "(y/n)",
        "[Y/n]", "[y/N]"
    ]

    for pattern in waiting_patterns:
        if pattern in output and output.rstrip().endswith(pattern[:5]):
            return True

    return False


# ============================================================================
# 进程控制
# ============================================================================

def send_input_to_process(session_id: str, input_text: str) -> bool:
    """
    向进程发送输入

    Args:
        session_id: 会话ID
        input_text: 输入内容

    Returns:
        是否成功
    """
    with _process_lock:
        if session_id not in _running_processes:
            return False

        proc_info = _running_processes[session_id]
        proc = proc_info["process"]

        if proc.poll() is not None:
            return False

        try:
            # 向进程的标准输入写入
            proc.stdin.write(input_text + "\n")
            proc.stdin.flush()

            # 更新活动时间
            proc_info["last_activity"] = datetime.utcnow()

            return True
        except Exception:
            return False


def terminate_process(session_id: str, force: bool = False) -> bool:
    """
    终止进程

    Args:
        session_id: 会话ID
        force: 是否强制终止（SIGKILL）

    Returns:
        是否成功
    """
    with _process_lock:
        if session_id not in _running_processes:
            return False

        proc_info = _running_processes[session_id]
        proc = proc_info["process"]

        if proc.poll() is not None:
            # 进程已结束
            _remove_process(session_id)
            return True

        try:
            if force:
                # 强制终止整个进程组
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            else:
                # 优雅终止
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)

            # 等待进程结束
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                # 强制终止
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                proc.wait()

            _remove_process(session_id)
            return True

        except Exception:
            return False


def cleanup_project_processes(project_id: str):
    """
    清理项目的所有进程

    Args:
        project_id: 项目ID
    """
    with _process_lock:
        to_remove = []

        for session_id, proc_info in _running_processes.items():
            if proc_info["project_id"] == project_id:
                terminate_process(session_id, force=True)
                to_remove.append(session_id)

        for session_id in to_remove:
            _remove_process(session_id)


# ============================================================================
# 进程列表和管理
# ============================================================================

def list_running_processes() -> list:
    """列出所有运行中的进程"""
    with _process_lock:
        result = []

        for session_id, proc_info in _running_processes.items():
            proc = proc_info["process"]
            if proc.poll() is None:
                result.append({
                    "session_id": session_id,
                    "pid": proc.pid,
                    "agent_id": proc_info["agent_id"],
                    "project_id": proc_info["project_id"],
                    "agent_type": proc_info["agent_type"],
                    "started_at": proc_info["started_at"].isoformat(),
                    "last_activity": proc_info["last_activity"].isoformat()
                })

        return result


def cleanup_dead_processes():
    """清理已死亡的进程"""
    with _process_lock:
        to_remove = []

        for session_id, proc_info in _running_processes.items():
            if proc_info["process"].poll() is not None:
                to_remove.append(session_id)

        for session_id in to_remove:
            _remove_process(session_id)

        return len(to_remove)


# ============================================================================
# Todo 相关的进程查询
# ============================================================================

def get_todo_process_status(session, todo_id: str) -> Dict:
    """
    获取 Todo 关联的进程状态

    Args:
        session: 数据库会话
        todo_id: Todo ID

    Returns:
        进程状态信息
    """
    from nova_platform.models import Todo

    todo = session.query(Todo).filter_by(id=todo_id).first()
    if not todo or not todo.session_id:
        return {"running": False, "error": "No session found"}

    return get_process_status(todo.session_id)
