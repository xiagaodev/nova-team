"""
Star Office UI 集成模块
将 Star Office UI 作为子路由 /office/ 挂载到 Nova Platform
"""

import os
import json
from datetime import datetime, timedelta
from flask import Blueprint, send_from_directory, jsonify, request, make_response, session

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
JOIN_KEYS_FILE = os.path.join(STAR_OFFICE_ROOT, 'join-keys.json')

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


def load_join_keys():
    """加载 join keys"""
    if os.path.exists(JOIN_KEYS_FILE):
        try:
            with open(JOIN_KEYS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"keys": []}


def save_join_keys(data):
    """保存 join keys"""
    with open(JOIN_KEYS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# 初始化状态文件
if not os.path.exists(STATE_FILE):
    save_state(DEFAULT_STATE)
if not os.path.exists(AGENTS_STATE_FILE):
    save_agents_state(DEFAULT_AGENTS)
if not os.path.exists(JOIN_KEYS_FILE):
    save_join_keys({"keys": []})


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
    """渲染 Star Office 页面"""
    from flask import render_template_string
    import time
    
    index_file = os.path.join(STAR_OFFICE_ROOT, 'static', 'index.html')
    if os.path.exists(index_file):
        with open(index_file, "r", encoding="utf-8") as f:
            html = f.read()
        # 渲染模板变量 {{VERSION_TIMESTAMP}}
        VERSION_TIMESTAMP = str(int(time.time()))
        html = html.replace('{{VERSION_TIMESTAMP}}', VERSION_TIMESTAMP)
        resp = make_response(html)
        resp.headers["Content-Type"] = "text/html; charset=utf-8"
        return resp
    return "Star Office UI 未找到", 404


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
    keys_data = load_join_keys()
    
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
    save_join_keys(keys_data)
    
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


@star_office_bp.route("/join-agent", methods=["POST"])
def join_agent():
    """Agent 加入办公室"""
    try:
        data = request.get_json()
        agent_id = (data.get("agentId") or "").strip()
        join_key = (data.get("joinKey") or "").strip()
        name = (data.get("name") or "").strip()
        
        if not agent_id or not join_key:
            return jsonify({"ok": False, "msg": "缺少 agentId/joinKey"}), 400
        
        keys_data = load_join_keys()
        key_item = next((k for k in keys_data.get("keys", []) if k.get("key") == join_key), None)
        
        if not key_item:
            return jsonify({"ok": False, "msg": "joinKey 无效"}), 403
        
        if key_item.get("used"):
            return jsonify({"ok": False, "msg": "joinKey 已被使用"}), 403
        
        # 标记 key 为已用
        key_item["used"] = True
        key_item["usedBy"] = name or agent_id
        key_item["usedByAgentId"] = agent_id
        key_item["usedAt"] = datetime.now().isoformat()
        save_join_keys(keys_data)
        
        # 添加 agent
        agents = load_agents_state()
        agents.append({
            "agentId": agent_id,
            "name": name or agent_id,
            "isMain": False,
            "state": "idle",
            "detail": "刚刚加入",
            "updated_at": datetime.now().isoformat(),
            "area": "breakroom",
            "source": "join",
            "joinKey": join_key,
            "authStatus": "approved",
            "authExpiresAt": (datetime.now() + timedelta(hours=24)).isoformat(),
            "lastPushAt": None
        })
        save_agents_state(agents)
        
        return jsonify({"ok": True, "msg": "加入成功"})
    except Exception as e:
        return jsonify({"ok": False, "msg": str(e)}), 500


@star_office_bp.route("/join-keys", methods=["GET"])
def get_join_keys():
    """获取 join keys"""
    return jsonify(load_join_keys())


@star_office_bp.route("/join-keys", methods=["POST"])
def create_join_key():
    """创建 join key"""
    import uuid
    keys_data = load_join_keys()
    new_key = str(uuid.uuid4())[:8]
    keys_data["keys"].append({
        "key": new_key,
        "used": False,
        "usedBy": None,
        "usedByAgentId": None,
        "usedAt": None,
        "expiresAt": (datetime.now() + timedelta(days=7)).isoformat()
    })
    save_join_keys(keys_data)
    return jsonify({"ok": True, "key": new_key})


# ============================================================================
# Missing API Endpoints (for Star Office dashboard)
# ============================================================================

@star_office_bp.route("/status", methods=["GET"])
def get_status():
    """获取状态 - 与 /state 相同，供前端 game.js fetchStatus() 调用"""
    state = load_state()
    return jsonify(state)


@star_office_bp.route("/yesterday-memo", methods=["GET"])
def get_yesterday_memo():
    """获取昨日小记"""
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    return jsonify({
        "success": True,
        "date": yesterday,
        "memo": "昨日暂无记录"
    })


@star_office_bp.route("/config/gemini", methods=["GET"])
def get_gemini_config():
    """获取 Gemini 配置"""
    return jsonify({
        "enabled": False,
        "model": "gemini-2.5-flash",
        "apiKey": "",
        "reasoningEffort": "low"
    })


@star_office_bp.route("/leave-agent", methods=["POST"])
def leave_agent():
    """离开办公室"""
    try:
        data = request.get_json() or {}
        agent_id = data.get("agentId", "").strip()
        if not agent_id:
            return jsonify({"ok": False, "msg": "缺少 agentId"}), 400

        agents = load_agents_state()
        agents = [a for a in agents if a.get("agentId") != agent_id]
        save_agents_state(agents)
        return jsonify({"ok": True, "msg": "已离开"})
    except Exception as e:
        return jsonify({"ok": False, "msg": str(e)}), 500


@star_office_bp.route("/agent-approve", methods=["POST"])
def agent_approve():
    """批准 agent"""
    try:
        data = request.get_json() or {}
        agent_id = data.get("agentId", "").strip()
        if not agent_id:
            return jsonify({"ok": False, "msg": "缺少 agentId"}), 400

        agents = load_agents_state()
        for a in agents:
            if a.get("agentId") == agent_id:
                a["authStatus"] = "approved"
                a["authExpiresAt"] = (datetime.now() + timedelta(hours=24)).isoformat()
                break
        save_agents_state(agents)
        return jsonify({"ok": True, "msg": "已批准"})
    except Exception as e:
        return jsonify({"ok": False, "msg": str(e)}), 500


# ============================================================================
# Assets API Endpoints (mock implementations)
# ============================================================================

@star_office_bp.route("/assets/auth", methods=["POST"])
def assets_auth():
    """资产认证"""
    return jsonify({"ok": True, "token": "mock-token"})


@star_office_bp.route("/assets/auth/status", methods=["GET"])
def assets_auth_status():
    """资产认证状态"""
    return jsonify({"authenticated": True, "token": "mock-token"})


@star_office_bp.route("/assets/positions", methods=["GET"])
def assets_positions():
    """获取位置列表"""
    return jsonify({"positions": []})


@star_office_bp.route("/assets/defaults", methods=["GET"])
def assets_defaults():
    """获取默认资产"""
    return jsonify({"defaults": {}})


@star_office_bp.route("/assets/list", methods=["GET"])
def assets_list():
    """获取资产列表"""
    return jsonify({"assets": [], "total": 0})


@star_office_bp.route("/assets/upload", methods=["POST"])
def assets_upload():
    """上传资产"""
    return jsonify({"ok": True, "path": ""})


@star_office_bp.route("/assets/generate-rpg-background", methods=["POST"])
def assets_generate_rpg_background():
    """生成 RPG 背景"""
    return jsonify({"ok": True, "taskId": "mock-task-id"})


@star_office_bp.route("/assets/generate-rpg-background/poll", methods=["GET"])
def assets_generate_rpg_background_poll():
    """轮询 RPG 背景生成状态"""
    return jsonify({"status": "completed", "path": ""})


@star_office_bp.route("/assets/restore-reference-background", methods=["POST"])
def assets_restore_reference_background():
    """恢复参考背景"""
    return jsonify({"ok": True})


@star_office_bp.route("/assets/restore-last-generated-background", methods=["POST"])
def assets_restore_last_generated_background():
    """恢复上次生成的背景"""
    return jsonify({"ok": True})


@star_office_bp.route("/assets/restore-default", methods=["POST"])
def assets_restore_default():
    """恢复默认背景"""
    return jsonify({"ok": True})


@star_office_bp.route("/assets/restore-prev", methods=["POST"])
def assets_restore_prev():
    """恢复上一个背景"""
    return jsonify({"ok": True})


@star_office_bp.route("/assets/home-favorites/<path:subpath>", methods=["GET"])
def assets_home_favorites_get(subpath):
    """获取收藏夹内容"""
    return jsonify({"favorites": []})


@star_office_bp.route("/assets/home-favorites/<path:subpath>", methods=["POST"])
def assets_home_favorites_post(subpath):
    """操作收藏夹"""
    return jsonify({"ok": True})
