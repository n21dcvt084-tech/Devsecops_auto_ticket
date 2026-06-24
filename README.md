# DevSecOps Auto Ticket v2

DevSecOps Auto Ticket v2 automatically pulls active and verified findings from
DefectDojo, prevents duplicate processing in PostgreSQL, and creates
ManageEngine tickets.

The current tested delivery path is `email_fetch`. For every new finding, the
backend sends:

1. A `ticket_email` to the dedicated mailbox fetched by ManageEngine Incoming
   Mail.
2. A separate `notify_email` to the configured project/customer recipients and
   CC recipients.

The project also contains an `api` mode for direct ticket creation through
`POST /api/v3/requests`.

The project is intentionally scoped for a demo/MVP:

- Pull only DefectDojo findings where `active=true` and `verified=true`.
- Create tickets only for new findings.
- Skip duplicate findings by `finding_id` and `dedupe_key`.
- Record processing and SMTP audit logs in PostgreSQL.
- Route tickets by product mapping instead of hardcoded project logic.
- Separate ticket creation email from project/customer notification email.
- Store each SMTP flow and delivery mode in the database for audit.
- Keep the ticket lifecycle simple: `CREATE` or `SKIP`.

`UPDATE`, `REOPEN`, and `CLOSE_CANDIDATE` are not enabled yet because those require confirmed ManageEngine field mapping and lifecycle rules.

## Workflow

```text
DefectDojo API
  -> Backend scheduler every SCHEDULER_INTERVAL_SECONDS
  -> Finding processor
  -> PostgreSQL dedupe + audit log
  -> New finding:
       email_fetch:
         -> ticket_email -> ManageEngine ticket mailbox
         -> ManageEngine Incoming Mail -> ticket/request
         -> notify_email -> project/customer To + CC recipients
       api:
         -> POST /api/v3/requests -> ticket/request
         -> notify_email -> project/customer To + CC recipients
  -> Duplicate finding: SKIP
```

Supported ManageEngine delivery modes:

```text
email_fetch: Backend sends SMTP email -> ManageEngine Incoming Mail creates ticket
api:         Backend calls ManageEngine API -> ManageEngine creates ticket directly
```

Current tested mode:

```text
MANAGEENGINE_DELIVERY_MODE=email_fetch
```

The same PostgreSQL audit schema supports both delivery modes.

## Source Layout

```text
src/
  main.py                  FastAPI app and lifecycle
  scheduler.py             Periodic polling job
  processor.py             Main finding workflow
  defectdojo_client.py     DefectDojo API client
  dedupe.py                Stable duplicate fingerprint
  sla.py                   Severity -> priority/SLA mapping
  email_template.py        Shared email/ticket description body
  smtp_client.py           SMTP sender for ticket and notification emails
  manageengine_client.py   ManageEngine API client
  manageengine_mapper.py   Finding -> ManageEngine request payload
  database.py              SQLAlchemy engine/session
  models.py                PostgreSQL models
  repositories.py          DB audit operations
  redaction.py             Secret masking
  config.py                Environment settings
  logging_config.py        Logging setup
  health.py                Health endpoints
tests/                     Unit tests for the core rules
config/                    Product -> recipient mapping sample
```

## Setup

```bash
cd /Users/quyph/Documents/DevSecOps_auto_ticket_v2
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` locally. Do not commit `.env`.

Use the JSON mapping file as the routing source:

```env
PROJECT_EMAIL_MAPPING_FILE=config/project_email_mapping.sample.json
PROJECT_EMAIL_MAPPING_JSON=
```

If `PROJECT_EMAIL_MAPPING_JSON` contains a value, it overrides the mapping file.

## Run Tests

```bash
.venv/bin/python -m pytest tests
```

## Start Services

```bash
docker compose build app
docker compose up -d postgres
docker compose run --rm -e PYTHONPATH=/app/src app python -c "from database import init_database; init_database()"
docker compose up -d app
docker compose logs -f app
```

