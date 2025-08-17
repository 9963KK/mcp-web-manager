"""MCP服务管理器 - 整合mcp-proxy核心功能."""

import asyncio
import logging
import os
import signal
import subprocess
from typing import Dict, List, Optional, Tuple
from datetime import datetime
import psutil

from mcp.client.stdio import StdioServerParameters
from core.mcp_server import MCPServerSettings, run_mcp_server
from models import MCPService, ServiceStatus
from database.crud import service_crud, proxy_instance_crud, status_log_crud

logger = logging.getLogger(__name__)

# 延迟导入避免循环导入
def get_event_broadcaster():
    """获取事件广播器实例 - 延迟导入避免循环依赖."""
    try:
        from websocket.handlers import event_broadcaster
        return event_broadcaster
    except ImportError:
        logger.warning("WebSocket event broadcaster not available")
        return None


class PortManager:
    """端口分配管理器."""
    
    def __init__(self, start_port: int = 10000, end_port: int = 19999):
        self.start_port = start_port
        self.end_port = end_port
        self.allocated_ports: set = set()
    
    def allocate_port(self) -> Optional[int]:
        """分配一个可用端口."""
        for port in range(self.start_port, self.end_port + 1):
            if port not in self.allocated_ports and self._is_port_available(port):
                self.allocated_ports.add(port)
                return port
        return None
    
    def release_port(self, port: int):
        """释放端口."""
        self.allocated_ports.discard(port)
    
    def _is_port_available(self, port: int) -> bool:
        """检查端口是否可用 (对 0.0.0.0 进行绑定更贴近实际监听)."""
        import socket
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(("0.0.0.0", port))
                return True
            except OSError:
                return False


