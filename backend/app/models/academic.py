import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Assignment(Base):
    __tablename__ = "assignments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    course_id: Mapped[str] = mapped_column(String(36), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, index=True)
    creator_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    instructions: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    max_score: Mapped[int] = mapped_column(Integer, default=100)
    allow_late: Mapped[bool] = mapped_column(Boolean, default=False)
    allow_resubmit: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Submission(Base):
    __tablename__ = "submissions"
    __table_args__ = (UniqueConstraint("assignment_id", "student_id", name="uq_submission_assignment_student"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    assignment_id: Mapped[str] = mapped_column(String(36), ForeignKey("assignments.id", ondelete="CASCADE"), nullable=False, index=True)
    student_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    answer_text: Mapped[str] = mapped_column(Text, default="")
    file_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    file_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="submitted", index=True)
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    feedback: Mapped[str] = mapped_column(Text, default="")
    graded_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    graded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AttendanceSession(Base):
    __tablename__ = "attendance_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    course_id: Mapped[str] = mapped_column(String(36), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, index=True)
    creator_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    title: Mapped[str] = mapped_column(String(200), default="Class attendance")
    code: Mapped[str] = mapped_column(String(12), nullable=False, index=True)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="open", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AttendanceRecord(Base):
    __tablename__ = "attendance_records"
    __table_args__ = (UniqueConstraint("session_id", "student_id", name="uq_attendance_session_student"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id: Mapped[str] = mapped_column(String(36), ForeignKey("attendance_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    student_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), default="present")
    checked_in_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    note: Mapped[str] = mapped_column(String(500), default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Announcement(Base):
    __tablename__ = "announcements"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    course_id: Mapped[str] = mapped_column(String(36), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, index=True)
    author_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    content: Mapped[str] = mapped_column(Text, default="")
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
