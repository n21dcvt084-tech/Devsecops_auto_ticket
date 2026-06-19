import sys
from pathlib import Path
from urllib.parse import urljoin

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import requests

from config import Settings
from defectdojo_client import DefectDojoClient
from dedupe import build_dedupe_key
from email_template import build_ticket_content
from schemas import EmailPayload, TicketAction
from sla import policy_for_severity
from smtp_client import SmtpClient


MAILPIT_RECIPIENT = "manageengine-mailbox@example.com"


def fetch_one_active_verified_finding(settings: Settings):
    response = requests.get(
        urljoin(settings.defectdojo_base_url + "/", "api/v2/findings/"),
        headers={
            "Authorization": f"Token {settings.defectdojo_api_token}",
            "Accept": "application/json",
        },
        params={
            "active": "true",
            "verified": "true",
            "limit": 1,
            "offset": 0,
        },
        timeout=settings.defectdojo_request_timeout_seconds,
    )
    response.raise_for_status()
    raw_findings = response.json().get("results", [])
    if not raw_findings:
        return None
    return DefectDojoClient(settings)._map_finding(raw_findings[0])


def main() -> int:
    settings = Settings()

    # Keep real DefectDojo settings from .env, but force email delivery to
    # local Mailpit so real findings are not sent to an external mailbox.
    settings.smtp_host = "localhost"
    settings.smtp_port = 1025
    settings.smtp_use_tls = False
    settings.smtp_username = None
    settings.smtp_password = None
    settings.smtp_from_email = "DevSecOps Automation <devsecops@example.local>"
    settings.defectdojo_findings_limit = 1

    finding = fetch_one_active_verified_finding(settings)
    if not finding:
        print("NO_FINDINGS")
        return 2

    dedupe_key = build_dedupe_key(finding)
    sla_policy = policy_for_severity(finding.severity)
    content = build_ticket_content(
        finding,
        settings.defectdojo_base_url,
        dedupe_key=dedupe_key,
        sla_policy=sla_policy,
        ticket_action=TicketAction.CREATE,
        group=settings.manageengine_default_group,
        category=settings.manageengine_default_category,
        subcategory=settings.manageengine_default_subcategory,
    )
    payload = EmailPayload(
        finding_id=content.finding_id,
        recipient_email=MAILPIT_RECIPIENT,
        subject=content.subject,
        body=content.body,
        html_body=content.html_body,
        dedupe_key=content.dedupe_key,
        priority=content.priority,
        sla_target=content.sla_target,
        ticket_action=content.ticket_action,
    )

    SmtpClient(settings).send(payload)

    print(f"SENT_TO_MAILPIT finding_id={finding.finding_id}")
    print(f"severity={finding.severity}")
    print(f"product={finding.product or 'N/A'}")
    print(f"dedupe_key={dedupe_key}")
    print(f"recipient={MAILPIT_RECIPIENT}")
    print("mailpit_url=http://localhost:8025")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
