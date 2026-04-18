import os
from pathlib import Path
from contextlib import contextmanager
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session, scoped_session
from nova_platform.models import Base

DATA_DIR = Path.home() / ".nova-platform"
DATA_DIR.mkdir(exist_ok=True)
DB_PATH = DATA_DIR / "nova.db"

# 增加连接池大小并优化配置
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
SessionLocal = scoped_session(sessionmaker(bind=engine, autocommit=False, autoflush=False))


def init_db():
    """初始化数据库，创建所有表"""
    Base.metadata.create_all(engine)


def get_session() -> Session:
    """获取数据库会话"""
    return SessionLocal()


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


def init_db():
    Base.metadata.create_all(engine)


def get_session() -> Session:
    return SessionLocal()
