import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from config import Settings
from email_template import build_ticket_content
from manageengine_mapper import build_manageengine_payload, map_manageengine_priority
from processor import FindingProcessor, missing_ticket_fields
from schemas import DefectDojoFinding, EmailPayload, TicketAction
from manageengine_mapper import policy_for_severity


def build_settings(**overrides):
    values = {
        "DEFECTDOJO_BASE_URL": "https://dojo.example.com",
        "DEFECTDOJO_API_TOKEN": "token",
        "DATABASE_URL": "postgresql://user:pass@localhost/db",
        "SMTP_HOST": "localhost",
        "SMTP_FROM_EMAIL": "devsecops@example.com",
        "MANAGEENGINE_REQUESTER_NAME": "DevSecOps Automation",
        "MANAGEENGINE_DELIVERY_MODE": "email_fetch",
        "MANAGEENGINE_DEFAULT_GROUP": "DevSecOps",
        "MANAGEENGINE_DEFAULT_CATEGORY": "Security",
        "MANAGEENGINE_DEFAULT_SUBCATEGORY": "Vulnerability",
        **overrides,
    }
    return Settings.model_validate(values)


def test_mapper_builds_payload_from_finding_and_phase2_fields():
    finding = DefectDojoFinding(
        finding_id=3282,
        title="SQL Injection",
        severity="Critical",
        product="canhvp-demo",
        endpoint="app.example.com/login",
    )
    sla_policy = policy_for_severity(finding.severity)

    payload = build_manageengine_payload(
        finding=finding,
        settings=build_settings(),
        dedupe_key="dd:example",
        sla_policy=sla_policy,
        ticket_action=TicketAction.CREATE,
    )

    assert payload.finding_id == 3282
    assert payload.ticket_action == TicketAction.CREATE
    assert payload.priority == "High"
    assert payload.sla_target == "7 days"
    assert payload.group == "DevSecOps"
    assert payload.category == "Security"
    assert payload.subcategory == "Vulnerability"
    assert "Ticket Routing Fields" not in payload.description
    assert "- Group: DevSecOps" not in payload.description
    assert "- Category: Security" not in payload.description
    assert "- Subcategory: Vulnerability" not in payload.description
    assert "- Priority: P1/Critical" not in payload.description
    assert "- SLA Target: 7 days" not in payload.description
    assert "Dedupe Key: dd:example" in payload.impact_details
    assert "https://dojo.example.com/finding/3282" in payload.description
    assert "Finding ID: 3282" in payload.impact_details


def test_mapper_uses_same_subject_and_body_as_email_ticket_content():
    finding = DefectDojoFinding(
        finding_id=3282,
        title="SQL Injection",
        severity="Critical",
        product="canhvp-demo",
        endpoint="app.example.com/login",
    )
    settings = build_settings()
    sla_policy = policy_for_severity(finding.severity)

    content = build_ticket_content(
        finding,
        settings.defectdojo_base_url,
        dedupe_key="dd:example",
        sla_policy=sla_policy,
        ticket_action=TicketAction.CREATE,
        group=settings.manageengine_default_group,
        category=settings.manageengine_default_category,
        subcategory=settings.manageengine_default_subcategory,
    )
    payload = build_manageengine_payload(
        finding=finding,
        settings=settings,
        dedupe_key="dd:example",
        sla_policy=sla_policy,
        ticket_action=TicketAction.CREATE,
    )

    assert payload.subject == content.subject
    assert payload.description == content.body
    assert payload.priority == "High"
    assert content.priority == "P1/Critical"
    assert payload.sla_target == content.sla_target


def test_mapper_converts_internal_sla_priority_to_manageengine_priority_name():
    assert map_manageengine_priority("P1/Critical") == "High"
    assert map_manageengine_priority("P2/High") == "High"
    assert map_manageengine_priority("P3/Medium") == "Medium"
    assert map_manageengine_priority("P4/Low") == "Low"


def test_critical_maps_to_p1_7_days():
    policy = policy_for_severity("Critical")

    assert policy.priority == "P1/Critical"
    assert policy.target == "7 days"
    assert policy.due_at is not None


def test_low_maps_to_p4_60_to_90_days():
    policy = policy_for_severity("Low")

    assert policy.priority == "P4/Low"
    assert policy.target == "60 - 90 days"


def test_manageengine_delivery_mode_defaults_to_email_fetch():
    settings = build_settings()

    assert settings.manageengine_delivery_mode == "email_fetch"


def test_manageengine_delivery_mode_accepts_api():
    settings = build_settings(
        MANAGEENGINE_DELIVERY_MODE="api",
    )

    assert settings.manageengine_delivery_mode == "api"


def processor_without_init():
    return object.__new__(FindingProcessor)


class FailingSmtpClient:
    def send(self, payload):
        raise ValueError("bad recipient")


class NoopRateLimiter:
    def quota_available(self):
        return True

    def record_send(self, *, finding_id, recipient_email):
        raise AssertionError("record_send should not run after SMTP failure")


class FakeProcessingLogs:
    def __init__(self):
        self.failed_payload = None

    def get_by_finding_id(self, finding_id):
        return None

    def mark_failed(self, **kwargs):
        self.failed_payload = kwargs


def test_current_ticket_lifecycle_scope_is_create_or_skip_only():
    assert not hasattr(FindingProcessor, "_should_reopen_duplicate")
    assert not hasattr(FindingProcessor, "_ticket_action_for_duplicate")


def test_missing_ticket_fields_reports_optional_defectdojo_gaps():
    finding = DefectDojoFinding(
        finding_id=3282,
        title="SQL Injection",
        severity="Critical",
        product="canhvp-demo",
    )

    assert missing_ticket_fields(finding) == [
        "impact_or_description",
        "mitigation",
    ]


def test_processor_logs_missing_finding_fields(caplog):
    finding = DefectDojoFinding(
        finding_id=3282,
        title="SQL Injection",
        severity="Critical",
        product="canhvp-demo",
    )
    processor = processor_without_init()

    with caplog.at_level("WARNING"):
        processor._log_missing_finding_fields(finding, "dd:example")

    assert "Finding missing recommended fields before ticket sync" in caplog.text
    record = caplog.records[0]
    assert record.finding_id == 3282
    assert record.dedupe_key == "dd:example"
    assert record.missing_fields == "impact_or_description,mitigation"


def test_send_with_retry_marks_failed_when_smtp_failure_is_not_transient():
    processor = processor_without_init()
    processor.settings = build_settings(SMTP_MAX_ATTEMPTS=3)
    processor.smtp_client = FailingSmtpClient()
    processor.rate_limiter = NoopRateLimiter()
    processor.processing_logs = FakeProcessingLogs()
    payload = EmailPayload(
        finding_id=3282,
        recipient_email="ticket@example.com",
        subject="Security finding",
        body="Finding body",
        dedupe_key="dd:example",
    )

    processor._send_with_retry(payload)

    failed_payload = processor.processing_logs.failed_payload
    assert failed_payload["finding_id"] == 3282
    assert failed_payload["recipient_email"] == "ticket@example.com"
    assert failed_payload["retry_count"] == 1
    assert failed_payload["error_message"] == "bad recipient"
    assert failed_payload["dedupe_key"] == "dd:example"
