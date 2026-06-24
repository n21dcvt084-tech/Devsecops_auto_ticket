import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from config import Settings
from schemas import EmailPayload
from smtp_client import SmtpClient


def build_settings(**overrides):
    values = {
        "DEFECTDOJO_BASE_URL": "https://dojo.example.com",
        "DEFECTDOJO_API_TOKEN": "token",
        "DATABASE_URL": "postgresql://user:pass@localhost/db",
        "SMTP_HOST": "smtp.example.com",
        "SMTP_FROM_EMAIL": "DevSecOps Automation <devsecops@example.com>",
        "SMTP_USERNAME": None,
        "SMTP_PASSWORD": None,
        "SMTP_USE_TLS": False,
        **overrides,
    }
    return Settings.model_validate(values)


class FakeSmtp:
    sent_messages = []

    def __init__(self, host, port, timeout):
        self.host = host
        self.port = port
        self.timeout = timeout

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def starttls(self):
        raise AssertionError("TLS should not be used in this test")

    def login(self, username, password):
        raise AssertionError("Login should not be used in this test")

    def send_message(self, message):
        self.sent_messages.append(message)


def test_smtp_client_sends_plain_text_and_html_alternative(monkeypatch):
    FakeSmtp.sent_messages = []
    monkeypatch.setattr("smtp_client.smtplib.SMTP", FakeSmtp)
    payload = EmailPayload(
        finding_id=3282,
        recipient_email="ticket@example.com",
        to_emails=["team-a@example.com", "team-b@example.com"],
        cc_emails=["team@example.com", "lead@example.com"],
        subject="Security finding",
        body="DefectDojo URL: https://dojo.example.com/finding/3282",
        html_body=(
            '<p>DefectDojo URL: '
            '<a href="https://dojo.example.com/finding/3282">Open finding</a></p>'
        ),
    )

    SmtpClient(build_settings()).send(payload)

    assert len(FakeSmtp.sent_messages) == 1
    message = FakeSmtp.sent_messages[0]
    assert message["To"] == "ticket@example.com, team-a@example.com, team-b@example.com"
    assert message["Cc"] == "team@example.com, lead@example.com"
    assert message.is_multipart()
    assert message.get_body(("plain",)).get_content_type() == "text/plain"
    assert message.get_body(("html",)).get_content_type() == "text/html"
    assert "https://dojo.example.com/finding/3282" in message.get_body(
        ("html",)
    ).get_content()
