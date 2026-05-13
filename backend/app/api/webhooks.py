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

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.core.deps import get_db
from app.models import (
    Client,
    CollectionSession,
    MonthlyFiling,
    MonthlyFilingStatus,
)
from app.api.collect import _ingest_message

logger = logging.getLogger(__name__)
router = APIRouter()


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

@router.post("/kakao")
async def kakao_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """카카오 i 오픈빌더 폴백 스킬 웹훅.

    오픈빌더에서 "폴백 스킬"로 설정하면, 사용자가 비즈채널에서 보낸 모든 메시지가
    이 엔드포인트로 전달됩니다.

    요청 형식 (카카오 오픈빌더 스킬 표준):
    {
      "intent": {...},
      "userRequest": {
        "utterance": "김연호 500, 조명신 300",
        "user": {
          "id": "kakao_user_id",
          "properties": {
            "plusfriendUserKey": "unique_key"
          }
        }
      },
      "bot": {...},
      "action": {...}
    }

    응답: 카카오 스킬 응답 형식 (simpleText)
    """
    settings = get_settings()
    raw_body = await request.body()

    # 카카오 오픈빌더 스킬 서버 서명 검증
    if settings.kakao_webhook_secret:
        signature = request.headers.get("x-kakao-signature", "")
        if not _verify_kakao_signature(settings.kakao_webhook_secret, raw_body, signature):
            logger.warning("카카오 웹훅: 서명 검증 실패")
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid signature")

    try:
        body = json.loads(raw_body)
    except Exception:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid JSON")

    user_request = body.get("userRequest", {})
    utterance = user_request.get("utterance", "").strip()
    user_props = user_request.get("user", {}).get("properties", {})
    plusfriend_key = user_props.get("plusfriendUserKey", "")

    if not utterance:
        return _kakao_response("메시지 내용이 비어 있습니다.")

    # 발신자 → Client 매칭: plusfriendUserKey 또는 phone으로 매칭
    # Phase 1에서는 kakao_channel_id 필드로 매칭
    client = None
    if plusfriend_key:
        client = (
            await db.execute(
                select(Client).where(Client.kakao_channel_id == plusfriend_key)
            )
        ).scalar_one_or_none()

    if not client:
        logger.warning("카카오 웹훅: 매칭 실패 (plusfriend_key=%s)", plusfriend_key)
        return _kakao_response(
            "거래처 매칭에 실패했습니다. 세무사사무소에 문의해주세요."
        )

    session = await _find_active_session(db, client)
    if not session:
        return _kakao_response(
            "현재 진행 중인 자료 수집 건이 없습니다. 세무사사무소에 문의해주세요."
        )

    try:
        result = await _ingest_message(
            db=db,
            session=session,
            client=session.client,
            filing=session.monthly_filing,
            text=utterance,
            channel="kakao",
        )
        followup = result.ambiguous + result.needs_followup
        return _kakao_response(
            f"자료가 접수되었습니다.\n"
            f"기존직원 {result.matched}명 · 신규 {result.new_hire_suspected}명 "
            f"· 퇴사 {result.resignation_suspected}명 · 확인필요 {followup}명\n"
            f"세무사가 검증 후 추가 확인 사항이 있으면 연락드리겠습니다."
        )
    except Exception as e:
        logger.exception("카카오 웹훅 처리 실패")
        return _kakao_response("자료 처리 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요.")


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
            import base64 as _b64
            try:
                att_json = att_resp.json()
                logger.info("Resend 첨부 JSON keys: %s", list(att_json.keys()))
                # Resend API: 파일 데이터는 "data" 또는 "content" 키에 base64로 들어옴
                b64_data = att_json.get("data") or att_json.get("content") or att_json.get("body") or ""
                if not b64_data:
                    logger.warning("Resend 첨부 JSON에 파일 데이터 키 없음: %s (keys=%s)", filename, list(att_json.keys()))
                    continue
                content = _b64.b64decode(b64_data)
                logger.info("Resend 첨부 base64 디코딩 완료: %s → %d bytes", filename, len(content))
            except Exception:
                logger.exception("Resend 첨부 base64 디코딩 실패: %s", filename)
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
