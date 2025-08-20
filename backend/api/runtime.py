"""Runtime maintenance endpoints: flush in-memory caches and optionally stop services."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from database import get_db
from services.mcp_manager import mcp_service_manager
# Import the in-memory session routing cache from the proxy router
from api.proxy_router import SESSION_TARGETS

router = APIRouter(prefix="/api/runtime", tags=["runtime"])


@router.post("/flush")
async def flush_runtime(
    stop_services: bool = Query(False, description="Whether to stop all running MCP services as part of the flush"),
    db: Session = Depends(get_db),
):
    """Flush runtime caches and optionally stop all running services.

    - Clears proxy session routing cache (SESSION_TARGETS)
    - Clears PortManager allocated ports
    - Optionally stops all services (cleanup_all)
    """
    sessions_before = len(SESSION_TARGETS)
    SESSION_TARGETS.clear()

    ports_before = len(mcp_service_manager.port_manager.allocated_ports)
    mcp_service_manager.port_manager.allocated_ports.clear()

    stopped_services = 0
    if stop_services:
        # Count roughly by running_services size
        stopped_services = len(mcp_service_manager.running_services)
        await mcp_service_manager.cleanup_all(db)

    return {
        "message": "runtime flushed",
        "session_targets_cleared": sessions_before,
        "ports_cleared": ports_before,
        "stopped_services": stopped_services if stop_services else 0,
    }

