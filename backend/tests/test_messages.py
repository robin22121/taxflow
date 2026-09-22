"""문자발송 메뉴 — 세목별 신고안내 (plan/13-messaging-activation.md §5).

실제 문자·알림톡은 나가지 않는다. 채널을 가로채 본문만 확인한다.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.channels import SendResult


class _CaptureChannel:
    def __init__(self, name: str, accepted: bool = True) -> None:
        self.name = name
        self.accepted = accepted
        self.sent: list[dict] = []

    async def send(self, recipient, *, body: str, template_code: str | None = None, **kwargs):
        self.sent.append({"body": body, "to": recipient.phone, "template_code": template_code})
        return SendResult(
            channel=self.name,
            accepted=self.accepted,
            provider_msg_id="captured" if self.accepted else None,
            error=None if self.accepted else "rejected",
        )


async def _make_clients() -> dict[str, str]:
    from app.db import SessionLocal
    from app.models import Client, User

    async with SessionLocal() as db:
        admin = (
            await db.execute(select(User).where(User.email == "admin@example.com"))
        ).scalar_one()
        specs = {
            "corp_fy3": Client(
                business_name="안내테스트 3월결산법인", is_corporation=True,
                fiscal_year_end_month=3, contact_phone="010-1111-0001",
            ),
            "exempt": Client(
                business_name="안내테스트 면세개인", representative="김면세",
                vat_type="EXEMPT", contact_phone="010-1111-0002",
            ),
            "general_semi": Client(
                business_name="안내테스트 일반개인", representative="이일반",
                vat_type="GENERAL", withholding_semiannual=True, sincere_filing=True,
                contact_phone="010-1111-0003",
            ),
            "no_phone": Client(business_name="안내테스트 무연락처", vat_type="GENERAL"),
        }
        for c in specs.values():
            c.tax_office_id = admin.tax_office_id
            db.add(c)
        await db.commit()
        return {k: c.id for k, c in specs.items()}


@pytest.fixture
async def ids():
    return await _make_clients()


async def _targets(http, headers, tax_type, scope="all") -> dict[str, dict]:
    r = await http.post(
        "/api/v1/messages/filing-notice/targets",
        json={"tax_type": tax_type, "scope": scope},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    return {t["client_id"]: t for t in r.json()["items"]}


@pytest.mark.asyncio
async def test_targets_filter_by_tax_type(http: AsyncClient, auth_headers, ids):
    vat = await _targets(http, auth_headers, "VAT")
    assert vat[ids["exempt"]]["eligible"] is False
    assert vat[ids["exempt"]]["reason"] == "면세사업자"
    assert vat[ids["general_semi"]]["eligible"] is True
    assert vat[ids["no_phone"]]["reason"] == "연락처 없음"

    simplified = await _targets(http, auth_headers, "VAT", "simplified")
    assert simplified[ids["general_semi"]]["eligible"] is False

    corp = await _targets(http, auth_headers, "CORPORATE", "fy12")
    assert corp[ids["corp_fy3"]]["reason"] == "3월 결산"
    assert corp[ids["exempt"]]["reason"] == "개인사업자"
    assert (await _targets(http, auth_headers, "CORPORATE", "fy_other"))[ids["corp_fy3"]]["eligible"]

    income = await _targets(http, auth_headers, "INCOME", "sincere")
    assert income[ids["corp_fy3"]]["reason"] == "법인"
    assert income[ids["general_semi"]]["eligible"] is True
    assert income[ids["exempt"]]["reason"] == "성실신고 대상 아님"

    wh = await _targets(http, auth_headers, "WITHHOLDING", "monthly")
    assert wh[ids["general_semi"]]["reason"] == "반기납부"


@pytest.mark.asyncio
async def test_sms_send_substitutes_and_logs(monkeypatch, http: AsyncClient, auth_headers, ids):
    from app.api import messages as mod

    sms = _CaptureChannel("sms_capture")
    monkeypatch.setattr(mod, "get_sms_channel", lambda **kw: sms)

    r = await http.post(
        "/api/v1/messages/filing-notice/send",
        json={
            "tax_type": "VAT",
            "channel": "sms",
            "client_ids": [ids["general_semi"], ids["exempt"], ids["no_phone"]],
            "body": "[{사무소명}] {거래처명} {대표자}대표님, {세목} 기한 {신고기한}",
            "deadline": "10월 25일",
        },
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["sent"] == 1 and out["failed"] == 2
    skipped = {x["client_id"]: x["error"] for x in out["results"] if not x["accepted"]}
    assert skipped == {ids["exempt"]: "면세사업자", ids["no_phone"]: "연락처 없음"}

    assert len(sms.sent) == 1
    body = sms.sent[0]["body"]
    assert "안내테스트 일반개인 이일반 대표님, 부가가치세 기한 10월 25일" in body
    assert "{" not in body

    hist = await http.get("/api/v1/messages/history", headers=auth_headers)
    top = hist.json()["items"][0]
    assert top["client_id"] == ids["general_semi"]
    assert top["channel"] == "sms_capture" and top["accepted"] is True
    assert top["tax_type"] == "VAT" and top["requested_channel"] == "sms"


@pytest.mark.asyncio
async def test_alimtalk_stub_provider_falls_back_to_sms(
    monkeypatch, http: AsyncClient, auth_headers, ids
):
    """운영 기본값(KAKAO_ALIMTALK_PROVIDER=stub)에서 카톡을 골라도 가짜 성공이 아니라 문자로 나간다."""
    from app.api import messages as mod

    sms = _CaptureChannel("sms_capture")
    monkeypatch.setattr(mod, "get_sms_channel", lambda **kw: sms)
    called = []
    monkeypatch.setattr(mod, "get_alimtalk_channel", lambda: called.append(1))

    r = await http.post(
        "/api/v1/messages/filing-notice/send",
        json={
            "tax_type": "WITHHOLDING", "channel": "alimtalk",
            "client_ids": [ids["general_semi"]], "body": "{거래처명} 안내",
        },
        headers=auth_headers,
    )
    assert r.json()["results"][0]["channel"] == "sms_capture"
    assert not called
    assert sms.sent[0]["body"] == "안내테스트 일반개인 안내"


@pytest.mark.asyncio
async def test_alimtalk_uses_fixed_template(monkeypatch, http: AsyncClient, auth_headers, ids):
    """알림톡은 사용자가 고친 본문이 아니라 심사 문구(T4)를 보낸다."""
    from app.api import messages as mod
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "kakao_alimtalk_provider", "aligo")
    kakao = _CaptureChannel("alimtalk_capture")
    sms = _CaptureChannel("sms_capture")
    monkeypatch.setattr(mod, "get_alimtalk_channel", lambda: kakao)
    monkeypatch.setattr(mod, "get_sms_channel", lambda **kw: sms)

    r = await http.post(
        "/api/v1/messages/filing-notice/send",
        json={
            "tax_type": "CORPORATE", "channel": "alimtalk",
            "client_ids": [ids["corp_fy3"]], "body": "자유 문구", "deadline": "6월 30일",
        },
        headers=auth_headers,
    )
    assert r.json()["results"][0]["channel"] == "alimtalk_capture"
    assert not sms.sent
    sent = kakao.sent[0]
    assert sent["template_code"] == "FILING_NOTICE"
    assert "법인세 신고기간" in sent["body"] and "6월 30일" in sent["body"]
    assert "결산 자료" in sent["body"] and "#{" not in sent["body"]
