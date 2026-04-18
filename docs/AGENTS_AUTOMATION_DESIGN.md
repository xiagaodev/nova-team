# AI Agents 自动化系统设计文档

## 一、数据模型设计

### 1.1 新增模型

```python
# nova_platform/models.py

class ProjectMethodology(Base):
    """项目方法论定义"""
    __tablename__ = "project_methodologies"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)  # 如 "敏捷Scrum"
    project_type: Mapped[str] = mapped_column(String(50), nullable=False)  # software_dev, content_ops
    description: Mapped[str] = mapped_column(Text, default="")

    # 适用场景 (JSON)
    applicable_scenarios: Mapped[str] = mapped_column(Text, default="{}")
    # {"team_size": "3-10人", "timeline": "1-6个月", "uncertainty": "高"}

    # 阶段定义 (JSON数组)
    phases: Mapped[str] = mapped_column(Text, nullable=False)
    # [{"id": "backlog", "name": "需求梳理", "objective": "...", ...}]

    # WBS拆解规则 (JSON)
    wbs_rules: Mapped[str] = mapped_column(Text, default="{}")
    # {"max_depth": 4, "task_size_limit": "2人日", "require_dependency": true}

    # 最佳实践 (JSON)
    best_practices: Mapped[str] = mapped_column(Text, default="[]")
    # [{"phase": "backlog", "practices": ["用户故事遵循INVEST原则"]}]

    # 决策规则 (JSON)
    decision_rules: Mapped[str] = mapped_column(Text, default="{}")
    # {"auto_dispatch": true, "leader_decide_on": ["prioritization", "phase_transition"]}

    # 示例项目 (JSON) - 用于prompt示例
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
    # clarification_needed: 需求澄清
    # decision_needed: 决策请求
    # approval_needed: 审批请求
    # escalation: 问题升级

    # 来源
    source: Mapped[str] = mapped_column(String(50), default="leader")  # leader, system

    # 上下文信息 (JSON)
    context: Mapped[str] = mapped_column(Text, default="{}")
    # {"phase": "backlog", "task_id": "xxx", "decomposition_attempt": 1}

    # 问题/请求内容
    questions: Mapped[str] = mapped_column(Text, nullable=False)  # JSON数组
    # [{"question": "...", "options": [...], "priority": "high"}]

    # Leader的建议 (如果有)
    leader_recommendation: Mapped[str] = mapped_column(Text, default="")

    # 状态
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending, answered, skipped

    # 人类响应
    human_response: Mapped[str] = mapped_column(Text, default="")
    response_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)

    # 响应后Leader的处理
    leader_action_taken: Mapped[str] = mapped_column(Text, default="")  # JSON
    action_taken_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)

    # 依赖的其他交互ID (JSON数组) - 用于依赖检测
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
    # decomposition: WBS拆解
    # decision: 决策
    # phase_transition: 阶段转换

    # 调用上下文 (JSON) - 用于检测是否是重复调用
    invocation_context: Mapped[str] = mapped_column(Text, default="{}")
    # {"requirement_hash": "xxx", "phase": "backlog"}

    # 锁定状态
    status: Mapped[str] = mapped_column(String(20), default="in_progress")
    # in_progress: 处理中
    # completed: 已完成
    # failed: 失败
    # cancelled: 取消

    # 结果
    result: Mapped[str] = mapped_column(Text, default="")  # JSON
    error: Mapped[str] = mapped_column(Text, default="")

    # 时间戳
    locked_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)

    # 超时时间（秒）
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=300)  # 5分钟默认

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
    phase_id: Mapped[str] = mapped_column(String(50), nullable=False)  # backlog, sprint, etc.
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
    result: Mapped[str] = mapped_column(String(20), default="in_progress")  # in_progress, completed, skipped

    # 备注
    notes: Mapped[str] = mapped_column(Text, default="")

    __table_args__ = (
        Index('idx_phase_history_project', 'project_id'),
        Index('idx_phase_history_phase', 'phase_id'),
        Index('idx_phase_history_started', 'started_at'),
    )
```

### 1.2 修改现有模型

