#!/usr/bin/env python3
"""
数据库迁移脚本 - P0级别修复

添加：
1. Project表: owner_id, target_at字段
2. OKR表
3. TaskHistory表
4. AsyncTaskState表
5. 各表索引

运行方式：
    python scripts/migrate_add_p0_fixes.py
"""

import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nova_platform.database import init_db, get_session
from nova_platform.models import Base, Project, OKR, TaskHistory, AsyncTaskState
from sqlalchemy import text


def migrate():
    """执行数据库迁移"""
    print("=" * 60)
    print("Nova Platform - 数据库迁移脚本 (P0级别修复)")
    print("=" * 60)
    print()

    # 初始化数据库连接
    init_db()
    session = get_session()

    try:
        # 检查是否已经迁移过
        print("📋 检查迁移状态...")

        # 检查新表是否存在
        inspector_result = session.execute(text(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='okrs'"
        )).fetchone()

        if inspector_result:
            print("✅ 数据库已经迁移过，跳过")
            return

        print("📊 开始迁移...")
        print()

        # 1. 为Project表添加新字段
        print("1️⃣  更新Project表...")
        try:
            session.execute(text("ALTER TABLE projects ADD COLUMN owner_id VARCHAR(36)"))
            print("   ✓ 添加 owner_id 字段")
        except Exception as e:
            if "duplicate column" not in str(e).lower():
                print(f"   ! 添加 owner_id 失败: {e}")

        try:
            session.execute(text("ALTER TABLE projects ADD COLUMN target_at DATETIME"))
            print("   ✓ 添加 target_at 字段")
        except Exception as e:
            if "duplicate column" not in str(e).lower():
                print(f"   ! 添加 target_at 失败: {e}")

        # 2. 创建OKR表
        print()
        print("2️⃣  创建OKR表...")
        session.execute(text("""
            CREATE TABLE okrs (
                id VARCHAR(36) PRIMARY KEY,
                project_id VARCHAR(36) NOT NULL,
                objective VARCHAR(500) NOT NULL,
                target_value FLOAT DEFAULT 0,
                current_value FLOAT DEFAULT 0,
                unit VARCHAR(50) DEFAULT '',
                status VARCHAR(20) DEFAULT 'on_track',
                due_date DATETIME,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """))
        print("   ✓ OKR表创建成功")

        # 创建OKR表索引
        session.execute(text("CREATE INDEX idx_okr_project_status ON okrs(project_id, status)"))
        print("   ✓ OKR表索引创建成功")

        # 3. 创建TaskHistory表
        print()
        print("3️⃣  创建TaskHistory表...")
        session.execute(text("""
            CREATE TABLE task_history (
                id VARCHAR(36) PRIMARY KEY,
                todo_id VARCHAR(36) NOT NULL,
                old_status VARCHAR(20),
                new_status VARCHAR(20) NOT NULL,
                changed_by VARCHAR(36),
                notes TEXT DEFAULT '',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """))
        print("   ✓ TaskHistory表创建成功")

        # 创建TaskHistory表索引
        session.execute(text("CREATE INDEX idx_task_history_todo ON task_history(todo_id)"))
        session.execute(text("CREATE INDEX idx_task_history_changed_by ON task_history(changed_by)"))
        print("   ✓ TaskHistory表索引创建成功")

        # 4. 创建AsyncTaskState表
        print()
        print("4️⃣  创建AsyncTaskState表...")
        session.execute(text("""
            CREATE TABLE async_task_states (
                id VARCHAR(36) PRIMARY KEY,
                status VARCHAR(20) DEFAULT 'running',
                pid INTEGER,
                output TEXT DEFAULT '',
                error TEXT DEFAULT '',
                started_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                completed_at DATETIME,
                employee_id VARCHAR(36),
                todo_id VARCHAR(36)
            )
        """))
        print("   ✓ AsyncTaskState表创建成功")

        # 创建AsyncTaskState表索引
        session.execute(text("CREATE INDEX idx_async_task_status ON async_task_states(status)"))
        session.execute(text("CREATE INDEX idx_async_task_employee ON async_task_states(employee_id)"))
        session.execute(text("CREATE INDEX idx_async_task_todo ON async_task_states(todo_id)"))
        print("   ✓ AsyncTaskState表索引创建成功")

        # 5. 为其他表添加索引
        print()
        print("5️⃣  更新现有表索引...")

        # Project表索引
        try:
            session.execute(text("CREATE INDEX idx_project_status ON projects(status)"))
            print("   ✓ Project表索引: status")
        except Exception:
            pass

        try:
            session.execute(text("CREATE INDEX idx_project_template ON projects(template)"))
            print("   ✓ Project表索引: template")
        except Exception:
            pass

        # Todo表索引
        try:
            session.execute(text("CREATE INDEX idx_todo_project_status ON todos(project_id, status)"))
            print("   ✓ Todo表索引: project_id+status")
        except Exception:
            pass

        try:
            session.execute(text("CREATE INDEX idx_todo_assignee_status ON todos(assignee_id, status)"))
            print("   ✓ Todo表索引: assignee_id+status")
        except Exception:
            pass

        try:
            session.execute(text("CREATE INDEX idx_todo_priority ON todos(priority)"))
            print("   ✓ Todo表索引: priority")
        except Exception:
            pass

        try:
            session.execute(text("CREATE INDEX idx_todo_project_priority ON todos(project_id, priority)"))
            print("   ✓ Todo表索引: project_id+priority")
        except Exception:
            pass

        # 提交所有更改
        session.commit()

        print()
        print("=" * 60)
        print("✅ 数据库迁移完成！")
        print("=" * 60)
        print()
        print("新增功能：")
        print("  • OKR目标管理")
        print("  • 任务历史追踪")
        print("  • 异步任务状态数据库存储")
        print("  • 数据库查询性能优化")
        print()
        print("下一步：")
        print("  • 重启Nova服务器以加载新模型")
        print("  • 使用 nova okr 命令管理目标")
        print()

    except Exception as e:
        session.rollback()
        print()
        print("=" * 60)
        print("❌ 迁移失败！")
        print("=" * 60)
        print(f"错误: {e}")
        print()
        import traceback
        traceback.print_exc()
        sys.exit(1)

    finally:
        session.close()


if __name__ == "__main__":
    migrate()
