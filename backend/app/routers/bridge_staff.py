"""Teacher-only BRIDGE pack drafting, review, regression and safe summaries."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import RequireTeacher
from app.models.bridge import (
    BridgeChunk, BridgeConcept, BridgeMaterial, BridgeModulePack,
    BridgeRegressionPrompt, BridgeTemplate, BridgeTutorSession,
)
from app.models.course import Course
from app.models.user import User
from app.services.bridge_analytics import dashboard_for_module
from app.services.bridge_compiler import (
    compiler_gaps, draft_concepts, draft_regression_prompts, draft_templates,
)
from app.services.bridge_retrieval import BRIDGE_SCAFFOLD_TYPES, retrieve_chunks


router = APIRouter(prefix="/api/bridge/staff/modules", tags=["bridge-staff"])


class ConceptEdit(BaseModel):
    key: str | None = Field(default=None, min_length=3, max_length=100, pattern=r"^[a-zA-Z0-9_-]+$")
    title_en: str | None = Field(default=None, max_length=200)
    title_zh: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    source_chunk_id: str | None = None
    reviewed: bool | None = None


class ConceptCreate(BaseModel):
    key: str = Field(min_length=3, max_length=100, pattern=r"^[a-zA-Z0-9_-]+$")
    title_en: str = Field(default="", max_length=200)
    title_zh: str = Field(default="", max_length=200)
    description: str = Field(default="", max_length=5000)
    source_chunk_id: str | None = None


class TemplateEdit(BaseModel):
    language: str | None = Field(default=None, pattern=r"^(en|zh)$")
    text: str | None = Field(default=None, min_length=1, max_length=4000)
    source_chunk_id: str | None = None
    reviewed: bool | None = None


class TemplateCreate(BaseModel):
    concept_id: str | None = None
    template_type: str = Field(pattern=r"^(misconception|micro_question)$")
    language: str = Field(pattern=r"^(en|zh)$")
    text: str = Field(min_length=1, max_length=4000)
    source_chunk_id: str | None = None


class PromptEdit(BaseModel):
    question: str | None = Field(default=None, min_length=1, max_length=2000)
    language: str | None = Field(default=None, pattern=r"^(en|zh)$")
    expected_chunk_id: str | None = None
    expected_status: str | None = Field(default=None, pattern=r"^(GROUNDED|INSUFFICIENT EVIDENCE)$")
    reviewed: bool | None = None


class PromptCreate(BaseModel):
    concept_id: str | None = None
    question: str = Field(min_length=1, max_length=2000)
    language: str = Field(pattern=r"^(en|zh)$")
    expected_chunk_id: str | None = None
    expected_status: str = Field(pattern=r"^(GROUNDED|INSUFFICIENT EVIDENCE)$")


async def _teacher_module(db: AsyncSession, user: User, module_id: str) -> BridgeModulePack:
    module = await db.scalar(select(BridgeModulePack).join(
        Course, BridgeModulePack.course_id == Course.id,
    ).where(BridgeModulePack.id == module_id, Course.teacher_id == user.id))
    if module is None:
        # Do not disclose module existence across teachers.
        raise HTTPException(status_code=404, detail="BRIDGE module not found")
    return module


async def _source(db: AsyncSession, module_id: str, chunk_id: str | None, *, require_reviewed: bool = False):
    if chunk_id is None:
        return None
    statement = select(BridgeChunk).join(
        BridgeMaterial, BridgeMaterial.id == BridgeChunk.material_id,
    ).where(BridgeChunk.id == chunk_id, BridgeChunk.module_id == module_id,
            BridgeMaterial.module_id == module_id, BridgeMaterial.processing_status == "ready")
    if require_reviewed:
        statement = statement.where(BridgeChunk.reviewed.is_(True),
                                    BridgeChunk.chunk_type.in_(BRIDGE_SCAFFOLD_TYPES))
    chunk = await db.scalar(statement)
    if chunk is None:
        raise HTTPException(status_code=422, detail=(
            "Source must be a teacher-reviewed DEFINITION, EXAMPLE or HINT chunk in this module"
            if require_reviewed else "Source must be a ready chunk in this module"))
    return chunk


def _concept_dict(item: BridgeConcept) -> dict:
    return {"id": item.id, "key": item.key, "title_en": item.title_en,
            "title_zh": item.title_zh, "description": item.description,
            "source_chunk_id": item.source_chunk_id, "reviewed": item.reviewed}


def _template_dict(item: BridgeTemplate) -> dict:
    return {"id": item.id, "concept_id": item.concept_id,
            "template_type": item.template_type, "language": item.language,
            "text": item.text, "source_chunk_id": item.source_chunk_id,
            "reviewed": item.reviewed}


def _prompt_dict(item: BridgeRegressionPrompt) -> dict:
    return {"id": item.id, "concept_id": item.concept_id, "question": item.question,
            "language": item.language, "expected_chunk_id": item.expected_chunk_id,
            "expected_status": item.expected_status, "reviewed": item.reviewed}


def _reject_nulls(changes: dict, *required: str) -> None:
    fields = [field for field in required if field in changes and changes[field] is None]
    if fields:
        raise HTTPException(status_code=422, detail=f"These fields cannot be null: {', '.join(fields)}")


async def _items(db: AsyncSession, module_id: str) -> dict:
    concepts = (await db.scalars(select(BridgeConcept).where(
        BridgeConcept.module_id == module_id).order_by(BridgeConcept.key))).all()
    templates = (await db.scalars(select(BridgeTemplate).where(
        BridgeTemplate.module_id == module_id).order_by(BridgeTemplate.template_type, BridgeTemplate.id))).all()
    prompts = (await db.scalars(select(BridgeRegressionPrompt).where(
        BridgeRegressionPrompt.module_id == module_id).order_by(BridgeRegressionPrompt.id))).all()
    return {"concepts": [_concept_dict(item) for item in concepts],
            "templates": [_template_dict(item) for item in templates],
            "regression_prompts": [_prompt_dict(item) for item in prompts]}


def _pack_gaps(chunks: list[BridgeChunk], drafts: list, prompts: list[dict], items: dict) -> list[str]:
    return compiler_gaps(
        chunks, drafts, prompts,
        reviewed_prompt_count=sum(item["reviewed"] for item in items["regression_prompts"]),
        reviewed_misconception_count=sum(
            item["reviewed"] and item["template_type"] == "misconception"
            for item in items["templates"]
        ),
        total_concept_count=len(items["concepts"]),
    )


async def _ready_chunks(db: AsyncSession, module_id: str) -> list[BridgeChunk]:
    return (await db.scalars(select(BridgeChunk).join(
        BridgeMaterial, BridgeMaterial.id == BridgeChunk.material_id,
    ).where(BridgeChunk.module_id == module_id, BridgeMaterial.module_id == module_id,
            BridgeMaterial.processing_status == "ready",
            BridgeChunk.chunk_type.in_((*BRIDGE_SCAFFOLD_TYPES, "UNREVIEWED")))
        .order_by(BridgeMaterial.created_at, BridgeChunk.chunk_index))).all()


@router.post("/{module_id}/compile")
async def compile_pack(module_id: str, user: User = Depends(RequireTeacher),
                       db: AsyncSession = Depends(get_db)):
    """Add unreviewed suggestions; never overwrite a teacher's edits."""
    await _teacher_module(db, user, module_id)
    chunks = await _ready_chunks(db, module_id)
    drafts = draft_concepts(chunks)
    suggested_templates = draft_templates(drafts)
    suggested_prompts = draft_regression_prompts(drafts)
    old_concepts = {item.key: item for item in (await db.scalars(select(BridgeConcept).where(
        BridgeConcept.module_id == module_id))).all()}
    old_templates = {(item.concept_id, item.template_type, item.language) for item in
                     (await db.scalars(select(BridgeTemplate).where(BridgeTemplate.module_id == module_id))).all()}
    old_prompts = {(item.question, item.language) for item in
                   (await db.scalars(select(BridgeRegressionPrompt).where(BridgeRegressionPrompt.module_id == module_id))).all()}
    created = {"concepts": 0, "templates": 0, "regression_prompts": 0}
    for draft in drafts:
        if draft.key not in old_concepts:
            item = BridgeConcept(module_id=module_id, key=draft.key,
                title_en=draft.title_en, title_zh=draft.title_zh,
                description=draft.description, source_chunk_id=draft.source_chunk_id,
                reviewed=False)
            db.add(item)
            await db.flush()
            old_concepts[item.key] = item
            created["concepts"] += 1
    for draft in suggested_templates:
        concept_id = old_concepts[draft["key"]].id
        identity = (concept_id, draft["type"], draft["language"])
        if identity not in old_templates:
            db.add(BridgeTemplate(module_id=module_id, concept_id=concept_id,
                template_type=draft["type"], language=draft["language"],
                text=draft["text"], source_chunk_id=draft["source_chunk_id"],
                reviewed=False))
            old_templates.add(identity)
            created["templates"] += 1
    for draft in suggested_prompts:
        identity = (draft["question"], draft["language"])
        if identity not in old_prompts:
            db.add(BridgeRegressionPrompt(module_id=module_id,
                concept_id=old_concepts[draft["key"]].id,
                question=draft["question"], language=draft["language"],
                expected_chunk_id=draft["expected_chunk_id"],
                expected_status=draft["expected_status"], reviewed=False))
            old_prompts.add(identity)
            created["regression_prompts"] += 1
    await db.flush()
    items = await _items(db, module_id)
    return {**items, "created_counts": created,
            "gaps": _pack_gaps(chunks, drafts, suggested_prompts, items)}


