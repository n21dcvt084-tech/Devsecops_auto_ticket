"""Generate stable logical-issue fingerprints for duplicate prevention."""

import hashlib
import re

from schemas import DefectDojoFinding


def build_dedupe_key(finding: DefectDojoFinding) -> str:
    """Build a stable issue fingerprint for Phase 2 duplicate detection."""
    parts = _fingerprint_parts(finding)
    raw_key = "|".join(_normalize(part) for part in parts if part not in (None, ""))
    if not raw_key:
        raw_key = f"finding:{finding.finding_id}"
    digest = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()[:24]
    return f"dd:{digest}"


def _fingerprint_parts(finding: DefectDojoFinding) -> list[object | None]:
    """Select stable fingerprint fields based on the finding type."""
    if finding.cve and finding.component_name:
        return [
            "dependency",
            finding.product,
            finding.component_name,
            finding.component_version,
            finding.cve,
        ]

    if finding.file_path:
        return [
            "sast",
            finding.product,
            finding.rule_id or finding.cwe or finding.title,
            finding.file_path,
            finding.line,
        ]

    if finding.endpoint:
        return [
            "web",
            finding.product,
            finding.rule_id or finding.cwe or finding.title,
            finding.endpoint,
            finding.parameter,
        ]

    return [
        finding.product,
        finding.scanner_type,
        finding.rule_id or finding.cwe or finding.cve or finding.title,
        finding.severity,
    ]


def _normalize(value: object) -> str:
    """Normalize one fingerprint component before hashing."""
    text = str(value).strip().lower()
    text = re.sub(r"\s+", " ", text)
    return text
