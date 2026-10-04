"""Deterministic, source-linked draft artefacts for BRIDGE module packs.

The compiler deliberately does not infer scientific misconceptions or translate
technical terms. Those require an authorised teacher's review and editing.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Iterable


_CHINESE = re.compile(r"[\u3400-\u9fff]")
_HEADING_PREFIX = re.compile(r"^(?:#{1,6}\s*|(?:unit|chapter|section|topic)\s*\d+[.:：\s-]*)", re.I)
_PAGE_MARKER = re.compile(r"^\[(?:Page|Slide|页|幻灯片)\s*\d+\]$", re.I)
_QUESTION_TEMPLATES = {
    "en": (
        "What does the module material say about {title}?",
        "Which key point does the source give for {title}?",
        "Help me understand {title} using the uploaded material.",
        "Where can I find {title} in the module material?",
        "Can you give me a source-based hint about {title}?",
    ),
    "zh": (
        "模块资料如何解释{title}？",
        "资料中关于{title}的关键点是什么？",
        "请根据已上传的资料帮我理解{title}。",
        "我能在模块资料的哪里找到{title}？",
        "请给我一个有资料依据的关于{title}的提示。",
    ),
}


@dataclass(frozen=True)
class Draft:
    """One proposed, unreviewed concept with its exact source chunk."""

    key: str
    title_en: str
    title_zh: str
    description: str
    source_chunk_id: str
    language: str


def _heading(text: str) -> str | None:
    for raw_line in text.splitlines()[:12]:
        line = raw_line.strip().strip("*_")
        if not line or _PAGE_MARKER.fullmatch(line):
            continue
        explicitly_heading = bool(_HEADING_PREFIX.match(line))
        heading = _HEADING_PREFIX.sub("", line).strip().strip("#:：")
        heading = re.sub(r"\s+", " ", heading)
        # A short first line is useful only if it is visibly a label, not a
        # clipped sentence, equation, instruction, or extracted paragraph.
        if not explicitly_heading and (len(heading) > 80 or heading.endswith((".", "。", "?", "？", ";"))):
            return None
        if 5 <= len(heading) <= 80 and sum(ch.isalpha() for ch in heading) >= 3:
            return heading
        return None
    return None


def draft_concepts(chunks: Iterable[object], *, limit: int = 10) -> list[Draft]:
    """Extract at most one clearly labelled topic per chunk, without translation."""
    proposed: list[Draft] = []
    seen: set[str] = set()
    for chunk in chunks:
        title = _heading(str(getattr(chunk, "text", "") or ""))
        if not title or title.casefold() in seen:
            continue
        seen.add(title.casefold())
        language = "zh" if _CHINESE.search(title) else "en"
        chunk_id = str(getattr(chunk, "id"))
        safe_key = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:36]
        key = (safe_key or "topic") + "-" + hashlib.sha256(title.encode("utf-8")).hexdigest()[:8]
        source_text = str(getattr(chunk, "text", "") or "")
        excerpt = re.sub(r"\s+", " ", source_text).strip()[:280]
        proposed.append(Draft(
            key=key,
            title_en=title if language == "en" else "",
            title_zh=title if language == "zh" else "",
            description=excerpt,
            source_chunk_id=chunk_id,
            language=language,
        ))
        if len(proposed) >= limit:
            break
    return proposed


def draft_templates(concepts: Iterable[Draft]) -> list[dict]:
    """Generate source-backed questions and explicit staff misconception slots."""
    templates: list[dict] = []
    for concept in concepts:
        title = concept.title_zh or concept.title_en
        if concept.language == "zh":
            micro = f"根据模块资料，{title}的一个关键点是什么？请指出来源。"
            misconception = f"教师待填写：请根据来源材料为“{title}”添加一个常见误解及纠正问题。"
        else:
            micro = f"According to the module material, what is one key point about {title}? Cite its source."
            misconception = f"TEACHER TO COMPLETE: Add one source-backed misconception and correction question about {title}."
        templates.extend((
            {"key": concept.key, "type": "micro_question", "language": concept.language,
             "text": micro, "source_chunk_id": concept.source_chunk_id, "reviewed": False},
            {"key": concept.key, "type": "misconception", "language": concept.language,
             "text": misconception, "source_chunk_id": concept.source_chunk_id, "reviewed": False},
        ))
    return templates


def draft_regression_prompts(concepts: Iterable[Draft], *, limit: int = 50) -> list[dict]:
    """Draft answerable retrieval questions; teachers must add negative tests."""
    prompts: list[dict] = []
    for concept in concepts:
        title = concept.title_zh or concept.title_en
        for template in _QUESTION_TEMPLATES[concept.language]:
            prompts.append({
                "key": concept.key,
                "question": template.format(title=title),
                "language": concept.language,
                "expected_chunk_id": concept.source_chunk_id,
                "expected_status": "GROUNDED",
                "reviewed": False,
            })
            if len(prompts) >= limit:
                return prompts
    return prompts


def compiler_gaps(chunks: Iterable[object], concepts: list[Draft], prompts: list[dict],
                  *, reviewed_prompt_count: int | None = None,
                  reviewed_misconception_count: int | None = None,
                  total_concept_count: int | None = None) -> list[str]:
    gaps: list[str] = []
    chunks = list(chunks)
    if not chunks:
        gaps.append("No processed teaching chunks are available. Upload and index teaching material first.")
    unreviewed = sum(not bool(getattr(chunk, "reviewed", False)) for chunk in chunks)
    if unreviewed:
        gaps.append(f"{unreviewed} source chunks need teacher-approved DEFINITION, EXAMPLE or HINT tags before student use.")
    if not concepts:
        gaps.append("No clear concept headings found. Staff must label concepts and link them to source chunks.")
    if reviewed_prompt_count is not None and reviewed_prompt_count < 20:
        gaps.append(f"Only {reviewed_prompt_count} regression prompts have been reviewed; staff must review at least 20.")
    elif reviewed_prompt_count is None and len(prompts) < 20:
        gaps.append(f"Only {len(prompts)} source-linked regression prompts could be drafted; staff must provide at least 20 reviewed prompts.")
    if reviewed_misconception_count is None:
        gaps.append("Misconceptions are placeholders. Staff must write and verify them against teaching sources.")
    elif reviewed_misconception_count < (total_concept_count if total_concept_count is not None else len(concepts)):
        gaps.append("Each concept needs a teacher-reviewed, source-backed misconception template.")
    gaps.append("Check reviewed prompts cover off-syllabus, module-isolation, solution-isolation and assessment-lock cases before acceptance.")
    return gaps
