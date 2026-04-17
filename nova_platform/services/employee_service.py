from sqlalchemy.orm import Session
from nova_platform.models import Employee
import json


def create_employee(session: Session, name: str, type: str = "human", role: str = "general", skills: list = None) -> Employee:
    skills_json = json.dumps(skills or [])
    employee = Employee(name=name, type=type, role=role, skills=skills_json)
    session.add(employee)
    session.commit()
    return employee


def list_employees(session: Session) -> list[Employee]:
    return session.query(Employee).order_by(Employee.created_at.desc()).all()


def get_employee(session: Session, employee_id: str) -> Employee | None:
    return session.query(Employee).filter_by(id=employee_id).first()


def get_employee_skills(session: Session, employee_id: str) -> list:
    employee = get_employee(session, employee_id)
    if not employee:
        return []
    return json.loads(employee.skills)


def update_employee(session: Session, employee_id: str, **kwargs) -> Employee | None:
    employee = get_employee(session, employee_id)
    if not employee:
        return None
    if "skills" in kwargs and kwargs["skills"] is not None:
        kwargs["skills"] = json.dumps(kwargs["skills"])
    for key, value in kwargs.items():
        if hasattr(employee, key) and value is not None:
            setattr(employee, key, value)
    session.commit()
    return employee


def delete_employee(session: Session, employee_id: str) -> bool:
    employee = get_employee(session, employee_id)
    if not employee:
        return False
    session.query(Employee).filter_by(id=employee_id).delete()
    session.commit()
    return True
