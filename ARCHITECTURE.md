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
| `openclaw` | `openclaw sessions_spawn` | ✅ |
| `hermes` | `hermes chat -q` | ✅ |
| `claude_code` | `claude --print` | ✅ |
| `codex` | `acpx openclaw exec` | ✅ |
| `openai` | API 调用 | 🔜 |
| `anthropic` | API 调用 | 🔜 |

### 4.2 类图

```
AgentType (Enum)
   │
   ▼
BaseAgent (ABC)
   ├── type: AgentType
   ├── config: AgentConfig
   ├── execute(prompt) -> AgentResult
   └── is_available() -> bool
   │
   ├─── OpenClawAgent
   ├─── HermesAgent
   ├─── ClaudeCodeAgent
   └─── CodexAgent

AgentFactory
   ├── create(config) -> BaseAgent
   ├── register(type, class)
   └── available_agents() -> list
```

### 4.3 使用示例

```python
from nova_platform.agents import AgentType, AgentFactory, AgentConfig

# 创建智能体
config = AgentConfig(
    agent_type=AgentType.HERMES,
    name="dev-agent",
    working_dir="/path/to/project"
)
agent = AgentFactory.create(config)

# 执行任务
if agent.is_available():
    result = agent.execute("写一个用户认证模块")
```

### 4.4 扩展新智能体

```python
# 在 implementations.py 添加
class CustomAgent(BaseAgent):
    @property
    def type(self) -> AgentType:
        return AgentType.CUSTOM
    
    def is_available(self) -> bool:
        return shutil.which("custom-cli") is not None
    
    def execute(self, prompt: str) -> AgentResult:
        # 实现逻辑
        pass

# 注册
AGENT_REGISTRY[AgentType.CUSTOM] = CustomAgent
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