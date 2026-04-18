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

## Server Daemon

Nova Platform 支持后台守护进程模式运行：

```bash
# 初始化配置文件
nova server config --init

# 启动服务
nova server start
nova server start --port 8080           # 指定端口
nova server start --debug               # 调试模式

# 管理服务
nova server stop                        # 停止
nova server restart                     # 重启
nova server status                      # 状态
nova server logs                        # 查看日志
nova server logs -f                     # 跟踪日志

# 查看当前配置
nova server config --show
```

### 配置文件

配置文件位于 `~/.nova-platform/config.yaml`，支持开发/生产环境切换：

```yaml
environment: development  # development | production
server:
  host: 0.0.0.0
  port: 5000
  debug: false           # 生产环境自动为 false
logging:
  level: INFO
  file: ~/.nova-platform/nova-server.log
database:
  path: ~/.nova-platform/nova.db
```

### Systemd 服务（生产环境）

```bash
# 安装为系统服务（需要 root）
sudo bash scripts/install-service.sh

# 管理服务
systemctl start nova-server
systemctl stop nova-server
systemctl status nova-server
journalctl -u nova-server -f
```

## Architecture

- **CLI**: Click framework
- **ORM**: SQLAlchemy 2.x
- **Database**: SQLite at `~/.nova-platform/nova.db`
- **Web UI**: Flask + 原生 JS/CSS（无框架依赖）
- **Star Office**: 独立蓝图，支持嵌入到其他 Flask 应用
