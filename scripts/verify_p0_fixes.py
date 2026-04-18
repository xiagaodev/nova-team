#!/usr/bin/env python3
"""
P0修复验证脚本

验证所有P0级别修复是否正确实施。
运行方式: python scripts/verify_p0_fixes.py
"""

import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def check_imports():
    """检查所有新模块是否可以正确导入"""
    print("=" * 60)
    print("1️⃣  检查模块导入...")
    print("=" * 60)

    modules_to_check = [
        ("nova_platform.models", ["OKR", "TaskHistory", "AsyncTaskState"]),
        ("nova_platform.services.okr_service", ["create_okr", "check_okr_health"]),
        ("nova_platform.services.human_interaction_service", ["ask_human", "get_pending_questions"]),
        ("nova_platform.services.task_state_service", ["create_async_task", "check_process_running"]),
    ]

    all_passed = True

    for module_name, items in modules_to_check:
        try:
            module = __import__(module_name, fromlist=items)
            print(f"✅ {module_name}")

            for item in items:
                if hasattr(module, item):
                    print(f"   ✓ {item}")
                else:
                    print(f"   ✗ {item} - 未找到")
                    all_passed = False

        except ImportError as e:
            print(f"✗ {module_name} - 导入失败: {e}")
            all_passed = False

    print()
    return all_passed


def check_database_schema():
    """检查数据库架构是否正确更新"""
    print("=" * 60)
    print("2️⃣  检查数据库架构...")
    print("=" * 60)

    from nova_platform.database import init_db, get_session
    from sqlalchemy import text

    init_db()
    session = get_session()

    # 检查新表是否存在
    tables_to_check = ["okrs", "task_history", "async_task_states"]
    all_passed = True

    for table in tables_to_check:
        result = session.execute(text(
            f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table}'"
        )).fetchone()

        if result:
            print(f"✅ 表 {table} 存在")

            # 检查索引
            indexes = session.execute(text(
                f"SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='{table}'"
            )).fetchall()

            if indexes:
                print(f"   ✓ 索引: {', '.join([idx[0] for idx in indexes])}")
            else:
                print(f"   ! 警告: 表 {table} 没有索引")

        else:
            print(f"✗ 表 {table} 不存在")
            all_passed = False

    # 检查Project表新字段
    print()
    print("检查Project表新字段...")

    project_columns = session.execute(text(
        "PRAGMA table_info(projects)"
    )).fetchall()

    column_names = [col[1] for col in project_columns]

    if "owner_id" in column_names:
        print("✅ owner_id 字段存在")
    else:
        print("✗ owner_id 字段缺失")
        all_passed = False

    if "target_at" in column_names:
        print("✅ target_at 字段存在")
    else:
        print("✗ target_at 字段缺失")
        all_passed = False

    # 检查索引
    print()
    print("检查数据库索引...")

    expected_indexes = [
        "idx_project_status",
        "idx_todo_project_status",
        "idx_todo_assignee_status",
        "idx_okr_project_status",
    ]

    for index_name in expected_indexes:
        result = session.execute(text(
            f"SELECT name FROM sqlite_master WHERE type='index' AND name='{index_name}'"
        )).fetchone()

        if result:
            print(f"✅ 索引 {index_name} 存在")
        else:
            print(f"! 索引 {index_name} 不存在（可能未运行迁移）")

    session.close()
    print()
    return all_passed


def check_model_fields():
    """检查模型字段是否正确定义"""
    print("=" * 60)
    print("3️⃣  检查模型字段定义...")
    print("=" * 60)

    from nova_platform.models import Project, OKR, TaskHistory, AsyncTaskState

    all_passed = True

    # 检查Project模型
    print("Project模型:")
    try:
        project = Project()
        if hasattr(project, 'owner_id'):
            print("   ✓ owner_id")
        else:
            print("   ✗ owner_id 缺失")
            all_passed = False

        if hasattr(project, 'target_at'):
            print("   ✓ target_at")
        else:
            print("   ✗ target_at 缺失")
            all_passed = False
    except Exception as e:
        print(f"   ✗ 错误: {e}")
        all_passed = False

    # 检查OKR模型
    print()
    print("OKR模型:")
    okr_fields = ["id", "project_id", "objective", "target_value",
                  "current_value", "unit", "status", "due_date"]

    try:
        okr = OKR()
        for field in okr_fields:
            if hasattr(okr, field):
                print(f"   ✓ {field}")
            else:
                print(f"   ✗ {field} 缺失")
                all_passed = False
    except Exception as e:
        print(f"   ✗ 错误: {e}")
        all_passed = False

    # 检查AsyncTaskState模型
    print()
    print("AsyncTaskState模型:")
    task_fields = ["id", "status", "pid", "output", "error",
                   "started_at", "completed_at", "employee_id", "todo_id"]

    try:
        task = AsyncTaskState()
        for field in task_fields:
            if hasattr(task, field):
                print(f"   ✓ {field}")
            else:
                print(f"   ✗ {field} 缺失")
                all_passed = False
    except Exception as e:
        print(f"   ✗ 错误: {e}")
        all_passed = False

    print()
    return all_passed


