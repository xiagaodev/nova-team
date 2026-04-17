#!/usr/bin/env python3
"""
Nova Platform - Task Dispatcher Script
基于 ReAct 迭代模型的定时调度器

Usage:
    python3 nova-dispatch.py [--project PROJECT_ID]
"""
import sys
import json
import argparse
from pathlib import Path

# Add project to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from nova_platform.database import init_db, get_session
from nova_platform.models import Project, Todo, Employee
from nova_platform.services import project_service, agent_service, automation_service


def run_project_iteration(session, project):
    """对单个项目运行迭代循环"""
    print(f"\n🔄 处理项目: {project.name}")

    result = automation_service.run_iteration_cycle(session, project.id)

    if result["success"]:
        print(f"   消息: {result['message']}")
        
        if result.get("actions"):
            for action in result["actions"]:
                print(f"   → {action['action']}: {action.get('todo', '')}")
        
        if result.get("leader_triggered"):
            print(f"   🐢 Leader 介入决策:")
            for d in result.get("leader_decisions", []):
                print(f"      - {d.get('action')} ({d.get('source')}): {d.get('reason', '')}")
        
        print(f"   {result.get('report', '')}")
        return result
    else:
        print(f"   ❌ 迭代失败: {result.get('message')}")
        return result


def dispatch_pending_tasks(session):
    """扫描并分发待处理任务"""
    results = {
        "projects_processed": 0,
        "iterations_run": 0,
        "errors": []
    }

    projects = session.query(Project).filter_by(status="active").all()

    for project in projects:
        results["projects_processed"] += 1

        try:
            iteration_result = run_project_iteration(session, project)
            if iteration_result.get("success"):
                results["iterations_run"] += 1
        except Exception as e:
            results["errors"].append(f"{project.name}: {str(e)}")
            print(f"   ❌ Error: {e}")

    return results


def generate_summary_report(session) -> str:
    """生成汇总报告"""
    projects = session.query(Project).filter_by(status="active").all()

    if not projects:
        return "📊 没有进行中的项目"

    lines = ["📊 Nova Platform 定时报告", "=" * 40]

    total_todos = 0
    total_completed = 0

    for project in projects:
        progress = automation_service.get_project_progress(session, project.id)
        lines.append(f"\n{project.name}")
        lines.append(f"  完成度: {progress['completion_rate']*100:.0f}% ({progress['completed']}/{progress['total']})")
        lines.append(f"  待处理: {progress['pending']} | 进行中: {progress['in_progress']}")

        total_todos += progress["total"]
        total_completed += progress["completed"]

    overall_rate = (total_completed / total_todos * 100) if total_todos > 0 else 0
    lines.append(f"\n{'=' * 40}")
    lines.append(f"总体完成度: {overall_rate:.0f}% ({total_completed}/{total_todos})")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Nova Platform Task Dispatcher")
    parser.add_argument("--project", help="Specific project ID (default: all active projects)")
    args = parser.parse_args()

    init_db()
    session = get_session()

    print("🔄 Nova Platform Task Dispatcher Started")
    print("-" * 50)

    try:
        results = dispatch_pending_tasks(session)

        print("\n" + "=" * 50)
        print(f"处理项目: {results['projects_processed']}")
        print(f"迭代运行: {results['iterations_run']}")

        if results["errors"]:
            print(f"错误数: {len(results['errors'])}")
            for err in results["errors"][:5]:
                print(f"  - {err}")

        report = generate_summary_report(session)
        print("\n" + report)

        if len(results["errors"]) > results["iterations_run"]:
            sys.exit(1)

    except Exception as e:
        print(f"❌ Fatal Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        session.close()


if __name__ == "__main__":
    main()
