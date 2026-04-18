# Agent 进程管理与交互设计

## 1. 概述

本文档描述 Nova Platform 中 Agent 进程管理和交互式 I/O 的技术设计。

**核心目标**:
1. 支持长期运行的 Agent 进程（非一次性任务）
2. 同一项目同一 Agent 复用会话（保持对话上下文）
3. 支持 Agent 交互式输入/输出
4. Leader Agent 协助处理 Agent 的输入请求

## 2. 架构图

```
┌─────────────────────────────────────────────────────────────┐
│                      Automation Cycle                        │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  1. check_progress - 检查进行中的任务                   │  │
│  │  2. leader_decide - Leader 决策下一步行动              │  │
│  │  3. leader_execute - 执行 Leader 决定的计划             │  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│              Agent Process Service                          │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  _running_processes: Dict[session_id, ProcessInfo]    │  │
│  │  - process: Popen                                     │  │
│  │  - agent_id, project_id, agent_type                   │  │
│  │  - output_queue, output_file                          │  │
│  │  - started_at, last_activity                          │  │
│  └───────────────────────────────────────────────────────┘  │
│                                                              │
│  get_or_create_process() → 复用或创建进程                    │
│  get_process_status() → 检查进程状态                          │
│  read_process_output() → 读取输出                            │
│  is_process_waiting_for_input() → 检测等待输入               │
│  send_input_to_process() → 发送输入                          │
└─────────────────────────────────────────────────────────────┘
                            │
                    ┌───────┴───────┐
                    ▼               ▼
┌───────────────────────┐   ┌───────────────────────┐
│   Mailbox Service     │   │   Agent Session       │
│                       │   │   Service             │
│  AgentMailbox         │   │                       │
│  - messages[]         │   │  get_project_session  │
│  - state              │   │  prepare_*_session    │
│  - 交互历史            │   │  会话目录管理          │
│                       │   │                       │
│  consult_leader()     │   │  会话隔离              │
│  handle_waiting()     │   │  输出文件管理          │
└───────────────────────┘   └───────────────────────┘
            │
            ▼
┌─────────────────────────────────────────────────────────────┐
│                        Agent 进程                            │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  $ openclaw agent --agent <id> --message <task>        │  │
│  │  $ hermes --profile <name> chat -q <task>             │  │
│  │  $ claude -p <task>                                    │  │
│  └───────────────────────────────────────────────────────┘  │
│          │                    │                    │          │
│          ▼                    ▼                    ▼          │
│     stdout/stdin         stdout/stdin        stdout/stdin     │
│          │                    │                    │          │
└──────────┴────────────────────┴────────────────────┴─────────┘
           (写入输出文件，等待 stdin 输入)
```

## 3. 会话 ID 规则

### 3.1 格式

```
session_id = "{project_id}#{agent_id}"
```

### 3.2 示例

| 项目 ID | Agent ID | Session ID |
|---------|----------|------------|
| proj-123 | openclaw-dev | `proj-123#openclaw-dev` |
| proj-123 | hermes-coder | `proj-123#hermes-coder` |
| proj-456 | openclaw-dev | `proj-456#openclaw-dev` |

**关键**: 同一项目同一 agent 使用同一 session_id，确保会话复用。

## 4. 进程生命周期

### 4.1 状态转换

```
pending → in_progress (dispatch)
    │
    ├─→ running (进程正常执行)
    │       │
    │       ├─→ waiting_input (需要输入) → running (收到输入)
    │       │
    │       ├─→ completed (成功完成)
    │       │
    │       ├─→ failed (失败)
    │       │
    │       └─→ stale (超时无活动) → terminated
    │
    └─→ pending (重置重试)
```

### 4.2 创建/复用流程

