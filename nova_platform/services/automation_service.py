"""
Automation Service - 项目协作的迭代循环

核心设计：
- Cron 高频触发（每分钟或更快）
- 快速推动：程序直接处理分发任务、解除阻塞
- 复杂决策：调用多层决策引擎（系统规则 → Leader决策 → 人类决策）

流程：
    Cron 触发 run_iteration_cycle()
        ↓
    [快速阶段] 程序判断
        - 有阻塞？→ 解除
        - 有可运行任务？→ 立即分发
        ↓
    [决策阶段] 多层决策引擎
        - 第1层：系统规则（快速、确定）
        - 第2层：Leader决策（项目级、异步、防重）
        - 第3层：人类决策（重大决策升级）
        ↓
    [执行阶段] 执行决策并更新状态
        - 分发任务
        - 转换阶段
        - 记录人类交互
"""

import asyncio
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import Optional, List, Dict
import threading

from sqlalchemy.orm import Session

from nova_platform.models import Project, Todo, Employee, ProjectMember, HumanInteraction, ProjectMethodology
from nova_platform.services import (
    todo_service, employee_service, project_member_service, project_log_service,
    decision_engine, wbs_service, human_interaction_service, leader_lock_service,
    task_dependency_service
)

# 全局线程池，用于并行分发任务
_executor = ThreadPoolExecutor(max_workers=10)


# ============================================================================
# 任务依赖图
# ============================================================================

# ============================================================================
# Leader 决策
# ============================================================================

def _call_leader(session: Session, project_id: str, context: dict) -> dict:
    """
    调用项目成员中的 leader 角色 agent 进行决策

    Args:
        session: 数据库会话
        project_id: 项目ID
        context: 决策上下文

    Returns:
        {"decisions": [...], "used_leader": bool}
    """
    # 获取项目的 leader 成员
    leader_employees = project_member_service.get_project_members_by_role(
        session, project_id, "leader"
    )

    if not leader_employees:
        return {"decisions": [], "used_leader": False, "reason": "No leader in project"}

    # 使用第一个 leader（项目应该只有一个 leader）
    leader = leader_employees[0]

    # 如果 leader 是人类，无法调用
    if leader.type == "human":
        return {"decisions": [], "used_leader": False, "reason": "Leader is human"}

    # 构建 prompt
    status = context.get("status_summary", {})
    blockers_count = context.get("blockers_count", 0)
    project_name = context.get("project_name", "Unknown")

    prompt = f"""你是项目 "{project_name}" 的负责人。

项目当前状态：
- 总任务数: {status.get('total', 0)}
- 待处理: {status.get('pending', 0)}
- 进行中: {status.get('in_progress', 0)}
- 已完成: {status.get('completed', 0)}
- 阻塞任务: {blockers_count}

请分析项目状态，给出下一步最重要的行动建议。

从以下行动中选择一个（只返回行动名称）：
- assign_tasks: 分配待处理任务给团队成员
- check_progress: 检查进行中任务的进度
- handle_blockers: 处理阻塞的任务
- start_next_phase: 开始下一阶段工作
- no_action: 无需行动，团队正常工作

只返回行动名称（如 assign_tasks），不要其他解释。"""

    try:
        from nova_platform.services import agent_service

        # 同步调用 leader agent
        result = agent_service.dispatch_task(
            session=session,
            employee_id=leader.id,
            task=prompt,
            project_id=project_id
        )

        if result.get("success"):
            output = result.get("output", "").strip().lower()

            # 解析输出获取行动
            action_map = {
                "assign_tasks": "assign_tasks",
                "assign": "assign_tasks",
                "check_progress": "check_progress",
                "check": "check_progress",
                "handle_blockers": "handle_blockers",
                "blockers": "handle_blockers",
                "start_next_phase": "start_next_phase",
                "next": "start_next_phase",
            }

            action = None
            for key, value in action_map.items():
                if key in output:
                    action = value
                    break

            if action:
                return {
                    "decisions": [{
                        "action": action,
                        "reason": f"Leader {leader.name} decision",
                        "source": "leader_agent"
                    }],
                    "used_leader": True
                }

        return {
            "decisions": [],
            "used_leader": True,
            "reason": f"Leader output unclear: {result.get('output', '')[:50]}"
        }

    except Exception as e:
        return {
            "decisions": [],
            "used_leader": True,
            "reason": f"Leader call failed: {str(e)}"
        }


async def leader_think(session: Session, project_id: str, observation: dict) -> dict:
    """
    使用多层决策引擎进行项目决策

    决策流程：
    - 第1层：系统规则决策（快速、确定）
    - 第2层：Leader决策（项目级、异步、防重）
    - 第3层：人类决策升级（重大决策）

    Returns:
        {"success": bool, "decisions": list, "layer": str}
    """
    try:
        # 使用多层决策引擎
        decision_result = await decision_engine.decision_engine.make_decision(
            session=session,
            project_id=project_id,
            observation=observation
        )

        decision_layer = decision_result.get("layer", "unknown")
        decision_data = decision_result.get("decision", {})

        # 将决策转换为标准格式
        if decision_layer == "system" or decision_layer == "system_fallback":
            # 系统规则决策
            action = decision_data.get("action", "")
            return {
                "success": True,
                "decisions": [{
                    "action": action,
                    "params": decision_data,
                    "reason": decision_result.get("reasoning", ""),
                    "source": "system_engine"
                }],
                "layer": decision_layer
            }

        elif decision_layer == "leader":
            # Leader决策
            action = decision_data.get("action", "")
            params = decision_data.get("params", {})
            return {
                "success": True,
                "decisions": [{
                    "action": action,
                    "params": params,
                    "reason": decision_data.get("reasoning", ""),
                    "risks": decision_data.get("risks", []),
                    "source": "leader_agent"
                }],
                "layer": decision_layer
            }

        elif decision_layer == "human":
            # 需要人类决策
            return {
                "success": True,
                "decisions": [{
                    "action": "awaiting_human",
                    "params": decision_data,
                    "reason": decision_data.get("reason", "需要人类决策"),
                    "source": "human_escalation"
                }],
                "layer": decision_layer,
                "interaction": decision_data.get("interaction")
            }

        else:
            # 未知决策层，回退到规则引擎
            decisions = _rule_based_think(observation)
            for d in decisions:
                d["source"] = "rule_engine_fallback"
            return {
                "success": True,
                "decisions": decisions,
                "layer": "fallback"
            }

    except Exception as e:
        # 决策引擎失败，回退到规则引擎
        import traceback
        traceback.print_exc()

        decisions = _rule_based_think(observation)
        for d in decisions:
            d["source"] = "rule_engine_emergency"
        return {
            "success": True,
            "decisions": decisions,
            "layer": "emergency",
            "error": str(e)
        }