@router.get("/{module_id}/artefacts")
async def get_artefacts(module_id: str, user: User = Depends(RequireTeacher),
                        db: AsyncSession = Depends(get_db)):
    await _teacher_module(db, user, module_id)
    chunks = await _ready_chunks(db, module_id)
    drafts = draft_concepts(chunks)
    items = await _items(db, module_id)
    return {**items, "gaps": _pack_gaps(chunks, drafts, draft_regression_prompts(drafts), items)}


@router.post("/{module_id}/concepts")
async def add_concept(module_id: str, data: ConceptCreate,
                      user: User = Depends(RequireTeacher), db: AsyncSession = Depends(get_db)):
    await _teacher_module(db, user, module_id)
    if not data.title_en.strip() and not data.title_zh.strip():
        raise HTTPException(status_code=422, detail="Provide a concept title")
    if await db.scalar(select(BridgeConcept.id).where(
        BridgeConcept.module_id == module_id, BridgeConcept.key == data.key)):
        raise HTTPException(status_code=409, detail="Concept key already exists")
    await _source(db, module_id, data.source_chunk_id)
    item = BridgeConcept(module_id=module_id, **data.model_dump(), reviewed=False)
    db.add(item)
    await db.flush()
    return _concept_dict(item)


@router.patch("/{module_id}/concepts/{concept_id}")
async def edit_concept(module_id: str, concept_id: str, data: ConceptEdit,
                       user: User = Depends(RequireTeacher), db: AsyncSession = Depends(get_db)):
    await _teacher_module(db, user, module_id)
    item = await db.scalar(select(BridgeConcept).where(
        BridgeConcept.id == concept_id, BridgeConcept.module_id == module_id))
    if item is None:
        raise HTTPException(status_code=404, detail="Concept not found")
    changes = data.model_dump(exclude_unset=True)
    _reject_nulls(changes, "key", "title_en", "title_zh", "description", "reviewed")
    if "key" in changes and changes["key"] != item.key:
        if await db.scalar(select(BridgeConcept.id).where(
            BridgeConcept.module_id == module_id, BridgeConcept.key == changes["key"])):
            raise HTTPException(status_code=409, detail="Concept key already exists")
    if "source_chunk_id" in changes:
        await _source(db, module_id, changes["source_chunk_id"])
    if changes.get("reviewed", item.reviewed):
        if not ((changes.get("title_en", item.title_en) or "").strip() or
                (changes.get("title_zh", item.title_zh) or "").strip()):
            raise HTTPException(status_code=422, detail="Reviewed concepts need a title")
        await _source(db, module_id, changes.get("source_chunk_id", item.source_chunk_id), require_reviewed=True)
        if not changes.get("source_chunk_id", item.source_chunk_id):
            raise HTTPException(status_code=422, detail="Reviewed concepts need a valid source")
    for key, value in changes.items():
        setattr(item, key, value)
    await db.flush()
    return _concept_dict(item)


