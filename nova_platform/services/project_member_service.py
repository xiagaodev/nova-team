"""
Project Member Service - 项目成员管理服务

设计说明：
- employee 是全局的，存储在 employees 表中
- project_members 是关联表，记录员工在项目中的角色
- 项目创建时，leader 角色默认加入
- 其他角色由用户通过 CLI 添加
"""

from sqlalchemy.orm import Session
from nova_platform.models import ProjectMember, Project, Employee
from datetime import datetime
from typing import Optional, List
import json


def add_member_to_project(
    session: Session,
    project_id: str,
    employee_id: str,
    role: str = "member"
) -> dict:
    """
    添加成员到项目

    Args:
        session: 数据库会话
        project_id: 项目ID
        employee_id: 员工ID
        role: 项目角色 (leader, member, reviewer)

    Returns:
        {"success": bool, "member": ProjectMember|None, "error": str|None}
    """
    # 验证项目存在
    project = session.query(Project).filter_by(id=project_id).first()
    if not project:
        return {"success": False, "member": None, "error": "Project not found"}

    # 验证员工存在
    employee = session.query(Employee).filter_by(id=employee_id).first()
    if not employee:
        return {"success": False, "member": None, "error": "Employee not found"}

    # 检查是否已是成员
    existing = session.query(ProjectMember).filter_by(
        project_id=project_id,
        employee_id=employee_id
    ).first()

    if existing:
        # 更新角色
        existing.role = role
        session.commit()
        return {"success": True, "member": existing, "error": None}

    # 创建新成员关联
    member = ProjectMember(
        project_id=project_id,
        employee_id=employee_id,
        role=role
    )
    session.add(member)
    session.commit()

    return {"success": True, "member": member, "error": None}


def remove_member_from_project(
    session: Session,
    project_id: str,
    employee_id: str
) -> dict:
    """
    从项目中移除成员

    Args:
        session: 数据库会话
        project_id: 项目ID
        employee_id: 员工ID

    Returns:
        {"success": bool, "error": str|None}
    """
    member = session.query(ProjectMember).filter_by(
        project_id=project_id,
        employee_id=employee_id
    ).first()

    if not member:
        return {"success": False, "error": "Member not found in project"}

    session.delete(member)
    session.commit()

    return {"success": True, "error": None}


def list_project_members(
    session: Session,
    project_id: str,
    role: Optional[str] = None
) -> List[dict]:
    """
    列出项目成员

    Args:
        session: 数据库会话
        project_id: 项目ID
        role: 可选，筛选特定角色

    Returns:
        [{"employee": Employee, "role": str, "joined_at": datetime}, ...]
    """
    query = session.query(ProjectMember).filter_by(project_id=project_id)

    if role:
        query = query.filter_by(role=role)

    memberships = query.all()

    result = []
    for m in memberships:
        employee = session.query(Employee).filter_by(id=m.employee_id).first()
        if employee:
            result.append({
                "employee": employee,
                "role": m.role,
                "joined_at": m.joined_at
            })

    return result


def update_member_role(
    session: Session,
    project_id: str,
    employee_id: str,
    new_role: str
) -> dict:
    """
    更新成员在项目中的角色

    Args:
        session: 数据库会话
        project_id: 项目ID
        employee_id: 员工ID
        new_role: 新角色

    Returns:
        {"success": bool, "member": ProjectMember|None, "error": str|None}
    """
    member = session.query(ProjectMember).filter_by(
        project_id=project_id,
        employee_id=employee_id
    ).first()

    if not member:
        return {"success": False, "member": None, "error": "Member not found in project"}

    member.role = new_role
    session.commit()

    return {"success": True, "member": member, "error": None}


def get_member_role(
    session: Session,
    project_id: str,
    employee_id: str
) -> Optional[str]:
    """
    获取成员在项目中的角色

    Args:
        session: 数据库会话
        project_id: 项目ID
        employee_id: 员工ID

    Returns:
        角色名称，如果成员不存在则返回 None
    """
    member = session.query(ProjectMember).filter_by(
        project_id=project_id,
        employee_id=employee_id
    ).first()

    return member.role if member else None


