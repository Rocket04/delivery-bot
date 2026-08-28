"""payment_events — идемпотентность Kaspi-платежей (ARCHITECTURE_REVIEW P0).

Уникальный ключ (external_id, type): повторный webhook отбрасывается
(INSERT ... ON CONFLICT DO NOTHING в core.payments.record_payment_event).

Revision ID: 0006
Revises: 0005
Create Date: 2026-08-28

"""
from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "payment_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("external_id", sa.String(length=64), nullable=False),
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("payload", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("external_id", "type", name="uq_payment_events_ext_type"),
    )


def downgrade() -> None:
    op.drop_table("payment_events")