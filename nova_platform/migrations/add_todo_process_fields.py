"""
数据库迁移脚本：为 Todo 添加进程跟踪字段

运行方式：
    python3 -m nova_platform.migrations.add_todo_process_fields
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from nova_platform.database import init_db, get_session
from sqlalchemy import text


def migrate():
    """执行迁移"""
    init_db()
    session = get_session()

    try:
        # 检查列是否已存在
        result = session.execute(text("PRAGMA table_info(todos)"))
        columns = [row[1] for row in result.fetchall()]

        # 添加 process_id 列
        if 'process_id' not in columns:
            print("正在添加 process_id 列...")
            session.execute(text(
                "ALTER TABLE todos ADD COLUMN process_id INTEGER"
            ))
            session.commit()
            print("✓ process_id 列已添加")
        else:
            print("✓ process_id 列已存在")

        # 添加 session_id 列
        if 'session_id' not in columns:
            print("正在添加 session_id 列...")
            session.execute(text(
                "ALTER TABLE todos ADD COLUMN session_id VARCHAR(100)"
            ))
            session.commit()
            print("✓ session_id 列已添加")
        else:
            print("✓ session_id 列已存在")

        print("✓ 迁移完成")

    except Exception as e:
        session.rollback()
        print(f"✗ 迁移失败: {e}")
        raise


if __name__ == "__main__":
    migrate()
