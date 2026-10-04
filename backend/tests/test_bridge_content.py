"""Contract tests for content isolation and public/staff visibility."""

import asyncio
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database import Base, get_db
from app.core.config import get_settings
from app.core.dependencies import get_current_user
from app.models.bridge import (
    BridgeChunk, BridgeConcept, BridgeGlossaryTerm, BridgeMaterial, BridgeModulePack,
    BridgeRegressionPrompt, BridgeStaffSolution, BridgeTemplate,
)
from app.models.course import Course
from app.models.user import User
from app.routers.bridge_content import router
from app.services.bridge_ingest import _extract_pages, _split_words, process_material, resume_pending_materials
from app.services.bridge_retrieval import RetrievalUnavailableError, retrieve_chunks
from app.services.pdf_extraction import extract_pdf_pages


def run(coroutine):
    return asyncio.run(coroutine)


async def setup_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        teacher = User(student_id="T100", phone="10000", password_hash="x", role="teacher")
        other = User(student_id="T200", phone="20000", password_hash="x", role="teacher")
        db.add_all([teacher, other])
        await db.flush()
        course = Course(name="Electronics", teacher_id=teacher.id)
        other_course = Course(name="Other", teacher_id=other.id)
        db.add_all([course, other_course])
        await db.flush()
        a = BridgeModulePack(course_id=course.id, title="Electronics pack", active=True)
        b = BridgeModulePack(course_id=other_course.id, title="Other pack", active=True)
        db.add_all([a, b])
        await db.commit()
    return engine, factory, teacher, other, a, b


def test_pdf_page_boundaries_and_docx_never_invents_page_numbers():
    from io import BytesIO
    from pypdf import PdfWriter
    from docx import Document

    output = BytesIO()
    pdf = PdfWriter()
    pdf.add_blank_page(width=100, height=100)
    pdf.add_blank_page(width=100, height=100)
    pdf.write(output)
    assert [page for page, _ in _extract_pages(output.getvalue(), ".pdf")] == [1, 2]
    doc = Document()
    doc.add_paragraph("Capacitance and charge")
    output = BytesIO()
    doc.save(output)
    assert _extract_pages(output.getvalue(), ".docx") == [(None, "Capacitance and charge")]
    assert all(len(part) <= 1100 for part in _split_words("capacitance " * 400))


def test_hung_pdf_worker_is_killed_on_wall_timeout(tmp_path, monkeypatch):
    # The timeout applies to a separate process, not to a Python thread that
    # would remain busy after the material is marked failed.
    worker = tmp_path / "hang.py"
    pid_file = tmp_path / "pid"
    worker.write_text(
        f"import os\nfrom pathlib import Path\nPath({str(pid_file)!r}).write_text(str(os.getpid()))\n"
        "while True:\n    pass\n"
    )
    monkeypatch.setattr("app.services.pdf_extraction._WORKER", worker)
    monkeypatch.setattr("app.services.pdf_extraction.PDF_TIMEOUT_SECONDS", 1)
    with pytest.raises(ValueError, match="timed out"):
        extract_pdf_pages(b"%PDF-1.7\n")
    assert pid_file.exists(), "The worker should reach the hanging parser"
    if os.name == "posix":
        with pytest.raises(ProcessLookupError):
            os.kill(int(pid_file.read_text()), 0)


