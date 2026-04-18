"""
人类交互服务

处理Leader与人类之间的沟通：
- 创建交互请求
- 接收人类响应
- 检查依赖关系
- 触发Leader继续处理
"""

import json
from datetime import datetime, timedelta
from typing import Optional, List
from sqlalchemy.orm import Session

from nova_platform.models import (
    Project, HumanInteraction, LeaderInvocationLock,
    Employee, ProjectMember
)


class HumanInteractionService:
    """人类交互服务"""

    async def create_interaction(
        self,
        session: Session,
        project_id: str,
        interaction_type: str,
        questions: List[str],
        context: dict,
        source: str = "leader",
        leader_recommendation: str = "",
        depends_on: List[str] = None
    ) -> HumanInteraction:
        """
        创建人类交互请求

        Args:
            session: 数据库会话
            project_id: 项目ID
            interaction_type: 交互类型（clarification_needed, decision_needed等）
            questions: 问题列表
            context: 上下文信息
            source: 来源（leader, system）
            leader_recommendation: Leader的建议
            depends_on: 依赖的其他交互ID列表

        Returns:
            HumanInteraction对象
        """

        # 检查依赖
        if depends_on:
            for dep_id in depends_on:
                dep = session.query(HumanInteraction).filter_by(id=dep_id).first()
                if not dep or dep.status != "answered":
                    raise ValueError(f"依赖交互未完成或不存在: {dep_id}")

        interaction = HumanInteraction(
            project_id=project_id,
            interaction_type=interaction_type,
            source=source,
            context=json.dumps(context, ensure_ascii=False),
            questions=json.dumps(questions, ensure_ascii=False),
            leader_recommendation=leader_recommendation,
            depends_on_interactions=json.dumps(depends_on or [], ensure_ascii=False),
            status="pending"
        )

        session.add(interaction)
        session.commit()
        session.refresh(interaction)

        # 更新项目状态
        project = session.query(Project).filter_by(id=project_id).first()
        if project and project.status != "awaiting_human":
            project.status = "awaiting_human"
            session.commit()

        return interaction

    async def answer_interaction(
        self,
        session: Session,
        interaction_id: str,
        response: str,
        responder: str = "web_user"
    ) -> dict:
        """
        回答人类交互

        Args:
            session: 数据库会话
            interaction_id: 交互ID
            response: 人类响应
            responder: 响应者标识

        Returns:
            处理结果
        """

        interaction = session.query(HumanInteraction).filter_by(
            id=interaction_id
        ).first()

        if not interaction:
            return {"success": False, "error": "交互不存在"}

        if interaction.status != "pending":
            return {"success": False, "error": f"交互已关闭（状态: {interaction.status}）"}

        # 记录响应
        interaction.human_response = response
        interaction.status = "answered"
        interaction.response_at = datetime.utcnow()
        session.commit()

        # 检查是否可以恢复项目
        project_id = interaction.project_id
        check_result = await self.check_and_resume(session, project_id)

        # TODO: 根据交互类型触发Leader的后续处理
        if check_result.get("action") == "resumed":
            leader_action = await self._trigger_leader_resume(
                session, interaction
            )
            interaction.leader_action_taken = json.dumps(leader_action, ensure_ascii=False)
            interaction.action_taken_at = datetime.utcnow()
            session.commit()

        return {
            "success": True,
            "interaction_id": interaction_id,
            "project_can_resume": check_result.get("can_resume", False),
            "project_action": check_result.get("action")
        }

    async def check_and_resume(
        self,
        session: Session,
        project_id: str
    ) -> dict:
        """
        检查人类交互是否全部完成，如果完成则恢复项目

        Args:
            session: 数据库会话
            project_id: 项目ID

        Returns:
            检查结果
        """

        # 统计待处理的交互
        pending_count = session.query(HumanInteraction).filter(
            HumanInteraction.project_id == project_id,
            HumanInteraction.status == "pending"
        ).count()

        if pending_count > 0:
            # 还有待处理的交互
            return {
                "can_resume": False,
                "pending_count": pending_count,
                "action": "waiting_for_more_responses"
            }

        # 所有交互已完成，恢复项目
        project = session.query(Project).filter_by(id=project_id).first()
        if project and project.status == "awaiting_human":
            project.status = "active"
            session.commit()

            return {
                "can_resume": True,
                "action": "resumed"
            }

        return {
            "can_resume": True,
            "action": "already_active"
        }

    async def _trigger_leader_resume(
        self,
        session: Session,
        interaction: HumanInteraction
    ) -> dict:
        """
        触发Leader处理人类响应

        Args:
            session: 数据库会话
            interaction: 交互对象

        Returns:
            Leader的处理动作
        """

        project_id = interaction.project_id

        # 根据交互类型决定后续动作
        if interaction.interaction_type == "clarification_needed":
            # 需求澄清后，重新尝试拆解
            context = json.loads(interaction.context or "{}")
            requirement = context.get("requirement", "")

            if requirement:
                # 调用WBS服务继续拆解
                from nova_platform.services.wbs_service import wbs_service

                result = await wbs_service.decompose_incremental(
                    session, project_id, [requirement]
                )

                return {
                    "action": "continued_decomposition",
                    "result": result
                }

        elif interaction.interaction_type == "decision_needed":
            # 决策后，执行决策
            # TODO: 实现决策执行逻辑
            pass

        return {
            "action": "not_implemented",
            "message": f"交互类型 {interaction.interaction_type} 的后续处理尚未实现"
        }

    def get_pending_interactions(
        self,
        session: Session,
        project_id: str = None
    ) -> List[HumanInteraction]:
        """
        获取待处理的交互

        Args:
            session: 数据库会话
            project_id: 项目ID（可选，为None则获取所有）

        Returns:
            待处理交互列表
        """

        query = session.query(HumanInteraction).filter(
            HumanInteraction.status == "pending"
        )

        if project_id:
            query = query.filter(HumanInteraction.project_id == project_id)

        return query.order_by(HumanInteraction.created_at).all()

    def get_interaction(
        self,
        session: Session,
        interaction_id: str
    ) -> Optional[HumanInteraction]:
        """获取单个交互"""
        return session.query(HumanInteraction).filter_by(id=interaction_id).first()

    def skip_interaction(
        self,
        session: Session,
        interaction_id: str,
        reason: str
    ) -> bool:
        """
        跳过交互（不等待响应，直接继续）

        Args:
            session: 数据库会话
            interaction_id: 交互ID
            reason: 跳过原因

        Returns:
            是否成功
        """

        interaction = session.query(HumanInteraction).filter_by(
            id=interaction_id
        ).first()

        if not interaction or interaction.status != "pending":
            return False

        interaction.status = "skipped"
        interaction.human_response = f"已跳过: {reason}"
        interaction.response_at = datetime.utcnow()
        session.commit()

        # 检查是否可以恢复项目
        import asyncio
        asyncio.create_task(self.check_and_resume(session, interaction.project_id))

        return True


