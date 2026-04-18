# Agent 进程管理与交互实现总结

## 实现日期
2026-04-18

## 需求背景

原有的 Agent 调用存在以下问题：
1. **一次性任务**：每次调用创建新进程，无法保持对话上下文
2. **无法交互**：不支持 Agent 请求用户输入的场景
3. **状态检查不准确**：只能检查进程是否存在，无法检测输出和等待状态

## 解决方案

### 核心设计

1. **会话复用**：同一项目同一 Agent 使用同一进程和会话
2. **进程持久化**：存储进程对象和 PID，便于后续交互
3. **输出监控**：实时读取进程输出，检测等待输入状态
4. **Leader 协作**：Agent 需要输入时，咨询 Leader Agent 进行决策

## 实现内容

### 1. 数据库模型更新

**文件**: `nova_platform/models.py`

```python
class Todo(Base):
    # ...原有字段...
    process_id: Mapped[int]      # 新增：Agent 进程 PID
    session_id: Mapped[str]      # 新增：会话 ID (project_id#agent_id)
```

**迁移脚本**: `nova_platform/migrations/add_todo_process_fields.py`

### 2. Agent 进程管理服务

**文件**: `nova_platform/services/agent_process_service.py`

**核心功能**:
- `get_or_create_process()` - 获取或创建进程（自动复用）
- `get_process_status()` - 检查进程状态
- `read_process_output()` - 读取进程输出
- `is_process_waiting_for_input()` - 检测是否等待输入
- `send_input_to_process()` - 向进程发送输入
- `terminate_process()` - 终止进程
- `cleanup_project_processes()` - 清理项目所有进程

**会话 ID 规则**: `{project_id}#{agent_id}`

### 3. Mailbox 服务（交互处理）

**文件**: `nova_platform/services/mailbox_service.py`

**核心功能**:
- `monitor_agent_output()` - 监听 Agent 输出并检测状态
- `consult_leader()` - 咨询 Leader 如何处理
- `handle_agent_waiting()` - 处理 Agent 等待输入
- `run_interaction_loop()` - 运行交互循环

**Agent 状态枚举**:
```python
class AgentState(Enum):
    RUNNING = "running"
    WAITING_INPUT = "waiting"
    COMPLETED = "completed"
    FAILED = "failed"
    IDLE = "idle"
```

### 4. Agent Service 更新

**文件**: `nova_platform/services/agent_service.py`

**更新内容**:
- 新增 `dispatch_task_async_with_todo()` - 更新 Todo 的 process_id 和 session_id
- 更新 `dispatch_task_async()` - 集成进程管理服务
- 更新 `_run_agent_async()` - 使用新的进程管理

### 5. Automation Service 更新

**文件**: `nova_platform/services/automation_service.py`

**更新内容**:
- 优先使用 `todo.session_id` 进行状态检查
- 检测 `WAITING_INPUT` 状态并触发 mailbox 处理
- 支持基于活动时间的 stale 检测
- 向后兼容旧的 `agent_task_id` 方式

## 调用流程

### 任务分发流程

```
1. Todo 创建
   ↓
2. dispatch_task_async(employee_id, task, project_id, todo_id)
   ↓
3. agent_process_service.get_or_create_process()
   - 计算 session_id = f"{project_id}#{agent_id}"
   - 检查是否已有运行中的进程
   - 有 → 复用，无 → 创建新进程
   ↓
4. 更新 Todo: process_id, session_id, status=in_progress
   ↓
5. 返回: {"success": True, "process_id": pid, "session_id": session_id}
```

### 状态检查流程

```
automation 循环
   ↓
1. 获取所有 in_progress 的 Todo
   ↓
2. 对每个 Todo:
   - 如果有 session_id:
     - agent_process_service.get_process_status(session_id)
     - 检测状态 (running/waiting/completed/failed)
     - 如果 waiting_input:
       - mailbox_service.handle_agent_waiting()
       - 咨询 leader
       - 发送输入或终止
   - 否则回退到旧方式
   ↓
3. 更新 Todo 状态
```

### 交互处理流程

```
1. 检测到 Agent 等待输入
   ↓
2. 读取 Agent 输出内容
   ↓
3. 构建咨询 Prompt (包含输出和交互历史)
   ↓
4. 调用 Leader Agent
   ↓
5. 解析 Leader 决策:
   - continue → send_input_to_process(input)
   - terminate → terminate_process(session_id)
   - retry → 终止并重试
   - wait → 等待更多信息
   ↓
6. 更新 AgentMailbox 状态
```

## 目录结构

### 会话目录

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

## 配置参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| max_workers | 10 | 最大并发线程数 |
| max_output_read | 8192 | 最大读取字节数 |
| stale_timeout | 600s | 活动超时时间 |
| process_timeout | 1800s | 进程总超时 |
| max_history | 50 | 最大交互历史条数 |

## 兼容性

- **向后兼容**: 保留旧的 `agent_task_id` 检查方式
- **渐进迁移**: 新任务使用 `session_id`，旧任务继续使用 `agent_task_id`

## 测试要点

1. **会话复用**: 同一项目同一 agent 使用同一进程
2. **状态检测**: 正确检测 running/waiting/completed/failed
3. **交互处理**: Agent 等待输入时正确触发 Leader 咨询
4. **进程清理**: 进程结束或超时时正确清理
5. **并发安全**: 多线程访问进程字典的安全性

## 后续优化

1. **持久化存储**: 将进程状态存储到数据库，重启后恢复
2. **WebSocket 推送**: 实时推送 Agent 输出到前端
3. **更智能的 Leader**: 支持更复杂的交互决策
4. **进程池管理**: 限制单个项目的最大进程数

## 相关文档

- `ARCHITECTURE.md` - 整体架构文档
- `docs/AGENT_PROCESS_DESIGN.md` - 详细技术设计

---

**实现者**: Nova Platform Team
**审核状态**: 待审核
**版本**: 1.0
