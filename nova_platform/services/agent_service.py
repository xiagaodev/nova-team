"""
Agent service - OpenClaw agent 集成
"""
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
from nova_platform.services import task_state_service, project_service

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


def verify_openclaw_agent(agent_id: str) -> dict:
    """
    验证 OpenClaw agent 是否存在

    Args:
        agent_id: OpenClaw agent ID

    Returns:
        {"exists": bool, "name": str, "error": str}
    """
    result = _run_command(["openclaw", "agents", "list", "--json"], timeout=30)

    if not result["success"]:
        return {"exists": False, "error": f"Failed to list agents: {result.get('stderr')}"}

    try:
        agents = json.loads(result["stdout"])
        for agent in agents:
            if agent.get("id") == agent_id or agent.get("name") == agent_id:
                return {
                    "exists": True,
                    "name": agent.get("name", agent_id),
                    "agent_id": agent.get("id", agent_id)
                }
        return {"exists": False, "error": f"Agent {agent_id} not found"}
    except json.JSONDecodeError:
        return {"exists": False, "error": "Failed to parse agent list"}


def verify_hermes_profile(profile_name: str) -> dict:
    """
    验证 Hermes profile 是否存在

    Args:
        profile_name: Hermes profile 名称

    Returns:
        {"exists": bool, "error": str}
    """
    result = _run_command(["hermes", "profile", "list"], timeout=30)

    if not result["success"]:
        return {"exists": False, "error": f"Failed to list profiles: {result.get('stderr')}"}

    # 检查输出中是否包含 profile 名称
    if profile_name in result.get("stdout", ""):
        return {"exists": True}

    return {"exists": False, "error": f"Profile {profile_name} not found"}


def verify_claude_code() -> dict:
    """
    验证 Claude Code CLI 是否可用

    Returns:
        {"exists": bool, "version": str, "error": str}
    """
    result = _run_command(["claude", "--version"], timeout=10)

    if result["success"]:
        return {
            "exists": True,
            "version": result.get("stdout", "").strip()
        }

    return {"exists": False, "error": "Claude Code CLI not available"}


