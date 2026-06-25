import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from config import Settings
from manageengine_client import ManageEngineClient, format_manageengine_description
from schemas import ManageEngineRequestPayload, TicketAction


def build_settings(**overrides):
    values = {
        "DEFECTDOJO_BASE_URL": "https://dojo.example.com",
        "DEFECTDOJO_API_TOKEN": "token",
        "DATABASE_URL": "postgresql://user:pass@localhost/db",
        "SMTP_HOST": "localhost",
        "SMTP_FROM_EMAIL": "devsecops@example.com",
        "MANAGEENGINE_BASE_URL": "https://servicedesk.example.com",
        "MANAGEENGINE_DRY_RUN": True,
        **overrides,
    }
    return Settings.model_validate(values)


def test_create_request_dry_run_builds_manageengine_v3_input_data():
    client = ManageEngineClient(build_settings())
    payload = ManageEngineRequestPayload(
        finding_id=3282,
        subject="[Critical] DevSecOps Finding - SQL Injection",
        description="Ticket Routing Fields\n- Ticket Action: CREATE\n\nFinding Details\n- Title: SQL Injection",
        ticket_action=TicketAction.CREATE,
        dedupe_key="dd:example",
        requester_name="DevSecOps Automation",
        priority="P1/Critical",
        group="DevSecOps",
        category="Security",
        subcategory="Vulnerability",
        impact_details="SLA Target: 7 days",
    )

    result = client.create_request(payload)

    request = result.raw_response["input_data"]["request"]
    assert result.status == "DRY_RUN"
    assert request["subject"] == "[Critical] DevSecOps Finding - SQL Injection"
    assert "Ticket Routing Fields<br>- Ticket Action: CREATE<br><br>Finding Details" in request["description"]
    assert request["status"]["name"] == "Open"
    assert request["priority"]["name"] == "P1/Critical"
    assert request["group"]["name"] == "DevSecOps"
    assert request["category"]["name"] == "Security"
    assert request["subcategory"]["name"] == "Vulnerability"


def test_manageengine_payload_redacts_secret_values():
    client = ManageEngineClient(build_settings())
    payload = ManageEngineRequestPayload(
        finding_id=3282,
        subject="Leaked secret_key=secret-value-12345",
        description="Authorization: Token ffffffffffffffffffffffffffffffffffffffff",
        ticket_action=TicketAction.CREATE,
    )

    result = client.create_request(payload)

    request = result.raw_response["input_data"]["request"]
    assert "secret-value-12345" not in request["subject"]
    assert "ffffffffffffffffffffffffffffffffffffffff" not in request["description"]
    assert "XXXXXX" in request["subject"]
    assert "XXXXXX" in request["description"]


def test_format_manageengine_description_preserves_line_breaks_and_escapes_html():
    description = "Finding Details\n- Endpoint: <script>alert(1)</script>"

    formatted = format_manageengine_description(description)

    assert "Finding Details<br>- Endpoint:" in formatted
    assert "<script>" not in formatted
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in formatted


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


def test_create_request_rejects_http_200_without_confirmed_request(monkeypatch):
    monkeypatch.setattr(
        "manageengine_client.requests.post",
        lambda *args, **kwargs: FakeResponse(
            {"response_status": {"status": "failed"}}
        ),
    )
    client = ManageEngineClient(
        build_settings(
            MANAGEENGINE_DRY_RUN=False,
            MANAGEENGINE_AUTH_TOKEN="token",
        )
    )
    payload = ManageEngineRequestPayload(
        finding_id=3282,
        subject="Security finding",
        description="Finding details",
        ticket_action=TicketAction.CREATE,
    )

    with pytest.raises(ValueError, match="request.id"):
        client.create_request(payload)