```python
# Project 模型添加字段
class Project(Base):
    # ... 现有字段 ...

    # 新增字段
    methodology_id: Mapped[str] = mapped_column(String(36), nullable=True)  # 关联的方法论
    current_phase: Mapped[str] = mapped_column(String(50), default="planning")  # 当前阶段
    phase_history_id: Mapped[str] = mapped_column(String(36), nullable=True)  # 当前阶段历史记录ID

    # 项目配置 (JSON) - 覆盖方法论默认配置
    project_config: Mapped[str] = mapped_column(Text, default="{}")
    # {"auto_dispatch": true, "require_human_approval": false}

    __table_args__ = (
        # ... 现有索引 ...
        Index('idx_project_phase', 'current_phase'),
    )
```

## 二、WBS拆解服务设计

### 2.1 动静结合拆解流程

```python
# nova_platform/services/wbs_service.py

class WBSService:
    """WBS拆解服务 - 动静结合策略"""

    async def decompose_incremental(
        self,
        session: Session,
        project_id: str,
        requirements: list[str]
    ) -> dict:
        """
        增量式WBS拆解

        策略：
        1. 拆解第一个模块/需求
        2. 立即创建任务并分配
        3. 同时继续拆解下一个模块
        4. 如果遇到问题，暂停并请求人类澄清
        5. 根据反馈调整后续拆解
        """

        project = session.query(Project).filter_by(id=project_id).first()
        methodology = self._get_methodology(session, project.methodology_id)

        results = {
            "modules_decomposed": [],
            "tasks_created": [],
            "clarifications_needed": [],
            "errors": []
        }

        # 获取当前可工作的团队成员
        available_members = self._get_available_members(session, project_id)

        for requirement in requirements:
            # 检查防重锁
            lock = self._acquire_decomposition_lock(
                session, project_id, requirement
            )
            if not lock:
                results["errors"].append({
                    "requirement": requirement[:50],
                    "reason": "already_being_processed"
                })
                continue

            try:
                # 调用Leader进行WBS拆解
                decomposition = await self._leader_decompose(
                    session, project_id, requirement, methodology
                )

                if decomposition.get("needs_clarification"):
                    # 需要人类澄清
                    interaction = await self._create_clarification_request(
                        session, project_id, requirement, decomposition
                    )
                    results["clarifications_needed"].append({
                        "requirement": requirement[:50],
                        "interaction_id": interaction.id
                    })
                    # 暂停后续拆解
                    break

                # 创建任务（带依赖关系）
                tasks = await self._create_tasks_from_decomposition(
                    session, project_id, decomposition, methodology
                )
                results["tasks_created"].extend(tasks)

                # 立即分配可执行的任务
                dispatched = await self._dispatch_ready_tasks(
                    session, project_id, tasks, available_members
                )
                results["modules_decomposed"].append({
                    "requirement": requirement[:50],
                    "tasks_created": len(tasks),
                    "tasks_dispatched": dispatched
                })

                # 释放锁
                self._release_decomposition_lock(session, lock)

            except Exception as e:
                results["errors"].append({
                    "requirement": requirement[:50],
                    "error": str(e)
                })
                self._release_decomposition_lock(session, lock)

        return results

    async def _leader_decompose(
        self,
        session: Session,
        project_id: str,
        requirement: str,
        methodology: dict
    ) -> dict:
        """调用Leader进行WBS拆解"""

        project = session.query(Project).filter_by(id=project_id).first()
        current_phase = project.current_phase
        phase_config = self._get_phase_config(methodology, current_phase)

        # 获取已有任务（用于避免重复）
        existing_tasks = session.query(Todo).filter_by(
            project_id=project_id
        ).all()

        # 构建prompt
        prompt = self._build_decomposition_prompt(
            project=project,
            methodology=methodology,
            phase_config=phase_config,
            requirement=requirement,
            existing_tasks=existing_tasks
        )

        # 获取Leader
        leader = self._get_project_leader(session, project_id)

        # 异步调用Leader
        result = await agent_service.dispatch_task_async(
            session=session,
            employee_id=leader.id,
            task=prompt,
            project_id=project_id
        )

        # 解析结果
        return self._parse_decomposition_result(result)

    def _build_decomposition_prompt(
        self, project, methodology, phase_config, requirement, existing_tasks
    ) -> str:
        """构建WBS拆解prompt"""

        existing_summary = self._summarize_existing_tasks(existing_tasks)

        return f"""你是项目 "{project.name}" 的负责人，正在进行WBS（工作分解结构）拆解。

【项目信息】
项目目标: {project.description}
项目类型: {methodology['project_type']}
方法论: {methodology['name']}
当前阶段: {phase_config['name']}

【阶段指导】
阶段目标: {phase_config['objective']}
阶段最佳实践:
{self._format_best_practices(phase_config.get('best_practices', []))}

【WBS拆解规则】
{self._format_wbs_rules(methodology.get('wbs_rules', {}))}

【已有任务】
{existing_summary}
注意：不要创建与已有任务重复的任务。

【待拆解需求】
{requirement}

请按照以下步骤进行WBS拆解：

1. **理解需求**：首先明确需求的交付物是什么
2. **识别分解点**：找出主要的分解维度（功能模块、层次、阶段等）
3. **分解任务**：
   - 第1层：识别主要交付物（Deliverables）
   - 第2层：将交付物分解为工作包（Work Packages）
   - 第3层：将工作包分解为具体任务（Tasks）
   - 第4层（如需要）：任务进一步细分为子任务

4. **建立依赖**：识别任务之间的前置关系

5. **检查完整性**：确保拆解覆盖需求的所有方面

输出JSON格式：
{{
  "deliverables": [
    {{
      "id": "d1",
      "name": "主要交付物名称",
      "description": "交付物描述",
      "work_packages": [
        {{
          "id": "wp1",
          "name": "工作包名称",
          "description": "工作包描述",
          "tasks": [
            {{
              "id": "t1",
              "title": "任务标题",
              "description": "详细描述",
              "assignee_role": "需要的角色类型（frontend/backend/designer等）",
              "acceptance_criteria": "验收标准",
              "estimated_hours": 预估工时,
              "depends_on": ["wp1"] 或 ["t1"],
              "priority": "high/medium/low",
              "tags": ["标签1", "标签2"]
            }}
          ]
        }}
      ]
    }}
  ],
  "assumptions": ["拆解时做的假设"],
  "risks": ["识别的风险"],
  "notes": "其他需要说明的内容",
  "needs_clarification": false,
  "questions": ["如果需求不明确，列出需要向人类确认的问题"]
}}

如果需求不够清晰无法进行有效拆解，请设置 needs_clarification=true 并在 questions 中列出具体问题。
不要强行拆解不明确的需求。
"""

    async def _create_tasks_from_decomposition(
        self,
        session: Session,
        project_id: str,
        decomposition: dict,
        methodology: dict
    ) -> list:
        """从拆解结果创建任务"""

        tasks_created = []
        task_id_map = {}  # 映射逻辑ID到真实ID

        deliverables = decomposition.get("deliverables", [])

        for deliverable in deliverables:
            for wp in deliverable.get("work_packages", []):
                for task_data in wp.get("tasks", []):
                    # 解析依赖关系
                    depends_on = []
                    for dep_ref in task_data.get("depends_on", []):
                        real_id = task_id_map.get(dep_ref)
                        if real_id:
                            depends_on.append(real_id)

                    # 创建任务
                    todo = todo_service.create_todo(
                        session=session,
                        title=task_data["title"],
                        description=task_data.get("description", ""),
                        project_id=project_id,
                        priority=task_data.get("priority", "medium"),
                        assignee_id=None,  # 稍后分配
                        depends_on=json.dumps(depends_on)
                    )

                    # 保存逻辑ID映射
                    task_id_map[task_data["id"]] = todo.id

                    # 保存额外信息到knowledge（验收标准、角色需求等）
                    knowledge = Knowledge(
                        project_id=project_id,
                        title=f"任务详情: {task_data['title']}",
                        content=json.dumps({
                            "acceptance_criteria": task_data.get("acceptance_criteria"),
                            "assignee_role": task_data.get("assignee_role"),
                            "estimated_hours": task_data.get("estimated_hours"),
                            "tags": task_data.get("tags", []),
                            "deliverable": deliverable["name"],
                            "work_package": wp["name"]
                        }, ensure_ascii=False),
                        tags=json.dumps(["task_detail", task_data.get("assignee_role", "general")])
                    )
                    session.add(knowledge)

                    tasks_created.append(todo)

        session.commit()
        return tasks_created

    async def _dispatch_ready_tasks(
        self,
        session: Session,
        project_id: str,
        tasks: list,
        available_members: list
    ) -> int:
        """立即分配可执行的任务（无依赖或依赖已满足）"""

        dispatched = 0
        graph = build_dependency_graph(session, project_id)
        ready_tasks = graph.get_ready_tasks()

        for task in tasks:
            if task.id in ready_tasks:
                # 找到合适的成员
                for member in available_members:
                    emp = member["employee"]
                    if emp.type != "human":
                        # 检查是否已经在工作中
                        busy = session.query(Todo).filter(
                            Todo.assignee_id == emp.id,
                            Todo.status == "in_progress"
                        ).first()

                        if not busy:
                            # 分配任务
                            todo.assignee_id = emp.id
                            todo.status = "in_progress"
                            session.commit()

                            # 异步执行
                            task_desc = f"[项目: {project_id}] {todo.title}"
                            agent_service.dispatch_task_async(
                                session, emp.id, task_desc, project_id
                            )

                            dispatched += 1
                            break

        return dispatched
```

