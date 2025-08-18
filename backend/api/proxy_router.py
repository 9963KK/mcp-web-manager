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
# Cache session_id -> target instance mapping to route /messages requests
SESSION_TARGETS: dict[str, dict[str, Any]] = {}



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
        # If this is a session creation, cache the target for later /messages routing
        if resp.status_code in (200, 202):
            try:
                import json
                data = json.loads(resp.content.decode("utf-8")) if resp.content else {}
                session_id = data.get("id") or data.get("sessionId")
                if session_id:
                    SESSION_TARGETS[session_id] = {"host": target_base.split("://",1)[1].split(":")[0], "port": int(target_base.split(":")[-1].split("/")[0])}
            except Exception:
                pass
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
    # Prefer routing by session_id to ensure we hit the same backend instance
    qs = request.url.query
    from urllib.parse import parse_qs
    params = parse_qs(qs)
    session_id = (params.get("session_id", [None])[0]) if qs else None

    target = None
    if session_id and session_id in SESSION_TARGETS:
        target = SESSION_TARGETS[session_id]
    else:
        target = _resolve_active_instance_by_name(name)
    if not target:
        return PlainTextResponse("Service not found or inactive", status_code=503)

    tail = f"/{path}" if path else ""
    url = f"http://{target['host']}:{target['port']}/messages{tail}"
    if qs:
        url = f"{url}?{qs}"

    headers = {k: v for k, v in request.headers.items() if k.lower() != "host"}
    body = await request.body()

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(url, headers=headers, content=body)
        return Response(content=resp.content, status_code=resp.status_code, headers=dict(resp.headers))

# Root-level /messages proxy for clients that post to absolute '/messages/'
@router.api_route("/messages/", methods=["POST"], include_in_schema=False)
@router.api_route("/messages/{path:path}", methods=["POST"], include_in_schema=False)
async def proxy_sse_messages_root(request: Request, path: str = "") -> Response:
    from urllib.parse import parse_qs
    qs = request.url.query
    params = parse_qs(qs)
    session_id = (params.get("session_id", [None])[0]) if qs else None
    if not session_id:
        return PlainTextResponse("Missing session_id", status_code=400)

    # 1) Try cached mapping
    target = SESSION_TARGETS.get(session_id)
    headers = {k: v for k, v in request.headers.items() if k.lower() != "host"}
    body = await request.body()
    tail = f"/{path}" if path else ""

    async def _forward_to(host: str, port: int) -> Response:
        url = f"http://{host}:{port}/messages{tail}"
        url = f"{url}?{qs}" if qs else url
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(url, headers=headers, content=body)
            return Response(content=resp.content, status_code=resp.status_code, headers=dict(resp.headers))

    if target:
        resp = await _forward_to(target["host"], target["port"])
        if resp.status_code < 400:
            return resp
        # fallback to probing

    # 2) Probe all active instances
    db = SessionLocal()
    try:
        instances = proxy_instance_crud.get_active(db)
        for inst in instances:
            host = getattr(inst, "host", "127.0.0.1")
            port = inst.port
            resp = await _forward_to(host, port)
            if resp.status_code < 400:
                SESSION_TARGETS[session_id] = {"host": host, "port": port}
                return resp
        return PlainTextResponse("Session not found on any active instance", status_code=404)
    finally:
        db.close()



@router.api_route("/{name}/mcp", methods=["GET"], include_in_schema=False)
async def hint_get_streamable_http(name: str) -> Response:
    # 友好提示，避免 405 误导用户
    return JSONResponse({
        "message": "Use POST to this endpoint for MCP Streamable HTTP; GET is not supported.",
        "endpoint": f"/{name}/mcp",
        "method": "POST"
    })

