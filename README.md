# Nova Platform

AI collaboration platform for multi-project management with human and AI agents.

## Quick Start

```bash
pip install -e .
nova --help
```

## Commands

### Project
```bash
nova project create <name> --description "..." --template software_dev
nova project list
nova project view <id>
nova project update <id> --status active
nova project delete <id>
```

### Employee
```bash
nova employee add <name> --type human --role developer --skills "python,javascript"
nova employee list
nova employee view <id>
nova employee assign <employee_id> --project <project_id>
```

### TODO
```bash
nova todo add "Task" --project <id> --assign <employee_id> --priority high
nova todo list --project <id>
nova todo list --assign <employee_id>
nova todo update <todo_id> --status completed
nova todo delete <todo_id>
```

### Knowledge
```bash
nova knowledge add --project <id> --title "Title" --content "..." --tags "python"
nova knowledge list --project <id>
nova knowledge search "query"
nova knowledge view <id>
```

### Status
```bash
nova status
nova report --project <id>
```

## Star Office 可视化看板

Web 界面地址：`http://localhost:5000/office/`

### 功能

- **Agent 状态看板** — 实时显示各 Agent 在线状态、所在区域、角色信息
- **状态切换** — 点击 Agent 卡片可切换其状态（空闲/工作中/休息/离线）
- **昨日 Memo** — 每日工作记录和总结
- **响应式设计** — 支持桌面和移动端访问

### API 端点

| 端点 | 方法 | 描述 |
|------|------|------|
| `/status` | GET | 获取系统状态 |
| `/agents` | GET | 获取所有 Agent 列表 |
| `/set_state` | POST | 更新 Agent 状态 |
| `/yesterday-memo` | GET | 获取昨日工作记录 |

## Architecture

- **CLI**: Click framework
- **ORM**: SQLAlchemy 2.x
- **Database**: SQLite at `~/.nova-platform/nova.db`
- **Web UI**: Flask + 原生 JS/CSS（无框架依赖）
- **Star Office**: 独立蓝图，支持嵌入到其他 Flask 应用
