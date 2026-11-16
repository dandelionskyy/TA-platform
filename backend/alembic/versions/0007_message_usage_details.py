"""Store model and token usage details for teacher analytics."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect


revision = "0007_message_usage_details"
down_revision = "0006_bridge_mvp"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    columns = {column["name"] for column in inspect(bind).get_columns("messages")}
    with op.batch_alter_table("messages") as batch_op:
        if "prompt_tokens" not in columns:
            batch_op.add_column(sa.Column("prompt_tokens", sa.Integer(), nullable=True))
        if "completion_tokens" not in columns:
            batch_op.add_column(sa.Column("completion_tokens", sa.Integer(), nullable=True))
        if "model_name" not in columns:
            batch_op.add_column(sa.Column("model_name", sa.String(100), nullable=True))
        if "response_time_ms" not in columns:
            batch_op.add_column(sa.Column("response_time_ms", sa.Integer(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    columns = {column["name"] for column in inspect(bind).get_columns("messages")}
    with op.batch_alter_table("messages") as batch_op:
        for name in ("response_time_ms", "model_name", "completion_tokens", "prompt_tokens"):
            if name in columns:
                batch_op.drop_column(name)
