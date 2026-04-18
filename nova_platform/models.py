from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String, Text, DateTime, Float, Index, Integer
from datetime import datetime
import uuid


class Base(DeclarativeBase):
    pass


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="planning")
    template: Mapped[str] = mapped_column(String(20), default="general")
    owner_id: Mapped[str] = mapped_column(String(36), nullable=True)  # 项目负责人（人类）
    target_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)  # 目标完成时间
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index('idx_project_status', 'status'),
        Index('idx_project_template', 'template'),
    )


class Employee(Base):
    __tablename__ = "employees"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[str] = mapped_column(String(20), default="human")  # human, openclaw, hermes
    role: Mapped[str] = mapped_column(String(50), default="general")
    skills: Mapped[str] = mapped_column(Text, default="[]")
    agent_id: Mapped[str] = mapped_column(String(100), nullable=True)  # OpenClaw/Hermes agent 标识
    agent_config: Mapped[str] = mapped_column(Text, nullable=True)  # JSON 存储 agent 配置
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ProjectMember(Base):
    __tablename__ = "project_members"

    project_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    employee_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    joined_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Todo(Base):
    __tablename__ = "todos"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    project_id: Mapped[str] = mapped_column(String(36), nullable=False)
    assignee_id: Mapped[str] = mapped_column(String(36), nullable=True)
    agent_task_id: Mapped[str] = mapped_column(String(100), nullable=True)  # 关联 agent_service 的异步任务 ID
    status: Mapped[str] = mapped_column(String(20), default="pending")
    priority: Mapped[str] = mapped_column(String(20), default="medium")
    due_date: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    depends_on: Mapped[str] = mapped_column(Text, default="[]")  # JSON 数组，存储依赖的 TODO ID 列表
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index('idx_todo_project_status', 'project_id', 'status'),
        Index('idx_todo_assignee_status', 'assignee_id', 'status'),
        Index('idx_todo_priority', 'priority'),
        Index('idx_todo_project_priority', 'project_id', 'priority'),
    )


class Knowledge(Base):
    __tablename__ = "knowledge"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id: Mapped[str] = mapped_column(String(36), nullable=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    content: Mapped[str] = mapped_column(Text, default="")
    tags: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class OKR(Base):
    """Objectives and Key Results - 目标与关键结果体系"""
    __tablename__ = "okrs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id: Mapped[str] = mapped_column(String(36), nullable=False)
    objective: Mapped[str] = mapped_column(String(500), nullable=False)  # 目标描述
    target_value: Mapped[float] = mapped_column(Float, default=0)  # 目标值
    current_value: Mapped[float] = mapped_column(Float, default=0)  # 当前值
    unit: Mapped[str] = mapped_column(String(50), default="")  # 单位: "%", "个", "次" 等
    status: Mapped[str] = mapped_column(String(20), default="on_track")  # on_track/at_risk/off_track/achieved
    due_date: Mapped[datetime] = mapped_column(DateTime, nullable=True)  # KR 截止日期
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index('idx_okr_project_status', 'project_id', 'status'),
    )


class TaskHistory(Base):
    """任务历史记录 - 追踪任务状态变更"""
    __tablename__ = "task_history"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    todo_id: Mapped[str] = mapped_column(String(36), nullable=False)
    old_status: Mapped[str] = mapped_column(String(20), nullable=True)
    new_status: Mapped[str] = mapped_column(String(20), nullable=False)
    changed_by: Mapped[str] = mapped_column(String(36), nullable=True)  # employee_id
    notes: Mapped[str] = mapped_column(Text, default="")  # 变更备注
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index('idx_task_history_todo', 'todo_id'),
        Index('idx_task_history_changed_by', 'changed_by'),
    )


class AsyncTaskState(Base):
    """异步任务状态 - 替代文件系统存储"""
    __tablename__ = "async_task_states"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    status: Mapped[str] = mapped_column(String(20), default="running")  # running/completed/failed/cancelled
    pid: Mapped[int] = mapped_column(Integer, nullable=True)  # 进程ID
    output: Mapped[str] = mapped_column(Text, default="")  # 执行输出
    error: Mapped[str] = mapped_column(Text, default="")  # 错误信息
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    employee_id: Mapped[str] = mapped_column(String(36), nullable=True)  # 关联的员工ID
    todo_id: Mapped[str] = mapped_column(String(36), nullable=True)  # 关联的任务ID

    __table_args__ = (
        Index('idx_async_task_status', 'status'),
        Index('idx_async_task_employee', 'employee_id'),
        Index('idx_async_task_todo', 'todo_id'),
    )
