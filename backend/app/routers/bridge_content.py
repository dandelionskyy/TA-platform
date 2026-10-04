"""BRIDGE module packs and restricted staff content administration."""

import mimetypes
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile, Query
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.dependencies import RequireTeacher
from app.models.bridge import BridgeChunk, BridgeGlossaryTerm, BridgeMaterial, BridgeModulePack, BridgeStaffSolution
from app.models.course import Course
from app.models.user import User
from app.services.bridge_ingest import ALLOWED_EXTENSIONS, bridge_upload_limit, invalidate_chunk_reviews, process_material
from app.services.bridge_retrieval import BRIDGE_EXPLANATION_TYPES, BRIDGE_SCAFFOLD_TYPES

router = APIRouter(prefix="/api/bridge", tags=["bridge-content"])


class ModuleCreate(BaseModel):
    course_id: str = Field(min_length=1, max_length=36)
    title: str = Field(min_length=1, max_length=200)


class ModulePatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    active: bool | None = None
    assessment_locked: bool | None = None


class GlossaryEntry(BaseModel):
    english: str = Field(min_length=1, max_length=200)
    chinese: str = Field(min_length=1, max_length=200)
    notes: str = Field(default="", max_length=500)


class GlossaryReplacement(BaseModel):
    terms: list[GlossaryEntry] = Field(max_length=1000)


class ChunkPatch(BaseModel):
    chunk_type: str
    reviewed: bool


async def _owned_module(db: AsyncSession, teacher: User, module_id: str) -> BridgeModulePack:
    module = await db.scalar(
        select(BridgeModulePack).join(Course, BridgeModulePack.course_id == Course.id)
        .where(BridgeModulePack.id == module_id, Course.teacher_id == teacher.id)
    )
    if not module:
        raise HTTPException(404, "BRIDGE module not found")
    return module


def _module_dict(module: BridgeModulePack, *, materials: int = 0, ready: int = 0) -> dict:
    return {
        "id": module.id, "course_id": module.course_id, "title": module.title,
        "active": module.active, "assessment_locked": module.assessment_locked,
        "created_at": module.created_at.isoformat() if module.created_at else None,
        "updated_at": module.updated_at.isoformat() if module.updated_at else None,
        "material_count": materials, "ready_count": ready,
    }


def _material_dict(material: BridgeMaterial) -> dict:
    return {
        "id": material.id, "module_id": material.module_id, "filename": material.filename,
        "size_bytes": material.size_bytes, "processing_status": material.processing_status,
        "processing_error": material.processing_error, "page_count": material.page_count,
        "chunk_count": material.chunk_count,
        "processing_started_at": material.processing_started_at.isoformat() if material.processing_started_at else None,
        "created_at": material.created_at.isoformat() if material.created_at else None,
        "processed_at": material.processed_at.isoformat() if material.processed_at else None,
    }


def _chunk_dict(chunk: BridgeChunk, filename: str) -> dict:
    return {
        "id": chunk.id, "module_id": chunk.module_id, "material_id": chunk.material_id,
        "filename": filename, "page_number": chunk.page_number, "chunk_index": chunk.chunk_index,
        "text": chunk.text, "language": chunk.language,
        "chunk_type": chunk.chunk_type, "reviewed": chunk.reviewed,
    }


async def _save_upload(file: UploadFile, subdirectory: str) -> tuple[str, Path, int]:
    """Stream up to 50 MB to an unguessable path; never use a client path."""
    filename = Path((file.filename or "").replace("\\", "/")).name
    suffix = Path(filename).suffix.lower()
    if not filename or len(filename) > 255 or suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, "Upload a PDF, DOCX, TXT or MD file")
    root = (Path(get_settings().UPLOAD_DIR) / "bridge" / subdirectory).resolve()
    root.mkdir(parents=True, exist_ok=True)
    stored = root / f"{uuid.uuid4().hex}{suffix}"
    size = 0
    limit = bridge_upload_limit()
    try:
        with stored.open("xb") as output:
            while block := await file.read(1024 * 1024):
                size += len(block)
                if size > limit:
                    raise HTTPException(413, "BRIDGE uploads are limited to 50 MB")
                output.write(block)
        if size == 0:
            raise HTTPException(400, "The uploaded file is empty")
        # Parser validates the actual PDF/DOCX structure in the background.
        return filename, stored, size
    except Exception:
        stored.unlink(missing_ok=True)
        raise
    finally:
        await file.close()


