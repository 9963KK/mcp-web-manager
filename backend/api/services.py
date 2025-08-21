"""API路由处理器 - MCP服务管理."""

from typing import List
import asyncio
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from database import get_db, SessionLocal
from database.crud import service_crud, status_log_crud, proxy_instance_crud
from schemas import (
    MCPServiceCreate,
    MCPServiceUpdate,
    MCPServiceResponse,
    ServiceActionRequest,
    ServiceListResponse,
    ServiceStatusLogResponse,
    ProxyInstanceResponse,
    BatchCreateServicesRequest,
    ImportResultResponse,
)
from services.mcp_manager import mcp_service_manager
from services import tools_cache
from websocket import event_broadcaster

router = APIRouter(prefix="/api/services", tags=["services"])


@router.get("/", response_model=ServiceListResponse)
async def list_services(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """获取所有MCP服务列表."""
    services = service_crud.get_all(db, skip=skip, limit=limit)
    stats = service_crud.get_stats(db)

    return ServiceListResponse(
        services=services,
        total=stats["total"],
        active_count=stats["active"],
        inactive_count=stats["inactive"],
        error_count=stats["error"]
    )


@router.get("/{service_id}", response_model=MCPServiceResponse)
async def get_service(service_id: int, db: Session = Depends(get_db)):
    """获取指定MCP服务详情."""
    service = service_crud.get_by_id(db, service_id)
    if not service:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="服务不存在"
        )
    return service


@router.post("/", response_model=MCPServiceResponse)
async def create_service(
    service: MCPServiceCreate,
    db: Session = Depends(get_db)
):
    """创建新的MCP服务."""
    # 检查服务名是否已存在
    existing_service = service_crud.get_by_name(db, service.name)
    if existing_service:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="服务名称已存在"
        )

    return service_crud.create(db, service)


@router.put("/{service_id}", response_model=MCPServiceResponse)
async def update_service(
    service_id: int,
    service_update: MCPServiceUpdate,
    db: Session = Depends(get_db)
):
    """更新MCP服务配置."""
    service = service_crud.get_by_id(db, service_id)
    if not service:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="服务不存在"
        )

    # 如果更新名称，检查是否与其他服务冲突
    if service_update.name and service_update.name != service.name:
        existing_service = service_crud.get_by_name(db, service_update.name)
        if existing_service:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="服务名称已存在"
            )

    updated_service = service_crud.update(db, service_id, service_update)
    return updated_service


@router.delete("/{service_id}")
async def delete_service(service_id: int, db: Session = Depends(get_db)):
    """删除MCP服务."""
    service = service_crud.get_by_id(db, service_id)
    if not service:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="服务不存在"
        )

    # 如果服务正在运行，先停止
    if service_id in mcp_service_manager.running_services:
        await mcp_service_manager.stop_service(db, service_id)

    success = service_crud.delete(db, service_id)
    if success:
        return {"message": "服务已删除"}
    else:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="删除服务失败"
        )


@router.post("/{service_id}/action")
async def service_action(
    service_id: int,
    action: ServiceActionRequest,
    db: Session = Depends(get_db)
):
    """执行服务操作（启动/停止/重启）."""
    service = service_crud.get_by_id(db, service_id)
    if not service:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="服务不存在"
        )

    success = False
    message = ""

    if action.action == "start":
        # 异步后台启动，快速响应，与停止保持一致
        async def _start_in_background(svc_id: int):
            local_db = SessionLocal()
            try:
                svc = service_crud.get_by_id(local_db, svc_id)
                if svc:
                    await mcp_service_manager.start_service(local_db, svc)
            finally:
                local_db.close()
        asyncio.create_task(_start_in_background(service_id))
        success, message = True, "启动指令已发送，正在启动..."
    elif action.action == "stop":
        # 异步后台停止，快速响应
        async def _stop_in_background(svc_id: int):
            local_db = SessionLocal()
            try:
                await mcp_service_manager.stop_service(local_db, svc_id)
            finally:
                local_db.close()

        asyncio.create_task(_stop_in_background(service_id))
        success, message = True, "停止指令已发送，正在停止..."
    elif action.action == "restart":
        success, message = await mcp_service_manager.restart_service(db, service)

    if success:
        return {"message": message}
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=message
        )


