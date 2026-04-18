"""
任务依赖服务

提供任务依赖图构建和可执行任务查询功能
"""

import json
from typing import Dict, List
from sqlalchemy.orm import Session

from nova_platform.models import Todo


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
