# Nova Platform 项目上下文

## 项目概述
Nova Platform 是一个团队管理平台，包含：
- **Dashboard** (`/`) - 现代深色卡片风格的项目管理界面
- **Star Office** (`/office/`) - 像素风格的 AI Agent 虚拟办公室可视化

## 技术栈
- Flask Web 框架
- SQLAlchemy ORM + SQLite
- Phaser 3 游戏引擎（Star Office）
- Inter/JetBrains Mono 字体（Dashboard）
- ArkPixel 像素字体（Star Office）

## 关键文件
- `app.py` - Flask 主应用，包含路由和 API
- `templates/dashboard.html` - Dashboard 界面
- `templates/star_office/static/index.html` - Star Office 主界面
- `templates/star_office/static/game.js` - Phaser 游戏逻辑
- `nova_platform/star_office.py` - Star Office 后端逻辑

## API 端点
- `GET /api/stats` - 全局统计
- `GET /api/projects` - 项目列表
- `GET /api/employees` - 员工列表
- `GET /status` - Star Office 状态
- `GET /agents` - Star Office Agent 列表
- `POST /set_state` - 设置状态
- `POST /api/sync-star-office` - 同步 Nova 到 Star Office

## 当前任务
将 Dashboard 和 Star Office 前端整合到单一入口 `/`，实现视图切换。
