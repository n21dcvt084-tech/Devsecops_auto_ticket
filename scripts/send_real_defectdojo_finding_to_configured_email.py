import json
import os
import sys
from pathlib import Path
from urllib.parse import urljoin

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import requests

from config import Settings
from defectdojo_client import DefectDojoClient
from dedupe import build_dedupe_key
from email_template import build_ticket_content
from schemas import EmailPayload, ProjectEmailMappingConfig, TicketAction
from sla import policy_for_severity
from smtp_client import SmtpClient


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


def resolve_recipient(settings: Settings, product_name: str | None) -> str | None:
    if not settings.project_email_mapping_json:
        return None

    mapping = ProjectEmailMappingConfig.model_validate(
        json.loads(settings.project_email_mapping_json)
    )
    for project in mapping.projects:
        if product_name and project.product_name.lower() == product_name.lower():
            if project.email_destinations:
                return str(project.email_destinations[0])
    return None


def main() -> int:
    if os.getenv("ALLOW_SEND_REAL_FINDING_TO_GMAIL") != "yes":
        print("Blocked: set ALLOW_SEND_REAL_FINDING_TO_GMAIL=yes to send a real finding.")
        return 2

    settings = Settings()
    finding = fetch_one_active_verified_finding(settings)
    if not finding:
        print("NO_FINDINGS")
        return 3

    recipient = resolve_recipient(settings, finding.product)
    if not recipient:
        print(f"NO_RECIPIENT_FOR_PRODUCT product={finding.product or 'N/A'}")
        return 4

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
        recipient_email=recipient,
        subject=content.subject,
        body=content.body,
        html_body=content.html_body,
        dedupe_key=content.dedupe_key,
        priority=content.priority,
        sla_target=content.sla_target,
        ticket_action=content.ticket_action,
    )

    SmtpClient(settings).send(payload)

    print(f"SENT finding_id={finding.finding_id}")
    print(f"severity={finding.severity}")
    print(f"product={finding.product or 'N/A'}")
    print(f"dedupe_key={dedupe_key}")
    print(f"recipient={recipient}")
    print(f"subject={content.subject}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
