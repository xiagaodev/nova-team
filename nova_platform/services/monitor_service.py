"""
Monitor Service - 定时检查任务状态并自动恢复卡住的任务
由 cron job 定期调用
"""

import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from nova_platform.database import init_db, get_session
from nova_platform.models import Todo, Employee
from nova_platform.services.agent_service import (
    check_todo_agent_status,
    check_agent_process_status,
    _load_task_state
)


def check_and_recover_stuck_tasks() -> dict:
    """
    检查所有 in_progress 的任务，恢复卡住的任务
    
    Returns:
        {
            "checked": int,      # 检查的任务数
            "recovered": int,    # 恢复的任务数
            "details": [...]    # 详细结果
        }
    """
    init_db()
    session = get_session()
    
    # 查找所有 in_progress 的任务
    in_progress_todos = session.query(Todo).filter_by(status="in_progress").all()
    
    results = {
        "checked": len(in_progress_todos),
        "recovered": 0,
        "details": []
    }
    
    # 统一收集需要更新的操作
    todos_to_update = []  # [(todo_id, new_status, new_assignee_id), ...]
    
    for todo in in_progress_todos:
        detail = {
            "todo_id": todo.id,
            "title": todo.title,
            "agent_task_id": todo.agent_task_id,
            "action": None,
            "message": None
        }
        
        if todo.agent_task_id:
            # 有 agent_task_id，使用 agent_service 检查（不 commit）
            status_result = check_todo_agent_status(session, todo.id, auto_commit=False)
            
            if status_result.get("todo_updated"):
                detail["action"] = "updated"
                detail["message"] = status_result.get("message", f"Status changed to {status_result.get('status')}")
                results["recovered"] += 1
            else:
                detail["action"] = "unchanged"
                detail["message"] = f"Still {status_result.get('status')}"
        else:
            # 没有 agent_task_id，检查是否超时（比如超过 30 分钟）
            if todo.updated_at:
                elapsed = (datetime.utcnow() - todo.updated_at.replace(tzinfo=None)).total_seconds()
                if elapsed > 1800:  # 30 分钟
                    # 收集超时任务，稍后统一更新
                    todos_to_update.append((todo.id, "pending", None))
                    detail["action"] = "timeout_recovered"
                    detail["message"] = f"Task timed out after {int(elapsed/60)} minutes"
                    results["recovered"] += 1
                else:
                    detail["action"] = "waiting"
                    detail["message"] = f"Waiting for {int(elapsed/60)} minutes"
        
        results["details"].append(detail)
    
    # 统一执行更新并 commit
    for todo_id, new_status, new_assignee_id in todos_to_update:
        todo = session.query(Todo).filter_by(id=todo_id).first()
        if todo:
            todo.status = new_status
            todo.assignee_id = new_assignee_id
            todo.updated_at = datetime.utcnow()
    
    if todos_to_update:
        session.commit()
    
    return results


def get_system_health() -> dict:
    """
    获取系统健康状态
    
    Returns:
        {
            "employees_total": int,
            "employees_online": int,  # 有活跃任务的员工
            "todos_pending": int,
            "todos_in_progress": int,
            "todos_completed": int,
            "stuck_tasks": int  # 卡住的任务数
        }
    """
    init_db()
    session = get_session()
    
    employees = session.query(Employee).all()
    todos = session.query(Todo).all()
    
    pending = [t for t in todos if t.status == "pending"]
    in_progress = [t for t in todos if t.status == "in_progress"]
    completed = [t for t in todos if t.status == "completed"]
    
    # 检查卡住的任务（in_progress 但 agent 进程已结束）
    stuck_count = 0
    for todo in in_progress:
        if todo.agent_task_id:
            task_info = _load_task_state(todo.agent_task_id)
            if task_info.get("status") == "running":
                pid = task_info.get("pid")
                if pid:
                    status = check_agent_process_status(pid)
                    if status in ("dead", "zombie"):
                        stuck_count += 1
    
    return {
        "employees_total": len(employees),
        "employees_online": len(set(t.assignee_id for t in in_progress if t.assignee_id)),
        "todos_pending": len(pending),
        "todos_in_progress": len(in_progress),
        "todos_completed": len(completed),
        "stuck_tasks": stuck_count
    }


if __name__ == "__main__":
    import json
    
    print("=== Nova Platform 健康检查 ===")
    print(f"时间: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC")
    print()
    
    # 系统健康
    health = get_system_health()
    print("📊 系统状态:")
    print(f"   员工总数: {health['employees_total']}")
    print(f"   活跃员工: {health['employees_online']}")
    print(f"   待处理任务: {health['todos_pending']}")
    print(f"   进行中: {health['todos_in_progress']}")
    print(f"   已完成: {health['todos_completed']}")
    print(f"   卡住任务: {health['stuck_tasks']}")
    print()
    
    # 任务检查与恢复
    print("🔍 检查卡住的任务...")
    result = check_and_recover_stuck_tasks()
    print(f"   检查了 {result['checked']} 个进行中的任务")
    print(f"   恢复了 {result['recovered']} 个任务")
    
    if result['details']:
        print()
        for d in result['details']:
            emoji = "✅" if d['action'] in ("updated", "timeout_recovered") else "⏳" if d['action'] == "waiting" else "🔄"
            print(f"   {emoji} {d['title'][:40]}: {d['message']}")
    
    print()
    print(json.dumps(result, indent=2, default=str))
