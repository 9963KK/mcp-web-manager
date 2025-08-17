"""配置导出API路由处理器."""

from typing import Dict, Any
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from database.crud import service_crud, proxy_instance_crud
from schemas import ClientConfigResponse
from services.mcp_manager import mcp_service_manager

router = APIRouter(prefix="/api/config", tags=["config"])


@router.get("/export", response_model=ClientConfigResponse)
async def export_client_config(db: Session = Depends(get_db)):
    """导出客户端配置文件（Claude Desktop格式）."""
    services = service_crud.get_all(db)
    mcp_servers = {}
    
    for service in services:
        # 获取代理实例信息
        instances = proxy_instance_crud.get_by_service(db, service.id)
        active_instances = [inst for inst in instances if inst.is_active]
        
        if not active_instances:
            continue
        
        # 使用第一个活跃实例
        instance = active_instances[0]
        
        # 构建配置
        server_config = {
            "command": "mcp-proxy",
            "args": [instance.sse_url]
        }
        
        # 添加环境变量（如果有）
        if service.env_vars:
            server_config["env"] = service.env_vars
        
        mcp_servers[service.name] = server_config
    
    return ClientConfigResponse(mcpServers=mcp_servers)


@router.get("/export/raw")
async def export_client_config_raw(db: Session = Depends(get_db)):
    """导出原始JSON格式的客户端配置."""
    config = await export_client_config(db)
    return {"mcpServers": config.mcpServers}


@router.get("/export/claude-desktop")
async def export_claude_desktop_config(db: Session = Depends(get_db)):
    """导出Claude Desktop配置格式."""
    config = await export_client_config(db)
    
    # Claude Desktop配置格式
    claude_config = {
        "mcpServers": config.mcpServers
    }
    
    return claude_config


@router.get("/export/service/{service_id}")
async def export_single_service_config(
    service_id: int,
    db: Session = Depends(get_db)
):
    """导出单个服务的配置."""
    service = service_crud.get_by_id(db, service_id)
    if not service:
        raise HTTPException(status_code=404, detail="服务不存在")
    
    # 获取代理实例
    instances = proxy_instance_crud.get_by_service(db, service_id)
    active_instances = [inst for inst in instances if inst.is_active]
    
    if not active_instances:
        raise HTTPException(status_code=400, detail="服务未运行或无活跃实例")
    
    instance = active_instances[0]
    
    server_config = {
        "command": "mcp-proxy",
        "args": [instance.sse_url]
    }
    
    if service.env_vars:
        server_config["env"] = service.env_vars
    
    return {
        "service_name": service.name,
        "config": server_config,
        "urls": {
            "sse": instance.sse_url,
            "streamhttp": instance.streamhttp_url
        }
    }


@router.get("/running-services")
async def get_running_services_info():
    """获取所有运行中服务的连接信息."""
    running_services = mcp_service_manager.get_all_running_services()
    
    if not running_services:
        return {"message": "没有运行中的服务", "services": {}}
    
    return {
        "message": f"发现 {len(running_services)} 个运行中的服务",
        "services": running_services
    }