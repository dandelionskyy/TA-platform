import uuid
from datetime import datetime
from sqlalchemy import String, Integer, Float, Text, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class RobotStatus(Base):
    __tablename__ = "robot_status"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    robot_name: Mapped[str] = mapped_column(String(100), default="TA-Robot-01")
    status: Mapped[str] = mapped_column(String(20), default="standby")  # active, standby, offline, charging
    battery_pct: Mapped[int] = mapped_column(Integer, default=100)
    position_x: Mapped[float] = mapped_column(Float, nullable=True)
    position_y: Mapped[float] = mapped_column(Float, nullable=True)
    position_label: Mapped[str] = mapped_column(String(200), default="")
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class RobotQuestion(Base):
    __tablename__ = "robot_questions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    robot_id: Mapped[str] = mapped_column(String(36), ForeignKey("robot_status.id"), nullable=False)
    student_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    response_text: Mapped[str] = mapped_column(Text, nullable=True)
    voice_audio_url: Mapped[str] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