@router.post("/{module_id}/templates")
async def add_template(module_id: str, data: TemplateCreate,
                       user: User = Depends(RequireTeacher), db: AsyncSession = Depends(get_db)):
    await _teacher_module(db, user, module_id)
    if data.concept_id and not await db.scalar(select(BridgeConcept.id).where(
        BridgeConcept.id == data.concept_id, BridgeConcept.module_id == module_id)):
        raise HTTPException(status_code=422, detail="Concept must belong to module")
    await _source(db, module_id, data.source_chunk_id)
    item = BridgeTemplate(module_id=module_id, **data.model_dump(), reviewed=False)
    db.add(item)
    await db.flush()
    return _template_dict(item)


@router.patch("/{module_id}/templates/{template_id}")
async def edit_template(module_id: str, template_id: str, data: TemplateEdit,
                        user: User = Depends(RequireTeacher), db: AsyncSession = Depends(get_db)):
    await _teacher_module(db, user, module_id)
    item = await db.scalar(select(BridgeTemplate).where(
        BridgeTemplate.id == template_id, BridgeTemplate.module_id == module_id))
    if item is None:
        raise HTTPException(status_code=404, detail="Template not found")
    changes = data.model_dump(exclude_unset=True)
    _reject_nulls(changes, "language", "text", "reviewed")
    if "source_chunk_id" in changes:
        await _source(db, module_id, changes["source_chunk_id"])
    if changes.get("reviewed", item.reviewed):
        source_id = changes.get("source_chunk_id", item.source_chunk_id)
        if not source_id:
            raise HTTPException(status_code=422, detail="Reviewed templates need a valid source")
        await _source(db, module_id, source_id, require_reviewed=True)
        text = changes.get("text", item.text)
        if not text.strip() or "TEACHER TO COMPLETE" in text or "教师待填写" in text:
            raise HTTPException(status_code=422, detail="Replace placeholder before review")
    for key, value in changes.items():
        setattr(item, key, value)
    await db.flush()
    return _template_dict(item)


