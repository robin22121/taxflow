"""Inbound webhook endpoints for automated data collection.

- ``POST /webhooks/kakao`` — 카카오 i 오픈빌더 폴백 스킬 웹훅
- ``POST /webhooks/email`` — SendGrid Inbound Parse 웹훅

Both resolve the sender to a Client + CollectionSession, then feed the text
into the shared ``_ingest_message()`` pipeline.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import re
import secrets

import asyncio

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.core.deps import get_db
from app.models import (
    Client,
    CollectionSession,
    KakaoUserBinding,
    KakaoPendingMessage,
    MonthlyFiling,
    MonthlyFilingStatus,
    PayrollEntry,
    TaxOffice,
)
from app.api.collect import _ingest_message

logger = logging.getLogger(__name__)
router = APIRouter()

# asyncio.create_task의 약한 참조 문제 방지 — 태스크 참조를 보관
_running_tasks: set[asyncio.Task] = set()  # type: ignore[type-arg]


# ---------------------------------------------------------------------------
# Webhook authentication helpers
# ---------------------------------------------------------------------------

def _verify_kakao_signature(secret: str, body: bytes, signature: str) -> bool:
    """카카오 오픈빌더 스킬 서버 요청 검증 (HMAC-SHA256)."""
    if not secret:
        return False
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def _verify_sendgrid_basic_auth(request: Request, expected_password: str) -> bool:
    """SendGrid Inbound Parse Basic Auth 검증."""
    if not expected_password:
        return False
    import base64
    auth = request.headers.get("authorization", "")
    if not auth.startswith("Basic "):
        return False
    try:
        decoded = base64.b64decode(auth[6:]).decode("utf-8")
        _, password = decoded.split(":", 1)
        return secrets.compare_digest(password, expected_password)
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Helper: find latest active collection session for a client
# ---------------------------------------------------------------------------

async def _find_active_session(
    db: AsyncSession, client: Client
) -> CollectionSession | None:
    """Find the most recent SENT/NEEDS_REVIEW session for a client."""
    filing = (
        await db.execute(
            select(MonthlyFiling)
            .where(
                MonthlyFiling.tax_office_id == client.tax_office_id,
                MonthlyFiling.status.in_([
                    MonthlyFilingStatus.COLLECTING,
                    MonthlyFilingStatus.REVIEWING,
                ]),
            )
            .order_by(MonthlyFiling.period.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if not filing:
        return None

    session = (
        await db.execute(
            select(CollectionSession)
            .where(
                CollectionSession.monthly_filing_id == filing.id,
                CollectionSession.client_id == client.id,
            )
            .options(
                selectinload(CollectionSession.client),
                selectinload(CollectionSession.monthly_filing),
            )
        )
    ).scalar_one_or_none()
    return session


# ---------------------------------------------------------------------------
# 카카오 i 오픈빌더 웹훅
# ---------------------------------------------------------------------------

@router.post("/kakao/welcome")
async def kakao_welcome(request: Request) -> dict:
    """카카오 웰컴 블록 스킬 — 현재 월 기반 동적 인사 메시지."""
    from datetime import datetime, timezone, timedelta
    kst = timezone(timedelta(hours=9))
    now = datetime.now(kst)
    filing_month = now.month - 1 if now.month > 1 else 12
    return _kakao_response(
        f"안녕하세요, 이지원천입니다.\n\n"
        f"{filing_month}월분 원천세 신고 자료를 보내주세요.\n\n"
        f"[전송방법]\n"
        f"거래처명 + 직원명 + 금액(만원)\n"
        f"예) 하늘식품 김영수 500 박미영 300\n\n"
        f"엑셀·사진·PDF 파일도 전송 가능\n"
        f"※ 파일 전송 시 거래처명 함께 입력\n\n"
        f"[주의]\n"
        f"• 거래처명 필수 (사업자등록증 상호명)\n"
        f"• 한 거래처씩 따로 전송\n"
        f"• 잘못 보낸 경우 다시 보내면 덮어씌움\n"
        f"• 반드시 이 채팅방에서 직접 입력해야 자료가 전송됩니다"
    )


@router.post("/kakao")
async def kakao_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """카카오 i 오픈빌더 폴백 스킬 웹훅.

    세무사 직원이 거래처로부터 받은 급여자료를 이지원천 비즈채널로 전달하면,
    사무소 바인딩 확인 → 거래처명 추출 → AI 파싱 → 서버 저장 → 상세 결과 응답.

    플로우:
    0. plusfriendUserKey로 사무소 바인딩 확인 (미등록 시 사무소 코드 입력 요청)
    1. 직원이 거래처명을 명기하여 전송 (예: "하늘식품 김영수 500 박미영 300")
    2. AI가 본문에서 거래처명 추출 → 해당 사무소의 Client DB에서만 매칭
    3. 매칭 실패 시 → "거래처명을 입력해주세요" 되물음
    4. 매칭 성공 → AI 파싱 → 상세 결과(이름+금액) 봇 응답
    """
    settings = get_settings()
    raw_body = await request.body()

    if settings.kakao_webhook_secret:
        signature = request.headers.get("x-kakao-signature", "")
        if not _verify_kakao_signature(settings.kakao_webhook_secret, raw_body, signature):
            logger.warning("카카오 웹훅: 서명 검증 실패")
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid signature")

    try:
        body = json.loads(raw_body)
    except Exception:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid JSON")

    logger.info("카카오 웹훅 수신 body keys=%s, body=%s", list(body.keys()), json.dumps(body, ensure_ascii=False)[:2000])

    user_request = body.get("userRequest", {})
    utterance = user_request.get("utterance", "").strip()
    user_props = user_request.get("user", {}).get("properties", {})
    plusfriend_key = user_props.get("plusfriendUserKey", "")

    # ── 사무소 바인딩 확인 ──
    binding = await _get_kakao_binding(db, plusfriend_key)

    if not binding:
        # 바인딩 안 됨 → 사무소 코드 입력인지 확인
        result = await _try_bind_office(db, plusfriend_key, utterance)
        if result:
            return result  # 바인딩 성공/실패 응답
        # 사무소 코드도 아닌 일반 메시지 → 등록 안내
        return _kakao_response(
            "사무소 등록이 필요합니다.\n"
            "소속 세무사사무소의 사무소 코드를 입력해주세요.\n\n"
            "예) 등록 JMS001\n\n"
            "※ 사무소 코드는 담당 세무사에게 문의하세요."
        )

    tax_office_id = binding.tax_office_id

    # 파일 첨부 처리 (이미지, 문서 등)
    params = body.get("action", {}).get("params", {})
    media = params.get("media", {})
    # 카카오는 media를 JSON 문자열로 보내는 경우도 있음
    if isinstance(media, str):
        try:
            media = json.loads(media)
        except Exception:
            media = {}

    file_text = ""
    file_images: list[tuple[bytes, str]] = []
    attachments_meta: list[dict] = []

    media_url = media.get("url", "")
    media_type = media.get("type", "")

    if media_url:
        file_text, file_images, attachments_meta = await _download_and_process_kakao_media(
            media_url, media_type
        )

    if not utterance and not file_text and not file_images:
        return _kakao_response("메시지 내용이 비어 있습니다.")

    # 거래처 매칭: 해당 사무소의 거래처에서만 매칭
    full_utterance = utterance
    if file_text:
        full_utterance = (utterance + "\n\n" + file_text).strip() if utterance else file_text
    client = await _match_client_from_text(db, full_utterance, tax_office_id=tax_office_id)

    if not client:
        # ── 거래처 매칭 실패 ──
        pending = await _get_pending(db, plusfriend_key)

        if pending and pending.client_id:
            # 역방향: 이전에 거래처명을 먼저 보내고, 지금 자료를 보낸 경우
            client = await db.get(Client, pending.client_id)
            if client:
                if file_text:
                    full_utterance = (utterance + "\n\n" + file_text).strip() if utterance else file_text
                await _delete_pending(db, plusfriend_key)
                logger.info("카카오 웹훅: 펜딩 거래처와 합침 (client=%s)", client.business_name)
                return await _process_and_respond(
                    db, client, full_utterance, file_images, attachments_meta,
                )

        # 미등록 거래처 — 자료 저장 보류, 세무사에게 알림
        data_preview = (utterance or "")[:200]
        if file_text:
            data_preview = ((utterance or "") + "\n" + file_text)[:200]

        if data_preview.strip():
            await _notify_office_unregistered_client(db, tax_office_id, data_preview)

        await _delete_pending(db, plusfriend_key)
        return _kakao_response(
            "등록되지 않은 거래처입니다.\n\n"
            "수신된 자료를 세무사사무소에 전달했습니다.\n"
            "사무소에서 거래처를 등록한 후 다시 보내주세요.\n\n"
            "거래처 등록: 이지원천 웹사이트 → 거래처 관리 → 거래처 추가"
        )

    # ── 거래처 매칭 성공 ──
    pending = await _get_pending(db, plusfriend_key)
    if pending:
        # 정방향: 이전에 자료를 먼저 보내고, 지금 거래처명을 보낸 경우
        if pending.file_text:
            full_utterance = (full_utterance + "\n\n" + pending.file_text).strip()
        if pending.utterance:
            full_utterance = (pending.utterance + "\n\n" + full_utterance).strip()
        if pending.attachments_meta:
            attachments_meta = (pending.attachments_meta or []) + attachments_meta
        await _delete_pending(db, plusfriend_key)
        logger.info("카카오 웹훅: 펜딩 자료와 합침 (client=%s)", client.business_name)

    # 거래처명만 있고 급여 데이터가 없는지 판별
    has_payroll_data = file_text or file_images or _has_payroll_content(utterance, client.business_name)

    if not has_payroll_data:
        # 역방향: 거래처명만 먼저 보낸 경우 → client_id를 펜딩에 저장
        await _save_pending(db, plusfriend_key, tax_office_id, client_id=client.id)
        logger.info("카카오 웹훅: 거래처명만 수신, 자료 대기 (client=%s)", client.business_name)
        return _kakao_response(
            f"{client.business_name} 확인되었습니다.\n"
            f"급여자료를 보내주세요.\n\n"
            f"예) 김영수 500 박미영 300\n"
            f"또는 엑셀·사진·PDF 파일 전송"
        )

    return await _process_and_respond(
        db, client, full_utterance, file_images, attachments_meta,
    )


def _kakao_response(text: str) -> dict:
    """카카오 i 오픈빌더 스킬 응답 포맷."""
    return {
        "version": "2.0",
        "template": {
            "outputs": [
                {
                    "simpleText": {
                        "text": text
                    }
                }
            ]
        }
    }


async def _process_and_respond(
    db: AsyncSession,
    client: Client,
    full_utterance: str,
    file_images: list[tuple[bytes, str]],
    attachments_meta: list[dict],
) -> dict:
    """거래처 매칭 완료 후 즉시 접수 응답 → 백그라운드에서 AI 파싱."""
    session = await _find_active_session(db, client)
    if not session:
        return _kakao_response(
            f"{client.business_name} — 현재 진행 중인 자료 수집 건이 없습니다."
        )

    # 백그라운드 처리에 필요한 ID를 미리 저장
    session_id = session.id
    filing_id = session.monthly_filing_id
    client_id = client.id
    client_name = client.business_name
    filing_period = session.monthly_filing.period

    task = asyncio.create_task(
        _background_ingest_kakao(
            session_id=session_id,
            filing_id=filing_id,
            client_id=client_id,
            client_name=client_name,
            filing_period=filing_period,
            tax_office_id=client.tax_office_id,
            full_utterance=full_utterance,
            file_images=file_images,
            attachments_meta=attachments_meta,
        )
    )
    _running_tasks.add(task)
    task.add_done_callback(_running_tasks.discard)

    return _kakao_response(
        f"✅ {client_name} 자료 접수 완료\n\n"
        f"AI가 분석 중입니다. 완료되면 결과를 보내드릴게요.\n"
        f"(보통 10~30초 소요)\n\n"
        f"※ 반드시 이 채팅방에서 직접 입력해야 자료가 전송됩니다"
    )


async def _background_ingest_kakao(
    *,
    session_id: str,
    filing_id: str,
    client_id: str,
    client_name: str,
    filing_period: str,
    tax_office_id: str,
    full_utterance: str,
    file_images: list[tuple[bytes, str]],
    attachments_meta: list[dict],
) -> None:
    """백그라운드에서 AI 파싱 후 세무사사무소에 SMS로 결과 전송."""
    from app.db import SessionLocal

    try:
        async with SessionLocal() as db:
            session = (
                await db.execute(
                    select(CollectionSession)
                    .where(CollectionSession.id == session_id)
                    .options(
                        selectinload(CollectionSession.client),
                        selectinload(CollectionSession.monthly_filing),
                    )
                )
            ).scalar_one_or_none()
            if not session:
                logger.error("백그라운드 파싱: 세션 없음 (id=%s)", session_id)
                return

            await _ingest_message(
                db=db,
                session=session,
                client=session.client,
                filing=session.monthly_filing,
                text=full_utterance,
                channel="kakao",
                images=file_images or None,
                attachments=attachments_meta or None,
            )

            entries = (
                await db.execute(
                    select(PayrollEntry)
                    .where(
                        PayrollEntry.monthly_filing_id == filing_id,
                        PayrollEntry.client_id == client_id,
                    )
                    .order_by(PayrollEntry.total_amount.desc())
                )
            ).scalars().all()

            response_text = _build_detailed_response(
                client_name=client_name,
                filing_period=filing_period,
                entries=list(entries),
            )
            logger.info("백그라운드 파싱 완료: client=%s, entries=%d", client_name, len(entries))

            # TODO: 카카오 알림톡 템플릿 등록 후 결과 전송 구현 (plan.md 백로그 참조)
            logger.info("파싱 결과 (알림톡 미구현, 대시보드에서 확인):\n%s", response_text)

    except Exception:
        logger.exception("백그라운드 카카오 파싱 실패: client=%s", client_name)


def _has_payroll_content(utterance: str, client_name: str) -> bool:
    """utterance에 거래처명 외에 급여 데이터(이름+금액)가 포함되어 있는지 판별."""
    remaining = utterance
    # 거래처명 제거
    for prefix in [client_name, client_name.replace("(주)", "").replace("주식회사", "").strip()]:
        remaining = remaining.replace(prefix, "").strip()
    if not remaining:
        return False
    # 숫자가 포함되어 있으면 급여 데이터로 간주
    return bool(re.search(r"\d", remaining))


async def _download_and_process_kakao_media(
    url: str, media_type: str
) -> tuple[str, list[tuple[bytes, str]], list[dict]]:
    """카카오톡에서 전송된 파일(이미지/문서)을 다운로드하고 처리."""
    import httpx
    from app.services.file_intake import intake_file
    from app.services.storage import get_storage
    from app.services.stt import get_stt_provider

    file_text = ""
    images: list[tuple[bytes, str]] = []
    attachments_meta: list[dict] = []

    try:
        async with httpx.AsyncClient(timeout=15.0) as cli:
            resp = await cli.get(url)
        if resp.status_code != 200:
            logger.warning("카카오 파일 다운로드 실패: url=%s, status=%s", url, resp.status_code)
            return file_text, images, attachments_meta

        content = resp.content
        content_type = resp.headers.get("content-type", "")

        # 파일명 추출: Content-Disposition 또는 URL에서
        filename = ""
        cd = resp.headers.get("content-disposition", "")
        if "filename=" in cd:
            filename = cd.split("filename=")[-1].strip('"').strip("'")
        if not filename:
            # URL 경로에서 파일명 추출
            from urllib.parse import urlparse, unquote
            path = urlparse(url).path
            filename = unquote(path.split("/")[-1]) if "/" in path else ""
        if not filename:
            # content-type으로 확장자 추정
            ext_map = {
                "image/jpeg": "photo.jpg", "image/png": "photo.png",
                "image/webp": "photo.webp",
                "text/plain": "file.txt",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "file.xlsx",
                "application/vnd.ms-excel": "file.xls",
                "text/csv": "file.csv",
                "application/pdf": "file.pdf",
            }
            filename = ext_map.get(content_type.split(";")[0].strip(), "file.bin")

        intake = await intake_file(
            filename=filename,
            content=content,
            storage=get_storage(),
            stt=get_stt_provider(),
        )
        if intake.text.strip():
            file_text = f"[첨부: {filename}]\n{intake.text}"
        images.extend(intake.images)
        if intake.storage_key:
            attachments_meta.append({
                "filename": filename,
                "storage_key": intake.storage_key,
                "kind": intake.kind,
            })
    except Exception:
        logger.exception("카카오 파일 처리 실패: url=%s", url)

    return file_text, images, attachments_meta


async def _notify_office_unregistered_client(
    db: AsyncSession, tax_office_id: str, data_preview: str
) -> None:
    """미등록 거래처 자료 수신 시 세무사사무소에 알림 (SMS + 이메일)."""
    office = await db.get(TaxOffice, tax_office_id)
    if not office:
        return

    msg = (
        f"[이지원천] 미등록 거래처 자료 수신\n\n"
        f"아래 자료가 수신되었으나, 등록되지 않은 거래처입니다.\n"
        f"거래처를 확인 후 웹사이트에서 등록해주세요.\n\n"
        f"--- 수신 내용 ---\n"
        f"{data_preview}\n"
        f"----------------"
    )

    # SMS 알림
    if office.phone:
        try:
            from app.channels.sms import get_sms_channel
            from app.channels.base import MessageRecipient
            sms = get_sms_channel()
            await sms.send(
                MessageRecipient(name=office.representative or office.name, phone=office.phone),
                body=msg,
            )
        except Exception:
            logger.exception("미등록 거래처 SMS 알림 실패 (office=%s)", office.name)

    # 이메일 알림
    if office.email:
        try:
            from app.channels.email import get_email_channel
            from app.channels.base import MessageRecipient
            email_ch = get_email_channel()
            result = await email_ch.send(
                MessageRecipient(name=office.representative or office.name, email=str(office.email)),
                body=msg,
                template_code="[이지원천] 미등록 거래처 자료 수신",
            )
            logger.info("미등록 거래처 이메일 알림: office=%s, email=%s, channel=%s, accepted=%s, error=%s",
                         office.name, office.email, result.channel, result.accepted, result.error)
        except Exception:
            logger.exception("미등록 거래처 이메일 알림 실패 (office=%s)", office.name)
    else:
        logger.warning("미등록 거래처 이메일 알림 스킵: office=%s — email 미등록", office.name)

    logger.info("미등록 거래처 알림 전송: office=%s, preview=%s", office.name, data_preview[:50])


async def _get_kakao_binding(
    db: AsyncSession, plusfriend_key: str
) -> KakaoUserBinding | None:
    """plusfriendUserKey로 사무소 바인딩 조회 (tax_office eager load)."""
    if not plusfriend_key:
        return None
    return (
        await db.execute(
            select(KakaoUserBinding)
            .where(KakaoUserBinding.plusfriend_key == plusfriend_key)
            .options(selectinload(KakaoUserBinding.tax_office))
        )
    ).scalar_one_or_none()


async def _try_bind_office(
    db: AsyncSession, plusfriend_key: str, utterance: str
) -> dict | None:
    """'등록 {코드}' 형식의 메시지면 사무소 바인딩 시도. 성공/실패 시 응답 반환, 해당 안 되면 None."""
    match = re.match(r"^등록\s+(\S+)$", utterance.strip())
    if not match:
        return None

    code = match.group(1).upper()
    office = (
        await db.execute(
            select(TaxOffice).where(TaxOffice.short_code == code)
        )
    ).scalar_one_or_none()

    if not office:
        return _kakao_response(
            f"사무소 코드 '{code}'을(를) 찾을 수 없습니다.\n"
            "코드를 다시 확인해주세요.\n\n"
            "예) 등록 JMS001"
        )

    binding = KakaoUserBinding(
        plusfriend_key=plusfriend_key,
        tax_office_id=office.id,
    )
    db.add(binding)
    await db.commit()

    logger.info("카카오 사무소 바인딩 완료: key=%s → %s (%s)", plusfriend_key[:8], office.name, code)
    return _kakao_response(
        f"'{office.name}' 사무소로 등록되었습니다.\n\n"
        f"이제 거래처명과 급여자료를 보내주세요.\n"
        f"예) 하늘식품 김영수 500 박미영 300"
    )


async def _match_client_from_text(
    db: AsyncSession, utterance: str, *, tax_office_id: str
) -> Client | None:
    """본문에서 거래처명을 추출하여 해당 사무소의 Client DB와 매칭.

    1. 해당 사무소 거래처명과 본문을 대조하여 가장 먼저 일치하는 거래처 반환
    2. 매칭 실패 시 None 반환 → 봇이 거래처명 재요청
    """
    clients = (
        await db.execute(
            select(Client)
            .where(Client.tax_office_id == tax_office_id)
            .order_by(Client.business_name)
        )
    ).scalars().all()

    if not clients:
        return None

    # 거래처명이 본문에 포함되어 있는지 확인 (긴 이름 우선 매칭)
    sorted_clients = sorted(clients, key=lambda c: len(c.business_name or ""), reverse=True)
    for client in sorted_clients:
        if client.business_name and client.business_name in utterance:
            return client

    # 부분 매칭: 거래처명에서 (주), 주식회사, 법인 등을 제거하고 재시도
    for client in sorted_clients:
        if not client.business_name:
            continue
        clean_name = (
            client.business_name
            .replace("(주)", "").replace("주식회사", "")
            .replace("(유)", "").replace("유한회사", "")
            .strip()
        )
        if clean_name and len(clean_name) >= 2 and clean_name in utterance:
            return client

    return None


# ---------------------------------------------------------------------------
# Pending message helpers (2단계 플로우: 파일 먼저 → 거래처명 나중)
# ---------------------------------------------------------------------------

async def _get_pending(db: AsyncSession, plusfriend_key: str) -> KakaoPendingMessage | None:
    """해당 유저의 대기 중인 임시 자료 조회."""
    return (
        await db.execute(
            select(KakaoPendingMessage)
            .where(KakaoPendingMessage.plusfriend_key == plusfriend_key)
            .order_by(KakaoPendingMessage.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def _save_pending(
    db: AsyncSession,
    plusfriend_key: str,
    tax_office_id: str,
    *,
    client_id: str | None = None,
    utterance: str | None = None,
    file_text: str | None = None,
    attachments_meta: list[dict] | None = None,
) -> None:
    """임시 자료 저장 (기존 펜딩은 삭제 후 새로 생성)."""
    await _delete_pending(db, plusfriend_key)
    db.add(KakaoPendingMessage(
        plusfriend_key=plusfriend_key,
        tax_office_id=tax_office_id,
        client_id=client_id,
        utterance=utterance or None,
        file_text=file_text or None,
        attachments_meta=attachments_meta or None,
    ))
    await db.commit()


async def _delete_pending(db: AsyncSession, plusfriend_key: str) -> None:
    """해당 유저의 대기 중인 임시 자료 모두 삭제."""
    from sqlalchemy import delete
    await db.execute(
        delete(KakaoPendingMessage)
        .where(KakaoPendingMessage.plusfriend_key == plusfriend_key)
    )


def _build_detailed_response(
    client_name: str,
    filing_period: str,
    entries: list,
) -> str:
    """카카오 봇 응답: 파싱된 직원별 이름+금액 상세 결과."""
    month = int(filing_period.split("-")[1]) if "-" in filing_period else ""
    lines = [f"✅ {client_name} {month}월 급여자료 접수 완료"]

    # 기존직원
    matched = [e for e in entries if e.match_status == "MATCHED"]
    if matched:
        lines.append(f"\n[기존직원 {len(matched)}명]")
        for e in matched:
            lines.append(f"· {e.raw_name} {_fmt_amount(e.total_amount)}")

    # 신규
    new_hires = [e for e in entries if e.match_status == "NEW_HIRE_SUSPECTED"]
    if new_hires:
        lines.append(f"\n[신규 {len(new_hires)}명]")
        for e in new_hires:
            lines.append(f"· {e.raw_name} {_fmt_amount(e.total_amount)}")

    # 퇴사
    resigned = [e for e in entries if e.match_status == "RESIGNATION_SUSPECTED"]
    if resigned:
        lines.append(f"\n[퇴사 {len(resigned)}명]")
        for e in resigned:
            lines.append(f"· {e.raw_name} (퇴사)")

    # 확인필요 (이상치)
    flagged = [
        e for e in entries
        if e.anomaly_notes and len(e.anomaly_notes) > 0 and not e.approved
    ]
    if flagged:
        lines.append(f"\n⚠️ 확인필요 {len(flagged)}건")
        for e in flagged:
            notes = e.anomaly_notes or {}
            reason = next(iter(notes.values()), "") if notes else ""
            prev = e.prev_amount
            if prev:
                lines.append(f"· {e.raw_name} {_fmt_amount(e.total_amount)} (전월 {_fmt_amount(prev)})")
            else:
                lines.append(f"· {e.raw_name} — {reason}")

    if not entries:
        lines.append("\n파싱된 데이터가 없습니다. 자료를 다시 확인해주세요.")

    return "\n".join(lines)


def _fmt_amount(amount: int | None) -> str:
    """금액을 한국어 형식으로 포맷."""
    if not amount:
        return "0원"
    return f"{amount:,}원"


# ---------------------------------------------------------------------------
# SendGrid Inbound Parse 웹훅
# ---------------------------------------------------------------------------

@router.post("/email")
async def email_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """SendGrid Inbound Parse 웹훅.

    매칭 우선순위:
    1. to 주소에서 collect+{client_id_8자리} 추출 → Client.id 매칭
    2. to 주소에서 collect+{session_token} 추출 → CollectionSession 매칭
    3. from 주소로 Client.contact_email 매칭

    첨부파일이 있으면 본문과 함께 처리 (엑셀/CSV → 텍스트 변환).
    """
    settings = get_settings()

    # SendGrid Inbound Parse Basic Auth 검증
    if settings.sendgrid_webhook_secret:
        if not _verify_sendgrid_basic_auth(request, settings.sendgrid_webhook_secret):
            logger.warning("이메일 웹훅: Basic Auth 검증 실패")
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")

    form = await request.form()

    to_addr = str(form.get("to", ""))
    from_addr = str(form.get("from", ""))
    subject = str(form.get("subject", ""))
    text_body = str(form.get("text", ""))
    html_body = str(form.get("html", ""))
    attachment_count = int(form.get("attachments", 0) or 0)

    # 본문 텍스트 추출
    body = text_body.strip()
    if not body and html_body:
        body = re.sub(r"<[^>]+>", "", html_body).strip()

    # 첨부파일 처리 — 텍스트 추출 + 이미지는 Vision 모델로 전달할 bytes 수집
    # 원본은 storage에 보존, 메타를 attachments_meta로 모아 세무사 대시보드에 노출
    attachment_texts: list[str] = []
    images: list[tuple[bytes, str]] = []
    attachments_meta: list[dict] = []
    for i in range(1, attachment_count + 1):
        att = form.get(f"attachment{i}")
        if att and hasattr(att, "read"):
            content = await att.read()
            filename = getattr(att, "filename", f"attachment{i}")
            if filename and content:
                from app.services.file_intake import intake_file
                from app.services.storage import get_storage
                from app.services.stt import get_stt_provider
                intake = await intake_file(
                    filename=filename,
                    content=content,
                    storage=get_storage(),
                    stt=get_stt_provider(),
                )
                if intake.text.strip():
                    attachment_texts.append(f"[첨부: {filename}]\n{intake.text}")
                images.extend(intake.images)
                if intake.storage_key:
                    attachments_meta.append({
                        "filename": filename,
                        "storage_key": intake.storage_key,
                        "kind": intake.kind,
                    })

    # 본문 + 첨부파일 텍스트 합산
    full_text = body
    if attachment_texts:
        full_text = (body + "\n\n" + "\n\n".join(attachment_texts)).strip()

    if not full_text and not images:
        logger.warning("이메일 웹훅: 본문+첨부 모두 비어있음 (from=%s, subject=%s)", from_addr, subject)
        return {"status": "ignored", "reason": "empty body and no parseable attachments"}

    # ── 세션 매칭 ──
    session = None

    # 1순위: collect+{client_id}@taxflow.ai → Client.id 매칭
    client_id = _extract_client_id(to_addr)
    if client_id:
        client = await db.get(Client, client_id)
        if client:
            session = await _find_active_session(db, client)

    # 2순위: collect+{session_token} → CollectionSession.request_token 매칭
    if not session:
        token = _extract_token_from_address(to_addr)
        if token:
            session = (
                await db.execute(
                    select(CollectionSession)
                    .where(CollectionSession.request_token == token)
                    .options(
                        selectinload(CollectionSession.client),
                        selectinload(CollectionSession.monthly_filing),
                    )
                )
            ).scalar_one_or_none()

    # 3순위: from 주소로 Client 매칭
    if not session:
        # 이메일 주소에서 <> 제거 (SendGrid가 "Name <email>" 형식으로 보낼 수 있음)
        clean_from = re.search(r"[\w.-]+@[\w.-]+", from_addr)
        sender_email = clean_from.group(0) if clean_from else from_addr
        client = (
            await db.execute(
                select(Client).where(Client.contact_email == sender_email)
            )
        ).scalar_one_or_none()
        if client:
            session = await _find_active_session(db, client)

    if not session:
        logger.warning(
            "이메일 웹훅: 세션 매칭 실패 (to=%s, from=%s, subject=%s)",
            to_addr, from_addr, subject,
        )
        # TODO: 매칭 실패 알림을 세무사 대시보드에 표시 (NotificationEvent 등)
        return {
            "status": "unmatched",
            "reason": "no matching session",
            "from": from_addr,
            "subject": subject,
        }

    try:
        result = await _ingest_message(
            db=db,
            session=session,
            client=session.client,
            filing=session.monthly_filing,
            text=full_text,
            channel="email",
            images=images or None,
            attachments=attachments_meta or None,
        )
    except Exception:
        logger.exception("이메일 웹훅 처리 실패 (from=%s, subject=%s)", from_addr, subject)
        # Return 200 to prevent SendGrid retry storms; log for investigation.
        return {"status": "error", "reason": "processing failed"}

    logger.info(
        "이메일 웹훅 처리 완료: from=%s, matched=%d, new_hire=%d, attachments=%d, images=%d",
        from_addr, result.matched, result.new_hire_suspected, len(attachment_texts), len(images),
    )
    return {
        "status": "processed",
        "session_id": result.session_id,
        "matched": result.matched,
        "new_hire_suspected": result.new_hire_suspected,
        "attachments_parsed": len(attachment_texts),
    }


# ---------------------------------------------------------------------------
# Resend Inbound 웹훅
# ---------------------------------------------------------------------------

@router.post("/resend")
async def resend_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Resend 인바운드 이메일 웹훅.

    Resend은 email.received 이벤트를 JSON으로 보내지만 본문은 포함하지 않음.
    → API로 본문+첨부를 별도 조회 후 파이프라인에 투입.
    """
    settings = get_settings()

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid JSON")

    # 전체를 try/except로 감싸서 500 방지 (Resend이 재시도 폭풍을 일으키지 않도록)
    try:
        return await _handle_resend_event(db, body, settings)
    except Exception:
        logger.exception("Resend 웹훅 처리 중 예상치 못한 오류")
        return {"status": "error", "reason": "unexpected error"}


