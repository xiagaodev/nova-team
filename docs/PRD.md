# Nova Platform - 产品需求文档 (PRD)

> 版本: v2.0
> 更新日期: 2026-04-18
> 状态: 开发中

---

## 1. 产品概述

### 1.1 核心定位

**Nova Platform — AI 团队的"鞭策系统"**

不是"让 AI 帮你做事"的工具，
而是"用多年项目管理经验，让 AI 团队系统性地达成目标"的管理框架。

```
Nova 的本质 = 管理系统，而不是 AI 工具

个人助手（OpenClaw/Hermes）= 聪明的个体，但能力有天花板
Nova Platform = 组织，用项目管理经验驱动多个 AI 协作完成复杂目标
```

### 1.2 解决的问题

| 问题 | 传统 AI 工具 | Nova Platform |
|------|-------------|---------------|
| **自驱不足** | 给出答案就停止 | 持续追问"达到目标了吗" |
| **无目标感** | 做什么都行 | OKR 驱动，聚焦大目标 |
| **无优先级** | 所有任务平等 | 项目制管理，关键路径优先 |
| **信息差** | AI 猜人类意图 | 强制追问，主动确认 |
| **单点局限** | 一个 AI 做所有事 | 多 Agent 协作，各司其职 |
| **无沉淀** | 做完就结束 | 项目归档，经验可复用 |

### 1.3 目标用户

**核心用户**：个人自由工作者
- 电商运营者（多店铺、多平台管理）
- 自媒体创作者（内容矩阵运营）
- 营销推广人员（多活动、多渠道跟进）

**用户特征**：
- 有大量需要长期跟进的周期性工作
- 需要同时管理多个项目/账号/平台
- 渴望"外包团队"式的 AI 支持，但负担不起人力外包成本

**不是目标用户**：
- 需要详细指令才能工作的场景（个人助手式使用）
- 技术背景不足、不愿学习新工具的用户

### 1.4 核心价值主张

```
你提目标，AI 自主完成工作
像管理外包团队一样管理 AI 员工
24小时运转，目标导向，不断反思
你只需要验收结果
```

---

## 2. 产品架构

### 2.1 整体架构

```
┌─────────────────────────────────────────────────────────────────────┐
│                          Nova Platform                               │
│                    AI 团队的 "鞭策系统"                                │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  用户界面层                                                           │
│  ┌──────────────────────┐  ┌──────────────────────┐                │
│  │   CLI 终端界面        │  │   Web 可视化界面       │                │
│  │   nova 命令           │  │   Dashboard +         │                │
│  │                       │  │   Star Office         │                │
│  └──────────┬───────────┘  └──────────┬───────────┘                │
│             │                          │                             │
│             └────────────┬─────────────┘                             │
│                          ▼                                           │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                    Automation Service                          │   │
│  │                  （鞭策系统的核心引擎）                         │   │
│  │                                                              │   │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐       │   │
│  │  │ Leader Agent │  │ TaskDispatch │  │ Monitor      │       │   │
│  │  │  (决策中心)   │  │ (任务分发)    │  │ (健康监控)    │       │   │
│  │  └──────────────┘  └──────────────┘  └──────────────┘       │   │
│  │                                                              │   │
│  │  ┌──────────────────────────────────────────────────┐       │   │
│  │  │          Iteration Cycle (高频鞭策循环)              │       │   │
│  │  │   Observe → Think → Plan → Execute → Reflect      │       │   │
│  │  └──────────────────────────────────────────────────┘       │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                          │                                           │
│                          ▼                                           │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                      Agent Layer                             │   │
│  │                                                              │   │
│  │  ┌────────────┐  ┌────────────┐  ┌────────────┐            │   │
│  │  │ OpenClaw  │  │  Hermes    │  │Claude Code │  ...        │   │
│  │  │  Agent    │  │  Agent     │  │  Agent     │            │   │
│  │  └────────────┘  └────────────┘  └────────────┘            │   │
│  │                                                              │   │
│  │  ┌──────────────────────────────────────────────────┐       │   │
│  │  │              Mailbox Module (Agent 通讯)           │       │   │
│  │  └──────────────────────────────────────────────────┘       │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                          │                                           │
│                          ▼                                           │
│            ┌─────────────────────────────┐                         │
│            │   SQLAlchemy ORM + SQLite    │                         │
│            │   (~/.nova-platform/)        │                         │
│            └─────────────────────────────┘                         │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.2 技术栈

| 层级 | 技术选型 | 说明 |
|------|----------|------|
| **CLI 框架** | Click 8.x | 命令行界面 |
| **Web 框架** | Flask 2.x | 轻量级 Web 框架 |
| **ORM** | SQLAlchemy 2.x | 数据库抽象层 |
| **数据库** | SQLite | 本地文件存储 |
| **游戏引擎** | Phaser 3 | Star Office 像素风格可视化 |
| **Agent 集成** | OpenClaw / Hermes / Claude Code | 可混用的 AI 执行者 |
| **定时任务** | Cron | 驱动迭代循环 |

---

## 3. 核心概念

### 3.1 与传统工具的本质区别

```
┌─────────────────────────────────────────────────────────────────┐
│                    AI 工具光谱                                    │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  个人助手                      管理框架                           │
│  OpenClaw/Hermes              Nova Platform                     │
│                                                                  │
│  "帮我做这件事"                  "帮我达成这个目标"                 │
│       ↓                              ↓                           │
│  AI 执行 → 完成 → 停止              AI 理解目标                    │
│                                 → 拆解任务                        │
│                                 → 分配给不同 Agent                │
│                                 → 追踪进度                        │
│                                 → 主动汇报                        │
│                                 → 持续迭代直到达成                 │
│                                                                  │
│  人类全程参与                        人类只在关键节点介入             │
│  每次都要给指令                      AI 自主运转                    │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 组织架构类比

