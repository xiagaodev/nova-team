"""
Star Office UI 集成模块
将 Star Office UI 整合到 Nova Platform
"""

import os
import json
from datetime import datetime, timedelta
from flask import Blueprint, send_from_directory, jsonify, request, make_response, redirect

# Star Office 模块路径
STAR_OFFICE_ROOT = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'templates', 'star_office')
STAR_OFFICE_STATIC = os.path.join(STAR_OFFICE_ROOT, 'static')
STATE_FILE = os.path.join(STAR_OFFICE_ROOT, 'state.json')

# Canonical agent states
VALID_AGENT_STATES = frozenset({"idle", "writing", "researching", "executing", "syncing", "error"})
WORKING_STATES = frozenset({"writing", "researching", "executing"})
STATE_TO_AREA_MAP = {
    "idle": "breakroom",
    "writing": "writing",
    "researching": "writing",
    "executing": "writing",
    "syncing": "writing",
    "error": "error",
}

# Default state
DEFAULT_STATE = {
    "state": "idle",
    "detail": "等待任务中...",
    "progress": 0,
    "updated_at": datetime.now().isoformat()
}

DEFAULT_AGENTS = [
    {
        "agentId": "nova-star",
        "name": "Nova Star",
        "isMain": True,
        "state": "idle",
        "detail": "Nova Platform 虚拟助手",
        "updated_at": datetime.now().isoformat(),
        "area": "breakroom",
        "source": "local",
        "joinKey": None,
        "authStatus": "approved",
        "authExpiresAt": None,
        "lastPushAt": None
    }
]

AGENTS_STATE_FILE = os.path.join(STAR_OFFICE_ROOT, 'agents-state.json')

star_office_bp = Blueprint('star_office', __name__,
                           template_folder='templates',
                           static_folder=STAR_OFFICE_STATIC,
                           static_url_path='/')


def load_state():
    """加载状态，支持 auto-idle"""
    state = None
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                state = json.load(f)
        except Exception:
            state = None

    if not isinstance(state, dict):
        state = dict(DEFAULT_STATE)

    # Auto-idle 机制
    try:
        ttl = int(state.get("ttl_seconds", 300))
        updated_at = state.get("updated_at")
        s = state.get("state", "idle")
        if updated_at and s in WORKING_STATES:
            dt = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
            if dt.tzinfo:
                from datetime import timezone
                age = (datetime.now(timezone.utc) - dt.astimezone(timezone.utc)).total_seconds()
            else:
                age = (datetime.now() - dt).total_seconds()
            if age > ttl:
                state["state"] = "idle"
                state["detail"] = "待命中（自动回到休息区）"
                state["progress"] = 0
                state["updated_at"] = datetime.now().isoformat()
                try:
                    save_state(state)
                except Exception:
                    pass
    except Exception:
        pass

    return state


def save_state(state: dict):
    """保存状态到文件"""
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def load_agents_state():
    """加载 agents 状态"""
    if os.path.exists(AGENTS_STATE_FILE):
        try:
            with open(AGENTS_STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return DEFAULT_AGENTS


def save_agents_state(agents):
    """保存 agents 状态"""
    with open(AGENTS_STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(agents, f, ensure_ascii=False, indent=2)


# 初始化状态文件
if not os.path.exists(STATE_FILE):
    save_state(DEFAULT_STATE)
if not os.path.exists(AGENTS_STATE_FILE):
    save_agents_state(DEFAULT_AGENTS)


def normalize_agent_state(state: str) -> str:
    """规范化 agent 状态"""
    if state in VALID_AGENT_STATES:
        return state
    if state in ("offline", "unknown"):
        return "idle"
    return "idle"


# ============================================================================
# Star Office 路由
# ============================================================================

@star_office_bp.route("/")
def office_index():
    """Star Office 已整合到主页，重定向"""
    return redirect('/')


@star_office_bp.route("/status", methods=["GET"])
def get_status():
    """获取状态 - 与 /state 相同，供前端 game.js fetchStatus() 调用"""
    state = load_state()
    return jsonify(state)


@star_office_bp.route("/state", methods=["GET"])
def get_state():
    """获取当前状态"""
    state = load_state()
    return jsonify(state)


@star_office_bp.route("/set_state", methods=["POST"])
def set_state():
    """设置状态"""
    try:
        data = request.get_json()
        if not isinstance(data, dict):
            return jsonify({"status": "error", "msg": "invalid json"}), 400
        state = load_state()
        if "state" in data:
            s = data["state"]
            if s in VALID_AGENT_STATES:
                state["state"] = s
        if "detail" in data:
            state["detail"] = data["detail"]
        if "progress" in data:
            state["progress"] = data["progress"]
        state["updated_at"] = datetime.now().isoformat()
        save_state(state)
        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"status": "error", "msg": str(e)}), 500


