"""
Task State Service - 异步任务状态管理服务

替代原有的文件系统存储，使用数据库存储异步任务状态。
支持跨平台、并发安全和数据持久化。
"""

import json
import uuid
from datetime import datetime
from typing import Optional, Dict, List
from sqlalchemy.orm import Session

from nova_platform.models import AsyncTaskState, Todo


def create_async_task(
    session: Session,
    employee_id: str,
    todo_id: Optional[str] = None
) -> AsyncTaskState:
    """创建新的异步任务记录"""
    task = AsyncTaskState(
        id=str(uuid.uuid4()),
        status="running",
        employee_id=employee_id,
        todo_id=todo_id,
        started_at=datetime.utcnow()
    )
    session.add(task)
    session.commit()
    session.refresh(task)
    return task


def update_task_status(
    session: Session,
    task_id: str,
    status: str,
    output: str = "",
    error: str = "",
    pid: Optional[int] = None
) -> Optional[AsyncTaskState]:
    """更新任务状态"""
    task = session.query(AsyncTaskState).filter_by(id=task_id).first()
    if not task:
        return None

    task.status = status
    task.output = output
    task.error = error

    if pid is not None:
        task.pid = pid

    if status in ["completed", "failed", "cancelled"]:
        task.completed_at = datetime.utcnow()

    session.commit()
    session.refresh(task)
    return task


def get_task_status(session: Session, task_id: str) -> Optional[Dict]:
    """获取任务状态"""
    task = session.query(AsyncTaskState).filter_by(id=task_id).first()
    if not task:
        return None

    # 检查进程是否还在运行
    if task.status == "running" and task.pid:
        is_running = check_process_running(task.pid)
        if not is_running:
            # 进程已结束但状态未更新，自动修正
            task.status = "completed"
            task.completed_at = datetime.utcnow()
            session.commit()

    return {
        "id": task.id,
        "status": task.status,
        "pid": task.pid,
        "output": task.output,
        "error": task.error,
        "started_at": task.started_at.isoformat() if task.started_at else None,
        "completed_at": task.completed_at.isoformat() if task.completed_at else None,
        "employee_id": task.employee_id,
        "todo_id": task.todo_id,
        "duration_seconds": (
            (task.completed_at - task.started_at).total_seconds()
            if task.completed_at and task.started_at
            else None
        )
    }


def get_employee_tasks(
    session: Session,
    employee_id: str,
    status: Optional[str] = None
) -> List[AsyncTaskState]:
    """获取员工的所有任务"""
    query = session.query(AsyncTaskState).filter_by(employee_id=employee_id)
    if status:
        query = query.filter_by(status=status)
    return query.order_by(AsyncTaskState.started_at.desc()).all()


def get_todo_tasks(
    session: Session,
    todo_id: str
) -> List[AsyncTaskState]:
    """获取Todo关联的所有任务"""
    return session.query(AsyncTaskState).filter_by(
        todo_id=todo_id
    ).order_by(AsyncTaskState.started_at.desc()).all()


def cleanup_old_tasks(session: Session, days: int = 7) -> int:
    """清理旧的任务记录"""
    from sqlalchemy import delete

    cutoff_date = datetime.utcnow() - timedelta(days=days)
    stmt = delete(AsyncTaskState).where(
        AsyncTaskState.completed_at < cutoff_date
    )
    result = session.execute(stmt)
    session.commit()
    return result.rowcount


def cancel_task(session: Session, task_id: str) -> Optional[Dict]:
    """取消任务"""
    task = session.query(AsyncTaskState).filter_by(id=task_id).first()
    if not task:
        return None

    # 尝试终止进程
    if task.pid:
        try:
            terminate_process(task.pid)
        except Exception:
            pass  # 进程可能已经结束

    task.status = "cancelled"
    task.completed_at = datetime.utcnow()
    session.commit()
    session.refresh(task)

    return {
        "id": task.id,
        "status": task.status
    }


