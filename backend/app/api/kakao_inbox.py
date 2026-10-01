"""카카오 미분류함 — 거래처 매칭 실패분 (plan/14-accounts-permissions.md §5.3).

담당 STAFF가 없는 사무소 단위 데이터라 OWNER만 조회·정리할 수 있다.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db, require_owner
from app.models import KakaoPendingMessage, User

router = APIRouter()


class PendingMessageOut(BaseModel):
    id: str
    plusfriend_key: str
    utterance: str | None
    file_text: str | None
    attachments_meta: dict | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


@router.get("", response_model=list[PendingMessageOut])
async def list_pending(
    db: AsyncSession = Depends(get_db),
    owner: User = Depends(require_owner),
) -> list[KakaoPendingMessage]:
    return list(
        (
            await db.execute(
                select(KakaoPendingMessage)
                .where(KakaoPendingMessage.tax_office_id == owner.tax_office_id)
                .order_by(KakaoPendingMessage.created_at.desc())
            )
        )
        .scalars()
        .all()
    )


@router.delete("/{message_id}", status_code=status.HTTP_204_NO_CONTENT)
async def dismiss_pending(
    message_id: str,
    db: AsyncSession = Depends(get_db),
    owner: User = Depends(require_owner),
) -> None:
    """확인·처리 완료 후 미분류함에서 제거 (거래처 매칭을 다시 시도하지 않는다)."""
    msg = await db.get(KakaoPendingMessage, message_id)
    if msg is None or msg.tax_office_id != owner.tax_office_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "항목을 찾을 수 없습니다")
    await db.execute(delete(KakaoPendingMessage).where(KakaoPendingMessage.id == message_id))
    await db.commit()
