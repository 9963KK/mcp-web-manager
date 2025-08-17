"""WebSocket处理器 - 实时状态推送."""

import json
import asyncio
import logging
from typing import List, Dict, Any
from fastapi import WebSocket, WebSocketDisconnect
from datetime import datetime

logger = logging.getLogger(__name__)


class ConnectionManager:
    """WebSocket连接管理器."""
    
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.status_subscribers: List[WebSocket] = []
    
    async def connect(self, websocket: WebSocket):
        """建立连接."""
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"WebSocket connected. Total connections: {len(self.active_connections)}")
    
    def disconnect(self, websocket: WebSocket):
        """断开连接."""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        if websocket in self.status_subscribers:
            self.status_subscribers.remove(websocket)
        logger.info(f"WebSocket disconnected. Total connections: {len(self.active_connections)}")
    
    async def subscribe_to_status(self, websocket: WebSocket):
        """订阅状态更新."""
        if websocket not in self.status_subscribers:
            self.status_subscribers.append(websocket)
            logger.info(f"Client subscribed to status updates. Total subscribers: {len(self.status_subscribers)}")
    
    async def send_personal_message(self, message: str, websocket: WebSocket):
        """发送个人消息."""
        try:
            await websocket.send_text(message)
        except Exception as e:
            logger.error(f"Error sending personal message: {e}")
            self.disconnect(websocket)
    
    async def broadcast_status_update(self, data: Dict[str, Any]):
        """广播状态更新给所有订阅者."""
        if not self.status_subscribers:
            return
        
        message = json.dumps({
            "type": "status_update",
            "data": data,
            "timestamp": datetime.now().isoformat()
        })
        
        disconnected = []
        for connection in self.status_subscribers:
            try:
                await connection.send_text(message)
            except Exception as e:
                logger.error(f"Error broadcasting to connection: {e}")
                disconnected.append(connection)
        
        # 清理断开的连接
        for conn in disconnected:
            self.disconnect(conn)
    
    async def broadcast_service_event(self, event_type: str, service_id: int, data: Dict[str, Any]):
        """广播服务事件."""
        message = json.dumps({
            "type": "service_event",
            "event": event_type,
            "service_id": service_id,
            "data": data,
            "timestamp": datetime.now().isoformat()
        })
        
        disconnected = []
        for connection in self.status_subscribers:
            try:
                await connection.send_text(message)
            except Exception as e:
                logger.error(f"Error broadcasting service event: {e}")
                disconnected.append(connection)
        
        # 清理断开的连接
        for conn in disconnected:
            self.disconnect(conn)


# 创建全局连接管理器
manager = ConnectionManager()


async def websocket_endpoint(websocket: WebSocket):
    """WebSocket端点处理器."""
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            try:
                message = json.loads(data)
                message_type = message.get("type")
                
                if message_type == "subscribe_status":
                    await manager.subscribe_to_status(websocket)
                    await manager.send_personal_message(
                        json.dumps({"type": "subscription_confirmed", "status": "success"}),
                        websocket
                    )
                elif message_type == "ping":
                    await manager.send_personal_message(
                        json.dumps({"type": "pong", "timestamp": datetime.now().isoformat()}),
                        websocket
                    )
                else:
                    await manager.send_personal_message(
                        json.dumps({"type": "error", "message": "Unknown message type"}),
                        websocket
                    )
                    
            except json.JSONDecodeError:
                await manager.send_personal_message(
                    json.dumps({"type": "error", "message": "Invalid JSON"}),
                    websocket
                )
                
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(websocket)


class ServiceEventBroadcaster:
    """服务事件广播器."""
    
    @staticmethod
    async def service_started(service_id: int, service_name: str, port: int):
        """服务启动事件."""
        await manager.broadcast_service_event("started", service_id, {
            "name": service_name,
            "port": port,
            "message": f"服务 {service_name} 已启动"
        })
    
    @staticmethod
    async def service_stopped(service_id: int, service_name: str):
        """服务停止事件."""
        await manager.broadcast_service_event("stopped", service_id, {
            "name": service_name,
            "message": f"服务 {service_name} 已停止"
        })

    @staticmethod
    async def service_stopping(service_id: int, service_name: str):
        """服务停止中事件."""
        await manager.broadcast_service_event("stopping", service_id, {
            "name": service_name,
            "message": f"服务 {service_name} 正在停止..."
        })
    
    @staticmethod
    async def service_error(service_id: int, service_name: str, error: str):
        """服务错误事件."""
        await manager.broadcast_service_event("error", service_id, {
            "name": service_name,
            "error": error,
            "message": f"服务 {service_name} 发生错误: {error}"
        })
    
    @staticmethod
    async def status_update(stats: Dict[str, Any]):
        """状态更新事件."""
        await manager.broadcast_status_update(stats)


# 创建事件广播器实例
event_broadcaster = ServiceEventBroadcaster()