import os
from urllib.parse import urljoin

import requests

from config import Settings
from database import get_session_factory, init_database
from defectdojo_client import DefectDojoClient
from processor import FindingProcessor


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


def apply_safe_mailpit_override(settings: Settings) -> None:
    if os.getenv("FORCE_SMTP_TO_MAILPIT") != "true":
        return

    settings.smtp_host = os.getenv("MAILPIT_SMTP_HOST", "mailpit")
    settings.smtp_port = int(os.getenv("MAILPIT_SMTP_PORT", "1025"))
    settings.smtp_use_tls = False
    settings.smtp_username = None
    settings.smtp_password = None


def main() -> int:
    settings = Settings()
    apply_safe_mailpit_override(settings)
    init_database()

    finding = fetch_one_active_verified_finding(settings)
    if finding is None:
        print("NO_FINDINGS")
        return 2

    db = get_session_factory()()
    try:
        FindingProcessor(settings, db).process_finding(finding)
    finally:
        db.close()

    print(f"PROCESSED finding_id={finding.finding_id}")
    print(f"severity={finding.severity}")
    print(f"product={finding.product or 'N/A'}")
    print(f"smtp_host={settings.smtp_host}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
