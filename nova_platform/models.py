from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String, Text, DateTime, Float, Index, Integer, Boolean
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
    workspace_path: Mapped[str] = mapped_column(String(500), nullable=True)  # 项目工作空间目录

    # 方法论相关字段
    methodology_id: Mapped[str] = mapped_column(String(36), nullable=True)
    current_phase: Mapped[str] = mapped_column(String(50), default="planning")
    phase_history_id: Mapped[str] = mapped_column(String(36), nullable=True)

    # 项目配置 (JSON) - 覆盖方法论默认配置
    project_config: Mapped[str] = mapped_column(Text, default="{}")

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index('idx_project_status', 'status'),
        Index('idx_project_template', 'template'),
        Index('idx_project_phase', 'current_phase'),
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
    role: Mapped[str] = mapped_column(String(50), default="member")  # leader, member, reviewer
    joined_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Todo(Base):
    __tablename__ = "todos"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    project_id: Mapped[str] = mapped_column(String(36), nullable=False)
    assignee_id: Mapped[str] = mapped_column(String(36), nullable=True)
    agent_task_id: Mapped[str] = mapped_column(String(100), nullable=True)  # 关联 agent_service 的异步任务 ID
    process_id: Mapped[int] = mapped_column(Integer, nullable=True)  # Agent 进程 PID
    session_id: Mapped[str] = mapped_column(String(100), nullable=True)  # 会话标识，同一项目同一agent使用相同session_id
    status: Mapped[str] = mapped_column(String(20), default="pending")
    priority: Mapped[str] = mapped_column(String(20), default="medium")
    due_date: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    depends_on: Mapped[str] = mapped_column(Text, default="[]")  # JSON 数组，存储依赖的 TODO ID 列表
    work_summary: Mapped[str] = mapped_column(Text, default="")  # 工作总结，任务完成后填写
    completed_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)  # 完成时间
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


class ProjectMethodology(Base):
    """项目方法论定义"""
    __tablename__ = "project_methodologies"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    project_type: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")

    # 适用场景 (JSON)
    applicable_scenarios: Mapped[str] = mapped_column(Text, default="{}")

    # 阶段定义 (JSON数组)
    phases: Mapped[str] = mapped_column(Text, nullable=False)

    # WBS拆解规则 (JSON)
    wbs_rules: Mapped[str] = mapped_column(Text, default="{}")

    # 最佳实践 (JSON)
    best_practices: Mapped[str] = mapped_column(Text, default="[]")

    # 决策规则 (JSON)
    decision_rules: Mapped[str] = mapped_column(Text, default="{}")

    # 示例项目 (JSON)
    example_project: Mapped[str] = mapped_column(Text, default="")

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index('idx_methodology_type', 'project_type'),
        Index('idx_methodology_active', 'is_active'),
    )


class HumanInteraction(Base):
    """人类交互记录 - Leader与人类的沟通"""
    __tablename__ = "human_interactions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id: Mapped[str] = mapped_column(String(36), nullable=False)

    # 交互类型
    interaction_type: Mapped[str] = mapped_column(String(50), nullable=False)

    # 来源
    source: Mapped[str] = mapped_column(String(50), default="leader")

    # 上下文信息 (JSON)
    context: Mapped[str] = mapped_column(Text, default="{}")

    # 问题/请求内容 (JSON数组)
    questions: Mapped[str] = mapped_column(Text, nullable=False)

    # Leader的建议
    leader_recommendation: Mapped[str] = mapped_column(Text, default="")

    # 状态
    status: Mapped[str] = mapped_column(String(20), default="pending")

    # 人类响应
    human_response: Mapped[str] = mapped_column(Text, default="")
    response_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)

    # 响应后Leader的处理 (JSON)
    leader_action_taken: Mapped[str] = mapped_column(Text, default="")
    action_taken_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)

    # 依赖的其他交互ID (JSON数组)
    depends_on_interactions: Mapped[str] = mapped_column(Text, default="[]")

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index('idx_interaction_project_status', 'project_id', 'status'),
        Index('idx_interaction_type', 'interaction_type'),
        Index('idx_interaction_created', 'created_at'),
    )


class LeaderInvocationLock(Base):
    """Leader调用防重锁"""
    __tablename__ = "leader_invocation_locks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id: Mapped[str] = mapped_column(String(36), nullable=False)

    # 调用类型
    invocation_type: Mapped[str] = mapped_column(String(50), nullable=False)

    # 调用上下文 (JSON) - 用于检测是否是重复调用
    invocation_context: Mapped[str] = mapped_column(Text, default="{}")

    # 锁定状态
    status: Mapped[str] = mapped_column(String(20), default="in_progress")

    # 结果 (JSON)
    result: Mapped[str] = mapped_column(Text, default="")
    error: Mapped[str] = mapped_column(Text, default="")

    # 时间戳
    locked_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)

    # 超时时间（秒）
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=300)

    __table_args__ = (
        Index('idx_lock_project_type', 'project_id', 'invocation_type'),
        Index('idx_lock_status', 'status'),
        Index('idx_lock_locked_at', 'locked_at'),
    )


class ProjectPhaseHistory(Base):
    """项目阶段历史"""
    __tablename__ = "project_phase_history"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id: Mapped[str] = mapped_column(String(36), nullable=False)

    # 阶段信息
    phase_id: Mapped[str] = mapped_column(String(50), nullable=False)
    phase_name: Mapped[str] = mapped_column(String(100), nullable=False)

    # 阶段目标
    phase_objective: Mapped[str] = mapped_column(Text, default="")

    # 进入/退出条件
    entry_condition: Mapped[str] = mapped_column(Text, default="")
    exit_condition: Mapped[str] = mapped_column(Text, default="")

    # 时间
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)

    # 结果
    result: Mapped[str] = mapped_column(String(20), default="in_progress")

    # 备注
    notes: Mapped[str] = mapped_column(Text, default="")

    __table_args__ = (
        Index('idx_phase_history_project', 'project_id'),
        Index('idx_phase_history_phase', 'phase_id'),
        Index('idx_phase_history_started', 'started_at'),
    )