def test_module_filter_solution_isolation_and_cross_language_glossary(monkeypatch):
    async def scenario():
        engine, factory, _, _, a, b = await setup_db()
        monkeypatch.setattr(get_settings(), "BRIDGE_ALLOW_LEXICAL_PROTOTYPE", True)
        monkeypatch.setattr(get_settings(), "BRIDGE_EMBEDDINGS_URL", "")
        async with factory() as db:
            material_a = BridgeMaterial(module_id=a.id, filename="lectures.pdf", stored_path="x.pdf", size_bytes=20, processing_status="ready")
            material_b = BridgeMaterial(module_id=b.id, filename="unrelated.pdf", stored_path="x.pdf", size_bytes=20, processing_status="ready")
            db.add_all([material_a, material_b])
            await db.flush()
            db.add_all([
                BridgeChunk(module_id=a.id, material_id=material_a.id, page_number=3, chunk_index=0, text="电容器储存电荷。", language="zh", chunk_type="DEFINITION", reviewed=True),
                BridgeChunk(module_id=b.id, material_id=material_b.id, page_number=1, chunk_index=0, text="Private answer: capacitance is secret", language="en", chunk_type="DEFINITION", reviewed=True),
                BridgeGlossaryTerm(module_id=a.id, english="capacitance", chinese="电容器", notes=""),
                BridgeStaffSolution(module_id=a.id, filename="solutions.pdf", stored_path="x.pdf", size_bytes=5),
            ])
            await db.commit()
            found = await retrieve_chunks(db, a.id, "What is capacitance?", language="en")
            assert found and found[0].chunk.module_id == a.id
            assert found[0].source_label == "lectures.pdf · p. 3"
            assert found[0].retrieval_mode == "lexical_prototype"
            assert "secret" not in " ".join(result.chunk.text for result in found)
            assert not await retrieve_chunks(db, a.id, "dragon fruit galaxy", language="en")
        await engine.dispose()
    run(scenario())


def test_retrieval_without_multilingual_backend_fails_closed(monkeypatch):
    async def scenario():
        engine, factory, _, _, a, _ = await setup_db()
        monkeypatch.setattr(get_settings(), "BRIDGE_ALLOW_LEXICAL_PROTOTYPE", False)
        monkeypatch.setattr(get_settings(), "BRIDGE_EMBEDDINGS_URL", "")
        async with factory() as db:
            material = BridgeMaterial(module_id=a.id, filename="notes.md", stored_path="x.md", size_bytes=20, processing_status="ready")
            db.add(material)
            await db.flush()
            db.add(BridgeChunk(module_id=a.id, material_id=material.id, chunk_index=0, text="Electronics", language="en", chunk_type="DEFINITION", reviewed=True))
            await db.commit()
            try:
                await retrieve_chunks(db, a.id, "Electronics")
            except RetrievalUnavailableError:
                pass
            else:
                assert False, "No generic answer is permitted when embeddings are unavailable"
        await engine.dispose()
    run(scenario())


def test_failed_ingest_is_visible_and_never_searchable(tmp_path, monkeypatch):
    async def scenario():
        engine, factory, _, _, a, _ = await setup_db()
        path = tmp_path / "lecture.md"
        path.write_text("Capacitance describes charge storage.")
        monkeypatch.setattr(get_settings(), "BRIDGE_ALLOW_LEXICAL_PROTOTYPE", False)
        monkeypatch.setattr(get_settings(), "BRIDGE_EMBEDDINGS_URL", "")
        monkeypatch.setattr("app.services.bridge_ingest.AsyncSessionFactory", factory)
        async with factory() as db:
            material = BridgeMaterial(module_id=a.id, filename="lecture.md", stored_path=str(path), size_bytes=path.stat().st_size, processing_status="queued")
            db.add(material)
            await db.commit()
        await process_material(material.id)
        async with factory() as db:
            row = await db.get(BridgeMaterial, material.id)
            assert row.processing_status == "failed"
            assert "embedding" in row.processing_error.lower()
            assert not (await db.execute(select(BridgeChunk).where(BridgeChunk.material_id == material.id))).scalars().all()
        await engine.dispose()
    run(scenario())


def test_malformed_pdf_marks_material_failed_without_chunks(tmp_path, monkeypatch):
    async def scenario():
        engine, factory, _, _, a, _ = await setup_db()
        stored = tmp_path / "malformed.pdf"
        stored.write_bytes(b"%PDF-1.7\nmalformed")
        monkeypatch.setattr("app.services.bridge_ingest.AsyncSessionFactory", factory)
        async with factory() as db:
            material = BridgeMaterial(
                module_id=a.id, filename="malformed.pdf", stored_path=str(stored),
                size_bytes=stored.stat().st_size, processing_status="queued",
            )
            db.add(material)
            await db.commit()
        await process_material(material.id)
        async with factory() as db:
            row = await db.get(BridgeMaterial, material.id)
            assert row.processing_status == "failed"
            assert "PDF" in row.processing_error
            assert not (await db.scalars(select(BridgeChunk).where(
                BridgeChunk.material_id == material.id
            ))).all()
        await engine.dispose()
    run(scenario())


