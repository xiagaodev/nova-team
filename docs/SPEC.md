# Nova Platform — Collaboration Platform MVP

## 1. 概念与愿景

一个 AI 原生的协作平台，融合人类员工和 AI Agent 的混合团队工作流。用户作为平台所有者，只需要发起需求和验收成果，其余全部由 AI Agent 自主推进。核心体验是"说一声就行，剩下的 Agent 会搞定"。

## 2. 设计原则

- **AI-First**: 默认由 Agent 协作完成，人工只做决策和验收
- **简洁**: CLI 优先，零废话，输出结构化
- **可扩展**: 架构支持未来多项目、多员工、多模板的复杂场景
- **本地优先**: 数据存储在本地（SQLite + 文件），不依赖云服务

## 3. 核心数据模型

### Project（项目）
| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID | 主键 |
| name | string | 项目名称 |
| description | text | 项目描述 |
| status | enum | planning / active / completed / paused |
| template | enum | software_dev / content_ops / general |
| created_at | datetime | 创建时间 |
| updated_at | datetime | 更新时间 |

### Employee（员工）
| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID | 主键 |
| name | string | 姓名/名称 |
| type | enum | human / agent |
| role | enum | manager / developer / designer / content_writer / reviewer / general |
| skills | JSON array | 技能标签列表 |
| created_at | datetime | 创建时间 |

### ProjectMember（项目成员）
| 字段 | 类型 | 说明 |
|------|------|------|
| project_id | UUID | 关联项目 |
| employee_id | UUID | 关联员工 |
| joined_at | datetime | 加入时间 |

### Todo（任务）
| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID | 主键 |
| title | string | 任务标题 |
| description | text | 任务描述 |
| project_id | UUID | 关联项目 |
| assignee_id | UUID | 负责人（员工或 Agent） |
| status | enum | pending / in_progress / completed / cancelled |
| priority | enum | low / medium / high / urgent |
| due_date | datetime | 截止日期（可选） |
| created_at | datetime | 创建时间 |
| updated_at | datetime | 更新时间 |

### Knowledge（知识库）
| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID | 主键 |
| project_id | UUID | 关联项目（None = 全局知识） |
| title | string | 标题 |
| content | text | 内容（Markdown） |
| tags | JSON array | 标签 |
| created_at | datetime | 创建时间 |
| updated_at | datetime | 更新时间 |

## 4. CLI 命令设计

### 项目管理
```bash
nova project create <name> --description "..." --template software_dev
nova project list
nova project view <project_id>
nova project update <project_id> --status active
nova project delete <project_id>
```

### 员工管理
```bash
nova employee add <name> --type human --role developer --skills "python,javascript"
nova employee list
nova employee view <employee_id>
nova employee assign <employee_id> --project <project_id>
nova employee remove <employee_id> --project <project_id>
```

### TODO 管理
```bash
nova todo add "任务标题" --project <project_id> --assign <employee_id> --priority high --due "2026-04-20"
nova todo list --project <project_id>
nova todo list --assign <employee_id>
nova todo list --status pending
nova todo update <todo_id> --status completed
nova todo delete <todo_id>
```

### 知识库
```bash
nova knowledge add --project <project_id> --title "标题" --content "内容" --tags "python,api"
nova knowledge list --project <project_id>
nova knowledge list --global
nova knowledge search "关键词"
nova knowledge view <knowledge_id>
nova knowledge delete <knowledge_id>
```

### 状态与报告
```bash
nova status                    # 所有项目总览
nova report --project <id>     # 单项目详细报告
nova report --all              # 全局报告
```

## 5. 技术方案

### 技术栈
- **语言**: Python 3.10+
- **CLI**: Click 8.x
- **ORM**: SQLAlchemy 2.x
- **数据库**: SQLite（存储在 ~/.nova-platform/nova.db）
- **打包**: setuptools / pyproject.toml

### 目录结构
```
/home/oops/projects/nova-platform/
├── nova_platform/
│   ├── __init__.py
│   ├── cli.py              # CLI 入口和所有命令
│   ├── models.py           # SQLAlchemy 模型
│   ├── database.py         # 数据库初始化和 Session 管理
│   └── services/
│       ├── __init__.py
│       ├── project_service.py
│       ├── employee_service.py
│       ├── todo_service.py
│       └── knowledge_service.py
├── tests/
│   ├── __init__.py
│   ├── test_projects.py
│   ├── test_employees.py
│   ├── test_todos.py
│   └── test_knowledge.py
├── docs/
│   └── SPEC.md
├── pyproject.toml
├── README.md
└── .gitignore
```

### 数据库路径
- 数据库: `~/.nova-platform/nova.db`
- 自动创建目录

## 6. MVP 范围

### 必须实现（MVP）
- [x] 项目 CRUD
- [x] 员工 CRUD + 项目分配
- [x] TODO CRUD + 分配 + 状态管理
- [x] 知识库 CRUD + 搜索
- [x] 状态总览命令

### 暂不实现（v1.0+）
- Agent 调度（nova 作为 Manager Agent）
- 飞书集成
- 定时任务和自动化
- 多模板高级工作流
- Web 界面

## 7. 成功标准

1. `nova --help` 能看到所有命令
2. 能创建项目、员工、TODO 并正确关联
3. `nova status` 能看到所有项目概览
4. `nova report --project <id>` 能生成项目报告
5. 知识库能跨项目搜索
6. 数据持久化到 SQLite，重启不丢失
