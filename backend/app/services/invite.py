"""Invite dispatch — per-client send via 알림톡 → SMS fallback + 이메일."""

from datetime import UTC, datetime as _dt, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.channels import (
    MessageRecipient,
    SendResult,
    get_alimtalk_channel,
    get_email_channel,
    get_sms_channel,
)
from app.config import Settings, get_settings
from app.models import (
    Client,
    CollectionEvent,
    CollectionSession,
    CollectionSessionStatus,
    MonthlyFiling,
)
from app.services.secure_tokens import issue_token


async def get_or_create_session(
    db: AsyncSession,
    filing: MonthlyFiling,
    client: Client,
    ttl_days: int = 14,
) -> CollectionSession:
    existing = (
        await db.execute(
            select(CollectionSession).where(
                CollectionSession.monthly_filing_id == filing.id,
                CollectionSession.client_id == client.id,
            )
        )
    ).scalar_one_or_none()
    if existing:
        return existing

    token = await issue_token(
        db,
        client_id=client.id,
        purpose="COLLECTION_REQUEST",
        ttl=timedelta(days=ttl_days),
        context={"filing_id": filing.id},
    )
    session = CollectionSession(
        monthly_filing_id=filing.id,
        client_id=client.id,
        request_token=token.token,
    )
    db.add(session)
    await db.flush()
    token.collection_session_id = session.id
    return session


async def send_invite_to_client(
    db: AsyncSession,
    filing: MonthlyFiling,
    client: Client,
    office_name: str,
    *,
    settings: Settings | None = None,
) -> tuple[CollectionSession, list[str], list[SendResult]]:
    """Send invite (알림톡 → SMS fallback + 이메일) to a single client.

    Returns (session, accepted_channels, all_attempts).
    - accepted_channels: 성공한 채널명 리스트 (예: ["sms_aligo", "email_sendgrid"])
    - all_attempts: 시도한 모든 SendResult (실패 채널 + 사유 진단용)
    Caller is responsible for db.commit().
    """
    settings = settings or get_settings()
    session = await get_or_create_session(db, filing, client, ttl_days=30)
    url = f"{settings.app_public_url}/r/{session.request_token}"

    invite_body = (
        f"안녕하세요, {office_name}입니다.\n\n"
        f"{filing.period} 원천세 자료를 요청드립니다.\n\n"
        f"아래 방법 중 편한 방법으로 보내주세요:\n\n"
        f"1) 카카오톡 채팅으로 직접 답장\n"
        f"2) 이메일: {client.collect_email}\n"
        f"3) 입력 폼: {url}\n\n"
        f"이 메일에 바로 회신하셔도 자동 접수됩니다."
    )

    if settings.kakao_alimtalk_provider in ("aligo", "nhn_cloud"):
        alimtalk = get_alimtalk_channel()
        alimtalk_result = await alimtalk.send(
            MessageRecipient(
                name=client.business_name,
                phone=client.contact_phone,
                email=client.contact_email,
            ),
            body=invite_body,
            template_code="COLLECTION_INVITE",
            url=url,
        )
    else:
        alimtalk_result = SendResult(
            channel="alimtalk_skipped",
            accepted=False,
            provider_msg_id=None,
            error="알림톡 provider 미설정 (KAKAO_ALIMTALK_PROVIDER)",
        )

    sms_result: SendResult | None = None
    if not alimtalk_result.accepted and client.contact_phone:
        sms = get_sms_channel()
        sms_body = f"[{office_name}] {filing.period} 원천세 자료 요청: {url}"
        sms_result = await sms.send(
            MessageRecipient(name=client.business_name, phone=client.contact_phone),
            body=sms_body,
            url=url,
        )

    email_result: SendResult | None = None
    if client.contact_email:
        email_ch = get_email_channel()
        email_body = (
            f"<p>안녕하세요, <b>{office_name}</b>입니다.</p>"
            f"<p><b>{filing.period}</b> 원천세 자료를 요청드립니다.</p>"
            f"<hr>"
            f"<p>아래 방법 중 편한 방법으로 보내주세요:</p>"
            f"<ol>"
            f"<li><b>이 메일에 바로 회신</b> (엑셀 첨부 가능)</li>"
            f"<li>전용 이메일: <a href='mailto:{client.collect_email}'>{client.collect_email}</a></li>"
            f"<li>입력 폼: <a href='{url}'>{url}</a></li>"
            f"</ol>"
            f"<p style='color:#666;font-size:12px;'>회신하시면 자동으로 접수됩니다.</p>"
        )
        email_result = await email_ch.send(
            MessageRecipient(
                name=client.business_name,
                phone=client.contact_phone,
                email=client.contact_email,
            ),
            body=email_body,
            template_code=f"[{office_name}] {filing.period} 원천세 자료 요청",
            url=url,
            reply_to=client.collect_email,
        )

    sent = (
        alimtalk_result.accepted
        or (sms_result is not None and sms_result.accepted)
        or (email_result is not None and email_result.accepted)
    )
    session.status = (
        CollectionSessionStatus.SENT if sent else CollectionSessionStatus.PENDING
    )
    if sent:
        session.request_sent_at = _dt.now(UTC)
        client.invite_sent = True

    channels_used = ["alimtalk"]
    if sms_result is not None:
        channels_used.append("sms")
    if email_result is not None:
        channels_used.append("email")

    db.add(
        CollectionEvent(
            session_id=session.id,
            event_type="SEND_INVITE",
            channel="+".join(channels_used),
            raw_text=invite_body,
            raw_payload={
                "alimtalk_ok": alimtalk_result.accepted,
                "alimtalk_error": alimtalk_result.error,
                "sms_ok": sms_result.accepted if sms_result else None,
                "sms_error": sms_result.error if sms_result else None,
                "email_ok": email_result.accepted if email_result else None,
                "email_error": email_result.error if email_result else None,
                "collect_email": client.collect_email,
            },
        )
    )

    # 실제 채널명 노출 — sms_aligo / sms_stub / email_sendgrid / email_stub 등
    # UI는 "_stub" 접미사로 테스트 모드를 감지해 경고를 표시
    # 시도된 모든 결과(성공/실패) 함께 반환 → UI에서 실패 사유까지 표시
    attempts: list[SendResult] = [alimtalk_result]
    if sms_result is not None:
        attempts.append(sms_result)
    if email_result is not None:
        attempts.append(email_result)
    accepted_channels = [a.channel for a in attempts if a.accepted]
    return session, accepted_channels, attempts