def _rule_based_think(observation: dict) -> list:
    """基于规则的决策引擎（回退方案）"""
    status = observation["status_summary"]
    blockers = observation.get("blockers", [])

    decisions = []

    if status["pending"] == 0 and status["in_progress"] == 0 and status["completed"] > 0:
        decisions.append({"action": "complete_project", "reason": "All tasks completed"})
        return decisions

    if blockers:
        decisions.append({
            "action": "handle_blockers",
            "blockers": blockers,
            "reason": f"Found {len(blockers)} blocked tasks"
        })

    unassigned = [t for t in observation["todos"] if t.status == "pending" and not t.assignee_id]
    if unassigned:
        decisions.append({
            "action": "assign_tasks",
            "count": len(unassigned),
            "reason": f"{len(unassigned)} tasks need assignment"
        })

    if status["in_progress"] > 0:
        decisions.append({
            "action": "check_progress",
            "count": status["in_progress"],
            "reason": f"{status['in_progress']} tasks in progress"
        })

    if status["pending"] > 0 and status["in_progress"] == 0:
        decisions.append({
            "action": "start_next_phase",
            "reason": "Workers idle, should start next task"
        })

    return decisions


# ============================================================================
# Leader 观察阶段
# ============================================================================

def leader_observe(session: Session, project_id: str) -> dict:
    """
    收集项目当前状态（为决策引擎准备完整的观察数据）

    Returns:
        包含项目、任务、成员、依赖图等完整信息的观察字典
    """
    project = session.query(Project).filter_by(id=project_id).first()
    if not project:
        return {"success": False, "error": "Project not found"}

    todos = session.query(Todo).filter_by(project_id=project_id).all()
    members = project_member_service.list_project_members(session, project_id)

    # 构建任务状态摘要
    status_summary = {
        "pending": [t for t in todos if t.status == "pending"],
        "in_progress": [t for t in todos if t.status == "in_progress"],
        "completed": [t for t in todos if t.status == "completed"],
        "blocked": [t for t in todos if t.status == "blocked"]
    }

    # 检测阻塞任务
    blockers = []
    for t in todos:
        if t.status == "in_progress" and t.assignee_id:
            assignee = session.query(Employee).filter_by(id=t.assignee_id).first()
            if assignee and assignee.type != "human":
                time_diff = datetime.utcnow() - t.updated_at
                if time_diff.total_seconds() > 1800:
                    blockers.append({"todo": t, "assignee": assignee})

    # 构建依赖图
    dependency_graph = task_dependency_service.build_dependency_graph(session, project_id)

    # 获取可执行任务
    runnable_tasks = task_dependency_service.get_next_runnable_tasks(session, project_id)

    # 构建成员状态（用于决策引擎）
    members_status = []
    idle_agents = []
    for m in members:
        emp = m.get("employee")
        if emp:
            busy_todo = session.query(Todo).filter(
                Todo.assignee_id == emp.id,
                Todo.status == "in_progress"
            ).first()
            member_info = {
                "employee": emp,
                "role": m.get("role", "member"),
                "busy": busy_todo is not None,
                "current_task": busy_todo.title if busy_todo else None
            }
            members_status.append(member_info)
            if not busy_todo and emp.type != "human":
                idle_agents.append(member_info)

    # 获取项目方法论配置
    methodology = None
    if project.methodology_id:
        meth = session.query(ProjectMethodology).filter_by(id=project.methodology_id).first()
        if meth:
            methodology = {
                "id": meth.id,
                "name": meth.name,
                "project_type": meth.project_type,
                "phases": json.loads(meth.phases) if meth.phases else [],
                "wbs_rules": json.loads(meth.wbs_rules) if meth.wbs_rules else {},
                "best_practices": json.loads(meth.best_practices) if meth.best_practices else [],
                "decision_rules": json.loads(meth.decision_rules) if meth.decision_rules else {}
            }

    return {
        "success": True,
        "project": project,
        "todos": todos,
        "members": members_status,
        "status_summary": {
            "total": len(todos),
            "pending": len(status_summary["pending"]),
            "in_progress": len(status_summary["in_progress"]),
            "completed": len(status_summary["completed"]),
            "blocked": len(blockers)
        },
        "blockers": blockers,
        "dependency_graph": dependency_graph,
        "runnable_tasks": runnable_tasks,
        "idle_agents": idle_agents,
        "methodology": methodology
    }


# ============================================================================
# Leader 计划阶段
# ============================================================================

