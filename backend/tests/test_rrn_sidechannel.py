"""RRN 사이드채널 (plan/10 §2.0·G4) — 파일 반입 → 결정론 추출 → AI 결과 병합 →
new_hire_followups 전파 → 커밋 시 rrn_encrypted_b64 복호화 저장 왕복.

LLM 은 이 흐름에서 마스킹된 텍스트만 본다는 원칙을 재확인하는 회귀 테스트를 함께 둔다.
"""

from __future__ import annotations

import base64
from pathlib import Path

import pytest
from httpx import AsyncClient

from app.services.ai_parser import (
    MatchedEmployee,
    NewHireSuspected,
    PayrollParsingResult,
    merge_rrn_sidechannel,
)
from app.services.crypto import decrypt_rrn, encrypt_rrn, normalize_rrn
from app.services.file_intake import _extract_rrn_map_excel
from app.services.matching import EmployeeMaster, reconcile
from app.services.pii import redact_pii


SAMPLE = Path(__file__).resolve().parents[2] / "samples" / "999-99-99998" / "employees.xlsx"


def test_extract_rrn_map_from_sample_excel():
    with open(SAMPLE, "rb") as f:
        m = _extract_rrn_map_excel(f.read())
    assert set(m) == {"홍길동", "이서준", "박선희"}
    # 뒤 4자리 정확도 + 왕복 복호화로 원본 일치 확인
    assert m["홍길동"]["rrn_last4"] == "4567"
    ct = base64.b64decode(m["홍길동"]["rrn_encrypted_b64"])
    assert decrypt_rrn(ct) == "9001011234567"


def test_extract_ignores_invalid_rrn(tmp_path: Path):
    """자릿수·생년월일·성별코드 실패 행은 조용히 스킵 — 사용자 직접입력 폴백."""
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.append(["사원명", "주민번호"])
    ws.append(["정상", "900101-1234567"])
    ws.append(["짧음", "9001011"])
    ws.append(["생년월일이상", "999901-1234567"])
    ws.append(["성별코드0", "900101-0234567"])
    path = tmp_path / "mixed.xlsx"
    wb.save(path)

    m = _extract_rrn_map_excel(path.read_bytes())
    assert set(m) == {"정상"}


def test_merge_rrn_sidechannel_populates_new_hire_and_matched():
    parsed = PayrollParsingResult(
        matched_employees=[MatchedEmployee(name="김연호", employee_id="e1", amount=3_000_000)],
        new_hire_suspected=[
            NewHireSuspected(name="홍길동", amount=200_000),
            NewHireSuspected(name="김지훈", amount=5_000_000),  # 파일에 없음
        ],
    )
    rrn_map = {
        "홍길동": {"rrn_last4": "4567", "rrn_encrypted_b64": "aGVsbG8="},
        "김연호": {"rrn_last4": "9876", "rrn_encrypted_b64": "d29ybGQ="},
    }
    merge_rrn_sidechannel(parsed, rrn_map)

    assert parsed.matched_employees[0].rrn_last4 == "9876"
    assert parsed.new_hire_suspected[0].rrn_last4 == "4567"
    # 파일에 없던 이름은 그대로 None
    assert parsed.new_hire_suspected[1].rrn_last4 is None
    assert parsed.new_hire_suspected[1].rrn_encrypted_b64 is None


def test_reconcile_propagates_rrn_to_new_hire_followups():
    parsed = PayrollParsingResult(
        matched_employees=[],
        new_hire_suspected=[
            NewHireSuspected(
                name="홍길동", amount=200_000,
                rrn_last4="4567", rrn_encrypted_b64="AAAA",
            ),
            NewHireSuspected(name="김지훈", amount=5_000_000),
        ],
    )
    result = reconcile(parsed, master=[], previous_month={})

    with_rrn = next(f for f in result.new_hire_followups if f["name"] == "홍길동")
    without_rrn = next(f for f in result.new_hire_followups if f["name"] == "김지훈")
    assert with_rrn["rrn_last4"] == "4567"
    assert with_rrn["rrn_encrypted_b64"] == "AAAA"
    assert "rrn_last4" not in without_rrn
    assert "rrn_encrypted_b64" not in without_rrn


