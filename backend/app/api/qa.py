"""AI 도우미 팝업 — 사용법/법령/고객응대 자유 질의응답.

plan 문서 없이 프론트엔드에 먼저 UI 셸(stub)이 구현된 기능. 법령(law) 탭은 아직
법령 MCP 검색과 연결되지 않았다 — 후속 단계에서 붙인다.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.core.deps import get_current_user
from app.models import User
from app.services import qa_assistant

router = APIRouter()


class QaHistoryItem(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class QaRequest(BaseModel):
    intent: Literal["howto", "law", "customer"]
    question: str
    history: list[QaHistoryItem] = []


class QaResponse(BaseModel):
    answer: str


@router.post("", response_model=QaResponse)
async def ask_qa(
    body: QaRequest,
    _: User = Depends(get_current_user),
) -> QaResponse:
    question = body.question.strip()
    if not question:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "질문을 입력하세요")

    try:
        answer = await qa_assistant.answer_question(
            question,
            intent=body.intent,
            history=[h.model_dump() for h in body.history],
        )
    except RuntimeError as e:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(e)) from e

    return QaResponse(answer=answer)