class HumanInteractionMonitor:
    """人类交互监控服务 - 后台定时运行"""

    def __init__(self, check_interval: int = 30):
        """
        Args:
            check_interval: 检查间隔（秒）
        """
        self.check_interval = check_interval
        self.running = False

    async def monitor_all_projects(self, session: Session) -> dict:
        """
        监控所有等待人类响应的项目

        Args:
            session: 数据库会话

        Returns:
            监控结果
        """

        # 找出所有等待人类响应的项目
        awaiting_projects = session.query(Project).filter(
            Project.status == "awaiting_human"
        ).all()

        results = {
            "awaiting_count": len(awaiting_projects),
            "projects": [],
            "resumed": []
        }

        for project in awaiting_projects:
            project_result = await self._monitor_project(session, project.id)
            results["projects"].append(project_result)

            if project_result.get("resumed"):
                results["resumed"].append(project.id)

        return results

    async def _monitor_project(
        self,
        session: Session,
        project_id: str
    ) -> dict:
        """
        监控单个项目

        Args:
            session: 数据库会话
            project_id: 项目ID

        Returns:
            监控结果
        """

        service = HumanInteractionService()
        return await service.check_and_resume(session, project_id)

    def start_monitoring(self):
        """启动监控（在后台运行）"""
        import asyncio
        import threading

        def run_monitor():
            asyncio.run(self._monitor_loop())

        self.running = True
        thread = threading.Thread(target=run_monitor, daemon=True)
        thread.start()

    def stop_monitoring(self):
        """停止监控"""
        self.running = False

    async def _monitor_loop(self):
        """监控循环"""
        from nova_platform.database import get_db_session

        while self.running:
            try:
                with get_db_session() as session:
                    await self.monitor_all_projects(session)
            except Exception as e:
                print(f"监控出错: {e}")

            # 等待下一次检查
            import asyncio
            await asyncio.sleep(self.check_interval)


# 全局服务实例
human_interaction_service = HumanInteractionService()
human_interaction_monitor = HumanInteractionMonitor()
