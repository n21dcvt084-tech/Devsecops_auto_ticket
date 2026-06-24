from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from models import (
    ProcessingLog,
    ProcessingStatus,
    SmtpSendEvent,
    TicketLifecycleStatus,
    utc_now,
)


class ProcessingLogRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_finding_id(self, finding_id: int) -> ProcessingLog | None:
        return self.db.scalar(
            select(ProcessingLog).where(ProcessingLog.finding_id == finding_id)
        )

    def get_by_dedupe_key(self, dedupe_key: str) -> ProcessingLog | None:
        return self.db.scalar(
            select(ProcessingLog)
            .where(ProcessingLog.dedupe_key == dedupe_key)
            .order_by(ProcessingLog.updated_at.desc())
            .limit(1)
        )

    def get_sent_or_queued_by_dedupe_key(self, dedupe_key: str) -> ProcessingLog | None:
        return self.db.scalar(
            select(ProcessingLog)
            .where(ProcessingLog.dedupe_key == dedupe_key)
            .where(
                ProcessingLog.status.in_(
                    [ProcessingStatus.SENT, ProcessingStatus.RATE_LIMITED]
                )
            )
            .order_by(ProcessingLog.updated_at.desc())
            .limit(1)
        )

    def get_rate_limited_items(self, limit: int = 100) -> list[ProcessingLog]:
        return list(
            self.db.scalars(
                select(ProcessingLog)
                .where(ProcessingLog.status == ProcessingStatus.RATE_LIMITED)
                .order_by(ProcessingLog.updated_at.asc())
                .limit(limit)
            )
        )

    def mark_seen(
        self,
        *,
        finding_id: int,
        dedupe_key: str,
        scanner_type: str | None,
        priority: str | None,
        sla_target: str | None,
        sla_due_at: datetime | None,
    ) -> ProcessingLog:
        record = self.get_by_finding_id(finding_id)
        now = utc_now()
        if record is None:
            record = ProcessingLog(finding_id=finding_id, first_seen_at=now)
            self.db.add(record)

        if record.first_seen_at is None:
            record.first_seen_at = now
        record.last_seen_at = now
        record.seen_count = (record.seen_count or 0) + 1
        record.missing_count = 0
        record.last_missing_at = None
        record.dedupe_key = dedupe_key
        record.scanner_type = scanner_type
        record.priority = priority
        record.sla_target = sla_target
        record.sla_due_at = sla_due_at
        if record.lifecycle_status != TicketLifecycleStatus.SUPPRESSED:
            record.lifecycle_status = TicketLifecycleStatus.OPEN
        record.updated_at = now
        self.db.commit()
        self.db.refresh(record)
        return record

    def upsert_status(
        self,
        *,
        finding_id: int,
        status: ProcessingStatus,
        recipient_email: str | None = None,
        to_emails: str | None = None,
        cc_emails: str | None = None,
        email_subject: str | None = None,
        email_body: str | None = None,
        retry_count: int | None = None,
        error_message: str | None = None,
        processed_at: datetime | None = None,
        dedupe_key: str | None = None,
        priority: str | None = None,
        sla_target: str | None = None,
        sla_due_at: datetime | None = None,
        lifecycle_status: TicketLifecycleStatus | None = None,
    ) -> ProcessingLog:
        record = self.get_by_finding_id(finding_id)
        now = utc_now()
        if record is None:
            record = ProcessingLog(finding_id=finding_id, first_seen_at=now)
            self.db.add(record)

        record.status = status
        record.recipient_email = recipient_email
        record.to_emails = to_emails
        record.cc_emails = cc_emails
        record.email_subject = email_subject
        record.email_body = email_body
        if retry_count is not None:
            record.retry_count = retry_count
        record.error_message = error_message
        record.processed_at = processed_at
        if dedupe_key is not None:
            record.dedupe_key = dedupe_key
        if priority is not None:
            record.priority = priority
        if sla_target is not None:
            record.sla_target = sla_target
        if sla_due_at is not None:
            record.sla_due_at = sla_due_at
        if lifecycle_status is not None:
            record.lifecycle_status = lifecycle_status
        if record.first_seen_at is None:
            record.first_seen_at = now
        record.last_seen_at = now
        record.updated_at = now
        self.db.commit()
        self.db.refresh(record)
        return record

    def mark_sent(
        self,
        *,
        finding_id: int,
        recipient_email: str,
        to_emails: str | None,
        cc_emails: str | None,
        email_subject: str,
        email_body: str,
        retry_count: int,
        dedupe_key: str | None = None,
        priority: str | None = None,
        sla_target: str | None = None,
        sla_due_at: datetime | None = None,
    ) -> ProcessingLog:
        return self.upsert_status(
            finding_id=finding_id,
            status=ProcessingStatus.SENT,
            recipient_email=recipient_email,
            to_emails=to_emails,
            cc_emails=cc_emails,
            email_subject=email_subject,
            email_body=email_body,
            retry_count=retry_count,
            error_message=None,
            processed_at=utc_now(),
            dedupe_key=dedupe_key,
            priority=priority,
            sla_target=sla_target,
            sla_due_at=sla_due_at,
            lifecycle_status=TicketLifecycleStatus.OPEN,
        )

    def mark_failed(
        self,
        *,
        finding_id: int,
        recipient_email: str | None,
        email_subject: str | None,
        email_body: str | None,
        retry_count: int,
        error_message: str,
        to_emails: str | None = None,
        cc_emails: str | None = None,
        dedupe_key: str | None = None,
    ) -> ProcessingLog:
        return self.upsert_status(
            finding_id=finding_id,
            status=ProcessingStatus.FAILED,
            recipient_email=recipient_email,
            to_emails=to_emails,
            cc_emails=cc_emails,
            email_subject=email_subject,
            email_body=email_body,
            retry_count=retry_count,
            error_message=error_message,
            processed_at=utc_now(),
            dedupe_key=dedupe_key,
        )

    def mark_rate_limited(
        self,
        *,
        finding_id: int,
        recipient_email: str,
        to_emails: str | None,
        cc_emails: str | None,
        email_subject: str,
        email_body: str,
        dedupe_key: str | None = None,
        priority: str | None = None,
        sla_target: str | None = None,
        sla_due_at: datetime | None = None,
    ) -> ProcessingLog:
        return self.upsert_status(
            finding_id=finding_id,
            status=ProcessingStatus.RATE_LIMITED,
            recipient_email=recipient_email,
            to_emails=to_emails,
            cc_emails=cc_emails,
            email_subject=email_subject,
            email_body=email_body,
            retry_count=0,
            error_message="SMTP rate limit exceeded",
            processed_at=None,
            dedupe_key=dedupe_key,
            priority=priority,
            sla_target=sla_target,
            sla_due_at=sla_due_at,
        )

    def mark_invalid_recipient(
        self,
        *,
        finding_id: int,
        error_message: str,
        dedupe_key: str | None = None,
        priority: str | None = None,
        sla_target: str | None = None,
        sla_due_at: datetime | None = None,
    ) -> ProcessingLog:
        return self.upsert_status(
            finding_id=finding_id,
            status=ProcessingStatus.INVALID_RECIPIENT,
            error_message=error_message,
            processed_at=utc_now(),
            dedupe_key=dedupe_key,
            priority=priority,
            sla_target=sla_target,
            sla_due_at=sla_due_at,
        )

    def mark_skipped(
        self,
        *,
        finding_id: int,
        error_message: str,
        dedupe_key: str | None = None,
        priority: str | None = None,
        sla_target: str | None = None,
        sla_due_at: datetime | None = None,
    ) -> ProcessingLog:
        return self.upsert_status(
            finding_id=finding_id,
            status=ProcessingStatus.SKIPPED,
            error_message=error_message,
            processed_at=utc_now(),
            dedupe_key=dedupe_key,
            priority=priority,
            sla_target=sla_target,
            sla_due_at=sla_due_at,
        )

    def mark_ticket_created(
        self,
        *,
        finding_id: int,
        ticket_id: str | None,
        ticket_status: str | None,
        email_subject: str | None,
        email_body: str | None,
        dedupe_key: str | None = None,
        priority: str | None = None,
        sla_target: str | None = None,
        error_message: str | None = None,
    ) -> ProcessingLog:
        record = self.upsert_status(
            finding_id=finding_id,
            status=ProcessingStatus.SENT,
            email_subject=email_subject,
            email_body=email_body,
            retry_count=0,
            error_message=error_message,
            processed_at=utc_now(),
            dedupe_key=dedupe_key,
            priority=priority,
            sla_target=sla_target,
            lifecycle_status=TicketLifecycleStatus.OPEN,
        )
        record.ticket_id = ticket_id
        record.ticket_status = ticket_status
        record.updated_at = utc_now()
        self.db.commit()
        self.db.refresh(record)
        return record


class SmtpRateLimitRepository:
    def __init__(self, db: Session):
        self.db = db

    def count_since(self, since: datetime) -> int:
        return int(
            self.db.scalar(
                select(func.count(SmtpSendEvent.id)).where(SmtpSendEvent.sent_at >= since)
            )
            or 0
        )

    def current_counts(self) -> tuple[int, int]:
        now = datetime.now(timezone.utc)
        minute_count = self.count_since(now - timedelta(minutes=1))
        hour_count = self.count_since(now - timedelta(hours=1))
        return minute_count, hour_count

    def record_send(
        self,
        *,
        finding_id: int,
        recipient_email: str,
        to_emails: str | None = None,
        cc_emails: str | None = None,
        flow_type: str | None = None,
        delivery_mode: str | None = None,
    ) -> SmtpSendEvent:
        event = SmtpSendEvent(
            finding_id=finding_id,
            recipient_email=recipient_email,
            to_emails=to_emails,
            cc_emails=cc_emails,
            flow_type=flow_type,
            delivery_mode=delivery_mode,
        )
        self.db.add(event)
        self.db.commit()
        self.db.refresh(event)
        return event
