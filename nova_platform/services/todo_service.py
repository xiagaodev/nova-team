from sqlalchemy.orm import Session
from nova_platform.models import Todo
from datetime import datetime


def create_todo(session: Session, title: str, project_id: str, description: str = "", assignee_id=None, priority: str = "medium", due_date=None) -> Todo:
    todo = Todo(
        title=title,
        project_id=project_id,
        description=description,
        assignee_id=assignee_id,
        priority=priority,
        due_date=due_date,
        status="pending"
    )
    session.add(todo)
    session.commit()
    return todo


def list_todos(session: Session, project_id=None, assignee_id=None, status=None) -> list[Todo]:
    query = session.query(Todo)
    if project_id is not None:
        query = query.filter_by(project_id=project_id)
    if assignee_id is not None:
        query = query.filter_by(assignee_id=assignee_id)
    if status is not None:
        query = query.filter_by(status=status)
    return query.order_by(Todo.created_at.desc()).all()


def get_todo(session: Session, todo_id: str) -> Todo | None:
    return session.query(Todo).filter_by(id=todo_id).first()


def update_todo(session: Session, todo_id: str, **kwargs) -> Todo | None:
    todo = get_todo(session, todo_id)
    if not todo:
        return None
    for key, value in kwargs.items():
        if hasattr(todo, key) and value is not None:
            if key == "due_date" and isinstance(value, str):
                from dateutil.parser import parse as parse_date
                value = parse_date(value)
            setattr(todo, key, value)
    todo.updated_at = datetime.utcnow()
    session.commit()
    return todo


def delete_todo(session: Session, todo_id: str) -> bool:
    todo = get_todo(session, todo_id)
    if not todo:
        return False
    session.delete(todo)
    session.commit()
    return True