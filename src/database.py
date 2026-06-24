from collections.abc import Generator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from config import get_settings


class Base(DeclarativeBase):
    pass


_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_engine(settings.database_url, pool_pre_ping=True)
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(
            bind=get_engine(), autoflush=False, autocommit=False
        )
    return _session_factory


def init_database() -> None:
    import models  # noqa: F401

    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    _apply_lightweight_migrations()


def _apply_lightweight_migrations() -> None:
    engine = get_engine()
    inspector = inspect(engine)
    if "processing_logs" not in inspector.get_table_names():
        return

    existing_columns = {column["name"] for column in inspector.get_columns("processing_logs")}
    migrations = {
        "dedupe_key": "ALTER TABLE processing_logs ADD COLUMN dedupe_key VARCHAR(80)",
        "scanner_type": "ALTER TABLE processing_logs ADD COLUMN scanner_type VARCHAR(120)",
        "ticket_id": "ALTER TABLE processing_logs ADD COLUMN ticket_id VARCHAR(120)",
        "ticket_status": "ALTER TABLE processing_logs ADD COLUMN ticket_status VARCHAR(80)",
        "lifecycle_status": "ALTER TABLE processing_logs ADD COLUMN lifecycle_status VARCHAR(40) DEFAULT 'OPEN' NOT NULL",
        "first_seen_at": "ALTER TABLE processing_logs ADD COLUMN first_seen_at TIMESTAMP WITH TIME ZONE",
        "last_seen_at": "ALTER TABLE processing_logs ADD COLUMN last_seen_at TIMESTAMP WITH TIME ZONE",
        "last_missing_at": "ALTER TABLE processing_logs ADD COLUMN last_missing_at TIMESTAMP WITH TIME ZONE",
        "seen_count": "ALTER TABLE processing_logs ADD COLUMN seen_count INTEGER DEFAULT 0 NOT NULL",
        "missing_count": "ALTER TABLE processing_logs ADD COLUMN missing_count INTEGER DEFAULT 0 NOT NULL",
        "priority": "ALTER TABLE processing_logs ADD COLUMN priority VARCHAR(80)",
        "sla_target": "ALTER TABLE processing_logs ADD COLUMN sla_target VARCHAR(80)",
        "sla_due_at": "ALTER TABLE processing_logs ADD COLUMN sla_due_at TIMESTAMP WITH TIME ZONE",
        "to_emails": "ALTER TABLE processing_logs ADD COLUMN to_emails TEXT",
        "cc_emails": "ALTER TABLE processing_logs ADD COLUMN cc_emails TEXT",
    }

    with engine.begin() as connection:
        for column_name, ddl in migrations.items():
            if column_name not in existing_columns:
                connection.execute(text(ddl))
        connection.execute(
            text("CREATE INDEX IF NOT EXISTS ix_processing_logs_dedupe_key ON processing_logs (dedupe_key)")
        )
        connection.execute(
            text("CREATE INDEX IF NOT EXISTS ix_processing_logs_lifecycle_status ON processing_logs (lifecycle_status)")
        )
        connection.execute(
            text("CREATE INDEX IF NOT EXISTS ix_processing_logs_ticket_id ON processing_logs (ticket_id)")
        )

    if "smtp_send_events" not in inspector.get_table_names():
        return

    existing_smtp_columns = {
        column["name"] for column in inspector.get_columns("smtp_send_events")
    }
    smtp_migrations = {
        "to_emails": "ALTER TABLE smtp_send_events ADD COLUMN to_emails TEXT",
        "cc_emails": "ALTER TABLE smtp_send_events ADD COLUMN cc_emails TEXT",
        "flow_type": "ALTER TABLE smtp_send_events ADD COLUMN flow_type VARCHAR(80)",
        "delivery_mode": "ALTER TABLE smtp_send_events ADD COLUMN delivery_mode VARCHAR(40)",
    }
    with engine.begin() as connection:
        for column_name, ddl in smtp_migrations.items():
            if column_name not in existing_smtp_columns:
                connection.execute(text(ddl))
        connection.execute(
            text("CREATE INDEX IF NOT EXISTS ix_smtp_send_events_flow_type ON smtp_send_events (flow_type)")
        )


def get_db_session() -> Generator[Session, None, None]:
    db = get_session_factory()()
    try:
        yield db
    finally:
        db.close()


def check_database_connection() -> bool:
    try:
        with get_engine().connect() as connection:
            connection.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