## 三、多层决策引擎

```python
# nova_platform/services/decision_engine.py

class DecisionEngine:
    """多层决策引擎"""

    async def make_decision(
        self,
        session: Session,
        project_id: str,
        observation: dict
    ) -> dict:
        """
        多层决策流程

        第1层：系统规则（快速、确定）
        第2层：Leader决策（项目级，异步）
        第3层：人类决策（重大决策）
        """

        # 第1层：系统规则
        system_decision = self._system_rule_decision(session, project_id, observation)

        if system_decision.get("confident"):
            # 系统有信心直接决策
            return {
                "layer": "system",
                "decision": system_decision
            }

        # 第2层：Leader决策（异步，防重）
        leader_decision = await self._leader_decision(
            session, project_id, observation, system_decision
        )

        if leader_decision.get("needs_human"):
            # 第3层：需要人类决策
            return await self._escalate_to_human(
                session, project_id, observation, leader_decision
            )

        return {
            "layer": "leader",
            "decision": leader_decision
        }

    def _system_rule_decision(self, session, project_id, observation):
        """第1层：系统规则决策"""

        project = session.query(Project).filter_by(id=project_id).first()
        config = json.loads(project.project_config or "{}")
        methodology = self._get_methodology(session, project.methodology_id)
        decision_rules = methodology.get("decision_rules", {})

        stats = observation.get("status_summary", {})

        # 规则1：自动分发（如果启用）
        if config.get("auto_dispatch", decision_rules.get("auto_dispatch", True)):
            runnable = observation.get("runnable_tasks", [])
            if len(runnable) == 1:
                return {
                    "confident": True,
                    "action": "auto_dispatch_single",
                    "task_id": runnable[0].id,
                    "reason": "唯一可执行任务，自动分发"
                }

        # 规则2：任务阻塞自动重置
        blockers = observation.get("blockers", [])
        if blockers:
            return {
                "confident": True,
                "action": "reset_blocked_tasks",
                "task_ids": [b["todo"].id for b in blockers],
                "reason": f"{len(blockers)}个任务阻塞超时"
            }

        # 规则3：所有任务完成
        if stats.get("completed", 0) > 0 and stats.get("pending", 0) == 0 and stats.get("in_progress", 0) == 0:
            return {
                "confident": True,
                "action": "complete_project",
                "reason": "所有任务已完成"
            }

        # 不确定，交给Leader
        return {
            "confident": False,
            "hints": {
                "runnable_count": len(observation.get("runnable_tasks", [])),
                "idle_agents": len([m for m in observation.get("members", []) if not m.get("busy")]),
                "pending_count": stats.get("pending", 0)
            }
        }

    async def _leader_decision(
        self, session, project_id, observation, system_hints
    ):
        """第2层：Leader决策（异步，防重）"""

        # 1. 检查是否已有相同决策在进行中
        context_hash = self._compute_decision_context(observation, system_hints)
        existing_lock = session.query(LeaderInvocationLock).filter(
            LeaderInvocationLock.project_id == project_id,
            LeaderInvocationLock.invocation_type == "decision",
            LeaderInvocationLock.status == "in_progress",
            LeaderInvocationLock.locked_at > datetime.utcnow() - timedelta(minutes=5)
        ).first()

        if existing_lock:
            # 检查是否是相同的决策上下文
            existing_context = json.loads(existing_lock.invocation_context or "{}")
            if existing_context.get("hash") == context_hash:
                # 相同决策，等待结果
                return await self._wait_for_lock_result(existing_lock)

        # 2. 创建新锁
        lock = LeaderInvocationLock(
            project_id=project_id,
            invocation_type="decision",
            invocation_context=json.dumps({"hash": context_hash}),
            status="in_progress"
        )
        session.add(lock)
        session.commit()

        try:
            # 3. 调用Leader
            project = session.query(Project).filter_by(id=project_id).first()
            methodology = self._get_methodology(session, project.methodology_id)
            current_phase = project.current_phase

            prompt = self._build_leader_decision_prompt(
                project, methodology, current_phase, observation, system_hints
            )

            leader = self._get_project_leader(session, project_id)
            result = await agent_service.dispatch_task_async(
                session, leader.id, prompt, project_id
            )

            # 4. 解析决策
            decision = self._parse_leader_decision(result)

            # 5. 更新锁状态
            lock.result = json.dumps(decision)
            lock.status = "completed"
            lock.completed_at = datetime.utcnow()
            session.commit()

            return decision

        except Exception as e:
            lock.status = "failed"
            lock.error = str(e)
            lock.completed_at = datetime.utcnow()
            session.commit()
            raise
```

