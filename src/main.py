from contextlib import asynccontextmanager

from fastapi import FastAPI

from config import get_settings
from database import init_database
from health import router as health_router
from logging_config import configure_logging
from scheduler import AppScheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    settings = get_settings()
    init_database()
    scheduler = AppScheduler(settings)
    app.state.scheduler = scheduler
    scheduler.start()
    try:
        yield
    finally:
        scheduler.shutdown()


app = FastAPI(
    title="DevSecOps Auto Ticket Notification Service",
    version="0.1.0",
    lifespan=lifespan,
)
app.include_router(health_router)
