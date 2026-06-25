"""Map finding severity and content to a ManageEngine request payload."""

from datetime import datetime, timedelta, timezone

from config import Settings
from email_template import build_ticket_content
from schemas import (
    DefectDojoFinding,
    ManageEngineRequestPayload,
    SlaPolicy,
    TicketAction,
)

MANAGEENGINE_PRIORITY_BY_SLA_PRIORITY = {
    "P1/Critical": "High",
    "P2/High": "High",
    "P3/Medium": "Medium",
    "P4/Low": "Low",
    "P5/Info": "Low",
}

SLA_BY_SEVERITY = {
    "critical": ("P1/Critical", timedelta(days=7), "7 days"),
    "high": ("P2/High", timedelta(days=14), "14 days"),
    "medium": ("P3/Medium", timedelta(days=30), "30 days"),
    "low": ("P4/Low", timedelta(days=90), "60 - 90 days"),
    "informational": ("P5/Info", None, "Best effort"),
    "info": ("P5/Info", None, "Best effort"),
}


def policy_for_severity(severity: str) -> SlaPolicy:
    """Map DefectDojo severity to internal priority, SLA target, and due date."""
    normalized = severity.strip().lower()
    priority, delta, target = SLA_BY_SEVERITY.get(
        normalized,
        ("P5/Info", None, "Best effort"),
    )
    now = datetime.now(timezone.utc)
    return SlaPolicy(
        severity=severity,
        priority=priority,
        target=target,
        due_at=now + delta if delta else None,
    )


def map_manageengine_priority(priority: str) -> str:
    """Translate internal priority labels to ManageEngine priority names."""
    return MANAGEENGINE_PRIORITY_BY_SLA_PRIORITY.get(priority, priority)


def build_manageengine_payload(
    *,
    finding: DefectDojoFinding,
    settings: Settings,
    dedupe_key: str,
    sla_policy: SlaPolicy,
    ticket_action: TicketAction,
) -> ManageEngineRequestPayload:
    """Build a validated ManageEngine API payload from one normalized finding."""
    content = build_ticket_content(
        finding,
        settings.defectdojo_base_url,
        dedupe_key=dedupe_key,
        sla_policy=sla_policy,
        ticket_action=ticket_action,
        group=settings.manageengine_default_group,
        category=settings.manageengine_default_category,
        subcategory=settings.manageengine_default_subcategory,
    )
    return ManageEngineRequestPayload(
        finding_id=content.finding_id,
        subject=content.subject,
        description=content.body,
        ticket_action=content.ticket_action,
        dedupe_key=content.dedupe_key,
        requester_name=settings.manageengine_requester_name,
        requester_email=settings.manageengine_requester_email or None,
        priority=map_manageengine_priority(content.priority),
        sla_target=content.sla_target,
        group=settings.manageengine_default_group,
        category=settings.manageengine_default_category,
        subcategory=settings.manageengine_default_subcategory,
        status="Open",
        impact_details=(
            f"Finding ID: {content.finding_id}; "
            f"Ticket Action: {content.ticket_action.value}; "
            f"SLA Target: {content.sla_target}; "
            f"Dedupe Key: {content.dedupe_key or 'N/A'}"
        ),
    )
