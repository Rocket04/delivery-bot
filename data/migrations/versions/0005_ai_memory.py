"""ai_chat_history + ai_llm_calls — персистентная память ИИ-ассистента (ARCHITECTURE_REVIEW P1).

История FAQ-диалогов в БД с TTL-чисткой (вместо in-memory deque бота) и
учёт LLM-вызовов на пользователя для лимита (скользящее окно).

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-28

"""
from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_chat_history",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),  # user | assistant
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_ai_chat_history_user_created", "ai_chat_history", ["user_id", "created_at"])

    op.create_table(
        "ai_llm_calls",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_ai_llm_calls_user_created", "ai_llm_calls", ["user_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_ai_llm_calls_user_created", table_name="ai_llm_calls")
    op.drop_table("ai_llm_calls")
    op.drop_index("ix_ai_chat_history_user_created", table_name="ai_chat_history")
    op.drop_table("ai_chat_history")