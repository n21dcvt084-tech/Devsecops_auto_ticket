"""Add atomic dedupe leases and persistent notification delivery queues.

Revision ID: 20260625_0002
Revises: 20260625_0001
Create Date: 2026-06-25
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260625_0002"
down_revision: Union[str, None] = "20260625_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add retry payloads, dedupe leases, and notification delivery state."""
    op.add_column("processing_logs", sa.Column("email_html_body", sa.Text()))
    op.add_column(
        "processing_logs",
        sa.Column("next_attempt_at", sa.DateTime(timezone=True)),
    )
    op.create_index(
        "ix_processing_logs_next_attempt_at",
        "processing_logs",
        ["next_attempt_at"],
    )

    op.create_table(
        "dedupe_claims",
        sa.Column("dedupe_key", sa.String(length=80), primary_key=True),
        sa.Column("finding_id", sa.Integer(), nullable=False),
        sa.Column("lease_owner", sa.String(length=36)),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_dedupe_claims_finding_id", "dedupe_claims", ["finding_id"])
    op.create_index(
        "ix_dedupe_claims_lease_expires_at",
        "dedupe_claims",
        ["lease_expires_at"],
    )

    notification_status = sa.Enum(
        "PENDING",
        "SENT",
        "RETRY_PENDING",
        "FAILED",
        name="notification_status",
    )
    op.create_table(
        "notification_deliveries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("finding_id", sa.Integer(), nullable=False),
        sa.Column("dedupe_key", sa.String(length=80), nullable=False),
        sa.Column("recipient_email", sa.String(length=320), nullable=False),
        sa.Column("cc_emails", sa.Text()),
        sa.Column("email_subject", sa.String(length=500), nullable=False),
        sa.Column("email_body", sa.Text(), nullable=False),
        sa.Column("email_html_body", sa.Text()),
        sa.Column(
            "status",
            notification_status,
            nullable=False,
            server_default="PENDING",
        ),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True)),
        sa.Column("error_message", sa.Text()),
        sa.Column("lease_owner", sa.String(length=36)),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "finding_id",
            "recipient_email",
            name="uq_notification_delivery_finding_recipient",
        ),
    )
    op.create_index(
        "ix_notification_deliveries_finding_id",
        "notification_deliveries",
        ["finding_id"],
    )
    op.create_index(
        "ix_notification_deliveries_dedupe_key",
        "notification_deliveries",
        ["dedupe_key"],
    )
    op.create_index(
        "ix_notification_deliveries_status",
        "notification_deliveries",
        ["status"],
    )
    op.create_index(
        "ix_notification_deliveries_next_attempt_at",
        "notification_deliveries",
        ["next_attempt_at"],
    )
    op.create_index(
        "ix_notification_deliveries_lease_expires_at",
        "notification_deliveries",
        ["lease_expires_at"],
    )


def downgrade() -> None:
    """Remove delivery queues and retry payload columns."""
    op.drop_table("notification_deliveries")
    sa.Enum(name="notification_status").drop(op.get_bind(), checkfirst=True)
    op.drop_table("dedupe_claims")
    op.drop_index("ix_processing_logs_next_attempt_at", table_name="processing_logs")
    op.drop_column("processing_logs", "next_attempt_at")
    op.drop_column("processing_logs", "email_html_body")
