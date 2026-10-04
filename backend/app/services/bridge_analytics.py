"""Anonymous daily counts and small-cell-suppressed BRIDGE teaching summaries."""

from collections import defaultdict
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bridge import (
    BridgeDailyAggregate, BridgeLearningEvent, BridgeMaterial, BridgeTutorSession,
)


MIN_GROUP_SIZE = 10


def _band(count: int, threshold: int = MIN_GROUP_SIZE) -> str:
    if count < threshold:
        return "suppressed"
    floor = count // threshold * threshold
    return f"{floor}–{floor + threshold - 1}"


def summarise_counts(rows: list[tuple[str, str | None, int]], *, threshold: int = MIN_GROUP_SIZE) -> dict:
    """Return no IDs, raw events, tiny cells, or exact grand totals.

    The total is banded to prevent a client inferring a hidden cell by
    subtracting published concept counts from an exact overall count.
    """
    # `source_retrieved` is additionally emitted per cited material, so it
    # must not be included when counting tutor interactions.
    total = sum(count for kind, _, count in rows if kind != "source_retrieved")
    misconceptions: list[dict] = []
    stall_points: list[dict] = []
    materials: list[dict] = []
    stages: dict[str, int] = defaultdict(int)
    for kind, concept_key, count in rows:
        if kind == "misconception" and concept_key and count >= threshold:
            misconceptions.append({"concept_key": concept_key, "count": count})
        if kind == "struggled" and concept_key and count >= threshold:
            stall_points.append({"concept_key": concept_key, "count": count})
        if kind == "source_retrieved" and concept_key and concept_key.startswith("material:") and count >= threshold:
            material_id = concept_key.removeprefix("material:")
            try:
                UUID(material_id)
            except ValueError:
                continue
            materials.append({"material_id": material_id, "count": count})
        if kind in {"started", "scaffold", "struggled", "explain_back_requested", "mastered", "assessment_refusal"}:
            stages[kind] += count
    misconceptions.sort(key=lambda item: (-item["count"], item["concept_key"]))
    stall_points.sort(key=lambda item: (-item["count"], item["concept_key"]))
    materials.sort(key=lambda item: (-item["count"], item["material_id"]))
    interventions = [
        {"concept_key": item["concept_key"],
         "suggestion": "Revisit this concept using a reviewed source-linked micro-question and an explain-back check."}
        for item in misconceptions[:5]
    ]
    interventions += [
        {"concept_key": item["concept_key"],
         "suggestion": "Provide another scaffolded hint and revisit the source passage in the next tutorial."}
        for item in stall_points[:5] if item["concept_key"] not in {i["concept_key"] for i in interventions}
    ]
    return {
        "interaction_count_band": _band(total, threshold),
        "suppression_threshold": threshold,
        "misconceptions": misconceptions,
        "stall_points": stall_points,
        "most_retrieved_materials": materials,
        "suggested_interventions": interventions,
        "stages": [
            {"stage": stage, "count": count}
            for stage, count in sorted(stages.items()) if count >= threshold
        ],
        "window": "all_time",
    }


async def record_bridge_event(db: AsyncSession, session: BridgeTutorSession,
                              concept_key: str | None, event_type: str, stage: str) -> None:
    """Record a short-lived event and an indefinite anonymous daily count atomically.

    No student identifier, session token, prompt text, or answer is ever copied
    to the aggregate. The caller's transaction commits or rolls back both.
    """
    if not session.id:
        raise ValueError("A persisted BRIDGE session is required")
    if event_type not in {
        "started", "scaffold", "struggled", "explain_back_requested",
        "misconception", "mastered", "assessment_refusal", "source_retrieved",
    }:
        raise ValueError("Unsupported BRIDGE event")
    key = concept_key or ""
    if len(key) > 100 or len(stage) > 30:
        raise ValueError("BRIDGE event fields are too long")
    db.add(BridgeLearningEvent(
        module_id=session.module_id, session_id=session.id,
        concept_key=key or None, event_type=event_type, stage=stage,
    ))
    values = {
        "module_id": session.module_id,
        "day": datetime.now(timezone.utc).date(),
        "concept_key": key,
        "event_type": event_type,
        "count": 1,
    }
    dialect = db.get_bind().dialect.name
    if dialect == "postgresql":
        statement = pg_insert(BridgeDailyAggregate).values(**values)
    elif dialect == "sqlite":
        statement = sqlite_insert(BridgeDailyAggregate).values(**values)
    else:
        raise RuntimeError("BRIDGE daily aggregation requires PostgreSQL or SQLite")
    await db.execute(statement.on_conflict_do_update(
        index_elements=["module_id", "day", "concept_key", "event_type"],
        set_={"count": BridgeDailyAggregate.count + 1},
    ))


async def dashboard_for_module(db: AsyncSession, module_id: str) -> dict:
    result = await db.execute(
        select(
            BridgeDailyAggregate.event_type,
            BridgeDailyAggregate.concept_key,
            func.sum(BridgeDailyAggregate.count),
        ).where(
            BridgeDailyAggregate.module_id == module_id,
        ).group_by(BridgeDailyAggregate.event_type, BridgeDailyAggregate.concept_key)
    )
    report = summarise_counts([(kind, key, int(count)) for kind, key, count in result.all()])
    visible_ids = [item["material_id"] for item in report["most_retrieved_materials"]]
    if visible_ids:
        materials = (await db.scalars(select(BridgeMaterial).where(
            BridgeMaterial.module_id == module_id, BridgeMaterial.id.in_(visible_ids)))).all()
        names = {item.id: item.filename for item in materials}
        for item in report["most_retrieved_materials"]:
            item["filename"] = names.get(item["material_id"], "Removed material")
    return report
