"""
OKR Service - 目标与关键结果管理

提供OKR的创建、更新、进度追踪和健康度监控功能。
"""

from datetime import datetime, timedelta
from typing import Optional, List, Dict
from sqlalchemy.orm import Session

from nova_platform.models import OKR, Project


def create_okr(
    session: Session,
    project_id: str,
    objective: str,
    target_value: float,
    unit: str = "",
    due_date: Optional[datetime] = None
) -> OKR:
    """创建新的OKR"""
    okr = OKR(
        project_id=project_id,
        objective=objective,
        target_value=target_value,
        current_value=0,
        unit=unit,
        status="on_track",
        due_date=due_date
    )
    session.add(okr)
    session.commit()
    session.refresh(okr)
    return okr


def update_okr_progress(
    session: Session,
    okr_id: str,
    current_value: float
) -> Optional[OKR]:
    """更新OKR进度"""
    okr = session.query(OKR).filter_by(id=okr_id).first()
    if not okr:
        return None

    okr.current_value = current_value
    okr.updated_at = datetime.utcnow()

    # 自动判断是否达成
    if okr.target_value > 0:
        progress = (okr.current_value / okr.target_value) * 100
        if progress >= 100:
            okr.status = "achieved"

    session.commit()
    session.refresh(okr)
    return okr


def get_project_okrs(session: Session, project_id: str) -> List[OKR]:
    """获取项目的所有OKR"""
    return session.query(OKR).filter_by(project_id=project_id).order_by(OKR.created_at).all()


def get_okr(session: Session, okr_id: str) -> Optional[OKR]:
    """获取单个OKR"""
    return session.query(OKR).filter_by(id=okr_id).first()


def delete_okr(session: Session, okr_id: str) -> bool:
    """删除OKR"""
    okr = session.query(OKR).filter_by(id=okr_id).first()
    if not okr:
        return False

    session.delete(okr)
    session.commit()
    return True


def check_okr_health(session: Session, project_id: str) -> Dict:
    """检查OKR健康度

    Returns:
        {
            "overall": "healthy|at_risk|off_track",
            "okrs": [
                {
                    "id": "...",
                    "objective": "...",
                    "progress": "85%",
                    "status": "on_track",
                    "health_score": 0.85
                }
            ]
        }
    """
    okrs = session.query(OKR).filter_by(project_id=project_id).all()

    health_report = {
        "overall": "healthy",
        "okrs": []
    }

    for okr in okrs:
        # 计算进度百分比
        if okr.target_value > 0:
            progress = (okr.current_value / okr.target_value)
        else:
            progress = 0

        progress_percent = f"{progress * 100:.1f}%"
        health_score = progress

        # 根据截止日期计算健康度
        if okr.due_date and okr.status != "achieved":
            time_total = (okr.due_date - okr.created_at).total_seconds()
            time_elapsed = (datetime.utcnow() - okr.created_at).total_seconds()
            time_left = (okr.due_date - datetime.utcnow()).total_seconds()

            if time_total > 0:
                expected_progress = time_elapsed / time_total

                # 健康度判断逻辑
                if progress < expected_progress * 0.5:
                    status = "at_risk"
                    health_score = max(health_score, 0.2)
                elif progress < expected_progress * 0.8:
                    status = "off_track"
                    health_score = max(health_score, 0.5)
                else:
                    status = "on_track"
            else:
                status = "on_track"
        else:
            status = okr.status if okr.status != "achieved" else "on_track"
            if okr.status == "achieved":
                health_score = 1.0

        # 更新OKR状态
        if okr.status != "achieved":
            okr.status = status

        health_report["okrs"].append({
            "id": okr.id,
            "objective": okr.objective,
            "current_value": okr.current_value,
            "target_value": okr.target_value,
            "unit": okr.unit,
            "progress": progress_percent,
            "status": status,
            "health_score": health_score,
            "due_date": okr.due_date.strftime("%Y-%m-%d") if okr.due_date else None
        })

    # 计算整体健康度
    if health_report["okrs"]:
        avg_health = sum(o["health_score"] for o in health_report["okrs"]) / len(health_report["okrs"])

        if avg_health < 0.5:
            health_report["overall"] = "at_risk"
        elif avg_health < 0.8:
            health_report["overall"] = "off_track"
        else:
            health_report["overall"] = "healthy"

    session.commit()
    return health_report


def get_okr_summary(session: Session, project_id: str) -> Dict:
    """获取OKR摘要统计"""
    okrs = session.query(OKR).filter_by(project_id=project_id).all()

    summary = {
        "total": len(okrs),
        "achieved": 0,
        "on_track": 0,
        "at_risk": 0,
        "off_track": 0,
        "average_progress": 0
    }

    total_progress = 0

    for okr in okrs:
        summary[okr.status] = summary.get(okr.status, 0) + 1

        if okr.target_value > 0:
            total_progress += (okr.current_value / okr.target_value)

    if len(okrs) > 0:
        summary["average_progress"] = total_progress / len(okrs)

    return summary