def test_public_catalogue_and_owner_only_admin():
    async def scenario():
        engine, factory, teacher, other, a, b = await setup_db()
        app = FastAPI()
        app.include_router(router)
        active_user = teacher

        async def override_db():
            async with factory() as db:
                yield db
                await db.commit()

        async def override_user():
            return active_user

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[get_current_user] = override_user
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            public = (await client.get("/api/bridge/modules/active")).json()
            assert {"id": a.id, "title": a.title} in public["modules"]
            assert all(set(module) == {"id", "title"} for module in public["modules"])
            assert (await client.get(f"/api/bridge/modules/{b.id}/materials")).status_code == 404
            owned = (await client.get("/api/bridge/modules")).json()["modules"]
            assert len(owned) == 1 and owned[0]["id"] == a.id
            active_user = other
            assert (await client.patch(f"/api/bridge/modules/{a.id}", json={"assessment_locked": True})).status_code == 404
        await engine.dispose()
    run(scenario())


def test_reviewed_tags_gate_students_and_release():
    async def scenario():
        engine, factory, teacher, _, a, _ = await setup_db()
        # Start inactive so activation must inspect a reviewed safe chunk.
        async with factory() as db:
            module = await db.get(BridgeModulePack, a.id)
            module.active = False
            material = BridgeMaterial(module_id=a.id, filename="notes.md", stored_path="x.md", size_bytes=20, processing_status="ready")
            db.add(material)
            await db.flush()
            chunk = BridgeChunk(module_id=a.id, material_id=material.id, chunk_index=0,
                                text="The capacitance unit is farad", language="en")
            db.add(chunk)
            await db.commit()
        app = FastAPI()
        app.include_router(router)

        async def override_db():
            async with factory() as db:
                yield db
                await db.commit()

        async def override_user():
            return teacher

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[get_current_user] = override_user
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            url = f"/api/bridge/modules/{a.id}"
            assert (await client.patch(url, json={"active": True})).status_code == 409
            assert (await client.patch(f"{url}/chunks/{chunk.id}", json={"chunk_type": "UNREVIEWED", "reviewed": True})).status_code == 400
            response = await client.patch(f"{url}/chunks/{chunk.id}", json={"chunk_type": "ANSWER", "reviewed": True})
            assert response.status_code == 200 and response.json()["chunk_type"] == "ANSWER"
            assert (await client.patch(url, json={"active": True})).status_code == 409
            assert (await client.patch(f"{url}/chunks/{chunk.id}", json={"chunk_type": "DEFINITION", "reviewed": True})).status_code == 200
            assert (await client.patch(url, json={"active": True})).status_code == 200
            chunks = (await client.get(f"{url}/chunks")).json()["chunks"]
            assert chunks[0]["reviewed"] and chunks[0]["text"].startswith("The capacitance")
        await engine.dispose()
    run(scenario())


def test_recovery_reschedules_persisted_queue_and_stale_processing(monkeypatch):
    async def scenario():
        engine, factory, _, _, a, _ = await setup_db()
        async with factory() as db:
            queued = BridgeMaterial(module_id=a.id, filename="queued.md", stored_path="queued.md", size_bytes=1, processing_status="queued")
            stale = BridgeMaterial(
                module_id=a.id, filename="stale.md", stored_path="stale.md", size_bytes=1,
                processing_status="processing", processing_started_at=datetime.now(timezone.utc) - timedelta(minutes=11),
            )
            db.add_all([queued, stale])
            await db.commit()
        scheduled = []
        monkeypatch.setattr("app.services.bridge_ingest.AsyncSessionFactory", factory)
        monkeypatch.setattr("app.services.bridge_ingest._schedule_ingest", scheduled.append)
        assert await resume_pending_materials() == 2
        assert set(scheduled) == {queued.id, stale.id}
        async with factory() as db:
            assert (await db.get(BridgeMaterial, stale.id)).processing_status == "queued"
        await engine.dispose()
    run(scenario())