@router.get("/{service_id}/status")
async def get_service_status(service_id: int, db: Session = Depends(get_db)):
    """获取服务运行状态."""
    service = service_crud.get_by_id(db, service_id)
    if not service:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="服务不存在"
        )

    runtime_status = mcp_service_manager.get_service_status(service_id)

    return {
        "service_id": service_id,
        "name": service.name,
        "status": service.status,
        "runtime": runtime_status,
        "database_status": service.status,
        "manager_has_service": service_id in mcp_service_manager.running_services
    }


@router.get("/{service_id}/logs", response_model=List[ServiceStatusLogResponse])
async def get_service_logs(
    service_id: int,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    """获取服务状态日志."""
    service = service_crud.get_by_id(db, service_id)
    if not service:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="服务不存在"
        )

    logs = status_log_crud.get_by_service(db, service_id, limit)
    return logs


@router.get("/{service_id}/proxy-instances", response_model=List[ProxyInstanceResponse])
async def get_service_proxy_instances(
    service_id: int,
    db: Session = Depends(get_db)
):
    """获取服务的代理实例."""
    service = service_crud.get_by_id(db, service_id)
    if not service:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="服务不存在"
        )

    instances = proxy_instance_crud.get_by_service(db, service_id)
    return instances



@router.get("/{service_id}/tools/count")
async def get_service_tools_count(service_id: int, db: Session = Depends(get_db)):
    """探测服务包含的工具数量（通过StreamHTTP实时探测）。

    优化：
    - 增加进程内缓存，优先返回最近结果；过期则后台刷新
    - 成功探测后通过 WebSocket 广播，前端收到后更新并缓存
    - 只要存在活跃代理实例即可尝试探测
    """
    service = service_crud.get_by_id(db, service_id)
    if not service:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="服务不存在")

    # 无活跃实例：直接返回 0
    instances = proxy_instance_crud.get_by_service(db, service_id)
    active = [inst for inst in instances if getattr(inst, "is_active", False)]
    if not active:
        return {"count": 0, "status": service.status, "message": "无活跃代理实例或服务未运行"}

    # 命中缓存则快速返回，同时异步触发一次后台刷新（避免频繁阻塞）
    cached = tools_cache.get_count(service_id)
    if isinstance(cached, int):
        # 后台刷新（轻量重试）
        asyncio.create_task(_refresh_tools_count_background(service_id, db))
        return {"count": cached, "status": service.status, "cached": True}

    # 未命中缓存：执行一次探测，探测成功即缓存并广播
    count = await _probe_tools_count_for_service(service_id, db)
    return {"count": count, "status": service.status, "cached": False}


async def _probe_tools_count_for_service(service_id: int, db: Session) -> int:
    """执行实际探测并写入缓存，失败抛出 HTTPException。"""
    service = service_crud.get_by_id(db, service_id)
    instances = proxy_instance_crud.get_by_service(db, service_id)
    active = [inst for inst in instances if getattr(inst, "is_active", False)]
    inst = max(active, key=lambda x: x.id)

    target_host = getattr(inst, 'host', '127.0.0.1')
    if target_host in ("0.0.0.0", "::"):
        target_host = "127.0.0.1"
    base = f"http://{target_host}:{inst.port}"
    candidate_urls = [f"{base}/mcp/"]

    try:
        from mcp.client.session import ClientSession  # type: ignore
        from mcp.client.streamable_http import streamablehttp_client  # type: ignore
        from mcp.client.streamable_http import StreamableHTTPTransport  # type: ignore
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"MCP客户端依赖缺失: {e}") from e

    async def _probe_high(target_url: str) -> int:
        """优先使用高级客户端会话进行探测。"""
        async with streamablehttp_client(url=target_url) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = await session.list_tools()
                try:
                    return len(getattr(tools, "tools", tools) or [])
                except Exception:
                    return 0

    async def _probe_fallback(target_url: str) -> int:
        """降级方案：直接用底层 Transport 调用 tools/list。"""
        transport = StreamableHTTPTransport(target_url)
        try:
            await transport.connect()
            result = await transport.call_rpc("tools/list", {})
            # 兼容多种结构：{"tools": [...] } 或 直接列表
            try:
                arr = result.get("tools") if isinstance(result, dict) else result
                return len(arr or [])
            except Exception:
                return 0
        finally:
            try:
                await transport.close()
            except Exception:
                pass

    import asyncio
    last_err: Exception | None = None
    for _ in range(2):
        for u in candidate_urls:
            try:
                # 先高层，失败则尝试降级
                try:
                    c = await asyncio.wait_for(_probe_high(u), timeout=3.5)
                except Exception as e_high:  # noqa: BLE001
                    last_err = e_high
                    c = await asyncio.wait_for(_probe_fallback(u), timeout=3.5)
                tools_cache.set_count(service_id, int(c))
                # 广播到前端
                try:
                    await event_broadcaster.broadcast_service_event(
                        "tools_count",
                        service_id,
                        {"count": int(c)}
                    )
                except Exception:
                    pass
                return int(c)
            except asyncio.TimeoutError as e:
                last_err = e
            except Exception as e:
                last_err = e
                continue
        await asyncio.sleep(0.4)

    if isinstance(last_err, asyncio.TimeoutError):
        raise HTTPException(status_code=504, detail="探测工具数超时")
    raise HTTPException(status_code=502, detail=f"探测工具数失败: {last_err}")


