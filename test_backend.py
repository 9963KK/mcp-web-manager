#!/usr/bin/env python3
"""简单的后端功能测试脚本."""

import sys
import os
import asyncio

# 更改工作目录到backend
os.chdir('/root/mcp-web-manager/backend')
sys.path.insert(0, '/root/mcp-web-manager/backend')

async def test_basic_functionality():
    """测试基本功能."""
    print("🧪 测试MCP Web Manager后端基础功能...")
    
    try:
        # 测试导入
        print("📦 测试模块导入...")
        from models.models import MCPService, ServiceStatus, Base, SystemSettings
        from schemas import MCPServiceCreate
        print("✅ 模块导入成功")
        
        # 测试数据库配置
        print("🗄️ 测试数据库配置...")
        import os
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from sqlalchemy.pool import StaticPool
        
        DATABASE_URL = "sqlite:///./test_mcp_web_manager.db"
        engine = create_engine(
            DATABASE_URL,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
            echo=False
        )
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        
        # 创建表
        Base.metadata.create_all(bind=engine)
        print("✅ 数据库配置成功")
        
        # 测试数据库操作
        print("📊 测试数据库操作...")
        from database.crud import service_crud
        
        db = SessionLocal()
        
        # 创建测试服务
        test_service = MCPServiceCreate(
            name="test-service",
            description="测试服务",
            command="echo",
            args=["hello", "world"],
            env_vars={"TEST_VAR": "test_value"}
        )
        
        created_service = service_crud.create(db, test_service)
        print(f"✅ 创建服务成功: {created_service.name}")
        
        # 查询服务
        services = service_crud.get_all(db)
        print(f"✅ 查询服务成功，共 {len(services)} 个服务")
        
        # 删除测试服务
        service_crud.delete(db, created_service.id)
        print("✅ 删除服务成功")
        
        db.close()
        
        print("\n🎉 基础功能测试通过！")
        return True
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(test_basic_functionality())
    sys.exit(0 if success else 1)