from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool
from config import settings
from models import Base
import logging

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 创建数据库引擎
engine = create_engine(
    settings.database_url,
    **({"poolclass": StaticPool} if "sqlite" in settings.database_url else {"pool_pre_ping": True}),
    connect_args={"check_same_thread": False} if "sqlite" in settings.database_url else
                 ({"connect_timeout": 5} if settings.database_url.startswith("postgresql") else {}),
    echo=settings.debug
)

# 创建会话工厂
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    """初始化数据库"""
    try:
        import models_operations  # 注册每日任务审计表，也覆盖容器 migrate 启动方式。
        from schema_migration import migrate_schema
        migrate_schema(engine)
        logger.info("数据库表创建成功")
    except Exception as e:
        logger.error(f"数据库初始化失败: {e}")
        raise

def get_db() -> Session:
    """获取数据库会话"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_db_session() -> Session:
    """获取数据库会话（用于Celery任务）"""
    return SessionLocal()
