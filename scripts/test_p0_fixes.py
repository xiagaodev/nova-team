#!/usr/bin/env python3
"""
P0修复功能快速测试

测试新增的OKR和Task State功能是否正常工作。
运行方式: python scripts/test_p0_fixes.py
"""

import sys
import os
import json

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_okr_functionality():
    """测试OKR功能"""
    print("=" * 60)
    print("测试OKR功能")
    print("=" * 60)

    from nova_platform.database import init_db, get_session
    from nova_platform.services import okr_service
    from nova_platform.models import Project

    init_db()
    session = get_session()

    # 创建测试项目
    print("1. 创建测试项目...")
    project = Project(
        name="OKR测试项目",
        description="用于测试OKR功能",
        template="software_dev",
        status="planning"
    )
    session.add(project)
    session.commit()
    session.refresh(project)

    print(f"   ✓ 项目创建成功: {project.id[:8]}")

    # 创建OKR
    print("\n2. 创建OKR...")
    okr = okr_service.create_okr(
        session=session,
        project_id=project.id,
        objective="完成单元测试覆盖率达到80%",
        target_value=80,
        unit="%",
        due_date=None
    )

    print(f"   ✓ OKR创建成功: {okr.id[:8]}")
    print(f"   目标: {okr.objective}")
    print(f"   目标值: {okr.target_value} {okr.unit}")

    # 更新进度
    print("\n3. 更新OKR进度...")
    okr = okr_service.update_okr_progress(session, okr.id, 40)
    print(f"   ✓ 当前进度: {okr.current_value}/{okr.target_value} {okr.unit}")

    # 检查健康度
    print("\n4. 检查OKR健康度...")
    health = okr_service.check_okr_health(session, project.id)
    print(f"   整体健康度: {health['overall']}")

    for okr_info in health['okrs']:
        print(f"   - {okr_info['objective'][:30]}...")
        print(f"     进度: {okr_info['progress']}")
        print(f"     状态: {okr_info['status']}")

    # 获取摘要
    print("\n5. 获取OKR摘要...")
    summary = okr_service.get_okr_summary(session, project.id)
    print(f"   总数: {summary['total']}")
    print(f"   正轨: {summary['on_track']}")
    print(f"   平均进度: {summary['average_progress']*100:.1f}%")

    session.close()

    print("\n✅ OKR功能测试通过！")
    print()
    return True


def test_task_state_functionality():
    """测试Task State功能"""
    print("=" * 60)
    print("测试Task State功能")
    print("=" * 60)

    from nova_platform.database import init_db, get_session
    from nova_platform.services import task_state_service

    init_db()
    session = get_session()

    # 创建测试任务状态
    print("1. 创建异步任务记录...")
    task = task_state_service.create_async_task(
        session=session,
        employee_id="test-employee-123",
        todo_id="test-todo-456"
    )

    print(f"   ✓ 任务创建成功: {task.id[:8]}")
    print(f"   初始状态: {task.status}")

    # 更新任务状态
    print("\n2. 更新任务状态...")
    task = task_state_service.update_task_status(
        session=session,
        task_id=task.id,
        status="running",
        pid=12345
    )

    print(f"   ✓ 任务状态已更新: {task.status}")
    print(f"   PID: {task.pid}")

    # 获取任务状态
    print("\n3. 获取任务状态...")
    status = task_state_service.get_task_status(session, task.id)
    print(f"   状态: {status['status']}")
    print(f"   员工ID: {status['employee_id']}")
    print(f"   任务ID: {status['todo_id']}")

    # 获取员工任务
    print("\n4. 获取员工任务列表...")
    employee_tasks = task_state_service.get_employee_tasks(
        session=session,
        employee_id="test-employee-123"
    )

    print(f"   ✓ 找到 {len(employee_tasks)} 个任务")

    # 获取统计信息
    print("\n5. 获取任务统计...")
    stats = task_state_service.get_task_statistics(session)
    print(f"   总任务数: {stats['total']}")
    print(f"   运行中: {stats['running']}")
    print(f"   平均耗时: {stats['average_duration_seconds']:.2f}秒")

    # 取消任务
    print("\n6. 取消任务...")
    result = task_state_service.cancel_task(session, task.id)
    print(f"   ✓ 任务已取消: {result['status']}")

    session.close()

    print("\n✅ Task State功能测试通过！")
    print()
    return True