def leader_plan(session: Session, project_id: str, decisions: list) -> list:
    """
    将决策转化为具体行动计划

    支持的决策类型：
    - complete_project: 完成项目
    - handle_blockers: 处理阻塞任务
    - dispatch_task: 分发指定任务
    - auto_dispatch_single: 自动分发唯一可执行任务
    - prioritize_tasks: 调整任务优先级
    - add_dependency: 添加任务依赖
    - split_task: 拆分任务
    - transition_phase: 进入下一阶段
    - move_to_next_phase: 进入下一阶段
    - continue_current_phase: 继续当前阶段
    - awaiting_human: 等待人类决策
    - no_action: 无需行动
    """
    plans = []

    for decision in decisions:
        action = decision["action"]
        params = decision.get("params", {})

        if action == "complete_project":
            plans.append({"stage": "act", "action": "update_project_status", "params": {"status": "completed"}})
            plans.append({"stage": "report", "action": "notify_completion", "params": {}})

        elif action == "reset_blocked_tasks":
            # 重置阻塞任务
            for task_id in params.get("task_ids", []):
                plans.append({
                    "stage": "act",
                    "action": "reset_task",
                    "params": {"todo_id": task_id, "reason": "阻塞超时，自动重置"}
                })

        elif action == "handle_blockers":
            # 处理阻塞任务（向后兼容）
            for blocker in decision.get("blockers", []):
                plans.append({
                    "stage": "act",
                    "action": "redispatch_task",
                    "params": {"todo_id": blocker["todo"].id, "assignee_id": blocker["assignee"].id}
                })

        elif action == "dispatch_task":
            # 分发指定任务
            task_id = params.get("task_id")
            assignee_id = params.get("assignee_id")
            if task_id and assignee_id:
                plans.append({
                    "stage": "act",
                    "action": "dispatch_specific_task",
                    "params": {"todo_id": task_id, "assignee_id": assignee_id}
                })

        elif action == "auto_dispatch_single":
            # 自动分发唯一可执行任务
            task_id = params.get("task_id")
            assignee_id = params.get("assignee_id")
            if task_id and assignee_id:
                plans.append({
                    "stage": "act",
                    "action": "dispatch_specific_task",
                    "params": {"todo_id": task_id, "assignee_id": assignee_id}
                })

        elif action == "prioritize_tasks":
            # 调整任务优先级
            task_id = params.get("task_id")
            new_priority = params.get("new_priority")
            if task_id and new_priority:
                plans.append({
                    "stage": "act",
                    "action": "update_priority",
                    "params": {"todo_id": task_id, "priority": new_priority}
                })

        elif action == "add_dependency":
            # 添加任务依赖
            task_id = params.get("task_id")
            depends_on = params.get("depends_on", [])
            if task_id and depends_on:
                plans.append({
                    "stage": "act",
                    "action": "add_task_dependency",
                    "params": {"todo_id": task_id, "depends_on": depends_on}
                })

        elif action == "transition_phase" or action == "move_to_next_phase":
            # 进入下一阶段
            next_phase = params.get("next_phase") or {}
            phase_id = next_phase.get("id") if isinstance(next_phase, dict) else None
            if phase_id:
                plans.append({
                    "stage": "act",
                    "action": "update_project_phase",
                    "params": {"phase_id": phase_id}
                })

        elif action == "assign_tasks":
            plans.append({"stage": "act", "action": "auto_assign_pending", "params": {"project_id": project_id}})

        elif action == "check_progress":
            plans.append({"stage": "act", "action": "query_agent_status", "params": {"project_id": project_id}})

        elif action == "start_next_phase":
            plans.append({"stage": "act", "action": "dispatch_next_task", "params": {"project_id": project_id}})

        elif action == "awaiting_human":
            # 等待人类决策，项目状态已在决策引擎中更新
            plans.append({"stage": "report", "action": "awaiting_human", "params": {}})

        elif action == "no_action":
            # 无需行动
            pass

        elif action == "continue_current_phase":
            # 继续当前阶段工作
            plans.append({"stage": "act", "action": "dispatch_next_task", "params": {"project_id": project_id}})

    return plans


# ============================================================================
# Leader 执行阶段
# ============================================================================

def leader_execute(session: Session, project_id: str, plans: list) -> dict:
    """
    执行计划

    支持的行动类型：
    - update_project_status: 更新项目状态
    - reset_task: 重置任务
    - dispatch_specific_task: 分发指定任务
    - update_priority: 更新任务优先级
    - add_task_dependency: 添加任务依赖
    - update_project_phase: 更新项目阶段
    - auto_assign_pending: 自动分配待处理任务
    - redispatch_task: 重新分发任务
    - dispatch_next_task: 分发下一个任务
    - query_agent_status: 查询Agent状态
    - awaiting_human: 等待人类响应
    """
    results = []
    sync_plans = []

    # 分类计划
    for plan in plans:
        action = plan["action"]
        if action in ("update_project_status", "notify_completion", "auto_assign_pending",
                     "reset_task", "update_priority", "add_task_dependency", "update_project_phase",
                     "awaiting_human", "query_agent_status"):
            sync_plans.append(plan)
        elif action in ("dispatch_specific_task", "redispatch_task"):
            sync_plans.append(plan)
        elif action == "dispatch_next_task":
            # 保持原有逻辑
            runnable_tasks = task_dependency_service.get_next_runnable_tasks(session, project_id)

            if runnable_tasks:
                from nova_platform.services import agent_service
                for todo in runnable_tasks:
                    assignee = session.query(Employee).filter_by(id=todo.assignee_id).first()
                    if assignee and assignee.type != "human":
                        task_description = f"[项目: {project_id}] {todo.title}"
                        result = agent_service.dispatch_task_async(session, assignee.id, task_description, project_id)
                        if result.get("success") and result.get("task_id"):
                            todo.agent_task_id = result["task_id"]
                        todo.status = "in_progress"
                        session.commit()
                results.append({"action": action, "success": True, "dispatched": len(runnable_tasks)})
            else:
                results.append({"action": action, "success": False, "error": "No runnable tasks"})

    # 执行同步操作
    for plan in sync_plans:
        action = plan["action"]
        params = plan.get("params", {})

        try:
            if action == "update_project_status":
                project = session.query(Project).filter_by(id=project_id).first()
                project.status = params["status"]
                session.commit()
                results.append({"action": action, "success": True})

            elif action == "reset_task":
                todo = session.query(Todo).filter_by(id=params["todo_id"]).first()
                if todo:
                    todo.status = "pending"
                    todo.assignee_id = None
                    todo.updated_at = datetime.utcnow()
                    session.commit()
                    results.append({"action": action, "success": True, "todo": todo.title})
                else:
                    results.append({"action": action, "success": False, "error": "Todo not found"})

            elif action == "dispatch_specific_task":
                todo = session.query(Todo).filter_by(id=params["todo_id"]).first()
                assignee = session.query(Employee).filter_by(id=params["assignee_id"]).first()
                if todo and assignee:
                    todo.assignee_id = assignee.id
                    todo.status = "in_progress"
                    todo.updated_at = datetime.utcnow()
                    session.commit()

                    from nova_platform.services import agent_service
                    task_desc = f"[项目: {project_id}] {todo.title}"
                    result = agent_service.dispatch_task_async(session, assignee.id, task_desc, project_id)
                    if result.get("success") and result.get("task_id"):
                        todo.agent_task_id = result["task_id"]
                        session.commit()

                    results.append({"action": action, "success": True, "todo": todo.title, "agent": assignee.name})
                else:
                    results.append({"action": action, "success": False, "error": "Todo or assignee not found"})

            elif action == "update_priority":
                todo = session.query(Todo).filter_by(id=params["todo_id"]).first()
                if todo:
                    todo.priority = params["priority"]
                    session.commit()
                    results.append({"action": action, "success": True, "todo": todo.title, "priority": params["priority"]})
                else:
                    results.append({"action": action, "success": False, "error": "Todo not found"})

            elif action == "add_task_dependency":
                todo = session.query(Todo).filter_by(id=params["todo_id"]).first()
                if todo:
                    try:
                        current_deps = json.loads(todo.depends_on) if todo.depends_on else []
                        new_deps = params.get("depends_on", [])
                        # 合并依赖，避免重复
                        for dep in new_deps:
                            if dep not in current_deps:
                                current_deps.append(dep)
                        todo.depends_on = json.dumps(current_deps, ensure_ascii=False)
                        session.commit()
                        results.append({"action": action, "success": True, "todo": todo.title})
                    except Exception as e:
                        results.append({"action": action, "success": False, "error": f"JSON error: {str(e)}"})
                else:
                    results.append({"action": action, "success": False, "error": "Todo not found"})

            elif action == "update_project_phase":
                project = session.query(Project).filter_by(id=project_id).first()
                phase_id = params.get("phase_id")
                if project and phase_id:
                    # 记录阶段历史
                    old_phase = project.current_phase
                    project.current_phase = phase_id
                    session.commit()
                    results.append({
                        "action": action,
                        "success": True,
                        "old_phase": old_phase,
                        "new_phase": phase_id
                    })
                else:
                    results.append({"action": action, "success": False, "error": "Project or phase_id not found"})

            elif action == "auto_assign_pending":
                result = auto_assign_tasks(session, project_id)
                results.append({"action": action, "success": True, "assigned": result.get("assigned", 0)})

            elif action == "notify_completion":
                results.append({"action": action, "success": True, "message": "Project completed!"})

            elif action == "query_agent_status":
                results.append({"action": action, "success": True, "message": "Agent status checked"})

            elif action == "redispatch_task":
                todo = session.query(Todo).filter_by(id=params["todo_id"]).first()
                if todo:
                    todo.assignee_id = None
                    todo.status = "pending"
                    todo.updated_at = datetime.utcnow()
                    session.commit()
                    results.append({"action": action, "success": True, "todo": todo.title})
                else:
                    results.append({"action": action, "success": False, "error": "Todo not found"})

            elif action == "awaiting_human":
                results.append({"action": action, "success": True, "message": "Awaiting human response"})

        except Exception as e:
            results.append({"action": action, "success": False, "error": str(e)})

    return {"success": True, "results": results}


