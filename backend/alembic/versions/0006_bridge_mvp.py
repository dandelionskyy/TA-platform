"""Add isolated BRIDGE module packs, tutor sessions and staff-only artefacts."""

from alembic import op
import sqlalchemy as sa

revision = "0006_bridge_mvp"
down_revision = "0005_chat_file_context"
branch_labels = None
depends_on = None


def _id():
    return sa.Column("id", sa.String(36), primary_key=True)


def _module_fk():
    return sa.Column("module_id", sa.String(36), sa.ForeignKey("bridge_module_packs.id", ondelete="CASCADE"), nullable=False)


def upgrade() -> None:
    # 0001 creates all currently registered metadata on a brand-new database.
    # Existing installations at 0005 lack BRIDGE tables. Avoid duplicate DDL
    # on the former while still upgrading the latter.
    if sa.inspect(op.get_bind()).has_table("bridge_module_packs"):
        return
    op.create_table(
        "bridge_module_packs", _id(),
        sa.Column("course_id", sa.String(36), sa.ForeignKey("courses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("assessment_locked", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_bridge_module_packs_course_id", "bridge_module_packs", ["course_id"])
    op.create_table(
        "bridge_materials", _id(), _module_fk(),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("stored_path", sa.String(500), nullable=False),
        sa.Column("mime_type", sa.String(100)),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("processing_status", sa.String(20), nullable=False, server_default="queued"),
        sa.Column("processing_error", sa.String(300)),
        sa.Column("processing_started_at", sa.DateTime(timezone=True)),
        sa.Column("page_count", sa.Integer()),
        sa.Column("chunk_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("processed_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_bridge_materials_module_id", "bridge_materials", ["module_id"])
    op.create_index("ix_bridge_materials_processing_status", "bridge_materials", ["processing_status"])
    op.create_table(
        "bridge_chunks", _id(), _module_fk(),
        sa.Column("material_id", sa.String(36), sa.ForeignKey("bridge_materials.id", ondelete="CASCADE"), nullable=False),
        sa.Column("page_number", sa.Integer()),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("language", sa.String(10), nullable=False, server_default="mixed"),
        sa.Column("chunk_type", sa.String(20), nullable=False, server_default="UNREVIEWED"),
        sa.Column("reviewed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("embedding_json", sa.Text()),
        sa.UniqueConstraint("material_id", "chunk_index", name="uq_bridge_material_chunk"),
    )
    op.create_index("ix_bridge_chunks_module_id", "bridge_chunks", ["module_id"])
    op.create_index("ix_bridge_chunks_material_id", "bridge_chunks", ["material_id"])
    op.create_table(
        "bridge_staff_solutions", _id(), _module_fk(),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("stored_path", sa.String(500), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_bridge_staff_solutions_module_id", "bridge_staff_solutions", ["module_id"])
    op.create_table(
        "bridge_glossary_terms", _id(), _module_fk(),
        sa.Column("english", sa.String(200), nullable=False),
        sa.Column("chinese", sa.String(200), nullable=False),
        sa.Column("notes", sa.String(500), nullable=False, server_default=""),
        sa.UniqueConstraint("module_id", "english", name="uq_bridge_glossary_english"),
    )
    op.create_index("ix_bridge_glossary_terms_module_id", "bridge_glossary_terms", ["module_id"])
    op.create_table(
        "bridge_tutor_sessions", _id(), _module_fk(),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("pseudonym", sa.String(64), nullable=False),
        sa.Column("language", sa.String(10), nullable=False, server_default="en"),
        sa.Column("stage", sa.String(30), nullable=False, server_default="greeting"),
        sa.Column("concept_key", sa.String(100)),
        sa.Column("scaffold_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("mastery", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("assessment_locked", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_bridge_tutor_sessions_module_id", "bridge_tutor_sessions", ["module_id"])
    op.create_index("ix_bridge_tutor_sessions_token_hash", "bridge_tutor_sessions", ["token_hash"], unique=True)
    op.create_index("ix_bridge_tutor_sessions_pseudonym", "bridge_tutor_sessions", ["pseudonym"])
    op.create_index("ix_bridge_tutor_sessions_expires_at", "bridge_tutor_sessions", ["expires_at"])
    op.create_table(
        "bridge_learning_events", _id(), _module_fk(),
        sa.Column("session_id", sa.String(36), sa.ForeignKey("bridge_tutor_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("concept_key", sa.String(100)),
        sa.Column("event_type", sa.String(40), nullable=False),
        sa.Column("stage", sa.String(30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    for field in ("module_id", "session_id", "created_at"):
        op.create_index(f"ix_bridge_learning_events_{field}", "bridge_learning_events", [field])
    op.create_table(
        "bridge_daily_aggregates", _id(), _module_fk(),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("concept_key", sa.String(100), nullable=False, server_default=""),
        sa.Column("event_type", sa.String(40), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False, server_default="0"),
        sa.UniqueConstraint("module_id", "day", "concept_key", "event_type", name="uq_bridge_daily_aggregate"),
    )
    op.create_index("ix_bridge_daily_aggregates_module_id", "bridge_daily_aggregates", ["module_id"])
    op.create_table(
        "bridge_concepts", _id(), _module_fk(),
        sa.Column("key", sa.String(100), nullable=False),
        sa.Column("title_en", sa.String(200), nullable=False),
        sa.Column("title_zh", sa.String(200), nullable=False, server_default=""),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("source_chunk_id", sa.String(36), sa.ForeignKey("bridge_chunks.id", ondelete="SET NULL")),
        sa.Column("reviewed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.UniqueConstraint("module_id", "key", name="uq_bridge_concept_module_key"),
    )
    op.create_index("ix_bridge_concepts_module_id", "bridge_concepts", ["module_id"])
    op.create_table(
        "bridge_templates", _id(), _module_fk(),
        sa.Column("concept_id", sa.String(36), sa.ForeignKey("bridge_concepts.id", ondelete="SET NULL")),
        sa.Column("template_type", sa.String(30), nullable=False),
        sa.Column("language", sa.String(10), nullable=False, server_default="en"),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("source_chunk_id", sa.String(36), sa.ForeignKey("bridge_chunks.id", ondelete="SET NULL")),
        sa.Column("reviewed", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_bridge_templates_module_id", "bridge_templates", ["module_id"])
    op.create_table(
        "bridge_regression_prompts", _id(), _module_fk(),
        sa.Column("concept_id", sa.String(36), sa.ForeignKey("bridge_concepts.id", ondelete="SET NULL")),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("language", sa.String(10), nullable=False, server_default="en"),
        sa.Column("expected_chunk_id", sa.String(36), sa.ForeignKey("bridge_chunks.id", ondelete="SET NULL")),
        sa.Column("expected_status", sa.String(30), nullable=False, server_default="GROUNDED"),
        sa.Column("reviewed", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_bridge_regression_prompts_module_id", "bridge_regression_prompts", ["module_id"])


def downgrade() -> None:
    for name in (
        "bridge_regression_prompts", "bridge_templates", "bridge_concepts",
        "bridge_daily_aggregates", "bridge_learning_events", "bridge_tutor_sessions", "bridge_glossary_terms",
        "bridge_staff_solutions", "bridge_chunks", "bridge_materials", "bridge_module_packs",
    ):
        op.drop_table(name)