Rebuild the image after changing Python source, dependencies, Dockerfile, or a
file copied into the image such as the JSON mapping. Changing only `.env`
requires an app restart, not a rebuild.

Stop the scheduler before one-shot manual tests:

```bash
docker compose stop app
```

## Mode 1: ManageEngine Email Fetch

Use this when ManageEngine reads a mailbox and creates a ticket from email.

`.env`:

```env
MANAGEENGINE_DELIVERY_MODE=email_fetch
MANAGEENGINE_ENABLED=false
MANAGEENGINE_DRY_RUN=true
```

Flow:

```text
DefectDojo
  -> Backend + PostgreSQL dedupe
  -> ticket_email
       To: ticket_mailbox only
       Cc: none
       -> ManageEngine Incoming Mail -> Ticket
  -> notify_email
       To: to_destinations
       Cc: cc_destinations
```

Backend requirements:

- SMTP configuration must be valid.
- The project mapping must contain the exact DefectDojo product name.
- `ticket_mailbox` is the mailbox that ManageEngine Incoming Mail fetches in `email_fetch` mode.
- `to_destinations` contains one or more primary notification recipients.
- `cc_destinations` contains zero or more recipients copied for tracking.
- The backend removes duplicate addresses from To/Cc.
- The `ticket_email` never includes notification To/Cc recipients.
- `Ticket Routing Fields` are intentionally hidden in the email body for now.
- Email is sent as multipart plain text + HTML. The HTML part includes a clickable DefectDojo finding link for mail clients or ManageEngine views that preserve HTML.
- Email subject is capped at 200 characters and ends with `.....` when truncated.
- `Finding Date` in the email is the email generation time, not the original DefectDojo finding date.
- `Mitigation / Recommendation` includes a support contact line for `DevSecOps Team`.

### Multi-project routing

Do not create one template per project. Keep one shared template and route by product mapping.

Example:

```json
{
  "projects": [
    {
      "project_name": "Customer Portal Security",
      "product_name": "Customer Portal",
      "ticket_mailbox": "me-ticket-mailbox@example.com",
      "to_destinations": ["customer-group@example.com", "devsecops-group@example.com"],
      "cc_destinations": ["devsecops-archive@example.com"],
      "group": "Application Security",
      "category": "Security",
      "subcategory": "Web Vulnerability"
    },
    {
      "project_name": "Infrastructure Security",
      "product_name": "Infrastructure",
      "ticket_mailbox": "me-ticket-mailbox@example.com",
      "to_destinations": ["infra-group@example.com", "devsecops-group@example.com"],
      "cc_destinations": ["devsecops-archive@example.com"],
      "group": "Infrastructure Security",
      "category": "Security",
      "subcategory": "Infrastructure Vulnerability"
    }
  ]
}
```

For five products and two mail groups, add five entries and point each product to the correct ticket mailbox/group. This keeps routing in config instead of code.

Current five-product mapping:

```text
canhvp-demo
check_500
check_threagile
demo-devsecops-project
demo-dojo
```

ManageEngine requirements:

- Incoming Mail must be configured and running.
- For Gmail lab testing, use Google App Password, not the real Gmail password.
- For enterprise mailboxes, use approved company mailbox/OAuth/API path.
- If `MANAGEENGINE_BASE_URL` uses an internal Docker/tunnel URL such as `https://host.docker.internal:18082`, set `MANAGEENGINE_PUBLIC_URL` to the browser-accessible ManageEngine URL. Email links use `MANAGEENGINE_PUBLIC_URL`.

## Manual Test: 1 Product

Use this flow when validating a single DefectDojo product before a larger demo.

1. Stop the scheduler so it does not run while preparing data:

```bash
docker compose stop app
docker compose up -d postgres
```

2. Clear local audit data:

```bash
docker compose exec -T postgres psql -U devsecops -d devsecops -c "truncate table processing_logs, smtp_send_events restart identity;"
```