def leader_reflect(session: Session, project_id: str, execution_results: dict) -> dict:
    """评估执行结果"""
    results = execution_results.get("results", [])
    successful = [r for r in results if r.get("success")]
    failed = [r for r in results if not r.get("success")]

    reflections = []

    if failed:
        reflections.append({
            "type": "issues_detected",
            "count": len(failed),
            "details": [f"{r['action']}: {r.get('error', 'unknown')}" for r in failed]
        })

    if successful and not failed:
        reflections.append({"type": "all_succeeded", "message": "All actions completed successfully"})

    return {
        "success": True,
        "reflections": reflections,
        "adjustments_needed": len(failed) > 0
    }


def leader_report(session: Session, project_id: str, reflection: dict) -> str:
    """生成进度报告"""
    progress = get_project_progress(session, project_id)

    lines = [
        f"📊 项目进度报告",
        f"   完成度: {progress['completion_rate']*100:.0f}% ({progress['completed']}/{progress['total']})",
        f"   待处理: {progress['pending']} | 进行中: {progress['in_progress']} | 已完成: {progress['completed']}",
        ""
    ]

    for reflection_item in reflection.get("reflections", []):
        if reflection_item["type"] == "issues_detected":
            lines.append(f"⚠️ 发现 {reflection_item['count']} 个问题:")
            for detail in reflection_item["details"]:
                lines.append(f"   - {detail}")
            lines.append("")
        elif reflection_item["type"] == "all_succeeded":
            lines.append("✅ 所有操作执行成功")
            lines.append("")

    return "\n".join(lines)


# ============================================================================
# 统一的高频迭代循环（Cron 直接调用）
# ============================================================================

