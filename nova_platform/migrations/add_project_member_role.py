"""
数据库迁移脚本：为 ProjectMember 添加 role 字段

运行方式：
    python3 -m nova_platform.migrations.add_project_member_role
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
        # 检查 role 列是否已存在
        result = session.execute(text("PRAGMA table_info(project_members)"))
        columns = [row[1] for row in result.fetchall()]

        if 'role' in columns:
            print("✓ role 列已存在，无需迁移")
            return

        # 添加 role 列
        print("正在添加 role 列...")
        session.execute(text(
            "ALTER TABLE project_members ADD COLUMN role VARCHAR(50) DEFAULT 'member'"
        ))
        session.commit()

        # 更新现有数据，将所有现有成员设为 member
        print("更新现有成员角色...")
        session.execute(text(
            "UPDATE project_members SET role = 'member' WHERE role IS NULL"
        ))
        session.commit()

        print("✓ 迁移完成")

    except Exception as e:
        session.rollback()
        print(f"✗ 迁移失败: {e}")
        raise


if __name__ == "__main__":
    migrate()
