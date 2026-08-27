"""users: contact_name (имя из последнего заказа — для быстрого повторного оформления)

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-28

"""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("contact_name", sa.String(length=128), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "contact_name")