async def _run_iteration_cycle_async(session: Session, project_id: str) -> dict:
    """
    异步版本的迭代循环 - 内部实现

    使用多层决策引擎进行项目决策和执行
    """
    project = session.query(Project).filter_by(id=project_id).first()
    if not project:
        return {"success": False, "error": "Project not found"}

    # 跳过暂停的项目
    if project.status == "paused":
        return {
            "success": True,
            "message": "Project is paused, skipping iteration",
            "actions": [],
            "leader_triggered": False,
            "skipped": True
        }

    # 跳过等待人类响应的项目
    if project.status == "awaiting_human":
        # 检查是否所有交互已完成
        pending_count = session.query(HumanInteraction).filter(
            HumanInteraction.project_id == project_id,
            HumanInteraction.status == "pending"
        ).count()

        if pending_count > 0:
            return {
                "success": True,
                "message": f"Project awaiting human response ({pending_count} pending)",
                "actions": [],
                "leader_triggered": False,
                "skipped": True,
                "awaiting_human": True
            }
        else:
            # 所有交互已完成，恢复项目状态
            project.status = "active"
            session.commit()

    actions_taken = []
    leader_triggered = False
    leader_decisions = []

    now = datetime.utcnow()

    # ================================================================
    # 快速阶段：程序直接处理
    # ================================================================

    # 收集所有待执行的操作
    todos_to_update = []  # [(todo, changes_dict), ...]
    tasks_to_dispatch = []  # [(todo, assignee_id), ...]

    # 1. 解除阻塞（长时间无响应的 in_progress 任务）
    in_progress_todos = session.query(Todo).filter(
        Todo.project_id == project_id,
        Todo.status == "in_progress"
    ).all()

    for todo in in_progress_todos:
        if todo.assignee_id:
            time_diff = now - todo.updated_at
            if time_diff.total_seconds() > 1800:
                todos_to_update.append((todo, {"assignee_id": None, "status": "pending", "updated_at": now}))
                actions_taken.append({
                    "action": "unblock_task",
                    "todo": todo.title,
                })

    # 1.5 检查所有 in_progress 任务的真实 agent 状态
    from nova_platform.services import agent_service as ag_svc
    from nova_platform.services import task_state_service

    in_progress_todos = session.query(Todo).filter(
        Todo.project_id == project_id,
        Todo.status == "in_progress"
    ).all()

    for todo in in_progress_todos:
        # 获取 assignee 信息
        assignee = None
        if todo.assignee_id:
            assignee = session.query(Employee).filter_by(id=todo.assignee_id).first()

        # 跳过人类员工
        if assignee and assignee.type == "human":
            continue

        if not todo.agent_task_id and not assignee:
            # 没有 agent_task_id 且没有 assignee，重置为 pending
            todos_to_update.append((todo, {"status": "pending", "assignee_id": None, "updated_at": now}))
            actions_taken.append({
                "action": "reset_task",
                "todo": todo.title,
                "reason": "no agent assigned"
            })
            continue

        if todo.agent_task_id or todo.session_id:
            # 有 agent_task_id 或 session_id，进行详细检查
            check_result = {
                "todo": todo,
                "agent_task_id": todo.agent_task_id,
                "session_id": todo.session_id,
                "process_id": todo.process_id,
                "checks": {}
            }

            # 优先使用新的 session_id 方式
            if todo.session_id:
                from nova_platform.services import agent_process_service

                # 检查进程状态
                proc_status = agent_process_service.get_process_status(todo.session_id)
                check_result["checks"]["process_status"] = proc_status

                is_running = proc_status.get("running", False)

                if not is_running:
                    # 进程已结束或不在列表中
                    returncode = proc_status.get("returncode")
                    check_result["checks"]["returncode"] = returncode

                    # 如果进程不在列表中，检查输出文件来判断完成状态
                    if proc_status.get("error") == "Process not found":
                        # 尝试读取输出
                        output = agent_process_service.read_process_output(todo.session_id, max_bytes=10240)
                        check_result["checks"]["output_length"] = len(output) if output else 0

                        # 如果有输出，认为任务完成
                        if output and output.strip():
                            work_summary = output.strip()
                            todo.status = "completed"
                            todo.work_summary = work_summary
                            todo.completed_at = now
                            todo.updated_at = now
                            todos_to_update.append((todo, {"status": "completed", "work_summary": work_summary, "completed_at": now, "updated_at": now}))
                            actions_taken.append({
                                "action": "mark_completed",
                                "todo": todo.title,
                                "reason": "agent process finished and output found",
                                "work_summary_length": len(work_summary)
                            })
                            continue  # 跳过后续处理

                    elif returncode == 0:
                        # 成功完成 - 读取工作总结
                        output = agent_process_service.read_process_output(todo.session_id, max_bytes=10240)
                        work_summary = output.strip() if output else "任务完成（无输出）"

                        todo.status = "completed"
                        todo.work_summary = work_summary
                        todo.completed_at = now
                        todo.updated_at = now
                        todos_to_update.append((todo, {"status": "completed", "work_summary": work_summary, "completed_at": now, "updated_at": now}))
                        actions_taken.append({
                            "action": "mark_completed",
                            "todo": todo.title,
                            "reason": "agent process completed successfully",
                            "work_summary_length": len(work_summary)
                        })
                    else:
                        # 失败
                        if (datetime.utcnow() - todo.updated_at).total_seconds() > 300:
                            todo.status = "pending"
                            todo.assignee_id = None
                            todo.session_id = None
                            todo.process_id = None
                            todo.agent_task_id = None
                            todo.updated_at = now
                            todos_to_update.append((todo, {"status": "pending", "assignee_id": None, "session_id": None, "process_id": None, "agent_task_id": None, "updated_at": now}))
                            actions_taken.append({
                                "action": "reset_task",
                                "todo": todo.title,
                                "reason": f"agent process failed with code {returncode}"
                            })
                else:
                    # 进程仍在运行，检查是否在等待输入
                    is_waiting = agent_process_service.is_process_waiting_for_input(todo.session_id)
                    check_result["checks"]["waiting_for_input"] = is_waiting

                    if is_waiting:
                        # Agent 等待输入，需要处理
                        from nova_platform.services import mailbox_service

                        # 读取 agent 输出
                        output = agent_process_service.read_process_output(todo.session_id, max_bytes=2048)
                        check_result["checks"]["agent_output"] = output[:200] if output else ""

                        # 咨询 leader 并处理
                        handle_result = mailbox_service.handle_agent_waiting(
                            session, todo.session_id, todo.project_id
                        )

                        action_taken = handle_result.get("action_taken")
                        check_result["checks"]["handle_action"] = action_taken

                        if action_taken == "terminate":
                            # Leader 决定终止
                            todo.status = "pending"
                            todo.assignee_id = None
                            todo.session_id = None
                            todo.process_id = None
                            todo.agent_task_id = None
                            todo.updated_at = now
                            todos_to_update.append((todo, {"status": "pending", "assignee_id": None, "session_id": None, "process_id": None, "agent_task_id": None, "updated_at": now}))
                            actions_taken.append({
                                "action": "terminate_agent",
                                "todo": todo.title,
                                "reason": handle_result.get("reason", "Leader decided to terminate")
                            })

                    # 检查进程运行时间
                    started_at = proc_status.get("started_at")
                    if started_at:
                        if isinstance(started_at, str):
                            started_at = datetime.fromisoformat(started_at)
                        elapsed = (datetime.utcnow() - started_at).total_seconds()
                        check_result["checks"]["elapsed_seconds"] = elapsed

                        # 超过 30 分钟视为可能卡住
                        if elapsed > 1800:
                            # 检查最后活动时间
                            last_activity = proc_status.get("last_activity")
                            if last_activity:
                                if isinstance(last_activity, str):
                                    last_activity = datetime.fromisoformat(last_activity)
                                activity_elapsed = (datetime.utcnow() - last_activity).total_seconds()

                                # 如果 10 分钟没有活动，认为卡住
                                if activity_elapsed > 600:
                                    check_result["checks"]["stale"] = True
                                    # 终止进程并重置任务
                                    agent_process_service.terminate_process(todo.session_id, force=True)
                                    todo.status = "pending"
                                    todo.assignee_id = None
                                    todo.session_id = None
                                    todo.process_id = None
                                    todo.agent_task_id = None
                                    todo.updated_at = now
                                    todos_to_update.append((todo, {"status": "pending", "assignee_id": None, "session_id": None, "process_id": None, "agent_task_id": None, "updated_at": now}))
                                    actions_taken.append({
                                        "action": "reset_stuck_task",
                                        "todo": todo.title,
                                        "reason": f"agent process stale for {int(activity_elapsed)}s"
                                    })

            elif todo.agent_task_id:
                # 回退到旧的 task_state_service 方式（向后兼容）
                task_info = task_state_service.get_task_status(session, todo.agent_task_id)
                check_result["checks"]["task_exists"] = task_info is not None

                if not task_info:
                    # 任务记录不存在，可能已清理
                    todos_to_update.append((todo, {"status": "completed", "updated_at": now}))
                    actions_taken.append({
                        "action": "mark_completed",
                        "todo": todo.title,
                        "reason": "agent task record not found, assuming completed"
                    })
                    continue

                check_result["checks"]["task_status"] = task_info.get("status")
                check_result["checks"]["task_pid"] = task_info.get("pid")

                # 检查进程是否在线
                pid = task_info.get("pid")
                if pid:
                    is_online = task_state_service.check_process_running(pid)
                    check_result["checks"]["process_online"] = is_online

                    if not is_online and task_info.get("status") == "running":
                        # 进程已死但任务状态仍为 running
                        # 检查是否有输出文件
                        import os
                        output_file = f"/tmp/{assignee.type}_task_{todo.agent_task_id}.output" if assignee else None
                        has_output = False
                        output_size = 0

                        if output_file and os.path.exists(output_file):
                            output_size = os.path.getsize(output_file)
                            has_output = output_size > 0

                        check_result["checks"]["has_output"] = has_output
                        check_result["checks"]["output_size"] = output_size

                        if has_output:
                            # 有输出但进程已死，说明任务已完成但状态未更新
                            todo.status = "completed"
                            todo.updated_at = now
                            todos_to_update.append((todo, {"status": "completed", "updated_at": now}))
                            actions_taken.append({
                                "action": "mark_completed",
                                "todo": todo.title,
                                "reason": f"agent process dead but output exists ({output_size} bytes)"
                            })
                        else:
                            # 无输出且进程已死，任务可能失败
                            if (datetime.utcnow() - todo.updated_at).total_seconds() > 300:  # 5分钟
                                todo.status = "pending"
                                todo.assignee_id = None
                                todo.agent_task_id = None
                                todo.updated_at = now
                                todos_to_update.append((todo, {"status": "pending", "assignee_id": None, "agent_task_id": None, "updated_at": now}))
                                actions_taken.append({
                                    "action": "reset_task",
                                    "todo": todo.title,
                                    "reason": "agent process dead, no output, timeout exceeded"
                                })

                # 检查任务是否已完成但 todo 状态未更新
                if task_info.get("status") in ["completed", "failed"]:
                    if todo.status != "completed" and task_info.get("status") == "completed":
                        todo.status = "completed"
                        todo.updated_at = now
                        todos_to_update.append((todo, {"status": "completed", "updated_at": now}))
                        actions_taken.append({
                            "action": "mark_completed",
                            "todo": todo.title,
                            "reason": "agent task completed"
                        })
                    elif todo.status != "pending" and task_info.get("status") == "failed":
                        todo.status = "pending"
                        todo.assignee_id = None
                        todo.updated_at = now
                        todos_to_update.append((todo, {"status": "pending", "assignee_id": None, "updated_at": now}))
                        actions_taken.append({
                            "action": "reset_task",
                            "todo": todo.title,
                            "reason": f"agent task failed: {task_info.get('error', 'unknown')[:50]}"
                        })

                # 检查任务运行时间是否过长（卡住检测）
                if task_info.get("status") == "running" and task_info.get("started_at"):
                    from datetime import timedelta
                    start_time = task_info["started_at"]
                    if isinstance(start_time, str):
                        start_time = datetime.fromisoformat(start_time)

                    elapsed = (datetime.utcnow() - start_time).total_seconds()
                    check_result["checks"]["elapsed_seconds"] = elapsed

                    # 超过 30 分钟视为卡住
                    if elapsed > 1800:
                        # 尝试检查输出文件是否有更新
                        output_file = None
                        if assignee:
                            if assignee.type == "openclaw":
                                output_file = f"/tmp/openclaw_task_{todo.agent_task_id}.output"
                            elif assignee.type == "hermes":
                                output_file = f"/tmp/hermes_task_{todo.agent_task_id}.output"
                            elif assignee.type == "claude-code":
                                output_file = f"/tmp/claude_task_{todo.agent_task_id}.output"

                        output_stale = True
                        if output_file:
                            import os
                            if os.path.exists(output_file):
                                file_mtime = datetime.fromtimestamp(os.path.getmtime(output_file))
                                # 如果输出文件在 5 分钟内有更新，认为还在工作
                                if (datetime.utcnow() - file_mtime).total_seconds() < 300:
                                    output_stale = False

                        check_result["checks"]["output_stale"] = output_stale

                        if output_stale:
                            # 输出文件长时间未更新，可能卡住
                            # 取消任务并重置
                            task_state_service.cancel_task(session, todo.agent_task_id)
                            todo.status = "pending"
                            todo.assignee_id = None
                            todo.agent_task_id = None
                            todo.updated_at = now
                            todos_to_update.append((todo, {"status": "pending", "assignee_id": None, "agent_task_id": None, "updated_at": now}))
                            actions_taken.append({
                                "action": "reset_stuck_task",
                            "todo": todo.title,
                            "reason": f"agent stuck for {int(elapsed/60)} minutes, no output update"
                        })
                        project_log_service.log_project_event(
                            project_id,
                            "warning",
                            f"Reset stuck task: {todo.title}",
                            details={"elapsed_minutes": int(elapsed/60), "agent_task_id": todo.agent_task_id}
                        )
            else:
                # 使用原有的 check_todo_agent_status 作为补充
                result = ag_svc.check_todo_agent_status(session, todo.id, auto_commit=False)
                if result.get("todo_updated"):
                    actions_taken.append({
                        "action": "agent_completed",
                        "todo": todo.title,
                        "reason": "agent task finished, auto-marked completed"
                    })
                elif result.get("status") == "failed":
                    todos_to_update.append((todo, {"status": "pending", "assignee_id": None, "updated_at": now}))
                    actions_taken.append({
                        "action": "agent_failed",
                        "todo": todo.title,
                        "reason": result.get("message", "agent task failed")
                    })

        elif assignee and assignee.type != "human":
            # 有 assignee 但没有 agent_task_id，可能状态不一致
            # 检查是否有该员工的异步任务
            active_tasks = task_state_service.get_employee_tasks(session, assignee.id, status="running")
            matching_task = None
            for task in active_tasks:
                if task.todo_id == todo.id:
                    matching_task = task
                    break

            if matching_task:
                # 找到了对应的异步任务，关联起来
                todo.agent_task_id = matching_task.id
                todos_to_update.append((todo, {"agent_task_id": matching_task.id}))
                actions_taken.append({
                    "action": "linked_task",
                    "todo": todo.title,
                    "reason": f"linked async task {matching_task.id[:8]}"
                })
            else:
                # 没有找到对应的异步任务，可能需要重新分发
                if (datetime.utcnow() - todo.updated_at).total_seconds() > 600:  # 10分钟
                    todo.status = "pending"
                    todo.assignee_id = None
                    todo.updated_at = now
                    todos_to_update.append((todo, {"status": "pending", "assignee_id": None, "updated_at": now}))
                    actions_taken.append({
                        "action": "reset_orphan_task",
                        "todo": todo.title,
                        "reason": "no active agent task found"
                    })

    # 2. 分发可执行的任务
    runnable_tasks = task_dependency_service.get_next_runnable_tasks(session, project_id)

    if runnable_tasks:
        for todo in runnable_tasks:
            members = project_member_service.list_project_members(session, project_id)

            for m in members:
                emp = m["employee"]
                if emp and emp.type != "human":
                    busy_todo = session.query(Todo).filter(
                        Todo.assignee_id == emp.id,
                        Todo.status == "in_progress"
                    ).first()

                    if not busy_todo and todo.status == "pending":
                        tasks_to_dispatch.append((todo, emp.id, emp.name))
                        break

    # 统一执行数据库更新
    for todo, changes in todos_to_update:
        for key, value in changes.items():
            setattr(todo, key, value)
    if todos_to_update:
        session.commit()

    # 统一分发任务并更新状态
    for todo, assignee_id, agent_name in tasks_to_dispatch:
        from nova_platform.services import agent_service
        task_desc = f"[项目: {project_id}] {todo.title}"
        result = agent_service.dispatch_task_async(session, assignee_id, task_desc, project_id, todo_id=todo.id)

        # 只有进程创建成功后才标记为 in_progress
        if result.get("success"):
            todo.assignee_id = assignee_id
            todo.status = "in_progress"
            todo.updated_at = now
            # 保存 session_id 和 process_id
            if result.get("session_id"):
                todo.session_id = result["session_id"]
            if result.get("process_id"):
                todo.process_id = result["process_id"]
            session.commit()

            actions_taken.append({
                "action": "dispatch",
                "todo": todo.title,
                "agent": agent_name,
                "session_id": result.get("session_id"),
                "process_id": result.get("process_id")
            })
        else:
            # 进程创建失败，记录错误但不改变任务状态
            actions_taken.append({
                "action": "dispatch_failed",
                "todo": todo.title,
                "agent": agent_name,
                "error": result.get("error", "Unknown error")
            })

    # ================================================================
    # 决策阶段：使用多层决策引擎
    # ================================================================

    need_decision = False

    # 检查是否需要决策
    pending_todos = session.query(Todo).filter(
        Todo.project_id == project_id,
        Todo.status == "pending"
    ).count()

    idle_agents = []
    members = project_member_service.list_project_members(session, project_id)
    for m in members:
        emp = m["employee"]
        if emp and emp.type != "human":
            busy_todo = session.query(Todo).filter(
                Todo.assignee_id == emp.id,
                Todo.status == "in_progress"
            ).first()
            if not busy_todo:
                idle_agents.append(emp)

    # 情况1：有待处理任务、有空闲 agent、但没有可运行任务（依赖死锁）
    if pending_todos > 0 and not runnable_tasks and idle_agents:
        need_decision = True

    # 情况2：有多个可运行任务，需要 Leader 决定优先级
    if pending_todos > 0 and len(runnable_tasks) > 1 and actions_taken:
        need_decision = True

    # 情况3：阶段检查 - 检查是否需要阶段转换
    completed_count = session.query(Todo).filter(
        Todo.project_id == project_id,
        Todo.status == "completed"
    ).count()

    if completed_count > 0 and pending_todos == 0:
        # 所有任务已完成，可能需要进入下一阶段
        need_decision = True

    if need_decision:
        leader_triggered = True

        # 收集观察数据
        observation = leader_observe(session, project_id)

        # 使用多层决策引擎
        thoughts = await leader_think(session, project_id, observation)
        decisions = thoughts.get("decisions", [])

        if decisions:
            for d in decisions:
                leader_decisions.append({
                    "action": d.get("action"),
                    "reason": d.get("reason", ""),
                    "source": d.get("source", "unknown"),
                    "layer": thoughts.get("layer", "unknown")
                })

            # 执行决策
            plans = leader_plan(session, project_id, decisions)
            execution = leader_execute(session, project_id, plans)
            reflection = leader_reflect(session, project_id, execution)

    # ================================================================
    # 生成报告
    # ================================================================

    progress = get_project_progress(session, project_id)

    report_lines = []
    report_lines.append("📊 项目进度报告")
    report_lines.append(f"   完成度: {progress['completion_rate']*100:.0f}% ({progress['completed']}/{progress['total']})")
    report_lines.append(f"   待处理: {progress['pending']} | 进行中: {progress['in_progress']} | 已完成: {progress['completed']}")
    report_lines.append("")

    if actions_taken:
        report_lines.append("⚡ 快速循环行动:")
        for a in actions_taken:
            report_lines.append(f"   → {a['action']}: {a['todo']} ({a.get('reason', '')})")
        report_lines.append("")

    if leader_triggered:
        report_lines.append("🧠 多层决策引擎:")
        for d in leader_decisions:
            layer_info = f" [{d['layer']}层]" if 'layer' in d else ""
            report_lines.append(f"   → {d['action']}{layer_info} ({d['source']}): {d['reason']}")
        report_lines.append("")
    elif not actions_taken:
        report_lines.append("✅ 无需行动，团队正在正常工作")

    # 记录迭代结束
    result = {
        "success": True,
        "message": "Iteration completed",
        "actions": actions_taken,
        "leader_triggered": leader_triggered,
        "leader_decisions": leader_decisions,
        "report": "\n".join(report_lines)
    }
    project_log_service.log_iteration_end(project_id, result)

    return result


