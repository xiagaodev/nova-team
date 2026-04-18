# nova-platform 架构文档

## 1. 项目概述

**nova-platform** 是一个 AI 协作平台，支持多项目管理及多种 AI 智能体（OpenClaw、Hermes、Claude Code、Codex 等）。

## 2. 当前问题分析

### 2.1 代码结构问题

| 问题 | 严重程度 | 文件 |
|------|----------|------|
| 单文件过大 | 🔴 高 | `cli.py` (30KB, 700+ 行) |
| 业务逻辑耦合 | 🔴 高 | `star_office.py` (17KB) |
| 服务层臃肿 | 🟡 中 | `agent_service.py` (21KB) |
| 模型与业务混在一起 | 🟡 中 | 多个 service 文件 |

### 2.2 耦合问题

- **CLI 与业务耦合**：`cli.py` 包含所有命令定义，业务逻辑散落各处
- **服务间直接依赖**：service 之间直接 import，牵一发而动全身
- **数据库与模型耦合**：业务逻辑写在 models.py

## 3. 目标架构

### 3.1 分层架构

```
nova_platform/
├── core/                    # 核心层（无业务）
│   ├── config.py           # 配置管理
│   ├── database.py        # 数据库连接
│   ├── exceptions.py     # 异常定义
│   └── events.py         # 事件总线
├── models/                # 数据模型层
│   ├── project.py
│   ├── employee.py
│   ├── todo.py
│   └── knowledge.py
├── services/               # 业务服务层
│   ├── project_service.py
│   ├── agent_service.py
│   └── automation_service.py
├── api/                   # API 层（新增）
│   ├── routes/
│   │   ├── projects.py
│   │   ├── employees.py
│   │   └── todos.py
│   └── schemas/
│       ├── project.py
│       └── todo.py
├── cli/                   # CLI 层（从 cli.py 拆分）
│   ├── __init__.py
│   ├── __main__.py
│   └── commands/
│       ├── project.py
│       ├── server.py
│       └── task.py
├── agents/                 # 智能体抽象层（新增）
│   ├── __init__.py
│   ├── base.py           # 抽象基类
│   ├── factory.py        # 工厂
│   └── implementations.py # 各智能体实现
├── services/              # 业务服务层
│   ├── project_service.py
│   ├── employee_service.py
│   ├── todo_service.py
│   ├── agent_service.py
│   ├── agent_process_service.py  # Agent 进程管理 (NEW)
│   ├── agent_session_service.py  # Agent 会话管理 (NEW)
│   ├── mailbox_service.py        # Agent 交互处理 (NEW)
│   ├── automation_service.py
│   ├── task_state_service.py
│   ├── project_member_service.py
│   ├── project_control_service.py
│   ├── project_log_service.py
│   └── knowledge_service.py
├── plugins/               # 插件扩展（预留）
└── utils/                # 工具函数
```

### 3.2 依赖规则

```
┌─────────────────┐
│    cli/         │  ← 只调用 services
├─────────────────┤
│   api/          │  ← 只调用 services + schemas
├─────────────────┤
│   services/     │  ← 调用 models + core
├─────────────────┤
│   models/       │  ← 无业务逻辑
├─────────────────┤
│    core/        │  ← 基础工具，无依赖
└─────────────────┘
```

## 4. 智能体模块设计

### 4.1 支持的智能体

| 类型 | 命令 | 状态 |
|------|------|------|
| `openclaw` | `openclaw agent --agent <id> --message <msg>` | ✅ |
| `hermes` | `hermes --profile <name> chat -q` | ✅ |
| `claude_code` | `claude -p <prompt>` | ✅ |

### 4.2 会话管理与进程复用

#### 4.2.1 设计原则

1. **会话隔离**: 不同项目使用独立的会话和上下文
2. **进程复用**: 同一项目同一 agent 使用同一进程（保持对话历史）
3. **交互支持**: Agent 可以请求输入，由 leader 决策后响应

#### 4.2.2 会话 ID 规则

```
session_id = "{project_id}#{agent_id}"
```

- 同一项目 + 同一 agent = 同一 session_id
- 进程在 `_running_processes` 字典中以 session_id 为 key 存储
- 输出文件存储在项目会话目录下

#### 4.2.3 目录结构

```
~/.nova/workspaces/<project_id>/.nova/sessions/
├── openclaw_<agent_id>/
│   ├── project_context.json
│   └── task_<timestamp>.output
├── hermes_<profile_name>/
│   ├── project_context.json
│   ├── conversation_history.json
│   └── task_<timestamp>.output
└── claude_<agent_id>/
    ├── .claude/
    │   ├── project_context.json
    │   ├── history.json
    │   └── task_<timestamp>.output
```

