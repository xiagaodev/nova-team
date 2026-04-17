"""
Automation Service - 项目协作的迭代循环

核心设计：
- Cron 高频触发（每分钟或更快）
- 快速推动：程序直接处理分发任务、解除阻塞
- 复杂决策：才调用 Hermes Leader Agent

流程：
    Cron 触发 run_iteration_cycle()
        ↓
    [快速阶段] 程序判断
        - 有阻塞？→ 解除
        - 有可运行任务？→ 立即分发
        ↓
    [慢速阶段] Leader 判断（按需）
        - 依赖死锁？→ Leader 决策
        - 复杂情况？→ Leader 决策
"""

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Optional, List, Dict
import threading

from sqlalchemy.orm import Session

from nova_platform.models import Project, Todo, Employee, ProjectMember
from nova_platform.services import todo_service, employee_service

# 全局线程池，用于并行分发任务
_executor = ThreadPoolExecutor(max_workers=10)

# Hermes Leader 配置
HERMES_LEADER_ENABLED = True
HERMES_LEADER_MODEL = "claude-sonnet-4"


# ============================================================================
# 任务依赖图
# ============================================================================

class TaskDependencyGraph:
    """任务依赖图 - 使用拓扑排序确定任务执行顺序"""
    
    def __init__(self):
        self.nodes: Dict[str, dict] = {}
        self.graph: Dict[str, list] = {}
    
    def add_task(self, task_id: str, title: str, depends_on: list = None):
        self.nodes[task_id] = {
            "title": title,
            "depends_on": depends_on or [],
            "status": "pending"
        }
        self.graph[task_id] = []
        for dep_id in (depends_on or []):
            if dep_id in self.graph:
                self.graph[dep_id].append(task_id)
            else:
                self.graph[dep_id] = [task_id]
    
    def get_ready_tasks(self) -> list:
        """获取所有就绪的任务（依赖都已完成）"""
        ready = []
        for task_id, node in self.nodes.items():
            if node["status"] != "pending":
                continue
            deps = node["depends_on"]
            if not deps:
                ready.append(task_id)
            else:
                all_deps_done = all(
                    self.nodes.get(dep_id, {}).get("status") == "completed"
                    for dep_id in deps
                )
                if all_deps_done:
                    ready.append(task_id)
        return ready
    
    def get_execution_order(self) -> list:
        """获取拓扑排序后的执行顺序（分层）"""
        in_degree = {task_id: len(self.nodes[task_id]["depends_on"]) 
                     for task_id in self.nodes}
        layers = []
        remaining = set(self.nodes.keys())
        
        while remaining:
            ready = [t for t in remaining if in_degree[t] == 0]
            if not ready:
                break
            layers.append(ready)
            for task_id in ready:
                remaining.remove(task_id)
                for dependent in self.graph.get(task_id, []):
                    if dependent in remaining:
                        in_degree[dependent] -= 1
        return layers


def build_dependency_graph(session: Session, project_id: str) -> TaskDependencyGraph:
    """从数据库构建项目的任务依赖图"""
    todos = session.query(Todo).filter_by(project_id=project_id).all()
    graph = TaskDependencyGraph()
    
    for todo in todos:
        try:
            deps = json.loads(todo.depends_on) if todo.depends_on else []
        except json.JSONDecodeError:
            deps = []
        graph.add_task(todo.id, todo.title, deps)
        if todo.id in graph.nodes:
            graph.nodes[todo.id]["status"] = todo.status
    
    return graph


def get_next_runnable_tasks(session: Session, project_id: str) -> list:
    """获取下一个可执行的任务列表（考虑依赖关系）"""
    graph = build_dependency_graph(session, project_id)
    ready = graph.get_ready_tasks()
    
    runnable = []
    for task_id in ready:
        todo = session.query(Todo).filter_by(id=task_id).first()
        if todo and todo.status == "pending":
            runnable.append(todo)
    
    return runnable


# ============================================================================
# Hermes Leader 决策
# ============================================================================