@router.get("/modules/active")
async def public_active_modules(db: AsyncSession = Depends(get_db)):
    """Anonymous catalogue: identifiers and titles only, no sources or keys."""
    rows = await db.execute(
        select(BridgeModulePack.id, BridgeModulePack.title)
        .where(BridgeModulePack.active.is_(True)).order_by(BridgeModulePack.title)
    )
    return {"modules": [{"id": identifier, "title": title} for identifier, title in rows]}


@router.get("/modules")
async def list_modules(teacher: User = Depends(RequireTeacher), db: AsyncSession = Depends(get_db)):
    modules = (await db.execute(
        select(BridgeModulePack).join(Course, BridgeModulePack.course_id == Course.id)
        .where(Course.teacher_id == teacher.id).order_by(BridgeModulePack.created_at.desc())
    )).scalars().all()
    result = []
    for module in modules:
        status_rows = (await db.execute(
            select(BridgeMaterial.processing_status, func.count())
            .where(BridgeMaterial.module_id == module.id).group_by(BridgeMaterial.processing_status)
        )).all()
        counts = dict(status_rows)
        result.append(_module_dict(module, materials=sum(counts.values()), ready=counts.get("ready", 0)))
    return {"modules": result}


@router.post("/modules", status_code=201)
async def create_module(payload: ModuleCreate, teacher: User = Depends(RequireTeacher), db: AsyncSession = Depends(get_db)):
    owned = await db.scalar(select(Course.id).where(Course.id == payload.course_id, Course.teacher_id == teacher.id))
    if not owned:
        raise HTTPException(404, "Course not found")
    module = BridgeModulePack(course_id=payload.course_id, title=payload.title.strip(), active=False)
    db.add(module)
    await db.flush()
    return _module_dict(module)


@router.get("/modules/{module_id}")
async def get_module(module_id: str, teacher: User = Depends(RequireTeacher), db: AsyncSession = Depends(get_db)):
    module = await _owned_module(db, teacher, module_id)
    counts = (await db.execute(
        select(BridgeMaterial.processing_status, func.count()).where(BridgeMaterial.module_id == module_id)
        .group_by(BridgeMaterial.processing_status)
    )).all()
    totals = dict(counts)
    return _module_dict(module, materials=sum(totals.values()), ready=totals.get("ready", 0))


@router.patch("/modules/{module_id}")
async def update_module(module_id: str, payload: ModulePatch, teacher: User = Depends(RequireTeacher), db: AsyncSession = Depends(get_db)):
    module = await _owned_module(db, teacher, module_id)
    if payload.title is not None:
        module.title = payload.title.strip()
    if payload.active is True:
        safe = await db.scalar(select(func.count()).select_from(BridgeChunk).join(
            BridgeMaterial, BridgeChunk.material_id == BridgeMaterial.id
        ).where(
            BridgeChunk.module_id == module_id, BridgeMaterial.module_id == module_id,
            BridgeMaterial.processing_status == "ready", BridgeChunk.reviewed.is_(True),
            BridgeChunk.chunk_type.in_(BRIDGE_SCAFFOLD_TYPES),
        ))
        if not safe:
            raise HTTPException(409, "Review and tag a safe source chunk before activating")
    if payload.active is not None:
        module.active = payload.active
    if payload.assessment_locked is not None:
        module.assessment_locked = payload.assessment_locked
    await db.flush()
    return await get_module(module_id, teacher, db)


@router.get("/modules/{module_id}/materials")
async def list_materials(module_id: str, teacher: User = Depends(RequireTeacher), db: AsyncSession = Depends(get_db)):
    await _owned_module(db, teacher, module_id)
    rows = (await db.execute(select(BridgeMaterial).where(BridgeMaterial.module_id == module_id)
                             .order_by(BridgeMaterial.created_at.desc()))).scalars().all()
    return {"materials": [_material_dict(row) for row in rows]}


@router.post("/modules/{module_id}/materials", status_code=202)
async def upload_material(module_id: str, tasks: BackgroundTasks, file: UploadFile = File(...),
                          teacher: User = Depends(RequireTeacher), db: AsyncSession = Depends(get_db)):
    await _owned_module(db, teacher, module_id)
    filename, stored, size = await _save_upload(file, f"materials/{module_id}")
    material = BridgeMaterial(
        module_id=module_id, filename=filename, stored_path=str(stored),
        mime_type=mimetypes.guess_type(filename)[0], size_bytes=size,
        processing_status="queued",
    )
    db.add(material)
    try:
        await db.commit()  # queued row must exist before independent background task runs
    except Exception:
        stored.unlink(missing_ok=True)
        raise
    await db.refresh(material)
    tasks.add_task(process_material, material.id)
    return _material_dict(material)