```
┌─────────────────────────────────────────────────────────────────┐
│                      Nova AI 团队                                │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│   👤 人类用户 (CEO)                                              │
│      │                                                         │
│      │ 设定愿景/目标/验收标准                                     │
│      ▼                                                         │
│   🧠 Leader Agent (项目经理)                                     │
│      │                                                         │
│      │ - 理解项目愿景                                            │
│      │ - 拆解 OKR                                               │
│      │ - 规划任务依赖                                            │
│      │ - 分配任务给 Worker Agent                                 │
│      │ - 处理冲突和异常                                          │
│      │ - 主动向人类确认关键决策                                    │
│      ▼                                                         │
│   ┌─────────┐  ┌─────────┐  ┌─────────┐                       │
│   │ Worker  │  │ Worker  │  │ Worker  │  ...                  │
│   │ Agent A │  │ Agent B │  │ Agent C │                       │
│   │         │  │         │  │         │                       │
│   │ 执行具体 │  │ 执行具体 │  │ 执行具体 │                       │
│   │ 任务    │  │ 任务    │  │ 任务    │                       │
│   └─────────┘  └─────────┘  └─────────┘                       │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 3.3 鞭策循环（Iteration Cycle）

```
         ┌─────────────────────────────────────────────────┐
         │              NOVA 鞭策循环                       │
         │         高频触发，持续推动项目前进                  │
         └─────────────────────────────────────────────────┘

         ┌──────────────────────────────────────────────┐
         │              [快速阶段] 程序直接处理            │
         │                                               │
         │   1. 有阻塞的任务？→ 解除                      │
         │   2. 有可运行任务？→ 立即分发                   │
         │   3. Agent 任务完成？→ 更新状态                 │
         │   4. 超时无响应？→ 重新分配                     │
         │                                               │
         └──────────────────────────────────────────────┘
                              │
                              │ 遇到复杂决策时触发
                              ▼
         ┌──────────────────────────────────────────────┐
         │              [慢速阶段] Leader Agent           │
         │                                               │
         │   5. Observe（观察）                           │
         │      - 收集项目状态                             │
         │      - 统计进度、阻塞、风险                      │
         │                                               │
         │   6. Think（思考）                             │
         │      - 分析问题根因                             │
         │      - 决定下一步行动                           │
         │      - 决定是否需要人类介入                      │
         │                                               │
         │   7. Plan（规划）                             │
         │      - 将决策转化为具体行动计划                  │
         │                                               │
         │   8. Execute（执行）                           │
         │      - 分发任务给 Agent                         │
         │      - 协调多 Agent 协作                        │
         │                                               │
         │   9. Reflect（反思）                           │
         │      - 评估执行结果                             │
         │      - 判断是否需要调整                         │
         │                                               │
         └──────────────────────────────────────────────┘
                              │
                              │ 产出报告
                              ▼
         ┌──────────────────────────────────────────────┐
         │                 人类                           │
         │     验收结果 / 确认关键决策 / 调整方向           │
         └──────────────────────────────────────────────┘