def _call_hermes_leader(context: dict) -> dict:
    """调用 Hermes Leader 进行决策"""
    import subprocess
    
    status = context.get("status_summary", {})
    blockers_count = context.get("blockers_count", 0)
    
    prompt = f"""项目状态：
- 总任务: {status.get('total', 0)}
- 待处理: {status.get('pending', 0)}
- 进行中: {status.get('in_progress', 0)}
- 已完成: {status.get('completed', 0)}
- 阻塞: {blockers_count}

分析并给出 1-2 个最重要的行动建议。只返回一个简短的英文 action 词：
- "assign" 表示需要分配任务
- "check" 表示检查进度
- "complete" 表示项目完成
- "idle" 表示无需行动
"""
    
    try:
        cmd = ["hermes", "chat", "-q", prompt]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        
        if result.returncode == 0:
            output = result.stdout.strip().lower()
            decisions = []
            if "assign" in output:
                decisions.append({"action": "assign_tasks", "reason": "Hermes: tasks need assignment"})
            elif "check" in output:
                decisions.append({"action": "check_progress", "reason": "Hermes: check task progress"})
            elif "complete" in output:
                decisions.append({"action": "complete_project", "reason": "Hermes: project completed"})
            else:
                decisions.append({"action": "no_action", "reason": f"Hermes: {result.stdout[:50]}"})
            return {"decisions": decisions}
        else:
            return {"decisions": [{"action": "no_action", "reason": f"Hermes error: {result.stderr}"}]}
    except Exception as e:
        return {"decisions": [{"action": "no_action", "reason": str(e)}]}


def leader_think(session: Session, project_id: str, observation: dict) -> dict:
    """分析问题，决定下一步行动（优先 Hermes，不行则规则）"""
    global HERMES_LEADER_ENABLED
    
    context = {
        "project_id": project_id,
        "project_name": observation.get("project", {}).name if observation.get("project") else None,
        "status_summary": observation.get("status_summary", {}),
        "blockers_count": len(observation.get("blockers", [])),
        "todos": [
            {"id": t.id, "title": t.title, "status": t.status, "assignee_id": t.assignee_id}
            for t in observation.get("todos", [])
        ]
    }
    
    if HERMES_LEADER_ENABLED:
        try:
            hermes_result = _call_hermes_leader(context)
            if hermes_result and hermes_result.get("decisions"):
                decisions = hermes_result["decisions"]
                for d in decisions:
                    d["source"] = "hermes"
                return {"success": True, "decisions": decisions}
        except Exception:
            pass
    
    # 回退到规则引擎
    decisions = _rule_based_think(observation)
    for d in decisions:
        d["source"] = "rule_engine"
    return {"success": True, "decisions": decisions}


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
    """收集项目当前状态"""
    project = session.query(Project).filter_by(id=project_id).first()
    if not project:
        return {"success": False, "error": "Project not found"}

    todos = session.query(Todo).filter_by(project_id=project_id).all()
    members = session.query(ProjectMember).filter_by(project_id=project_id).all()

    status_summary = {
        "pending": [t for t in todos if t.status == "pending"],
        "in_progress": [t for t in todos if t.status == "in_progress"],
        "completed": [t for t in todos if t.status == "completed"],
        "blocked": [t for t in todos if t.status == "blocked"]
    }

    blockers = []
    for t in todos:
        if t.status == "in_progress" and t.assignee_id:
            assignee = session.query(Employee).filter_by(id=t.assignee_id).first()
            if assignee and assignee.type != "human":
                time_diff = datetime.utcnow() - t.updated_at
                if time_diff.total_seconds() > 1800:
                    blockers.append({"todo": t, "assignee": assignee})

    return {
        "success": True,
        "project": project,
        "todos": todos,
        "members": members,
        "status_summary": {
            "total": len(todos),
            "pending": len(status_summary["pending"]),
            "in_progress": len(status_summary["in_progress"]),
            "completed": len(status_summary["completed"]),
            "blocked": len(blockers)
        },
        "blockers": blockers
    }


# ============================================================================
# Leader 计划阶段
# ============================================================================