@router.delete("/modules/{module_id}/materials/{material_id}")
async def delete_material(module_id: str, material_id: str, teacher: User = Depends(RequireTeacher),
                          db: AsyncSession = Depends(get_db)):
    module = await _owned_module(db, teacher, module_id)
    material = await db.scalar(select(BridgeMaterial).where(
        BridgeMaterial.id == material_id, BridgeMaterial.module_id == module_id
    ))
    if not material:
        raise HTTPException(404, "Material not found")
    # Explicit child removal also works when a local SQLite database has FKs off.
    chunk_ids = list((await db.scalars(select(BridgeChunk.id).where(
        BridgeChunk.material_id == material_id
    ))).all())
    await invalidate_chunk_reviews(db, chunk_ids, remove_source=True)
    await db.execute(delete(BridgeChunk).where(BridgeChunk.material_id == material_id))
    await db.delete(material)
    await db.flush()
    safe = await db.scalar(select(func.count()).select_from(BridgeChunk).join(
        BridgeMaterial, BridgeChunk.material_id == BridgeMaterial.id
    ).where(
        BridgeChunk.module_id == module_id, BridgeMaterial.module_id == module_id,
        BridgeMaterial.processing_status == "ready", BridgeChunk.reviewed.is_(True),
        BridgeChunk.chunk_type.in_(BRIDGE_SCAFFOLD_TYPES),
    ))
    if not safe:
        module.active = False
    await db.commit()
    Path(material.stored_path).unlink(missing_ok=True)
    return {"deleted": True}


@router.post("/modules/{module_id}/materials/{material_id}/reindex", status_code=202)
async def reindex_material(module_id: str, material_id: str, tasks: BackgroundTasks,
                           teacher: User = Depends(RequireTeacher), db: AsyncSession = Depends(get_db)):
    module = await _owned_module(db, teacher, module_id)
    material = await db.scalar(select(BridgeMaterial).where(
        BridgeMaterial.id == material_id, BridgeMaterial.module_id == module_id
    ))
    if not material:
        raise HTTPException(404, "Material not found")
    if material.processing_status not in {"failed", "ready"}:
        raise HTTPException(409, "Indexing is already queued or in progress")
    if not Path(material.stored_path).is_file():
        raise HTTPException(409, "Original file is missing; upload it again")
    module.active = False  # all source tags must be reviewed again after replacement
    chunk_ids = list((await db.scalars(select(BridgeChunk.id).where(
        BridgeChunk.material_id == material_id
    ))).all())
    await invalidate_chunk_reviews(db, chunk_ids, remove_source=False)
    material.processing_status = "queued"
    material.processing_started_at = None
    material.processing_error = None
    await db.commit()
    tasks.add_task(process_material, material.id)
    return _material_dict(material)


@router.get("/modules/{module_id}/chunks")
async def list_chunks(module_id: str, material_id: str | None = Query(default=None),
                      teacher: User = Depends(RequireTeacher), db: AsyncSession = Depends(get_db)):
    await _owned_module(db, teacher, module_id)
    query = (select(BridgeChunk, BridgeMaterial.filename)
             .join(BridgeMaterial, BridgeChunk.material_id == BridgeMaterial.id)
             .where(BridgeChunk.module_id == module_id, BridgeMaterial.module_id == module_id)
             .order_by(BridgeMaterial.created_at, BridgeChunk.chunk_index))
    if material_id is not None:
        query = query.where(BridgeChunk.material_id == material_id)
    rows = (await db.execute(query)).all()
    return {"chunks": [_chunk_dict(chunk, filename) for chunk, filename in rows]}


