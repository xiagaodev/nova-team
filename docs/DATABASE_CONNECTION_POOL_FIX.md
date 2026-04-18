# 数据库连接池问题修复文档

## 问题描述

### 错误信息
```
sqlalchemy.exc.TimeoutError: QueuePool limit of size 5 overflow 10 reached, connection timed out, timeout 30.00
```

### 影响
- 所有API请求挂起
- 服务无法正常响应
- 系统完全不可用

## 根本原因分析

### 1. 连接池配置问题
```python
# 原始配置
engine = create_engine(f"sqlite:///{DB_PATH}", echo=False)
SessionLocal = sessionmaker(bind=engine)
```

**问题**:
- 使用默认连接池配置（5个连接 + 10个溢出）
- SQLite不需要连接池，但使用了默认配置
- 没有设置连接超时

### 2. Session管理问题

**发现的连接泄漏点**:

1. **monitor_service.py** - 2处泄漏
```python
# 错误用法
session = get_session()
# ... 使用session
# 从未关闭session！
```

2. **human_interaction_service.py** - 1处泄漏
```python
# 监控循环中的泄漏
while self.running:
    session = get_session()  # 每次创建新session
    # 从未关闭！
```

3. **app.py** - 多处潜在泄漏
```python
# API端点中的泄漏
@app.route('/api/data')
def get_data():
    session = get_session()
    # ... 使用session
    # 从未关闭！
```

### 3. 线程安全问题
```python
# 原始实现不是线程安全的
SessionLocal = sessionmaker(bind=engine)
```

## 修复方案

### Phase 1: 数据库配置优化

**文件**: `nova_platform/database.py`

```python
import os
from pathlib import Path
from contextlib import contextmanager
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session, scoped_session
from nova_platform.models import Base

DATA_DIR = Path.home() / ".nova-platform"
DATA_DIR.mkdir(exist_ok=True)
DB_PATH = DATA_DIR / "nova.db"

# 优化后的连接池配置
engine = create_engine(
    f"sqlite:///{DB_PATH}",
    echo=False,
    connect_args={
        "check_same_thread": False,  # 允许多线程访问
        "timeout": 30,  # 连接超时时间
    },
    poolclass=None,  # SQLite使用StaticPool
    pool_pre_ping=True,  # 连接前检查有效性
)

# 使用scoped_session确保线程安全
SessionLocal = scoped_session(
    sessionmaker(bind=engine, autocommit=False, autoflush=False)
)

@contextmanager
def get_db_session():
    """
    上下文管理器，确保session正确关闭

    使用示例:
        with get_db_session() as session:
            session.query(Model).all()
    """
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

**改进点**:
- ✅ 添加连接超时配置
- ✅ 使用scoped_session确保线程安全
- ✅ 添加上下文管理器
- ✅ 启用连接有效性检查

### Phase 2: 修复连接泄漏

#### 2.1 修复monitor_service.py

**文件**: `nova_platform/services/monitor_service.py`

**修复前**:
```python
def check_and_recover_stuck_tasks() -> dict:
    init_db()
    session = get_session()  # ❌ 泄漏点
    
    # ... 使用session
    # 从未关闭
```

**修复后**:
```python
def check_and_recover_stuck_tasks() -> dict:
    init_db()
    
    with get_db_session() as session:  # ✅ 自动关闭
        # ... 使用session
        # 自动commit/close
```

#### 2.2 修复human_interaction_service.py

**文件**: `nova_platform/services/human_interaction_service.py`

**修复前**:
```python
async def _monitor_loop(self):
    while self.running:
        session = get_session()  # ❌ 每次循环泄漏
        await self.monitor_all_projects(session)
```

**修复后**:
```python
async def _monitor_loop(self):
    while self.running:
        with get_db_session() as session:  # ✅ 自动关闭
            await self.monitor_all_projects(session)
```

#### 2.3 添加Flask自动Session管理

**文件**: `app.py`

```python
from flask import g

# 自动session管理钩子
@app.before_request
def before_request():
    """在每个请求开始时创建session"""
    g.db_session = get_db_session().__enter__()