def is_member_in_project(
    session: Session,
    project_id: str,
    employee_id: str
) -> bool:
    """
    检查员工是否是项目成员

    Args:
        session: 数据库会话
        project_id: 项目ID
        employee_id: 员工ID

    Returns:
        bool: 是否是成员
    """
    return session.query(ProjectMember).filter_by(
        project_id=project_id,
        employee_id=employee_id
    ).first() is not None


def get_employee_projects(
    session: Session,
    employee_id: str
) -> List[dict]:
    """
    获取员工参与的所有项目

    Args:
        session: 数据库会话
        employee_id: 员工ID

    Returns:
        [{"project": Project, "role": str, "joined_at": datetime}, ...]
    """
    memberships = session.query(ProjectMember).filter_by(employee_id=employee_id).all()

    result = []
    for m in memberships:
        project = session.query(Project).filter_by(id=m.project_id).first()
        if project:
            result.append({
                "project": project,
                "role": m.role,
                "joined_at": m.joined_at
            })

    return result


def get_project_members_by_role(
    session: Session,
    project_id: str,
    role: str
) -> List[Employee]:
    """
    获取项目中特定角色的所有员工

    Args:
        session: 数据库会话
        project_id: 项目ID
        role: 角色名称

    Returns:
        [Employee, ...]
    """
    memberships = session.query(ProjectMember).filter_by(
        project_id=project_id,
        role=role
    ).all()

    employee_ids = [m.employee_id for m in memberships]
    if not employee_ids:
        return []

    return session.query(Employee).filter(Employee.id.in_(employee_ids)).all()


def get_active_project_members(
    session: Session,
    project_id: str
) -> List[Employee]:
    """
    获取项目中所有活跃成员（用于任务分配）
    排除人类成员，只返回 agent 类型成员

    Args:
        session: 数据库会话
        project_id: 项目ID

    Returns:
        [Employee, ...]
    """
    memberships = session.query(ProjectMember).filter_by(project_id=project_id).all()
    employee_ids = [m.employee_id for m in memberships]

    if not employee_ids:
        return []

    return session.query(Employee).filter(
        Employee.id.in_(employee_ids),
        Employee.type != "human"
    ).all()


def transfer_project_ownership(
    session: Session,
    project_id: str,
    new_leader_id: str
) -> dict:
    """
    转移项目负责人

    Args:
        session: 数据库会话
        project_id: 项目ID
        new_leader_id: 新负责人ID

    Returns:
        {"success": bool, "error": str|None}
    """
    # 验证新负责人是项目成员
    if not is_member_in_project(session, project_id, new_leader_id):
        return {"success": False, "error": "New leader is not a project member"}

    # 将原 leader 改为 member
    current_leaders = session.query(ProjectMember).filter_by(
        project_id=project_id,
        role="leader"
    ).all()

    for m in current_leaders:
        m.role = "member"

    # 将新成员设为 leader
    new_leader = session.query(ProjectMember).filter_by(
        project_id=project_id,
        employee_id=new_leader_id
    ).first()

    if new_leader:
        new_leader.role = "leader"

    session.commit()

    return {"success": True, "error": None}


def format_member_list(members: List[dict]) -> str:
    """
    格式化成员列表为可读字符串

    Args:
        members: list_project_members 返回的列表

    Returns:
        格式化的字符串
    """
    if not members:
        return "No members found."

    lines = []
    for m in members:
        emp = m["employee"]
        role_icon = {"leader": "👑", "member": "👤", "reviewer": "👁"}.get(m["role"], "👤")
        type_icon = {"human": "🧑", "agent": "🤖", "claude-code": "🤖", "openclaw": "🤖", "hermes": "🧠"}.get(emp.type, "❓")
        lines.append(
            f"  {role_icon} {type_icon} {emp.name} ({m['role']}) - {emp.type} - {emp.id[:8]}"
        )

    return "\n".join(lines)
