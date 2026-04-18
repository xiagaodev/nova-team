"""
Project Log Service - 项目日志服务

记录 automation 循环中的输出内容，支持实时查看
"""

import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from nova_platform.services import project_service


def get_project_log_path(project_id: str) -> str:
    """
    获取项目日志文件路径

    Args:
        project_id: 项目ID

    Returns:
        日志文件路径
    """
    # 默认使用项目工作空间
    workspace_root = Path.home() / ".nova" / "workspaces"
    workspace = workspace_root / project_id
    log_dir = workspace / ".nova"

    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        return str(log_dir / "automation.log")
    except Exception:
        # 回退到全局日志目录
        log_dir = Path.home() / ".nova-platform" / "logs" / "projects"
        log_dir.mkdir(parents=True, exist_ok=True)
        return str(log_dir / f"{project_id}.log")


def log_project_event(
    project_id: str,
    event_type: str,
    message: str,
    details: dict = None
):
    """
    记录项目事件到日志

    Args:
        project_id: 项目ID
        event_type: 事件类型 (cycle, action, decision, error, etc.)
        message: 日志消息
        details: 额外详情（会作为 JSON 记录）
    """
    log_path = get_project_log_path(project_id)

    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

    # 构建日志行
    log_parts = [
        f"[{timestamp}]",
        f"[{event_type.upper()}]",
        message
    ]

    if details:
        import json
        try:
            details_str = json.dumps(details, ensure_ascii=False)
            log_parts.append(f"| {details_str}")
        except:
            pass

    log_line = " ".join(log_parts) + "\n"

    # 写入日志文件
    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(log_line)
    except Exception as e:
        # 静默失败，避免影响主流程
        pass


def log_iteration_start(project_id: str, observation: dict):
    """记录迭代开始"""
    status = observation.get("status_summary", {})
    log_project_event(
        project_id,
        "cycle",
        f"Iteration started - {status.get('total', 0)} tasks, "
        f"{status.get('pending', 0)} pending, {status.get('in_progress', 0)} in progress"
    )


def log_iteration_action(project_id: str, action: dict):
    """记录迭代行动"""
    action_type = action.get("action", "unknown")
    log_project_event(
        project_id,
        "action",
        f"Action: {action_type}",
        details=action
    )


def log_iteration_leader(project_id: str, triggered: bool, decisions: list):
    """记录 Leader 介入"""
    if triggered:
        log_project_event(
            project_id,
            "leader",
            f"Leader triggered - {len(decisions)} decisions",
            details={"decisions": decisions}
        )
    else:
        log_project_event(
            project_id,
            "leader",
            "Leader not triggered"
        )


def log_iteration_end(project_id: str, result: dict):
    """记录迭代结束"""
    actions_count = len(result.get("actions", []))
    leader_triggered = result.get("leader_triggered", False)

    log_project_event(
        project_id,
        "cycle",
        f"Iteration completed - {actions_count} actions, leader: {leader_triggered}"
    )


def log_project_error(project_id: str, error: str, context: dict = None):
    """记录项目错误"""
    log_project_event(
        project_id,
        "error",
        error,
        details=context
    )


def get_project_logs(project_id: str, lines: int = 100) -> list:
    """
    获取项目日志

    Args:
        project_id: 项目ID
        lines: 返回的行数

    Returns:
        日志行列表（最新的在前）
    """
    log_path = get_project_log_path(project_id)

    if not os.path.exists(log_path):
        return []

    try:
        with open(log_path, "r", encoding="utf-8") as f:
            all_lines = f.readlines()

        # 返回最后 N 行
        return all_lines[-lines:] if len(all_lines) > lines else all_lines
    except Exception:
        return []


def follow_project_logs(project_id: str, callback=None):
    """
    实时跟踪项目日志（类似 tail -f）

    Args:
        project_id: 项目ID
        callback: 每次有新日志时调用的函数，接收日志行作为参数

    Yields:
        新的日志行
    """
    log_path = get_project_log_path(project_id)

    if not os.path.exists(log_path):
        # 等待文件创建
        import time
        for _ in range(30):  # 等待最多 30 秒
            time.sleep(0.1)
            if os.path.exists(log_path):
                break
        else:
            return

    # 首先显示现有内容
    with open(log_path, "r", encoding="utf-8") as f:
        for line in f:
            if callback:
                callback(line.rstrip())
            else:
                yield line.rstrip()

    # 监控新内容
    last_size = os.path.getsize(log_path)

    import time
    try:
        while True:
            time.sleep(0.1)
            current_size = os.path.getsize(log_path)

            if current_size > last_size:
                with open(log_path, "r", encoding="utf-8") as f:
                    f.seek(last_size)
                    new_lines = f.readlines()

                for line in new_lines:
                    if callback:
                        callback(line.rstrip())
                    else:
                        yield line.rstrip()

                last_size = current_size
    except KeyboardInterrupt:
        return


def clear_project_logs(project_id: str) -> bool:
    """
    清空项目日志

    Args:
        project_id: 项目ID

    Returns:
        是否成功
    """
    log_path = get_project_log_path(project_id)

    try:
        if os.path.exists(log_path):
            open(log_path, "w").close()
        return True
    except Exception:
        return False


def get_project_log_stats(project_id: str) -> dict:
    """
    获取项目日志统计信息

    Args:
        project_id: 项目ID

    Returns:
        统计信息字典
    """
    log_path = get_project_log_path(project_id)

    if not os.path.exists(log_path):
        return {
            "exists": False,
            "lines": 0,
            "size_bytes": 0
        }

    try:
        with open(log_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        # 统计各类事件
        event_counts = {}
        for line in lines:
            if "] [" in line:
                try:
                    event_type = line.split("] [")[1].split("]")[0].lower()
                    event_counts[event_type] = event_counts.get(event_type, 0) + 1
                except:
                    pass

        return {
            "exists": True,
            "lines": len(lines),
            "size_bytes": os.path.getsize(log_path),
            "event_counts": event_counts,
            "last_modified": datetime.fromtimestamp(os.path.getmtime(log_path)).isoformat()
        }
    except Exception:
        return {
            "exists": True,
            "lines": 0,
            "size_bytes": 0,
            "error": "Failed to read log"
        }
