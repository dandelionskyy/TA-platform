import uuid
from datetime import datetime
from sqlalchemy import String, Integer, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class FileAsset(Base):
    __tablename__ = "file_assets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    conversation_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True, index=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    processing_status: Mapped[str] = mapped_column(String(20), default="processed")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