### 4.3 进程管理服务 (agent_process_service)

#### 4.3.1 核心功能

```python
# 获取或创建进程（自动复用）
proc, session_id = agent_process_service.get_or_create_process(
    project_id, employee, task, session
)

# 检查进程状态
status = agent_process_service.get_process_status(session_id)
# {"running": bool, "pid": int, "started_at": str, ...}

# 读取进程输出
output = agent_process_service.read_process_output(session_id)

# 检测是否等待输入
waiting = agent_process_service.is_process_waiting_for_input(session_id)

# 向进程发送输入
agent_process_service.send_input_to_process(session_id, input_text)

# 终止进程
agent_process_service.terminate_process(session_id, force=True)
```

#### 4.3.2 进程状态

| 状态 | 说明 |
|------|------|
| running | 进程正常运行 |
| waiting | 等待用户输入 |
| completed | 任务完成 |
| failed | 执行失败 |

### 4.4 邮箱服务 (mailbox_service)

#### 4.4.1 交互流程

```
1. Agent 输出 → 监听检测到等待输入
   ↓
2. 读取 Agent 输出内容
   ↓
3. 咨询 Leader Agent 如何处理
   ↓
4. Leader 决策 (continue/terminate/retry/wait)
   ↓
5. 执行决策
   - continue: 发送输入到 agent
   - terminate: 终止进程
   - retry: 重启任务
   - wait: 等待更多信息
```

#### 4.4.2 AgentMailbox

存储每个会话的交互历史：

```python
class AgentMailbox:
    session_id: str
    project_id: str
    agent_id: str
    messages: List[MailboxMessage]  # 交互历史
    state: AgentState                # 当前状态
```

### 4.5 Todo 模型更新

```python
class Todo(Base):
    # ...原有字段...
    process_id: Mapped[int]           # Agent 进程 PID
    session_id: Mapped[str]           # 会话 ID (project_id#agent_id)
```

### 4.6 Automation 状态检查

```python
# 新的基于进程的状态检查
if todo.session_id:
    proc_status = agent_process_service.get_process_status(todo.session_id)
    
    if not proc_status["running"]:
        # 进程已结束，根据返回码判断成功/失败
        if proc_status["returncode"] == 0:
            todo.status = "completed"
        else:
            todo.status = "pending"  # 重试
    
    elif agent_process_service.is_process_waiting_for_input(todo.session_id):
        # Agent 等待输入，触发 mailbox 处理
        mailbox_service.handle_agent_waiting(session, todo.session_id, project_id)
```

### 4.7 完整调用流程

```
1. 创建 Todo (待分配任务)
   ↓
2. dispatch_task_async(employee_id, task, project_id, todo_id)
   ↓
3. agent_process_service.get_or_create_process()
   - 检查 session_id 是否存在
   - 存在且运行中 → 复用进程
   - 不存在 → 创建新进程
   ↓
4. 更新 Todo: process_id, session_id, status=in_progress
   ↓
5. automation 循环检查 Todo 状态
   ↓
6. agent_process_service.get_process_status(session_id)
   - running → 继续监控
   - waiting_input → mailbox 处理
   - completed → 标记完成
   - failed → 重置任务
```

## 5. 开发规范

### 5.1 文件规范

- **单文件行数**：≤ 100 行
- **单文件职责**：单一功能
- **命名**：小写下划线 `project_service.py`

### 5.2 依赖规范

- 只能向下依赖，不能跨层调用
- service 之间通过事件通信
- 禁止循环依赖

### 5.3 代码审查检查点

```markdown
## PR 检查清单
- [ ] 文件行数 ≤ 100
- [ ] 无跨层依赖
- [ ] 有单元测试
- [ ] 文档更新
- [ ] 无 hardcode 配置
```

## 6. 迁移计划

### Phase 1: 提取核心层
- [ ] 创建 `core/` 目录
- [ ] 移动 config.py, database.py
- [ ] 定义 exceptions.py

### Phase 2: 拆分 CLI
- [ ] 创建 `cli/commands/`
- [ ] 按功能拆分 cli.py
- [ ] 保留 __main__.py 入口

### Phase 3: 智能体抽象
- [ ] 移动现有 agent_service.py 到 agents/
- [ ] 实现 AgentType 抽象
- [ ] 集成到 employee_service

### Phase 4: API 层
- [ ] 创建 api/schemas/
- [ ] 定义 Pydantic models
- [ ] 添加 FastAPI routes

## 7. 后续扩展

### 7.1 插件系统

