import os
from pathlib import Path
from sqlalchemy.orm import Session
from nova_platform.models import Project, ProjectMember, Employee, Todo, TaskHistory, Knowledge, OKR
from nova_platform.config import get_workspace_root
from datetime import datetime


def create_project(
    session: Session,
    name: str,
    description: str = "",
    template: str = "general",
    workspace_path: str = None,
    leader_id: str = None
) -> Project:
    """
    创建项目

    Args:
        session: 数据库会话
        name: 项目名称
        description: 项目描述
        template: 项目模板
        workspace_path: 工作空间路径（如果为 None，自动创建）
        leader_id: 项目负责人ID（可选，如果提供则自动添加为leader并创建规划任务）

    Returns:
        Project 对象
    """
    # 默认状态为 pending（待启动）
    project = Project(name=name, description=description, template=template, status="pending")

    # 如果未指定工作空间，自动创建
    if workspace_path is None:
        # 先保存项目以获取 ID
        session.add(project)
        session.commit()
        session.refresh(project)

        # 使用项目 ID 创建工作空间
        workspace_root = get_workspace_root()
        workspace_path = os.path.join(workspace_root, project.id)

    project.workspace_path = workspace_path
    session.add(project)
    session.commit()
    session.refresh(project)

    # 创建工作空间目录
    ensure_workspace(project.workspace_path)

    # 如果指定了 leader，添加到项目并创建规划任务
    if leader_id:
        from nova_platform.services import project_member_service
        member_result = project_member_service.add_member_to_project(
            session, project.id, leader_id, role="leader"
        )
        if member_result["success"]:
            # 创建项目规划待办任务
            planning_todo = Todo(
                title=f"项目规划：{project.name}",
                description=f"请为项目 {project.name} 制定详细的规划方案。\n\n项目描述：{project.description}\n模板：{project.template}\n\n请创建以下内容：\n1. 项目目标拆解\n2. 技术方案设计\n3. 任务分解（TODO列表）\n4. 里程碑规划",
                project_id=project.id,
                assignee_id=leader_id,
                priority="high",
                status="pending"
            )
            session.add(planning_todo)
            session.commit()
            session.refresh(project)

    return project


def ensure_workspace(workspace_path: str) -> Path:
    """
    确保工作空间目录存在

    Args:
        workspace_path: 工作空间路径

    Returns:
        Path 对象
    """
    path = Path(os.path.expanduser(workspace_path))
    path.mkdir(parents=True, exist_ok=True)

    # 创建子目录结构
    (path / "src").mkdir(exist_ok=True)
    (path / "docs").mkdir(exist_ok=True)
    (path / "output").mkdir(exist_ok=True)
    (path / ".nova").mkdir(exist_ok=True)

    # 创建 .gitkeep 文件保持目录结构
    (path / "src" / ".gitkeep").touch(exist_ok=True)
    (path / "docs" / ".gitkeep").touch(exist_ok=True)
    (path / "output" / ".gitkeep").touch(exist_ok=True)

    return path


def get_project_workspace(session: Session, project_id: str) -> str | None:
    """
    获取项目工作空间路径（自动创建目录）

    Args:
        session: 数据库会话
        project_id: 项目ID

    Returns:
        工作空间路径，如果项目不存在则返回 None
    """
    project = get_project(session, project_id)
    if not project:
        return None

    # 如果工作空间路径为空，设置默认路径
    if not project.workspace_path:
        workspace_root = get_workspace_root()
        project.workspace_path = os.path.join(workspace_root, project.id)
        session.commit()

    # 确保目录存在
    ensure_workspace(project.workspace_path)

    return project.workspace_path


def set_project_workspace(session: Session, project_id: str, workspace_path: str) -> bool:
    """
    设置项目工作空间

    Args:
        session: 数据库会话
        project_id: 项目ID
        workspace_path: 新的工作空间路径

    Returns:
        是否设置成功
    """
    project = get_project(session, project_id)
    if not project:
        return False

    project.workspace_path = workspace_path
    project.updated_at = datetime.utcnow()
    session.commit()

    # 确保目录存在
    ensure_workspace(workspace_path)

    return True


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
    """
    删除项目及其所有关联数据

    级联删除：
    - 项目成员 (ProjectMember)
    - 任务 (Todo)
    - 任务历史 (TaskHistory)
    - 知识库 (Knowledge)
    - OKR 目标 (OKR)

    注意：工作空间目录不会被删除，需要手动清理
    """
    project = get_project(session, project_id)
    if not project:
        return False

    workspace = project.workspace_path  # 保存路径用于提示

    # 获取该项目的所有任务ID（用于删除任务历史）
    todo_ids = [t.id for t in session.query(Todo).filter_by(project_id=project_id).all()]

    # 删除任务历史记录
    if todo_ids:
        session.query(TaskHistory).filter(TaskHistory.todo_id.in_(todo_ids)).delete()

    # 删除任务
    session.query(Todo).filter_by(project_id=project_id).delete()

    # 删除知识库
    session.query(Knowledge).filter_by(project_id=project_id).delete()

    # 删除OKR
    session.query(OKR).filter_by(project_id=project_id).delete()

    # 删除项目成员
    session.query(ProjectMember).filter_by(project_id=project_id).delete()

    # 删除项目
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
