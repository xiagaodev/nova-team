"""
Agent Session Service - Agent 会话管理服务

确保不同项目的 agent 调用使用独立的会话和上下文
"""

import os
import json
from pathlib import Path
from typing import Optional, Dict
from datetime import datetime

from nova_platform.services import project_service


def get_project_session_dir(project_id: str) -> Path:
    """
    获取项目的 agent 会话目录

    Args:
        project_id: 项目ID

    Returns:
        会话目录路径
    """
    from nova_platform.database import get_session
    from nova_platform.models import Project

    # 获取项目工作空间
    session = get_session()
    project = session.query(Project).filter_by(id=project_id).first()

    if project and project.workspace_path:
        session_dir = Path(project.workspace_path) / ".nova" / "sessions"
    else:
        # 回退到全局目录
        session_dir = Path.home() / ".nova-platform" / "sessions" / project_id

    session_dir.mkdir(parents=True, exist_ok=True)
    return session_dir


def prepare_openclaw_session(project_id: str, agent_id: str) -> Dict:
    """
    为 OpenClaw agent 准备项目会话

    Args:
        project_id: 项目ID
        agent_id: OpenClaw agent ID

    Returns:
        会话配置信息
    """
    session_dir = get_project_session_dir(project_id)
    agent_session_dir = session_dir / f"openclaw_{agent_id}"
    agent_session_dir.mkdir(exist_ok=True)

    # 创建项目上下文文件
    context_file = agent_session_dir / "project_context.json"
    context = {
        "project_id": project_id,
        "agent_id": agent_id,
        "created_at": datetime.utcnow().isoformat()
    }

    with open(context_file, "w") as f:
        json.dump(context, f, indent=2)

    return {
        "session_dir": str(agent_session_dir),
        "context_file": str(context_file),
        "workspace_root": str(session_dir)
    }


def prepare_hermes_session(project_id: str, profile_name: str) -> Dict:
    """
    为 Hermes agent 准备项目会话

    Args:
        project_id: 项目ID
        profile_name: Hermes profile 名称

    Returns:
        会话配置信息
    """
    session_dir = get_project_session_dir(project_id)
    agent_session_dir = session_dir / f"hermes_{profile_name}"
    agent_session_dir.mkdir(exist_ok=True)

    # 创建项目上下文文件
    context_file = agent_session_dir / "project_context.json"
    context = {
        "project_id": project_id,
        "profile_name": profile_name,
        "created_at": datetime.utcnow().isoformat()
    }

    with open(context_file, "w") as f:
        json.dump(context, f, indent=2)

    # 创建对话历史文件
    history_file = agent_session_dir / "conversation_history.json"
    if not history_file.exists():
        with open(history_file, "w") as f:
            json.dump([], f)

    return {
        "session_dir": str(agent_session_dir),
        "context_file": str(context_file),
        "history_file": str(history_file)
    }


def prepare_claude_code_session(project_id: str, agent_id: str) -> Dict:
    """
    为 Claude Code agent 准备项目会话

    Args:
        project_id: 项目ID
        agent_id: Claude Code agent 内部 ID

    Returns:
        会话配置信息
    """
    session_dir = get_project_session_dir(project_id)
    agent_session_dir = session_dir / f"claude_{agent_id}"
    agent_session_dir.mkdir(exist_ok=True)

    # 创建 .claude 目录（Claude Code 的工作目录）
    claude_dir = agent_session_dir / ".claude"
    claude_dir.mkdir(exist_ok=True)

    # 创建项目上下文文件
    context_file = claude_dir / "project_context.json"
    context = {
        "project_id": project_id,
        "agent_id": agent_id,
        "created_at": datetime.utcnow().isoformat()
    }

    with open(context_file, "w") as f:
        json.dump(context, f, indent=2)

    # 创建对话历史文件
    history_file = claude_dir / "history.json"
    if not history_file.exists():
        with open(history_file, "w") as f:
            json.dump([], f)

    return {
        "session_dir": str(agent_session_dir),
        "claude_dir": str(claude_dir),
        "context_file": str(context_file),
        "history_file": str(history_file)
    }


def get_session_context(project_id: str, agent_id: str, agent_type: str) -> Dict:
    """
    获取项目的 agent 会话上下文

    Args:
        project_id: 项目ID
        agent_id: Agent ID
        agent_type: Agent 类型

    Returns:
        会话上下文信息
    """
    session_dir = get_project_session_dir(project_id)

    if agent_type == "openclaw":
        agent_session_dir = session_dir / f"openclaw_{agent_id}"
        context_file = agent_session_dir / "project_context.json"

    elif agent_type == "hermes":
        agent_session_dir = session_dir / f"hermes_{agent_id}"
        context_file = agent_session_dir / "project_context.json"

    elif agent_type == "claude-code":
        agent_session_dir = session_dir / f"claude_{agent_id}"
        context_file = agent_session_dir / ".claude" / "project_context.json"

    else:
        return {}

    if context_file.exists():
        try:
            with open(context_file, "r") as f:
                return json.load(f)
        except:
            return {}

    return {}


def append_conversation_history(project_id: str, agent_id: str, agent_type: str,
                              user_message: str, agent_response: str):
    """
    追加对话历史

    Args:
        project_id: 项目ID
        agent_id: Agent ID
        agent_type: Agent 类型
        user_message: 用户消息
        agent_response: Agent 响应
    """
    session_dir = get_project_session_dir(project_id)

    if agent_type == "hermes":
        history_file = session_dir / f"hermes_{agent_id}" / "conversation_history.json"
    elif agent_type == "claude-code":
        history_file = session_dir / f"claude_{agent_id}" / ".claude" / "history.json"
    else:
        return

    try:
        if history_file.exists():
            with open(history_file, "r") as f:
                history = json.load(f)
        else:
            history = []

        history.append({
            "timestamp": datetime.utcnow().isoformat(),
            "user_message": user_message,
            "agent_response": agent_response
        })

        # 只保留最近 50 条对话
        history = history[-50:]

        with open(history_file, "w") as f:
            json.dump(history, f, indent=2)
    except Exception:
        pass


def clear_project_sessions(project_id: str) -> int:
    """
    清空项目的所有 agent 会话

    Args:
        project_id: 项目ID

    Returns:
        删除的会话数
    """
    session_dir = get_project_session_dir(project_id)

    if not session_dir.exists():
        return 0

    count = 0
    for item in session_dir.iterdir():
        if item.is_dir():
            import shutil
            shutil.rmtree(item)
            count += 1

    return count


def get_project_session_info(project_id: str) -> Dict:
    """
    获取项目的会话信息

    Args:
        project_id: 项目ID

    Returns:
        会话信息统计
    """
    session_dir = get_project_session_dir(project_id)

    if not session_dir.exists():
        return {"exists": False, "sessions": []}

    sessions = []
    for item in session_dir.iterdir():
        if item.is_dir():
            sessions.append({
                "name": item.name,
                "path": str(item)
            })

    return {
        "exists": True,
        "session_dir": str(session_dir),
        "sessions": sessions,
        "count": len(sessions)
    }
