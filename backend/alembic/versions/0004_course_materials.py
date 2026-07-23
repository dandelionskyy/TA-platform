"""Add managed course chapters, materials and stable chapter conversations."""
import json
import uuid

from alembic import op
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, inspect, text

revision = "0004_course_materials"
down_revision = "0003_messaging"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if not inspector.has_table("course_chapters"):
        op.create_table(
            "course_chapters",
            op.Column("id", String(36), primary_key=True),
            op.Column("course_id", String(36), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False),
            op.Column("title", String(200), nullable=False),
            op.Column("description", Text, nullable=False, server_default=""),
            op.Column("sort_order", Integer, nullable=False, server_default="0"),
            op.Column("created_by", String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            op.Column("created_at", DateTime(timezone=True), nullable=True),
            op.Column("updated_at", DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_course_chapters_course_id", "course_chapters", ["course_id"])
    if not inspector.has_table("course_materials"):
        op.create_table(
            "course_materials",
            op.Column("id", String(36), primary_key=True),
            op.Column("course_id", String(36), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False),
            op.Column("chapter_id", String(36), ForeignKey("course_chapters.id", ondelete="CASCADE"), nullable=False),
            op.Column("uploader_id", String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            op.Column("filename", String(255), nullable=False),
            op.Column("stored_path", String(500), nullable=False),
            op.Column("mime_type", String(100), nullable=True),
            op.Column("size_bytes", Integer, nullable=False),
            op.Column("extracted_text", Text, nullable=False, server_default=""),
            op.Column("processing_status", String(20), nullable=False, server_default="processed"),
            op.Column("created_at", DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_course_materials_course_id", "course_materials", ["course_id"])
        op.create_index("ix_course_materials_chapter_id", "course_materials", ["chapter_id"])
    inspector = inspect(bind)
    conversation_columns = {column["name"] for column in inspector.get_columns("conversations")}
    if "chapter_id" not in conversation_columns:
        with op.batch_alter_table("conversations") as batch_op:
            batch_op.add_column(op.Column("chapter_id", String(36), ForeignKey("course_chapters.id", ondelete="SET NULL"), nullable=True))
            batch_op.create_index("ix_conversations_chapter_id", ["chapter_id"])

    rows = bind.execute(text("SELECT id, chapters_json FROM courses")).mappings().all()
    for row in rows:
        try:
            titles = json.loads(row["chapters_json"] or "[]")
        except (json.JSONDecodeError, TypeError):
            titles = []
        titles = [title.strip() for title in titles if isinstance(title, str) and title.strip()]
        count = bind.execute(text(
            "SELECT COUNT(*) FROM course_chapters WHERE course_id = :course_id"
        ), {"course_id": row["id"]}).scalar_one()
        if titles and not count:
            for index, title in enumerate(titles):
                bind.execute(text(
                    "INSERT INTO course_chapters (id, course_id, title, description, sort_order) "
                    "VALUES (:id, :course_id, :title, '', :sort_order)"
                ), {"id": str(uuid.uuid4()), "course_id": row["id"], "title": title, "sort_order": index})
        if titles:
            bind.execute(text("UPDATE courses SET chapters_json = '[]' WHERE id = :course_id"), {"course_id": row["id"]})


def downgrade() -> None:
    with op.batch_alter_table("conversations") as batch_op:
        batch_op.drop_index("ix_conversations_chapter_id")
        batch_op.drop_column("chapter_id")
    op.drop_table("course_materials")
    op.drop_table("course_chapters")
