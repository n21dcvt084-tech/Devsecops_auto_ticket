from datetime import date, datetime
from enum import Enum

from pydantic import BaseModel, EmailStr, Field


class ProcessingStatusValue(str, Enum):
    PENDING = "PENDING"
    SENT = "SENT"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    RATE_LIMITED = "RATE_LIMITED"
    INVALID_RECIPIENT = "INVALID_RECIPIENT"


class TicketLifecycleStatus(str, Enum):
    OPEN = "OPEN"
    RESOLVED_CANDIDATE = "RESOLVED_CANDIDATE"
    CLOSED = "CLOSED"
    REOPENED = "REOPENED"
    SUPPRESSED = "SUPPRESSED"


class TicketAction(str, Enum):
    CREATE = "CREATE"
    UPDATE = "UPDATE"
    REOPEN = "REOPEN"
    CLOSE_CANDIDATE = "CLOSE_CANDIDATE"


class SlaPolicy(BaseModel):
    severity: str
    priority: str
    target: str
    due_at: datetime | None = None


class DefectDojoFinding(BaseModel):
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
    finding_id: int
    recipient_email: EmailStr
    cc_emails: list[EmailStr] = Field(default_factory=list)
    subject: str
    body: str
    html_body: str | None = None
    dedupe_key: str | None = None
    priority: str | None = None
    sla_target: str | None = None
    ticket_action: TicketAction = TicketAction.CREATE


class ProjectEmailMapping(BaseModel):
    project_name: str
    product_name: str
    email_destinations: list[EmailStr] = Field(default_factory=list)
    cc_destinations: list[EmailStr] = Field(default_factory=list)
    group: str | None = None
    category: str | None = None
    subcategory: str | None = None


class ProjectEmailMappingConfig(BaseModel):
    projects: list[ProjectEmailMapping] = Field(default_factory=list)


class ManageEngineRequestPayload(BaseModel):
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
    request_id: str | None = None
    status: str
    raw_response: dict = Field(default_factory=dict)
