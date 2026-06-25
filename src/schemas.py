"""Define validated data contracts exchanged between application modules."""

from datetime import date, datetime
from enum import Enum
from pydantic import BaseModel, EmailStr, Field


class TicketAction(str, Enum):
    """Ticket action supported by the current CREATE-only lifecycle."""

    CREATE = "CREATE"


class SlaPolicy(BaseModel):
    """Internal priority, target, and due date derived from severity."""

    severity: str
    priority: str
    target: str
    due_at: datetime | None = None


class DefectDojoFinding(BaseModel):
    """Normalized representation of a finding returned by DefectDojo."""

    finding_id: int
    title: str
    severity: str
    description: str | None = None
    impact: str | None = None
    mitigation: str | None = None
    product: str | None = None
    endpoint: str | None = None
    date: date | str | None = None
    ticket_email: str | None = None
    scanner_type: str | None = None
    cwe: str | int | None = None
    cve: str | None = None
    rule_id: str | None = None
    file_path: str | None = None
    line: int | None = None
    component_name: str | None = None
    component_version: str | None = None
    parameter: str | None = None
    resource: str | None = None
    resource_type: str | None = None
    aws_account_id: str | None = None
    region: str | None = None
    compliance_status: str | None = None


class EmailPayload(BaseModel):
    """Complete plain-text and HTML message passed to the SMTP client."""

    finding_id: int
    recipient_email: EmailStr
    to_emails: list[EmailStr] = Field(default_factory=list)
    cc_emails: list[EmailStr] = Field(default_factory=list)
    subject: str
    body: str
    html_body: str | None = None
    dedupe_key: str | None = None
    priority: str | None = None
    sla_target: str | None = None
    ticket_action: TicketAction = TicketAction.CREATE


class ProjectEmailMapping(BaseModel):
    """Per-product ticket mailbox, notification recipients, and routing fields."""

    product_name: str
    ticket_mailbox: EmailStr | None = None
    to_destinations: list[EmailStr] = Field(default_factory=list)
    cc_destinations: list[EmailStr] = Field(default_factory=list)
    group: str | None = None
    category: str | None = None
    subcategory: str | None = None


class ProjectEmailMappingConfig(BaseModel):
    """Root schema for the project mapping JSON file."""

    projects: list[ProjectEmailMapping] = Field(default_factory=list)


class ManageEngineRequestPayload(BaseModel):
    """Normalized request fields required by the ManageEngine API client."""

    finding_id: int
    subject: str
    description: str
    ticket_action: TicketAction
    dedupe_key: str | None = None
    requester_name: str | None = None
    requester_email: EmailStr | None = None
    priority: str | None = None
    sla_target: str | None = None
    group: str | None = None
    category: str | None = None
    subcategory: str | None = None
    status: str = "Open"
    impact_details: str | None = None


class ManageEngineRequestResult(BaseModel):
    """Relevant ticket information parsed from a ManageEngine API response."""

    request_id: str | None = None
    status: str
    raw_response: dict = Field(default_factory=dict)
