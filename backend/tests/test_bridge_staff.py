"""Meaningful BRIDGE staff invariants: no invented content, no cross-course edit,
no revealing small aggregate cells, and no overwriting teacher-reviewed drafts.
"""

import asyncio
from types import SimpleNamespace

from app.services.bridge_compiler import (
    compiler_gaps, draft_concepts, draft_regression_prompts, draft_templates,
)
from app.services.bridge_analytics import summarise_counts


def test_compiler_does_not_invent_misconceptions_or_translate_heading():
    chunks = [SimpleNamespace(id="chunk-1", text="# Semiconductor Doping\nDonor and acceptor regions are compared.")]
    concepts = draft_concepts(chunks)
    assert len(concepts) == 1
    assert concepts[0].title_en == "Semiconductor Doping"
    assert concepts[0].title_zh == ""
    templates = draft_templates(concepts)
    misconception = next(item for item in templates if item["type"] == "misconception")
    assert not misconception["reviewed"]
    assert "TEACHER TO COMPLETE" in misconception["text"]
    assert "Only 5 source-linked" in " ".join(compiler_gaps(chunks, concepts, draft_regression_prompts(concepts)))


def test_compiler_supplies_20_to_50_source_linked_prompts_when_material_supports_it():
    chunks = [SimpleNamespace(id=f"chunk-{i}", text=f"# Topic {i} label\nEvidence in topic {i}.") for i in range(6)]
    concepts = draft_concepts(chunks)
    prompts = draft_regression_prompts(concepts)
    assert 20 <= len(prompts) <= 50
    assert all(item["expected_chunk_id"] in {chunk.id for chunk in chunks} and not item["reviewed"] for item in prompts)


def test_dashboard_hides_small_groups_and_does_not_allow_subtraction():
    report = summarise_counts([
        ("misconception", "logic-gates", 11),
        ("misconception", "tiny-group", 2),
    ])
    assert report["interaction_count_band"] == "10–19"
    assert report["misconceptions"] == [{"concept_key": "logic-gates", "count": 11}]
    assert "2" not in str(report)
    report_under_threshold = summarise_counts([("misconception", "tiny-group", 9)])
    assert report_under_threshold["interaction_count_band"] == "suppressed"
    assert report_under_threshold["misconceptions"] == []


def test_dashboard_only_suggests_interventions_for_publishable_cells():
    visible_id = "00000000-0000-0000-0000-000000000001"
    hidden_id = "00000000-0000-0000-0000-000000000002"
    report = summarise_counts([
        ("struggled", "circuit-analysis", 10),
        ("struggled", "single-student-concept", 1),
        ("source_retrieved", "material:" + visible_id, 15),
        ("source_retrieved", "material:" + hidden_id, 4),
    ])
    assert report["stall_points"] == [{"concept_key": "circuit-analysis", "count": 10}]
    assert report["most_retrieved_materials"] == [{"material_id": visible_id, "count": 15}]
    assert all(item["concept_key"] != "single-student-concept" for item in report["suggested_interventions"])
    assert report["interaction_count_band"] == "10–19"  # cited material events do not count as turns


def test_daily_anonymous_counts_survive_session_event_deletion(tmp_path):
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import delete, select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from app.core.database import Base
    from app.models.base import Course, User
    from app.models.bridge import (
        BridgeDailyAggregate, BridgeLearningEvent, BridgeModulePack, BridgeTutorSession,
    )
    from app.services.bridge_analytics import record_bridge_event, dashboard_for_module

    async def scenario():
        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'bridge_analytics.sqlite'}")
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as db:
            owner = User(student_id="analytics-owner", phone="13000000003", password_hash="hash", role="teacher")
            db.add(owner)
            await db.flush()
            course = Course(name="Test", teacher_id=owner.id)
            db.add(course)
            await db.flush()
            pack = BridgeModulePack(course_id=course.id, title="Module")
            db.add(pack)
            await db.flush()
            session = BridgeTutorSession(module_id=pack.id, token_hash="a" * 64,
                pseudonym="some-pseudonym", expires_at=datetime.now(timezone.utc) + timedelta(days=1))
            db.add(session)
            await db.flush()
            for _ in range(10):
                await record_bridge_event(db, session, "logic-gates", "misconception", "check")
            await db.commit()
            rows = (await db.scalars(select(BridgeDailyAggregate))).all()
            assert len(rows) == 1 and rows[0].count == 10
            assert "session" not in " ".join(column.name for column in BridgeDailyAggregate.__table__.columns)
            await db.execute(delete(BridgeLearningEvent).where(BridgeLearningEvent.session_id == session.id))
            await db.delete(session)
            await db.commit()
            report = await dashboard_for_module(db, pack.id)
            assert report["misconceptions"] == [{"concept_key": "logic-gates", "count": 10}]
        await engine.dispose()

    asyncio.run(scenario())


def test_teacher_cannot_open_another_teachers_pack(tmp_path):
    """Exercise the database ownership check that guards every staff route."""
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from app.core.database import Base
    from app.models.base import Course, User
    from app.models.bridge import BridgeModulePack
    from app.routers.bridge_staff import _teacher_module
    from fastapi import HTTPException

    async def scenario():
        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'bridge_staff.sqlite'}")
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as db:
            owner = User(student_id="owner", phone="13000000001", password_hash="hash", role="teacher")
            stranger = User(student_id="stranger", phone="13000000002", password_hash="hash", role="teacher")
            db.add_all([owner, stranger])
            await db.flush()
            course = Course(name="Test", teacher_id=owner.id)
            db.add(course)
            await db.flush()
            pack = BridgeModulePack(course_id=course.id, title="Module")
            db.add(pack)
            await db.commit()
            assert (await _teacher_module(db, owner, pack.id)).id == pack.id
            try:
                await _teacher_module(db, stranger, pack.id)
            except HTTPException as exc:
                assert exc.status_code == 404
            else:
                raise AssertionError("Cross-course BRIDGE pack was exposed")
        await engine.dispose()

    asyncio.run(scenario())


