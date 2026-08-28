"""order_items: product_grams — снапшот веса упаковки для весовых товаров
(quantity в порциях; без колонки нельзя восстановить сумму и метку после смены меню)

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-28

"""
from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("order_items", sa.Column("product_grams", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("order_items", "product_grams")