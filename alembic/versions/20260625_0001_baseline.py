"""Create the initial audit schema or baseline an existing compatible schema.

Revision ID: 20260625_0001
Revises:
Create Date: 2026-06-25
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260625_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

PROCESSING_COLUMNS = {
    "id",
    "finding_id",
    "dedupe_key",
    "ticket_id",
    "ticket_status",
    "last_seen_at",
    "seen_count",
    "priority",
    "sla_target",
    "sla_due_at",
    "recipient_email",
    "email_subject",
    "email_body",
    "status",
    "retry_count",
    "error_message",
    "processed_at",
    "created_at",
    "updated_at",
}

SMTP_EVENT_COLUMNS = {
    "id",
    "finding_id",
    "recipient_email",
    "cc_emails",
    "flow_type",
    "delivery_mode",
    "sent_at",
}


def _validate_existing_table(inspector, table_name: str, expected: set[str]) -> None:
    """Refuse to baseline an existing table with an incomplete schema."""
    actual = {column["name"] for column in inspector.get_columns(table_name)}
    missing = expected - actual
    if missing:
        raise RuntimeError(
            f"Existing table {table_name} is missing required columns: "
            f"{', '.join(sorted(missing))}"
        )


def upgrade() -> None:
    """Create a new schema or mark an existing compatible schema as baseline."""
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    tables = set(inspector.get_table_names())

    processing_status = sa.Enum(
        "PENDING",
        "SENT",
        "FAILED",
        "SKIPPED",
        "RATE_LIMITED",
        "INVALID_RECIPIENT",
        name="processing_status",
    )

    if "processing_logs" not in tables:
        op.create_table(
            "processing_logs",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("finding_id", sa.Integer(), nullable=False),
            sa.Column("dedupe_key", sa.String(length=80)),
            sa.Column("ticket_id", sa.String(length=120)),
            sa.Column("ticket_status", sa.String(length=80)),
            sa.Column("last_seen_at", sa.DateTime(timezone=True)),
            sa.Column("seen_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("priority", sa.String(length=80)),
            sa.Column("sla_target", sa.String(length=80)),
            sa.Column("sla_due_at", sa.DateTime(timezone=True)),
            sa.Column("recipient_email", sa.String(length=320)),
            sa.Column("email_subject", sa.String(length=500)),
            sa.Column("email_body", sa.Text()),
            sa.Column(
                "status",
                processing_status,
                nullable=False,
                server_default="PENDING",
            ),
            sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("error_message", sa.Text()),
            sa.Column("processed_at", sa.DateTime(timezone=True)),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint(
                "finding_id",
                name="uq_processing_logs_finding_id",
            ),
        )
        op.create_index(
            "ix_processing_logs_finding_id",
            "processing_logs",
            ["finding_id"],
        )
        op.create_index(
            "ix_processing_logs_dedupe_key",
            "processing_logs",
            ["dedupe_key"],
        )
        op.create_index(
            "ix_processing_logs_ticket_id",
            "processing_logs",
            ["ticket_id"],
        )
        op.create_index(
            "ix_processing_logs_status",
            "processing_logs",
            ["status"],
        )
    else:
        _validate_existing_table(inspector, "processing_logs", PROCESSING_COLUMNS)

    if "smtp_send_events" not in tables:
        op.create_table(
            "smtp_send_events",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("finding_id", sa.Integer()),
            sa.Column("recipient_email", sa.String(length=320), nullable=False),
            sa.Column("cc_emails", sa.Text()),
            sa.Column("flow_type", sa.String(length=80)),
            sa.Column("delivery_mode", sa.String(length=40)),
            sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index(
            "ix_smtp_send_events_finding_id",
            "smtp_send_events",
            ["finding_id"],
        )
        op.create_index(
            "ix_smtp_send_events_flow_type",
            "smtp_send_events",
            ["flow_type"],
        )
        op.create_index(
            "ix_smtp_send_events_sent_at",
            "smtp_send_events",
            ["sent_at"],
        )
    else:
        _validate_existing_table(inspector, "smtp_send_events", SMTP_EVENT_COLUMNS)


def downgrade() -> None:
    """Drop the initial audit schema when explicitly downgrading the database."""
    op.drop_table("smtp_send_events")
    op.drop_table("processing_logs")
    sa.Enum(name="processing_status").drop(op.get_bind(), checkfirst=True)