@router.patch("/modules/{module_id}/chunks/{chunk_id}")
async def review_chunk(module_id: str, chunk_id: str, payload: ChunkPatch,
                       teacher: User = Depends(RequireTeacher), db: AsyncSession = Depends(get_db)):
    module = await _owned_module(db, teacher, module_id)
    row = (await db.execute(select(BridgeChunk, BridgeMaterial.filename)
                            .join(BridgeMaterial, BridgeChunk.material_id == BridgeMaterial.id)
                            .where(BridgeChunk.id == chunk_id, BridgeChunk.module_id == module_id,
                                   BridgeMaterial.module_id == module_id, BridgeMaterial.processing_status == "ready"))).first()
    if not row:
        raise HTTPException(404, "Ready source chunk not found")
    chunk, filename = row
    category = payload.chunk_type.strip().upper()
    if category not in {*BRIDGE_EXPLANATION_TYPES, "UNREVIEWED"}:
        raise HTTPException(400, "Invalid source category")
    if payload.reviewed and category == "UNREVIEWED":
        raise HTTPException(400, "An unreviewed chunk cannot be approved")
    chunk.chunk_type = category
    chunk.reviewed = payload.reviewed if category != "UNREVIEWED" else False
    if category not in BRIDGE_SCAFFOLD_TYPES or not chunk.reviewed:
        await invalidate_chunk_reviews(db, [chunk.id])
    await db.flush()
    if module.active and (category not in BRIDGE_SCAFFOLD_TYPES or not chunk.reviewed):
        safe = await db.scalar(select(func.count()).select_from(BridgeChunk).join(
            BridgeMaterial, BridgeChunk.material_id == BridgeMaterial.id
        ).where(BridgeChunk.module_id == module_id, BridgeMaterial.module_id == module_id,
                BridgeMaterial.processing_status == "ready", BridgeChunk.reviewed.is_(True),
                BridgeChunk.chunk_type.in_(BRIDGE_SCAFFOLD_TYPES)))
        if not safe:
            module.active = False
    return _chunk_dict(chunk, filename)


@router.get("/modules/{module_id}/glossary")
async def get_glossary(module_id: str, teacher: User = Depends(RequireTeacher), db: AsyncSession = Depends(get_db)):
    await _owned_module(db, teacher, module_id)
    terms = (await db.execute(select(BridgeGlossaryTerm).where(BridgeGlossaryTerm.module_id == module_id)
                              .order_by(BridgeGlossaryTerm.english))).scalars().all()
    return {"terms": [{"id": t.id, "english": t.english, "chinese": t.chinese, "notes": t.notes} for t in terms]}


@router.put("/modules/{module_id}/glossary")
async def replace_glossary(module_id: str, payload: GlossaryReplacement, teacher: User = Depends(RequireTeacher),
                           db: AsyncSession = Depends(get_db)):
    await _owned_module(db, teacher, module_id)
    clean = [(term.english.strip(), term.chinese.strip(), term.notes.strip()) for term in payload.terms]
    if any(not english or not chinese for english, chinese, _ in clean):
        raise HTTPException(400, "Glossary entries cannot be blank")
    if len({english.casefold() for english, _, _ in clean}) != len(clean):
        raise HTTPException(400, "English glossary terms must be unique")
    await db.execute(delete(BridgeGlossaryTerm).where(BridgeGlossaryTerm.module_id == module_id))
    for english, chinese, notes in clean:
        db.add(BridgeGlossaryTerm(module_id=module_id, english=english, chinese=chinese, notes=notes))
    await db.flush()
    return await get_glossary(module_id, teacher, db)


@router.get("/modules/{module_id}/solutions")
async def list_solutions(module_id: str, teacher: User = Depends(RequireTeacher), db: AsyncSession = Depends(get_db)):
    await _owned_module(db, teacher, module_id)
    rows = (await db.execute(select(BridgeStaffSolution).where(BridgeStaffSolution.module_id == module_id)
                             .order_by(BridgeStaffSolution.created_at.desc()))).scalars().all()
    return {"solutions": [{"id": s.id, "filename": s.filename, "size_bytes": s.size_bytes} for s in rows]}


@router.post("/modules/{module_id}/solutions", status_code=201)
async def upload_solution(module_id: str, file: UploadFile = File(...), teacher: User = Depends(RequireTeacher),
                          db: AsyncSession = Depends(get_db)):
    await _owned_module(db, teacher, module_id)
    filename, stored, size = await _save_upload(file, f"restricted_solutions/{module_id}")
    solution = BridgeStaffSolution(module_id=module_id, filename=filename, stored_path=str(stored), size_bytes=size)
    db.add(solution)
    try:
        await db.flush()
    except Exception:
        stored.unlink(missing_ok=True)
        raise
    return {"id": solution.id, "filename": filename, "size_bytes": size}


@router.delete("/modules/{module_id}/solutions/{solution_id}")
async def delete_solution(module_id: str, solution_id: str, teacher: User = Depends(RequireTeacher),
                          db: AsyncSession = Depends(get_db)):
    await _owned_module(db, teacher, module_id)
    solution = await db.scalar(select(BridgeStaffSolution).where(
        BridgeStaffSolution.id == solution_id, BridgeStaffSolution.module_id == module_id
    ))
    if not solution:
        raise HTTPException(404, "Solution not found")
    await db.delete(solution)
    await db.commit()
    Path(solution.stored_path).unlink(missing_ok=True)
    return {"deleted": True}