## 四、人类交互处理

```python
# nova_platform/services/human_interaction_service.py

class HumanInteractionService:
    """人类交互服务"""

    async def create_interaction(
        self,
        session: Session,
        project_id: str,
        interaction_type: str,
        questions: list,
        context: dict,
        source: str = "leader",
        leader_recommendation: str = ""
    ) -> HumanInteraction:
        """创建人类交互请求"""

        # 检查依赖
        dependencies = context.get("depends_on_interactions", [])
        for dep_id in dependencies:
            dep = session.query(HumanInteraction).filter_by(id=dep_id).first()
            if not dep or dep.status != "answered":
                raise ValueError(f"依赖交互未完成: {dep_id}")

        interaction = HumanInteraction(
            project_id=project_id,
            interaction_type=interaction_type,
            source=source,
            context=json.dumps(context),
            questions=json.dumps(questions),
            leader_recommendation=leader_recommendation,
            depends_on_interactions=json.dumps(dependencies),
            status="pending"
        )

        session.add(interaction)
        session.commit()

        # 更新项目状态
        project = session.query(Project).filter_by(id=project_id).first()
        if project:
            project.status = "awaiting_human"
            session.commit()

        return interaction

    async def check_and_resume(
        self, session: Session, project_id: str
    ) -> dict:
        """检查人类交互是否全部完成，如果完成则恢复项目"""

        interactions = session.query(HumanInteraction).filter(
            HumanInteraction.project_id == project_id,
            HumanInteraction.status == "pending"
        ).all()

        if interactions:
            # 还有待处理的交互
            return {
                "can_resume": False,
                "pending_count": len(interactions),
                "interactions": [i.id for i in interactions]
            }

        # 所有交互已完成，恢复项目
        project = session.query(Project).filter_by(id=project_id).first()
        if project and project.status == "awaiting_human":
            project.status = "active"
            session.commit()

            # 触发Leader继续处理
            await self._trigger_leader_resume(session, project_id)

            return {
                "can_resume": True,
                "action": "resumed"
            }

        return {"can_resume": True, "action": "already_active"}

    async def answer_interaction(
        self,
        session: Session,
        interaction_id: str,
        response: str,
        responder: str
    ) -> dict:
        """回答人类交互"""

        interaction = session.query(HumanInteraction).filter_by(
            id=interaction_id
        ).first()

        if not interaction:
            raise ValueError("交互不存在")

        if interaction.status != "pending":
            return {"error": "交互已关闭"}

        interaction.human_response = response
        interaction.status = "answered"
        interaction.response_at = datetime.utcnow()
        session.commit()

        # 检查是否可以恢复项目
        project_id = interaction.project_id
        check_result = await self.check_and_resume(session, project_id)

        # 记录Leader的后续处理
        if check_result.get("action") == "resumed":
            # Leader将会处理这个响应
            leader_action = await self._process_leader_response(
                session, interaction
            )
            interaction.leader_action_taken = json.dumps(leader_action)
            interaction.action_taken_at = datetime.utcnow()
            session.commit()

        return {
            "success": True,
            "interaction_id": interaction_id,
            "project_can_resume": check_result.get("can_resume", False)
        }
```

