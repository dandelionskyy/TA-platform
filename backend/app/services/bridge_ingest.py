"""Background ingestion for BRIDGE teaching documents.

Uses only an institution-configured local embedding service. Documents from the
separate staff solutions table never enter this pipeline. A missing or failed
embedding service leaves the material marked failed unless the explicitly
opted-in lexical prototype mode is enabled.
"""

import asyncio
import io
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
from docx import Document
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import AsyncSessionFactory
from app.models.bridge import BridgeChunk, BridgeConcept, BridgeMaterial, BridgeRegressionPrompt, BridgeTemplate
from app.services.pdf_extraction import extract_pdf_pages

MAX_BRIDGE_BYTES = 50 * 1024 * 1024
ALLOWED_EXTENSIONS = frozenset({".pdf", ".docx", ".txt", ".md"})
MAX_TEXT_CHARS = 8_000_000  # explicit processing failure if a 50 MB file expands beyond this


class EmbeddingUnavailableError(RuntimeError):
    """Configured institution-hosted embedding service is unavailable."""


def lexical_prototype_enabled() -> bool:
    return get_settings().BRIDGE_ALLOW_LEXICAL_PROTOTYPE


def bridge_upload_limit() -> int:
    """Configuration can lower, but never raise, the contractual 50 MiB limit."""
    return min(MAX_BRIDGE_BYTES, max(1, get_settings().BRIDGE_UPLOAD_MAX_MB) * 1024 * 1024)


def _extract_pages(data: bytes, suffix: str) -> list[tuple[int | None, str]]:
    if suffix == ".pdf":
        return list(enumerate(extract_pdf_pages(data), 1))
    if suffix == ".docx":
        doc = Document(io.BytesIO(data))
        # DOCX does not contain authoritative rendered page numbers. Label as
        # sections/chunks in the UI rather than fabricating a PDF page number.
        blocks = [p.text for p in doc.paragraphs if p.text.strip()]
        for table in doc.tables:
            for row in table.rows:
                blocks.append(" | ".join(cell.text for cell in row.cells))
        return [(None, "\n".join(blocks))]
    if suffix in {".txt", ".md"}:
        return [(None, data.decode("utf-8-sig", errors="strict"))]
    raise ValueError("Unsupported file extension")