def test_self_hosted_embedding_adapter_and_cross_language_vector_query(monkeypatch):
    async def scenario():
        engine, factory, _, _, a, _ = await setup_db()
        monkeypatch.setattr(get_settings(), "BRIDGE_EMBEDDINGS_URL", "http://institution-model:11434/api/embed")
        monkeypatch.setattr(get_settings(), "BRIDGE_EMBEDDINGS_MODEL", "bge-m3")
        monkeypatch.setattr(get_settings(), "BRIDGE_ALLOW_LEXICAL_PROTOTYPE", False)
        calls = []

        def handler(request):
            payload = json.loads(request.content)
            assert request.url.path == "/api/embed"
            assert payload["model"] == "bge-m3"
            calls.extend(payload["input"])
            return httpx.Response(200, json={"embeddings": [[1.0] + [0.0] * 7 for _ in payload["input"]]})

        original_client = httpx.AsyncClient
        transport = httpx.MockTransport(handler)
        monkeypatch.setattr("app.services.bridge_ingest.httpx.AsyncClient",
                            lambda **options: original_client(transport=transport, **options))
        async with factory() as db:
            material = BridgeMaterial(module_id=a.id, filename="English notes.md", stored_path="x.md", size_bytes=50, processing_status="ready")
            db.add(material)
            await db.flush()
            db.add(BridgeChunk(module_id=a.id, material_id=material.id, chunk_index=0, text="A capacitor stores charge.",
                               language="en", chunk_type="DEFINITION", reviewed=True,
                               embedding_json=json.dumps([1.0] + [0.0] * 7)))
            await db.commit()
            found = await retrieve_chunks(db, a.id, "电容器如何储存电荷？", language="zh")
            assert found and found[0].retrieval_mode == "multilingual_embedding"
            assert found[0].source_label == "English notes.md · section 1"
            assert calls == ["电容器如何储存电荷？"]
        await engine.dispose()
    run(scenario())


def test_unsafe_retag_revokes_derived_staff_approvals_and_module_activation():
    async def scenario():
        engine, factory, teacher, _, a, _ = await setup_db()
        async with factory() as db:
            material = BridgeMaterial(module_id=a.id, filename="notes.md", stored_path="x.md", size_bytes=10, processing_status="ready")
            db.add(material)
            await db.flush()
            chunk = BridgeChunk(module_id=a.id, material_id=material.id, chunk_index=0,
                                text="Give the learner a hint without a result", chunk_type="HINT", reviewed=True)
            db.add(chunk)
            await db.flush()
            concept = BridgeConcept(module_id=a.id, key="circuit", title_en="Circuit",
                                    source_chunk_id=chunk.id, reviewed=True)
            template = BridgeTemplate(module_id=a.id, template_type="micro_question", language="en",
                                      text="What changes first?", source_chunk_id=chunk.id, reviewed=True)
            prompt = BridgeRegressionPrompt(module_id=a.id, question="What is current?", language="en",
                                            expected_chunk_id=chunk.id, reviewed=True)
            db.add_all([concept, template, prompt])
            await db.commit()
        app = FastAPI()
        app.include_router(router)

        async def override_db():
            async with factory() as db:
                yield db
                await db.commit()

        async def override_user():
            return teacher

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[get_current_user] = override_user
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            result = await client.patch(
                f"/api/bridge/modules/{a.id}/chunks/{chunk.id}",
                json={"chunk_type": "ANSWER", "reviewed": True},
            )
            assert result.status_code == 200
        async with factory() as db:
            assert not (await db.get(BridgeModulePack, a.id)).active
            assert not (await db.get(BridgeConcept, concept.id)).reviewed
            assert not (await db.get(BridgeTemplate, template.id)).reviewed
            assert not (await db.get(BridgeRegressionPrompt, prompt.id)).reviewed
        await engine.dispose()
    run(scenario())
