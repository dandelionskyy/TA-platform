"""Module-scoped bilingual source retrieval for BRIDGE.

Production uses a configured self-hosted multilingual embedding endpoint.
Lexical/glossary retrieval is an explicitly opted-in local prototype fallback;
it is not an acceptance substitute for the 80% bilingual Recall@5 target.
"""

import json
import math
import re
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.bridge import BridgeChunk, BridgeGlossaryTerm, BridgeMaterial
from app.services.bridge_ingest import EmbeddingUnavailableError, embed_texts, lexical_prototype_enabled

BRIDGE_SCAFFOLD_TYPES = ("DEFINITION", "EXAMPLE", "HINT")
BRIDGE_EXPLANATION_TYPES = BRIDGE_SCAFFOLD_TYPES + ("PARTIAL_SOLUTION", "WORKED_SOLUTION", "ANSWER")


class RetrievalUnavailableError(RuntimeError):
    """No trustworthy semantic retrieval is currently available."""


@dataclass(frozen=True)
class RetrievedChunk:
    chunk: BridgeChunk
    score: float
    source_label: str
    retrieval_mode: str = "multilingual_embedding"


def _cosine(left: list[float], right: list[float]) -> float:
    if not left or len(left) != len(right):
        return 0.0
    numerator = sum(a * b for a, b in zip(left, right, strict=True))
    denominator = math.sqrt(sum(a * a for a in left) * sum(b * b for b in right))
    return max(0.0, min(1.0, numerator / denominator)) if denominator else 0.0


_STOPWORDS = frozenset({
    "a", "an", "the", "is", "are", "of", "for", "to", "and", "or", "in", "on", "at",
    "this", "that", "what", "which", "how", "why", "can", "could", "please", "help",
    "you", "me", "my", "with", "from", "it", "i", "explain", "about", "does",
})


def _tokens(text: str) -> set[str]:
    text = text.casefold()
    english = set(re.findall(r"[a-z][a-z0-9]{1,}", text)) - _STOPWORDS
    han = re.findall(r"[\u3400-\u9fff]+", text)
    chinese = {sequence[i:i + 2] for sequence in han for i in range(len(sequence) - 1)}
    return english | chinese


async def _prototype_query_tokens(db: AsyncSession, module_id: str, question: str) -> set[str]:
    tokens = _tokens(question)
    terms = (await db.execute(select(BridgeGlossaryTerm).where(BridgeGlossaryTerm.module_id == module_id))).scalars().all()
    q = question.casefold()
    for term in terms:
        if term.english.casefold() in q or term.chinese in question:
            tokens |= _tokens(term.english) | _tokens(term.chinese)
    return tokens


async def retrieve_chunks(
    db: AsyncSession,
    module_id: str,
    question: str,
    language: str = "en",
    limit: int = 5,
    allowed_types: tuple[str, ...] = BRIDGE_SCAFFOLD_TYPES,
) -> list[RetrievedChunk]:
    """Return relevant *teaching* chunks within one module only.

    There is no dynamic table selection and no join to bridge_staff_solutions.
    Staff or session authorization of module_id must occur in the caller.
    Empty return means insufficient evidence; endpoint errors raise closed.
    """
    allowed_types = tuple(set(allowed_types) & set(BRIDGE_EXPLANATION_TYPES))
    if not module_id or not question.strip() or not allowed_types:
        return []
    limit = max(1, min(limit, 10))
    rows = (await db.execute(
        select(BridgeChunk, BridgeMaterial.filename)
        .join(BridgeMaterial, BridgeChunk.material_id == BridgeMaterial.id)
        .where(
            BridgeChunk.module_id == module_id,
            BridgeMaterial.module_id == module_id,
            BridgeMaterial.processing_status == "ready",
            BridgeChunk.reviewed.is_(True),
            BridgeChunk.chunk_type.in_(allowed_types),
        )
    )).all()
    if not rows:
        return []

    prototype = lexical_prototype_enabled()
    query_vector = None
    if get_settings().BRIDGE_EMBEDDINGS_URL.strip():
        try:
            query_vector = (await embed_texts([question]))[0]
        except (EmbeddingUnavailableError, IndexError) as exc:
            if not prototype:
                raise RetrievalUnavailableError("Local multilingual retrieval is unavailable") from exc
    elif not prototype:
        raise RetrievalUnavailableError("Local multilingual retrieval is not configured")

    use_prototype = query_vector is None
    query_tokens = await _prototype_query_tokens(db, module_id, question) if use_prototype else set()
    if use_prototype and not query_tokens:
        return []
    minimum_similarity = get_settings().BRIDGE_MIN_SIMILARITY
    minimum_similarity = min(1.0, max(0.0, minimum_similarity))

    candidates: list[RetrievedChunk] = []
    for chunk, filename in rows:
        if use_prototype:
            # This transparent mode is useful for local development only.
            overlap = query_tokens & _tokens(chunk.text)
            score = len(overlap) / len(query_tokens) if overlap else 0.0
            threshold = 0.20
        else:
            if not chunk.embedding_json:
                continue  # never mix unindexed/prototype chunks into semantic retrieval
            try:
                score = _cosine(query_vector, json.loads(chunk.embedding_json))
            except (TypeError, ValueError):
                continue
            threshold = minimum_similarity
        if score < threshold:
            continue
        display_name = Path(filename.replace("\\", "/")).name
        locator = f"p. {chunk.page_number}" if chunk.page_number is not None else f"section {chunk.chunk_index + 1}"
        candidates.append(RetrievedChunk(
            chunk=chunk, score=score, source_label=f"{display_name} · {locator}",
            retrieval_mode="lexical_prototype" if use_prototype else "multilingual_embedding",
        ))
    return sorted(candidates, key=lambda row: row.score, reverse=True)[:limit]
