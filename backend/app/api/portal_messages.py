"""세무사무소 직원 ↔ 사장님 메시지 (plan/12-owner-portal.md §3.8).

AI가 아닌 담당 직원이 직접 응대한다. 알림은 의도적으로 보내지 않는다 — 급한 건은
기존 카톡·전화로 별도 연락한다.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path as PurePath

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.deps import get_current_user, get_db, require_write
from app.models import Client, MessageSender, PortalMessage, User
from app.services.storage import get_storage

router = APIRouter()


class PortalMessageOut(BaseModel):
    id: str
    sender_type: str
    staff_name: str | None
    body: str | None
    attachment_url: str | None
    attachment_name: str | None
    created_at: datetime


def _out(msg: PortalMessage) -> PortalMessageOut:
    return PortalMessageOut(
        id=msg.id,
        sender_type=msg.sender_type.value,
        staff_name=msg.staff_user.name if msg.staff_user else None,
        body=msg.body,
        attachment_url=msg.attachment_url,
        attachment_name=msg.attachment_name,
        created_at=msg.created_at,
    )


async def _client_or_404(db: AsyncSession, client_id: str, user: User) -> Client:
    stmt = select(Client).where(
        Client.id == client_id, Client.tax_office_id == user.tax_office_id
    )
    if user.role == "STAFF":
        stmt = stmt.where(Client.assigned_user_id == user.id)
    client = (await db.execute(stmt)).scalar_one_or_none()
    if not client:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "거래처를 찾을 수 없습니다")
    return client


@router.get("/{client_id}/messages", response_model=list[PortalMessageOut])
async def list_messages(
    client_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[PortalMessageOut]:
    await _client_or_404(db, client_id, user)
    rows = (
        await db.execute(
            select(PortalMessage)
            .where(PortalMessage.client_id == client_id)
            .options(selectinload(PortalMessage.staff_user))
            .order_by(PortalMessage.created_at)
        )
    ).scalars().all()
    return [_out(m) for m in rows]


@router.post(
    "/{client_id}/messages",
    response_model=PortalMessageOut,
    status_code=status.HTTP_201_CREATED,
)
async def post_message(
    client_id: str,
    body: str | None = Form(default=None),
    file: UploadFile | None = File(default=None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    _writer: User = Depends(require_write),
) -> PortalMessageOut:
    """담당 직원이 직접 답한다 — AI가 생성하지 않는다(§3.8). 알림은 가지 않는다."""
    await _client_or_404(db, client_id, user)

    text = (body or "").strip()
    attachment_url = attachment_name = None
    if file is not None and file.filename:
        content = await file.read()
        if content:
            if len(content) > 25 * 1024 * 1024:
                raise HTTPException(
                    status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "25MB 초과 파일은 허용되지 않습니다"
                )
            storage = get_storage()
            key = storage.make_key("portal_message", PurePath(file.filename).suffix)
            attachment_url = storage.put_object(key, content, file.content_type)
            attachment_name = file.filename

    if not text and not attachment_url:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "내용을 입력하거나 파일을 첨부해 주세요")

    msg = PortalMessage(
        client_id=client_id,
        sender_type=MessageSender.STAFF,
        staff_user_id=user.id,
        body=text or None,
        attachment_url=attachment_url,
        attachment_name=attachment_name,
    )
    db.add(msg)
    await db.commit()
    await db.refresh(msg)
    msg.staff_user = user
    return _out(msg)
