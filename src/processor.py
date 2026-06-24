import json
import logging
import time
from pathlib import Path

from pydantic import EmailStr, TypeAdapter, ValidationError
from sqlalchemy.orm import Session

from config import Settings
from dedupe import build_dedupe_key
from defectdojo_client import DefectDojoClient
from email_template import build_ticket_content
from manageengine_client import ManageEngineClient
from manageengine_mapper import build_manageengine_payload
from models import ProcessingLog, ProcessingStatus
from rate_limiter import SmtpRateLimiter
from repositories import ProcessingLogRepository, SmtpRateLimitRepository
from retry import is_transient_smtp_error, retry_delay_seconds
from schemas import (
    DefectDojoFinding,
    EmailPayload,
    ProjectEmailMapping,
    ProjectEmailMappingConfig,
    SlaPolicy,
    TicketAction,
)
from sla import policy_for_severity
from smtp_client import SmtpClient

logger = logging.getLogger(__name__)
email_adapter = TypeAdapter(EmailStr)


def missing_ticket_fields(finding: DefectDojoFinding) -> list[str]:
    missing: list[str] = []
    if not finding.product:
        missing.append("product")
    if not finding.endpoint:
        missing.append("endpoint")
    if not finding.date:
        missing.append("date")
    if not (finding.impact or finding.description):
        missing.append("impact_or_description")
    if not finding.mitigation:
        missing.append("mitigation")
    return missing


