import argparse
import os
import sys
from pathlib import Path
from urllib.parse import urljoin

import requests
from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from config import Settings
from database import get_session_factory
from defectdojo_client import DefectDojoClient
from processor import FindingProcessor
from schemas import DefectDojoFinding


DEFAULT_LIMIT = int(os.getenv("TEST_FINDINGS_LIMIT", "1"))
DEFAULT_PAGE_SIZE = 100
DEFAULT_MAX_PAGES = 5


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Fetch active + verified DefectDojo findings and process them through "
            "the normal backend flow using the configured SMTP mailbox."
        )
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_LIMIT,
        help="Maximum number of findings to process. Default: TEST_FINDINGS_LIMIT or 1.",
    )
    parser.add_argument(
        "--product-name",
        default=os.getenv("DEFECTDOJO_PRODUCT_NAME") or None,
        help="Optional DefectDojo product name filter.",
    )
    parser.add_argument(
        "--product-names",
        default=None,
        help=(
            "Comma-separated DefectDojo product names. Use this for a multi-product "
            "production test, for example: product-a,product-b,product-c."
        ),
    )
    parser.add_argument(
        "--per-product-limit",
        type=int,
        default=1,
        help="Maximum findings to process per product when --product-names is used.",
    )
    parser.add_argument(
        "--clear-db",
        action="store_true",
        help="Truncate local workflow, queue, dedupe, and SMTP audit tables.",
    )
    parser.add_argument(
        "--page-size",
        type=int,
        default=DEFAULT_PAGE_SIZE,
        help="DefectDojo API page size.",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=DEFAULT_MAX_PAGES,
        help="Maximum DefectDojo pages to scan while applying local filters.",
    )
    return parser.parse_args()


def parse_product_names(value: str | None) -> list[str]:
    if not value:
        return []
    return [name.strip() for name in value.split(",") if name.strip()]


def require_real_send_confirmation() -> None:
    if os.getenv("ALLOW_SEND_REAL_FINDING_TO_GMAIL") != "yes":
        raise RuntimeError(
            "Blocked: set ALLOW_SEND_REAL_FINDING_TO_GMAIL=yes to send real "
            "DefectDojo findings to the configured SMTP mailbox."
        )


def clear_database() -> None:
    session_factory = get_session_factory()
    with session_factory() as db:
        db.execute(
            text(
                """
                TRUNCATE TABLE
                    notification_deliveries,
                    dedupe_claims,
                    smtp_send_events,
                    processing_logs
                RESTART IDENTITY
                """
            )
        )
        db.commit()


def fetch_active_verified_findings(
    settings: Settings,
    *,
    limit: int,
    product_name: str | None,
    page_size: int,
    max_pages: int,
) -> list[DefectDojoFinding]:
    client = DefectDojoClient(settings)
    findings: list[DefectDojoFinding] = []
    offset = 0

    for _ in range(max_pages):
        response = requests.get(
            urljoin(settings.defectdojo_base_url + "/", "api/v2/findings/"),
            headers={
                "Authorization": f"Token {settings.defectdojo_api_token}",
                "Accept": "application/json",
            },
            params={
                "active": "true",
                "verified": "true",
                "limit": page_size,
                "offset": offset,
            },
            timeout=settings.defectdojo_request_timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        raw_findings = payload.get("results", [])
        if not raw_findings:
            break

        for raw_finding in raw_findings:
            finding = client._map_finding(raw_finding)
            if product_name and finding.product != product_name:
                continue
            findings.append(finding)
            if len(findings) >= limit:
                return findings

        if not payload.get("next"):
            break
        offset += page_size

    return findings


def main() -> int:
    args = parse_args()
    require_real_send_confirmation()
    product_names = parse_product_names(args.product_names)
    if args.product_name and product_names:
        raise ValueError("Use either --product-name or --product-names, not both.")

    settings = Settings()
    settings.manageengine_delivery_mode = "email_fetch"
    if args.clear_db:
        clear_database()

    missing_products: list[str] = []
    if product_names:
        findings = []
        for product_name in product_names:
            product_findings = fetch_active_verified_findings(
                settings,
                limit=args.per_product_limit,
                product_name=product_name,
                page_size=args.page_size,
                max_pages=args.max_pages,
            )
            if not product_findings:
                missing_products.append(product_name)
            findings.extend(product_findings)
    else:
        findings = fetch_active_verified_findings(
            settings,
            limit=args.limit,
            product_name=args.product_name,
            page_size=args.page_size,
            max_pages=args.max_pages,
        )
    if missing_products:
        print("MISSING_ACTIVE_VERIFIED_FINDINGS_FOR_PRODUCTS")
        for product_name in missing_products:
            print(f"- {product_name}")
        print("No emails were sent. Import or enable active+verified findings first.")
        return 3
    if not findings:
        print("NO_ACTIVE_VERIFIED_FINDINGS")
        print(f"product_filter={args.product_name or args.product_names or 'N/A'}")
        return 2

    session_factory = get_session_factory()
    with session_factory() as db:
        processor = FindingProcessor(settings, db)
        for finding in findings:
            processor.process_finding(finding)
            print(
                "PROCESSED_REAL_EMAIL "
                f"finding_id={finding.finding_id} "
                f"severity={finding.severity} "
                f"product={finding.product or 'N/A'} "
                f"scanner_type={finding.scanner_type or 'N/A'}"
            )

    print("DONE_PROCESS_ACTIVE_VERIFIED_FINDINGS_TO_CONFIGURED_EMAIL")
    print(f"processed_count={len(findings)}")
    print("delivery_mode=email_fetch")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