def test_recompiling_pack_preserves_teacher_reviewed_edits(tmp_path):
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from app.core.database import Base
    from app.models.base import Course, User
    from app.models.bridge import BridgeChunk, BridgeMaterial, BridgeModulePack
    from app.routers.bridge_staff import ConceptEdit, compile_pack, edit_concept

    async def scenario():
        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'bridge_compile.sqlite'}")
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as db:
            owner = User(student_id="compiler-owner", phone="13000000004", password_hash="hash", role="teacher")
            db.add(owner)
            await db.flush()
            course = Course(name="Test", teacher_id=owner.id)
            db.add(course)
            await db.flush()
            pack = BridgeModulePack(course_id=course.id, title="Module")
            db.add(pack)
            await db.flush()
            material = BridgeMaterial(module_id=pack.id, filename="notes.txt", stored_path="/tmp/notes.txt",
                size_bytes=500, processing_status="ready")
            db.add(material)
            await db.flush()
            for number in range(4):
                db.add(BridgeChunk(module_id=pack.id, material_id=material.id, chunk_index=number,
                    text=f"# Topic {number} label\nThe chapter discusses topic {number}."))
            await db.flush()
            compiled = await compile_pack(pack.id, owner, db)
            assert compiled["created_counts"] == {"concepts": 4, "templates": 8, "regression_prompts": 20}
            concept = compiled["concepts"][0]
            # Drafts can be compiled from unreviewed material, but staff may
            # approve one only after tagging that source for safe retrieval.
            from fastapi import HTTPException
            try:
                await edit_concept(pack.id, concept["id"], ConceptEdit(reviewed=True), owner, db)
            except HTTPException as exc:
                assert exc.status_code == 422
            else:
                raise AssertionError("Unreviewed source was accepted")
            for chunk in (await db.scalars(select(BridgeChunk))).all():
                chunk.chunk_type = "DEFINITION"
                chunk.reviewed = True
            await db.flush()
            await edit_concept(pack.id, concept["id"], ConceptEdit(description="Teacher revised and checked.", reviewed=True), owner, db)
            again = await compile_pack(pack.id, owner, db)
            assert again["created_counts"] == {"concepts": 0, "templates": 0, "regression_prompts": 0}
            edited = next(item for item in again["concepts"] if item["id"] == concept["id"])
            assert edited["reviewed"] and edited["description"] == "Teacher revised and checked."
        await engine.dispose()

    asyncio.run(scenario())


def test_pack_runner_checks_guarded_sources_and_out_of_scope_response(tmp_path, monkeypatch):
    """Prototype retrieval is explicitly enabled for this isolated local test."""
    from app.services import bridge_retrieval
    monkeypatch.setattr(bridge_retrieval, "lexical_prototype_enabled", lambda: True)
    monkeypatch.setattr(bridge_retrieval, "get_settings", lambda: SimpleNamespace(
        BRIDGE_EMBEDDINGS_URL="", BRIDGE_MIN_SIMILARITY=0.65))
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from app.core.database import Base
    from app.models.base import Course, User
    from app.models.bridge import BridgeChunk, BridgeMaterial, BridgeModulePack, BridgeRegressionPrompt
    from app.routers.bridge_staff import test_pack as run_pack

    async def scenario():
        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'bridge_runner.sqlite'}")
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as db:
            owner = User(student_id="runner-owner", phone="13000000005", password_hash="hash", role="teacher")
            db.add(owner)
            await db.flush()
            course = Course(name="Test", teacher_id=owner.id)
            db.add(course)
            await db.flush()
            # Regression must work before the teacher makes the pack public.
            pack = BridgeModulePack(course_id=course.id, title="Module", active=False)
            db.add(pack)
            await db.flush()
            material = BridgeMaterial(module_id=pack.id, filename="notes.txt", stored_path="/tmp/notes.txt",
                size_bytes=500, processing_status="ready")
            db.add(material)
            await db.flush()
            chunk = BridgeChunk(module_id=pack.id, material_id=material.id, chunk_index=0,
                text="# Topic nine label\nEvidence about topic nine label in this module.",
                chunk_type="DEFINITION", reviewed=True)
            db.add(chunk)
            await db.flush()
            db.add_all([
                BridgeRegressionPrompt(module_id=pack.id, question="What does the module say about topic nine label?",
                    language="en", expected_chunk_id=chunk.id, expected_status="GROUNDED", reviewed=True),
                BridgeRegressionPrompt(module_id=pack.id, question="What is the tennis league score?",
                    language="en", expected_chunk_id=None, expected_status="INSUFFICIENT EVIDENCE", reviewed=True),
            ])
            await db.flush()
            result = await run_pack(pack.id, owner, db)
            assert result["total"] == 2 and result["passed"] == 2, [item["reason"] for item in result["results"]]
            assert result["failed"] == 0
            assert all(item["passed"] is True for item in result["results"])
        await engine.dispose()

    asyncio.run(scenario())
