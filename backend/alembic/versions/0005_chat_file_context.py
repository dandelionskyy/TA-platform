"""Persist chat files and their extracted document context."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "0005_chat_file_context"
down_revision = "0004_course_materials"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    columns = {column["name"] for column in inspect(bind).get_columns("file_assets")}
    additions = [
        ("stored_path", sa.Column("stored_path", sa.String(500), nullable=True)),
        ("extracted_text", sa.Column("extracted_text", sa.Text(), nullable=False, server_default="")),
        ("page_count", sa.Column("page_count", sa.Integer(), nullable=True)),
        ("is_active", sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true())),
    ]
    with op.batch_alter_table("file_assets") as batch_op:
        for name, column in additions:
            if name not in columns:
                batch_op.add_column(column)


def downgrade() -> None:
    bind = op.get_bind()
    columns = {column["name"] for column in inspect(bind).get_columns("file_assets")}
    with op.batch_alter_table("file_assets") as batch_op:
        for name in ("is_active", "page_count", "extracted_text", "stored_path"):
            if name in columns:
                batch_op.drop_column(name)
