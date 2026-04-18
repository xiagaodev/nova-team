# Nova Platform 前端整合需求文档

## 项目背景

当前存在两个独立的前端界面：

| 界面 | 路径 | 技术风格 | 功能 |
|------|------|----------|------|
| **Dashboard** | `/` | 现代深色卡片 UI (Inter/JetBrains 字体) | 项目管理、员工统计、TODO 任务 |
| **Star Office** | `/office/` | 像素风格游戏 (Phaser 引擎) | AI Agent 状态可视化、虚拟办公室 |

## 整合目标

1. **统一入口**: 访问 `/` 展示整合后的主界面
2. **界面融合**: 将 Dashboard 的管理功能与 Star Office 的可视化融合
3. **功能保留**: 两个原有界面的功能模块都要保留
4. **无缝切换**: 在整合界面内可以切换不同的视图/面板

## 整合方案

### 推荐方案：Dashboard 内嵌 Office 视图

在 Dashboard 顶部导航添加 "虚拟办公室" 入口，点击后在主内容区加载 Star Office 的像素办公室视图（iframe 或组件化），同时保留 Dashboard 的其他功能标签页。

### 页面结构

```
/ (整合后的主界面)
├── 顶部导航栏
│   ├── Logo + 标题
│   ├── 视图切换: [看板] [虚拟办公室]
│   └── 右侧: 刷新按钮、状态指示
│
├── 视图1: 看板视图 (默认)
│   ├── 统计卡片区 (4列: 项目数/员工数/TODO/AI Agent)
│   ├── 项目卡片网格
│   │   ├── 项目进度条
│   │   ├── 任务统计
│   │   └── 成员头像
│   └── 任务列表
│
└── 视图2: 虚拟办公室视图
    ├── 像素办公室游戏画面 (Phaser)
    └── 右侧抽屉: 资产面板
```

### 技术要求

1. **路由设计**
   - `/` → 渲染整合后的 `index.html`（新）
   - `/office/` → 保留 Star Office Blueprint（独立运行）
   - `/api/*` → 保持现有 API 不变

2. **静态资源**
   - 共享 `/static/` 路径（Flask 已配置）
   - Star Office 静态文件在 `templates/star_office/static/`
   - 整合后需要统一的 CSS/字体

3. **状态管理**
   - Dashboard 数据通过 `/api/stats`, `/api/projects`, `/api/employees` 获取
   - Star Office 状态通过 `/status`, `/agents`, `/set_state` 获取

4. **关键文件**
   - 新建 `templates/index.html` - 整合主界面
   - 修改 `app.py` - 根路径渲染新界面
   - 保留 `templates/dashboard.html` - 看板视图组件
   - 保留 `templates/star_office/` - Office 视图组件

### 实现步骤

1. 创建 `templates/index.html` 整合界面
   - 引入 Dashboard 的 CSS 变量和字体
   - 实现顶部导航和视图切换
   - 实现看板视图（可复用 dashboard.html 的结构和样式）
   - 实现虚拟办公室视图（加载 Star Office 游戏）

2. 修改 `app.py`
   - 根路径 `/` 渲染新的 `index.html`
   - 保留 `/office/` Blueprint

3. 确保 API 正常工作
   - `/api/stats` - 全局统计
   - `/api/projects` - 项目列表
   - `/api/employees` - 员工列表
   - `/status` - Star Office 状态
   - `/agents` - Star Office Agent 列表

### 验证清单

- [ ] 访问 `/` 显示整合后的主界面
- [ ] 顶部导航可以切换"看板"和"虚拟办公室"视图
- [ ] 看板视图显示统计卡片、项目列表、任务列表
- [ ] 虚拟办公室视图正确加载像素游戏
- [ ] 统计数据显示真实数据（从数据库）
- [ ] 移动端可正常使用（响应式）
- [ ] 页面加载无 404 错误