```
get_or_create_process(project_id, employee, task)
    │
    ├─→ 计算 session_id = f"{project_id}#{agent_id}"
    │
    ├─→ 检查 _running_processes[session_id]
    │       │
    │       ├─→ 存在且 poll() == None (运行中)
    │       │       └─→ 复用进程，返回
    │       │
    │       └─→ 不存在或已结束
    │               └─→ 创建新进程
    │                       ├─→ 准备会话目录
    │                       ├─→ 构建命令行
    │                       ├─→ 创建子进程 (Popen)
    │                       ├─→ 存储到 _running_processes
    │                       └─→ 返回进程和 session_id
```

## 5. 交互式 I/O 处理

### 5.1 等待输入检测

通过检查输出文件的最后几行，检测特征模式：

```python
WAITING_PATTERNS = [
    ">>>",      # Python 提示符
    "$ ",       # Shell 提示符
    "? ",       # 通用提示
    "Input:",   # 明确提示
    "Enter:",
    "Continue?",
    "(y/n)",
    "[Y/n]",
    "[y/N]"
]

def is_process_waiting_for_input(session_id):
    output = read_process_output(session_id)
    for pattern in WAITING_PATTERNS:
        if pattern in output and output.rstrip().endswith(pattern[:5]):
            return True
    return False
```

### 5.2 Mailbox 交互流程

```
1. monitor_agent_output(session_id)
   ├─→ 读取进程输出
   ├─→ 检测状态 (running/waiting/completed/failed)
   └─→ 更新 AgentMailbox

2. is_process_waiting_for_input(session_id) == True
   │
3. handle_agent_waiting(session, session_id, project_id)
   ├─→ 读取 agent 输出
   ├─→ consult_leader(session, project_id, output)
   │       │
   │       └─→ dispatch_task to leader
   │               ├─→ 提供上下文 (agent 输出 + 交互历史)
   │               └─→ 请求决策 (continue/terminate/retry/wait)
   │
   └─→ 执行 leader 决策
       ├─→ continue: send_input_to_process(input)
       ├─→ terminate: terminate_process(session_id)
       ├─→ retry: terminate + 标记重试
       └─→ wait: 等待更多信息
```

### 5.3 Leader 咨询 Prompt

```
Agent {agent_session_id} 需要处理：

Agent 输出：
{agent_output[:1000]}

{context}  # 包含最近的交互历史

请分析并决定如何处理：

选项：
1. continue - 提供输入让 agent 继续（在 input 字段中输入内容）
2. terminate - 终止 agent 任务
3. retry - 重试当前任务
4. wait - 等待更多信息

请以 JSON 格式回复：
{"action": "continue|terminate|retry|wait", "input": "输入内容", "notes": "说明"}
```

## 6. 输出文件管理

### 6.1 文件位置

```
~/.nova/workspaces/<project_id>/.nova/sessions/
├── openclaw_<agent_id>/
│   └── task_YYYYMMDD_HHMMSS.output
├── hermes_<agent_id>/
│   └── task_YYYYMMDD_HHMMSS.output
└── claude_<agent_id>/
    └── .claude/task_YYYYMMDD_HHMMSS.output
```

### 6.2 读取策略

```python
# 只读取最后的 N 字节，避免读取大量历史数据
def read_process_output(session_id, max_bytes=8192):
    output_file = _running_processes[session_id]["output_file"]
    with open(output_file, "r") as f:
        f.seek(0, 2)      # 移到末尾
        size = f.tell()
        f.seek(max(0, size - max_bytes))
        return f.read()
```

## 7. 进程清理

### 7.1 自动清理条件

1. 进程自然结束 (poll() != None)
2. 活动超时 (last_activity > 10 分钟无新输出)
3. 项目被删除或归档
4. 手动终止

### 7.2 清理操作

```python
# 优雅终止
terminate_process(session_id, force=False)
    └─→ SIGTERM → wait(5s) → SIGKILL (如果需要)

# 强制终止
terminate_process(session_id, force=True)
    └─→ SIGKILL → kill entire process group

# 项目级清理
cleanup_project_processes(project_id)
    └─→ 终止该项目的所有 agent 进程
```

