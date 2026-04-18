"""Agent service - OpenClaw agent 集成"""
import json
import subprocess
import uuid
import os
import signal
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy.orm import Session

from nova_platform.models import Employee, Todo
from nova_platform.services import task_state_service

# 全局线程池，用于并行分发任务
_executor = ThreadPoolExecutor(max_workers=10)


def _run_command(cmd: list[str], timeout: int = 120) -> dict:
    """执行 shell 命令并返回结果"""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout
        )
        return {
            "success": result.returncode == 0,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Command timeout", "stdout": "", "stderr": ""}
    except Exception as e:
        return {"success": False, "error": str(e), "stdout": "", "stderr": ""}


def create_openclaw_agent(name: str, workspace: str = None, model: str = None) -> dict:
    """
    创建 OpenClaw agent
    
    Returns:
        {"success": True, "agent_id": "xxx", "workspace": "/path/to/workspace"}
        或
        {"success": False, "error": "..."}
    """
    # 默认 workspace 路径
    if not workspace:
        workspace = f"/tmp/openclaw_agents/{name}_{uuid.uuid4().hex[:8]}"
    
    # 确保 workspace 目录存在
    Path(workspace).mkdir(parents=True, exist_ok=True)
    
    # 构建命令
    cmd = [
        "openclaw", "agents", "add", name,
        "--non-interactive",
        "--workspace", workspace
    ]
    
    if model:
        cmd.extend(["--model", model])
    
    result = _run_command(cmd)
    
    if result["success"]:
        # 解析输出获取 agent 信息
        # 尝试 JSON 格式
        try:
            output = json.loads(result["stdout"])
            return {
                "success": True,
                "agent_id": output.get("id") or output.get("name"),
                "workspace": output.get("workspace"),
                "agent_dir": output.get("agentDir")
            }
        except json.JSONDecodeError:
            # 非 JSON 输出，尝试从文本提取
            return {
                "success": True,
                "agent_id": name,
                "workspace": workspace
            }
    else:
        return {
            "success": False,
            "error": result.get("stderr") or result.get("error", "Unknown error")
        }


def send_task_to_agent(agent_id: str, task: str, timeout: int = 300) -> dict:
    """
    向 OpenClaw agent 发送任务
    
    Returns:
        {"success": True, "output": "..."}
        或
        {"success": False, "error": "..."}
    """
    # OpenClaw 通过 agent 命令发送任务 (local 模式，不等待网关)
    # openclaw agent --agent <agent_id> --message "<task>" --local --json
    cmd = ["openclaw", "agent", "--agent", agent_id, "--message", task, "--local", "--json"]
    result = _run_command(cmd, timeout=timeout)
    
    if result["success"]:
        return {
            "success": True,
            "output": result["stdout"]
        }
    else:
        return {
            "success": False,
            "error": result.get("stderr") or result.get("error", "Unknown error")
        }


def list_openclaw_agents() -> list:
    """列出所有 OpenClaw agents"""
    result = _run_command(["openclaw", "agents", "list", "--json"])
    if result["success"]:
        try:
            return json.loads(result["stdout"])
        except json.JSONDecodeError:
            return []
    return []


def delete_openclaw_agent(agent_id: str) -> dict:
    """删除 OpenClaw agent"""
    cmd = ["openclaw", "agents", "delete", agent_id, "--non-interactive"]
    result = _run_command(cmd)
    return {"success": result["success"], "error": result.get("stderr") if not result["success"] else None}


def recruit_agent(session: Session, name: str, agent_type: str = "openclaw", 
                  role: str = "worker", skills: list = None, **kwargs) -> dict:
    """
    招募一个 agent（创建 + 存储到数据库）
    
    Args:
        session: 数据库 session
        name: agent 名称
        agent_type: "openclaw" 或 "hermes"
        role: 角色
        skills: 技能列表
        **kwargs: 额外配置（如 model 等）
    
    Returns:
        {"success": True, "employee": Employee对象}
        或
        {"success": False, "error": "..."}
    """
    skills_json = json.dumps(skills or [])
    agent_config = json.dumps(kwargs) if kwargs else None
    
    if agent_type == "openclaw":
        # 创建 OpenClaw agent
        model = kwargs.get("model")
        workspace = kwargs.get("workspace")
        
        create_result = create_openclaw_agent(name, workspace=workspace, model=model)
        
        if not create_result["success"]:
            return {"success": False, "error": create_result.get("error", "Failed to create agent")}
        
        agent_id = create_result["agent_id"]
        workspace_path = create_result.get("workspace")
        
        # 存储到数据库
        agent_config_obj = {
            "workspace": workspace_path,
            "model": model
        }
        
        employee = Employee(
            name=name,
            type="openclaw",
            role=role,
            skills=skills_json,
            agent_id=agent_id,
            agent_config=json.dumps(agent_config_obj)
        )
        session.add(employee)
        session.commit()
        
        return {"success": True, "employee": employee}
    
    elif agent_type == "hermes":
        # Hermes - 暂时用 profile 方式
        # 先创建 profile
        profile_name = f"agent_{uuid.uuid4().hex[:8]}"
        cmd = ["hermes", "profile", "create", profile_name]
        result = _run_command(cmd)
        
        if not result["success"]:
            return {"success": False, "error": f"Failed to create Hermes profile: {result.get('stderr')}"}
        
        agent_id = profile_name
        
        # 存储到数据库
        employee = Employee(
            name=name,
            type="hermes",
            role=role,
            skills=skills_json,
            agent_id=agent_id,
            agent_config=agent_config
        )
        session.add(employee)
        session.commit()
        
        return {"success": True, "employee": employee}
    
    elif agent_type == "claude-code":
        # Claude Code agent - 使用 claude CLI
        agent_id = f"claude-code-{uuid.uuid4().hex[:8]}"
        
        # Claude Code 不需要预先创建，只需存储配置
        agent_config_obj = {
            "model": kwargs.get("model"),
            "max_turns": kwargs.get("max_turns", 10),
            "allowed_tools": kwargs.get("allowed_tools", ["Read", "Edit", "Write", "Bash"]),
        }
        
        employee = Employee(
            name=name,
            type="claude-code",
            role=role,
            skills=skills_json,
            agent_id=agent_id,
            agent_config=json.dumps(agent_config_obj)
        )
        session.add(employee)
        session.commit()
        
        return {"success": True, "employee": employee}
    
    else:
        return {"success": False, "error": f"Unknown agent type: {agent_type}"}


def dispatch_task(session: Session, employee_id: str, task: str, project_id: str = None) -> dict:
    """
    分配任务给 agent 执行
    
    Returns:
        {"success": True, "output": "..."}
    """
    employee = session.query(Employee).filter_by(id=employee_id).first()
    
    if not employee:
        return {"success": False, "error": "Employee not found"}
    
    if employee.type == "openclaw":
        return send_task_to_agent(employee.agent_id, task)
    
    elif employee.type == "hermes":
        # Hermes 用 --profile 方式执行命令
        cmd = ["hermes", "--profile", employee.agent_id, "chat", "-q", task]
        result = _run_command(cmd, timeout=300)
        return {
            "success": result["success"],
            "output": result.get("stdout") if result["success"] else None,
            "error": result.get("stderr") if not result["success"] else None
        }
    
    elif employee.type == "claude-code":
        # Claude Code 用 claude -p 方式执行命令
        config = json.loads(employee.agent_config) if employee.agent_config else {}
        model = config.get("model")
        max_turns = config.get("max_turns", 10)
        
        cmd = ["claude", "-p", task, f"--max-turns={max_turns}"]
        if model:
            cmd.insert(1, f"--model={model}")
        
        result = _run_command(cmd, timeout=300)
        return {
            "success": result["success"],
            "output": result.get("stdout") if result["success"] else None,
            "error": result.get("stderr") if not result["success"] else None
        }
    
    else:
        return {"success": False, "error": f"Employee type {employee.type} cannot execute tasks"}


# ============================================================================
# 异步任务分发（优化 2）
# ============================================================================

def _run_agent_async(task_id: str, agent_type: str, agent_id: str, task: str, agent_config: str = None, db_session=None):
    """
    在后台线程中运行 agent 任务，不阻塞主线程
    任务完成后更新状态到数据库
    """
    try:
        if agent_type == "openclaw":
            # OpenClaw agent - 使用 nohup 脱离终端运行
            cmd = [
                "nohup", "openclaw", "agent",
                "--agent", agent_id,
                "--message", task,
                "--local", "--json"
            ]
            # 重定向输出到临时文件
            output_file = f"/tmp/openclaw_task_{task_id}.output"
            with open(output_file, "w") as f:
                proc = subprocess.Popen(
                    cmd,
                    stdout=f,
                    stderr=subprocess.STDOUT,
                    preexec_fn=os.setsid if os.name != 'nt' else None
                )

            # 更新数据库状态
            if db_session:
                task_state_service.update_task_status(
                    db_session, task_id,
                    status="running",
                    pid=proc.pid
                )
            return {"dispatched": True, "task_id": task_id}

        elif agent_type == "hermes":
            # Hermes agent - 后台执行
            cmd = ["hermes", "--profile", agent_id, "chat", "-q", task]
            output_file = f"/tmp/hermes_task_{task_id}.output"
            with open(output_file, "w") as f:
                proc = subprocess.Popen(
                    cmd,
                    stdout=f,
                    stderr=subprocess.STDOUT,
                    preexec_fn=os.setsid if os.name != 'nt' else None
                )

            if db_session:
                task_state_service.update_task_status(
                    db_session, task_id,
                    status="running",
                    pid=proc.pid
                )
            return {"dispatched": True, "task_id": task_id}

        elif agent_type == "claude-code":
            # Claude Code agent - 后台执行
            config = json.loads(agent_config) if agent_config else {}
            model = config.get("model")
            max_turns = config.get("max_turns", 10)

            cmd = ["claude", "-p", task, f"--max-turns={max_turns}"]
            if model:
                cmd.insert(1, f"--model={model}")

            output_file = f"/tmp/claude_task_{task_id}.output"
            with open(output_file, "w") as f:
                proc = subprocess.Popen(
                    cmd,
                    stdout=f,
                    stderr=subprocess.STDOUT,
                    preexec_fn=os.setsid if os.name != 'nt' else None
                )

            if db_session:
                task_state_service.update_task_status(
                    db_session, task_id,
                    status="running",
                    pid=proc.pid
                )
            return {"dispatched": True, "task_id": task_id}

    except Exception as e:
        if db_session:
            task_state_service.update_task_status(
                db_session, task_id,
                status="failed",
                error=str(e)
            )
        return {"dispatched": False, "error": str(e)}


def dispatch_task_async(session: Session, employee_id: str, task: str, project_id: str = None) -> dict:
    """
    异步分配任务给 agent，立即返回，不等待执行结果

    Returns:
        {"success": True, "task_id": "xxx", "status": "dispatched"}
    """
    employee = session.query(Employee).filter_by(id=employee_id).first()

    if not employee:
        return {"success": False, "error": "Employee not found"}

    # 创建数据库任务记录
    db_task = task_state_service.create_async_task(
        session,
        employee_id=employee_id,
        todo_id=project_id  # 这里project_id实际上可能是todo_id，需要调整
    )

    task_id = db_task.id

    if employee.type in ("openclaw", "hermes", "claude-code"):
        # 提交到线程池异步执行
        _executor.submit(
            _run_agent_async,
            task_id,
            employee.type,
            employee.agent_id,
            task,
            employee.agent_config,  # 传递配置
            session  # 传递数据库会话
        )

        return {
            "success": True,
            "task_id": task_id,
            "status": "dispatched",
            "message": f"Task dispatched to {employee.type} agent {employee.name}"
        }
    else:
        return {"success": False, "error": f"Employee type {employee.type} cannot execute tasks"}


def get_async_task_status(session: Session, task_id: str) -> dict:
    """
    查询异步任务状态

    Returns:
        {"status": "running|completed|failed", "output": "...", "error": "..."}
    """
    task_info = task_state_service.get_task_status(session, task_id)
    if not task_info:
        return {"status": "unknown", "error": "Task not found"}

    return task_info


def cancel_async_task(session: Session, task_id: str) -> dict:
    """取消正在运行的异步任务"""
    result = task_state_service.cancel_task(session, task_id)
    if not result:
        return {"success": False, "error": "Task not found"}
    return {"success": True, "message": "Task cancelled"}


# ============================================================================
# Agent 进程存活检查（使用task_state_service中的实现）
# ============================================================================

# 这些函数已经移到 task_state_service 中
# check_agent_process_status -> task_state_service.check_process_running
# check_todo_agent_status -> task_state_service.check_todo_agent_status

# 为了向后兼容，保留这些函数作为代理
def check_agent_process_status(pid: int) -> str:
    """检查 agent 进程状态（已废弃，使用task_state_service.check_process_running）"""
    return task_state_service.check_process_running(pid)

def check_todo_agent_status(session: Session, todo_id: str, auto_commit: bool = True) -> dict:
    """检查Todo对应的agent任务是否完成（已废弃，使用task_state_service.check_todo_agent_status）"""
    return task_state_service.check_todo_agent_status(session, todo_id, auto_commit)

