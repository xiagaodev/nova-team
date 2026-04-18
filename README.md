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

## Web Dashboard

Web 界面地址：`http://localhost:5000/`

### 功能特性

- **🏢 办公室视图** — Star Office 虚拟办公室可视化
  - 实时显示各 Agent 在线状态、所在区域、角色信息
  - Phaser 3 像素风格游戏引擎驱动
  - Agent 状态切换（空闲/工作中/休息/离线）
  - 昨日 Memo 工作记录

- **📊 统计概览** — 项目整体数据可视化
  - 项目、员工、任务总数统计
  - 任务状态分布（待处理/进行中/已完成）
  - 人类员工 vs AI Agent 比例

- **📁 项目管理** — 项目卡片视图
  - 项目进度条和完成度
  - 项目成员展示
  - 任务统计和最近任务预览
  - 点击任务查看详情

- **🤖 团队管理** — 员工列表
  - 人类员工和 AI Agent 分类
  - 角色和技能展示
  - 任务分配统计

- **✅ 任务看板** — 四泳道看板布局
  - 待处理、进行中、审核中、已完成四列
  - 任务卡片显示执行者、优先级、所属项目
  - 点击任务查看详情和工作总结
  - 拖拽式看板界面

### API 端点

| 端点 | 方法 | 描述 |
|------|------|------|
| `/api/stats` | GET | 获取全局统计数据 |
| `/api/projects` | GET | 获取所有项目及详情 |
| `/api/employees` | GET | 获取所有员工 |
| `/api/project/<id>` | GET | 获取单个项目详情 |
| `/api/todo/<id>` | GET | 获取任务详情（含工作总结） |
| `/api/sync-star-office` | POST | 同步 Nova 到 Star Office |
| `/status` | GET | 获取 Star Office 状态 |
| `/agents` | GET | 获取所有 Agent 列表 |
| `/set_state` | POST | 更新 Agent 状态 |
| `/yesterday-memo` | GET | 获取昨日工作记录 |

### 时区处理

所有时间显示均使用 **UTC+8** 时区，确保时间一致性。

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
- **Star Office**: Phaser 3 游戏引擎，直接集成到主页面
- **时区**: 统一使用 UTC+8 时区处理

## 最新功能 ⭐

### Web Dashboard 2.0
- **🏢 办公室视图** - Star Office + 统计概览整合
- **✅ 四泳道看板** - 待处理/进行中/审核中/已完成
- **📊 现代化UI** - 深色主题、卡片式布局、渐变效果
- **📋 任务详情** - 点击查看工作总结和完成时间
- **🌐 UTC+8时区** - 统一时区处理

### 多层决策引擎
- **第1层**: 系统规则决策（快速、确定）
- **第2层**: Leader决策（项目级、异步、防重）
- **第3层**: 人类决策升级（重大决策）

### 人类交互界面
- 待处理交互列表
- 回答模态框
- 头部通知徽章
- 自动刷新机制

### WBS任务拆解
- 增量式拆解（边拆解边执行）
- 任务依赖关系支持
- 需求澄清机制
- 方法论驱动（敏捷Scrum、内容运营）

## 技术文档

- **[架构文档](ARCHITECTURE.md)** - 系统架构和设计
- **[实施总结](docs/IMPLEMENTATION_SUMMARY.md)** - 功能实施进度
- **[数据库连接池修复](docs/DATABASE_CONNECTION_POOL_FIX.md)** - 问题诊断和修复方案
- **[Agent自动化设计](docs/AGENTS_AUTOMATION_DESIGN.md)** - AI Agent自动化系统设计
- **[Agent进程设计](docs/AGENT_PROCESS_DESIGN.md)** - Agent进程管理设计

## 开发状态

- ✅ **Phase 5**: 多层决策引擎
- ✅ **Phase 6**: 集成到automation_service循环
- ✅ **Phase 7**: WebUI人类交互界面
- ✅ **Phase 8**: Web Dashboard重构（办公室整合、四泳道看板）
- ✅ **数据库连接池优化**: 修复连接泄漏问题
- ✅ **时区处理**: 统一使用UTC+8时区

## License

MIT
