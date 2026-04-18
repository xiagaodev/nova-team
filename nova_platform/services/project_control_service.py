"""
Project Control Service - 项目控制服务

功能：
1. 暂停项目 - 停止所有正在进行的任务，保存状态
2. 恢复项目 - 恢复项目状态，允许任务继续执行
3. 获取项目控制状态
"""

from datetime import datetime
from typing import Dict, List
from sqlalchemy.orm import Session

from nova_platform.models import Project, Todo, AsyncTaskState
from nova_platform.services import task_state_service


def pause_project(session: Session, project_id: str) -> dict:
    """
    暂停项目

    流程：
    1. 将项目状态设为 paused
    2. 找到所有 in_progress 的任务
    3. 取消所有正在运行的 agent 进程
    4. 将任务状态保存为 paused（保存在 output 字段）
    5. 更新 Todo 状态为 paused

    Args:
        session: 数据库会话
        project_id: 项目ID

    Returns:
        {
            "success": bool,
            "message": str,
            "paused_todos": int,
            "cancelled_tasks": int,
            "details": List[dict]
        }
    """
    project = session.query(Project).filter_by(id=project_id).first()
    if not project:
        return {"success": False, "message": "Project not found"}

    if project.status == "paused":
        return {"success": False, "message": "Project is already paused"}

    # 获取所有进行中的任务
    in_progress_todos = session.query(Todo).filter(
        Todo.project_id == project_id,
        Todo.status == "in_progress"
    ).all()

    paused_count = 0
    cancelled_count = 0
    details = []

    # 保存每个任务的当前状态并取消
    for todo in in_progress_todos:
        detail = {
            "todo_id": todo.id,
            "title": todo.title,
            "assignee_id": todo.assignee_id,
            "agent_task_id": todo.agent_task_id,
            "paused": False,
            "cancelled": False
        }

        # 保存当前状态到 Todo 的描述中（作为临时存储）
        state_snapshot = {
            "paused_at": datetime.utcnow().isoformat(),
            "original_status": "in_progress",
            "assignee_id": todo.assignee_id,
            "agent_task_id": todo.agent_task_id
        }

        # 如果有 agent_task_id，尝试取消进程
        if todo.agent_task_id:
            task_info = task_state_service.get_task_status(session, todo.agent_task_id)
            if task_info and task_info.get("status") == "running":
                # 取消任务
                cancel_result = task_state_service.cancel_task(session, todo.agent_task_id)
                if cancel_result:
                    detail["cancelled"] = True
                    cancelled_count += 1

        # 更新 Todo 状态为 paused
        # 将状态快照保存到 description 前面
        import json
        snapshot_text = f"\n\n--- PAUSED STATE ---\n{json.dumps(state_snapshot)}\n"
        todo.description = snapshot_text + (todo.description or "")
        todo.status = "paused"
        todo.updated_at = datetime.utcnow()

        detail["paused"] = True
        paused_count += 1
        details.append(detail)

    # 更新项目状态
    project.status = "paused"
    project.updated_at = datetime.utcnow()
    session.commit()

    return {
        "success": True,
        "message": f"Project paused. {paused_count} tasks paused, {cancelled_count} agent tasks cancelled.",
        "paused_todos": paused_count,
        "cancelled_tasks": cancelled_count,
        "details": details
    }


def resume_project(session: Session, project_id: str) -> dict:
    """
    恢复项目

    流程：
    1. 将项目状态设为 active
    2. 找到所有 paused 的任务
    3. 恢复任务状态到 in_progress
    4. 如果任务有 assignee，可以重新分发

    Args:
        session: 数据库会话
        project_id: 项目ID

    Returns:
        {
            "success": bool,
            "message": str,
            "resumed_todos": int,
            "details": List[dict]
        }
    """
    project = session.query(Project).filter_by(id=project_id).first()
    if not project:
        return {"success": False, "message": "Project not found"}

    if project.status != "paused":
        return {"success": False, "message": "Project is not paused"}

    # 获取所有暂停的任务
    paused_todos = session.query(Todo).filter(
        Todo.project_id == project_id,
        Todo.status == "paused"
    ).all()

    resumed_count = 0
    details = []

    import json

    for todo in paused_todos:
        detail = {
            "todo_id": todo.id,
            "title": todo.title,
            "assignee_id": todo.assignee_id,
            "resumed": False
        }

        # 从 description 中提取并移除暂停状态快照
        if todo.description and "--- PAUSED STATE ---" in todo.description:
            parts = todo.description.split("--- PAUSED STATE ---\n", 1)
            if len(parts) > 1:
                snapshot_part = parts[1].split("\n", 1)[0]
                try:
                    snapshot = json.loads(snapshot_part)
                    # 恢复 assignee
                    if snapshot.get("assignee_id"):
                        todo.assignee_id = snapshot["assignee_id"]
                    # agent_task_id 不再有效，需要重新分发时生成
                    todo.agent_task_id = None
                except json.JSONDecodeError:
                    pass
                # 恢复原始描述
                todo.description = parts[1].split("\n", 1)[1] if len(parts[1].split("\n", 1)) > 1 else ""

        # 恢复任务状态为 pending（等待重新分配）
        todo.status = "pending"
        todo.updated_at = datetime.utcnow()

        detail["resumed"] = True
        resumed_count += 1
        details.append(detail)

    # 更新项目状态
    project.status = "active"
    project.updated_at = datetime.utcnow()
    session.commit()

    return {
        "success": True,
        "message": f"Project resumed. {resumed_count} tasks restored to pending.",
        "resumed_todos": resumed_count,
        "details": details
    }