```python
# nova_platform/plugins/__init__.py
class Plugin:
    name: str
    version: str
    
    def on_load(self): ...
    def on_unload(self): ...
```

### 7.2 事件总线

```python
# 服务间通信
from nova_platform.core import events

events.emit("task:created", {"task_id": "..."})
events.on("task:created", handle_task)
```

### 7.3 WebSocket 支持

- 实时任务状态推送
- 多客户端同步

---

**维护者**: nova-platform team
**最后更新**: 2026-04-18

## 8. 服务列表

| 服务 | 文件 | 职责 |
|------|------|------|
| Project Service | `project_service.py` | 项目 CRUD、工作空间管理 |
| Employee Service | `employee_service.py` | 员工 CRUD |
| Todo Service | `todo_service.py` | 任务 CRUD |
| Agent Service | `agent_service.py` | Agent 任务分发 |
| **Agent Process Service** | `agent_process_service.py` | Agent 进程管理、会话复用 |
| **Agent Session Service** | `agent_session_service.py` | Agent 会话目录管理 |
| **Mailbox Service** | `mailbox_service.py` | Agent 交互式 I/O 处理 |
| Automation Service | `automation_service.py` | 自动化循环、多层决策引擎 ⭐ |
| Task State Service | `task_state_service.py` | 异步任务状态跟踪 |
| Project Member Service | `project_member_service.py` | 项目成员管理、角色 |
| Project Control Service | `project_control_service.py` | 项目暂停/恢复 |
| Project Log Service | `project_log_service.py` | 项目事件日志 |
| Knowledge Service | `knowledge_service.py` | 知识库 CRUD |
| **WBS Service** | `wbs_service.py` | WBS任务拆解、增量式分解 ⭐ |
| **Leader Lock Service** | `leader_lock_service.py` | Leader调用防重机制 ⭐ |
| **Human Interaction Service** | `human_interaction_service.py` | 人类交互管理 ⭐ |
| **Decision Engine** | `decision_engine.py` | 多层决策引擎 ⭐ |
| **Task Dependency Service** | `task_dependency_service.py` | 任务依赖图管理 ⭐ |

⭐ = 最新更新（2025年1月）

## 9. 数据库模型

| 模型 | 表名 | 新增字段 |
|------|------|----------|
| Project | `projects` | `workspace_path`, `methodology_id`, `current_phase`, `phase_history_id`, `project_config` ⭐ |
| Employee | `employees` | `agent_config` |
| Todo | `todos` | `process_id`, `session_id` |
| ProjectMember | `project_members` | `role` |
| OKR | `okrs` | - |
| Knowledge | `knowledge` | - |
| TaskHistory | `task_history` | - |
| AsyncTaskState | `async_task_states` | - |
| **ProjectMethodology** | `project_methodologies` | ⭐ 新增 |
| **HumanInteraction** | `human_interactions` | ⭐ 新增 |
| **LeaderInvocationLock** | `leader_invocation_locks` | ⭐ 新增 |
| **ProjectPhaseHistory** | `project_phase_history` | ⭐ 新增 |

⭐ = 最新更新（2025年1月）

---

## 10. Web Dashboard 架构 ⭐

### 10.1 技术栈

- **前端框架**: Flask + 原生 JavaScript/CSS
- **游戏引擎**: Phaser 3.80.1 (Star Office)
- **字体**: Inter (UI)、JetBrains Mono (代码)、ArkPixel (像素风)
- **时区处理**: UTC+8 统一时区
- **无依赖**: 无React/Vue等前端框架

### 10.2 视图架构

```
┌─────────────────────────────────────────────────────────┐
│                    Web Dashboard (templates/)           │
├─────────────────────────────────────────────────────────┤
│                                                           │
│  ┌─────────────────────────────────────────────────┐    │
│  │  🏢 办公室 (overview-view)                       │    │
│  │  - Star Office Phaser 游戏                       │    │
│  │  - 统计卡片 (4个)                                │    │
│  │  - 项目/员工/任务总览                            │    │
│  └─────────────────────────────────────────────────┘    │
│                                                           │
│  ┌─────────────────────────────────────────────────┐    │
│  │  📁 项目 (projects-view)                         │    │
│  │  - 项目卡片网格                                  │    │
│  │  - 进度条、成员、任务预览                        │    │
│  └─────────────────────────────────────────────────┘    │
│                                                           │
│  ┌─────────────────────────────────────────────────┐    │
│  │  🤖 团队 (employees-view)                        │    │
│  │  - 员工卡片                                      │    │
│  │  - 角色、技能、任务统计                          │    │
│  └─────────────────────────────────────────────────┘    │
│                                                           │
│  ┌─────────────────────────────────────────────────┐    │
│  │  ✅ 任务 (tasks-view) - 四泳道看板                │    │
│  │  - 待处理 | 进行中 | 审核中 | 已完成            │    │
│  │  - 任务卡片、点击查看详情                        │    │
│  └─────────────────────────────────────────────────┘    │
│                                                           │
└─────────────────────────────────────────────────────────┘
```

