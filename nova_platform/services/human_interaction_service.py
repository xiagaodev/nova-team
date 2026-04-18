"""
Human Interaction Service - Agent与人类交互服务

处理Agent向人类提问、获取回答以及Human-in-the-Loop机制。
"""

import json
from datetime import datetime
from typing import Optional, List, Dict
from sqlalchemy.orm import Session

from nova_platform.models import Employee, Project


class HumanQuestion:
    """人类问题表（暂时使用字典模拟，后续迁移到ORM）"""
    def __init__(self, id, project_id, question, context, status, asked_at, answered_at=None, answer=None):
        self.id = id
        self.project_id = project_id
        self.question = question
        self.context = context
        self.status = status
        self.asked_at = asked_at
        self.answered_at = answered_at
        self.answer = answer


# 临时存储（生产环境应使用数据库）
_questions_store: Dict[str, Dict] = {}


def ask_human(
    session: Session,
    project_id: str,
    question: str,
    context: Optional[Dict] = None,
    priority: str = "normal"
) -> Dict:
    """Agent向人类提问

    Args:
        session: 数据库会话
        project_id: 项目ID
        question: 问题内容
        context: 上下文信息（字典）
        priority: 优先级 (low/normal/high/urgent)

    Returns:
        {
            "id": "问题ID",
            "question": "问题内容",
            "status": "pending",
            "asked_at": "提问时间"
        }
    """
    import uuid

    question_id = str(uuid.uuid4())
    now = datetime.utcnow()

    question_data = {
        "id": question_id,
        "project_id": project_id,
        "question": question,
        "context": json.dumps(context) if context else None,
        "status": "pending",
        "priority": priority,
        "asked_at": now.isoformat(),
        "answered_at": None,
        "answer": None
    }

    _questions_store[question_id] = question_data

    # TODO: 发送通知（邮件、Web推送等）
    # 可以在这里集成邮件发送或WebSocket推送

    return {
        "id": question_id,
        "question": question,
        "status": "pending",
        "asked_at": now.isoformat(),
        "priority": priority
    }


def get_pending_questions(session: Session, project_id: str) -> List[Dict]:
    """获取待回答的问题"""
    pending = []
    for q_id, q_data in _questions_store.items():
        if q_data["project_id"] == project_id and q_data["status"] == "pending":
            pending.append(q_data)

    # 按优先级和提问时间排序
    priority_order = {"urgent": 0, "high": 1, "normal": 2, "low": 3}
    pending.sort(key=lambda x: (
        priority_order.get(x.get("priority", "normal"), 2),
        x["asked_at"]
    ))

    return pending


def answer_question(session: Session, question_id: str, answer: str) -> Optional[Dict]:
    """回答问题"""
    if question_id not in _questions_store:
        return None

    question_data = _questions_store[question_id]
    question_data["answer"] = answer
    question_data["status"] = "answered"
    question_data["answered_at"] = datetime.utcnow().isoformat()

    return question_data


def skip_question(session: Session, question_id: str, reason: str = "") -> Optional[Dict]:
    """跳过问题"""
    if question_id not in _questions_store:
        return None

    question_data = _questions_store[question_id]
    question_data["status"] = "skipped"
    question_data["answer"] = f"[SKIPPED] {reason}" if reason else "[SKIPPED]"
    question_data["answered_at"] = datetime.utcnow().isoformat()

    return question_data


def get_question(session: Session, question_id: str) -> Optional[Dict]:
    """获取单个问题详情"""
    return _questions_store.get(question_id)


def should_ask_human(session: Session, project_id: str, context: Dict) -> bool:
    """判断是否需要向人类提问

    基于以下条件判断：
    1. 有阻塞性问题需要决策
    2. 多个OKR处于at_risk状态
    3. 长时间未获得人类反馈
    """
    from nova_platform.services import okr_service

    # 检查OKR健康度
    health = okr_service.check_okr_health(session, project_id)

    # 如果有OKR处于at_risk状态，需要人类介入
    if health["overall"] == "at_risk":
        return True

    # 检查是否有未解决的阻塞性问题
    blockers = context.get("blockers", [])
    if len(blockers) > 2:
        return True

    # 检查距离上次人类反馈的时间
    last_feedback = context.get("last_human_feedback")
    if last_feedback:
        last_feedback_time = datetime.fromisoformat(last_feedback)
        if (datetime.utcnow() - last_feedback_time).total_seconds() > 86400:  # 24小时
            return True

    return False


def generate_question_from_context(session: Session, project_id: str, context: Dict) -> Optional[str]:
    """根据上下文自动生成问题"""
    blockers = context.get("blockers", [])
    health = context.get("okr_health", {})

    if health.get("overall") == "at_risk":
        return f"项目OKR健康度为 at_risk，是否需要调整目标或增加资源？"

    if len(blockers) > 0:
        blocker_names = [b.get("todo", {}).title for b in blockers[:3]]
        return f"以下任务已被阻塞较长时间：{', '.join(blocker_names)}。是否需要重新分配或取消？"

    pending_tasks = context.get("pending_tasks", 0)
    if pending_tasks > 10:
        return f"当前有{pending_tasks}个待处理任务，是否需要增加Agent成员或调整优先级？"

    return None


def get_interaction_summary(session: Session, project_id: str) -> Dict:
    """获取人类交互摘要"""
    all_questions = [q for q in _questions_store.values() if q["project_id"] == project_id]

    summary = {
        "total": len(all_questions),
        "pending": 0,
        "answered": 0,
        "skipped": 0,
        "avg_response_time_hours": 0,
        "recent_questions": []
    }

    total_response_time = 0
    answered_count = 0

    for q in sorted(all_questions, key=lambda x: x["asked_at"], reverse=True)[:10]:
        summary["recent_questions"].append({
            "id": q["id"],
            "question": q["question"][:100] + "..." if len(q["question"]) > 100 else q["question"],
            "status": q["status"],
            "asked_at": q["asked_at"],
            "answered_at": q["answered_at"]
        })

    for q in all_questions:
        summary[q["status"]] = summary.get(q["status"], 0) + 1

        if q["status"] == "answered" and q["answered_at"]:
            asked_at = datetime.fromisoformat(q["asked_at"])
            answered_at = datetime.fromisoformat(q["answered_at"])
            response_time_hours = (answered_at - asked_at).total_seconds() / 3600
            total_response_time += response_time_hours
            answered_count += 1

    if answered_count > 0:
        summary["avg_response_time_hours"] = total_response_time / answered_count

    return summary
