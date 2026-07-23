"""Add course-scoped direct messaging and teacher message permissions."""
from alembic import op
from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, inspect

revision = "0003_messaging"
down_revision = "0002_academic_workflows"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if not inspector.has_table("message_permissions"):
        op.create_table(
            "message_permissions",
            op.Column("id", String(36), primary_key=True),
            op.Column("course_id", String(36), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False),
            op.Column("student_id", String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            op.Column("teacher_id", String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            op.Column("accepted", Boolean, nullable=False, server_default="1"),
            op.Column("updated_at", DateTime(timezone=True), nullable=True),
            op.UniqueConstraint("course_id", "student_id", name="uq_message_permission_course_student"),
        )
    if not inspector.has_table("direct_threads"):
        op.create_table(
            "direct_threads",
            op.Column("id", String(36), primary_key=True),
            op.Column("course_id", String(36), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False),
            op.Column("participant_a_id", String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            op.Column("participant_b_id", String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            op.Column("created_at", DateTime(timezone=True), nullable=True),
            op.Column("updated_at", DateTime(timezone=True), nullable=True),
            op.UniqueConstraint("course_id", "participant_a_id", "participant_b_id", name="uq_direct_thread_course_participants"),
        )
    if not inspector.has_table("direct_messages"):
        op.create_table(
            "direct_messages",
            op.Column("id", String(36), primary_key=True),
            op.Column("thread_id", String(36), ForeignKey("direct_threads.id", ondelete="CASCADE"), nullable=False),
            op.Column("sender_id", String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            op.Column("content", Text, nullable=False),
            op.Column("is_read", Boolean, nullable=False, server_default="0"),
            op.Column("created_at", DateTime(timezone=True), nullable=True),
        )


def downgrade() -> None:
    op.drop_table("direct_messages")
    op.drop_table("direct_threads")
    op.drop_table("message_permissions")