def leader_plan(session: Session, project_id: str, decisions: list) -> list:
    """将决策转化为具体行动计划"""
    plans = []

    for decision in decisions:
        action = decision["action"]

        if action == "complete_project":
            plans.append({"stage": "act", "action": "update_project_status", "params": {"status": "completed"}})
            plans.append({"stage": "report", "action": "notify_completion", "params": {}})

        elif action == "handle_blockers":
            for blocker in decision.get("blockers", []):
                plans.append({
                    "stage": "act",
                    "action": "redispatch_task",
                    "params": {"todo_id": blocker["todo"].id, "assignee_id": blocker["assignee"].id}
                })

        elif action == "assign_tasks":
            plans.append({"stage": "act", "action": "auto_assign_pending", "params": {"project_id": project_id}})

        elif action == "check_progress":
            plans.append({"stage": "act", "action": "query_agent_status", "params": {"project_id": project_id}})

        elif action == "start_next_phase":
            plans.append({"stage": "act", "action": "dispatch_next_task", "params": {"project_id": project_id}})

    return plans


# ============================================================================
# Leader 执行阶段
# ============================================================================

def _dispatch_single_task_async(args: tuple) -> dict:
    """在独立线程中异步分发任务"""
    todo_id, assignee_id, task_description = args
    
    from nova_platform.services import agent_service
    from nova_platform.database import get_session
    
    session = get_session()
    try:
        result = agent_service.dispatch_task_async(session, assignee_id, task_description)
        return {
            "success": result["success"],
            "todo_id": todo_id,
            "task_id": result.get("task_id"),
            "message": result.get("message"),
            "error": result.get("error") if not result["success"] else None
        }
    except Exception as e:
        return {"success": False, "todo_id": todo_id, "error": str(e)}


def leader_execute(session: Session, project_id: str, plans: list) -> dict:
    """执行计划"""
    results = []
    sync_plans = []
    async_task_args = []

    for plan in plans:
        action = plan["action"]
        params = plan.get("params", {})

        if action in ("update_project_status", "notify_completion", "auto_assign_pending"):
            sync_plans.append(plan)
        elif action == "redispatch_task":
            sync_plans.append(plan)  # 需要在同步阶段处理
        elif action == "dispatch_next_task":
            runnable_tasks = get_next_runnable_tasks(session, project_id)
            
            if runnable_tasks:
                from nova_platform.services import agent_service
                for todo in runnable_tasks:
                    assignee = session.query(Employee).filter_by(id=todo.assignee_id).first()
                    if assignee and assignee.type != "human":
                        task_description = f"[项目: {project_id}] {todo.title}"
                        # 先同步获取 task_id 并保存到 Todo
                        result = agent_service.dispatch_task_async(session, assignee.id, task_description, project_id)
                        if result.get("success") and result.get("task_id"):
                            todo.agent_task_id = result["task_id"]
                        todo.status = "in_progress"
                        session.commit()
                        # 异步任务已在前面的调用中提交到线程池
            else:
                results.append({"action": action, "success": False, "error": "No runnable tasks"})
        elif action == "redispatch_task":
            # 收集，稍后统一处理
            pass  # 由 leader_execute 统一处理
        elif action == "query_agent_status":
            sync_plans.append(plan)

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
        except Exception as e:
            results.append({"action": action, "success": False, "error": str(e)})

    # 并行分发异步任务
    if async_task_args:
        dispatch_futures = [_executor.submit(_dispatch_single_task_async, args) for args in async_task_args]
        for future in as_completed(dispatch_futures):
            try:
                result = future.result(timeout=10)
                results.append({
                    "action": "dispatch_next_task",
                    "success": result["success"],
                    "todo_id": result.get("todo_id"),
                    "error": result.get("error")
                })
            except Exception as e:
                results.append({"action": "dispatch_next_task", "success": False, "error": str(e)})

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