@router.post("/{module_id}/regression-prompts")
async def add_prompt(module_id: str, data: PromptCreate,
                     user: User = Depends(RequireTeacher), db: AsyncSession = Depends(get_db)):
    await _teacher_module(db, user, module_id)
    if data.concept_id and not await db.scalar(select(BridgeConcept.id).where(
        BridgeConcept.id == data.concept_id, BridgeConcept.module_id == module_id)):
        raise HTTPException(status_code=422, detail="Concept must belong to module")
    await _source(db, module_id, data.expected_chunk_id)
    item = BridgeRegressionPrompt(module_id=module_id, **data.model_dump(), reviewed=False)
    db.add(item)
    await db.flush()
    return _prompt_dict(item)


@router.patch("/{module_id}/regression-prompts/{prompt_id}")
async def edit_prompt(module_id: str, prompt_id: str, data: PromptEdit,
                      user: User = Depends(RequireTeacher), db: AsyncSession = Depends(get_db)):
    await _teacher_module(db, user, module_id)
    item = await db.scalar(select(BridgeRegressionPrompt).where(
        BridgeRegressionPrompt.id == prompt_id, BridgeRegressionPrompt.module_id == module_id))
    if item is None:
        raise HTTPException(status_code=404, detail="Regression prompt not found")
    changes = data.model_dump(exclude_unset=True)
    _reject_nulls(changes, "question", "language", "expected_status", "reviewed")
    if "expected_chunk_id" in changes:
        await _source(db, module_id, changes["expected_chunk_id"])
    if changes.get("reviewed", item.reviewed):
        expected_status = changes.get("expected_status", item.expected_status)
        source_id = changes.get("expected_chunk_id", item.expected_chunk_id)
        if expected_status == "GROUNDED" and not source_id:
            raise HTTPException(status_code=422, detail="Grounded regression prompts need a source")
        if expected_status == "INSUFFICIENT EVIDENCE" and source_id:
            raise HTTPException(status_code=422, detail="Insufficient evidence prompts cannot expect a source")
        await _source(db, module_id, source_id, require_reviewed=True)
    for key, value in changes.items():
        setattr(item, key, value)
    await db.flush()
    return _prompt_dict(item)