### 10.3 核心 UI 组件

#### 10.3.1 统计卡片

```html
<div class="stats-grid">
  <div class="stat-card">📁 项目总数</div>
  <div class="stat-card green">👥 团队成员 (人类/AI分布)</div>
  <div class="stat-card amber">📋 任务总数 (状态分布)</div>
  <div class="stat-card purple">🤖 AI Agent 数量</div>
</div>
```

#### 10.3.2 任务看板（四泳道）

```javascript
// 四泳道布局
lanes = ['pending', 'in_progress', 'review', 'completed']

// 每个泳道包含:
// - 泳道头部（带颜色标识 + 计数）
// - 泳道内容区（可滚动任务卡片列表）
// - 任务卡片（标题、执行者、优先级、所属项目）
```

#### 10.3.3 任务详情 Modal

```javascript
// 点击任务卡片打开
openTaskDetail(todoId, projectId)

// Modal内容:
// - 基本信息（状态、优先级、项目、创建时间）
// - 工作总结（完成任务后显示）
// - 执行者信息
// - 完成时间（如果已完成）
```

### 10.4 Star Office 集成

#### 10.4.1 Phaser 游戏容器

```html
<div id="game-wrapper">
  <div id="loading-overlay">加载界面</div>
  <div id="game-container"></div>  <!-- Phaser 挂载点 -->
  <div id="memo-overlay">昨日小记</div>
</div>
```

#### 10.4.2 游戏配置

```javascript
// layout.js - 游戏布局配置
const LAYOUT = {
  game: { width: 1280, height: 720 },
  areas: {
    door: { x: 640, y: 550 },
    writing: { x: 320, y: 360 },
    breakroom: { x: 640, y: 360 }
  },
  // ...家具、装饰物坐标
}
```

#### 10.4.3 静态资源结构

```
templates/star_office/static/
├── game.js           # Phaser 游戏主逻辑
├── layout.js         # 布局配置
├── vendor/
│   └── phaser-3.80.1.min.js
├── office_bg_small.webp
├── cats-spritesheet.webp
├── desk-v3.webp
├── star-idle-v5.png
└── ... (其他资源)
```

### 10.5 时区处理

所有时间显示统一使用 **UTC+8** 时区：

```python
# nova_platform/utils/timetools.py
TZ_UTC8 = timezone(timedelta(hours=8))

def to_utc8(dt):
    """转换任意时区到 UTC+8"""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(TZ_UTC8)

def format_datetime(dt):
    """格式化为 UTC+8 字符串"""
    return to_utc8(dt).strftime('%Y-%m-%d %H:%M')
```

### 10.6 UI 样式系统

#### 10.6.1 颜色变量

```css
:root {
  --bg-primary: #0f1419;
  --bg-secondary: #1a2332;
  --bg-card: #232f3e;
  --text-primary: #f7f9fc;
  --text-secondary: #8b9db5;
  --accent-blue: #3b82f6;
  --accent-green: #10b981;
  --accent-amber: #f59e0b;
  --accent-purple: #8b5cf6;
}
```

#### 10.6.2 深色主题

- 深蓝灰色背景系
- 渐变装饰光晕
- 卡片悬停效果
- 脉冲动画指示器

### 10.7 数据同步

```python
# Nova Platform → Star Office 同步
@app.route('/api/sync-star-office', methods=['POST'])
def sync_star_office():
    # 遍历所有员工
    # 根据任务状态确定 agent 状态
    # 更新 agents-state.json
    return {"synced_agents": len(agents)}
```

---

## 11. 多层决策引擎架构 ⭐⭐

### 11.1 设计目标

实现智能化的项目决策系统，支持：
- 系统规则快速处理常规情况
- Leader Agent 处理复杂项目级决策
- 人类介入处理重大决策

### 11.2 三层决策架构

