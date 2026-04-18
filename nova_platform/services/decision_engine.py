"""
多层决策引擎

实现三层决策架构：
- 第1层：系统规则（快速、确定）
- 第2层：Leader决策（项目级，异步）
- 第3层：人类决策（重大决策）
"""

import json
import hashlib
from datetime import datetime, timedelta
from typing import Optional, List, Dict
from sqlalchemy.orm import Session

from nova_platform.models import (
    Project, Todo, Employee, ProjectMember,
    ProjectMethodology, HumanInteraction
)
from nova_platform.services import (
    todo_service,
    agent_service,
    project_member_service,
    human_interaction_service,
    leader_lock_service
)
from nova_platform.services import task_dependency_service


class DecisionEngine:
    """多层决策引擎"""

    def __init__(self):
        self.system_confidence_threshold = 0.8  # 系统决策的信心阈值

    async def make_decision(
        self,
        session: Session,
        project_id: str,
        observation: dict
    ) -> dict:
        """
        多层决策流程

        Args:
            session: 数据库会话
            project_id: 项目ID
            observation: 观察数据

        Returns:
            决策结果
        """

        # 第1层：系统规则（快速、确定）
        system_decision = self._system_rule_decision(session, project_id, observation)

        if system_decision.get("confident"):
            # 系统有信心直接决策
            return {
                "layer": "system",
                "decision": system_decision,
                "reasoning": system_decision.get("reason", "")
            }

        # 第2层：Leader决策（项目级，异步）
        try:
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
                "decision": leader_decision,
                "reasoning": leader_decision.get("reasoning", "")
            }

        except Exception as e:
            # Leader决策失败，回退到系统规则
            fallback_decision = self._fallback_decision(observation, str(e))
            return {
                "layer": "system_fallback",
                "decision": fallback_decision,
                "reasoning": f"Leader决策失败，使用系统规则: {e}"
            }

    def _system_rule_decision(
        self, session: Session, project_id: str, observation: dict
    ) -> dict:
        """
        第1层：系统规则决策

        快速、确定的规则，无需Leader介入
        """

        project = session.query(Project).filter_by(id=project_id).first()
        if not project:
            return {"confident": False, "error": "项目不存在"}

        # 获取方法论配置
        methodology = self._get_methodology(session, project)
        if not methodology:
            methodology = {"decision_rules": {}}

        decision_rules = methodology.get("decision_rules", {})
        config = json.loads(project.project_config or "{}")

        stats = observation.get("status_summary", {})
        blockers = observation.get("blockers", [])
        runnable_tasks = observation.get("runnable_tasks", [])
        idle_agents = observation.get("idle_agents", [])

        # 规则1: 任务阻塞自动重置（30分钟无响应）
        if blockers:
            return {
                "confident": True,
                "action": "reset_blocked_tasks",
                "task_ids": [b["todo"].id for b in blockers],
                "reason": f"{len(blockers)}个任务阻塞超时，自动重置"
            }

        # 规则2: 唯一可执行任务自动分发
        if config.get("auto_dispatch", decision_rules.get("auto_dispatch", True)):
            if len(runnable_tasks) == 1 and idle_agents:
                return {
                    "confident": True,
                    "action": "auto_dispatch_single",
                    "task_id": runnable_tasks[0].id,
                    "assignee_id": idle_agents[0]["employee"].id,
                    "reason": "唯一可执行任务，自动分发"
                }

        # 规则3: 所有任务完成
        if stats.get("completed", 0) > 0 and stats.get("pending", 0) == 0 and stats.get("in_progress", 0) == 0:
            return {
                "confident": True,
                "action": "complete_project",
                "reason": "所有任务已完成"
            }

        # 规则4: 任务完成且有待处理，检查是否需要进入下一阶段
        if stats.get("completed", 0) > 0 and stats.get("pending", 0) == 0:
            # 检查是否可以进入下一阶段
            next_phase = self._check_phase_transition(session, project, observation)
            if next_phase:
                return {
                    "confident": True,
                    "action": "transition_phase",
                    "current_phase": project.current_phase,
                    "next_phase": next_phase,
                    "reason": f"当前阶段完成，进入{next_phase['name']}"
                }

        # 不确定情况，交给Leader
        return {
            "confident": False,
            "hints": {
                "runnable_count": len(runnable_tasks),
                "idle_agent_count": len(idle_agents),
                "blocker_count": len(blockers),
                "pending_count": stats.get("pending", 0),
                "completed_count": stats.get("completed", 0)
            }
        }

    async def _leader_decision(
        self,
        session: Session,
        project_id: str,
        observation: dict,
        system_hints: dict
    ) -> dict:
        """
        第2层：Leader决策（异步，防重）
        """

        # 获取防重锁
        lock = leader_lock_service.acquire_decision_lock(
            session, project_id, observation, system_hints
        )

        if not lock:
            # 有相同的决策在进行中，等待结果
            # TODO: 可以实现等待逻辑
            return {
                "needs_human": False,
                "action": "waiting_for_duplicate_decision",
                "reason": "相同决策正在处理中"
            }

        try:
            project = session.query(Project).filter_by(id=project_id).first()
            methodology = self._get_methodology(session, project)
            current_phase = project.current_phase or "planning"
            phase_config = self._get_phase_config(methodology, current_phase)

            # 构建Leader决策prompt
            prompt = self._build_leader_decision_prompt(
                project=project,
                methodology=methodology,
                phase_config=phase_config,
                observation=observation,
                system_hints=system_hints,
                lock=lock
            )

            # 获取Leader
            leader = self._get_project_leader(session, project_id)
            if not leader:
                return {
                    "needs_human": True,
                "reason": "项目中没有配置Leader成员"
                }

            # 异步调用Leader
            result = await agent_service.dispatch_task_async(
                session=session,
                employee_id=leader.id,
                task=prompt,
                project_id=project_id
            )

            # 解析Leader决策
            decision = self._parse_leader_decision(result)

            # 释放锁
            leader_lock_service.release_lock(session, lock, decision)

            return decision

        except Exception as e:
            # 失败，标记锁为失败
            leader_lock_service.fail_lock(session, lock, str(e))
            raise

    def _build_leader_decision_prompt(
        self, project, methodology, phase_config, observation, system_hints, lock
    ) -> str:
        """构建Leader决策prompt"""

        stats = observation.get("status_summary", {})
        blockers = observation.get("blockers", [])
        runnable_tasks = observation.get("runnable_tasks", [])
        members = observation.get("members", [])
        idle_agents = [m for m in members if not m.get("busy")]

        # 获取当前阶段的决策规则
        decision_rules = methodology.get("decision_rules", {})
        leader_decide_on = decision_rules.get("leader_decide_on", [])

        # 构建任务列表
        tasks_list = self._format_tasks_for_leader(observation)

        # 构建团队状态
        team_status = self._format_team_for_leader(observation)

        prompt = f"""你是项目 "{project.name}" 的负责人（Leader），需要做出项目决策。

【项目信息】
项目目标: {project.description or "未提供"}
项目类型: {methodology['project_type']}
方法论: {methodology['name']}
当前阶段: {phase_config.get('name', current_phase) if phase_config else '规划阶段'}
阶段目标: {phase_config.get('objective', '') if phase_config else ''}

【当前状态】
总任务: {stats.get('total', 0)} | 待处理: {stats.get('pending', 0)} | 进行中: {stats.get('in_progress', 0)} | 已完成: {stats.get('completed', 0)}

【系统提示】
{self._format_system_hints(system_hints)}

【决策权限】
根据项目方法论配置，你需要就以下类型的问题做出决策：
{self._format_decision_types(leader_decide_on)}

【当前可执行任务】
{tasks_list}

【团队状态】
{team_status}

【任务依赖图】
{self._format_dependency_graph(observation.get("dependency_graph", {}))}

【阶段最佳实践】
{self._format_best_practices(phase_config.get('best_practices', []) if phase_config else [])}

请分析当前情况，给出决策：

1. 如果情况清晰且在你的决策权限内，直接给出行动方案
2. 如果情况复杂或超出权限，请求人类介入

决策JSON格式：
{{
  "action": "具体行动类型",
  "params": {{"task_id": "...", "assignee_id": "...", ...}},
  "reasoning": "你的决策逻辑（为什么这样做）",
  "risks": ["识别的潜在风险"],
  "needs_human": false,
  "human_question": "如果需要人类，具体说明问题",
  "suggested_answer": "你的建议（如果有）"
}}

可用的行动类型：
- dispatch_task: 分配指定任务给指定成员
- prioritize_tasks: 调整任务优先级（params: {{"task_id": "xxx", "new_priority": "high"}}）
- add_dependency: 添加任务依赖（params: {{"task_id": "xxx", "depends_on": ["yyy"]}}）
- split_task: 拆分任务
- request_clarification: 向人类请求澄清
- move_to_next_phase: 进入下一阶段
- continue_current_phase: 继续当前阶段工作
- escalate_to_human: 升级到人类决策
- no_action: 无需行动，团队正常工作

只输出JSON，不要其他内容。
"""
        return prompt

    def _format_system_hints(self, hints: dict) -> str:
        """格式化系统提示"""
        if not hints:
            return "  （无系统提示）"

        lines = []
        if "runnable_count" in hints:
            lines.append(f"  - 可执行任务数: {hints['runnable_count']}")
        if "idle_agent_count" in hints:
            lines.append(f"  - 空闲成员数: {hints['idle_agent_count']}")
        if "blocker_count" in hints:
            lines.append(f"  - 阻塞任务数: {hints['blocker_count']}")
        if "pending_count" in hints:
            lines.append(f"  - 待处理任务数: {hints['pending_count']}")

        return "\n".join(lines) if lines else "  （无系统提示）"

    def _format_decision_types(self, decide_on: list) -> str:
        """格式化决策类型"""
        if not decide_on:
            return "  （无特定决策权限）"

        type_names = {
            "prioritization": "任务优先级调整",
            "phase_transition": "阶段转换决策",
            "blocker_escalation": "阻塞问题升级",
            "scope_adjustment": "项目范围调整",
            "resource_allocation": "资源分配决策",
            "content_approval": "内容审核（内容运营）"
        }

        lines = []
        for dt in decide_on:
            name = type_names.get(dt, dt)
            lines.append(f"  - {name}")

        return "\n".join(lines)

    def _format_tasks_for_leader(self, observation: dict) -> str:
        """格式化任务列表给Leader"""
        todos = observation.get("todos", [])
        if not todos:
            return "  （无任务）"

        lines = []
        for todo in todos[:10]:  # 最多显示10个
            status_emoji = {"pending": "⏳", "in_progress": "🚀", "completed": "✅"}.get(todo.status, "❓")
            assignee = todo.get("assignee", "未分配")
            lines.append(f"  {status_emoji} {todo['title'][:40]} ({assignee})")

        if len(todos) > 10:
            lines.append(f"  ... 还有 {len(todos) - 10} 个任务")

        return "\n".join(lines)

    def _format_team_for_leader(self, observation: dict) -> str:
        """格式化团队状态给Leader"""
        members = observation.get("members", [])
        if not members:
            return "  （无成员）"

        lines = []
        for m in members[:10]:
            busy_status = "🚀 工作中" if m.get("busy") else "💤 空闲"
            role = m.get("role", "member")
            name = m.get("employee", {}).get("name", "未知")
            lines.append(f"  {busy_status} {name} ({role})")

        if len(members) > 10:
            lines.append(f"  ... 还有 {len(members) - 10} 个成员")

        return "\n".join(lines)

    def _format_dependency_graph(self, graph: dict) -> str:
        """格式化依赖图"""
        if not graph or not graph.get("nodes"):
            return "  （无依赖关系）"

        # 简化显示：只显示阻塞的任务
        lines = []
        for task_id, node in graph.get("nodes", {}).items():
            if node["status"] == "pending":
                deps = node.get("depends_on", [])
                if deps:
                    lines.append(f"  ⏳ {node['title'][:30]} 等待: {', '.join(deps)}")

        if lines:
            return "\n".join(lines)

        return "  （无阻塞的待处理任务）"

    def _format_best_practices(self, practices: list) -> str:
        """格式化最佳实践"""
        if not practices:
            return "  （无最佳实践）"

        lines = []
        for i, practice in enumerate(practices[:5], 1):
            lines.append(f"  {i}. {practice}")

        if len(practices) > 5:
            lines.append(f"  ... 还有 {len(practices) - 5} 条实践")

        return "\n".join(lines)

    def _parse_leader_decision(self, result: dict) -> dict:
        """解析Leader的决策结果"""
        if not result.get("success"):
            return {
                "action": "no_action",
                "reasoning": f"Leader调用失败: {result.get('error', 'unknown')}",
                "needs_human": False,
                "risks": ["Leader调用失败"]
            }

        output = result.get("output", "")

        # 尝试解析JSON
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
                json_str = output.strip()

            decision = json.loads(json_str)
            return decision

        except json.JSONDecodeError:
            # JSON解析失败，尝试解析文本
            return self._parse_text_decision(output)

    def _parse_text_decision(self, text: str) -> dict:
        """解析文本格式的决策"""
        text_lower = text.lower()

        # 简单的文本决策解析
        action_map = {
            "dispatch": "dispatch_task",
            "分配": "dispatch_task",
            "prioritize": "prioritize_tasks",
            "优先级": "prioritize_tasks",
            "阻塞": "handle_blockers",
            "升级": "escalate_to_human",
            "下一阶段": "move_to_next_phase",
            "继续": "continue_current_phase",
            "澄清": "request_clarification",
            "无需": "no_action"
        }

        for keyword, action in action_map.items():
            if keyword in text_lower:
                return {
                    "action": action,
                    "reasoning": f"Leader回复关键词: {keyword}",
                    "needs_human": action == "escalate_to_human"
                }

        # 默认：无行动
        return {
            "action": "no_action",
            "reasoning": "无法解析Leader的决策，默认为无行动",
            "needs_human": False,
            "raw_output": text[:200]
        }

    async def _escalate_to_human(
        self,
        session: Session,
        project_id: str,
        observation: dict,
        leader_decision: dict
    ) -> dict:
        """
        升级到人类决策

        Args:
            session: 数据库会话
            project_id: 项目ID
            observation: 观察数据
            leader_decision: Leader的决策

        Returns:
            第3层决策结果
        """

        # 创建人类交互请求
        questions = []

        # 从Leader决策中提取问题
        if leader_decision.get("human_question"):
            questions.append(leader_decision["human_question"])
        else:
            # 生成默认问题
            questions.append("Leader遇到了需要决策的问题，请查看具体情况并给出指示")

        # 添加上下文信息
        context = {
            "observation": observation,
            "leader_recommendation": leader_decision.get("suggested_answer", ""),
            "decision_type": leader_decision.get("action", "unknown")
        }

        interaction = await human_interaction_service.create_interaction(
            session=session,
            project_id=project_id,
            interaction_type="decision_needed",
            questions=questions,
            context=context,
            source="leader",
            leader_recommendation=leader_decision.get("reasoning", "")
        )

        return {
            "layer": "human",
            "decision": {
                "action": "awaiting_human_response",
                "interaction_id": interaction.id,
                "reason": "需要人类决策",
                "interaction": interaction
            }
        }

    def _get_methodology(self, session: Session, project: Project) -> Optional[dict]:
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

    def _get_phase_config(
        self, methodology: dict, phase_id: str
    ) -> Optional[dict]:
        """获取阶段配置"""
        for phase in methodology.get("phases", []):
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

        return session.query(Employee).filter_by(id=members[0].employee_id).first()

    def _check_phase_transition(
        self,
        session: Session,
        project: Project,
        observation: dict
    ) -> Optional[dict]:
        """检查是否可以进入下一阶段"""
        methodology = self._get_methodology(session, project)
        if not methodology:
            return None

        current_phase = project.current_phase or "planning"
        phases = methodology.get("phases", [])

        # 找到当前阶段
        current_index = -1
        for i, phase in enumerate(phases):
            if phase["id"] == current_phase:
                current_index = i
                break

        if current_index >= 0 and current_index < len(phases) - 1:
            next_phase = phases[current_index + 1]

            # 检查退出条件
            exit_condition = next_phase.get("exit_condition", "")
            if exit_condition:
                # 简化检查：如果没有待处理和进行中的任务，认为可以进入下一阶段
                stats = observation.get("status_summary", {})
                if stats.get("pending", 0) == 0 and stats.get("in_progress", 0) == 0:
                    return {
                        "id": next_phase["id"],
                        "name": next_phase["name"],
                        "objective": next_phase.get("objective", "")
                    }

        return None

    def _fallback_decision(self, observation: dict, error: str) -> dict:
        """回退决策（Leader失败时使用）"""
        stats = observation.get("status_summary", {})

        # 简单规则：如果有可执行任务，尝试自动分发
        runnable_tasks = observation.get("runnable_tasks", [])

        if runnable_tasks:
            return {
                "action": "auto_dispatch_best_effort",
                "task_id": runnable_tasks[0].id,
                "reasoning": f"Leader决策失败，使用备用规则：分发第一个可执行任务。错误: {error[:50]}"
            }

        return {
            "action": "no_action",
            "reasoning": f"Leader决策失败，无备用规则。错误: {error[:50]}"
        }


# 全局决策引擎实例
decision_engine = DecisionEngine()