async def _handle_resend_event(
    db: AsyncSession,
    body: dict,
    settings,
) -> dict:
    """Resend email.received 이벤트 실제 처리."""
    import httpx

    event_type = body.get("type", "")
    if event_type != "email.received":
        # 다른 이벤트(delivery, bounce 등)는 무시
        return {"status": "ignored", "type": event_type}

    data = body.get("data", {})
    email_id = data.get("email_id", "")
    to_list = data.get("to", [])
    from_addr = data.get("from", "")
    subject = data.get("subject", "")

    if not email_id:
        return {"status": "ignored", "reason": "no email_id"}

    logger.info(
        "Resend 웹훅: email_id=%s, from=%s, to=%s, subject=%s",
        email_id, from_addr, to_list, subject,
    )

    # Resend API로 이메일 본문 조회
    if not settings.resend_api_key:
        logger.error("Resend 웹훅: RESEND_API_KEY 미설정")
        return {"status": "error", "reason": "RESEND_API_KEY not configured"}

    async with httpx.AsyncClient(timeout=15.0) as cli:
        resp = await cli.get(
            f"https://api.resend.com/emails/receiving/{email_id}",
            headers={"Authorization": f"Bearer {settings.resend_api_key}"},
        )

    if resp.status_code != 200:
        logger.error("Resend API 조회 실패: status=%s body=%s", resp.status_code, resp.text[:200])
        return {"status": "error", "reason": f"API fetch failed: {resp.status_code}"}

    email_data = resp.json()
    logger.info(
        "Resend 이메일 조회 성공: keys=%s, attachments=%s",
        list(email_data.keys()),
        email_data.get("attachments"),
    )
    text_body = (email_data.get("text") or "").strip()
    html_body = (email_data.get("html") or "").strip()

    # 본문 추출
    email_text = text_body
    if not email_text and html_body:
        email_text = re.sub(r"<[^>]+>", "", html_body).strip()

    # 첨부파일 처리
    attachment_texts: list[str] = []
    images: list[tuple[bytes, str]] = []
    attachments_meta: list[dict] = []
    for att in email_data.get("attachments", []):
        att_id = att.get("id")
        filename = att.get("filename", "attachment")
        if not att_id:
            continue
        # 첨부파일 다운로드
        async with httpx.AsyncClient(timeout=30.0) as cli:
            att_resp = await cli.get(
                f"https://api.resend.com/emails/receiving/{email_id}/attachments/{att_id}",
                headers={"Authorization": f"Bearer {settings.resend_api_key}"},
            )
        if att_resp.status_code != 200:
            logger.warning("Resend 첨부 다운로드 실패: %s status=%s", filename, att_resp.status_code)
            continue

        # Resend API는 첨부파일을 JSON { "data": "<base64>" } 또는 raw binary로 반환
        content = att_resp.content
        content_type = att_resp.headers.get("content-type", "")
        logger.info(
            "Resend 첨부 응답: filename=%s, content_type=%s, size=%d, first_bytes=%s",
            filename, content_type, len(content), content[:80],
        )
        if "application/json" in content_type:
            try:
                att_json = att_resp.json()
                download_url = att_json.get("download_url")
                if download_url:
                    # Resend API: 첨부파일은 download_url에서 별도 다운로드
                    async with httpx.AsyncClient(timeout=30.0) as dl_cli:
                        dl_resp = await dl_cli.get(download_url)
                    if dl_resp.status_code != 200:
                        logger.warning("Resend 첨부 다운로드 실패: %s status=%s", filename, dl_resp.status_code)
                        continue
                    content = dl_resp.content
                    logger.info("Resend 첨부 다운로드 완료: %s → %d bytes", filename, len(content))
                else:
                    logger.warning("Resend 첨부 JSON에 download_url 없음: %s", filename)
                    continue
            except Exception:
                logger.exception("Resend 첨부 다운로드 실패: %s", filename)
                continue
        if content:
            from app.services.file_intake import intake_file
            from app.services.storage import get_storage
            from app.services.stt import get_stt_provider
            intake = await intake_file(
                filename=filename,
                content=content,
                storage=get_storage(),
                stt=get_stt_provider(),
            )
            if intake.text.strip():
                attachment_texts.append(f"[첨부: {filename}]\n{intake.text}")
            images.extend(intake.images)
            if intake.storage_key:
                attachments_meta.append({
                    "filename": filename,
                    "storage_key": intake.storage_key,
                    "kind": intake.kind,
                })

    full_text = email_text
    if attachment_texts:
        full_text = (email_text + "\n\n" + "\n\n".join(attachment_texts)).strip()

    if not full_text and not images:
        logger.warning("Resend 웹훅: 본문+첨부 비어있음 (from=%s)", from_addr)
        return {"status": "ignored", "reason": "empty content"}

    # ── 세션 매칭 (to 주소에서 collect+{id} 추출) ──
    to_addr = to_list[0] if to_list else ""
    session = None

    client_id = _extract_client_id(to_addr)
    if client_id:
        client = await db.get(Client, client_id)
        if client:
            session = await _find_active_session(db, client)

    if not session:
        token = _extract_token_from_address(to_addr)
        if token:
            session = (
                await db.execute(
                    select(CollectionSession)
                    .where(CollectionSession.request_token == token)
                    .options(
                        selectinload(CollectionSession.client),
                        selectinload(CollectionSession.monthly_filing),
                    )
                )
            ).scalar_one_or_none()

    if not session:
        clean_from = re.search(r"[\w.-]+@[\w.-]+", from_addr)
        sender_email = clean_from.group(0) if clean_from else from_addr
        client = (
            await db.execute(
                select(Client).where(Client.contact_email == sender_email)
            )
        ).scalar_one_or_none()
        if client:
            session = await _find_active_session(db, client)

    if not session:
        logger.warning("Resend 웹훅: 세션 매칭 실패 (to=%s, from=%s)", to_addr, from_addr)
        return {"status": "unmatched", "from": from_addr, "subject": subject}

    try:
        result = await _ingest_message(
            db=db,
            session=session,
            client=session.client,
            filing=session.monthly_filing,
            text=full_text,
            channel="email",
            images=images or None,
            attachments=attachments_meta or None,
        )
    except Exception:
        logger.exception("Resend 웹훅 처리 실패 (from=%s)", from_addr)
        return {"status": "error", "reason": "processing failed"}

    logger.info(
        "Resend 웹훅 처리 완료: from=%s, matched=%d, new_hire=%d",
        from_addr, result.matched, result.new_hire_suspected,
    )
    return {
        "status": "processed",
        "session_id": result.session_id,
        "matched": result.matched,
        "new_hire_suspected": result.new_hire_suspected,
    }


def _extract_client_id(address: str) -> str | None:
    """Extract full client ID from 'collect+{uuid}@domain' format.

    Supports both hyphenated (36-char) and non-hyphenated (32-char) UUIDs.
    """
    match = re.search(r"collect\+([a-f0-9-]{32,36})@", address)
    return match.group(1) if match else None


def _extract_token_from_address(address: str) -> str | None:
    """Extract token from 'collect+{token}@domain' format (longer tokens)."""
    match = re.search(r"collect\+([a-zA-Z0-9_-]{9,})@", address)
    return match.group(1) if match else None
