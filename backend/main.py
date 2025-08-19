"""MCP Web Manager主应用入口."""

import logging
import asyncio
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from database import init_database
from api import services_router, config_router, dashboard_router, proxy_router
from services.mcp_manager import mcp_service_manager
from websocket import websocket_endpoint

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理."""
    # 启动时初始化
    logger.info("Initializing MCP Web Manager...")
    
    # 初始化数据库
    init_database()
    logger.info("Database initialized")
    
    # 同步服务状态 - 重启后将所有数据库中标记为运行的服务状态重置为 inactive
    from database import SessionLocal
    from database.crud import service_crud
    from models import ServiceStatus, MCPService
    
    db = SessionLocal()
    try:
        # 获取所有标记为运行或启动中的服务
        active_services = db.query(MCPService).filter(
            MCPService.status.in_([ServiceStatus.ACTIVE.value, ServiceStatus.STARTING.value])
        ).all()
        
        if active_services:
            logger.info(f"Found {len(active_services)} services in active/starting state, resetting to inactive...")
            for service in active_services:
                service_crud.update_status(db, service.id, ServiceStatus.INACTIVE, "服务重启后状态重置")
            logger.info("Service status synchronized")
        else:
            logger.info("No active services found, status already synchronized")
            
    except Exception as e:
        logger.error(f"Error synchronizing service status: {e}")
    finally:
        db.close()
    
    yield
    
    # 关闭时清理
    logger.info("Shutting down MCP Web Manager...")
    db = SessionLocal()
    try:
        await mcp_service_manager.cleanup_all(db)
        logger.info("All services cleaned up")
    except Exception as e:
        logger.error(f"Error during cleanup: {e}")
    finally:
        db.close()


def create_app() -> FastAPI:
    """创建FastAPI应用."""
    app = FastAPI(
        title="MCP Web Manager",
        description="A web-based management interface for MCP proxy services",
        version="0.1.0",
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        lifespan=lifespan
    )
    
    # 配置CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # 生产环境应该限制具体域名
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # 注册API路由
    app.include_router(services_router)
    app.include_router(config_router)
    app.include_router(dashboard_router)

    # 统一域名下的反向代理：/{name}/mcp 与 /{name}/sse
    app.include_router(proxy_router, tags=["proxy"])

    # 注册WebSocket端点
    app.websocket("/ws")(websocket_endpoint)
    
    # 静态文件服务
    frontend_dir = os.path.join(os.path.dirname(__file__), "..", "frontend", "public")
    if os.path.exists(frontend_dir):
        app.mount("/static", StaticFiles(directory=frontend_dir), name="static")
        
        @app.get("/")
        async def read_index():
            return FileResponse(os.path.join(frontend_dir, "index.html"))
    
    # 健康检查端点
    @app.get("/health")
    async def health_check():
        return {"status": "healthy", "service": "mcp-web-manager"}
    
    # 提供用于前端展示用的主机名（外网/本机）
    @app.get("/api/system/display-host")
    async def get_display_host(request: Request):
        import os as _os
        env_host = _os.getenv("PUBLIC_HOST") or _os.getenv("BASE_HOST") or _os.getenv("PUBLIC_IP")
        req_host = request.headers.get("host", "")
        host_only = req_host.split(":")[0] if req_host else ""

        def _is_local(h: str) -> bool:
            return h in ("localhost", "127.0.0.1", "")

        if env_host and not _is_local(env_host):
            return {"host": env_host, "source": "env", "request_host": host_only}
        if host_only and not _is_local(host_only):
            return {"host": host_only, "source": "request_host", "request_host": host_only}
        # 默认本地
        return {"host": "127.0.0.1", "source": "local_default", "request_host": host_only}
    
    # 如果没有静态文件，提供默认根路径
    if not os.path.exists(frontend_dir):
        @app.get("/")
        async def root():
            return {"message": "MCP Web Manager API", "docs": "/api/docs"}
    
    return app


# 创建应用实例
app = create_app()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8765,
        reload=True,
        log_level="info"
    )