@router.get("/{module_id}/dashboard")
async def dashboard(module_id: str, user: User = Depends(RequireTeacher),
                    db: AsyncSession = Depends(get_db)):
    await _teacher_module(db, user, module_id)
    return await dashboard_for_module(db, module_id)


@router.post("/{module_id}/test")
async def test_pack(module_id: str, user: User = Depends(RequireTeacher),
                    db: AsyncSession = Depends(get_db)):
    """Run reviewed source tests through the actual guarded tutor, in dry-run mode."""
    module = await _teacher_module(db, user, module_id)
    prompts = (await db.scalars(select(BridgeRegressionPrompt).where(
        BridgeRegressionPrompt.module_id == module_id).order_by(BridgeRegressionPrompt.id))).all()
    from app.services.bridge_tutor import run_guarded_tutor

    results: list[dict] = []
    # Teacher-reviewed checks take priority if a draft pack contains over 50
    # prompts. The response explicitly counts those omitted from this run.
    selected = sorted(prompts, key=lambda item: (not item.reviewed, item.id))[:50]
    not_run = len(prompts) - len(selected)
    for prompt in selected:
        if not prompt.reviewed:
            results.append({"id": prompt.id, "question": prompt.question,
                            "passed": None, "reason": "Awaiting teacher review", "actual_sources": []})
            continue
        session = BridgeTutorSession(
            module_id=module.id, language=prompt.language,
            token_hash="0" * 64, pseudonym="ephemeral-regression",
            stage="greeting", scaffold_count=0, mastery=False,
            assessment_locked=module.assessment_locked,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        )
        try:
            retrieved = await retrieve_chunks(db, module.id, prompt.question, prompt.language, limit=5)
            outside = [chunk for chunk in retrieved if chunk.chunk.module_id != module.id]
            answer = await run_guarded_tutor(
                db, session, prompt.question, prompt.language,
                dry_run=True, allow_inactive=True,
            )
            source_ids = [source.source_id for source in answer.sources]
            if prompt.expected_status == "GROUNDED":
                passed = (answer.grounding_status == "GROUNDED"
                          and prompt.expected_chunk_id in [hit.chunk.id for hit in retrieved]
                          and prompt.expected_chunk_id in source_ids and not outside)
                reason = "Grounded status, expected source in top five and citation checked"
            else:
                passed = answer.grounding_status == "INSUFFICIENT EVIDENCE" and not source_ids and not outside
                reason = "No-evidence status, empty citations and module isolation checked"
            results.append({"id": prompt.id, "question": prompt.question,
                            "passed": passed, "reason": reason if passed else f"Failed: {reason}",
                            "actual_sources": source_ids})
        except Exception as exc:
            # Never return internal exception details or student/session data.
            results.append({"id": prompt.id, "question": prompt.question,
                            "passed": False, "reason": f"Test execution failed ({type(exc).__name__})",
                            "actual_sources": []})
    passed = sum(result["passed"] is True for result in results)
    failed = sum(result["passed"] is False for result in results)
    skipped = sum(result["passed"] is None for result in results) + not_run
    return {"total": len(prompts), "executed": passed + failed,
            "passed": passed, "failed": failed, "skipped": skipped,
            "not_run": not_run, "scope": "reviewed prompts: guarded response and Recall@5",
            "results": results}