async def _refresh_tools_count_background(service_id: int, db: Session) -> None:
    """后台刷新工具数：使用独立的 DB 会话，防止当前请求阻塞。"""
    try:
        local_db = SessionLocal()
        try:
            await _probe_tools_count_for_service(service_id, local_db)
        finally:
            local_db.close()
    except Exception:
        # 静默失败，保持缓存值
        pass


@router.post("/import", response_model=ImportResultResponse)
async def import_services(
    payload: dict,
    db: Session = Depends(get_db),
):
    """从 JSON 导入服务配置。

    - 支持直接传入 { services: MCPServiceCreate[] }
    - 支持 Claude Desktop 格式 { mcpServers: { name: { command, args, env } } }
    - 逐条创建，已存在同名服务将跳过
    """
    created = 0
    skipped = 0
    failed = 0
    errors: list[str] = []

    try:
        services_list: list[MCPServiceCreate] = []

        # 情况1: 标准批量结构
        if isinstance(payload, dict) and "services" in payload:
            parsed = BatchCreateServicesRequest(**payload)
            services_list = parsed.services

        # 情况2: mcp-proxy/Claude Desktop 常见结构 { mcpServers: { name: { command, args, env, ... } } }
        elif isinstance(payload, dict) and "mcpServers" in payload and isinstance(payload["mcpServers"], dict):
            for name, raw_cfg in payload["mcpServers"].items():
                if not isinstance(raw_cfg, dict):
                    continue
                # 兼容 enabled/disabled 两种写法
                if raw_cfg.get("enabled") is False:
                    continue
                if raw_cfg.get("disabled") is True:
                    continue

                command = raw_cfg.get("command")
                args = raw_cfg.get("args") or []
                env = raw_cfg.get("env") or raw_cfg.get("environment") or {}
                cwd = raw_cfg.get("cwd")
                if not command:
                    # 有些配置可能把整条命令放在 args 的第一个元素中（不符合规范），忽略
                    continue
                services_list.append(
                    MCPServiceCreate(
                        name=name,
                        description=f"Imported from mcpServers: {name}",
                        command=command,
                        args=args,
                        env_vars=env,
                        working_directory=cwd,
                    )
                )
        else:
            # 尝试将单对象视为一个服务
            try:
                single = MCPServiceCreate(**payload)
                services_list = [single]
            except Exception as e:  # noqa: BLE001
                raise HTTPException(status_code=400, detail=f"无法识别的导入格式: {e}")

        # 逐条写入
        for s in services_list:
            try:
                if service_crud.get_by_name(db, s.name):
                    skipped += 1
                    continue
                service_crud.create(db, s)
                created += 1
            except Exception as e:  # noqa: BLE001
                failed += 1
                errors.append(f"{s.name}: {e}")

        return ImportResultResponse(created=created, skipped=skipped, failed=failed, errors=errors)

    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"导入失败: {e}")