class FindingProcessor:
    def __init__(self, settings: Settings, db: Session):
        self.settings = settings
        self.db = db
        self.processing_logs = ProcessingLogRepository(db)
        self.rate_limiter = SmtpRateLimiter(
            SmtpRateLimitRepository(db),
            settings.smtp_max_emails_per_minute,
            settings.smtp_max_emails_per_hour,
        )
        self.smtp_client = SmtpClient(settings)
        self.defectdojo_client = DefectDojoClient(settings)
        self.manageengine_client = ManageEngineClient(settings)
        self.project_email_mapping = self._load_project_email_mapping()

    def _log_missing_finding_fields(
        self, finding: DefectDojoFinding, dedupe_key: str
    ) -> None:
        missing_fields = missing_ticket_fields(finding)
        if not missing_fields:
            return

        logger.warning(
            "Finding missing recommended fields before ticket sync",
            extra={
                "finding_id": finding.finding_id,
                "dedupe_key": dedupe_key,
                "product": finding.product,
                "severity": finding.severity,
                "missing_fields": ",".join(missing_fields),
            },
        )

    def process_scheduler_cycle(self) -> None:
        logger.info("Scheduler cycle started")
        self.process_rate_limited_queue()

        try:
            findings = self.defectdojo_client.fetch_active_verified_findings()
        except Exception as error:
            logger.exception(
                "DefectDojo API call failed",
                extra={"error_message": str(error)},
            )
            return

        for finding in findings:
            self.process_finding(finding)

        logger.info("Scheduler cycle ended")

    def process_rate_limited_queue(self) -> None:
        queued_items = self.processing_logs.get_rate_limited_items()
        for item in queued_items:
            if not self.rate_limiter.quota_available():
                logger.info("Rate limit still active")
                break

            if not item.recipient_email or not item.email_subject or not item.email_body:
                self.processing_logs.mark_failed(
                    finding_id=item.finding_id,
                    recipient_email=item.recipient_email,
                    email_subject=item.email_subject,
                    email_body=item.email_body,
                    retry_count=item.retry_count,
                    error_message="Queued email payload is incomplete",
                    dedupe_key=item.dedupe_key,
                )
                continue

            queued_to_recipients = self._parse_email_list(item.to_emails)
            queued_cc_recipients = self._parse_email_list(item.cc_emails)
            payload = EmailPayload(
                finding_id=item.finding_id,
                recipient_email=item.recipient_email,
                to_emails=[
                    email
                    for email in queued_to_recipients
                    if email.lower() != item.recipient_email.lower()
                ],
                cc_emails=queued_cc_recipients,
                subject=item.email_subject,
                body=item.email_body,
                dedupe_key=item.dedupe_key,
                priority=item.priority,
                sla_target=item.sla_target,
                ticket_action=TicketAction.CREATE,
            )
            self._send_with_retry(
                payload,
                flow_type="ticket_email",
            )

    def process_finding(self, finding: DefectDojoFinding) -> None:
        dedupe_key = build_dedupe_key(finding)
        sla_policy = policy_for_severity(finding.severity)
        self._log_missing_finding_fields(finding, dedupe_key)
        existing = self.processing_logs.get_by_finding_id(finding.finding_id)
        dedupe_duplicate = self.processing_logs.get_sent_or_queued_by_dedupe_key(
            dedupe_key
        )

        self.processing_logs.mark_seen(
            finding_id=finding.finding_id,
            dedupe_key=dedupe_key,
            scanner_type=finding.scanner_type,
            priority=sla_policy.priority,
            sla_target=sla_policy.target,
            sla_due_at=sla_policy.due_at,
        )

        duplicate_record = self._select_duplicate_record(existing, dedupe_duplicate)
        if duplicate_record and duplicate_record.status == ProcessingStatus.SENT:
            if not existing or existing.status != ProcessingStatus.SENT:
                self.processing_logs.mark_skipped(
                    finding_id=finding.finding_id,
                    error_message=(
                        "Duplicate issue skipped because dedupe_key already has "
                        f"SENT finding_id={duplicate_record.finding_id}"
                    ),
                    dedupe_key=dedupe_key,
                    priority=sla_policy.priority,
                    sla_target=sla_policy.target,
                    sla_due_at=sla_policy.due_at,
                )
            logger.info(
                "Duplicate skipped",
                extra={
                    "finding_id": finding.finding_id,
                    "dedupe_key": dedupe_key,
                    "existing_finding_id": duplicate_record.finding_id,
                    "product": finding.product,
                    "severity": finding.severity,
                    "status": ProcessingStatus.SKIPPED.value,
                },
            )
            return

        if duplicate_record and duplicate_record.status == ProcessingStatus.RATE_LIMITED:
            logger.info(
                "Finding already queued due to rate limit",
                extra={
                    "finding_id": finding.finding_id,
                    "dedupe_key": dedupe_key,
                    "status": ProcessingStatus.RATE_LIMITED.value,
                },
            )
            return

        ticket_action = TicketAction.CREATE
        project_mapping = self._resolve_project_mapping(finding)
        if self._use_manageengine_api():
            ticket_synced = self._sync_manageengine_ticket(
                finding=finding,
                dedupe_key=dedupe_key,
                sla_policy=sla_policy,
                ticket_action=ticket_action,
            )
            if ticket_synced:
                self._send_notification_email(
                    finding=finding,
                    dedupe_key=dedupe_key,
                    sla_policy=sla_policy,
                    ticket_action=ticket_action,
                    project_mapping=project_mapping,
                )
            return

        ticket_mailbox = self._resolve_ticket_mailbox(finding, project_mapping)
        if not ticket_mailbox:
            self.processing_logs.mark_invalid_recipient(
                finding_id=finding.finding_id,
                error_message="No valid recipient from ticket_email or project mapping",
                dedupe_key=dedupe_key,
                priority=sla_policy.priority,
                sla_target=sla_policy.target,
                sla_due_at=sla_policy.due_at,
            )
            logger.info(
                "Invalid recipient",
                extra={
                    "finding_id": finding.finding_id,
                    "dedupe_key": dedupe_key,
                    "product": finding.product,
                    "severity": finding.severity,
                    "status": ProcessingStatus.INVALID_RECIPIENT.value,
                },
            )
            return

        ticket_payload = self._build_email_payload(
            finding=finding,
            recipient=ticket_mailbox,
            to_recipients=[],
            cc_recipients=[],
            dedupe_key=dedupe_key,
            sla_policy=sla_policy,
            ticket_action=ticket_action,
            project_mapping=project_mapping,
        )

        if not self.rate_limiter.quota_available():
            self.processing_logs.mark_rate_limited(
                finding_id=finding.finding_id,
                recipient_email=str(ticket_payload.recipient_email),
                to_emails=self._format_email_list(self._payload_to_recipients(ticket_payload)),
                cc_emails=self._format_email_list(ticket_payload.cc_emails),
                email_subject=ticket_payload.subject,
                email_body=ticket_payload.body,
                dedupe_key=dedupe_key,
                priority=sla_policy.priority,
                sla_target=sla_policy.target,
                sla_due_at=sla_policy.due_at,
            )
            logger.info(
                "Email queued",
                extra={
                    "finding_id": finding.finding_id,
                    "dedupe_key": dedupe_key,
                    "recipient_email": str(ticket_payload.recipient_email),
                    "status": ProcessingStatus.RATE_LIMITED.value,
                },
            )
            return

        ticket_sent = self._send_with_retry(
            ticket_payload,
            flow_type="ticket_email",
        )
        if ticket_sent:
            self._send_notification_email(
                finding=finding,
                dedupe_key=dedupe_key,
                sla_policy=sla_policy,
                ticket_action=ticket_action,
                project_mapping=project_mapping,
            )

    def _select_duplicate_record(
        self,
        existing: ProcessingLog | None,
        dedupe_duplicate: ProcessingLog | None,
    ) -> ProcessingLog | None:
        if existing and existing.status in (
            ProcessingStatus.SENT,
            ProcessingStatus.RATE_LIMITED,
        ):
            return existing
        if dedupe_duplicate:
            return dedupe_duplicate
        return existing

    def _use_manageengine_api(self) -> bool:
        return (
            self.settings.manageengine_enabled
            and self.settings.manageengine_delivery_mode == "api"
        )

    def _build_email_payload(
        self,
        *,
        finding: DefectDojoFinding,
        recipient: str,
        dedupe_key: str,
        sla_policy: SlaPolicy,
        ticket_action: TicketAction,
        project_mapping: ProjectEmailMapping | None = None,
        to_recipients: list[str] | None = None,
        cc_recipients: list[str] | None = None,
    ) -> EmailPayload:
        group = (
            project_mapping.group
            if project_mapping and project_mapping.group is not None
            else self.settings.manageengine_default_group
        )
        category = (
            project_mapping.category
            if project_mapping and project_mapping.category is not None
            else self.settings.manageengine_default_category
        )
        subcategory = (
            project_mapping.subcategory
            if project_mapping and project_mapping.subcategory is not None
            else self.settings.manageengine_default_subcategory
        )
        content = build_ticket_content(
            finding,
            self.settings.defectdojo_base_url,
            manageengine_public_url=(
                self.settings.manageengine_public_url
                or self.settings.manageengine_base_url
            ),
            dedupe_key=dedupe_key,
            sla_policy=sla_policy,
            ticket_action=ticket_action,
            group=group,
            category=category,
            subcategory=subcategory,
        )
        return EmailPayload(
            finding_id=content.finding_id,
            recipient_email=recipient,
            to_emails=to_recipients or [],
            cc_emails=cc_recipients or [],
            subject=content.subject,
            body=content.body,
            html_body=content.html_body,
            dedupe_key=content.dedupe_key,
            priority=content.priority,
            sla_target=content.sla_target,
            ticket_action=content.ticket_action,
        )

    def _sync_manageengine_ticket(
        self,
        *,
        finding: DefectDojoFinding,
        dedupe_key: str,
        sla_policy: SlaPolicy,
        ticket_action: TicketAction,
    ) -> bool:
        payload = build_manageengine_payload(
            finding=finding,
            settings=self.settings,
            dedupe_key=dedupe_key,
            sla_policy=sla_policy,
            ticket_action=ticket_action,
        )
        try:
            result = self.manageengine_client.create_request(payload)

            self.processing_logs.mark_ticket_created(
                finding_id=finding.finding_id,
                ticket_id=result.request_id,
                ticket_status=result.status,
                email_subject=payload.subject,
                email_body=payload.description,
                dedupe_key=dedupe_key,
                priority=sla_policy.priority,
                sla_target=sla_policy.target,
            )
            logger.info(
                "ManageEngine ticket synced",
                extra={
                    "finding_id": finding.finding_id,
                    "dedupe_key": dedupe_key,
                    "ticket_id": result.request_id,
                    "ticket_status": result.status,
                },
            )
            return True
        except Exception as error:
            self.processing_logs.mark_failed(
                finding_id=finding.finding_id,
                recipient_email=None,
                email_subject=payload.subject,
                email_body=payload.description,
                retry_count=0,
                error_message=str(error),
                dedupe_key=dedupe_key,
            )
            logger.exception(
                "ManageEngine ticket sync failed",
                extra={
                    "finding_id": finding.finding_id,
                    "dedupe_key": dedupe_key,
                    "error_message": str(error),
                },
            )
            return False

    def _send_with_retry(
        self,
        payload: EmailPayload,
        *,
        flow_type: str = "ticket_email",
        update_processing_log: bool = True,
        fail_processing_log: bool = True,
    ) -> bool:
        max_attempts = self.settings.smtp_max_attempts
        last_error: Exception | None = None

        attempts_made = 0
        for attempt in range(1, max_attempts + 1):
            attempts_made = attempt
            try:
                self.smtp_client.send(payload)
                self.rate_limiter.record_send(
                    finding_id=payload.finding_id,
                    recipient_email=str(payload.recipient_email),
                    to_emails=self._format_email_list(self._payload_to_recipients(payload)),
                    cc_emails=self._format_email_list(payload.cc_emails),
                    flow_type=flow_type,
                    delivery_mode=self.settings.manageengine_delivery_mode,
                )
                if update_processing_log:
                    self.processing_logs.mark_sent(
                        finding_id=payload.finding_id,
                        recipient_email=str(payload.recipient_email),
                        to_emails=self._format_email_list(
                            self._payload_to_recipients(payload)
                        ),
                        cc_emails=self._format_email_list(payload.cc_emails),
                        email_subject=payload.subject,
                        email_body=payload.body,
                        retry_count=attempt - 1,
                        dedupe_key=payload.dedupe_key,
                        priority=payload.priority,
                        sla_target=payload.sla_target,
                    )
                logger.info(
                    "Email sent",
                    extra={
                        "finding_id": payload.finding_id,
                        "dedupe_key": payload.dedupe_key,
                        "recipient_email": str(payload.recipient_email),
                        "to_emails": self._format_email_list(
                            self._payload_to_recipients(payload)
                        ),
                        "cc_emails": self._format_email_list(payload.cc_emails),
                        "flow_type": flow_type,
                        "status": ProcessingStatus.SENT.value,
                    },
                )
                return True
            except Exception as error:
                last_error = error
                logger.warning(
                    "SMTP send failed",
                    extra={
                        "finding_id": payload.finding_id,
                        "dedupe_key": payload.dedupe_key,
                        "recipient_email": str(payload.recipient_email),
                        "flow_type": flow_type,
                        "error_message": str(error),
                    },
                )
                if attempt >= max_attempts or not is_transient_smtp_error(error):
                    break

                delay = retry_delay_seconds(
                    attempt_number=attempt,
                    base_delay_seconds=self.settings.smtp_retry_delay_seconds,
                    backoff_multiplier=self.settings.smtp_retry_backoff_multiplier,
                )
                logger.info(
                    "Retry scheduled",
                    extra={
                        "finding_id": payload.finding_id,
                        "dedupe_key": payload.dedupe_key,
                        "recipient_email": str(payload.recipient_email),
                        "flow_type": flow_type,
                        "error_message": f"retry_after_seconds={delay}",
                    },
                )
                time.sleep(delay)

        if not fail_processing_log:
            logger.info(
                "Email flow failed without changing finding status",
                extra={
                    "finding_id": payload.finding_id,
                    "dedupe_key": payload.dedupe_key,
                    "recipient_email": str(payload.recipient_email),
                    "flow_type": flow_type,
                    "error_message": str(last_error) if last_error else "SMTP send failed",
                },
            )
            return False

        existing_log = self.processing_logs.get_by_finding_id(payload.finding_id)
        retry_count = max(
            existing_log.retry_count if existing_log else 0,
            attempts_made - 1,
        )
        self.processing_logs.mark_failed(
            finding_id=payload.finding_id,
            recipient_email=str(payload.recipient_email),
            to_emails=self._format_email_list(self._payload_to_recipients(payload)),
            cc_emails=self._format_email_list(payload.cc_emails),
            email_subject=payload.subject,
            email_body=payload.body,
            retry_count=retry_count,
            error_message=str(last_error) if last_error else "SMTP send failed",
            dedupe_key=payload.dedupe_key,
        )
        logger.info(
            "Processing status updated",
            extra={
                "finding_id": payload.finding_id,
                "dedupe_key": payload.dedupe_key,
                "recipient_email": str(payload.recipient_email),
                "flow_type": flow_type,
                "status": ProcessingStatus.FAILED.value,
                "error_message": str(last_error) if last_error else "SMTP send failed",
            },
        )
        return False

    def _send_notification_email(
        self,
        *,
        finding: DefectDojoFinding,
        dedupe_key: str,
        sla_policy: SlaPolicy,
        ticket_action: TicketAction,
        project_mapping: ProjectEmailMapping | None,
    ) -> None:
        to_recipients = self._resolve_notify_to_recipients(project_mapping)
        if not to_recipients:
            logger.info(
                "Notification email skipped because no to_destinations are configured",
                extra={
                    "finding_id": finding.finding_id,
                    "dedupe_key": dedupe_key,
                    "flow_type": "notify_email",
                },
            )
            return

        cc_recipients = self._resolve_cc_recipients(project_mapping, to_recipients)
        if not self.rate_limiter.quota_available():
            logger.warning(
                "Notification email skipped because SMTP rate limit is active",
                extra={
                    "finding_id": finding.finding_id,
                    "dedupe_key": dedupe_key,
                    "recipient_email": to_recipients[0],
                    "flow_type": "notify_email",
                },
            )
            return

        payload = self._build_email_payload(
            finding=finding,
            recipient=to_recipients[0],
            to_recipients=to_recipients[1:],
            cc_recipients=cc_recipients,
            dedupe_key=dedupe_key,
            sla_policy=sla_policy,
            ticket_action=ticket_action,
            project_mapping=project_mapping,
        )
        self._send_with_retry(
            payload,
            flow_type="notify_email",
            update_processing_log=False,
            fail_processing_log=False,
        )

    def _resolve_project_mapping(
        self, finding: DefectDojoFinding
    ) -> ProjectEmailMapping | None:
        if not finding.product:
            return None
        return self.project_email_mapping.get(finding.product.lower())

    def _resolve_recipient(
        self,
        finding: DefectDojoFinding,
        project_mapping: ProjectEmailMapping | None = None,
    ) -> str | None:
        ticket_email = self._validate_email(finding.ticket_email)
        if ticket_email:
            return ticket_email

        if not project_mapping:
            return None

        for destination in project_mapping.email_destinations:
            valid_destination = self._validate_email(destination)
            if valid_destination:
                return valid_destination
        return None

    def _resolve_ticket_recipients(
        self,
        finding: DefectDojoFinding,
        project_mapping: ProjectEmailMapping | None = None,
    ) -> list[str]:
        ticket_email = self._validate_email(finding.ticket_email)
        if ticket_email:
            return [ticket_email]

        if not project_mapping:
            return []

        recipients: list[str] = []
        seen: set[str] = set()
        for destination in project_mapping.email_destinations:
            valid_destination = self._validate_email(destination)
            if not valid_destination:
                continue
            normalized = valid_destination.lower()
            if normalized in seen:
                continue
            seen.add(normalized)
            recipients.append(valid_destination)
        return recipients

    def _resolve_email_fetch_to_recipients(
        self,
        finding: DefectDojoFinding,
        project_mapping: ProjectEmailMapping | None = None,
    ) -> list[str]:
        ticket_mailbox = self._resolve_ticket_mailbox(finding, project_mapping)
        if not ticket_mailbox:
            return []

        notify_recipients = self._resolve_notify_to_recipients(project_mapping)
        return self._dedupe_email_values([ticket_mailbox, *notify_recipients])

    def _resolve_ticket_mailbox(
        self,
        finding: DefectDojoFinding,
        project_mapping: ProjectEmailMapping | None = None,
    ) -> str | None:
        ticket_email = self._validate_email(finding.ticket_email)
        if ticket_email:
            return ticket_email

        if not project_mapping:
            return None

        ticket_mailbox = self._validate_email(project_mapping.ticket_mailbox)
        if ticket_mailbox:
            return ticket_mailbox

        for destination in project_mapping.email_destinations:
            valid_destination = self._validate_email(destination)
            if valid_destination:
                return valid_destination
        return None

    def _resolve_notify_to_recipients(
        self, project_mapping: ProjectEmailMapping | None
    ) -> list[str]:
        if not project_mapping:
            return []

        configured_destinations = (
            project_mapping.to_destinations or project_mapping.alert_destinations
        )
        return self._dedupe_email_values(configured_destinations)

    def _resolve_cc_recipients(
        self,
        project_mapping: ProjectEmailMapping | None,
        excluded_recipients: str | list[str],
    ) -> list[str]:
        if not project_mapping:
            return []

        recipients: list[str] = []
        if isinstance(excluded_recipients, str):
            seen = {excluded_recipients.lower()}
        else:
            seen = {recipient.lower() for recipient in excluded_recipients}
        for destination in project_mapping.cc_destinations:
            valid_destination = self._validate_email(destination)
            if not valid_destination:
                continue
            normalized = valid_destination.lower()
            if normalized in seen:
                continue
            seen.add(normalized)
            recipients.append(valid_destination)
        return recipients

    def _resolve_alert_recipients(
        self,
        project_mapping: ProjectEmailMapping | None,
        excluded_recipients: list[str],
    ) -> list[str]:
        if not project_mapping:
            return []

        configured_destinations = (
            project_mapping.alert_destinations or project_mapping.cc_destinations
        )
        recipients: list[str] = []
        seen = {recipient.lower() for recipient in excluded_recipients}
        for destination in configured_destinations:
            valid_destination = self._validate_email(destination)
            if not valid_destination:
                continue
            normalized = valid_destination.lower()
            if normalized in seen:
                continue
            seen.add(normalized)
            recipients.append(valid_destination)
        return recipients

    def _payload_to_recipients(self, payload: EmailPayload) -> list[str]:
        return self._dedupe_email_values(
            [str(payload.recipient_email), *[str(email) for email in payload.to_emails]]
        )

    def _dedupe_email_values(self, values: list[EmailStr] | list[str]) -> list[str]:
        recipients: list[str] = []
        seen: set[str] = set()
        for value in values:
            valid_value = self._validate_email(str(value))
            if not valid_value:
                continue
            normalized = valid_value.lower()
            if normalized in seen:
                continue
            seen.add(normalized)
            recipients.append(valid_value)
        return recipients

    def _format_email_list(self, values: list[EmailStr] | list[str]) -> str | None:
        if not values:
            return None
        return ",".join(str(value) for value in values)

    def _parse_email_list(self, value: str | None) -> list[str]:
        if not value:
            return []
        parsed: list[str] = []
        for item in value.split(","):
            valid_item = self._validate_email(item.strip())
            if valid_item:
                parsed.append(valid_item)
        return parsed

    def _validate_email(self, value: str | None) -> str | None:
        if not value:
            return None
        try:
            return str(email_adapter.validate_python(value))
        except ValidationError:
            return None

    def _load_project_email_mapping(self) -> dict[str, ProjectEmailMapping]:
        merged: dict[str, ProjectEmailMapping] = {}

        if self.settings.project_email_mapping_file:
            path = Path(self.settings.project_email_mapping_file)
            if path.exists():
                file_mapping = ProjectEmailMappingConfig.model_validate_json(
                    path.read_text(encoding="utf-8")
                )
                for project in file_mapping.projects:
                    merged[project.product_name.lower()] = project

        if self.settings.project_email_mapping_json:
            raw_mapping = json.loads(self.settings.project_email_mapping_json)
            json_mapping = ProjectEmailMappingConfig.model_validate(raw_mapping)
            for project in json_mapping.projects:
                merged[project.product_name.lower()] = project

        return merged