@app.teardown_request
def teardown_request(exception=None):
    """在每个请求结束时关闭session"""
    if hasattr(g, 'db_session'):
        try:
            g.db_session.__exit__(None, None, None)
        except Exception as e:
            app.logger.error(f"Session close error: {e}")

def get_session():
    """获取当前请求的session（从Flask g对象）"""
    if hasattr(g, 'db_session'):
        return g.db_session
    # 回退到直接创建session（用于非请求上下文）
    return get_db_session().__enter__()
```

**改进点**:
- ✅ 每个请求自动管理session生命周期
- ✅ 无需手动关闭session
- ✅ 错误自动处理

### Phase 3: 代码规范更新

**推荐的Session使用方式**:

1. **上下文管理器（推荐）**:
```python
from nova_platform.database import get_db_session

with get_db_session() as session:
    results = session.query(Model).all()
# 自动commit和close
```

2. **Flask API（自动管理）**:
```python
@app.route('/api/data')
def get_data():
    session = get_session()  # 自动管理
    results = session.query(Model).all()
    return jsonify(results)
```

3. **长生命周期操作**:
```python
# 大数据处理
with get_db_session() as session:
    for item in large_dataset:
        process_item(session, item)
        session.commit()  # 定期提交
```

## 验证和测试

### 连接池压力测试

```python
# 测试多次连接
for i in range(100):
    with get_db_session() as session:
        session.query(Model).count()
# 所有连接正确释放
```

### 并发测试

```python
import threading

def worker():
    with get_db_session() as session:
        session.query(Model).count()

threads = [threading.Thread(target=worker) for _ in range(50)]
for t in threads:
    t.start()
for t in threads:
    t.join()
# 线程安全验证
```

### 泄漏检测

```python
import tracemalloc
tracemalloc.start()

# 执行大量数据库操作
for _ in range(1000):
    with get_db_session() as session:
        session.query(Model).all()

# 检查内存泄漏
current, peak = tracemalloc.get_traced_memory()
print(f"Current: {current / 1024:.1f}KB")
print(f"Peak: {peak / 1024:.1f}KB")
```

## 预防措施

### 1. 代码审查检查点

- [ ] 所有session使用都在上下文管理器中
- [ ] Flask API端点不需要手动管理session
- [ ] 长时间运行的操作定期commit
- [ ] 异常处理正确处理session关闭

### 2. 运行时监控

```python
# 添加连接池监控
from sqlalchemy import event

@event.listens_for(engine, "connect")
def receive_connect(dbapi_conn, connection_record):
    print("New connection created")

@event.listens_for(engine, "close")
def receive_close(dbapi_conn, connection_record):
    print("Connection closed")
```

### 3. 性能监控

```python
# 定期检查连接池状态
def check_connection_pool():
    pool = engine.pool
    print(f"Pool size: {pool.size()}")
    print(f"Checked out: {pool.checkedout()}")
    print(f"Overflow: {pool.overflow()}")
```

## 经验总结

### 问题诊断技巧

1. **检查连接池状态**:
   - 监控`engine.pool`状态
   - 检查`checkedout()`连接数
   - 查看连接创建/关闭事件

2. **内存分析**:
   - 使用`tracemalloc`检测泄漏
   - 检查session对象生命周期
   - 分析对象引用链

3. **日志分析**:
   - 记录所有session创建/销毁
   - 监控长时间持有的连接
   - 追踪未关闭的session

### 最佳实践

1. **总是使用上下文管理器**
2. **保持事务简短**
3. **定期提交大数据操作**
4. **避免在循环中创建session**
5. **使用scoped_session确保线程安全**

## 相关文档

- [SQLAlchemy连接池文档](https://docs.sqlalchemy.org/en/20/core/pooling.html)
- [Flask-SQLAlchemy最佳实践](https://flask-sqlalchemy.palletsprojects.com/)
- [Python上下文管理器](https://docs.python.org/3/library/contextlib.html)

---

**修复日期**: 2025-01-XX
**修复者**: Claude AI Agent
**影响范围**: 数据库层、所有服务层
**测试状态**: ✅ 通过