def run_iteration_cycle(session: Session, project_id: str) -> dict:
    """
    统一的高频迭代循环 - Cron 直接调用这个函数

    内部自动判断：
    - 简单推动（分发任务、解除阻塞）→ 程序直接处理，不调用 Leader
    - 复杂决策（依赖死锁、复杂情况）→ 使用多层决策引擎
      - 第1层：系统规则（快速、确定）
      - 第2层：Leader决策（项目级、异步、防重）
      - 第3层：人类决策（重大决策升级）

    目的：像鞭子一样推动团队前进，同时节约 token
    """
    try:
        # 创建新的事件循环运行异步代码
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(_run_iteration_cycle_async(session, project_id))
        loop.close()
        return result
    except Exception as e:
        import traceback
        error_msg = f"Iteration cycle failed: {str(e)}"
        traceback.print_exc()
        project_log_service.log_project_error(project_id, error_msg)
        return {
            "success": False,
            "error": error_msg
        }


# ============================================================================
# 原有功能（保持兼容）
# ============================================================================

def decompose_requirements(session: Session, project_id: str, requirements: str) -> dict:
    """将需求分解为 TODO 列表"""
    project = session.query(Project).filter_by(id=project_id).first()
    if not project:
        return {"success": False, "error": "Project not found"}

    lines = requirements.strip().split("\n")
    created_todos = []

    for line in lines:
        line = line.strip()
        if not line:
            continue

        is_high = line.startswith("!") or "HIGH" in line.upper()
        if is_high:
            line = line.lstrip("! ").strip()

        is_subtask = line.startswith("-") or line.startswith(">")
        if is_subtask:
            line = line.lstrip("- ").strip()
            priority = "low"
        else:
            priority = "high" if is_high else "medium"

        if line:
            todo = todo_service.create_todo(
                session=session,
                title=line,
                project_id=project_id,
                priority=priority
            )
            created_todos.append(todo)

    return {"success": True, "todos": created_todos}


