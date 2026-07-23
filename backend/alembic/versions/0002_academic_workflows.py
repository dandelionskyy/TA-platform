"""Add assignments, submissions, attendance and course announcements."""
from alembic import op
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, inspect

revision = "0002_academic_workflows"
down_revision = "0001_platform_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if not inspector.has_table("assignments"):
        op.create_table(
            "assignments",
            op.Column("id", String(36), primary_key=True),
            op.Column("course_id", String(36), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False),
            op.Column("creator_id", String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            op.Column("title", String(200), nullable=False),
            op.Column("instructions", Text, nullable=False, server_default=""),
            op.Column("status", String(20), nullable=False, server_default="draft"),
            op.Column("due_at", DateTime(timezone=True), nullable=True),
            op.Column("max_score", Integer, nullable=False, server_default="100"),
            op.Column("allow_late", Boolean, nullable=False, server_default="0"),
            op.Column("allow_resubmit", Boolean, nullable=False, server_default="1"),
            op.Column("created_at", DateTime(timezone=True), nullable=True),
            op.Column("updated_at", DateTime(timezone=True), nullable=True),
        )
    if not inspector.has_table("submissions"):
        op.create_table(
            "submissions",
            op.Column("id", String(36), primary_key=True),
            op.Column("assignment_id", String(36), ForeignKey("assignments.id", ondelete="CASCADE"), nullable=False),
            op.Column("student_id", String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            op.Column("answer_text", Text, nullable=False, server_default=""),
            op.Column("file_name", String(255), nullable=True),
            op.Column("file_path", String(500), nullable=True),
            op.Column("status", String(20), nullable=False, server_default="submitted"),
            op.Column("score", Integer, nullable=True),
            op.Column("feedback", Text, nullable=False, server_default=""),
            op.Column("graded_by", String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            op.Column("submitted_at", DateTime(timezone=True), nullable=True),
            op.Column("updated_at", DateTime(timezone=True), nullable=True),
            op.Column("graded_at", DateTime(timezone=True), nullable=True),
            op.UniqueConstraint("assignment_id", "student_id", name="uq_submission_assignment_student"),
        )
    if not inspector.has_table("attendance_sessions"):
        op.create_table(
            "attendance_sessions",
            op.Column("id", String(36), primary_key=True),
            op.Column("course_id", String(36), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False),
            op.Column("creator_id", String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            op.Column("title", String(200), nullable=False, server_default="Class attendance"),
            op.Column("code", String(12), nullable=False),
            op.Column("starts_at", DateTime(timezone=True), nullable=False),
            op.Column("ends_at", DateTime(timezone=True), nullable=False),
            op.Column("status", String(20), nullable=False, server_default="open"),
            op.Column("created_at", DateTime(timezone=True), nullable=True),
        )
    if not inspector.has_table("attendance_records"):
        op.create_table(
            "attendance_records",
            op.Column("id", String(36), primary_key=True),
            op.Column("session_id", String(36), ForeignKey("attendance_sessions.id", ondelete="CASCADE"), nullable=False),
            op.Column("student_id", String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            op.Column("status", String(20), nullable=False, server_default="present"),
            op.Column("checked_in_at", DateTime(timezone=True), nullable=True),
            op.Column("note", String(500), nullable=False, server_default=""),
            op.Column("updated_at", DateTime(timezone=True), nullable=True),
            op.UniqueConstraint("session_id", "student_id", name="uq_attendance_session_student"),
        )
    if not inspector.has_table("announcements"):
        op.create_table(
            "announcements",
            op.Column("id", String(36), primary_key=True),
            op.Column("course_id", String(36), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False),
            op.Column("author_id", String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            op.Column("title", String(200), nullable=False),
            op.Column("content", Text, nullable=False, server_default=""),
            op.Column("published_at", DateTime(timezone=True), nullable=True),
            op.Column("expires_at", DateTime(timezone=True), nullable=True),
            op.Column("created_at", DateTime(timezone=True), nullable=True),
        )


def downgrade() -> None:
    op.drop_table("announcements")
    op.drop_table("attendance_records")
    op.drop_table("attendance_sessions")
    op.drop_table("submissions")
    op.drop_table("assignments")