```

---

## 4. 数据模型

### 4.1 实体关系图

```
┌─────────────────────────────────────────────────────────────────┐
│                                                                  │
│   ┌─────────────┐       ┌──────────────────┐       ┌─────────────┐
│   │   Project   │──────<│  ProjectMember    │>──────│  Employee   │
│   │   (项目)    │       │   (项目成员)      │       │  (员工/Agent)│
│   └──────┬──────┘       └──────────────────┘       └──────┬──────┘
│          │                                                  │
│          │ 1:N                                             │ 1:N
│          ▼                                                  ▼
│   ┌─────────────┐                                    ┌─────────────┐
│   │    OKR     │                                    │  TaskHistory│
│   │ (目标体系) │                                    │ (任务历史)  │
│   └──────┬──────┘                                    └─────────────┘
│          │
│          │ 1:N
│          ▼
│   ┌─────────────┐       ┌──────────────────┐
│   │    Todo     │<>────│   TaskDependency  │
│   │   (任务)    │       │     (依赖关系)     │
│   └──────┬──────┘       └──────────────────┘
│          │
│          │
│          ▼
│   ┌─────────────┐
│   │  Knowledge  │
│   │  (知识库)    │
│   └─────────────┘
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 4.2 模型详细定义

#### Project (项目)

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID | 主键 |
| name | string | 项目名称 |
| description | text | 项目描述 |
| status | enum | planning / active / completed / paused |
| template | enum | software_dev / ecommerce / content_ops / marketing / general |
| owner_id | UUID | 项目负责人（人类） |
| target_at | datetime | 目标完成时间 |
| created_at | datetime | 创建时间 |
| updated_at | datetime | 更新时间 |

#### Employee (员工/Agent)

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID | 主键 |
| name | string | 名称 |
| type | enum | human / openclaw / hermes / claude-code |
| role | enum | leader / developer / designer / content_writer / reviewer / general |
| skills | JSON array | 技能标签列表 |
| agent_id | string | 关联的外部 Agent ID |
| agent_config | JSON | Agent 配置信息 |
| status | enum | idle / busy / offline |
| created_at | datetime | 创建时间 |

#### ProjectMember (项目成员)

| 字段 | 类型 | 说明 |
|------|------|------|
| project_id | UUID | 关联项目 |
| employee_id | UUID | 关联员工/Agent |
| joined_at | datetime | 加入时间 |

#### Todo (任务)

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID | 主键 |
| title | string | 任务标题 |
| description | text | 详细描述 |
| project_id | UUID | 关联项目 |
| assignee_id | UUID | 负责人 |
| status | enum | pending / in_progress / completed / blocked / cancelled |
| priority | enum | low / medium / high / urgent |
| depends_on | JSON array | 依赖的任务 ID 列表 |
| agent_task_id | string | 关联的 Agent 任务 ID |
| estimated_duration | int | 预估时长（分钟） |
| due_date | datetime | 截止日期 |
| created_at | datetime | 创建时间 |
| updated_at | datetime | 更新时间 |

#### Knowledge (知识库)

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID | 主键 |
| project_id | UUID | 关联项目（None = 全局） |
| title | string | 标题 |
| content | text | 内容（Markdown） |
| tags | JSON array | 标签 |
| created_at | datetime | 创建时间 |
| updated_at | datetime | 更新时间 |

---

## 5. 功能模块

### 5.1 Agent 管理层

#### 5.1.1 招募 Agent

```bash
# 招募 OpenClaw Agent
nova agent recruit <name> --type openclaw --role developer --skills "python,javascript"

# 招募 Claude Code Agent
nova agent recruit <name> --type claude-code --role developer

# 招募 Hermes Agent
nova agent recruit <name> --type hermes --role reviewer

# 查看所有 Agent
nova agent list

# 查看 Agent 状态
nova agent status <agent_id>
```

#### 5.1.2 Agent 角色定义

