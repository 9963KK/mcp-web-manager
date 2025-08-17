"""仪表板API路由处理器."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import get_db
from database.crud import service_crud, status_log_crud, proxy_instance_crud
from schemas import DashboardStatsResponse
from services.mcp_manager import mcp_service_manager

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/stats", response_model=DashboardStatsResponse)
async def get_dashboard_stats(db: Session = Depends(get_db)):
    """获取仪表板统计信息."""
    # 服务统计
    service_stats = service_crud.get_stats(db)
    
    # 代理实例统计
    active_instances = proxy_instance_crud.get_active(db)
    total_requests = sum(instance.request_count for instance in active_instances)
    total_errors = sum(instance.error_count for instance in active_instances)
    
    # 计算正常运行时间百分比
    if total_requests > 0:
        uptime_percentage = ((total_requests - total_errors) / total_requests) * 100
    else:
        uptime_percentage = 100.0 if service_stats["active"] > 0 else 0.0
    
    # 最近日志
    recent_logs = status_log_crud.get_recent(db, limit=10)
    
    return DashboardStatsResponse(
        total_services=service_stats["total"],
        active_services=service_stats["active"],
        inactive_services=service_stats["inactive"],
        error_services=service_stats["error"],
        total_requests=total_requests,
        total_errors=total_errors,
        uptime_percentage=round(uptime_percentage, 2),
        recent_logs=recent_logs
    )


@router.get("/running-services")
async def get_running_services_overview():
    """获取运行中服务概览."""
    running_services = mcp_service_manager.get_all_running_services()
    
    return {
        "count": len(running_services),
        "services": running_services
    }


@router.get("/system-health")
async def get_system_health(db: Session = Depends(get_db)):
    """获取系统健康状态."""
    service_stats = service_crud.get_stats(db)
    active_instances = proxy_instance_crud.get_active(db)
    
    # 检查系统健康状态
    health_status = "healthy"
    if service_stats["error"] > 0:
        health_status = "warning"
    if service_stats["active"] == 0 and service_stats["total"] > 0:
        health_status = "critical"
    
    return {
        "status": health_status,
        "total_services": service_stats["total"],
        "active_services": service_stats["active"],
        "error_services": service_stats["error"],
        "active_proxy_instances": len(active_instances),
        "timestamp": "now"
    }