3. Process one product through the configured email path:

```bash
docker compose run --rm -e ALLOW_SEND_REAL_FINDING_TO_GMAIL=yes app python scripts/process_active_verified_findings_to_configured_email.py --product-name "demo-dojo" --limit 1
```

Replace `demo-dojo` with the target DefectDojo product name. Keep `--limit 1` for a safe first test.

4. Check the backend audit log:

```bash
docker compose exec -T postgres psql -U devsecops -d devsecops -c "select finding_id, status, seen_count, to_emails, cc_emails, left(email_subject,160) as subject, processed_at, updated_at from processing_logs order by updated_at desc;"
```

5. Check SMTP send events:

```bash
docker compose exec -T postgres psql -U devsecops -d devsecops -c "select id, finding_id, flow_type, delivery_mode, to_emails, cc_emails, sent_at from smtp_send_events order by sent_at desc;"
```

Expected result:

```text
processing_logs.status = SENT
smtp_send_events contains:
  1 ticket_email event
  1 notify_email event
ManageEngine creates a request after Incoming Mail fetches the mailbox
```

Run the same command again without clearing the database to validate duplicate prevention:

```bash
docker compose run --rm -e ALLOW_SEND_REAL_FINDING_TO_GMAIL=yes app python scripts/process_active_verified_findings_to_configured_email.py --product-name "demo-dojo" --limit 1
```

The same finding should not create another email/ticket. `seen_count` may increase, but `smtp_send_events` should not add duplicate rows for the same finding and flow.

## Manual Test: 5 Products

Use this flow for a broader demo across multiple DefectDojo products.

1. Confirm `config/project_email_mapping.sample.json` contains all target products and approved recipients:

```json
{
  "project_name": "demo-dojo",
  "product_name": "demo-dojo",
  "ticket_mailbox": "me-ticket-mailbox@example.com",
  "to_destinations": ["customer-group@example.com", "devsecops-group@example.com"],
  "cc_destinations": ["devsecops-archive@example.com"]
}
```

In `email_fetch` mode, backend sends one ticket email to `ticket_mailbox` only, then one notify email to `to_destinations` and copies `cc_destinations`. In `api` mode, backend creates the ticket by API first, then sends one notify email to `to_destinations` and copies `cc_destinations`.

2. Rebuild the app image if the mapping file or Python code changed:

```bash
docker compose build app
```

Changing only `.env` does not require a rebuild; restart the app instead.

3. Stop the scheduler and clear local audit data:

```bash
docker compose stop app
docker compose up -d postgres
docker compose exec -T postgres psql -U devsecops -d devsecops -c "truncate table processing_logs, smtp_send_events restart identity;"
```

4. Run one finding per product:

```bash
docker compose run --rm -e ALLOW_SEND_REAL_FINDING_TO_GMAIL=yes app python scripts/process_active_verified_findings_to_configured_email.py --product-names "canhvp-demo,check_500,check_threagile,demo-devsecops-project,demo-dojo" --per-product-limit 1
```

5. Check database counts:

```bash
docker compose exec -T postgres psql -U devsecops -d devsecops -c "select 'processing_logs' as table_name, count(*) from processing_logs union all select 'smtp_send_events', count(*) from smtp_send_events;"
```

6. Check processed findings:

```bash
docker compose exec -T postgres psql -U devsecops -d devsecops -c "select finding_id, status, seen_count, to_emails, cc_emails, left(email_subject,160) as subject, processed_at, updated_at from processing_logs order by updated_at desc;"
```

7. Check send events:

```bash
docker compose exec -T postgres psql -U devsecops -d devsecops -c "select id, finding_id, flow_type, delivery_mode, to_emails, cc_emails, sent_at from smtp_send_events order by sent_at desc;"
```

8. Validate duplicate prevention by running the same command again without clearing the database:

```bash
docker compose run --rm -e ALLOW_SEND_REAL_FINDING_TO_GMAIL=yes app python scripts/process_active_verified_findings_to_configured_email.py --product-names "canhvp-demo,check_500,check_threagile,demo-devsecops-project,demo-dojo" --per-product-limit 1
```

Expected duplicate-test result:

```text
processing_logs keeps the same finding rows
seen_count increases when the same finding is observed again
smtp_send_events does not create duplicate send rows for the same finding and flow
ManageEngine should not create duplicate tickets for the same finding
```

## Scheduler Test: 5-minute Polling

Use scheduler mode for a deployment-like test. `.env` should contain:

```env
DEFECTDOJO_FINDINGS_LIMIT=100
DEFECTDOJO_REQUEST_TIMEOUT_SECONDS=60
SCHEDULER_INTERVAL_SECONDS=300
MANAGEENGINE_DELIVERY_MODE=email_fetch
```

Start the scheduler:

```bash
docker compose up -d app
docker compose logs -f app
```

The scheduler runs once on startup and then every `SCHEDULER_INTERVAL_SECONDS`. Stop it after manual testing to avoid repeated polling:

```bash
docker compose stop app
```

## Mode 2: ManageEngine API

Use this when backend creates tickets directly through ManageEngine API.

Flow:

```text
DefectDojo
  -> Backend + PostgreSQL dedupe
  -> POST /api/v3/requests
  -> Save ticket_id and ticket_status
  -> notify_email
       To: to_destinations
       Cc: cc_destinations
```

The notification email is sent only after ManageEngine ticket creation
succeeds.

`.env` for dry-run payload validation:

```env
MANAGEENGINE_DELIVERY_MODE=api
MANAGEENGINE_ENABLED=true
MANAGEENGINE_DRY_RUN=true
MANAGEENGINE_BASE_URL=https://manageengine.example.com
MANAGEENGINE_AUTH_TOKEN=XXXXXX
```

`.env` for real ticket creation:

```env
MANAGEENGINE_DELIVERY_MODE=api
MANAGEENGINE_ENABLED=true
MANAGEENGINE_DRY_RUN=false
MANAGEENGINE_BASE_URL=https://manageengine.example.com
MANAGEENGINE_AUTH_TOKEN=XXXXXX
```

If ManageEngine rejects `group`, `category`, or `subcategory`, keep them blank until the exact names exist in ManageEngine:

```env
MANAGEENGINE_DEFAULT_GROUP=
MANAGEENGINE_DEFAULT_CATEGORY=
MANAGEENGINE_DEFAULT_SUBCATEGORY=
```

## Useful Database Checks

```bash
docker compose exec -T postgres psql -U devsecops -d devsecops -c "
select finding_id, dedupe_key, status, to_emails, cc_emails, ticket_id, ticket_status,
left(coalesce(error_message,''),180) as error_message,
processed_at, updated_at
from processing_logs
order by updated_at desc
limit 20;
"
```

Check each SMTP flow separately:

```bash
docker compose exec -T postgres psql -U devsecops -d devsecops -c "
select id, finding_id, flow_type, delivery_mode, to_emails, cc_emails, sent_at
from smtp_send_events
order by sent_at desc
limit 30;
"
```

Reset local audit data for a clean test:

```bash
docker compose exec -T postgres psql -U devsecops -d devsecops -c "truncate table processing_logs, smtp_send_events restart identity;"
```

## Safety Notes

- Do not hardcode DefectDojo tokens, SMTP passwords, or ManageEngine tokens.
- Never commit `.env`, private keys, certificates, or exported credentials.
- Keep placeholders such as `XXXXXX` in `.env.example`.
- Do not send real security findings to personal mailboxes unless explicitly approved.
- Use `--limit 1` or `--per-product-limit 1` for the first manual test.
- Keep `MANAGEENGINE_DRY_RUN=true` until payload mapping is reviewed.
