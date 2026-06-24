import enum
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ProcessingStatus(str, enum.Enum):
    PENDING = "PENDING"
    SENT = "SENT"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    RATE_LIMITED = "RATE_LIMITED"
    INVALID_RECIPIENT = "INVALID_RECIPIENT"


class TicketLifecycleStatus(str, enum.Enum):
    OPEN = "OPEN"
    RESOLVED_CANDIDATE = "RESOLVED_CANDIDATE"
    CLOSED = "CLOSED"
    REOPENED = "REOPENED"
    SUPPRESSED = "SUPPRESSED"


class ProcessingLog(Base):
    __tablename__ = "processing_logs"
    __table_args__ = (UniqueConstraint("finding_id", name="uq_processing_logs_finding_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    finding_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    dedupe_key: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    scanner_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    ticket_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    ticket_status: Mapped[str | None] = mapped_column(String(80), nullable=True)
    lifecycle_status: Mapped[TicketLifecycleStatus] = mapped_column(
        Enum(TicketLifecycleStatus, name="ticket_lifecycle_status"),
        default=TicketLifecycleStatus.OPEN,
        nullable=False,
        index=True,
    )
    first_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_missing_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    seen_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    missing_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    priority: Mapped[str | None] = mapped_column(String(80), nullable=True)
    sla_target: Mapped[str | None] = mapped_column(String(80), nullable=True)
    sla_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    recipient_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    to_emails: Mapped[str | None] = mapped_column(Text, nullable=True)
    cc_emails: Mapped[str | None] = mapped_column(Text, nullable=True)
    email_subject: Mapped[str | None] = mapped_column(String(500), nullable=True)
    email_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[ProcessingStatus] = mapped_column(
        Enum(ProcessingStatus, name="processing_status"),
        default=ProcessingStatus.PENDING,
        nullable=False,
        index=True,
    )
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class SmtpSendEvent(Base):
    __tablename__ = "smtp_send_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    finding_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    recipient_email: Mapped[str] = mapped_column(String(320), nullable=False)
    to_emails: Mapped[str | None] = mapped_column(Text, nullable=True)
    cc_emails: Mapped[str | None] = mapped_column(Text, nullable=True)
    flow_type: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    delivery_mode: Mapped[str | None] = mapped_column(String(40), nullable=True)
    sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False, index=True
    )