```
┌─────────────────────────────────────────────────────────┐
│                   决策引擎 (DecisionEngine)              │
├─────────────────────────────────────────────────────────┤
│                                                           │
│  第1层: 系统规则决策 (快速、确定)                         │
│  ✓ 任务阻塞自动重置（30分钟无响应）                        │
│  ✓ 唯一可执行任务自动分发                                │
│  ✓ 所有任务完成自动结束项目                              │
│  ✓ 阶段转换检查                                          │
│                                                           │
│  ↓ 不确定情况                                            │
│                                                           │
│  第2层: Leader决策（项目级、异步、防重）                  │
│  ✓ 构建完整项目上下文prompt                              │
│  ✓ 包含方法论、阶段、最佳实践                            │
│  ✓ 防重机制避免重复调用                                  │
│  ✓ 支持决策权限配置                                      │
│                                                           │
│  ↓ 需要人类决策                                          │
│                                                           │
│  第3层: 人类决策升级                                      │
│  ✓ 创建交互请求                                          │
│  ✓ 包含Leader建议和理由                                  │
│  ✓ 等待人类响应                                          │
│                                                           │
└─────────────────────────────────────────────────────────┘
```

### 11.3 核心组件

**Decision Engine (decision_engine.py)** - 多层决策引擎核心
**Leader Lock Service (leader_lock_service.py)** - 防重机制
**Human Interaction Service (human_interaction_service.py)** - 人类交互管理
**WBS Service (wbs_service.py)** - 任务拆解服务
**Task Dependency Service (task_dependency_service.py)** - 依赖图管理

### 11.4 WebUI人类交互界面

#### 11.4.1 交互管理界面

新增人类交互管理界面，集成在Web Dashboard中：

- **待处理交互列表** - 显示所有需要人类响应的交互
  - 交互ID、类型、问题内容
  - 项目上下文信息
  - 创建时间显示
  - 状态指示器（待处理/已回答/已跳过）

- **回答模态框** - 支持单个/批量回答
  - 文本输入框
  - 提交/跳过按钮
  - Leader建议显示
  - 理由说明展示

- **头部通知徽章** - 实时显示待处理数量
  - 红色圆点提示
  - 数字计数
  - 点击跳转到交互列表

- **自动刷新机制** - 每30秒更新状态
  - 后台轮询新交互
  - 无刷新更新UI
  - 声音提示（可选）

#### 11.4.2 交互流程

```
1. Leader决策需要人类介入
   ↓
2. Decision Engine创建HumanInteraction记录
   ↓
3. WebUI检测到新交互
   ↓
4. 头部徽章显示待处理数量
   ↓
5. 用户点击查看交互列表
   ↓
6. 打开回答模态框
   ↓
7. 用户输入回答或跳过
   ↓
8. 提交到 /api/interactions/<id>/answer
   ↓
9. HumanInteractionService处理回答
   ↓
10. 更新任务状态，继续执行
```

#### 11.4.3 API端点

| 端点 | 方法 | 功能 |
|------|------|------|
| `/api/interactions` | GET | 获取待处理交互列表 |
| `/api/interactions/<id>` | GET | 获取交互详情 |
| `/api/interactions/<id>/answer` | POST | 回答交互 |
| `/api/interactions/<id>/skip` | POST | 跳过交互 |
| `/api/projects/<id>/interactions-summary` | GET | 获取项目交互摘要 |

#### 11.4.4 数据模型

```python
class HumanInteraction(Base):
    """人类交互记录"""
    __tablename__ = "human_interactions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(36), nullable=False)
    interaction_type: Mapped[str] = mapped_column(String(50), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    context: Mapped[str] = mapped_column(Text, default="")
    leader_suggestion: Mapped[str] = mapped_column(Text, default="")
    leader_reasoning: Mapped[str] = mapped_column(Text, default="")
    answer: Mapped[str] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    answered_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
```

---

## 12. 数据库连接池优化 ⭐⭐

### 12.1 问题诊断

**错误**: `QueuePool limit of size 5 overflow 10 reached`

**根本原因**:
- 连接池配置过小
- Session未正确关闭导致连接泄漏
- 缺乏线程安全保护

### 12.2 修复方案

**数据库配置优化**:
```python
engine = create_engine(
    f"sqlite:///{DB_PATH}",
    echo=False,
    connect_args={
        "check_same_thread": False,
        "timeout": 30,
    },
    pool_pre_ping=True,
)
SessionLocal = scoped_session(sessionmaker(...))
```

**自动Session管理**:
```python
@contextmanager
def get_db_session():
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
```

**Flask自动管理**:
```python
@app.before_request
def before_request():
    g.db_session = get_db_session().__enter__()

@app.teardown_request
def teardown_request(exception=None):
    if hasattr(g, 'db_session'):
        g.db_session.__exit__(None, None, None)
```

### 12.3 预防措施

- ✅ 所有服务使用上下文管理器
- ✅ Flask自动管理请求session
- ✅ 连接有效性检查
- ✅ 线程安全保护

---

**维护者**: nova-platform team
**最后更新**: 2026-04-18
**文档版本**: v2.1