def recruit_agent(session: Session, name: str, agent_type: str = "openclaw",
                  role: str = "worker", skills: list = None, **kwargs) -> dict:
    """
    招募一个 agent（使用已存在的 agent，不创建新的）

    Args:
        session: 数据库 session
        name: 员工名称
        agent_type: "openclaw" 或 "hermes" 或 "claude-code"
        role: 角色
        skills: 技能列表
        **kwargs: 额外配置
            - agent_id: openclaw 必需，已存在的 agent ID
            - profile_name: hermes 必需，已存在的 profile 名称
            - model: claude-code 可选，使用的模型

    Returns:
        {"success": True, "employee": Employee对象}
        或
        {"success": False, "error": "..."}
    """
    skills_json = json.dumps(skills or [])
    agent_config = json.dumps(kwargs) if kwargs else None

    if agent_type == "openclaw":
        # OpenClaw: 需要提供已存在的 agent_id
        agent_id = kwargs.get("agent_id")
        if not agent_id:
            return {"success": False, "error": "openclaw requires agent_id parameter"}

        # 检查该 agent_id 是否已被招募
        existing_employee = session.query(Employee).filter_by(
            type="openclaw",
            agent_id=agent_id
        ).first()
        if existing_employee:
            return {
                "success": False,
                "error": f"OpenClaw agent {agent_id} has already been recruited as employee {existing_employee.name}"
            }

        # 验证 agent 是否存在
        verify_result = verify_openclaw_agent(agent_id)
        if not verify_result["exists"]:
            return {
                "success": False,
                "error": f"OpenClaw agent not found: {agent_id}. Details: {verify_result.get('error')}"
            }

        # 存储到数据库
        agent_config_obj = {
            "agent_id": verify_result.get("agent_id", agent_id),
            "agent_name": verify_result.get("name", name),
            "model": kwargs.get("model")
        }

        employee = Employee(
            name=name,
            type="openclaw",
            role=role,
            skills=skills_json,
            agent_id=verify_result.get("agent_id", agent_id),
            agent_config=json.dumps(agent_config_obj)
        )
        session.add(employee)
        session.commit()

        return {"success": True, "employee": employee}

    elif agent_type == "hermes":
        # Hermes: 需要提供已存在的 profile_name
        profile_name = kwargs.get("profile_name")
        if not profile_name:
            return {"success": False, "error": "hermes requires profile_name parameter"}

        # 验证 profile 是否存在
        verify_result = verify_hermes_profile(profile_name)
        if not verify_result["exists"]:
            return {
                "success": False,
                "error": f"Hermes profile not found: {profile_name}. Details: {verify_result.get('error')}"
            }

        # 存储到数据库
        agent_config_obj = {
            "profile_name": profile_name,
            "model": kwargs.get("model")
        }

        employee = Employee(
            name=name,
            type="hermes",
            role=role,
            skills=skills_json,
            agent_id=profile_name,
            agent_config=json.dumps(agent_config_obj)
        )
        session.add(employee)
        session.commit()

        return {"success": True, "employee": employee}

    elif agent_type == "claude-code":
        # Claude Code: 验证 CLI 是否可用
        verify_result = verify_claude_code()
        if not verify_result["exists"]:
            return {
                "success": False,
                "error": f"Claude Code CLI not available. Details: {verify_result.get('error')}"
            }

        # 生成内部 ID 用于标识
        agent_id = f"claude-code-{uuid.uuid4().hex[:8]}"

        # Claude Code 不需要预先创建，只需存储配置
        agent_config_obj = {
            "model": kwargs.get("model"),
            "max_turns": kwargs.get("max_turns", 10),
            "allowed_tools": kwargs.get("allowed_tools", ["Read", "Edit", "Write", "Bash"]),
            "version": verify_result.get("version", "unknown")
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

    Args:
        session: 数据库会话
        employee_id: 员工ID
        task: 任务描述
        project_id: 项目ID（用于会话隔离）

    Returns:
        {"success": True, "output": "..."}
    """
    employee = session.query(Employee).filter_by(id=employee_id).first()

    if not employee:
        return {"success": False, "error": "Employee not found"}

    if not project_id:
        return {"success": False, "error": "Project ID required for session isolation"}

    if employee.type == "openclaw":
        # 准备项目会话
        from nova_platform.services import agent_session_service
        session_info = agent_session_service.prepare_openclaw_session(project_id, employee.agent_id)
        return send_task_to_agent(employee.agent_id, task, project_context=session_info)

    elif employee.type == "hermes":
        # 准备项目会话
        from nova_platform.services import agent_session_service
        session_info = agent_session_service.prepare_hermes_session(project_id, employee.agent_id)

        # Hermes 用 --profile 方式执行命令，并添加项目上下文
        enhanced_task = f"[Project: {project_id}] {task}"
        cmd = ["hermes", "--profile", employee.agent_id, "chat", "-q", enhanced_task]
        result = _run_command(cmd, timeout=300)
        return {
            "success": result["success"],
            "output": result.get("stdout") if result["success"] else None,
            "error": result.get("stderr") if not result["success"] else None
        }

    elif employee.type == "claude-code":
        # 准备项目会话
        from nova_platform.services import agent_session_service
        session_info = agent_session_service.prepare_claude_code_session(project_id, employee.agent_id)

        # Claude Code 用 claude -p 方式执行命令，并使用项目会话目录
        config = json.loads(employee.agent_config) if employee.agent_config else {}
        model = config.get("model")
        max_turns = config.get("max_turns", 10)

        enhanced_task = f"[Project: {project_id}] {task}"
        cmd = ["claude", "-p", enhanced_task, f"--max-turns={max_turns}"]
        if model:
            cmd.insert(1, f"--model={model}")

        # 设置工作目录为项目会话目录
        import subprocess
        env = os.environ.copy()
        env["HOME"] = session_info["claude_dir"]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300, env=env)
        return {
            "success": result.returncode == 0,
            "output": result.stdout if result.returncode == 0 else None,
            "error": result.stderr if result.returncode != 0 else None
        }

    else:
        return {"success": False, "error": f"Employee type {employee.type} cannot execute tasks"}


def send_task_to_agent(agent_id: str, task: str, project_context: dict = None, timeout: int = 300) -> dict:
    """
    向 OpenClaw agent 发送任务

    Args:
        agent_id: OpenClaw agent ID
        task: 任务描述
        project_context: 项目上下文（包含会话目录等信息）
        timeout: 超时时间

    Returns:
        {"success": True, "output": "..."}
        或
        {"success": False, "error": "..."}
    """
    # OpenClaw 通过 agent 命令发送任务 (local 模式，不等待网关)
    cmd = ["openclaw", "agent", "--agent", agent_id, "--message", task, "--local", "--json"]

    # 如果有项目上下文，添加工作空间参数
    if project_context and "workspace_root" in project_context:
        cmd.extend(["--cwd", project_context["workspace_root"]])

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


# ============================================================================
# 异步任务分发 - 使用进程管理服务
# ============================================================================

def dispatch_task_async_with_todo(session: Session, employee_id: str, task: str, todo_id: str, project_id: str = None) -> dict:
    """
    异步分配任务给 agent，并关联到 Todo 记录

    使用 agent_process_service 管理进程，支持会话复用和进程跟踪

    Args:
        session: 数据库会话
        employee_id: 员工ID
        task: 任务描述
        todo_id: Todo ID
        project_id: 项目ID（用于会话隔离）

    Returns:
        {"success": True, "task_id": "xxx", "session_id": "xxx", "process_id": int}
    """
    from nova_platform.services import agent_process_service
    from nova_platform.models import Todo

    employee = session.query(Employee).filter_by(id=employee_id).first()

    if not employee:
        return {"success": False, "error": "Employee not found"}

    if not project_id:
        return {"success": False, "error": "Project ID required for session isolation"}

    if employee.type not in ("openclaw", "hermes", "claude-code"):
        return {"success": False, "error": f"Employee type {employee.type} cannot execute tasks"}

    # 获取或创建进程（会话复用）
    proc, session_id = agent_process_service.get_or_create_process(
        project_id, employee, task, session
    )

    if not proc:
        return {"success": False, "error": "Failed to create agent process"}

    # 更新 Todo 记录
    todo = session.query(Todo).filter_by(id=todo_id).first()
    if todo:
        todo.process_id = proc.pid
        todo.session_id = session_id
        todo.status = "in_progress"
        session.commit()

    return {
        "success": True,
        "process_id": proc.pid,
        "session_id": session_id,
        "message": f"Task dispatched to {employee.type} agent {employee.name}"
    }


def _run_agent_async(task_id: str, agent_type: str, agent_id: str, task: str, agent_config: str = None, db_session=None, project_id: str = None):
    """
    在后台线程中运行 agent 任务（已废弃，使用 agent_process_service）

    保留此函数以向后兼容，新代码应使用 dispatch_task_async_with_todo
    """
    try:
        from nova_platform.services import agent_process_service
        from nova_platform.database import get_session

        session = db_session if db_session else get_session()

        # 获取 employee
        employee = session.query(Employee).filter_by(id=agent_id if agent_type in ("hermes", "claude-code") else agent_id).first()
        if not employee and agent_type == "openclaw":
            # 对于 openclaw，agent_id 是实际的 agent ID，需要查找对应的 employee
            employee = session.query(Employee).filter(
                Employee.type == "openclaw",
                Employee.agent_id == agent_id
            ).first()

        if not employee:
            if db_session:
                task_state_service.update_task_status(
                    db_session, task_id,
                    status="failed",
                    error="Employee not found"
                )
            return {"dispatched": False, "error": "Employee not found"}

        # 使用新的进程管理服务
        proc, session_id = agent_process_service.get_or_create_process(
            project_id, employee, task, session
        )

        if not proc:
            if db_session:
                task_state_service.update_task_status(
                    db_session, task_id,
                    status="failed",
                    error="Failed to create agent process"
                )
            return {"dispatched": False, "error": "Failed to create agent process"}

        # 更新数据库状态
        if db_session:
            task_state_service.update_task_status(
                db_session, task_id,
                status="running",
                pid=proc.pid
            )

        return {"dispatched": True, "task_id": task_id, "process_id": proc.pid, "session_id": session_id}

    except Exception as e:
        if db_session:
            task_state_service.update_task_status(
                db_session, task_id,
                status="failed",
                error=str(e)
            )
        return {"dispatched": False, "error": str(e)}


def dispatch_task_async(session: Session, employee_id: str, task: str, project_id: str = None, todo_id: str = None) -> dict:
    """
    异步分配任务给 agent，立即返回，不等待执行结果

    Args:
        session: 数据库会话
        employee_id: 员工ID
        task: 任务描述
        project_id: 项目ID（用于获取工作空间和会话隔离）
        todo_id: 可选的 Todo ID，如果提供则更新 Todo 的 process_id 和 session_id

    Returns:
        {"success": True, "task_id": "xxx", "status": "dispatched"}
    """
    from nova_platform.services import agent_process_service
    from nova_platform.models import Todo

    employee = session.query(Employee).filter_by(id=employee_id).first()

    if not employee:
        return {"success": False, "error": "Employee not found"}

    if not project_id:
        return {"success": False, "error": "Project ID required for session isolation"}

    if employee.type not in ("openclaw", "hermes", "claude-code"):
        return {"success": False, "error": f"Employee type {employee.type} cannot execute tasks"}

    # 获取或创建进程（会话复用）
    proc, session_id = agent_process_service.get_or_create_process(
        project_id, employee, task, session
    )

    if not proc:
        return {"success": False, "error": "Failed to create agent process"}

    # 如果提供了 todo_id，更新 Todo 记录
    if todo_id:
        todo = session.query(Todo).filter_by(id=todo_id).first()
        if todo:
            todo.process_id = proc.pid
            todo.session_id = session_id
            todo.status = "in_progress"
            todo.agent_task_id = session_id  # 使用 session_id 作为 agent_task_id
            session.commit()

    return {
        "success": True,
        "process_id": proc.pid,
        "session_id": session_id,
        "status": "dispatched",
        "message": f"Task dispatched to {employee.type} agent {employee.name}"
    }


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
