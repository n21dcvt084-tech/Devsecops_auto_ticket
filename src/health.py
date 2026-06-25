"""Expose lightweight application and database health endpoints."""

from fastapi import APIRouter, Request, Response, status

from database import check_database_connection

router = APIRouter()


@router.get("/health")
def health_check(request: Request, response: Response) -> dict[str, str]:
    """Report application, database, and scheduler health."""
    scheduler = getattr(request.app.state, "scheduler", None)
    database_connected = check_database_connection()
    scheduler_running = scheduler is not None and scheduler.is_running()
    healthy = database_connected and scheduler_running
    if not healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {
        "status": "ok" if healthy else "error",
        "database": "connected" if database_connected else "disconnected",
        "scheduler": "running" if scheduler_running else "stopped",
    }


@router.get("/health/db")
def db_health_check(response: Response) -> dict[str, str]:
    """Report database connectivity only."""
    database_connected = check_database_connection()
    if not database_connected:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {"status": "ok" if database_connected else "error"}
