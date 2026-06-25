"""FastAPI entrypoint, logging setup, and application lifecycle management."""

from contextlib import asynccontextmanager
import logging
import sys

from fastapi import FastAPI

from config import get_settings
from health import router as health_router
from scheduler import AppScheduler


class ContextFormatter(logging.Formatter):
    """Append known DevSecOps context fields to each structured log line."""

    def format(self, record: logging.LogRecord) -> str:
        """Format the base log message and append available context values."""
        fields = {
            "finding_id": getattr(record, "finding_id", None),
            "product": getattr(record, "product", None),
            "severity": getattr(record, "severity", None),
            "recipient_email": getattr(record, "recipient_email", None),
            "dedupe_key": getattr(record, "dedupe_key", None),
            "ticket_id": getattr(record, "ticket_id", None),
            "missing_fields": getattr(record, "missing_fields", None),
            "status": getattr(record, "status", None),
            "error_message": getattr(record, "error_message", None),
        }
        context = " ".join(
            f"{key}={value}" for key, value in fields.items() if value is not None
        )
        message = super().format(record)
        return f"{message} {context}" if context else message


def configure_logging() -> None:
    """Configure process-wide logging to write structured lines to stdout."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        ContextFormatter(
            fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S%z",
        )
    )

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start the scheduler after deployment migrations have completed."""
    configure_logging()
    settings = get_settings()
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
