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
PROJECT_EMAIL_MAPPING_FILE=config/project_mapping.json
```

If `PROJECT_EMAIL_MAPPING_JSON` is explicitly set, it overrides entries from
the file.

Mapping schema:

```json
{
  "projects": [
    {
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
- `to_destinations` contains primary notification recipients. Each address
  receives its own independent notification email and is the only address in
  that email's `To` header.
- `cc_destinations` contains optional notification-copy recipients.
- Duplicate addresses must be removed.
- An address already in To must not also appear in Cc.

## 6. Required Delivery Modes

### 6.1 `email_fetch`

Configuration:

```env
MANAGEENGINE_DELIVERY_MODE=email_fetch
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
To: one address from to_destinations per email
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
```

Behavior:

1. Build ManageEngine request payload.
2. Call `POST /api/v3/requests`.
3. Store returned `ticket_id` and `ticket_status`.
4. Send one independent `notify_email` per `to_destinations` address, with
   `cc_destinations` copied, only after ticket creation succeeds.

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

Database schema changes must be applied through versioned Alembic migrations
before FastAPI starts. Application startup must not create, alter, truncate, or
drop database tables.

### `processing_logs`

Must support:

```text
finding_id
dedupe_key
status
seen_count
recipient_email
ticket_id
ticket_status
email_subject
email_body
email_html_body
retry_count
next_attempt_at
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
cc_emails
flow_type
delivery_mode
sent_at
```

### `dedupe_claims`

Must provide an expiring database lease for each logical `dedupe_key`:

```text
dedupe_key
finding_id
lease_owner
lease_expires_at
timestamps
```

The lease must prevent concurrent workers from processing the same logical
finding and must expire so another worker can recover after a crash.

### `notification_deliveries`

Must persist one independent delivery per `finding_id + recipient_email`:

```text
finding_id
dedupe_key
recipient_email
cc_emails
email_subject
email_body
email_html_body
status
retry_count
next_attempt_at
error_message
lease_owner
lease_expires_at
sent_at
timestamps
```

Notification retry state must survive application restart and must not require
the finding to remain in the next DefectDojo API response.

Supported `flow_type` values:

```text
ticket_email
notify_email
```

Expected events for one new finding:

| Mode | Expected SMTP events |
| --- | --- |
| `email_fetch` with notification recipients | One `ticket_email` plus one `notify_email` per To recipient |
| `email_fetch` without notification recipients | One `ticket_email` |
| `api` after successful ticket creation | One `notify_email` per To recipient |
| Duplicate finding | No new SMTP events |

Alembic migrations must support both a new database and an existing compatible
database without deleting audit rows.

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
- Use a PostgreSQL scheduler lease to prevent multiple app instances from
  polling concurrently.
- Create and close a database session per cycle.

One-shot tests must stop the app scheduler first to avoid concurrent polling.

## 13. SMTP Reliability Requirements

- Support authenticated SMTP with TLS.
- Support multiple configured recipients by sending one email per To recipient;
  each email may include the configured Cc recipients.
- Enforce per-minute and per-hour quotas.
- Persist transient SMTP failures with configurable backoff and retry them in a
  later scheduler cycle instead of blocking the worker with long sleeps.
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
- Unit tests and guarded limited SMTP tests must remain available for safe validation.

## 15. Acceptance Criteria

The implementation is accepted when:

- DefectDojo client filters active+verified findings.
- Product resolution and product mapping work.
- Dedupe key remains stable for the same logical issue.
- Duplicate findings do not create additional emails or tickets.
- `email_fetch` sends separate `ticket_email` and `notify_email` flows.
- Ticket email contains no notification Cc recipients.
- Notify flow sends one independent email per To recipient and supports Cc.
- API mode stores ticket result and sends notification after success.
- PostgreSQL records `recipient_email`, `cc_emails`, `flow_type`, and
  `delivery_mode` for each individual SMTP send.
- Email templates are adaptive, HTML-safe, and omit empty fields.
- Subject truncation and contextual redaction are tested.
- SLA mapping returns the documented values.
- SMTP retry and rate-limit behavior are tested.
- Unit test suite passes.

Latest verified result on 25/06/2026:

```text
49 passed
```

## 16. Manual Test Guardrails

- Start with `--limit 1` or `--per-product-limit 1`.
- Run unit tests before configured real SMTP.
- Use `--clear-db` only when a clean test is explicitly required.
- Do not clear database before the second duplicate-test run.
- Clearing backend tables does not delete ManageEngine tickets or mailbox
  messages.
- Keep ManageEngine API in dry run until token permissions and field mapping
  are approved.
