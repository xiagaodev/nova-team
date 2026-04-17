from sqlalchemy.orm import Session
from nova_platform.models import Project, ProjectMember, Employee
from datetime import datetime


def create_project(session: Session, name: str, description: str = "", template: str = "general") -> Project:
    project = Project(name=name, description=description, template=template)
    session.add(project)
    session.commit()
    return project


def list_projects(session: Session) -> list[Project]:
    return session.query(Project).order_by(Project.created_at.desc()).all()


def get_project(session: Session, project_id: str) -> Project | None:
    return session.query(Project).filter_by(id=project_id).first()


def update_project(session: Session, project_id: str, **kwargs) -> Project | None:
    project = get_project(session, project_id)
    if not project:
        return None
    for key, value in kwargs.items():
        if hasattr(project, key) and value is not None:
            setattr(project, key, value)
    project.updated_at = datetime.utcnow()
    session.commit()
    return project


def delete_project(session: Session, project_id: str) -> bool:
    project = get_project(session, project_id)
    if not project:
        return False
    session.query(ProjectMember).filter_by(project_id=project_id).delete()
    session.delete(project)
    session.commit()
    return True


def get_project_members(session: Session, project_id: str) -> list[Employee]:
    members = session.query(ProjectMember).filter_by(project_id=project_id).all()
    member_ids = [m.employee_id for m in members]
    return session.query(Employee).filter(Employee.id.in_(member_ids)).all() if member_ids else []


def add_project_member(session: Session, project_id: str, employee_id: str) -> bool:
    project = get_project(session, project_id)
    employee = session.query(Employee).filter_by(id=employee_id).first()
    if not project or not employee:
        return False
    existing = session.query(ProjectMember).filter_by(project_id=project_id, employee_id=employee_id).first()
    if existing:
        return True
    member = ProjectMember(project_id=project_id, employee_id=employee_id)
    session.add(member)
    session.commit()
    return True


def get_employee_projects(session: Session, employee_id: str) -> list[Project]:
    memberships = session.query(ProjectMember).filter_by(employee_id=employee_id).all()
    project_ids = [m.project_id for m in memberships]
    return session.query(Project).filter(Project.id.in_(project_ids)).all() if project_ids else []
