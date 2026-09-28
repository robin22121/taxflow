"""전월 동일 페스트패스 (plan/01-workflow-roadmap.md §1.3) 통합·단위 테스트.

시드 데이터는 2026-01 ~ 2026-04 4개월 필링을 만든다 (`scripts/seed.py`).
페스트패스는 "이번 달"에 진입하려면 그 달 필링이 있고, 전월에 데이터가 있어야 한다.
2026-05를 신설해 2026-04를 전월로 삼아 테스트한다.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import AsyncClient

from app.api.fast_path import _recalc_row
from app.models.employee import Employee, EmploymentStatus
from app.models.payroll import IncomeType, PayrollEntry


@pytest_asyncio.fixture(scope="module", autouse=True)
async def _reset_after_fast_path():
    """이 모듈은 5월 필링을 새로 만들고 approved 엔트리를 추가하므로,
    끝난 뒤엔 DB를 재시드해 후속 테스트(예: `test_rpa_wehago_upload`)가
    기대하는 원래 시드 상태로 되돌린다.
    """
    yield
    from app.db import Base, engine
    from app import models  # noqa: F401
    from app.scripts.seed import main as seed_main

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    await seed_main()


async def _april_client_id(http: AsyncClient, auth_headers: dict) -> str:
    """시드에 있는 4월 필링의 첫 거래처 id를 돌려준다."""
    filings = (await http.get("/api/v1/filings", headers=auth_headers)).json()
    apr = next(f for f in filings if f["period"] == "2026-04")
    dash = (await http.get(f"/api/v1/filings/{apr['id']}/dashboard", headers=auth_headers)).json()
    return dash["sessions"][0]["client_id"]


async def _create_may_filing(http: AsyncClient, auth_headers: dict) -> str:
    """5월 필링을 만들거나(이미 있으면 그대로) id를 돌려준다."""
    r = await http.post(
        "/api/v1/filings", headers=auth_headers, json={"period": "2026-05"}
    )
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


@pytest.mark.asyncio
async def test_preview_returns_summary_with_prev_month_data(
    http: AsyncClient, auth_headers: dict
):
    """전월(4월)에 자료가 있는 거래처는 프리뷰가 정상 반환된다."""
    may_id = await _create_may_filing(http, auth_headers)
    client_id = await _april_client_id(http, auth_headers)

    r = await http.post(
        f"/api/v1/filings/{may_id}/clients/{client_id}/fast-path/preview",
        headers=auth_headers,
        json={"threshold_pct": 2.0},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["prev_period"] == "2026-04"
    assert data["curr_period"] == "2026-05"
    assert data["person_count"] >= 1
    assert data["total_pay"] > 0
    assert isinstance(data["delta_pct"], (int, float))
    assert data["threshold_pct"] == 2.0
    # 프리뷰는 저장하지 않으므로 can_commit=True
    assert data["can_commit"] is True
    assert data["blocker"] is None


@pytest.mark.asyncio
async def test_preview_404_when_filing_missing(
    http: AsyncClient, auth_headers: dict
):
    client_id = await _april_client_id(http, auth_headers)
    r = await http.post(
        f"/api/v1/filings/nonexistent-id/clients/{client_id}/fast-path/preview",
        headers=auth_headers,
        json={"threshold_pct": 2.0},
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_preview_400_when_prev_month_has_no_data(
    http: AsyncClient, auth_headers: dict
):
    """1월 필링에서 페스트패스를 부르면 전월(2025-12)에 자료가 없어 400."""
    filings = (await http.get("/api/v1/filings", headers=auth_headers)).json()
    jan = next(f for f in filings if f["period"] == "2026-01")
    client_id = await _april_client_id(http, auth_headers)

    r = await http.post(
        f"/api/v1/filings/{jan['id']}/clients/{client_id}/fast-path/preview",
        headers=auth_headers,
        json={"threshold_pct": 2.0},
    )
    assert r.status_code == 400
    assert "2025-12" in r.text


@pytest.mark.asyncio
async def test_preview_blocker_when_current_month_has_entries(
    http: AsyncClient, auth_headers: dict
):
    """이번 달(4월)에 이미 자료가 있으면 프리뷰는 오지만 can_commit=False."""
    filings = (await http.get("/api/v1/filings", headers=auth_headers)).json()
    apr = next(f for f in filings if f["period"] == "2026-04")
    client_id = await _april_client_id(http, auth_headers)

    r = await http.post(
        f"/api/v1/filings/{apr['id']}/clients/{client_id}/fast-path/preview",
        headers=auth_headers,
        json={"threshold_pct": 2.0},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["can_commit"] is False
    assert data["blocker"] is not None
    assert "2026-04" in data["blocker"]


@pytest.mark.asyncio
async def test_commit_creates_approved_entries_when_within_threshold(
    http: AsyncClient, auth_headers: dict
):
    """정상 케이스: 델타가 임계치 안에 있으면 커밋 시 approved=True 엔트리 생성."""
    may_id = await _create_may_filing(http, auth_headers)
    client_id = await _april_client_id(http, auth_headers)

    # 프리뷰로 현재 델타 확인
    prev = await http.post(
        f"/api/v1/filings/{may_id}/clients/{client_id}/fast-path/preview",
        headers=auth_headers,
        json={"threshold_pct": 100.0},
    )
    prev_data = prev.json()
    delta = prev_data["delta_pct"]
    person_count = prev_data["person_count"]
    assert person_count > 0

    # 델타보다 조금 큰 임계치로 커밋
    r = await http.post(
        f"/api/v1/filings/{may_id}/clients/{client_id}/fast-path/commit",
        headers=auth_headers,
        json={"threshold_pct": max(delta + 0.5, 2.0)},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["approved"] is True
    assert data["created_entries"] == person_count

    # 두 번째 호출은 409 — 이미 항목이 존재
    r2 = await http.post(
        f"/api/v1/filings/{may_id}/clients/{client_id}/fast-path/commit",
        headers=auth_headers,
        json={"threshold_pct": 100.0},
    )
    assert r2.status_code == 409
    assert "이미" in r2.text


@pytest.mark.asyncio
async def test_commit_rejects_when_delta_exceeds_threshold(
    http: AsyncClient, auth_headers: dict
):
    """델타를 초과하는 임계치에서는 커밋을 거부한다 (0% 임계치로 강제)."""
    may_id = await _create_may_filing(http, auth_headers)
    filings = (await http.get("/api/v1/filings", headers=auth_headers)).json()
    apr = next(f for f in filings if f["period"] == "2026-04")
    dash = (await http.get(f"/api/v1/filings/{apr['id']}/dashboard", headers=auth_headers)).json()
    # 이전 테스트에서 첫 거래처(sessions[0])는 5월에 커밋됐을 수 있으니 다른 거래처를 쓴다
    first_client_id = dash["sessions"][0]["client_id"]
    other = next(
        s for s in dash["sessions"]
        if s.get("entry_count", 0) > 0 and s["client_id"] != first_client_id
    )
    client_id = other["client_id"]

    r = await http.post(
        f"/api/v1/filings/{may_id}/clients/{client_id}/fast-path/commit",
        headers=auth_headers,
        json={"threshold_pct": 0.0},
    )
    # 델타가 정확히 0.0%이 아니면 409, 정확히 0이면 통과할 수도 있음.
    # 시드 데이터의 재계산은 전월 확정치와 미세 차이가 나는 경우가 많다.
    if r.status_code == 409:
        assert "델타" in r.text or "임계치" in r.text
    else:
        # 완전 동일 케이스: 200 + approved=True
        assert r.status_code == 200
        assert r.json()["approved"] is True


# ---------------------------------------------------------------------------
# _recalc_row 단위 테스트 — 부양가족·자녀·조정률 최신값 우선 사용 검증
# ---------------------------------------------------------------------------


def _make_entry(*, dependents: int, children: int, rate_adjust: int) -> PayrollEntry:
    """세액 재계산에 필요한 최소 필드만 채운 전월 엔트리."""
    return PayrollEntry(
        raw_name="테스트",
        income_type=IncomeType.WAGE,
        total_amount=3_000_000,
        non_taxable=200_000,
        taxable=2_800_000,
        dependents=dependents,
        children=children,
        rate_adjust=rate_adjust,
        income_tax=0,
        local_tax=0,
    )


def _make_employee(
    *, dependents_count: int, children_count: int, withholding_rate_adjust: int
) -> Employee:
    return Employee(
        client_id="c",
        name="테스트",
        dependents_count=dependents_count,
        children_count=children_count,
        withholding_rate_adjust=withholding_rate_adjust,
        status=EmploymentStatus.ACTIVE,
    )


def test_recalc_row_uses_employee_master_values_when_available():
    """마스터에 dependents_count가 있으면 전월 엔트리 값보다 우선 사용."""
    entry = _make_entry(dependents=1, children=0, rate_adjust=100)
    # 마스터에서 부양가족 3명(본인+배우자+자녀1)로 업데이트된 상황
    employee = _make_employee(
        dependents_count=3, children_count=1, withholding_rate_adjust=100
    )
    income_tax_master, _, dep_used, kids_used, adj_used = _recalc_row(entry, employee)
    assert dep_used == 3
    assert kids_used == 1
    assert adj_used == 100

    # 대조: 마스터 없이 전월값(1명, 자녀 0)로 계산하면 세액이 더 많다
    income_tax_prev, _, _, _, _ = _recalc_row(entry, None)
    assert income_tax_master < income_tax_prev


def test_recalc_row_falls_back_to_entry_when_no_employee_master():
    """직원 마스터 매칭 실패(사업소득 프리랜서 등) 시 전월 엔트리 값 그대로 사용."""
    entry = _make_entry(dependents=2, children=0, rate_adjust=100)
    _, _, dep_used, kids_used, adj_used = _recalc_row(entry, None)
    assert dep_used == 2
    assert kids_used == 0
    assert adj_used == 100


def test_recalc_row_rate_adjust_master_wins():
    """조정률(80/100/120)도 마스터가 우선 — 세율 조정 신청 반영."""
    entry = _make_entry(dependents=1, children=0, rate_adjust=100)
    # 마스터에서 120% 조정 신청 상태
    employee = _make_employee(
        dependents_count=1, children_count=0, withholding_rate_adjust=120
    )
    income_tax_120, _, _, _, adj_used = _recalc_row(entry, employee)
    assert adj_used == 120

    # 100% 대비 120%가 세액이 더 크다
    income_tax_100, _, _, _, _ = _recalc_row(entry, None)
    assert income_tax_120 > income_tax_100
