import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class MessagePermission(Base):
    """Teacher-controlled permission for a student to start a teacher chat."""

    __tablename__ = "message_permissions"
    __table_args__ = (
        UniqueConstraint("course_id", "student_id", name="uq_message_permission_course_student"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    course_id: Mapped[str] = mapped_column(String(36), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, index=True)
    student_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    teacher_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    accepted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="1")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class DirectThread(Base):
    """A direct conversation between any two members of one course."""

    __tablename__ = "direct_threads"
    __table_args__ = (
        UniqueConstraint("course_id", "participant_a_id", "participant_b_id", name="uq_direct_thread_course_participants"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    course_id: Mapped[str] = mapped_column(String(36), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, index=True)
    participant_a_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    participant_b_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class DirectMessage(Base):
    __tablename__ = "direct_messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    thread_id: Mapped[str] = mapped_column(String(36), ForeignKey("direct_threads.id", ondelete="CASCADE"), nullable=False, index=True)
    sender_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    is_read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