def check_todo_agent_status(
    session: Session,
    todo_id: str,
    auto_commit: bool = True
) -> Dict:
    """检查Todo对应的agent任务是否完成

    流程：
    1. 查找Todo的agent_task_id
    2. 从数据库获取任务状态
    3. 如果任务完成，更新Todo状态

    Args:
        session: 数据库session
        todo_id: Todo ID
        auto_commit: 是否自动提交

    Returns:
        {"status": "running|completed|failed|unknown", "todo_updated": bool}
    """
    todo = session.query(Todo).filter_by(id=todo_id).first()
    if not todo:
        return {"status": "unknown", "error": "Todo not found", "todo_updated": False}

    if not todo.agent_task_id:
        return {"status": "unknown", "error": "No agent task", "todo_updated": False}

    task_info = get_task_status(session, todo.agent_task_id)
    if not task_info:
        # 任务不存在，可能已完成但记录被清理
        if todo.status == "in_progress":
            todo.status = "completed"
            todo.updated_at = datetime.utcnow()
            if auto_commit:
                session.commit()
            return {"status": "completed", "todo_updated": True, "message": "Task record missing, auto-completed"}
        return {"status": "unknown", "error": "Task not found", "todo_updated": False}

    if task_info["status"] == "running":
        return {"status": "running", "todo_updated": False}

    if task_info["status"] == "completed":
        if todo.status != "completed":
            todo.status = "completed"
            todo.updated_at = datetime.utcnow()
            if auto_commit:
                session.commit()
            return {"status": "completed", "todo_updated": True}
        return {"status": "completed", "todo_updated": False}

    elif task_info["status"] == "failed":
        if todo.status != "pending":
            todo.status = "pending"
            todo.assignee_id = None
            todo.updated_at = datetime.utcnow()
            if auto_commit:
                session.commit()
            return {"status": "failed", "todo_updated": True, "message": "Task failed, reset to pending"}
        return {"status": "failed", "todo_updated": False}

    return {"status": task_info["status"], "todo_updated": False}


# ============================================================================
# 进程管理（跨平台兼容）
# ============================================================================

def check_process_running(pid: int) -> bool:
    """检查进程是否在运行（跨平台兼容）"""
    try:
        import psutil
        proc = psutil.Process(pid)
        return proc.is_running()
    except ImportError:
        # 回退到os方法（不兼容Windows）
        import os
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False
    except Exception:
        return False


def terminate_process(pid: int) -> bool:
    """终止进程（跨平台兼容）"""
    try:
        import psutil
        proc = psutil.Process(pid)
        proc.terminate()
        proc.wait(timeout=5)
        return True
    except ImportError:
        # 回退到os方法
        import os
        import signal
        try:
            os.kill(pid, signal.SIGTERM)
            return True
        except Exception:
            return False
    except Exception:
        return False


# ============================================================================
# 统计和报告
# ============================================================================

def get_task_statistics(session: Session, employee_id: Optional[str] = None) -> Dict:
    """获取任务统计信息"""
    query = session.query(AsyncTaskState)
    if employee_id:
        query = query.filter_by(employee_id=employee_id)

    all_tasks = query.all()

    stats = {
        "total": len(all_tasks),
        "running": 0,
        "completed": 0,
        "failed": 0,
        "cancelled": 0,
        "average_duration_seconds": 0
    }

    total_duration = 0
    completed_count = 0

    for task in all_tasks:
        stats[task.status] = stats.get(task.status, 0) + 1

        if task.status == "completed" and task.started_at and task.completed_at:
            duration = (task.completed_at - task.started_at).total_seconds()
            total_duration += duration
            completed_count += 1

    if completed_count > 0:
        stats["average_duration_seconds"] = total_duration / completed_count

    return stats


def get_stuck_tasks(session: Session, timeout_minutes: int = 30) -> List[Dict]:
    """获取卡住的任务（运行时间过长的任务）"""
    from datetime import timedelta

    timeout = datetime.utcnow() - timedelta(minutes=timeout_minutes)
    stuck_tasks = session.query(AsyncTaskState).filter(
        AsyncTaskState.status == "running",
        AsyncTaskState.started_at < timeout
    ).all()

    return [
        {
            "id": t.id,
            "employee_id": t.employee_id,
            "todo_id": t.todo_id,
            "started_at": t.started_at.isoformat(),
            "duration_minutes": (datetime.utcnow() - t.started_at).total_seconds() / 60,
            "pid": t.pid
        }
        for t in stuck_tasks
    ]
