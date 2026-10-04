"""BRIDGE-specific records. Student source search reads teaching chunks only.

Solutions are deliberately in a separate table and are never joined by the
student retrieval service. Tutor sessions retain only a hash of their bearer
token, a pseudonym and small state/event records, not conversation transcripts.
"""

import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class BridgeModulePack(Base):
    __tablename__ = "bridge_module_packs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    course_id: Mapped[str] = mapped_column(String(36), ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    assessment_locked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class BridgeMaterial(Base):
    __tablename__ = "bridge_materials"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    module_id: Mapped[str] = mapped_column(String(36), ForeignKey("bridge_module_packs.id", ondelete="CASCADE"), nullable=False, index=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_path: Mapped[str] = mapped_column(String(500), nullable=False)
    mime_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    processing_status: Mapped[str] = mapped_column(String(20), nullable=False, default="queued", index=True)
    processing_error: Mapped[str | None] = mapped_column(String(300), nullable=True)
    processing_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    chunks: Mapped[list["BridgeChunk"]] = relationship(back_populates="material", cascade="all, delete-orphan", passive_deletes=True)


class BridgeChunk(Base):
    __tablename__ = "bridge_chunks"
    __table_args__ = (UniqueConstraint("material_id", "chunk_index", name="uq_bridge_material_chunk"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    module_id: Mapped[str] = mapped_column(String(36), ForeignKey("bridge_module_packs.id", ondelete="CASCADE"), nullable=False, index=True)
    material_id: Mapped[str] = mapped_column(String(36), ForeignKey("bridge_materials.id", ondelete="CASCADE"), nullable=False, index=True)
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    language: Mapped[str] = mapped_column(String(10), nullable=False, default="mixed")
    chunk_type: Mapped[str] = mapped_column(String(20), nullable=False, default="UNREVIEWED")
    reviewed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    embedding_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    material: Mapped[BridgeMaterial] = relationship(back_populates="chunks")


class BridgeStaffSolution(Base):
    """Restricted source file: there is intentionally no student retrieval FK."""

    __tablename__ = "bridge_staff_solutions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    module_id: Mapped[str] = mapped_column(String(36), ForeignKey("bridge_module_packs.id", ondelete="CASCADE"), nullable=False, index=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_path: Mapped[str] = mapped_column(String(500), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class BridgeGlossaryTerm(Base):
    __tablename__ = "bridge_glossary_terms"
    __table_args__ = (UniqueConstraint("module_id", "english", name="uq_bridge_glossary_english"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    module_id: Mapped[str] = mapped_column(String(36), ForeignKey("bridge_module_packs.id", ondelete="CASCADE"), nullable=False, index=True)
    english: Mapped[str] = mapped_column(String(200), nullable=False)
    chinese: Mapped[str] = mapped_column(String(200), nullable=False)
    notes: Mapped[str] = mapped_column(String(500), nullable=False, default="")


class BridgeTutorSession(Base):
    __tablename__ = "bridge_tutor_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    pseudonym: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    module_id: Mapped[str] = mapped_column(String(36), ForeignKey("bridge_module_packs.id", ondelete="CASCADE"), nullable=False, index=True)
    language: Mapped[str] = mapped_column(String(10), nullable=False, default="en")
    stage: Mapped[str] = mapped_column(String(30), nullable=False, default="greeting")
    concept_key: Mapped[str | None] = mapped_column(String(100), nullable=True)
    scaffold_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    mastery: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    assessment_locked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class BridgeLearningEvent(Base):
    __tablename__ = "bridge_learning_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    module_id: Mapped[str] = mapped_column(String(36), ForeignKey("bridge_module_packs.id", ondelete="CASCADE"), nullable=False, index=True)
    session_id: Mapped[str] = mapped_column(String(36), ForeignKey("bridge_tutor_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    concept_key: Mapped[str | None] = mapped_column(String(100), nullable=True)
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    stage: Mapped[str] = mapped_column(String(30), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


class BridgeDailyAggregate(Base):
    """Counts without a learner ID, preserved after 30-day event/session deletion."""

    __tablename__ = "bridge_daily_aggregates"
    __table_args__ = (UniqueConstraint("module_id", "day", "concept_key", "event_type", name="uq_bridge_daily_aggregate"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    module_id: Mapped[str] = mapped_column(String(36), ForeignKey("bridge_module_packs.id", ondelete="CASCADE"), nullable=False, index=True)
    day: Mapped[date] = mapped_column(Date, nullable=False)
    concept_key: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class BridgeConcept(Base):
    __tablename__ = "bridge_concepts"
    __table_args__ = (UniqueConstraint("module_id", "key", name="uq_bridge_concept_module_key"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    module_id: Mapped[str] = mapped_column(String(36), ForeignKey("bridge_module_packs.id", ondelete="CASCADE"), nullable=False, index=True)
    key: Mapped[str] = mapped_column(String(100), nullable=False)
    title_en: Mapped[str] = mapped_column(String(200), nullable=False)
    title_zh: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    source_chunk_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("bridge_chunks.id", ondelete="SET NULL"), nullable=True)
    reviewed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class BridgeTemplate(Base):
    __tablename__ = "bridge_templates"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    module_id: Mapped[str] = mapped_column(String(36), ForeignKey("bridge_module_packs.id", ondelete="CASCADE"), nullable=False, index=True)
    concept_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("bridge_concepts.id", ondelete="SET NULL"), nullable=True)
    template_type: Mapped[str] = mapped_column(String(30), nullable=False)
    language: Mapped[str] = mapped_column(String(10), nullable=False, default="en")
    text: Mapped[str] = mapped_column(Text, nullable=False)
    source_chunk_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("bridge_chunks.id", ondelete="SET NULL"), nullable=True)
    reviewed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class BridgeRegressionPrompt(Base):
    __tablename__ = "bridge_regression_prompts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    module_id: Mapped[str] = mapped_column(String(36), ForeignKey("bridge_module_packs.id", ondelete="CASCADE"), nullable=False, index=True)
    concept_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("bridge_concepts.id", ondelete="SET NULL"), nullable=True)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str] = mapped_column(String(10), nullable=False, default="en")
    expected_chunk_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("bridge_chunks.id", ondelete="SET NULL"), nullable=True)
    expected_status: Mapped[str] = mapped_column(String(30), nullable=False, default="GROUNDED")
    reviewed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