| 角色 | 说明 | 典型 Agent 类型 |
|------|------|----------------|
| leader | 项目Leader，协调者 | Hermes |
| developer | 开发者 | Claude Code / OpenClaw |
| designer | 设计 | OpenClaw |
| content_writer | 内容创作 | OpenClaw / Hermes |
| reviewer | 审核 | Hermes |
| general | 通用 | 任意 |

### 5.2 项目管理

#### 5.2.1 项目 CRUD

```bash
# 创建项目（支持模板）
nova project create "抖音店铺运营" --template ecommerce
nova project create "月度内容计划" --template content_ops
nova project create "新品推广" --template marketing

# 列出项目
nova project list

# 查看项目详情
nova project view <project_id>

# 更新项目状态
nova project update <project_id> --status active
```

#### 5.2.2 项目启动

```bash
# 启动项目工作流（开始鞭策循环）
nova project start <project_id>

# 设置项目目标
nova project set-goal <project_id> "本月销售额增长30%"
```

### 5.3 任务管理

#### 5.3.1 手动任务管理

```bash
# 添加任务
nova todo add "设计首页" --project <id> --priority high
nova todo add "写推广文案" --project <id> --assign <agent_id>

# 设置任务依赖
nova todo add "开发API" --project <id> --depends-on <todo_id>

# 列出任务
nova todo list --project <id>
nova todo list --status pending

# 更新任务
nova todo update <todo_id> --status completed
```

#### 5.3.2 需求分解

```bash
# 将自然语言需求分解为任务列表
nova decompose "我要上架蓝牙耳机新品" --project <id>

# 输出示例：
# ✓ 已分解为 5 个任务：
#   1. [HIGH] 竞品分析 - 依赖: 无
#   2. [HIGH] 产品详情页文案 - 依赖: 1
#   3. [MEDIUM] 推广海报设计 - 依赖: 1
#   4. [HIGH] 抖音短视频脚本 - 依赖: 2, 3
#   5. [MEDIUM] 客服 SOP - 依赖: 2
```

### 5.4 鞭策系统（Automation）

#### 5.4.1 迭代循环

```bash
# 手动触发一次迭代
nova iterate <project_id>

# 启动 Cron 守护进程（高频模式）
nova daemon start --project <id>

# 查看迭代状态
nova daemon status
```

#### 5.4.2 健康监控

```bash
# 系统健康检查
nova health

# 输出示例：
# 📊 系统状态:
#    员工总数: 5
#    活跃员工: 3
#    待处理任务: 12
#    进行中: 3
#    已完成: 45
#    卡住任务: 0
```

### 5.5 报告与进度

#### 5.5.1 进度报告

```bash
# 项目进度报告
nova report --project <id>

# 输出示例：
# 📊 项目进度报告: 抖音店铺运营
#    完成度: 65% (13/20)
#    待处理: 4 | 进行中: 3 | 已完成: 13
#
# ⚡ 快速循环行动:
#    → dispatch: 竞品分析 → Agent-Dev-1
#    → agent_completed: 详情页文案 → 已自动标记完成
#
# 🐢 Leader 介入:
#    → assign_tasks (rule_engine): 3 tasks need assignment

# 全局报告
nova report --all
```

#### 5.5.2 Star Office 可视化

访问地址: `http://localhost:5000/office/`

- **作战指挥室视图**：实时显示各 Agent 状态、任务进度、KR 健康度
- **AI 每日站会**：Agent 自动汇报进展、问题、今日计划
- **进度预警**：KR 进度滞后时主动告警

---

## 6. 已实现服务详解

### 6.1 Automation Service

**文件**: `nova_platform/services/automation_service.py`

核心鞭策引擎，包含：

| 模块 | 功能 |
|------|------|
| `TaskDependencyGraph` | 任务依赖图，支持拓扑排序 |
| `leader_observe` | 观察阶段：收集项目状态 |
| `leader_think` | 思考阶段：Hermes Leader + 规则引擎决策 |
| `leader_plan` | 规划阶段：将决策转化为行动计划 |
| `leader_execute` | 执行阶段：分发任务、协调 Agent |
| `leader_reflect` | 反思阶段：评估执行结果 |
| `run_iteration_cycle` | 统一的高频迭代循环 |

