# Changelog

All notable changes to Nova Platform will be documented in this file.

## [2.2.0] - 2026-04-18

### Added

#### Web Dashboard重构 ⭐
- **🏢 办公室视图整合** - Star Office与统计概览合并为首个页签
- **✅ 四泳道任务看板** - 任务按状态分为四列（待处理/进行中/审核中/已完成）
- **📊 现代化UI设计** - 深色主题、卡片式布局、渐变效果
- **📋 任务详情Modal** - 点击任务查看详情和工作总结
- **🌐 UTC+8时区统一** - 所有时间显示使用UTC+8时区

#### 新增时间工具模块
- `nova_platform/utils/timetools.py` - 统一时区处理
  - `now()` - 获取当前UTC+8时间
  - `to_utc8()` - 转换任意时区到UTC+8
  - `format_datetime()` - 格式化时间为UTC+8字符串
  - `format_date()` - 格式化日期
  - 便捷时间计算函数（seconds_ago, minutes_ago, hours_ago, days_ago等）

#### Todo模型扩展
- `work_summary` - 工作总结字段
- `completed_at` - 完成时间字段

#### 新增API端点
- `/api/todo/<id>` - 获取任务详情（含工作总结）
- `/api/sync-star-office` - 同步Nova员工状态到Star Office

### Changed

#### 导航结构优化
- 页签从5个减少到4个
- 办公室与概览合并为"🏢 办公室"页签（首个）
- 调整页签顺序：办公室 → 项目 → 团队 → 任务

#### 任务看板重构
- 从垂直分组布局改为水平四泳道布局
- 每个泳道独立滚动
- 任务卡片优化：显示执行者、优先级、所属项目

#### Star Office集成
- 从iframe嵌套改为直接集成
- Phaser游戏直接挂载到主页面
- 优化加载界面和进度显示

### UI/UX改进

- **深色主题** - 深蓝灰色背景系
- **卡片设计** - 统一的卡片样式和悬停效果
- **渐变装饰** - 背景光晕动画
- **响应式布局** - 适配不同屏幕尺寸
- **实时刷新** - 每30秒自动更新数据
- **交互反馈** - 点击、悬停动画效果

### Fixed

- **OpenClaw Agent重复招募** - 相同agent_id只能招募一次
- **静态文件服务** - 修复STAR_OFFICE_STATIC路径问题
- **时间显示** - 统一使用UTC+8时区
- **视图切换** - 修复视图容器切换逻辑

### Documentation

- 更新: `README.md` - Web Dashboard功能说明
- 更新: `ARCHITECTURE.md` - 新增第10章Web Dashboard架构
- 更新: `CHANGELOG.md` - 添加2.2.0版本更新记录

---

## [2.1.0] - 2026-04-18

### Added

#### 多层决策引擎 (Phase 5)
- **DecisionEngine** - 三层决策架构
  - 第1层：系统规则决策（快速、确定）
  - 第2层：Leader决策（项目级、异步、防重）
  - 第3层：人类决策升级（重大决策）
- **Leader Lock Service** - Leader调用防重机制
- **支持决策类型**: dispatch_task, prioritize_tasks, transition_phase, escalate_to_human等

#### 任务依赖管理 (Phase 6)
- **Task Dependency Service** - 独立的任务依赖图服务
- **拓扑排序** - 确定任务执行顺序
- **可执行任务查询** - 考虑依赖关系的任务分发
- **WBS Service集成** - 动静结合的任务拆解

#### 人类交互界面 (Phase 7)
- **待处理交互列表** - 显示所有需要人类响应的交互
- **回答模态框** - 支持单个/批量回答
- **头部通知徽章** - 实时显示待处理数量
- **自动刷新机制** - 每30秒更新状态

#### 数据模型扩展
- `ProjectMethodology` - 项目方法论模板
- `HumanInteraction` - 人类交互记录
- `LeaderInvocationLock` - Leader调用防重锁
- `ProjectPhaseHistory` - 项目阶段历史

- **Project表新增字段**:
  - `methodology_id` - 关联方法论
  - `current_phase` - 当前阶段
  - `phase_history_id` - 阶段历史记录
  - `project_config` - 项目级配置覆盖

### Changed

#### automation_service重构
- 集成多层决策引擎
- 使用异步决策支持
- 优化观察数据收集
- 支持阶段转换逻辑

#### 数据库连接池优化
- **修复连接泄漏问题** - QueuePool耗尽错误
- 使用scoped_session确保线程安全
- 添加上下文管理器get_db_session()
- Flask自动session管理
- 优化连接池配置

#### 服务层更新
- monitor_service.py - 修复连接泄漏
- human_interaction_service.py - 修复监控循环泄漏
- 所有服务使用上下文管理器模式

### API端点新增

| 端点 | 方法 | 功能 |
|------|------|------|
| `/api/interactions` | GET | 获取待处理交互 |
| `/api/interactions/<id>` | GET | 获取交互详情 |
| `/api/interactions/<id>/answer` | POST | 回答交互 |
| `/api/interactions/<id>/skip` | POST | 跳过交互 |
| `/api/projects/<id>/interactions-summary` | GET | 交互摘要 |

### Fixed

- **数据库连接池耗尽** - QueuePool limit错误
- **Session连接泄漏** - 多处未正确关闭session
- **线程安全问题** - 使用scoped_session
- **循环依赖问题** - 创建task_dependency_service独立模块

### Documentation

- 新增: `docs/DATABASE_CONNECTION_POOL_FIX.md`
- 更新: `ARCHITECTURE.md` - 多层决策引擎架构
- 更新: `docs/IMPLEMENTATION_SUMMARY.md` - Phase 5、6、7完成状态
- 更新: `README.md` - 最新功能说明

---

## [2.0.0] - 2026-04-18

### Added

#### Agent进程管理系统
- **Agent Process Service** - Agent进程生命周期管理
- **Agent Session Service** - 会话目录和上下文管理
- **Mailbox Service** - Agent交互式I/O处理

#### Todo模型扩展
- `process_id` - Agent进程PID
- `session_id` - 会话ID（project_id#agent_id）

#### Star Office可视化看板
- Phaser 3游戏引擎实现
- 实时Agent状态显示
- 状态切换功能
- 昨日Memo功能

### Changed

#### 任务状态检查机制
- 支持基于session_id的进程状态查询
- 自动检测Agent等待输入状态
- 进程卡住检测和恢复

#### CLI增强
- 守护进程模式支持
- 配置文件管理
- Systemd服务集成

### Fixed

- P0修复：OKR模型、任务状态服务、跨平台支持

---

## [1.0.0] - Earlier

### Initial Features

- 项目管理（创建、查看、更新、删除）
- 员工管理（添加、列表、分配）
- TODO管理（添加、列表、更新、删除）
- 知识库管理（添加、搜索、查看）
- 基础Web Dashboard

---

## 版本规则

- **Major.Minor.Patch** (例如: 2.1.0)
- **Major**: 重大架构变更
- **Minor**: 新功能添加
- **Patch**: Bug修复和小改进

---

**维护者**: nova-platform team
**最后更新**: 2026-04-18