@star_office_bp.route("/agents", methods=["GET"])
def get_agents():
    """获取 agents 列表"""
    agents = load_agents_state()
    now = datetime.now()

    cleaned_agents = []

    for a in agents:
        if a.get("isMain"):
            cleaned_agents.append(a)
            continue

        auth_expires_at_str = a.get("authExpiresAt")
        auth_status = a.get("authStatus", "pending")

        # 超时未批准自动 leave
        if auth_status == "pending" and auth_expires_at_str:
            try:
                auth_expires_at = datetime.fromisoformat(auth_expires_at_str)
                if now > auth_expires_at:
                    continue
            except Exception:
                pass

        # 超时未推送自动离线（超过5分钟）
        if auth_status == "approved" and a.get("lastPushAt"):
            try:
                last_push_at = datetime.fromisoformat(a.get("lastPushAt"))
                age = (now - last_push_at).total_seconds()
                if age > 300:
                    a["authStatus"] = "offline"
            except Exception:
                pass

        cleaned_agents.append(a)

    save_agents_state(cleaned_agents)

    return jsonify(cleaned_agents)


@star_office_bp.route("/agent-push", methods=["POST"])
def agent_push():
    """接收 agent 状态推送"""
    try:
        data = request.get_json()
        if not isinstance(data, dict):
            return jsonify({"ok": False, "msg": "invalid json"}), 400

        agent_id = (data.get("agentId") or "").strip()
        join_key = (data.get("joinKey") or "").strip()
        state = (data.get("state") or "").strip()
        detail = (data.get("detail") or "").strip()
        name = (data.get("name") or "").strip()

        if not agent_id or not state:
            return jsonify({"ok": False, "msg": "缺少 agentId/state"}), 400

        state = normalize_agent_state(state)

        agents = load_agents_state()
        target = next((a for a in agents if a.get("agentId") == agent_id and not a.get("isMain")), None)

        if target:
            target["state"] = state
            target["detail"] = detail or target.get("detail", "")
            target["area"] = STATE_TO_AREA_MAP.get(state, "breakroom")
            target["lastPushAt"] = datetime.now().isoformat()
            if name:
                target["name"] = name
        else:
            # 自动创建新 agent
            new_agent = {
                "agentId": agent_id,
                "name": name or agent_id,
                "isMain": False,
                "state": state,
                "detail": detail or "",
                "updated_at": datetime.now().isoformat(),
                "area": STATE_TO_AREA_MAP.get(state, "breakroom"),
                "source": "push",
                "joinKey": join_key or None,
                "authStatus": "approved",
                "authExpiresAt": (datetime.now() + timedelta(hours=24)).isoformat(),
                "lastPushAt": datetime.now().isoformat()
            }
            agents.append(new_agent)

        save_agents_state(agents)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "msg": str(e)}), 500


@star_office_bp.route("/yesterday-memo", methods=["GET"])
def get_yesterday_memo():
    """获取昨日小记"""
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    return jsonify({
        "success": True,
        "date": yesterday,
        "memo": "昨日暂无记录"
    })