**触发逻辑**：
```
快速阶段（每次 Cron 触发）：
- 解除阻塞任务
- 分发可运行任务
- 检查 Agent 真实状态

慢速阶段（按需触发）：
- 依赖死锁时 → Leader 介入
- 多个可运行任务需优先级判断 → Leader 介入
```

### 6.2 Agent Service

**文件**: `nova_platform/services/agent_service.py`

统一封装多种 Agent 类型：

| Agent 类型 | 命令方式 | 用途 |
|------------|----------|------|
| OpenClaw | `openclaw agent --agent <id> --message` | 通用任务 |
| Hermes | `hermes --profile <profile> chat -q` | 对话式任务 |
| Claude Code | `claude -p <prompt> --max-turns=N` | 代码任务 |

**异步任务分发**：
- 任务立即分发，不阻塞
- 状态文件追踪：`/tmp/nova_agent_tasks/<task_id>.json`
- 支持取消和状态查询

### 6.3 Monitor Service

**文件**: `nova_platform/services/monitor_service.py`

健康监控和恢复机制：

| 功能 | 说明 |
|------|------|
| `check_and_recover_stuck_tasks` | 检查卡住任务并恢复 |
| `get_system_health` | 获取系统健康状态 |
| 进程存活检测 | 使用 `os.kill(pid, 0)` 检测 |
| 超时恢复 | 30 分钟无响应的 in_progress 任务自动重置 |

---

## 7. 竞品分析

### 7.1 竞品对比

| 产品 | 定位 | 局限性 | Nova 优势 |
|------|------|--------|----------|
| **OpenClaw** | 个人 AI 助手 | 杂乱、随时响应、无组织 | 项目制管理、目标驱动 |
| **Hermes Agent** | 个人 AI 助手 | 单 Agent、依赖人工指令 | 多 Agent 协作、Leader 驱动 |
| **Claude Code** | 开发者工具 | 仅限代码、不支持多 Agent | 全任务类型、多 Agent 协调 |
| **Cursor** | AI IDE | 仅限代码开发 | 通用项目、跨领域 |
| **Linear/Asana** | 人类任务管理 | 无 AI 能力 | AI 原生、Agent 自主执行 |
| **Notion AI** | AI 辅助 | 单点功能、无 Agent 协作 | Agent 团队协作 |

### 7.2 Nova 的差异化定位

```
Nova 不是 "又一个 AI 工具"
Nova 是 "AI 团队的管理框架"

竞品解决的是 "让 AI 做事"
Nova 解决的是 "让 AI 像团队一样协作完成目标"
```

---

## 8. 目录结构

```
/home/oops/projects/nova-platform/
├── app.py                              # Flask Web 应用入口
├── nova_platform/
│   ├── __init__.py
│   ├── cli.py                          # CLI 命令行入口
│   ├── models.py                       # SQLAlchemy 数据模型
│   ├── database.py                     # 数据库初始化和会话管理
│   ├── config.py                       # 配置管理
│   ├── star_office.py                  # Star Office 蓝图和路由
│   └── services/
│       ├── __init__.py
│       ├── project_service.py          # 项目服务
│       ├── employee_service.py         # 员工服务
│       ├── todo_service.py            # 任务服务
│       ├── knowledge_service.py        # 知识库服务
│       ├── agent_service.py            # Agent 集成服务 ✓
│       ├── automation_service.py      # 鞭策系统核心 ✓
│       └── monitor_service.py          # 健康监控服务 ✓
├── templates/
│   ├── index.html                      # 整合后的主界面
│   ├── dashboard.html                  # Dashboard 看板界面
│   └── star_office/                    # Star Office 前端资源
├── tests/
├── docs/
├── scripts/
├── config.example.yaml
├── pyproject.toml
├── README.md
└── PRD.md                              # 本文档
```

---

## 9. 配置文件

配置文件位于 `~/.nova-platform/config.yaml`:

```yaml
environment: development  # development | production
server:
  host: 0.0.0.0
  port: 5000
  debug: false
logging:
  level: INFO
  file: ~/.nova-platform/nova-server.log
database:
  path: ~/.nova-platform/nova.db

# Agent 配置
agents:
  default_type: openclaw  # 默认 Agent 类型
  hermes_leader_enabled: true
  hermes_leader_model: claude-sonnet-4

# 迭代循环配置
automation:
  iteration_interval: 60  # 秒
  task_timeout: 1800      # 30 分钟无响应则重置
  max_parallel_tasks: 10  # 最大并行任务数
```

