"""
数据库迁移脚本：添加AI自动化系统相关表

运行方式：
    python3 -m nova_platform.migrations.add_automation_models
"""

import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from nova_platform.database import init_db, get_session
from nova_platform.models import ProjectMethodology, HumanInteraction, LeaderInvocationLock, ProjectPhaseHistory
from sqlalchemy import text


def migrate():
    """执行迁移"""
    init_db()
    session = get_session()

    try:
        # 检查表是否已存在
        result = session.execute(text(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='project_methodologies'"
        ))
        if result.fetchone():
            print("✓ project_methodologies 表已存在，跳过创建")
        else:
            # 创建新表
            print("正在创建新表...")

            # 1. project_methodologies 表
            session.execute(text("""
                CREATE TABLE project_methodologies (
                    id VARCHAR(36) PRIMARY KEY,
                    name VARCHAR(100) NOT NULL UNIQUE,
                    project_type VARCHAR(50) NOT NULL,
                    description TEXT,
                    applicable_scenarios TEXT DEFAULT '{}',
                    phases TEXT NOT NULL,
                    wbs_rules TEXT DEFAULT '{}',
                    best_practices TEXT DEFAULT '[]',
                    decision_rules TEXT DEFAULT '{}',
                    example_project TEXT,
                    is_active BOOLEAN DEFAULT 1,
                    created_at DATETIME,
                    updated_at DATETIME
                )
            """))

            # 2. human_interactions 表
            session.execute(text("""
                CREATE TABLE human_interactions (
                    id VARCHAR(36) PRIMARY KEY,
                    project_id VARCHAR(36) NOT NULL,
                    interaction_type VARCHAR(50) NOT NULL,
                    source VARCHAR(50) DEFAULT 'leader',
                    context TEXT DEFAULT '{}',
                    questions TEXT NOT NULL,
                    leader_recommendation TEXT,
                    status VARCHAR(20) DEFAULT 'pending',
                    human_response TEXT,
                    response_at DATETIME,
                    leader_action_taken TEXT,
                    action_taken_at DATETIME,
                    depends_on_interactions TEXT DEFAULT '[]',
                    created_at DATETIME,
                    updated_at DATETIME
                )
            """))

            # 3. leader_invocation_locks 表
            session.execute(text("""
                CREATE TABLE leader_invocation_locks (
                    id VARCHAR(36) PRIMARY KEY,
                    project_id VARCHAR(36) NOT NULL,
                    invocation_type VARCHAR(50) NOT NULL,
                    invocation_context TEXT DEFAULT '{}',
                    status VARCHAR(20) DEFAULT 'in_progress',
                    result TEXT,
                    error TEXT,
                    locked_at DATETIME,
                    completed_at DATETIME,
                    timeout_seconds INTEGER DEFAULT 300
                )
            """))

            # 4. project_phase_history 表
            session.execute(text("""
                CREATE TABLE project_phase_history (
                    id VARCHAR(36) PRIMARY KEY,
                    project_id VARCHAR(36) NOT NULL,
                    phase_id VARCHAR(50) NOT NULL,
                    phase_name VARCHAR(100) NOT NULL,
                    phase_objective TEXT,
                    entry_condition TEXT,
                    exit_condition TEXT,
                    started_at DATETIME,
                    completed_at DATETIME,
                    result VARCHAR(20) DEFAULT 'in_progress',
                    notes TEXT
                )
            """))

            # 创建索引
            print("正在创建索引...")

            session.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_methodology_type ON project_methodologies(project_type)"
            ))
            session.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_methodology_active ON project_methodologies(is_active)"
            ))

            session.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_interaction_project_status ON human_interactions(project_id, status)"
            ))
            session.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_interaction_type ON human_interactions(interaction_type)"
            ))
            session.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_interaction_created ON human_interactions(created_at)"
            ))

            session.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_lock_project_type ON leader_invocation_locks(project_id, invocation_type)"
            ))
            session.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_lock_status ON leader_invocation_locks(status)"
            ))
            session.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_lock_locked_at ON leader_invocation_locks(locked_at)"
            ))

            session.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_phase_history_project ON project_phase_history(project_id)"
            ))
            session.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_phase_history_phase ON project_phase_history(phase_id)"
            ))
            session.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_phase_history_started ON project_phase_history(started_at)"
            ))

            session.commit()
            print("✓ 新表创建完成")

        # 为 projects 表添加新字段
        print("正在为 projects 表添加新字段...")
        result = session.execute(text("PRAGMA table_info(projects)"))
        columns = [row[1] for row in result.fetchall()]

        new_fields = {
            'methodology_id': 'VARCHAR(36)',
            'current_phase': 'VARCHAR(50) DEFAULT "planning"',
            'phase_history_id': 'VARCHAR(36)',
            'project_config': "TEXT DEFAULT '{}'"
        }

        for field, field_type in new_fields.items():
            if field not in columns:
                session.execute(text(
                    f"ALTER TABLE projects ADD COLUMN {field} {field_type}"
                ))
                print(f"  ✓ 添加字段: {field}")
            else:
                print(f"  - 字段已存在: {field}")

        # 创建新索引
        result = session.execute(text(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_project_phase'"
        ))
        if not result.fetchone():
            session.execute(text(
                "CREATE INDEX idx_project_phase ON projects(current_phase)"
            ))
            print("  ✓ 添加索引: idx_project_phase")

        session.commit()

        # 插入默认方法论数据
        print("\n正在插入默认方法论数据...")
        _insert_default_methodologies(session)

        print("\n✓ 迁移完成")

    except Exception as e:
        session.rollback()
        print(f"✗ 迁移失败: {e}")
        raise


