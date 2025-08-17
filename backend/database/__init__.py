"""Database configuration and session management."""

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from models.models import Base, SystemSettings

# 数据库URL配置
DATABASE_URL = os.getenv(
    "DATABASE_URL", 
    "sqlite:///./mcp_web_manager.db"
)

# 创建数据库引擎
if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False
    )
else:
    engine = create_engine(DATABASE_URL, echo=False)

# 创建会话工厂
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def create_tables():
    """创建所有数据库表."""
    Base.metadata.create_all(bind=engine)


def get_db():
    """获取数据库会话依赖."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_database():
    """初始化数据库 - 创建表和默认数据."""
    create_tables()
    
    # 创建默认系统设置
    db = SessionLocal()
    try:
        # 检查是否已有系统设置
        existing_settings = db.query(SystemSettings).first()
        if not existing_settings:
            default_settings = [
                SystemSettings(
                    key="default_host",
                    value="127.0.0.1",
                    description="默认服务绑定主机"
                ),
                SystemSettings(
                    key="port_range_start",
                    value=10000,
                    description="端口分配起始范围"
                ),
                SystemSettings(
                    key="port_range_end",
                    value=19999,
                    description="端口分配结束范围"
                ),
                SystemSettings(
                    key="auto_cleanup_logs",
                    value=True,
                    description="自动清理旧日志"
                ),
                SystemSettings(
                    key="log_retention_days",
                    value=30,
                    description="日志保留天数"
                )
            ]
            
            for setting in default_settings:
                db.add(setting)
            
            db.commit()
            
    except Exception as e:
        db.rollback()
        print(f"Failed to initialize default settings: {e}")
    finally:
        db.close()