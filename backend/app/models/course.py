import uuid
from datetime import datetime
from sqlalchemy import String, Integer, Text, DateTime, ForeignKey, func, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class Course(Base):
    __tablename__ = "courses"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    teacher_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    knowledge_base_path: Mapped[str] = mapped_column(String(500), default="")
    chapters_json: Mapped[str] = mapped_column(Text, default="[]")  # JSON array of chapter names
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Enrollment(Base):
    __tablename__ = "enrollments"
    __table_args__ = (UniqueConstraint("course_id", "student_id", name="uq_enrollment_course_student"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    course_id: Mapped[str] = mapped_column(String(36), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False)
    student_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    ta_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    enrolled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CourseStaff(Base):
    __tablename__ = "course_staff"
    __table_args__ = (UniqueConstraint("course_id", "user_id", name="uq_course_staff_course_user"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    course_id: Mapped[str] = mapped_column(String(36), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(10), nullable=False, default="ta")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CourseChapter(Base):
    __tablename__ = "course_chapters"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    course_id: Mapped[str] = mapped_column(String(36), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class CourseMaterial(Base):
    __tablename__ = "course_materials"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    course_id: Mapped[str] = mapped_column(String(36), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, index=True)
    chapter_id: Mapped[str] = mapped_column(String(36), ForeignKey("course_chapters.id", ondelete="CASCADE"), nullable=False, index=True)
    uploader_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_path: Mapped[str] = mapped_column(String(500), nullable=False)
    mime_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    extracted_text: Mapped[str] = mapped_column(Text, default="")
    processing_status: Mapped[str] = mapped_column(String(20), nullable=False, default="processed")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
