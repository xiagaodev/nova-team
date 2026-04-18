#!/usr/bin/env python3
"""
添加工作总结字段到 Todo 表

运行方式:
    python3 scripts/migrate_add_work_summary.py
"""

import sys
import os

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nova_platform.database import get_session, init_db
from sqlalchemy import text


def migrate():
    """执行数据库迁移"""
    session = get_session()

    try:
        # 检查字段是否已存在
        result = session.execute(text("PRAGMA table_info(todos)"))
        columns = [row[1] for row in result.fetchall()]

        if "work_summary" in columns and "completed_at" in columns:
            print("✅ 字段已存在，无需迁移")
            return True

        # 添加 work_summary 字段
        if "work_summary" not in columns:
            print("添加 work_summary 字段...")
            session.execute(text(
                "ALTER TABLE todos ADD COLUMN work_summary TEXT DEFAULT ''"
            ))
            print("✅ work_summary 字段添加成功")

        # 添加 completed_at 字段
        if "completed_at" not in columns:
            print("添加 completed_at 字段...")
            session.execute(text(
                "ALTER TABLE todos ADD COLUMN completed_at DateTime"
            ))
            print("✅ completed_at 字段添加成功")

        session.commit()
        print("\n🎉 迁移完成！")
        return True

    except Exception as e:
        session.rollback()
        print(f"❌ 迁移失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def rollback():
    """回滚迁移（删除字段）"""
    print("⚠️  SQLite 不支持 DROP COLUMN，需要手动重建表")
    print("建议做法：")
    print("1. 创建新表（不包含 work_summary 和 completed_at）")
    print("2. 复制数据到新表")
    print("3. 删除旧表")
    print("4. 重命名新表")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "rollback":
        rollback()
    else:
        migrate()
