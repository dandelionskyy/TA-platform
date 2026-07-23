from typing import Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.usage_log import AuditLog


async def write_audit(
    db: AsyncSession,
    action: str,
    actor_id: Optional[str] = None,
    target_type: Optional[str] = None,
    target_id: Optional[str] = None,
    ip_address: Optional[str] = None,
    metadata: Optional[dict[str, Any]] = None,
) -> None:
    db.add(AuditLog(
        action=action,
        actor_id=actor_id,
        target_type=target_type,
        target_id=target_id,
        ip_address=ip_address,
        metadata_=metadata or {},
    ))
    await db.flush()
