"""접속·접근 기록 조회 — 대표(OWNER) 전용 (plan/14-accounts-permissions.md §8.1)."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db, require_owner
from app.models import AccessLog, Client, User
from app.schemas.access_log import AccessLogOut

router = APIRouter()


@router.get("", response_model=list[AccessLogOut])
async def list_access_log(
    limit: int = Query(200, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
    owner: User = Depends(require_owner),
) -> list[AccessLogOut]:
    rows = (
        await db.execute(
            select(AccessLog)
            .where(AccessLog.tax_office_id == owner.tax_office_id)
            .order_by(AccessLog.created_at.desc())
            .limit(limit)
        )
    ).scalars().all()

    user_ids = {r.user_id for r in rows if r.user_id}
    client_ids = {r.client_id for r in rows if r.client_id}
    users = {
        u.id: u.name
        for u in (await db.execute(select(User).where(User.id.in_(user_ids)))).scalars().all()
    } if user_ids else {}
    clients = {
        c.id: c.business_name
        for c in (await db.execute(select(Client).where(Client.id.in_(client_ids)))).scalars().all()
    } if client_ids else {}

    return [
        AccessLogOut(
            id=r.id,
            created_at=r.created_at,
            user_id=r.user_id,
            user_name=users.get(r.user_id) if r.user_id else None,
            ip=r.ip,
            action=r.action,
            client_id=r.client_id,
            client_name=clients.get(r.client_id) if r.client_id else None,
            subject_employee_id=r.subject_employee_id,
            endpoint=r.endpoint,
        )
        for r in rows
    ]
