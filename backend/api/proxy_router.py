"""Dynamic reverse proxy routes for per-service MCP endpoints.

Exposes unified URLs:
  - /{name}/mcp[...]
  - /{name}/sse and /{name}/messages/

Requests are forwarded to the active internal instance of the service.
When a service is stopped, we mark it inactive so that proxy returns 503 quickly,
without waiting for process termination or port release.
"""

from __future__ import annotations

from typing import Any

import httpx
from fastapi.responses import StreamingResponse
import asyncio

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse, PlainTextResponse

from urllib.parse import urlparse
import re

from database import SessionLocal
from database.crud import service_crud, proxy_instance_crud
from models import ServiceStatus

router = APIRouter()


def _resolve_active_instance_by_name(name: str) -> dict[str, Any] | None:
    """Return the latest active proxy instance for the service name.
    Only returns when there exists an instance with is_active=True; otherwise None.
    This ensures that when stopping a service and marking instances inactive first,
    the proxy immediately returns 503 instead of forwarding to stale instances.
    """
    db = SessionLocal()
    try:
        service = service_crud.get_by_name(db, name)
        if not service:
            return None
        instances = proxy_instance_crud.get_by_service(db, service.id)
        if not instances:
            return None
        active = [i for i in instances if getattr(i, "is_active", False)]
        if not active:
            return None
        inst = max(active, key=lambda x: x.id)
        return {
            "host": getattr(inst, "host", "127.0.0.1"),
            "port": inst.port,
        }
    finally:
        db.close()


async def _forward_streamable_http(request: Request, target_base: str, tail: str) -> Response:
    method = request.method
    # Normalize root POST to /sessions like server-side logic
    normalized_tail = tail
    if method.upper() == "POST" and (tail == "" or tail == "/"):
        normalized_tail = "/sessions"

    url = f"{target_base}{normalized_tail}"

    # Build headers except host
    headers = {k: v for k, v in request.headers.items() if k.lower() != "host"}

    # Read body
    body = await request.body()

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.request(method, url, headers=headers, content=body)
        return Response(content=resp.content, status_code=resp.status_code, headers=dict(resp.headers))


@router.api_route("/{name}/mcp", methods=["POST", "OPTIONS"], include_in_schema=False)
@router.api_route("/{name}/mcp/{tail:path}", methods=["POST", "OPTIONS"], include_in_schema=False)
async def proxy_streamable_http(name: str, request: Request, tail: str = "") -> Response:
    target = _resolve_active_instance_by_name(name)
    if not target:
        return PlainTextResponse("Service not found or inactive", status_code=503)
    target_base = f"http://{target['host']}:{target['port']}/mcp"
    return await _forward_streamable_http(request, target_base, f"/{tail}" if tail else "")


@router.api_route("/{name}/sse", methods=["GET"], include_in_schema=False)
async def proxy_sse(name: str, request: Request) -> Response:
    # Stream SSE directly to the client to keep same origin and avoid redirects.
    target = _resolve_active_instance_by_name(name)
    if not target:
        return PlainTextResponse("Service not found or inactive", status_code=503)

    url = f"http://{target['host']}:{target['port']}/sse"

    async def _event_stream() -> asyncio.AsyncIterator[bytes]:
        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream("GET", url, headers={k: v for k, v in request.headers.items() if k.lower() != "host"}) as resp:
                # propagate non-200
                if resp.status_code != 200:
                    yield f"retry: 5000\n\n".encode()
                    return
                async for chunk in resp.aiter_bytes():
                    if chunk:
                        yield chunk

    return StreamingResponse(_event_stream(), media_type="text/event-stream")


@router.api_route("/{name}/messages/", methods=["POST"], include_in_schema=False)
@router.api_route("/{name}/messages/{path:path}", methods=["POST"], include_in_schema=False)
async def proxy_sse_messages(name: str, request: Request, path: str = "") -> Response:
    target = _resolve_active_instance_by_name(name)
    if not target:
        return PlainTextResponse("Service not found or inactive", status_code=503)

    # Preserve query string (e.g., ?session_id=...)
    qs = request.url.query
    tail = f"/{path}" if path else ""
    url = f"http://{target['host']}:{target['port']}/messages{tail}"
    if qs:
        url = f"{url}?{qs}"

    headers = {k: v for k, v in request.headers.items() if k.lower() != "host"}
    body = await request.body()

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(url, headers=headers, content=body)
        return Response(content=resp.content, status_code=resp.status_code, headers=dict(resp.headers))


    return StreamingResponse(_event_stream(), media_type="text/event-stream")


@router.api_route("/{name}/mcp", methods=["GET"], include_in_schema=False)
async def hint_get_streamable_http(name: str) -> Response:
    # 友好提示，避免 405 误导用户
    return JSONResponse({
        "message": "Use POST to this endpoint for MCP Streamable HTTP; GET is not supported.",
        "endpoint": f"/{name}/mcp",
        "method": "POST"
    })