## 五、WebUI接口

```python
# nova_platform/api/human_interaction_api.py

@bp.route("/api/interactions/pending", methods=["GET"])
def get_pending_interactions():
    """获取待处理的人类交互"""
    project_id = request.args.get("project_id")
    session = get_session()

    interactions = session.query(HumanInteraction).filter(
        HumanInteraction.project_id == project_id,
        HumanInteraction.status == "pending"
    ).order_by(HumanInteraction.created_at).all()

    return jsonify({
        "interactions": [{
            "id": i.id,
            "type": i.interaction_type,
            "questions": json.loads(i.questions),
            "leader_recommendation": i.leader_recommendation,
            "context": json.loads(i.context),
            "created_at": i.created_at.isoformat()
        } for i in interactions]
    })

@bp.route("/api/interactions/<interaction_id>/answer", methods=["POST"])
def answer_interaction(interaction_id):
    """回答人类交互"""
    data = request.get_json()
    response = data.get("response")

    if not response:
        return jsonify({"error": "缺少response"}), 400

    session = get_session()
    service = HumanInteractionService()

    result = service.answer_interaction(
        session, interaction_id, response, "web_user"
    )

    return jsonify(result)
```

## 六、后台监控服务

```python
# nova_platform/services/human_monitor_service.py

class HumanInteractionMonitor:
    """人类交互监控服务 - 后台定时运行"""

    async def monitor_all_projects(self, session: Session):
        """监控所有等待人类响应的项目"""

        awaiting_projects = session.query(Project).filter(
            Project.status == "awaiting_human"
        ).all()

        results = []
        for project in awaiting_projects:
            result = await self.check_project(session, project.id)
            results.append(result)

        return results

    async def check_project(self, session, project_id: str):
        """检查单个项目是否可以恢复"""

        service = HumanInteractionService()
        return await service.check_and_resume(session, project_id)
```

