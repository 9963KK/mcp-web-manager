#!/usr/bin/env python3
"""MCP Web Manager后端启动脚本."""

import sys
import os
import asyncio
import uvicorn

# 设置工作目录
os.chdir('/root/mcp-web-manager/backend')
sys.path.insert(0, '/root/mcp-web-manager/backend')

def main():
    """启动后端服务."""
    print("🚀 启动MCP Web Manager后端服务...")
    print("📍 工作目录:", os.getcwd())
    print("🌐 服务将运行在: http://0.0.0.0:8765")
    print("📚 API文档: http://0.0.0.0:8765/api/docs")
    print("🔗 WebSocket: ws://0.0.0.0:8765/ws")
    print("=" * 50)
    
    try:
        uvicorn.run(
            "main:app",
            host="0.0.0.0",
            port=8765,
            reload=True,
            log_level="info"
        )
    except KeyboardInterrupt:
        print("\n👋 服务已停止")
    except Exception as e:
        print(f"❌ 启动失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()