def check_service_functions():
    """检查服务函数是否可用"""
    print("=" * 60)
    print("4️⃣  检查服务函数...")
    print("=" * 60)

    from nova_platform.database import init_db, get_session
    from nova_platform.services import okr_service, task_state_service

    init_db()
    session = get_session()

    all_passed = True

    # 测试OKR服务
    print("OKR服务:")
    try:
        summary = okr_service.get_okr_summary(session, "test-project-id")
        print("   ✓ get_okr_summary()")
    except Exception as e:
        print(f"   ✗ get_okr_summary() - {e}")
        all_passed = False

    try:
        health = okr_service.check_okr_health(session, "test-project-id")
        print("   ✓ check_okr_health()")
    except Exception as e:
        print(f"   ✗ check_okr_health() - {e}")
        all_passed = False

    # 测试Task State服务
    print()
    print("Task State服务:")
    try:
        stats = task_state_service.get_task_statistics(session)
        print("   ✓ get_task_statistics()")
    except Exception as e:
        print(f"   ✗ get_task_statistics() - {e}")
        all_passed = False

    try:
        stuck = task_state_service.get_stuck_tasks(session)
        print("   ✓ get_stuck_tasks()")
    except Exception as e:
        print(f"   ✗ get_stuck_tasks() - {e}")
        all_passed = False

    session.close()
    print()
    return all_passed


def check_cli_commands():
    """检查CLI命令是否注册"""
    print("=" * 60)
    print("5️⃣  检查CLI命令...")
    print("=" * 60)

    from nova_platform.cli import cli

    all_passed = True

    # 检查命令组
    commands_to_check = [
        ("okr", "OKR管理命令组"),
    ]

    for command, description in commands_to_check:
        if command in cli.commands:
            print(f"✅ nova {command} - {description}")
        else:
            print(f"✗ nova {command} - 未找到")
            all_passed = False

    print()
    return all_passed


def check_cross_platform_compatibility():
    """检查跨平台兼容性"""
    print("=" * 60)
    print("6️⃣  检查跨平台兼容性...")
    print("=" * 60)

    import platform

    system = platform.system()
    print(f"操作系统: {system}")

    # 测试进程管理函数
    from nova_platform.services.task_state_service import check_process_running

    # 使用一个不存在的PID进行测试
    try:
        result = check_process_running(999999)
        print(f"✅ check_process_running() 正常工作 (返回: {result})")
    except Exception as e:
        print(f"✗ check_process_running() 失败: {e}")
        return False

    print()
    return True


def main():
    """运行所有验证测试"""
    print()
    print("╔" + "=" * 58 + "╗")
    print("║" + " " * 10 + "Nova Platform - P0修复验证脚本" + " " * 16 + "║")
    print("╚" + "=" * 58 + "╝")
    print()

    results = []

    # 运行所有检查
    results.append(("模块导入", check_imports()))
    results.append(("数据库架构", check_database_schema()))
    results.append(("模型字段", check_model_fields()))
    results.append(("服务函数", check_service_functions()))
    results.append(("CLI命令", check_cli_commands()))
    results.append(("跨平台兼容性", check_cross_platform_compatibility()))

    # 汇总结果
    print("=" * 60)
    print("📊 验证结果汇总")
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
        print("🎉 所有验证通过！P0修复已正确实施。")
        print()
        print("下一步:")
        print("  1. 重启Nova服务器: nova server restart")
        print("  2. 创建OKR: nova okr create <project_id> <objective> --target <value>")
        print("  3. 查看健康度: nova okr health <project_id>")
    else:
        print("⚠️  部分验证失败，请检查上述错误并修复。")
        print()
        print("常见问题:")
        print("  • 数据库未迁移: 运行 python scripts/migrate_add_p0_fixes.py")
        print("  • 模块导入失败: 检查Python路径和依赖")
        print("  • 服务函数错误: 查看详细错误信息")

    print("=" * 60)
    print()

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