## 七、Migration

```python
# nova_platform/migrations/versions/001_add_methodology_models.py

def upgrade():
    # 创建新表
    op.create_table(
        'project_methodologies',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('name', sa.String(100), nullable=False, unique=True),
        sa.Column('project_type', sa.String(50), nullable=False),
        sa.Column('description', sa.Text),
        sa.Column('applicable_scenarios', sa.Text),
        sa.Column('phases', sa.Text, nullable=False),
        sa.Column('wbs_rules', sa.Text),
        sa.Column('best_practices', sa.Text),
        sa.Column('decision_rules', sa.Text),
        sa.Column('example_project', sa.Text),
        sa.Column('is_active', sa.Boolean, default=True),
        sa.Column('created_at', sa.DateTime),
        sa.Column('updated_at', sa.DateTime)
    )

    op.create_table(
        'human_interactions',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('project_id', sa.String(36), nullable=False),
        sa.Column('interaction_type', sa.String(50), nullable=False),
        sa.Column('source', sa.String(50)),
        sa.Column('context', sa.Text),
        sa.Column('questions', sa.Text),
        sa.Column('leader_recommendation', sa.Text),
        sa.Column('status', sa.String(20)),
        sa.Column('human_response', sa.Text),
        sa.Column('response_at', sa.DateTime),
        sa.Column('leader_action_taken', sa.Text),
        sa.Column('action_taken_at', sa.DateTime),
        sa.Column('depends_on_interactions', sa.Text),
        sa.Column('created_at', sa.DateTime),
        sa.Column('updated_at', sa.DateTime)
    )

    # ... 其他表 ...

    # 修改Project表
    op.add_column('projects', sa.Column('methodology_id', sa.String(36)))
    op.add_column('projects', sa.Column('current_phase', sa.String(50)))
    op.add_column('projects', sa.Column('phase_history_id', sa.String(36)))
    op.add_column('projects', sa.Column('project_config', sa.Text))

    # 创建索引
    op.create_index('idx_project_phase', 'projects', ['current_phase'])

    # 插入默认方法论
    _insert_default_methodologies()

def _insert_default_methodologies():
    """插入默认的方法论模板"""
    session = Session(bind=op.get_bind())

    # 敏捷Scrum方法论
    scrum = ProjectMethodology(
        name="敏捷Scrum",
        project_type="software_dev",
        description="适用于软件开发的敏捷方法论",
        applicable_scenarios=json.dumps({
            "team_size": "3-10人",
            "timeline": "1-6个月",
            "uncertainty": "中高",
            "iteration": "1-4周Sprint"
        }),
        phases=json.dumps(_SCRUM_PHASES),
        wbs_rules=json.dumps({
            "max_depth": 4,
            "task_size_limit": "2人日",
            "require_dependency": True,
            "decomposition_pattern": "Epic → Feature → Story → Task"
        }),
        best_practices=json.dumps(_SCRUM_BEST_PRACTICES),
        decision_rules=json.dumps({
            "auto_dispatch": True,
            "leader_decide_on": ["prioritization", "phase_transition", "blocker_escalation"]
        })
    )
    session.add(scrum)

    # 内容运营方法论
    content_ops = ProjectMethodology(
        name="内容运营",
        project_type="content_ops",
        description="适用于内容生产和发布的流程管理",
        applicable_scenarios=json.dumps({
            "team_size": "2-8人",
            "timeline": "持续进行",
            "uncertainty": "低",
            "workflow": "线性流程"
        }),
        phases=json.dumps(_CONTENT_PHASES),
        wbs_rules=json.dumps({
            "max_depth": 3,
            "task_size_limit": "1人日",
            "require_dependency": True,
            "decomposition_pattern": "栏目 → 主题 → 文章"
        }),
        best_practices=json.dumps(_CONTENT_BEST_PRACTICES),
        decision_rules=json.dumps({
            "auto_dispatch": True,
            "leader_decide_on": ["content_approval", "schedule_adjustment"]
        })
    )
    session.add(content_ops)

    session.commit()

_SCRUM_PHASES = [
    {
        "id": "backlog",
        "name": "产品待办",
        "objective": "创建和维护产品待办列表",
        "entry_condition": "项目启动",
        "exit_condition": "至少有3个用户故事",
        "checkpoints": [...],
        "best_practices": [...]
    },
    # ... 其他阶段 ...
]
```

## 八、实施计划

### Phase 1: 数据模型（Week 1）
- [ ] 创建新模型
- [ ] 编写migration
- [ ] 插入默认方法论数据

### Phase 2: WBS服务（Week 2）
- [ ] 实现WBSService核心逻辑
- [ ] 实现增量拆解
- [ ] 实现依赖管理

### Phase 3: 决策引擎（Week 2-3）
- [ ] 实现多层决策
- [ ] 实现防重机制
- [ ] 实现阶段检查点

### Phase 4: 人类交互（Week 3）
- [ ] 实现交互记录表
- [ ] 实现WebUI接口
- [ ] 实现后台监控

### Phase 5: 集成测试（Week 4）
- [ ] 端到端测试
- [ ] 性能优化
- [ ] 文档完善