def run_iteration_cycle(session: Session, project_id: str) -> dict:
    """
    统一的高频迭代循环 - Cron 直接调用这个函数
    
    内部自动判断：
    - 简单推动（分发任务、解除阻塞）→ 程序直接处理，不调用 Leader
    - 复杂决策（依赖死锁、复杂情况）→ 才调用 Leader Agent
    
    目的：像鞭子一样推动团队前进，同时节约 token
    """
    project = session.query(Project).filter_by(id=project_id).first()
    if not project:
        return {"success": False, "error": "Project not found"}

    actions_taken = []
    leader_triggered = False
    leader_decisions = []
    leader_report_text = None

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
    in_progress_todos = session.query(Todo).filter(
        Todo.project_id == project_id,
        Todo.status == "in_progress"
    ).all()
    
    for todo in in_progress_todos:
        if todo.agent_task_id:
            # 有 agent_task_id，检查真实状态（不自动 commit）
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

    # 2. 分发可执行的任务
    runnable_tasks = get_next_runnable_tasks(session, project_id)
    
    if runnable_tasks:
        for todo in runnable_tasks:
            members = session.query(ProjectMember).filter_by(project_id=project_id).all()
            
            for member in members:
                emp = session.query(Employee).filter_by(id=member.employee_id).first()
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
        todo.assignee_id = assignee_id
        todo.status = "in_progress"
        todo.updated_at = now
        session.commit()
        
        from nova_platform.services import agent_service
        task_desc = f"[项目: {project_id}] {todo.title}"
        result = agent_service.dispatch_task_async(session, assignee_id, task_desc, project_id)
        
        # 保存 task_id 到 Todo，以便后续检查真实状态
        if result.get("success") and result.get("task_id"):
            todo.agent_task_id = result["task_id"]
            session.commit()
        
        actions_taken.append({
            "action": "dispatch",
            "todo": todo.title,
            "agent": agent_name
        })

    # 3. 检查空闲 agent 和待处理任务
    pending_todos = session.query(Todo).filter(
        Todo.project_id == project_id,
        Todo.status == "pending"
    ).count()
    
    idle_agents = []
    members = session.query(ProjectMember).filter_by(project_id=project_id).all()
    for member in members:
        emp = session.query(Employee).filter_by(id=member.employee_id).first()
        if emp and emp.type != "human":
            busy_todo = session.query(Todo).filter(
                Todo.assignee_id == emp.id,
                Todo.status == "in_progress"
            ).first()
            if not busy_todo:
                idle_agents.append(emp)

    # ================================================================
    # 慢速阶段：按需调用 Leader
    # ================================================================
    
    need_leader = False
    
    # 情况1：有待处理任务、有空闲 agent、但没有可运行任务（依赖死锁）
    if pending_todos > 0 and not runnable_tasks and idle_agents:
        need_leader = True
    
    # 情况2：有多个可运行任务，需要 Leader 决定优先级
    if pending_todos > 0 and len(runnable_tasks) > 1 and actions_taken:
        need_leader = True

    if need_leader:
        leader_triggered = True
        observation = leader_observe(session, project_id)
        thoughts = leader_think(session, project_id, observation)
        decisions = thoughts.get("decisions", [])
        
        if decisions:
            for d in decisions:
                leader_decisions.append({
                    "action": d.get("action"),
                    "reason": d.get("reason", ""),
                    "source": d.get("source", "hermes")
                })
            
            plans = leader_plan(session, project_id, decisions)
            execution = leader_execute(session, project_id, plans)
            reflection = leader_reflect(session, project_id, execution)
            leader_report_text = leader_report(session, project_id, reflection)

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
        report_lines.append("🐢 Leader 介入:")
        for d in leader_decisions:
            report_lines.append(f"   → {d['action']} ({d['source']}): {d['reason']}")
        report_lines.append("")
        if leader_report_text:
            report_lines.append(leader_report_text)
    elif not actions_taken:
        report_lines.append("✅ 无需行动，团队正在正常工作")

    return {
        "success": True,
        "message": "Iteration completed",
        "actions": actions_taken,
        "leader_triggered": leader_triggered,
        "leader_decisions": leader_decisions,
        "report": "\n".join(report_lines)
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
    members = session.query(ProjectMember).filter_by(project_id=project_id).all()
    if not members:
        return {"success": True, "assigned": 0, "message": "No members in project"}

    member_ids = [m.employee_id for m in members]
    employees = session.query(Employee).filter(Employee.id.in_(member_ids)).all()

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