def auto_assign_tasks(session: Session, project_id: str) -> dict:
    """根据项目成员技能自动分配 TODO"""
    members = project_member_service.list_project_members(session, project_id)
    if not members:
        return {"success": True, "assigned": 0, "message": "No members in project"}

    employees = [m["employee"] for m in members]

    todos = session.query(Todo).filter(
        Todo.project_id == project_id,
        Todo.assignee_id.is_(None),
        Todo.status.in_(["pending"])
    ).order_by(Todo.priority.desc()).all()

    assigned_count = 0
    current_index = 0

    for todo in todos:
        for _ in range(len(employees)):
            emp = employees[current_index % len(employees)]
            current_index += 1

            if emp.type == "human":
                continue

            todo_service.update_todo(
                session=session,
                todo_id=todo.id,
                assignee_id=emp.id,
                status="pending"
            )
            assigned_count += 1
            break

    return {"success": True, "assigned": assigned_count}


def get_project_progress(session: Session, project_id: str) -> dict:
    """获取项目进度统计"""
    todos = session.query(Todo).filter_by(project_id=project_id).all()

    total = len(todos)
    if total == 0:
        return {"total": 0, "pending": 0, "in_progress": 0, "completed": 0, "completion_rate": 0}

    pending = sum(1 for t in todos if t.status == "pending")
    in_progress = sum(1 for t in todos if t.status == "in_progress")
    completed = sum(1 for t in todos if t.status == "completed")

    return {
        "total": total,
        "pending": pending,
        "in_progress": in_progress,
        "completed": completed,
        "completion_rate": round(completed / total, 2)
    }


def get_progress_report(session: Session, project_id: str) -> str:
    """生成项目进度报告文本"""
    project = session.query(Project).filter_by(id=project_id).first()
    if not project:
        return "Project not found"

    progress = get_project_progress(session, project_id)

    lines = [
        f"📊 项目进度报告: {project.name}",
        f"   完成度: {progress['completion_rate']*100:.0f}% ({progress['completed']}/{progress['total']})",
        f"   待处理: {progress['pending']} | 进行中: {progress['in_progress']} | 已完成: {progress['completed']}",
        ""
    ]

    return "\n".join(lines)


def start_project_workflow(session: Session, project_id: str) -> dict:
    """启动项目工作流"""
    project = session.query(Project).filter_by(id=project_id).first()
    if not project:
        return {"success": False, "error": "Project not found"}

    assign_result = auto_assign_tasks(session, project_id)
    project.status = "active"
    session.commit()

    return {
        "success": True,
        "message": f"项目工作流已启动",
        "assigned_tasks": assign_result.get("assigned", 0)
    }