class MCPServiceManager:
    """MCP服务管理器."""
    
    def __init__(self):
        self.port_manager = PortManager()
        self.running_services: Dict[int, Dict] = {}  # service_id -> service_info
        self.processes: Dict[int, subprocess.Popen] = {}  # service_id -> process
        
    async def start_service(self, db, service: MCPService) -> Tuple[bool, str]:
        """启动MCP服务."""
        try:
            if service.id in self.running_services:
                return False, "服务已在运行中"
            
            # 分配端口
            port = self.port_manager.allocate_port()
            if not port:
                return False, "无法分配可用端口"
            
            # 更新服务状态为启动中
            service_crud.update_status(db, service.id, ServiceStatus.STARTING, "正在启动服务...")
            
            # 创建stdio服务器参数
            stdio_params = StdioServerParameters(
                command=service.command,
                args=service.args,
                env=service.env_vars or {},
                cwd=service.working_directory
            )
            
            # 创建MCP服务器设置
            bind_host = (
                service.streamhttp_host if service.streamhttp_host not in ("127.0.0.1", "localhost") else "0.0.0.0"
            )
            mcp_settings = MCPServerSettings(
                bind_host=bind_host,
                port=port,
                stateless=False,
                allow_origins=["*"],  # 开发环境允许所有来源
                log_level="INFO"
            )
            
            # 启动MCP代理服务器（以命名服务器方式挂载到 /{service.name} 下）
            task = asyncio.create_task(
                run_mcp_server(
                    mcp_settings=mcp_settings,
                    default_server_params=None,
                    named_server_params={service.name: stdio_params},
                    mount_base=""  # 根路径，形如 /{name}/mcp
                )
            )
            
            # 记录运行信息
            service_info = {
                "task": task,
                "port": port,
                "host": bind_host,
                "base_path": f"/{service.name}",
                "started_at": datetime.now(),
                "stdio_params": stdio_params,
                "mcp_settings": mcp_settings
            }
            
            self.running_services[service.id] = service_info
            
            # 创建代理实例记录
            sse_url = f"http://{service.streamhttp_host}:{port}/{service.name}/sse"
            streamhttp_url = f"http://{service.streamhttp_host}:{port}/{service.name}/mcp"
            
            proxy_instance_crud.create(
                db=db,
                service_id=service.id,
                sse_url=sse_url,
                streamhttp_url=streamhttp_url,
                port=port,
                host=service.streamhttp_host,
                is_active=True,
                stateless=False,
                allow_origins=["*"]
            )
            
            # 更新服务状态
            service.streamhttp_port = port
            service_crud.update_status(db, service.id, ServiceStatus.ACTIVE, f"服务已启动，端口: {port}")
            
            # 广播服务启动事件
            broadcaster = get_event_broadcaster()
            if broadcaster:
                asyncio.create_task(broadcaster.service_started(service.id, service.name, port))
            
            logger.info(f"Service {service.name} started on port {port} at path /{service.name}")
            return True, f"服务已成功启动，端口: {port}"
            
        except Exception as e:
            logger.error(f"Failed to start service {service.name}: {e}")
            # 清理资源
            if service.id in self.running_services:
                port = self.running_services[service.id]["port"]
                self.port_manager.release_port(port)
                del self.running_services[service.id]
            
            service_crud.update_status(db, service.id, ServiceStatus.ERROR, f"启动失败: {str(e)}")
            
            # 广播服务错误事件
            broadcaster = get_event_broadcaster()
            if broadcaster:
                asyncio.create_task(broadcaster.service_error(service.id, service.name, str(e)))
            
            return False, f"启动失败: {str(e)}"
    
    async def stop_service(self, db, service_id: int) -> Tuple[bool, str]:
        """停止MCP服务."""
        try:
            if service_id not in self.running_services:
                return False, "服务未在运行中"
            
            service_info = self.running_services[service_id]
            
            # 更新状态为停止中
            service_crud.update_status(db, service_id, ServiceStatus.STOPPING, "正在停止服务...")
            # 广播停止中
            broadcaster = get_event_broadcaster()
            if broadcaster:
                service = service_crud.get_by_id(db, service_id)
                if service:
                    asyncio.create_task(broadcaster.service_stopping(service_id, service.name))
            
            # 取消任务
            task = service_info["task"]
            task.cancel()
            
            try:
                await asyncio.wait_for(task, timeout=10.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
            
            # 等待端口真正释放后再释放记录，避免立即重启时判定占用
            port = service_info["port"]
            await self._wait_port_closed(port, timeout=8.0)
            self.port_manager.release_port(port)
            
            # 更新代理实例状态
            instances = proxy_instance_crud.get_by_service(db, service_id)
            for instance in instances:
                proxy_instance_crud.update_status(db, instance.id, False)
            
            # 清理运行信息
            del self.running_services[service_id]
            
            # 更新服务状态
            service_crud.update_status(db, service_id, ServiceStatus.INACTIVE, "服务已停止")
            
            # 获取服务信息用于广播
            service = service_crud.get_by_id(db, service_id)
            
            # 广播服务停止事件
            broadcaster = get_event_broadcaster()
            if broadcaster and service:
                asyncio.create_task(broadcaster.service_stopped(service_id, service.name))
            
            logger.info(f"Service {service_id} stopped")
            return True, "服务已成功停止"
            
        except Exception as e:
            logger.error(f"Failed to stop service {service_id}: {e}")
            service_crud.update_status(db, service_id, ServiceStatus.ERROR, f"停止失败: {str(e)}")
            
            # 获取服务信息用于广播
            service = service_crud.get_by_id(db, service_id)
            
            # 广播服务错误事件
            broadcaster = get_event_broadcaster()
            if broadcaster and service:
                asyncio.create_task(broadcaster.service_error(service_id, service.name, str(e)))
            
            return False, f"停止失败: {str(e)}"

    async def _wait_port_closed(self, port: int, timeout: float = 8.0) -> None:
        """等待直到端口关闭或超时 (轮询 0.2s)."""
        start = asyncio.get_event_loop().time()
        while True:
            try:
                if self.port_manager._is_port_available(port):  # noqa: SLF001
                    return
            except Exception:
                return
            if asyncio.get_event_loop().time() - start > timeout:
                logger.warning("Port %s still busy after %.1fs; next start may allocate a new port", port, timeout)
                return
            await asyncio.sleep(0.2)
    
    async def restart_service(self, db, service: MCPService) -> Tuple[bool, str]:
        """重启MCP服务."""
        if service.id in self.running_services:
            success, message = await self.stop_service(db, service.id)
            if not success:
                return False, f"停止服务失败: {message}"
            
            # 等待一秒确保完全停止
            await asyncio.sleep(1)
        
        return await self.start_service(db, service)
    
    def get_service_status(self, service_id: int) -> Dict:
        """获取服务运行状态."""
        if service_id not in self.running_services:
            return {"running": False}
        
        service_info = self.running_services[service_id]
        return {
            "running": True,
            "port": service_info["port"],
            "host": service_info["host"],
            "started_at": service_info["started_at"],
            "sse_url": f"http://{service_info['host']}:{service_info['port']}{service_info.get('base_path','')}/sse",
            "streamhttp_url": f"http://{service_info['host']}:{service_info['port']}{service_info.get('base_path','')}/mcp"
        }
    
    def get_all_running_services(self) -> Dict[int, Dict]:
        """获取所有运行中的服务."""
        result = {}
        for service_id, service_info in self.running_services.items():
            result[service_id] = {
                "port": service_info["port"],
                "host": service_info["host"],
                "started_at": service_info["started_at"],
                "sse_url": f"http://{service_info['host']}:{service_info['port']}{service_info.get('base_path','')}/sse",
                "streamhttp_url": f"http://{service_info['host']}:{service_info['port']}{service_info.get('base_path','')}/mcp"
            }
        return result
    
    async def cleanup_all(self, db):
        """清理所有运行中的服务."""
        logger.info("Cleaning up all running services...")
        for service_id in list(self.running_services.keys()):
            try:
                await self.stop_service(db, service_id)
            except Exception as e:
                logger.error(f"Error stopping service {service_id}: {e}")


# 创建全局服务管理器实例
mcp_service_manager = MCPServiceManager()