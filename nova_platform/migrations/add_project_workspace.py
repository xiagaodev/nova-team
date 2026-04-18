"""
数据库迁移脚本：为 Project 添加 workspace_path 字段

运行方式：
    python3 -m nova_platform.migrations.add_project_workspace
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
        # 检查 workspace_path 列是否已存在
        result = session.execute(text("PRAGMA table_info(projects)"))
        columns = [row[1] for row in result.fetchall()]

        if 'workspace_path' in columns:
            print("✓ workspace_path 列已存在，无需迁移")
            return

        # 添加 workspace_path 列
        print("正在添加 workspace_path 列...")
        session.execute(text(
            "ALTER TABLE projects ADD COLUMN workspace_path VARCHAR(500)"
        ))
        session.commit()

        # 为现有项目设置默认工作空间
        print("为现有项目设置默认工作空间...")
        from nova_platform.config import get_workspace_root
        workspace_root = get_workspace_root()

        result = session.execute(text(
            "SELECT id FROM projects WHERE workspace_path IS NULL"
        ))
        project_ids = [row[0] for row in result.fetchall()]

        for pid in project_ids:
            workspace = os.path.join(workspace_root, pid)
            session.execute(text(
                "UPDATE projects SET workspace_path = :ws WHERE id = :pid"
            ), {"ws": workspace, "pid": pid})

        session.commit()
        print(f"✓ 为 {len(project_ids)} 个项目设置了默认工作空间")

        print("✓ 迁移完成")

    except Exception as e:
        session.rollback()
        print(f"✗ 迁移失败: {e}")
        raise


if __name__ == "__main__":
    migrate()