---

## 10. 系统要求

### 10.1 依赖环境

- Python 3.10+
- click >= 8.0.0
- sqlalchemy >= 2.0.0
- flask >= 2.0.0
- python-dateutil >= 2.8.0
- psutil >= 5.9.0

### 10.2 外部依赖

- **OpenClaw CLI** (可选): 用于 OpenClaw Agent
- **Hermes CLI** (可选): 用于 Hermes Agent
- **Claude CLI** (可选): 用于 Claude Code Agent

### 10.3 数据存储

| 数据 | 路径 |
|------|------|
| 数据库 | `~/.nova-platform/nova.db` |
| 日志 | `~/.nova-platform/nova-server.log` |
| Agent 任务状态 | `/tmp/nova_agent_tasks/` |
| Star Office 状态 | `templates/star_office/*.json` |

---

## 11. 开发计划

### 11.1 当前进度

| 模块 | 状态 | 说明 |
|------|------|------|
| 数据模型 | ✅ 完成 | Project/Employee/Todo/Knowledge |
| CLI 命令 | ✅ 完成 | 基础的 CRUD 命令 |
| Agent 集成 | ✅ 完成 | OpenClaw/Hermes/Claude Code |
| Automation Service | ✅ 完成 | 鞭策循环核心 |
| Monitor Service | ✅ 完成 | 健康监控 |
| Star Office | ✅ 完成 | 可视化界面 |
| Web Dashboard | ✅ 完成 | 整合界面 |

### 11.2 待开发功能

| 功能 | 优先级 | 说明 |
|------|--------|------|
| **Mailbox 模块** | P0 | Agent 间通信机制 |
| **OKR 模型** | P0 | 目标-关键结果体系 |
| **主动追问机制** | P1 | Agent 发现问题时主动询问人类 |
| **冲突解决** | P1 | Git-style 版本控制 |
| **评审机制** | P2 | Logic Conflict 处理 |
| **首个 MVP 测试** | P1 | 验证完整工作流 |

### 11.3 验证计划

**第一个验证场景**：使用 Nova 开发一个小型软件系统

```
目标：验证 "AI 外包团队自主开发" 的可行性

步骤：
1. 创建项目，招募 2-3 个 Agent
2. 输入一个中等复杂度的需求
3. 观察 Nova 如何：
   - 理解需求
   - 拆解任务
   - 分配给不同 Agent
   - 协调冲突
   - 向人类确认关键决策
4. 记录需要人类介入的次数
5. 评估最终产出质量

预期：7x24h 运行，3-5 天完成验证
```

---

## 12. 附录

### 12.1 术语表

| 术语 | 说明 |
|------|------|
| **Leader Agent** | 项目经理 Agent，负责理解目标、规划任务、协调执行 |
| **Worker Agent** | 执行者 Agent，负责完成具体任务 |
| **Iteration Cycle** | 迭代循环，Nova 的高频鞭策机制 |
| **Mailbox** | Agent 间消息通信模块 |
| **OKR** | Objectives and Key Results，目标与关键结果 |
| **Human-in-the-Loop** | 人类在关键节点介入的机制 |
| **鞭策系统** | Nova 的核心定位，让 AI 自驱运转的系统 |

### 12.2 相关文档

- [SPEC.md](./docs/SPEC.md) - 详细规格说明
- [IMPLEMENTATION_PLAN.md](./docs/IMPLEMENTATION_PLAN.md) - CLI 实施计划
- [integration-plan.md](./docs/integration-plan.md) - 前端整合计划
- [README.md](./README.md) - 项目使用说明

### 12.3 设计决策记录

| 日期 | 决策 | 理由 |
|------|------|------|
| 2026-04-18 | 采用 Leader + Worker 两级架构 | 简化协调复杂度，同时保留自主决策能力 |
| 2026-04-18 | Cron 驱动的高频迭代 | 替代 WebSocket，简化架构，提高可靠性 |
| 2026-04-18 | 文件系统作为 Agent 状态存储 | 简化分布式协调，无需额外消息队列 |
| 2026-04-18 | 优先 Hermes 作为 Leader | 强对话能力，适合协调和追问人类 |
