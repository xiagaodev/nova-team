"""Knowledge service - 经验共享"""
import json
from sqlalchemy.orm import Session
from nova_platform.models import Knowledge, Employee


def create_knowledge(session: Session, title: str, project_id: str = None,
                     content: str = "", tags: list = None) -> dict:
    """创建知识条目"""
    tags_json = json.dumps(tags or [])

    knowledge = Knowledge(
        title=title,
        project_id=project_id,
        content=content,
        tags=tags_json
    )
    session.add(knowledge)
    session.commit()

    return {"success": True, "knowledge": knowledge}


def list_knowledge(session: Session, project_id: str = None) -> list:
    """列出知识条目"""
    query = session.query(Knowledge)
    if project_id:
        query = query.filter_by(project_id=project_id)
    return query.order_by(Knowledge.updated_at.desc()).all()


def search_knowledge(session: Session, query_text: str, project_id: str = None) -> list:
    """搜索知识库（简单的文本匹配）"""
    query = session.query(Knowledge).filter(
        (Knowledge.title.contains(query_text)) |
        (Knowledge.content.contains(query_text)) |
        (Knowledge.tags.contains(query_text))
    )
    if project_id:
        query = query.filter_by(project_id=project_id)
    return query.order_by(Knowledge.updated_at.desc()).all()


def get_knowledge(session: Session, knowledge_id: str) -> Knowledge | None:
    """获取单个知识条目"""
    return session.query(Knowledge).filter_by(id=knowledge_id).first()


def update_knowledge(session: Session, knowledge_id: str, **kwargs) -> dict:
    """更新知识条目"""
    knowledge = get_knowledge(session, knowledge_id)
    if not knowledge:
        return {"success": False, "error": "Knowledge not found"}

    if "tags" in kwargs and kwargs["tags"] is not None:
        kwargs["tags"] = json.dumps(kwargs["tags"])

    for key, value in kwargs.items():
        if hasattr(knowledge, key) and value is not None:
            setattr(knowledge, key, value)

    session.commit()
    return {"success": True, "knowledge": knowledge}


def delete_knowledge(session: Session, knowledge_id: str) -> bool:
    """删除知识条目"""
    knowledge = get_knowledge(session, knowledge_id)
    if not knowledge:
        return False

    session.query(Knowledge).filter_by(id=knowledge_id).delete()
    session.commit()
    return True


def get_employee_knowledge(session: Session, employee_id: str, query_text: str = None) -> list:
    """获取某员工在跨项目中积累的知识"""
    # 找到该员工参与的所有项目
    from nova_platform.models import ProjectMember
    memberships = session.query(ProjectMember).filter_by(employee_id=employee_id).all()
    project_ids = [m.project_id for m in memberships]

    if not project_ids:
        return []

    query = session.query(Knowledge).filter(Knowledge.project_id.in_(project_ids))

    if query_text:
        query = query.filter(
            (Knowledge.title.contains(query_text)) |
            (Knowledge.content.contains(query_text)) |
            (Knowledge.tags.contains(query_text))
        )

    return query.order_by(Knowledge.updated_at.desc()).all()
