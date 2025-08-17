"""Pydantic schemas for API request/response validation."""

from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

from models.models import ServiceStatus


class MCPServiceBase(BaseModel):
    """MCP服务基础Schema."""
    name: str = Field(..., min_length=1, max_length=100, description="服务名称")
    description: Optional[str] = Field(None, description="服务描述")
    command: str = Field(..., min_length=1, max_length=500, description="启动命令")
    args: List[str] = Field(default_factory=list, description="命令参数")
    env_vars: Dict[str, str] = Field(default_factory=dict, description="环境变量")
    working_directory: Optional[str] = Field(None, description="工作目录")
    streamhttp_host: str = Field(default="127.0.0.1", description="StreamHTTP绑定主机")
    auto_restart: bool = Field(default=True, description="自动重启")
    timeout: int = Field(default=60, ge=10, le=300, description="超时时间(秒)")


class MCPServiceCreate(MCPServiceBase):
    """创建MCP服务Schema."""
    pass


class MCPServiceUpdate(BaseModel):
    """更新MCP服务Schema."""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    command: Optional[str] = Field(None, min_length=1, max_length=500)
    args: Optional[List[str]] = None
    env_vars: Optional[Dict[str, str]] = None
    working_directory: Optional[str] = None
    streamhttp_host: Optional[str] = None
    auto_restart: Optional[bool] = None
    timeout: Optional[int] = Field(None, ge=10, le=300)


class MCPServiceResponse(MCPServiceBase):
    """MCP服务响应Schema."""
    id: int
    status: ServiceStatus
    streamhttp_port: Optional[int]
    created_at: datetime
    updated_at: datetime
    last_started_at: Optional[datetime]
    last_stopped_at: Optional[datetime]
    
    class Config:
        from_attributes = True


class ServiceStatusLogResponse(BaseModel):
    """服务状态日志响应Schema."""
    id: int
    service_id: int
    status: str
    message: Optional[str]
    timestamp: datetime
    extra_data: Dict[str, Any]
    
    class Config:
        from_attributes = True


class ProxyInstanceResponse(BaseModel):
    """代理实例响应Schema."""
    id: int
    service_id: int
    sse_url: str
    streamhttp_url: str
    port: int
    host: str
    is_active: bool
    pid: Optional[int]
    started_at: Optional[datetime]
    stopped_at: Optional[datetime]
    request_count: int
    error_count: int
    last_request_at: Optional[datetime]
    last_error_at: Optional[datetime]
    stateless: bool
    allow_origins: List[str]
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class SystemSettingResponse(BaseModel):
    """系统设置响应Schema."""
    id: int
    key: str
    value: Any
    description: Optional[str]
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class ClientConfigResponse(BaseModel):
    """客户端配置导出Schema."""
    mcpServers: Dict[str, Dict[str, Any]]


class ServiceActionRequest(BaseModel):
    """服务操作请求Schema."""
    action: str = Field(..., pattern="^(start|stop|restart)$", description="操作类型")


class ServiceListResponse(BaseModel):
    """服务列表响应Schema."""
    services: List[MCPServiceResponse]
    total: int
    active_count: int
    inactive_count: int
    error_count: int


class DashboardStatsResponse(BaseModel):
    """仪表板统计响应Schema."""
    total_services: int
    active_services: int
    inactive_services: int
    error_services: int
    total_requests: int
    total_errors: int
    uptime_percentage: float
    recent_logs: List[ServiceStatusLogResponse]


class ImportResultResponse(BaseModel):
    """批量导入结果响应Schema."""
    created: int
    skipped: int
    failed: int
    errors: List[str] = Field(default_factory=list)


class ClaudeServerConfig(BaseModel):
    """Claude Desktop mcpServers 中的单个服务配置."""
    command: str
    args: Optional[List[str]] = Field(default_factory=list)
    env: Optional[Dict[str, str]] = Field(default_factory=dict)


class ClaudeDesktopConfig(BaseModel):
    """Claude Desktop 的配置结构."""
    mcpServers: Dict[str, ClaudeServerConfig]


class BatchCreateServicesRequest(BaseModel):
    """批量创建服务的请求结构."""
    services: List[MCPServiceCreate]