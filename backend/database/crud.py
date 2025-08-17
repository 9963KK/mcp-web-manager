"""Database CRUD operations."""

from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc, func

from models.models import MCPService, ServiceStatusLog, ProxyInstance, SystemSettings, ServiceStatus
from schemas import MCPServiceCreate, MCPServiceUpdate


class MCPServiceCRUD:
    """MCP服务CRUD操作."""
    
    @staticmethod
    def get_all(db: Session, skip: int = 0, limit: int = 100) -> List[MCPService]:
        """获取所有服务."""
        return db.query(MCPService).offset(skip).limit(limit).all()
    
    @staticmethod
    def get_by_id(db: Session, service_id: int) -> Optional[MCPService]:
        """根据ID获取服务."""
        return db.query(MCPService).filter(MCPService.id == service_id).first()
    
    @staticmethod
    def get_by_name(db: Session, name: str) -> Optional[MCPService]:
        """根据名称获取服务."""
        return db.query(MCPService).filter(MCPService.name == name).first()
    
    @staticmethod
    def create(db: Session, service: MCPServiceCreate) -> MCPService:
        """创建新服务."""
        db_service = MCPService(**service.dict())
        db.add(db_service)
        db.commit()
        db.refresh(db_service)
        return db_service
    
    @staticmethod
    def update(db: Session, service_id: int, service_update: MCPServiceUpdate) -> Optional[MCPService]:
        """更新服务."""
        db_service = db.query(MCPService).filter(MCPService.id == service_id).first()
        if db_service:
            update_data = service_update.dict(exclude_unset=True)
            for field, value in update_data.items():
                setattr(db_service, field, value)
            db.commit()
            db.refresh(db_service)
        return db_service
    
    @staticmethod
    def delete(db: Session, service_id: int) -> bool:
        """删除服务."""
        db_service = db.query(MCPService).filter(MCPService.id == service_id).first()
        if db_service:
            db.delete(db_service)
            db.commit()
            return True
        return False
    
    @staticmethod
    def update_status(db: Session, service_id: int, status: ServiceStatus, message: str = None) -> Optional[MCPService]:
        """更新服务状态."""
        db_service = db.query(MCPService).filter(MCPService.id == service_id).first()
        if db_service:
            db_service.status = status.value
            if status == ServiceStatus.ACTIVE:
                db_service.last_started_at = func.now()
            elif status in [ServiceStatus.INACTIVE, ServiceStatus.ERROR]:
                db_service.last_stopped_at = func.now()
            
            # 记录状态日志
            status_log = ServiceStatusLog(
                service_id=service_id,
                status=status.value,
                message=message
            )
            db.add(status_log)
            db.commit()
            db.refresh(db_service)
        return db_service
    
    @staticmethod
    def get_stats(db: Session) -> Dict[str, int]:
        """获取服务统计信息."""
        total = db.query(MCPService).count()
        active = db.query(MCPService).filter(MCPService.status == ServiceStatus.ACTIVE.value).count()
        inactive = db.query(MCPService).filter(MCPService.status == ServiceStatus.INACTIVE.value).count()
        error = db.query(MCPService).filter(MCPService.status == ServiceStatus.ERROR.value).count()
        
        return {
            "total": total,
            "active": active,
            "inactive": inactive,
            "error": error
        }


class ServiceStatusLogCRUD:
    """服务状态日志CRUD操作."""
    
    @staticmethod
    def get_by_service(db: Session, service_id: int, limit: int = 50) -> List[ServiceStatusLog]:
        """获取指定服务的状态日志."""
        return (db.query(ServiceStatusLog)
                .filter(ServiceStatusLog.service_id == service_id)
                .order_by(desc(ServiceStatusLog.timestamp))
                .limit(limit)
                .all())
    
    @staticmethod
    def get_recent(db: Session, limit: int = 10) -> List[ServiceStatusLog]:
        """获取最近的状态日志."""
        return (db.query(ServiceStatusLog)
                .order_by(desc(ServiceStatusLog.timestamp))
                .limit(limit)
                .all())
    
    @staticmethod
    def create(db: Session, service_id: int, status: str, message: str = None, extra_data: Dict[str, Any] = None) -> ServiceStatusLog:
        """创建状态日志."""
        log = ServiceStatusLog(
            service_id=service_id,
            status=status,
            message=message,
            extra_data=extra_data or {}
        )
        db.add(log)
        db.commit()
        db.refresh(log)
        return log


class ProxyInstanceCRUD:
    """代理实例CRUD操作."""
    
    @staticmethod
    def get_by_service(db: Session, service_id: int) -> List[ProxyInstance]:
        """获取指定服务的代理实例."""
        return db.query(ProxyInstance).filter(ProxyInstance.service_id == service_id).all()
    
    @staticmethod
    def get_active(db: Session) -> List[ProxyInstance]:
        """获取所有活跃的代理实例."""
        return db.query(ProxyInstance).filter(ProxyInstance.is_active == True).all()
    
    @staticmethod
    def create(db: Session, service_id: int, **kwargs) -> ProxyInstance:
        """创建代理实例."""
        instance = ProxyInstance(service_id=service_id, **kwargs)
        db.add(instance)
        db.commit()
        db.refresh(instance)
        return instance
    
    @staticmethod
    def update_status(db: Session, instance_id: int, is_active: bool, pid: int = None) -> Optional[ProxyInstance]:
        """更新代理实例状态."""
        instance = db.query(ProxyInstance).filter(ProxyInstance.id == instance_id).first()
        if instance:
            instance.is_active = is_active
            if pid:
                instance.pid = pid
            if is_active:
                instance.started_at = func.now()
            else:
                instance.stopped_at = func.now()
            db.commit()
            db.refresh(instance)
        return instance
    
    @staticmethod
    def increment_requests(db: Session, instance_id: int) -> Optional[ProxyInstance]:
        """增加请求计数."""
        instance = db.query(ProxyInstance).filter(ProxyInstance.id == instance_id).first()
        if instance:
            instance.request_count += 1
            instance.last_request_at = func.now()
            db.commit()
            db.refresh(instance)
        return instance
    
    @staticmethod
    def increment_errors(db: Session, instance_id: int) -> Optional[ProxyInstance]:
        """增加错误计数."""
        instance = db.query(ProxyInstance).filter(ProxyInstance.id == instance_id).first()
        if instance:
            instance.error_count += 1
            instance.last_error_at = func.now()
            db.commit()
            db.refresh(instance)
        return instance


class SystemSettingsCRUD:
    """系统设置CRUD操作."""
    
    @staticmethod
    def get_all(db: Session) -> List[SystemSettings]:
        """获取所有系统设置."""
        return db.query(SystemSettings).all()
    
    @staticmethod
    def get_by_key(db: Session, key: str) -> Optional[SystemSettings]:
        """根据键获取设置."""
        return db.query(SystemSettings).filter(SystemSettings.key == key).first()
    
    @staticmethod
    def set_value(db: Session, key: str, value: Any, description: str = None) -> SystemSettings:
        """设置配置值."""
        setting = db.query(SystemSettings).filter(SystemSettings.key == key).first()
        if setting:
            setting.value = value
            if description:
                setting.description = description
        else:
            setting = SystemSettings(key=key, value=value, description=description)
            db.add(setting)
        
        db.commit()
        db.refresh(setting)
        return setting


# 创建CRUD实例
service_crud = MCPServiceCRUD()
status_log_crud = ServiceStatusLogCRUD()
proxy_instance_crud = ProxyInstanceCRUD()
system_settings_crud = SystemSettingsCRUD()