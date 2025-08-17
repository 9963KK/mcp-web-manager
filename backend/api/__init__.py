"""API routes module."""

from .services import router as services_router
from .config import router as config_router  
from .dashboard import router as dashboard_router

__all__ = ["services_router", "config_router", "dashboard_router"]