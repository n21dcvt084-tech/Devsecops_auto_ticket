# DevSecOps Auto Ticket v2 Requirements

This document is the implementation contract for the current v2 project.
`README.md` contains operating instructions; this file defines required
behavior, scope, and acceptance criteria.

## 1. Goals

The service must:

1. Poll DefectDojo for findings where `active=true` and `verified=true`.
2. Normalize findings into a common internal schema.
3. Build a stable `dedupe_key` for logical duplicate detection.
4. Prevent duplicate ticket creation using both `finding_id` and `dedupe_key`.
5. Store processing, recipient, ticket, and SMTP audit data in PostgreSQL.
6. Route findings by DefectDojo product mapping rather than hardcoded logic.
7. Support ManageEngine `email_fetch` and `api` delivery modes.
8. Keep ticket lifecycle actions limited to `CREATE` and `SKIP`.
9. Redact secrets and sensitive identifiers before email/API delivery.
10. Support safe one-product and five-product test workflows.

## 2. Non-Goals

The current scope does not include:

- Automatic ticket update.
- Automatic ticket reopen.
- Automatic ticket close or close-candidate workflow.
- Synchronizing ManageEngine ticket status back to DefectDojo.
- Reading email through backend IMAP.
- Storing production secrets in source control or documentation.
- Sending real findings to unapproved personal/external mailboxes.

Database enums may contain future lifecycle values, but the processor must not
use them until requirements and ManageEngine field mapping are approved.

## 3. Finding Selection

DefectDojo API queries must request:

```text
active=true
verified=true
```

Product name may be resolved through finding/test/engagement/product
relationships when it is not present directly on the finding.

Manual scripts must support:

- One product with `--product-name`.
- Multiple products with `--product-names`.
- A safe per-product limit.
- Failure before sending when a requested product has no active+verified
  finding.

## 4. Duplicate Rules

The processor must:

1. Track every observed finding by `finding_id`.
2. Generate `dedupe_key` using normalized stable fields.
3. Skip an existing finding whose status is already `SENT`.
4. Skip a different finding ID when its `dedupe_key` matches a sent or queued
   issue.
5. Increase `seen_count` when the same finding is observed again.
6. Avoid new SMTP events and ManageEngine tickets for duplicates.

`dedupe_key` format:

```text
dd:<24-character SHA-256 prefix>
```

Fingerprint fields vary by finding type:

- Dependency: product, component, version, CVE.
- SAST: product, rule/CWE/title, file path, line.
- DAST/web: product, rule/CWE/title, endpoint, parameter.
- Fallback: product, scanner, identifier/title, severity.

## 5. Product and Email Mapping

New configuration must use:

```env
PROJECT_EMAIL_MAPPING_FILE=config/project_email_mapping.sample.json
PROJECT_EMAIL_MAPPING_JSON=
```

If `PROJECT_EMAIL_MAPPING_JSON` is non-empty, it overrides the file.

Mapping schema:

```json
{
  "projects": [
    {
      "project_name": "Customer Portal Security",
      "product_name": "Customer Portal",
      "ticket_mailbox": "ticket-mailbox@example.com",
      "to_destinations": [
        "customer-group@example.com",
        "devsecops-group@example.com"
      ],
      "cc_destinations": [
        "devsecops-archive@example.com"
      ],
      "group": null,
      "category": null,
      "subcategory": null
    }
  ]
}
```

Rules:

- `product_name` must match the resolved DefectDojo product name.
- `ticket_mailbox` is the mailbox used to create tickets in `email_fetch`.
- `to_destinations` contains primary notification recipients.
- `cc_destinations` contains optional notification-copy recipients.
- Duplicate addresses must be removed.
- An address already in To must not also appear in Cc.
- Legacy `email_destinations` and `alert_destinations` may remain as fallback
  compatibility fields, but must not be used in new configuration.

## 6. Required Delivery Modes

### 6.1 `email_fetch`

Configuration:

```env
MANAGEENGINE_DELIVERY_MODE=email_fetch
MANAGEENGINE_ENABLED=false
```

For each new finding, backend must send two independent email flows when
notification recipients are configured.

#### `ticket_email`

```text
To: ticket_mailbox only
Cc: none
```

Purpose:

- ManageEngine Incoming Mail fetches this mailbox.
- ManageEngine creates one request/ticket.
- Successful send marks the finding `SENT`.

#### `notify_email`

```text
To: to_destinations
Cc: cc_destinations
```

Purpose:

- Notify customer/project/internal recipients.
- Must be sent only after `ticket_email` succeeds.
- Failure must be logged but must not change a successfully sent ticket flow to
  `FAILED`.

Backend only knows that SMTP succeeded. `ticket_id` may remain empty because
Incoming Mail does not return a ticket ID to backend.

### 6.2 `api`

Configuration:

```env
MANAGEENGINE_DELIVERY_MODE=api
MANAGEENGINE_ENABLED=true
```

Behavior:

1. Build ManageEngine request payload.
2. Call `POST /api/v3/requests`.
3. Store returned `ticket_id` and `ticket_status`.
4. Send one `notify_email` to `to_destinations` and `cc_destinations` only
   after ticket creation succeeds.

With `MANAGEENGINE_DRY_RUN=true`, payload construction must be validated without
creating a real request.

With `MANAGEENGINE_DRY_RUN=false`, backend may create a real request only when
the user/operator explicitly enables the integration and provides approved
credentials.

## 7. Processing Status Rules

