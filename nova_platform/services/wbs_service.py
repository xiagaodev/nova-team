"""
WBS（工作分解结构）服务

实现动静结合的任务拆解策略：
- 拆解一个模块后立即创建任务并分配
- 同时继续拆解下一个模块
- 遇到问题时暂停并请求人类澄清
"""

import json
import hashlib
from datetime import datetime
from typing import Optional, List, Dict
from sqlalchemy.orm import Session

from nova_platform.models import (
    Project, Todo, Employee, ProjectMember,
    ProjectMethodology, HumanInteraction, Knowledge
)
from nova_platform.services import (
    todo_service,
    agent_service,
    project_member_service,
    human_interaction_service
)
from nova_platform.services.leader_lock_service import (
    acquire_decomposition_lock,
    release_lock,
    fail_lock
)


class WBSService:
    """WBS拆解服务"""

    def __init__(self):
        self.max_decomposition_attempts = 3  # 最大拆解尝试次数
        self.requirement_clarification_timeout = 86400  # 需求澄清超时（24小时）

    async def decompose_incremental(
        self,
        session: Session,
        project_id: str,
        requirements: List[str],
        auto_dispatch: bool = True
    ) -> dict:
        """
        增量式WBS拆解

        Args:
            session: 数据库会话
            project_id: 项目ID
            requirements: 需求列表
            auto_dispatch: 是否自动分配任务

        Returns:
            拆解结果
        """

        project = session.query(Project).filter_by(id=project_id).first()
        if not project:
            return {"success": False, "error": "项目不存在"}

        # 获取方法论
        methodology = self._get_methodology(session, project)
        if not methodology:
            return {"success": False, "error": "项目没有关联方法论"}

        results = {
            "success": True,
            "project_id": project_id,
            "modules_decomposed": [],
            "tasks_created": [],
            "clarifications_needed": [],
            "errors": []
        }

        # 获取当前可工作的团队成员
        available_members = self._get_available_members(session, project_id)

        # 记录开始时间
        start_time = datetime.utcnow()

        for requirement in requirements:
            # 检查项目状态
            project = session.query(Project).filter_by(id=project_id).first()
            if project.status == "awaiting_human":
                # 等待人类响应，暂停拆解
                results["status"] = "paused_awaiting_human"
                results["message"] = "等待人类响应，暂停拆解"
                break

            # 尝试获取拆解锁（防重）
            lock = acquire_decomposition_lock(session, project_id, requirement)

            if not lock:
                # 已有相同的拆解在进行中，跳过
                results["errors"].append({
                    "requirement": requirement[:50],
                    "reason": "already_being_processed"
                })
                continue

            try:
                # 检查是否已经拆解过类似需求
                existing_tasks = self._check_existing_decomposition(
                    session, project_id, requirement
                )

                if existing_tasks:
                    # 已有类似任务，跳过
                    results["modules_decomposed"].append({
                        "requirement": requirement[:50],
                        "action": "skipped",
                        "reason": "similar_tasks_exist",
                        "existing_task_count": len(existing_tasks)
                    })
                    release_lock(session, lock)
                    continue

                # 调用Leader进行WBS拆解
                decomposition = await self._leader_decompose(
                    session, project_id, requirement, methodology, existing_tasks
                )

                if decomposition.get("needs_clarification"):
                    # 需要人类澄清
                    interaction = await self._request_clarification(
                        session, project_id, requirement, decomposition
                    )
                    results["clarifications_needed"].append({
                        "requirement": requirement[:50],
                        "interaction_id": interaction.id
                    })

                    # 暂停后续拆解
                    results["status"] = "awaiting_clarification"
                    results["message"] = "需要人类澄清需求"
                    break

                # 创建任务（带依赖关系）
                tasks = await self._create_tasks_from_decomposition(
                    session, project_id, decomposition, methodology
                )
                results["tasks_created"].extend(tasks)

                # 立即分配可执行的任务
                dispatched_count = 0
                if auto_dispatch and available_members:
                    dispatched_count = await self._dispatch_ready_tasks(
                        session, project_id, tasks, available_members
                    )

                results["modules_decomposed"].append({
                    "requirement": requirement[:50],
                    "tasks_created": len(tasks),
                    "tasks_dispatched": dispatched_count
                })

                # 释放锁
                release_lock(session, lock, {
                    "success": True,
                    "tasks_created": len(tasks),
                    "tasks_dispatched": dispatched_count
                })

            except Exception as e:
                # 失败，释放锁
                lock_obj = session.query(LeaderInvocationLock).filter(
                    LeaderInvocationLock.project_id == project_id,
                    LeaderInvocationLock.invocation_type == "decomposition",
                    LeaderInvocationLock.status == "in_progress"
                ).first()

                if lock_obj:
                    fail_lock(session, lock_obj, str(e))

                results["errors"].append({
                    "requirement": requirement[:50],
                    "error": str(e)
                })

        # 计算耗时
        elapsed = (datetime.utcnow() - start_time).total_seconds()
        results["elapsed_seconds"] = elapsed

        # 更新项目阶段
        if results.get("clarifications_needed"):
            # 有待处理的澄清
            pass  # 项目状态已设为awaiting_human
        elif results.get("tasks_created"):
            # 有任务创建，更新项目状态
            project = session.query(Project).filter_by(id=project_id).first()
            if project and project.status == "planning":
                project.status = "active"
                project.current_phase = "execution"
                session.commit()

        return results

    def _get_methodology(
        self, session: Session, project: Project
    ) -> Optional[Dict]:
        """获取项目的方法论配置"""
        if not project.methodology_id:
            # 尝试根据template匹配
            methodology = session.query(ProjectMethodology).filter(
                ProjectMethodology.project_type == project.template,
                ProjectMethodology.is_active == True
            ).first()
        else:
            methodology = session.query(ProjectMethodology).filter_by(
                id=project.methodology_id
            ).first()

        if not methodology:
            return None

        # 解析JSON字段
        return {
            "id": methodology.id,
            "name": methodology.name,
            "project_type": methodology.project_type,
            "phases": json.loads(methodology.phases),
            "wbs_rules": json.loads(methodology.wbs_rules),
            "best_practices": json.loads(methodology.best_practices),
            "decision_rules": json.loads(methodology.decision_rules)
        }

    def _get_available_members(
        self, session: Session, project_id: str
    ) -> List[Dict]:
        """获取当前可工作的团队成员"""
        members = project_member_service.list_project_members(session, project_id)

        available = []
        for m in members:
            emp = m["employee"]
            if not emp or emp.type == "human":
                continue

            # 检查是否正在工作中
            busy_todo = session.query(Todo).filter(
                Todo.assignee_id == emp.id,
                Todo.status == "in_progress"
            ).first()

            if not busy_todo:
                available.append({
                    "employee": emp,
                    "role": m.get("role", "member")
                })

        return available

    def _check_existing_decomposition(
        self, session: Session, project_id: str, requirement: str
    ) -> List[Todo]:
        """检查是否已经有类似的拆解"""
        # 计算需求的关键词
        keywords = self._extract_keywords(requirement)

        if not keywords:
            return []

        # 查找包含关键词的任务
        matching_tasks = []
        for keyword in keywords:
            tasks = session.query(Todo).filter(
                Todo.project_id == project_id,
                Todo.title.contains(keyword)
            ).all()
            matching_tasks.extend(tasks)

        # 去重
        seen = set()
        unique_tasks = []
        for task in matching_tasks:
            if task.id not in seen:
                seen.add(task.id)
                unique_tasks.append(task)

        return unique_tasks

    def _extract_keywords(self, requirement: str) -> List[str]:
        """从需求中提取关键词"""
        # 简单实现：提取中文词汇
        import re
        # 匹配2-4个字的中文词汇
        words = re.findall(r'[\u4e00-\u9fa5]{2,4}', requirement)
        return list(set(words))[:5]  # 最多5个关键词

    async def _leader_decompose(
        self,
        session: Session,
        project_id: str,
        requirement: str,
        methodology: Dict,
        existing_tasks: List[Todo]
    ) -> Dict:
        """
        调用Leader进行WBS拆解

        Returns:
            拆解结果
        """

        project = session.query(Project).filter_by(id=project_id).first()
        current_phase = project.current_phase or "planning"

        # 获取当前阶段配置
        phase_config = self._get_phase_config(methodology, current_phase)

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
        if not leader:
            return {
                "needs_clarification": True,
                "questions": ["项目中没有配置Leader成员，无法进行拆解"],
                "error": "no_leader"
            }

        # 异步调用Leader
        result = await agent_service.dispatch_task_async(
            session=session,
            employee_id=leader.id,
            task=prompt,
            project_id=project_id
        )

        # 解析结果
        return self._parse_decomposition_result(result)

    def _get_phase_config(
        self, methodology: Dict, phase_id: str
    ) -> Optional[Dict]:
        """获取阶段配置"""
        for phase in methodology["phases"]:
            if phase["id"] == phase_id:
                return phase
        return None

    def _get_project_leader(
        self, session: Session, project_id: str
    ) -> Optional[Employee]:
        """获取项目的Leader成员"""
        members = session.query(ProjectMember).filter(
            ProjectMember.project_id == project_id,
            ProjectMember.role == "leader"
        ).all()

        if not members:
            return None

        # 返回第一个leader
        member = members[0]
        return session.query(Employee).filter_by(id=member.employee_id).first()

    def _build_decomposition_prompt(
        self, project, methodology, phase_config, requirement, existing_tasks
    ) -> str:
        """构建WBS拆解prompt"""

        existing_summary = self._summarize_existing_tasks(existing_tasks)

        # 获取WBS规则
        wbs_rules = methodology.get("wbs_rules", {})
        pattern = wbs_rules.get("decomposition_pattern", "任务 → 子任务")

        return f"""你是项目 "{project.name}" 的负责人，正在进行WBS（工作分解结构）拆解。

【项目信息】
项目目标: {project.description or "未提供"}
项目类型: {methodology['project_type']}
方法论: {methodology['name']}
当前阶段: {phase_config.get('name', current_phase) if phase_config else '规划阶段'}

【阶段指导】
阶段目标: {phase_config.get('objective', '完成项目规划') if phase_config else ''}

阶段最佳实践:
{self._format_best_practices(phase_config.get('best_practices', []) if phase_config else [])}

【WBS拆解规则】
拆解模式: {pattern}
最大深度: {wbs_rules.get('max_depth', 3)}层
任务粒度: {wbs_rules.get('task_size_limit', '1-2人日')}
必须建立依赖: {'是' if wbs_rules.get('require_dependency') else '否'}

【已有任务】
{existing_summary}
注意：不要创建与已有任务重复的任务。

【待拆解需求】
{requirement}

请按照以下步骤进行WBS拆解：

1. **理解需求**：首先明确需求的交付物是什么
2. **识别分解点**：找出主要的分解维度
3. **分解任务**：按照 "{pattern}" 的模式进行分解
4. **建立依赖**：识别任务之间的前置关系
5. **检查完整性**：确保拆解覆盖需求的所有方面

输出JSON格式（必须严格按照此格式）：
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
              "title": "任务标题（简明扼要，10-20字）",
              "description": "详细描述（包括具体要做的事情）",
              "assignee_role": "需要的角色类型（frontend/backend/designer/qa/researcher等）",
              "acceptance_criteria": "验收标准（如何判断任务完成）",
              "estimated_hours": 预估工时（数字）,
              "depends_on": ["依赖的任务ID，如wp1或t1"],
              "priority": "high/medium/low",
              "tags": ["标签1", "标签2"]
            }}
          ]
        }}
      ]
    }}
  ],
  "assumptions": ["拆解时做的假设（如技术选型、资源限制等）"],
  "risks": ["识别的风险（如时间紧张、技术难度等）"],
  "notes": "其他需要说明的内容",
  "needs_clarification": false,
  "questions": ["如果需求不明确，列出需要向人类确认的问题"]
}}

重要：
1. 如果需求不够清晰无法进行有效拆解，请设置 needs_clarification=true 并在 questions 中列出具体问题
2. 不要强行拆解不明确的需求
3. 任务标题要具体，避免过于宽泛（如"开发功能"、"实现需求"等）
4. 每个任务应该是可分配、可执行、可验收的
5. 注意：只输出JSON，不要有其他内容

请输出JSON：
"""

    def _summarize_existing_tasks(self, tasks: List[Todo]) -> str:
        """总结已有任务"""
        if not tasks:
            return "  （无）"

        summary = []
        for task in tasks[:10]:  # 最多显示10个
            status_emoji = {
                "pending": "⏳",
                "in_progress": "🚀",
                "completed": "✅"
            }.get(task.status, "❓")

            summary.append(f"  {status_emoji} {task.title[:40]}")

        if len(tasks) > 10:
            summary.append(f"  ... 还有 {len(tasks) - 10} 个任务")

        return "\n".join(summary)

    def _format_best_practices(self, practices: List) -> str:
        """格式化最佳实践"""
        if not practices:
            return "  （无）"

        lines = []
        for i, practice in enumerate(practices, 1):
            lines.append(f"  {i}. {practice}")

        return "\n".join(lines)

    def _parse_decomposition_result(self, result: dict) -> dict:
        """解析Leader的拆解结果"""
        if not result.get("success"):
            return {
                "needs_clarification": True,
                "questions": [f"Leader调用失败: {result.get('error', 'unknown')}"],
                "error": result.get("error")
            }

        output = result.get("output", "")

        # 尝试从输出中提取JSON
        try:
            # 查找JSON代码块
            if "```json" in output:
                start = output.find("```json") + 7
                end = output.find("```", start)
                json_str = output[start:end].strip()
            elif "```" in output:
                start = output.find("```") + 3
                end = output.find("```", start)
                json_str = output[start:end].strip()
            else:
                # 尝试直接解析
                json_str = output.strip()

            decomposition = json.loads(json_str)

            # 检查是否需要澄清
            if decomposition.get("needs_clarification"):
                return {
                    "needs_clarification": True,
                    "questions": decomposition.get("questions", []),
                    "deliverables": decomposition.get("deliverables", [])
                }

            return {
                "needs_clarification": False,
                "deliverables": decomposition.get("deliverables", []),
                "assumptions": decomposition.get("assumptions", []),
                "risks": decomposition.get("risks", []),
                "notes": decomposition.get("notes", "")
            }

        except json.JSONDecodeError:
            # JSON解析失败
            return {
                "needs_clarification": True,
                "questions": [
                    "无法解析Leader的输出，输出格式不正确",
                    f"Leader输出预览: {output[:200]}..."
                ],
                "error": "json_parse_error",
                "raw_output": output
            }

    async def _create_tasks_from_decomposition(
        self,
        session: Session,
        project_id: str,
        decomposition: dict,
        methodology: dict
    ) -> List[Todo]:
        """从拆解结果创建任务"""
        import uuid

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
                        depends_on=json.dumps(depends_on, ensure_ascii=False)
                    )

                    # 保存逻辑ID映射
                    task_id_map[task_data["id"]] = todo.id

                    # 保存额外信息到knowledge
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
                        tags=json.dumps(["task_detail", task_data.get("assignee_role", "general")], ensure_ascii=False)
                    )
                    session.add(knowledge)

                    tasks_created.append(todo)

        session.commit()
        return tasks_created

    async def _dispatch_ready_tasks(
        self,
        session: Session,
        project_id: str,
        tasks: List[Todo],
        available_members: List[Dict]
    ) -> int:
        """立即分配可执行的任务（无依赖或依赖已满足）"""

        from nova_platform.services.automation_service import build_dependency_graph, get_next_runnable_tasks

        dispatched = 0

        # 构建依赖图
        graph = build_dependency_graph(session, project_id)
        ready_task_ids = graph.get_ready_tasks()

        # 找出可执行的任务
        ready_tasks = [t for t in tasks if t.id in ready_task_ids and t.status == "pending"]

        for task in ready_tasks:
            # 从任务详情中获取需要的角色
            knowledge = session.query(Knowledge).filter(
                Knowledge.project_id == project_id,
                Knowledge.title.contains(task.title)
            ).first()

            required_role = None
            if knowledge:
                try:
                    content = json.loads(knowledge.content)
                    required_role = content.get("assignee_role")
                except:
                    pass

            # 找到合适的成员
            for member in available_members:
                emp = member["employee"]

                # 检查角色匹配
                if required_role:
                    emp_skills = json.loads(emp.skills or "[]")
                    if required_role not in emp_skills and required_role not in str(emp.role).lower():
                        continue

                # 分配任务
                task.assignee_id = emp.id
                task.status = "in_progress"
                session.commit()

                # 异步执行
                task_desc = f"[项目: {project_id}] {task.title}"
                agent_result = agent_service.dispatch_task_async(
                    session, emp.id, task_desc, project_id
                )

                # 保存task_id
                if agent_result.get("success") and agent_result.get("task_id"):
                    task.agent_task_id = agent_result["task_id"]
                    session.commit()

                dispatched += 1
                break

        return dispatched

    async def _request_clarification(
        self,
        session: Session,
        project_id: str,
        requirement: str,
        decomposition: dict
    ) -> HumanInteraction:
        """创建人类澄清请求"""

        questions = decomposition.get("questions", [])
        if not questions:
            questions = ["需求描述不够清晰，请提供更多细节"]

        # 创建交互记录
        interaction = HumanInteraction(
            project_id=project_id,
            interaction_type="clarification_needed",
            source="leader",
            context=json.dumps({
                "requirement": requirement,
                "decomposition_attempt": decomposition
            }, ensure_ascii=False),
            questions=json.dumps(questions, ensure_ascii=False),
            leader_recommendation=f"在拆解需求 '{requirement[:50]}...' 时遇到问题，需要澄清",
            depends_on_interactions=json.dumps([])
        )

        session.add(interaction)

        # 更新项目状态
        project = session.query(Project).filter_by(id=project_id).first()
        if project:
            project.status = "awaiting_human"
            session.commit()

        session.commit()
        return interaction

    def handle_human_response(
        self,
        session: Session,
        interaction_id: str,
        response: str
    ) -> dict:
        """
        处理人类响应

        当人类回答了问题后，继续拆解流程
        """

        interaction = session.query(HumanInteraction).filter_by(
            id=interaction_id
        ).first()

        if not interaction or interaction.status != "pending":
            return {"success": False, "error": "交互不存在或已关闭"}

        # 记录响应
        interaction.human_response = response
        interaction.status = "answered"
        interaction.response_at = datetime.utcnow()
        session.commit()

        # 获取项目
        project_id = interaction.project_id
        project = session.query(Project).filter_by(id=project_id).first()

        # 检查是否所有待处理交互都已完成
        pending_interactions = session.query(HumanInteraction).filter(
            HumanInteraction.project_id == project_id,
            HumanInteraction.status == "pending"
        ).count()

        if pending_interactions == 0:
            # 所有交互已完成，恢复项目
            project.status = "active"
            session.commit()

            # TODO: 触发Leader继续拆解
            # 这里可以发送一个事件或调用继续拆解的逻辑

        return {
            "success": True,
            "interaction_id": interaction_id,
            "project_resumed": pending_interactions == 0
        }


# 全局服务实例
wbs_service = WBSService()