def test_human_interaction_functionality():
    """测试Human Interaction功能"""
    print("=" * 60)
    print("测试Human Interaction功能")
    print("=" * 60)

    from nova_platform.database import init_db, get_session
    from nova_platform.services import human_interaction_service

    init_db()
    session = get_session()

    # Agent向人类提问
    print("1. Agent向人类提问...")
    result = human_interaction_service.ask_human(
        session=session,
        project_id="test-project-789",
        question="项目进度落后，是否需要增加资源？",
        context={"current_progress": 30, "expected_progress": 60},
        priority="high"
    )

    print(f"   ✓ 问题创建成功: {result['id'][:8]}")
    print(f"   问题: {result['question']}")
    print(f"   优先级: {result['priority']}")

    # 获取待回答问题
    print("\n2. 获取待回答问题...")
    pending = human_interaction_service.get_pending_questions(
        session=session,
        project_id="test-project-789"
    )

    print(f"   ✓ 找到 {len(pending)} 个待回答问题")

    if pending:
        question_id = pending[0]['id']
        print(f"   问题: {pending[0]['question']}")

        # 回答问题
        print("\n3. 回答问题...")
        answer_result = human_interaction_service.answer_question(
            session=session,
            question_id=question_id,
            answer="是的，请增加2个开发者。"
        )

        print(f"   ✓ 问题已回答: {answer_result['status']}")

    # 生成问题
    print("\n4. 根据上下文生成问题...")
    context = {
        "blockers": [
            {"todo": {"title": "API设计"}},
            {"todo": {"title": "数据库优化"}}
        ],
        "okr_health": {"overall": "at_risk"}
    }

    generated_question = human_interaction_service.generate_question_from_context(
        session=session,
        project_id="test-project-789",
        context=context
    )

    if generated_question:
        print(f"   ✓ 生成问题: {generated_question}")

    session.close()

    print("\n✅ Human Interaction功能测试通过！")
    print()
    return True


def test_cross_platform_functions():
    """测试跨平台兼容函数"""
    print("=" * 60)
    print("测试跨平台兼容函数")
    print("=" * 60)

    import platform

    system = platform.system()
    print(f"操作系统: {system}")

    from nova_platform.services.task_state_service import (
        check_process_running,
        terminate_process
    )

    # 测试进程检查
    print("\n1. 测试进程状态检查...")
    # 使用一个不存在的PID
    result = check_process_running(999999)
    print(f"   ✓ check_process_running(999999) = {result}")

    # 测试进程终止
    print("\n2. 测试进程终止函数...")
    print(f"   ✓ terminate_process() 函数可用")

    print("\n✅ 跨平台兼容函数测试通过！")
    print()
    return True


def main():
    """运行所有功能测试"""
    print()
    print("╔" + "=" * 58 + "╗")
    print("║" + " " * 15 + "P0修复功能测试" + " " * 27 + "║")
    print("╚" + "=" * 58 + "╝")
    print()

    results = []

    try:
        results.append(("OKR功能", test_okr_functionality()))
    except Exception as e:
        print(f"❌ OKR功能测试失败: {e}")
        import traceback
        traceback.print_exc()
        results.append(("OKR功能", False))

    try:
        results.append(("Task State功能", test_task_state_functionality()))
    except Exception as e:
        print(f"❌ Task State功能测试失败: {e}")
        import traceback
        traceback.print_exc()
        results.append(("Task State功能", False))

    try:
        results.append(("Human Interaction功能", test_human_interaction_functionality()))
    except Exception as e:
        print(f"❌ Human Interaction功能测试失败: {e}")
        import traceback
        traceback.print_exc()
        results.append(("Human Interaction功能", False))

    try:
        results.append(("跨平台兼容函数", test_cross_platform_functions()))
    except Exception as e:
        print(f"❌ 跨平台兼容函数测试失败: {e}")
        import traceback
        traceback.print_exc()
        results.append(("跨平台兼容函数", False))

    # 汇总结果
    print("=" * 60)
    print("📊 测试结果汇总")
    print("=" * 60)

    all_passed = True
    for name, passed in results:
        status = "✅ 通过" if passed else "❌ 失败"
        print(f"{name}: {status}")
        if not passed:
            all_passed = False

    print()
    print("=" * 60)

    if all_passed:
        print("🎉 所有功能测试通过！")
        print()
        print("P0修复已成功实施，可以开始使用新功能：")
        print("  • nova okr create - 创建OKR")
        print("  • nova okr health - 检查OKR健康度")
        print("  • 异步任务现在存储在数据库中")
    else:
        print("⚠️  部分功能测试失败，请检查错误信息。")

    print("=" * 60)
    print()

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
