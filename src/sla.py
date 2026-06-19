from datetime import datetime, timedelta, timezone

from schemas import SlaPolicy


SLA_BY_SEVERITY = {
    "critical": ("P1/Critical", timedelta(days=7), "7 days"),
    "high": ("P2/High", timedelta(days=14), "14 days"),
    "medium": ("P3/Medium", timedelta(days=30), "30 days"),
    "low": ("P4/Low", timedelta(days=90), "60 - 90 days"),
    "informational": ("P5/Info", None, "Best effort"),
    "info": ("P5/Info", None, "Best effort"),
}


def policy_for_severity(severity: str) -> SlaPolicy:
    normalized = severity.strip().lower()
    priority, delta, target = SLA_BY_SEVERITY.get(
        normalized,
        ("P5/Info", None, "Best effort"),
    )
    now = datetime.now(timezone.utc)
    due_at = now + delta if delta else None
    return SlaPolicy(
        severity=severity,
        priority=priority,
        target=target,
        due_at=due_at,
    )