## 8. Todo 记录更新

### 8.1 字段映射

```python
# Todo 模型
todo.process_id = proc.pid           # 进程 PID
todo.session_id = session_id         # 会话 ID
todo.status = "in_progress"          # 状态
todo.agent_task_id = session_id      # 兼容性字段
```

### 8.2 状态同步

```
automation 循环每 N 秒检查一次：
    │
    ├─→ get_process_status(todo.session_id)
    │       │
    │       ├─→ running → 继续
    │       ├─→ waiting → 触发 mailbox 处理
    │       ├─→ completed → todo.status = "completed"
    │       └─→ failed → todo.status = "pending" (重试)
    │
    └─→ 更新 todo.updated_at
```

## 9. 错误处理

### 9.1 进程创建失败

```python
if not proc:
    todo.status = "pending"
    todo.assignee_id = None
    todo.error = "Failed to create agent process"
```

### 9.2 进程意外终止

```python
if proc_status["returncode"] != 0:
    # 检查是否有输出
    if has_output:
        # 有输出但非 0 返回码，部分完成
        todo.status = "completed"
    else:
        # 无输出，完全失败
        todo.status = "pending"
        todo.assignee_id = None
```

### 9.3 Leader 咨询失败

```python
if not leader_available:
    # 默认策略：终止并标记失败
    terminate_process(session_id)
    todo.status = "pending"
    todo.error = "Leader unavailable for consultation"
```

## 10. 性能考虑

### 10.1 内存管理

- `_running_processes` 只存储元数据，不存储完整输出
- 输出文件按需读取，只读取最后 N 字节
- 定期清理已结束进程的记录

### 10.2 并发控制

- 使用 `threading.RLock()` 保护进程字典
- 每个进程在独立线程中运行
- 输出读取使用非阻塞 I/O

### 10.3 资源限制

| 限制 | 值 | 说明 |
|------|---|------|
| 最大并发进程 | 50 | ThreadPoolExecutor max_workers |
| 输出读取大小 | 8KB | 每次 read_process_output |
| 交互历史条数 | 50 | AgentMailbox 保留 |
| 活动超时 | 600s | 10 分钟无活动视为 stale |
| 进程总超时 | 1800s | 30 分钟强制终止 |

## 11. 安全考虑

### 11.1 进程隔离

- 每个项目独立的会话目录
- 使用 `os.setsid()` 创建进程组
- 终止时杀掉整个进程组

### 11.2 输入验证

```python
# 过滤危险输入
def sanitize_input(text: str) -> str:
    # 移除控制字符
    return ''.join(c for c in text if c.isprintable() or c in '\n\r\t')
```

### 11.3 权限控制

- Agent 只能访问项目工作空间目录
- 通过 `cwd=` 限制工作目录
- 环境变量隔离 (HOME 指向会话目录)

## 12. 监控和调试

### 12.1 日志记录

```python
# 进程创建
log.info(f"Created agent process: session_id={session_id}, pid={proc.pid}")

# 状态变化
log.info(f"Agent state changed: {session_id} {old_state} → {new_state}")

# 交互事件
log.info(f"Agent input/output: {session_id} waiting={waiting}")
```

### 12.2 调试命令

```bash
# 查看运行中的进程
nova-cli agent processes list

# 查看特定会话状态
nova-cli agent sessions show <session_id>

# 查看进程输出
nova-cli agent processes output <session_id>

# 终止进程
nova-cli agent processes terminate <session_id>
```

### 12.3 状态导出

```python
def export_process_status() -> dict:
    return {
        "running_processes": len(_running_processes),
        "by_project": group_by_project(_running_processes),
        "by_agent_type": group_by_type(_running_processes),
        "stale_processes": count_stale(_running_processes)
    }
```

---

**文档版本**: 1.0
**最后更新**: 2026-04-18
**作者**: Nova Platform Team
