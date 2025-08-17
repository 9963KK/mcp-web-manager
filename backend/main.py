"""MCP Web Manager主应用入口."""

import logging
import asyncio
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from database import init_database
from api import services_router, config_router, dashboard_router
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
    
    yield
    
    # 关闭时清理
    logger.info("Shutting down MCP Web Manager...")
    from database import SessionLocal
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
        port=8000,
        reload=True,
        log_level="info"
    )