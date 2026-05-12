"""거래처 인식 결과 확인 요청 — 세무사가 수동 트리거로 발송.

흐름:
1. 세무사가 세션 상세에서 "거래처에 인식 결과 확인 요청" 버튼 클릭
2. 백엔드가 현재까지 파싱된 PayrollEntry를 사람이 읽을 수 있는 요약으로 변환
3. 인입 채널(email/kakao 등)을 자동 감지해 같은 채널로 발신
4. 거래처가 같은 채널로 회신하면 기존 webhook 파이프라인이 후속 수정 반영
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.channels import MessageRecipient, SendResult, get_email_channel, get_sms_channel
from app.channels.alimtalk import get_alimtalk_channel
from app.config import get_settings
from app.models import (
    Client,
    CollectionEvent,
    CollectionSession,
    MonthlyFiling,
    PayrollEntry,
)
from app.models.payroll import IncomeType, MatchStatus

logger = logging.getLogger(__name__)


_INCOME_LABEL = {
    IncomeType.WAGE: "근로",
    IncomeType.BUSINESS: "사업",
    IncomeType.OTHER: "기타",
    IncomeType.DAILY: "일용",
    IncomeType.RETIREMENT: "퇴직",
}


def _fmt_won(amount: int) -> str:
    """1500000 → '150만원'. 만원 단위 미만은 원으로 표시."""
    if amount % 10000 == 0:
        return f"{amount // 10000}만원"
    return f"{amount:,}원"


def _status_label(s: str) -> str:
    return {
        MatchStatus.MATCHED.value: "기존직원",
        MatchStatus.NEW_HIRE_SUSPECTED.value: "신규",
        MatchStatus.RESIGNATION_SUSPECTED.value: "퇴사",
        MatchStatus.AMBIGUOUS.value: "확인필요",
    }.get(s, s)


def build_confirmation_text(
    *,
    client: Client,
    filing: MonthlyFiling,
    entries: list[PayrollEntry],
    office_name: str,
    collect_email: str | None,
    public_url: str | None,
) -> str:
    """카톡/SMS용 — 짧은 평문 요약."""
    lines: list[str] = [
        f"[{office_name}] {filing.period} 원천세 자료 확인 요청",
        "",
        f"보내주신 자료를 아래와 같이 정리했습니다.",
        f"잘못 인식된 부분이 있으면 회신 부탁드립니다.",
        "",
    ]

    if not entries:
        lines.append("(아직 파싱된 항목이 없습니다)")
    else:
        for e in entries:
            biz = _INCOME_LABEL.get(IncomeType(e.income_type), e.income_type)
            tag = _status_label(e.match_status)
            name = e.raw_name or "(이름 미상)"
            lines.append(f"· {name} ({biz}) {_fmt_won(e.total_amount)} — {tag}")

    lines.append("")
    lines.append("회신 주실 곳:")
    if collect_email:
        lines.append(f"- 이메일: {collect_email}")
    if public_url:
        lines.append(f"- 입력 폼: {public_url}")

    return "\n".join(lines)


def build_confirmation_html(
    *,
    client: Client,
    filing: MonthlyFiling,
    entries: list[PayrollEntry],
    office_name: str,
    collect_email: str | None,
    public_url: str | None,
) -> str:
    """이메일용 — 표 형식."""
    if entries:
        rows = "".join(
            f"<tr>"
            f"<td style='padding:4px 8px;border-bottom:1px solid #eee'>{e.raw_name or '-'}</td>"
            f"<td style='padding:4px 8px;border-bottom:1px solid #eee'>{_INCOME_LABEL.get(IncomeType(e.income_type), e.income_type)}</td>"
            f"<td style='padding:4px 8px;border-bottom:1px solid #eee;text-align:right'>{_fmt_won(e.total_amount)}</td>"
            f"<td style='padding:4px 8px;border-bottom:1px solid #eee'>{_status_label(e.match_status)}</td>"
            f"</tr>"
            for e in entries
        )
        table = (
            f"<table style='border-collapse:collapse;width:100%;margin-top:8px'>"
            f"<thead><tr style='background:#f5f5f5'>"
            f"<th style='padding:4px 8px;text-align:left'>성명</th>"
            f"<th style='padding:4px 8px;text-align:left'>구분</th>"
            f"<th style='padding:4px 8px;text-align:right'>총지급액</th>"
            f"<th style='padding:4px 8px;text-align:left'>상태</th>"
            f"</tr></thead><tbody>{rows}</tbody></table>"
        )
    else:
        table = "<p style='color:#666'>아직 파싱된 항목이 없습니다.</p>"

    reply_links = ""
    if collect_email:
        reply_links += f"<li>이메일: <a href='mailto:{collect_email}'>{collect_email}</a></li>"
    if public_url:
        reply_links += f"<li>입력 폼: <a href='{public_url}'>{public_url}</a></li>"

    return (
        f"<p>안녕하세요, <b>{office_name}</b>입니다.</p>"
        f"<p><b>{filing.period}</b> 원천세 자료를 아래와 같이 정리했습니다.</p>"
        f"<p>잘못 인식되었거나 누락된 부분이 있으면 회신 부탁드립니다.</p>"
        f"{table}"
        f"<p style='margin-top:16px;color:#666;font-size:13px'>"
        f"※ 이미지/파일로 보내주신 경우 AI가 자동으로 읽었습니다. 자릿수 오인 가능성이 있으니 확인 부탁드립니다."
        f"</p>"
        f"<p style='margin-top:12px'>회신 주실 곳:</p>"
        f"<ul>{reply_links}</ul>"
    )


async def detect_inbound_channel(
    db: AsyncSession, session: CollectionSession,
) -> str | None:
    """세션의 가장 최근 RECEIVE_* 이벤트에서 인입 채널 추출."""
    ev = (
        await db.execute(
            select(CollectionEvent)
            .where(
                CollectionEvent.session_id == session.id,
                CollectionEvent.event_type.like("RECEIVE_%"),
            )
            .order_by(CollectionEvent.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if not ev:
        return None
    return ev.channel  # "email" | "kakao" | "public_url" | "public_upload_image" | ...


async def send_confirmation(
    db: AsyncSession,
    *,
    session: CollectionSession,
    client: Client,
    filing: MonthlyFiling,
    entries: list[PayrollEntry],
    office_name: str,
    channel: str | None = None,  # 명시 안 하면 인입 채널 기반 자동
) -> tuple[bool, str, str | None]:
    """반환: (성공여부, 사용한 채널, 에러 메시지). 호출자가 commit 책임."""
    settings = get_settings()

    if not channel or channel == "auto":
        detected = await detect_inbound_channel(db, session)
        # public_url / public_upload_* 는 reply 채널이 아님 → email/sms로 폴백
        if detected in ("email", "kakao"):
            channel = detected
        elif client.contact_email:
            channel = "email"
        elif client.contact_phone:
            channel = "sms"
        else:
            return False, "none", "거래처 연락처가 없어 회신할 수 없습니다."

    public_url = (
        f"{settings.app_public_url}/r/{session.request_token}"
        if session.request_token
        else None
    )

    if channel == "email":
        if not client.contact_email:
            return False, channel, "거래처 이메일이 없습니다."
        body = build_confirmation_html(
            client=client, filing=filing, entries=entries,
            office_name=office_name, collect_email=client.collect_email, public_url=public_url,
        )
        result = await get_email_channel().send(
            MessageRecipient(
                name=client.business_name, phone=client.contact_phone, email=client.contact_email,
            ),
            body=body, url=public_url,
        )
    elif channel == "kakao":
        if settings.kakao_alimtalk_provider not in ("aligo", "nhn_cloud"):
            # 알림톡 provider 미설정 → SMS로 폴백
            return await send_confirmation(
                db, session=session, client=client, filing=filing, entries=entries,
                office_name=office_name, channel="sms",
            )
        if not client.contact_phone:
            return False, channel, "거래처 전화번호가 없습니다."
        body = build_confirmation_text(
            client=client, filing=filing, entries=entries,
            office_name=office_name, collect_email=client.collect_email, public_url=public_url,
        )
        result = await get_alimtalk_channel().send(
            MessageRecipient(
                name=client.business_name, phone=client.contact_phone, email=client.contact_email,
            ),
            body=body, template_code="CONFIRM_PARSED", url=public_url,
        )
    elif channel == "sms":
        if not client.contact_phone:
            return False, channel, "거래처 전화번호가 없습니다."
        body = build_confirmation_text(
            client=client, filing=filing, entries=entries,
            office_name=office_name, collect_email=client.collect_email, public_url=public_url,
        )
        result = await get_sms_channel().send(
            MessageRecipient(name=client.business_name, phone=client.contact_phone),
            body=body, url=public_url,
        )
    else:
        return False, channel, f"알 수 없는 채널: {channel}"

    # 감사 로그
    db.add(
        CollectionEvent(
            session_id=session.id,
            event_type="SEND_CONFIRMATION",
            channel=result.channel,
            raw_text=body,
            raw_payload={
                "accepted": result.accepted,
                "error": result.error,
                "msg_id": result.provider_msg_id,
                "requested_channel": channel,
            },
        )
    )
    return result.accepted, result.channel, result.error
