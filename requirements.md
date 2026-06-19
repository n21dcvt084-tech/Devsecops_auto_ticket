# DevSecOps Auto Ticket v2 Requirements

This is the implementation contract for the clean v2 rebuild.

## Goals

Build a small, readable backend service that:

1. Polls DefectDojo for `active=true` and `verified=true` findings.
2. Normalizes findings into an internal schema.
3. Builds a stable `dedupe_key` to reduce duplicate tickets.
4. Stores processing audit state in PostgreSQL.
5. Delivers new findings to ManageEngine using either `email_fetch` or `api` mode.
6. Keeps current ticket lifecycle limited to `CREATE` and `SKIP`.

## Non-Goals

- No automatic ticket close.
- No automatic reopen.
- No automatic update to existing tickets.
- No production secret stored in source control.
- No unapproved personal mailbox for real security findings.

## Required Modes

### `email_fetch`

```text
DefectDojo -> Backend -> SMTP email -> ManageEngine Incoming Mail -> Ticket
```

Config:

```env
MANAGEENGINE_DELIVERY_MODE=email_fetch
MANAGEENGINE_ENABLED=false
```

Backend only knows whether SMTP send succeeded. `ticket_id` can remain empty.

### `api`

```text
DefectDojo -> Backend -> ManageEngine API -> Ticket
```

Config:

```env
MANAGEENGINE_DELIVERY_MODE=api
MANAGEENGINE_ENABLED=true
```

With `MANAGEENGINE_DRY_RUN=true`, backend validates payload without creating a real ticket.
With `MANAGEENGINE_DRY_RUN=false`, backend creates a real ManageEngine request and stores returned ticket metadata.

## Processing Rules

- New finding/dedupe key -> `CREATE`.
- Existing `SENT` finding ID -> `SKIP`.
- Existing `SENT` dedupe key -> `SKIP`.
- Invalid recipient in `email_fetch` mode -> `INVALID_RECIPIENT`.
- SMTP rate limit exceeded -> `RATE_LIMITED`.
- Runtime/API/SMTP error -> `FAILED`.

## SLA Mapping

| DefectDojo severity | Internal priority | SLA target |
| --- | --- | --- |
| Critical | P1/Critical | 7 days |
| High | P2/High | 14 days |
| Medium | P3/Medium | 30 days |
| Low | P4/Low | 60 - 90 days |
| Informational | P5/Info | Best effort |

## Acceptance Tests

- Dedupe key is stable for the same issue when finding ID changes.
- Email subject/body contains project, severity, finding ID, DefectDojo URL, SLA, and routing fields.
- Secrets are redacted as `XXXXXX` before email/API delivery.
- ManageEngine API dry-run builds a valid payload.
- SLA mapping returns expected priority and target.
- Retry helper detects transient SMTP errors.

## Operational Guardrails

- Use `.env.example` as a template only.
- Keep `DEFECTDOJO_FINDINGS_LIMIT=1` for manual demo tests.
- Keep group/category/subcategory blank until exact ManageEngine values are confirmed.
- Use Gmail App Password only for lab mailbox fetch testing.
- Prefer ManageEngine API mode when API token and field mapping are approved.