def test_redact_pii_still_masks_rrn_in_text():
    """G3 회귀: 텍스트로 흘러가는 RRN 은 여전히 마스킹된다 (LLM 프롬프트 스크러빙)."""
    assert "******-*******" in redact_pii("홍길동 900101-1234567 200만원")


async def _pick_session(http: AsyncClient, auth_headers: dict) -> tuple[str, str]:
    filings = (await http.get("/api/v1/filings", headers=auth_headers)).json()
    apr = next(f for f in filings if f["period"] == "2026-04")
    dash = (await http.get(f"/api/v1/filings/{apr['id']}/dashboard", headers=auth_headers)).json()
    return apr["id"], dash["sessions"][0]["id"]


@pytest.mark.asyncio
async def test_commit_uses_encrypted_sidechannel_when_user_didnt_type_rrn(
    http: AsyncClient, auth_headers: dict
):
    """반입 파일 사이드채널 rrn_encrypted_b64 만 왕복되어도 Employee 가 정상 생성된다."""
    filing_id, session_id = await _pick_session(http, auth_headers)

    # 사이드채널이 프리뷰 응답에 실려 프론트에 갔다가 그대로 커밋으로 돌아오는 시나리오 재현
    digits = normalize_rrn("900101-1234567")
    b64 = base64.b64encode(encrypt_rrn(digits)).decode()

    res = await http.post(
        f"/api/v1/collect/sessions/{session_id}/messages/commit",
        headers=auth_headers,
        json={
            "text": "신규 사이드채널테스트 300만원",
            "channel": "manual",
            "sender_name": "직접입력",
            "received_date": "2026-04-10",
            "entries": [{
                "raw_name": "사이드채널테스트",
                "income_type": "WAGE",
                "total_amount": 3_000_000,
                "match_status": "NEW_HIRE_SUSPECTED",
                # rrn 필드는 비워두고 사이드채널만 전달 — 원본 평문이 왕복되지 않음
                "new_employee": {"rrn_encrypted_b64": b64, "hired_at": "2026-04-01"},
            }],
        },
    )
    assert res.status_code == 200, res.text

    dash = (await http.get(f"/api/v1/filings/{filing_id}/dashboard", headers=auth_headers)).json()
    client_id = dash["sessions"][0]["client_id"]
    employees = (
        await http.get(f"/api/v1/clients/{client_id}/employees", headers=auth_headers)
    ).json()
    created = next(e for e in employees if e["name"] == "사이드채널테스트")
    assert created["rrn_last4"] == "4567"
    assert created["status"] == "ACTIVE"


@pytest.mark.asyncio
async def test_commit_rejects_tampered_sidechannel(http: AsyncClient, auth_headers: dict):
    """base64 는 맞아도 GCM 태그가 안 맞는 위조 암호문은 반드시 거부."""
    _, session_id = await _pick_session(http, auth_headers)

    junk = base64.b64encode(b"\x00" * 32).decode()
    res = await http.post(
        f"/api/v1/collect/sessions/{session_id}/messages/commit",
        headers=auth_headers,
        json={
            "text": "신규 위조테스트 300만원",
            "channel": "manual",
            "sender_name": "직접입력",
            "received_date": "2026-04-10",
            "entries": [{
                "raw_name": "위조테스트",
                "income_type": "WAGE",
                "total_amount": 3_000_000,
                "match_status": "NEW_HIRE_SUSPECTED",
                "new_employee": {"rrn_encrypted_b64": junk},
            }],
        },
    )
    assert res.status_code == 400, res.text
    assert "주민번호" in res.json()["detail"]