def _split_words(text: str, max_chars: int = 1100, overlap: int = 150) -> list[str]:
    """Keep PDF page boundaries, then split large text with a small overlap."""
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []
    out = []
    start = 0
    while start < len(text):
        end = min(len(text), start + max_chars)
        if end < len(text):
            break_at = text.rfind(" ", start + max_chars // 2, end)
            if break_at > start:
                end = break_at
        chunk = text[start:end].strip()
        if chunk:
            out.append(chunk)
        if end == len(text):
            break
        start = max(start + 1, end - overlap)
    return out


def _language(text: str) -> str:
    han = len(re.findall(r"[\u3400-\u9fff]", text))
    latin = len(re.findall(r"[A-Za-z]", text))
    if han > latin * 0.5:
        return "zh"
    if latin > han * 3:
        return "en"
    return "mixed"


async def embed_texts(texts: list[str]) -> list[list[float]]:
    """Ollama-compatible POST /api/embed, on a self-hosted endpoint.

    Set BRIDGE_EMBEDDINGS_URL to the *full* local endpoint, for example
    http://embedding-service:11434/api/embed. No text is sent if unset.
    """
    if not texts:
        return []
    url = get_settings().BRIDGE_EMBEDDINGS_URL.strip()
    if not url:
        raise EmbeddingUnavailableError("BRIDGE_EMBEDDINGS_URL is not configured")
    model = get_settings().BRIDGE_EMBEDDINGS_MODEL.strip() or "bge-m3"
    try:
        async with httpx.AsyncClient(timeout=120.0, trust_env=False) as client:
            result = await client.post(url, json={"model": model, "input": texts})
            result.raise_for_status()
            payload = result.json()
            if not isinstance(payload, dict):
                raise ValueError("Invalid embedding response")
            vectors = payload.get("embeddings")
    except (httpx.HTTPError, ValueError) as exc:
        raise EmbeddingUnavailableError("Local embedding service request failed") from exc
    if not isinstance(vectors, list) or len(vectors) != len(texts):
        raise EmbeddingUnavailableError("Local embedding service returned invalid vectors")
    dimension = len(vectors[0]) if vectors and isinstance(vectors[0], list) else 0
    if dimension < 8 or any(not isinstance(v, list) or len(v) != dimension or
                            any(not isinstance(n, (int, float)) or not -1e30 < n < 1e30 for n in v)
                            for v in vectors):
        raise EmbeddingUnavailableError("Local embedding service returned invalid vectors")
    return vectors


async def invalidate_chunk_reviews(db: AsyncSession, chunk_ids: list[str], *, remove_source: bool = False) -> None:
    """A changed/removed source cannot keep staff-approved derived artefacts."""
    if not chunk_ids:
        return
    await db.execute(update(BridgeConcept)
                     .where(BridgeConcept.source_chunk_id.in_(chunk_ids))
                     .values(reviewed=False, **({"source_chunk_id": None} if remove_source else {})))
    await db.execute(update(BridgeTemplate)
                     .where(BridgeTemplate.source_chunk_id.in_(chunk_ids))
                     .values(reviewed=False, **({"source_chunk_id": None} if remove_source else {})))
    await db.execute(update(BridgeRegressionPrompt)
                     .where(BridgeRegressionPrompt.expected_chunk_id.in_(chunk_ids))
                     .values(reviewed=False, **({"expected_chunk_id": None} if remove_source else {})))


async def process_material(material_id: str) -> None:
    """Run after the queued row has been committed. A durable worker is needed at scale."""
    async with AsyncSessionFactory() as db:
        # Claim atomically. Multiple web processes can discover the same queue.
        claim = await db.execute(update(BridgeMaterial)
                                 .where(BridgeMaterial.id == material_id, BridgeMaterial.processing_status == "queued")
                                 .values(processing_status="processing", processing_started_at=datetime.now(timezone.utc)))
        if claim.rowcount != 1:
            await db.rollback()
            return
        await db.commit()
        material = await db.get(BridgeMaterial, material_id)
        try:
            stored = Path(material.stored_path)
            data = await asyncio.to_thread(stored.read_bytes)
            if len(data) > bridge_upload_limit():
                raise ValueError("File exceeds 50 MB")
            pages = await asyncio.to_thread(_extract_pages, data, stored.suffix.lower())
            if sum(len(text) for _, text in pages) > MAX_TEXT_CHARS:
                raise ValueError("Extracted text is too large to index")
            if not any(text.strip() for _, text in pages):
                raise ValueError("No extractable text; provide a text PDF or OCR version")
            pieces = [(page_number, piece) for page_number, text in pages for piece in _split_words(text)]
            vectors: list[list[float] | None] = []
            if get_settings().BRIDGE_EMBEDDINGS_URL.strip():
                for offset in range(0, len(pieces), 16):
                    vectors.extend(await embed_texts([text for _, text in pieces[offset:offset + 16]]))
            elif lexical_prototype_enabled():
                vectors = [None] * len(pieces)
            else:
                raise EmbeddingUnavailableError("Local multilingual embedding service not configured")

            # Old chunks are replaced atomically only once the full new index is ready.
            old_ids = list((await db.scalars(select(BridgeChunk.id).where(
                BridgeChunk.material_id == material_id
            ))).all())
            await invalidate_chunk_reviews(db, old_ids, remove_source=True)
            await db.execute(delete(BridgeChunk).where(BridgeChunk.material_id == material_id))
            for index, ((page_number, text), vector) in enumerate(zip(pieces, vectors, strict=True)):
                db.add(BridgeChunk(
                    module_id=material.module_id, material_id=material.id,
                    page_number=page_number, chunk_index=index, text=text,
                    language=_language(text), chunk_type="UNREVIEWED", reviewed=False,
                    embedding_json=json.dumps(vector) if vector is not None else None,
                ))
            material.page_count = len(pages) if stored.suffix.lower() == ".pdf" else None
            material.chunk_count = len(pieces)
            material.processing_status = "ready"
            material.processing_error = None
            material.processed_at = datetime.now(timezone.utc)
            await db.commit()
        except Exception as exc:
            await db.rollback()
            material = await db.get(BridgeMaterial, material_id)
            if material:
                material.processing_status = "failed"
                # A short, generic message avoids exposing network details or file paths.
                if isinstance(exc, EmbeddingUnavailableError):
                    material.processing_error = "The local multilingual embedding service is unavailable"
                elif isinstance(exc, ValueError):
                    material.processing_error = str(exc)[:300]
                else:
                    material.processing_error = "Could not extract this document"
                material.processed_at = datetime.now(timezone.utc)
                await db.commit()


_ingestion_tasks: set[asyncio.Task] = set()
_recovery_task: asyncio.Task | None = None


def _schedule_ingest(material_id: str) -> None:
    task = asyncio.create_task(process_material(material_id))
    _ingestion_tasks.add(task)
    task.add_done_callback(_ingestion_tasks.discard)


async def resume_pending_materials() -> int:
    """Reclaim stale work and schedule persisted queued rows after a restart.

    A multi-worker deployment should use a dedicated durable queue. This
    recovery task repairs normal web-process restarts but cannot guarantee the
    five-minute SLA while a host or embedding service is unavailable.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=10)
    async with AsyncSessionFactory() as db:
        await db.execute(update(BridgeMaterial)
                         .where(BridgeMaterial.processing_status == "processing",
                                (BridgeMaterial.processing_started_at < cutoff) |
                                (BridgeMaterial.processing_started_at.is_(None)))
                         .values(processing_status="queued", processing_started_at=None))
        queued = (await db.execute(select(BridgeMaterial.id).where(
            BridgeMaterial.processing_status == "queued"
        ))).scalars().all()
        await db.commit()
    for material_id in queued:
        _schedule_ingest(material_id)
    return len(queued)


async def _reconcile_loop() -> None:
    while True:
        await asyncio.sleep(60)
        try:
            await resume_pending_materials()
        except Exception:
            # DB outages are retried at the next interval. Individual material
            # errors are persisted as failed by process_material.
            continue


async def start_ingestion_recovery() -> None:
    """Call during FastAPI lifespan startup, after database initialization."""
    global _recovery_task
    await resume_pending_materials()
    if _recovery_task is None or _recovery_task.done():
        _recovery_task = asyncio.create_task(_reconcile_loop())


async def stop_ingestion_recovery() -> None:
    """Call during FastAPI lifespan shutdown before closing the DB engine."""
    global _recovery_task
    if _recovery_task is not None:
        _recovery_task.cancel()
        try:
            await _recovery_task
        except asyncio.CancelledError:
            pass
        _recovery_task = None
    if _ingestion_tasks:
        for task in tuple(_ingestion_tasks):
            task.cancel()
        await asyncio.gather(*_ingestion_tasks, return_exceptions=True)
