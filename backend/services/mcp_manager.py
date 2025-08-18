"""MCP服务管理器 - 整合mcp-proxy核心功能."""

import asyncio
import logging
import os
import signal
import subprocess
from typing import Dict, List, Optional, Tuple
from datetime import datetime
import psutil
import sys
import shutil

# 采用方案A：以独立 mcp-proxy 进程运行，不再在进程内启动代理服务器
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

    def try_allocate_specific(self, port: int) -> bool:
        """尝试分配指定端口，成功返回 True。"""
        if port in self.allocated_ports:
            return False
        if not self._is_port_available(port):
            return False
        self.allocated_ports.add(port)
        return True


class MCPServiceManager:
    """MCP服务管理器."""
    
    def __init__(self):
        self.port_manager = PortManager()
        self.running_services: Dict[int, Dict] = {}  # service_id -> service_info
        self.processes: Dict[int, subprocess.Popen] = {}  # service_id -> process
        
    async def start_service(self, db, service: MCPService) -> Tuple[bool, str]:
        """启动MCP服务（独立 mcp-proxy 进程）."""
        try:
            if service.id in self.running_services:
                return False, "服务已在运行中"
            
            # 分配端口：优先尝试复用上次端口，最多等待 ~3s
            desired_port = service.streamhttp_port
            port: Optional[int] = None
            if desired_port and self.port_manager.start_port <= desired_port <= self.port_manager.end_port:
                for _ in range(15):  # 15 * 0.2s = 3s
                    if self.port_manager.try_allocate_specific(desired_port):
                        port = desired_port
                        logger.info("Reusing previous port for service %s: %s", service.name, port)
                        break
                    await asyncio.sleep(0.2)
            # 回退选择任意可用端口
            if port is None:
                port = self.port_manager.allocate_port()
            if not port:
                return False, "无法分配可用端口"
            
            # 更新服务状态为启动中
            service_crud.update_status(db, service.id, ServiceStatus.STARTING, "正在启动服务...")
            
            # 以外部 mcp-proxy 进程运行，默认服务器路由为 /mcp 与 /sse
            bind_host = (
                service.streamhttp_host if service.streamhttp_host not in ("127.0.0.1", "localhost") else "0.0.0.0"
            )
            # 使用 python -m mcp_proxy 以确保通过 PYTHONPATH 加载到本仓库内源码
            python_exec = sys.executable or shutil.which("python3") or "python3"
            base_cmd: List[str] = [
                python_exec, "-m", "mcp_proxy",
                "--host", str(bind_host),
                "--port", str(port),
                "--allow-origin", "*",
                "--pass-environment",
                "--",
                service.command,
            ] + (service.args or [])

            env = os.environ.copy()
            if service.env_vars:
                env.update({k: str(v) for k, v in (service.env_vars or {}).items()})

            working_dir = service.working_directory or None

            # 确保子进程优先加载本仓库内的 mcp-proxy 源码（以便我们自带的路由修复生效）
            env = os.environ.copy()
            if service.env_vars:
                env.update({k: str(v) for k, v in (service.env_vars or {}).items()})
            repo_proxy_path = "/root/mcp-web-manager/mcp-proxy/src"
            existing_pythonpath = env.get("PYTHONPATH", "")
            env["PYTHONPATH"] = f"{repo_proxy_path}:{existing_pythonpath}" if existing_pythonpath else repo_proxy_path

            process = subprocess.Popen(
                base_cmd,
                cwd=working_dir,
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            # 等待端口开放
            await self._wait_port_open("127.0.0.1", port, timeout=8.0)

            # 记录运行信息
            service_info = {
                "process": process,
                "pid": process.pid,
                "port": port,
                "host": bind_host,
                "base_path": "",
                "started_at": datetime.now(),
            }
            
            self.running_services[service.id] = service_info
            
            # 创建代理实例记录
            sse_url = f"http://{service.streamhttp_host}:{port}/sse"
            streamhttp_url = f"http://{service.streamhttp_host}:{port}/mcp"
            
            proxy_instance_crud.create(
                db=db,
                service_id=service.id,
                sse_url=sse_url,
                streamhttp_url=streamhttp_url,
                port=port,
                host=service.streamhttp_host,
                is_active=True,
                stateless=False,
                allow_origins=["*"],
                pid=process.pid,
            )
            
            # 更新服务状态
            service.streamhttp_port = port
            service_crud.update_status(db, service.id, ServiceStatus.ACTIVE, f"服务已启动，端口: {port}")
            
            # 广播服务启动事件
            broadcaster = get_event_broadcaster()
            if broadcaster:
                asyncio.create_task(broadcaster.service_started(service.id, service.name, port))
            
            logger.info(f"Service {service.name} started on port {port} (external mcp-proxy pid={process.pid})")
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
        """停止MCP服务（终止外部 mcp-proxy 进程）。"""
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
            
            # 终止外部进程
            process: Optional[subprocess.Popen] = service_info.get("process")
            if process and psutil.pid_exists(process.pid):
                try:
                    process.terminate()
                    try:
                        process.wait(timeout=6)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=3)
                except Exception as ex:  # noqa: BLE001
                    logger.warning("Error terminating process %s: %s", process.pid, ex)
            
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
            "sse_url": f"http://{service_info['host']}:{service_info['port']}/sse",
            "streamhttp_url": f"http://{service_info['host']}:{service_info['port']}/mcp"
        }
    
    def get_all_running_services(self) -> Dict[int, Dict]:
        """获取所有运行中的服务."""
        result = {}
        for service_id, service_info in self.running_services.items():
            result[service_id] = {
                "port": service_info["port"],
                "host": service_info["host"],
                "started_at": service_info["started_at"],
                "sse_url": f"http://{service_info['host']}:{service_info['port']}/sse",
                "streamhttp_url": f"http://{service_info['host']}:{service_info['port']}/mcp"
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

    async def _wait_port_open(self, host: str, port: int, timeout: float = 8.0) -> None:
        """等待端口开始监听或超时."""
        start = asyncio.get_event_loop().time()
        import socket
        while True:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(0.2)
                try:
                    if sock.connect_ex((host, port)) == 0:
                        return
                except Exception:
                    pass
            if asyncio.get_event_loop().time() - start > timeout:
                logger.warning("Port %s not opened within %.1fs", port, timeout)
                return
            await asyncio.sleep(0.2)


# 创建全局服务管理器实例
mcp_service_manager = MCPServiceManager()