def _insert_default_methodologies(session):
    """插入默认的方法论模板"""

    # 检查是否已有数据
    existing = session.query(ProjectMethodology).count()
    if existing > 0:
        print("  - 方法论数据已存在，跳过插入")
        return

    # 敏捷Scrum方法论
    scrum_phases = [
        {
            "id": "backlog",
            "name": "产品待办",
            "objective": "创建和维护产品待办列表，明确优先级",
            "entry_condition": "项目启动",
            "exit_condition": "至少有3个用户故事，每个故事都有验收标准",
            "checkpoints": [
                {
                    "trigger": "待处理任务为0且进行中任务为0",
                    "action": "review_backlog",
                    "questions": ["需求是否充分?", "是否需要更多用户故事?", "优先级是否合理?"]
                }
            ],
            "best_practices": [
                "用户故事应遵循INVEST原则（Independent独立的, Negotiable可协商的, Valuable有价值的, Estimable可估算的, Small小的, Testable可测试的）",
                "每个故事应有明确的验收标准",
                "优先级考虑业务价值和依赖关系",
                "保持待办列表精简，只保留2-3个Sprint的工作量"
            ]
        },
        {
            "id": "sprint_planning",
            "name": "Sprint计划",
            "objective": "确定Sprint目标和要完成的任务",
            "entry_condition": "backlog阶段完成",
            "exit_condition": "选定任务已分配给团队成员",
            "duration_target": "1-2周",
            "checkpoints": [
                {
                    "trigger": "有可分配任务但无空闲成员",
                    "action": "review_capacity",
                    "questions": ["是否需要调整Sprint范围?", "是否需要增加成员?"]
                }
            ],
            "best_practices": [
                "Sprint长度固定（推荐1-2周）",
                "团队根据容量承诺任务，而不是被迫接受",
                "每个Sprint应有明确的目标",
                "任务分配考虑技能匹配和负载均衡"
            ]
        },
        {
            "id": "sprint_execution",
            "name": "Sprint执行",
            "objective": "团队完成分配的任务",
            "entry_condition": "Sprint计划完成",
            "exit_condition": "所有Sprint任务完成",
            "checkpoints": [
                {
                    "trigger": "有任务阻塞超过30分钟",
                    "action": "handle_blocker",
                    "auto_action": "system_reset_task",
                    "leader_action": "decide_escalate_or_reprioritize"
                },
                {
                    "trigger": "Sprint时间过半",
                    "action": "mid_sprint_review",
                    "questions": ["进度正常?", "风险识别?", "需要调整?"]
                }
            ],
            "best_practices": [
                "每日站会（15分钟）同步进度",
                "任务阻塞立即上报，不要等待",
                "保持Sprint范围稳定，避免中途变更",
                "技术债务也要留时间处理"
            ]
        },
        {
            "id": "sprint_review",
            "name": "Sprint回顾",
            "objective": "展示完成的工作、总结经验教训",
            "entry_condition": "Sprint执行完成",
            "exit_condition": "回顾完成、改进计划已制定",
            "checkpoints": [],
            "best_practices": [
                "演示应聚焦于完成的用户故事",
                "回顾会议保持建设性，不指责个人",
                "识别1-2个改进点，在下一个Sprint实践",
                "将经验教训记录到项目知识库"
            ]
        }
    ]

    scrum = ProjectMethodology(
        name="敏捷Scrum",
        project_type="software_dev",
        description="适用于软件开发的敏捷方法论，强调迭代交付和持续改进",
        applicable_scenarios=json.dumps({
            "team_size": "3-10人",
            "timeline": "1-6个月",
            "uncertainty": "中高",
            "iteration": "1-4周Sprint",
            "适合场景": ["新功能开发", "产品迭代", "技术重构"]
        }, ensure_ascii=False),
        phases=json.dumps(scrum_phases, ensure_ascii=False),
        wbs_rules=json.dumps({
            "max_depth": 4,
            "task_size_limit": "2人日",
            "require_dependency": True,
            "decomposition_pattern": "Epic → Feature → Story → Task",
            "task_size_guidance": {
                "Epic": "跨多个Sprint的大型功能",
                "Feature": "1-2个Sprint可完成的功能",
                "Story": "1周内可完成的用户故事",
                "Task": "1-2天可完成的具体任务"
            }
        }, ensure_ascii=False),
        best_practices=json.dumps([
            {
                "phase": "all",
                "practices": [
                    "保持透明度，让所有团队成员了解项目状态",
                    "频繁沟通，减少文档依赖",
                    "拥抱变化，及时调整优先级",
                    "技术卓越与良好设计并重"
                ]
            },
            {
                "phase": "backlog",
                "practices": [
                    "待办列表按优先级排序",
                    "高价值项目优先",
                    "考虑依赖关系和技术风险"
                ]
            }
        ], ensure_ascii=False),
        decision_rules=json.dumps({
            "auto_dispatch": True,
            "leader_decide_on": ["prioritization", "phase_transition", "blocker_escalation", "scope_adjustment"],
            "system_auto_handle": ["task_completion", "blocker_timeout", "dependency_satisfied"]
        }, ensure_ascii=False),
        example_project=json.dumps({
            "name": "电商网站开发",
            "description": "使用Scrum方法开发一个B2C电商网站",
            "phases_example": {
                "backlog": ["用户注册/登录", "商品展示", "购物车", "支付集成", "订单管理"],
                "sprint_1": ["用户注册/登录", "商品展示基础功能"],
                "sprint_2": ["购物车功能", "库存管理"]
            }
        }, ensure_ascii=False)
    )
    session.add(scrum)
    print("  ✓ 插入方法论: 敏捷Scrum")

    # 内容运营方法论
    content_phases = [
        {
            "id": "planning",
            "name": "内容规划",
            "objective": "制定内容生产计划和发布时间表",
            "entry_condition": "项目启动",
            "exit_condition": "有明确的内容日历和分工",
            "checkpoints": [],
            "best_practices": [
                "内容类型多样化（文章、视频、图文等）",
                "考虑热点和季节性",
                "保持一定的内容库存"
            ]
        },
        {
            "id": "production",
            "name": "内容创作",
            "objective": "按照规划生产内容",
            "entry_condition": "规划完成",
            "exit_condition": "内容完成初稿",
            "checkpoints": [
                {
                    "trigger": "内容创作超期",
                    "action": "review_delay",
                    "questions": ["是否需要调整计划?", "是否需要协助?"]
                }
            ],
            "best_practices": [
                "保持内容质量和风格一致",
                "及时记录创作灵感和素材",
                "初稿完成后先自检一遍"
            ]
        },
        {
            "id": "review",
            "name": "审核编辑",
            "objective": "审核内容质量、准确性、合规性",
            "entry_condition": "内容创作完成",
            "exit_condition": "内容通过审核",
            "checkpoints": [],
            "best_practices": [
                "建立审核清单",
                "关注事实准确性和合规风险",
                "保持建设性反馈"
            ]
        },
        {
            "id": "publish",
            "name": "发布上线",
            "objective": "将审核通过的内容发布到各渠道",
            "entry_condition": "内容审核通过",
            "exit_condition": "内容已发布",
            "checkpoints": [],
            "best_practices": [
                "选择合适的发布时间",
                "多渠道同步发布",
                "发布后监控数据表现"
            ]
        },
        {
            "id": "analyze",
            "name": "数据分析",
            "objective": "分析内容表现，优化后续策略",
            "entry_condition": "内容发布24小时后",
            "exit_condition": "完成数据分析报告",
            "checkpoints": [],
            "best_practices": [
                "关注阅读量、互动率、转化率",
                "总结高表现内容的特点",
                "形成内容优化建议"
            ]
        }
    ]

    content_ops = ProjectMethodology(
        name="内容运营",
        project_type="content_ops",
        description="适用于内容生产和发布的流程管理",
        applicable_scenarios=json.dumps({
            "team_size": "2-8人",
            "timeline": "持续进行",
            "uncertainty": "低",
            "workflow": "线性流程",
            "适合场景": ["公众号运营", "博客创作", "视频制作", "知识付费"]
        }, ensure_ascii=False),
        phases=json.dumps(content_phases, ensure_ascii=False),
        wbs_rules=json.dumps({
            "max_depth": 3,
            "task_size_limit": "1人日",
            "require_dependency": True,
            "decomposition_pattern": "栏目 → 主题 → 内容",
            "task_size_guidance": {
                "栏目": "长期内容分类，如技术博客、行业观察",
                "主题": "具体的选题方向",
                "内容": "单篇文章或视频，1-2天完成"
            }
        }, ensure_ascii=False),
        best_practices=json.dumps([
            {
                "phase": "all",
                "practices": [
                    "保持内容日历更新",
                    "建立内容模板提高效率",
                    "定期回顾内容表现数据"
                ]
            },
            {
                "phase": "production",
                "practices": [
                    "提前准备素材和资料",
                    "保持和审核人的沟通"
                ]
            }
        ], ensure_ascii=False),
        decision_rules=json.dumps({
            "auto_dispatch": True,
            "leader_decide_on": ["content_approval", "schedule_adjustment", "quality_issues"],
            "system_auto_handle": ["task_completion", "schedule_reminder"]
        }, ensure_ascii=False),
        example_project=json.dumps({
            "name": "技术公众号运营",
            "description": "每周发布3-5篇技术文章",
            "phases_example": {
                "planning": ["制定月度内容计划", "分配撰稿人"],
                "production": ["撰写文章", "配图制作"],
                "review": ["技术审核", "语言校对"],
                "publish": ["公众号发布", "同步到其他平台"]
            }
        }, ensure_ascii=False)
    )
    session.add(content_ops)
    print("  ✓ 插入方法论: 内容运营")

    session.commit()
    print("  ✓ 默认方法论数据插入完成")


if __name__ == "__main__":
    migrate()