def get_project_control_status(session: Session, project_id: str) -> dict:
    """
    获取项目控制状态

    Args:
        session: 数据库会话
        project_id: 项目ID

    Returns:
        {
            "project_id": str,
            "project_name": str,
            "status": str,
            "paused_todos": int,
            "in_progress_todos": int,
            "running_agents": int,
            "can_pause": bool,
            "can_resume": bool
        }
    """
    project = session.query(Project).filter_by(id=project_id).first()
    if not project:
        return {"success": False, "error": "Project not found"}

    # 统计任务
    paused_todos = session.query(Todo).filter(
        Todo.project_id == project_id,
        Todo.status == "paused"
    ).count()

    in_progress_todos = session.query(Todo).filter(
        Todo.project_id == project_id,
        Todo.status == "in_progress"
    ).count()

    # 统计正在运行的 agent
    running_agents = 0
    if in_progress_todos > 0:
        todos = session.query(Todo).filter(
            Todo.project_id == project_id,
            Todo.status == "in_progress"
        ).all()
        for todo in todos:
            if todo.agent_task_id:
                task_info = task_state_service.get_task_status(session, todo.agent_task_id)
                if task_info and task_info.get("status") == "running":
                    running_agents += 1

    return {
        "success": True,
        "project_id": project.id,
        "project_name": project.name,
        "status": project.status,
        "paused_todos": paused_todos,
        "in_progress_todos": in_progress_todos,
        "running_agents": running_agents,
        "can_pause": project.status == "active",
        "can_resume": project.status == "paused"
    }


def list_paused_projects(session: Session) -> List[dict]:
    """
    列出所有暂停的项目

    Args:
        session: 数据库会话

    Returns:
        [{"project": Project, "paused_todos": int, "paused_at": datetime}, ...]
    """
    projects = session.query(Project).filter_by(status="paused").all()

    result = []
    for project in projects:
        paused_count = session.query(Todo).filter(
            Todo.project_id == project.id,
            Todo.status == "paused"
        ).count()

        # 获取最后暂停时间（从 updated_at 推断）
        result.append({
            "project": project,
            "paused_todos": paused_count,
            "paused_at": project.updated_at
        })

    return result


def force_stop_project(session: Session, project_id: str) -> dict:
    """
    强制停止项目（比 pause 更激进）

    与 pause 的区别：
    - pause: 保存状态，可以恢复
    - force_stop: 不保存状态，直接停止，任务需要重新分配

    Args:
        session: 数据库会话
        project_id: 项目ID

    Returns:
        {"success": bool, "message": str, ...}
    """
    project = session.query(Project).filter_by(id=project_id).first()
    if not project:
        return {"success": False, "message": "Project not found"}

    # 获取所有进行中和暂停的任务
    active_todos = session.query(Todo).filter(
        Todo.project_id == project_id,
        Todo.status.in_(["in_progress", "paused"])
    ).all()

    stopped_count = 0
    cancelled_count = 0

    for todo in active_todos:
        # 取消 agent 任务
        if todo.agent_task_id:
            cancel_result = task_state_service.cancel_task(session, todo.agent_task_id)
            if cancel_result:
                cancelled_count += 1

        # 重置任务为 pending
        todo.status = "pending"
        todo.assignee_id = None
        todo.agent_task_id = None
        todo.updated_at = datetime.utcnow()
        stopped_count += 1

    # 更新项目状态
    project.status = "paused"
    project.updated_at = datetime.utcnow()
    session.commit()

    return {
        "success": True,
        "message": f"Project force stopped. {stopped_count} tasks reset, {cancelled_count} agent tasks cancelled.",
        "stopped_todos": stopped_count,
        "cancelled_tasks": cancelled_count
    }
