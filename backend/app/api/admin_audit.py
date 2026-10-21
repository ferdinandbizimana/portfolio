"""Admin: read the audit log."""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlalchemy import func, select

from app.api.deps import CurrentUserDep, DbDep
from app.db.models import AuditEvent

router = APIRouter(prefix="/api/admin/audit", tags=["admin"])


class AuditEventOut(BaseModel):
    id: int
    occurred_at: datetime
    action: str
    ip_address: str | None
    detail: dict[str, Any]


class AuditPage(BaseModel):
    total: int
    items: list[AuditEventOut]


@router.get("", response_model=AuditPage)
def list_audit_events(
    _: CurrentUserDep,
    db: DbDep,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    action: str | None = Query(default=None, max_length=64),
) -> AuditPage:
    query = select(AuditEvent)
    count = select(func.count()).select_from(AuditEvent)
    if action:
        query = query.where(AuditEvent.action == action)
        count = count.where(AuditEvent.action == action)
    rows = db.scalars(
        query.order_by(AuditEvent.occurred_at.desc(), AuditEvent.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return AuditPage(
        total=db.scalar(count) or 0,
        items=[
            AuditEventOut(
                id=row.id,
                occurred_at=row.occurred_at,
                action=row.action,
                ip_address=row.ip_address,
                detail=row.detail or {},
            )
            for row in rows
        ],
    )