- New finding before completion -> `PENDING`.
- Ticket email sent or API ticket created -> `SENT`.
- Existing finding ID or dedupe key -> `SKIPPED`.
- Missing/invalid ticket mailbox in `email_fetch` -> `INVALID_RECIPIENT`.
- SMTP quota exceeded before ticket send -> `RATE_LIMITED`.
- Ticket SMTP/API operation fails -> `FAILED`.
- Notification-only failure must not overwrite a successful ticket status.

## 8. PostgreSQL Audit Requirements

### `processing_logs`

Must support:

```text
finding_id
dedupe_key
status
seen_count
recipient_email
to_emails
cc_emails
ticket_id
ticket_status
email_subject
email_body
retry_count
error_message
priority
sla_target
sla_due_at
timestamps
```

### `smtp_send_events`

Every successful SMTP send must record:

```text
finding_id
recipient_email
to_emails
cc_emails
flow_type
delivery_mode
sent_at
```

Supported `flow_type` values:

```text
ticket_email
notify_email
```

Expected events for one new finding:

| Mode | Expected SMTP events |
| --- | --- |
| `email_fetch` with notification recipients | One `ticket_email` and one `notify_email` |
| `email_fetch` without notification recipients | One `ticket_email` |
| `api` after successful ticket creation | One `notify_email` |
| Duplicate finding | No new SMTP events |

Database initialization must apply lightweight migrations for existing local
databases.

## 9. Email Content Requirements

Email must:

- Be multipart `text/plain` and `text/html`.
- Include project, severity, finding ID, title, impact, and recommendation when
  available.
- Include a plain URL and clickable HTML link to the DefectDojo finding.
- Use adaptive details for dependency, cloud, SAST, and DAST findings.
- Omit empty values such as `N/A`, `None`, `[]`, `{}`, and empty strings.
- Omit `Ticket Routing Fields` from the rendered email for now.
- Omit `Finding Date` from the rendered email for now.
- Include `DevSecOps Team` as the support contact.
- Cap subject length at 200 characters.
- End a truncated subject with `.....`.
- Escape dynamic HTML content.

## 10. Redaction Requirements

Before email/API delivery:

- Passwords, tokens, API keys, secrets, and credentials must be masked as
  `XXXXXX`.
- Cloud redaction must be contextual rather than masking all operational data.
- AWS account IDs must be masked.
- Full AWS Security Hub finding ARNs must be summarized.
- Control ID, standard, region, and shortened finding reference may remain
  visible when needed for investigation.
- Subject redaction must follow the same cloud-safety rules as body redaction.

## 11. SLA Mapping

| DefectDojo severity | Internal priority | SLA target |
| --- | --- | --- |
| Critical | P1/Critical | 7 days |
| High | P2/High | 14 days |
| Medium | P3/Medium | 30 days |
| Low | P4/Low | 60 - 90 days |
| Informational / Info / unknown | P5/Info | Best effort |

## 12. Scheduler and Operational Requirements

Default deployment-style settings:

```env
DEFECTDOJO_FINDINGS_LIMIT=100
DEFECTDOJO_REQUEST_TIMEOUT_SECONDS=60
SCHEDULER_INTERVAL_SECONDS=300
```

Scheduler must:

- Run one cycle immediately when the app starts.
- Poll again every configured interval.
- Use `max_instances=1`.
- Create and close a database session per cycle.

One-shot tests must stop the app scheduler first to avoid concurrent polling.

## 13. SMTP Reliability Requirements

- Support authenticated SMTP with TLS.
- Support multiple To and Cc recipients.
- Enforce per-minute and per-hour quotas.
- Retry transient SMTP failures using configurable backoff.
- Record an SMTP event only after successful send.
- Prevent duplicated addresses across recipient lists.

## 14. Security Requirements

- `.env` must not be committed.
- `.env.example` must contain placeholders only.
- Private keys, certificates, credential exports, tokens, and App Passwords
  must not be committed.
- Secrets must not appear in README, docs, reports, or application logs.
- A private GitHub repository does not permit committing secrets.
- Real findings may be sent only to explicitly approved destinations.
- The guarded real-email script must require
  `ALLOW_SEND_REAL_FINDING_TO_GMAIL=yes`.
- Mailpit must remain available for safe email testing.

## 15. Acceptance Criteria

The implementation is accepted when:

- DefectDojo client filters active+verified findings.
- Product resolution and product mapping work.
- Dedupe key remains stable for the same logical issue.
- Duplicate findings do not create additional emails or tickets.
- `email_fetch` sends separate `ticket_email` and `notify_email` flows.
- Ticket email contains no notification Cc recipients.
- Notify email supports multiple To and Cc recipients.
- API mode stores ticket result and sends notification after success.
- PostgreSQL records `to_emails`, `cc_emails`, `flow_type`, and
  `delivery_mode`.
- Email templates are adaptive, HTML-safe, and omit empty fields.
- Subject truncation and contextual redaction are tested.
- SLA mapping returns the documented values.
- SMTP retry and rate-limit behavior are tested.
- Unit test suite passes.

Latest verified result on 24/06/2026:

```text
41 passed
```

## 16. Manual Test Guardrails

- Start with `--limit 1` or `--per-product-limit 1`.
- Test Mailpit before configured real SMTP.
- Use `--clear-db` only when a clean test is explicitly required.
- Do not clear database before the second duplicate-test run.
- Clearing backend tables does not delete ManageEngine tickets or mailbox
  messages.
- Keep ManageEngine API in dry run until token permissions and field mapping
  are approved.
