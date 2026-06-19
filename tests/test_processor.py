import sys
import json
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import models  # noqa: F401
from config import Settings
from database import Base
from models import ProcessingLog, ProcessingStatus
from processor import FindingProcessor
from schemas import DefectDojoFinding, EmailPayload, ManageEngineRequestResult, TicketAction
from sla import policy_for_severity


def build_settings(**overrides):
    values = {
        "DEFECTDOJO_BASE_URL": "https://dojo.example.com",
        "DEFECTDOJO_API_TOKEN": "token",
        "DATABASE_URL": "sqlite:///:memory:",
        "SMTP_HOST": "localhost",
        "SMTP_FROM_EMAIL": "devsecops@example.com",
        "MANAGEENGINE_DELIVERY_MODE": "api",
        "MANAGEENGINE_ENABLED": True,
        "MANAGEENGINE_DRY_RUN": True,
        "MANAGEENGINE_BASE_URL": "https://servicedesk.example.com",
        "PROJECT_EMAIL_MAPPING_FILE": "",
        "PROJECT_EMAIL_MAPPING_JSON": "",
        **overrides,
    }
    return Settings.model_validate(values)


def build_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


class FakeManageEngineClient:
    def __init__(self):
        self.created_payloads = []

    def create_request(self, payload):
        self.created_payloads.append(payload)
        return ManageEngineRequestResult(
            request_id=None,
            status="DRY_RUN",
            raw_response={"input_data": {"request": {"subject": payload.subject}}},
        )


def build_finding(finding_id: int) -> DefectDojoFinding:
    return DefectDojoFinding(
        finding_id=finding_id,
        title="SQL Injection",
        severity="Critical",
        product="Customer Portal",
        endpoint="app.example.com/login",
        parameter="username",
        description="SQL injection in login form",
        mitigation="Use parameterized queries",
        date="2026-06-12",
    )


def test_process_finding_api_dry_run_records_ticket_created_audit_log():
    db = build_session()
    processor = FindingProcessor(build_settings(), db)
    fake_manageengine = FakeManageEngineClient()
    processor.manageengine_client = fake_manageengine

    processor.process_finding(build_finding(100))

    record = db.scalar(select(ProcessingLog).where(ProcessingLog.finding_id == 100))
    assert record is not None
    assert record.status == ProcessingStatus.SENT
    assert record.ticket_status == "DRY_RUN"
    assert record.processed_at is not None
    assert record.dedupe_key is not None
    assert record.priority == "P1/Critical"
    assert record.sla_target == "7 days"
    assert len(fake_manageengine.created_payloads) == 1


def test_process_finding_skips_duplicate_dedupe_key_after_ticket_created():
    db = build_session()
    processor = FindingProcessor(build_settings(), db)
    fake_manageengine = FakeManageEngineClient()
    processor.manageengine_client = fake_manageengine

    processor.process_finding(build_finding(100))
    processor.process_finding(build_finding(200))

    first = db.scalar(select(ProcessingLog).where(ProcessingLog.finding_id == 100))
    duplicate = db.scalar(select(ProcessingLog).where(ProcessingLog.finding_id == 200))
    assert first is not None
    assert duplicate is not None
    assert first.status == ProcessingStatus.SENT
    assert duplicate.status == ProcessingStatus.SKIPPED
    assert duplicate.dedupe_key == first.dedupe_key
    assert "Duplicate issue skipped" in duplicate.error_message
    assert len(fake_manageengine.created_payloads) == 1


def test_email_payload_uses_project_mapping_routing_fields():
    mapping = {
        "projects": [
            {
                "project_name": "Customer Portal Security",
                "product_name": "Customer Portal",
                "email_destinations": ["appsec-ticket@example.com"],
                "cc_destinations": [
                    "customer-portal-team@example.com",
                    "appsec-ticket@example.com",
                ],
                "group": "Application Security",
                "category": "Security",
                "subcategory": "Web Vulnerability",
            }
        ]
    }
    db = build_session()
    processor = FindingProcessor(
        build_settings(
            MANAGEENGINE_DELIVERY_MODE="email_fetch",
            MANAGEENGINE_ENABLED=False,
            PROJECT_EMAIL_MAPPING_JSON=json.dumps(mapping),
        ),
        db,
    )
    finding = build_finding(100)

    project_mapping = processor._resolve_project_mapping(finding)
    recipient = processor._resolve_recipient(finding, project_mapping)
    cc_recipients = processor._resolve_cc_recipients(project_mapping, recipient)
    payload = processor._build_email_payload(
        finding=finding,
        recipient=recipient,
        dedupe_key="dd:test",
        sla_policy=policy_for_severity(finding.severity),
        ticket_action=TicketAction.CREATE,
        project_mapping=project_mapping,
        cc_recipients=cc_recipients,
    )

    assert str(payload.recipient_email) == "appsec-ticket@example.com"
    assert [str(email) for email in payload.cc_emails] == [
        "customer-portal-team@example.com"
    ]
    assert "Ticket Routing Fields" not in payload.body
    assert "- Group: Application Security" not in payload.body
    assert "- Category: Security" not in payload.body
    assert "- Subcategory: Web Vulnerability" not in payload.body
    assert "Ticket Routing Fields" not in payload.html_body
    assert "<strong>" not in payload.html_body


class RecordingSmtpClient:
    def __init__(self):
        self.sent_payloads = []

    def send(self, payload):
        self.sent_payloads.append(payload)


class RecordingRateLimiter:
    def __init__(self):
        self.sent_events = []

    def record_send(self, *, finding_id, recipient_email, cc_emails=None):
        self.sent_events.append(
            {
                "finding_id": finding_id,
                "recipient_email": recipient_email,
                "cc_emails": cc_emails,
            }
        )


class RecordingProcessingLogs:
    def __init__(self):
        self.sent_payload = None

    def get_by_finding_id(self, finding_id):
        return None

    def mark_sent(self, **kwargs):
        self.sent_payload = kwargs


def test_send_with_retry_sends_ticket_email_without_cc_then_alert_copy():
    processor = object.__new__(FindingProcessor)
    processor.settings = build_settings(SMTP_MAX_ATTEMPTS=1)
    processor.smtp_client = RecordingSmtpClient()
    processor.rate_limiter = RecordingRateLimiter()
    processor.processing_logs = RecordingProcessingLogs()
    payload = EmailPayload(
        finding_id=3282,
        recipient_email="ticket@example.com",
        cc_emails=["team@example.com", "lead@example.com"],
        subject="Security finding",
        body="Finding body",
        dedupe_key="dd:example",
    )

    processor._send_with_retry(payload)

    assert len(processor.smtp_client.sent_payloads) == 2
    ticket_email = processor.smtp_client.sent_payloads[0]
    alert_email = processor.smtp_client.sent_payloads[1]
    assert str(ticket_email.recipient_email) == "ticket@example.com"
    assert ticket_email.cc_emails == []
    assert str(alert_email.recipient_email) == "team@example.com"
    assert [str(email) for email in alert_email.cc_emails] == ["lead@example.com"]
    assert processor.processing_logs.sent_payload["recipient_email"] == "ticket@example.com"
    assert processor.processing_logs.sent_payload["cc_emails"] == (
        "team@example.com,lead@example.com"
    )
