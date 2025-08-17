"""Database models for MCP Web Manager."""

from datetime import datetime
from enum import Enum
from typing import Optional

from sqlalchemy import Column, DateTime, Integer, String, Text, Boolean, JSON, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

Base = declarative_base()


class ServiceStatus(str, Enum):
    """MCP service status enumeration."""
    ACTIVE = "active"
    INACTIVE = "inactive"
    ERROR = "error"
    STARTING = "starting"
    STOPPING = "stopping"


class MCPService(Base):
    """MCP服务配置表."""
    __tablename__ = "mcp_services"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False, index=True)
    description = Column(Text, nullable=True)
    command = Column(String(500), nullable=False)
    args = Column(JSON, default=list)
    env_vars = Column(JSON, default=dict)
    working_directory = Column(String(500), nullable=True)
    
    # MCP配置
    stdio_enabled = Column(Boolean, default=True)
    streamhttp_port = Column(Integer, nullable=True)
    streamhttp_host = Column(String(100), default="127.0.0.1")
    
    # 状态管理
    status = Column(String(20), default=ServiceStatus.INACTIVE.value)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    last_started_at = Column(DateTime, nullable=True)
    last_stopped_at = Column(DateTime, nullable=True)
    
    # 配置选项
    auto_restart = Column(Boolean, default=True)
    timeout = Column(Integer, default=60)
    
    # 关联
    status_logs = relationship("ServiceStatusLog", back_populates="service", cascade="all, delete-orphan")
    proxy_instances = relationship("ProxyInstance", back_populates="service", cascade="all, delete-orphan")


class ServiceStatusLog(Base):
    """服务状态历史记录表."""
    __tablename__ = "service_status_logs"

    id = Column(Integer, primary_key=True, index=True)
    service_id = Column(Integer, ForeignKey("mcp_services.id"), nullable=False)
    status = Column(String(20), nullable=False)
    message = Column(Text, nullable=True)
    timestamp = Column(DateTime, default=func.now())
    
    # 额外信息
    extra_data = Column(JSON, default=dict)
    
    # 关联
    service = relationship("MCPService", back_populates="status_logs")


class ProxyInstance(Base):
    """代理实例表 - 存储stdio到streamhttp的转换实例信息."""
    __tablename__ = "proxy_instances"

    id = Column(Integer, primary_key=True, index=True)
    service_id = Column(Integer, ForeignKey("mcp_services.id"), nullable=False)
    
    # 网络配置
    sse_url = Column(String(500), nullable=False)
    streamhttp_url = Column(String(500), nullable=False)
    port = Column(Integer, nullable=False)
    host = Column(String(100), default="127.0.0.1")
    
    # 状态信息
    is_active = Column(Boolean, default=False)
    pid = Column(Integer, nullable=True)
    started_at = Column(DateTime, nullable=True)
    stopped_at = Column(DateTime, nullable=True)
    
    # 性能指标
    request_count = Column(Integer, default=0)
    error_count = Column(Integer, default=0)
    last_request_at = Column(DateTime, nullable=True)
    last_error_at = Column(DateTime, nullable=True)
    
    # 配置
    stateless = Column(Boolean, default=False)
    allow_origins = Column(JSON, default=list)
    
    # 时间戳
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    
    # 关联
    service = relationship("MCPService", back_populates="proxy_instances")


class SystemSettings(Base):
    """系统设置表."""
    __tablename__ = "system_settings"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(100), unique=True, nullable=False, index=True)
    value = Column(JSON, nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())