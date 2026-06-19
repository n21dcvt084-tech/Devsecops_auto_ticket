from fastapi import APIRouter, Request

from database import check_database_connection

router = APIRouter()


@router.get("/health")
def health_check(request: Request) -> dict[str, str]:
    scheduler = getattr(request.app.state, "scheduler", None)
    return {
        "status": "ok",
        "database": "connected" if check_database_connection() else "disconnected",
        "scheduler": "running"
        if scheduler is not None and scheduler.is_running()
        else "stopped",
    }


@router.get("/health/db")
def db_health_check() -> dict[str, str]:
    return {"status": "ok" if check_database_connection() else "error"}
