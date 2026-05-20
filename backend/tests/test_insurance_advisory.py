"""산재·고용보험 어드바이저 테스트 (in-memory, no DB)."""

from datetime import date
from types import SimpleNamespace

from app.models.payroll import IncomeType, MatchStatus
from app.services.insurance_advisory import build_advisory


def _emp(name, hired=None, resigned=None):
    return SimpleNamespace(id="e_" + name, name=name, hired_at=hired, resigned_at=resigned)


def _entry(name, total, *, match=MatchStatus.MATCHED, prev=None,
           income_type=IncomeType.WAGE, emp=None):
    return SimpleNamespace(
        id="p_" + name,
        raw_name=name,
        employee=emp if emp is not None else _emp(name),
        income_type=income_type,
        total_amount=total,
        match_status=match,
        prev_amount=prev,
    )


TODAY = date(2026, 5, 16)  # 귀속월 2026-04 기준 다음달 15일 = 2026-05-15 (지연)


def test_deadline_alerts_and_dday():
    entries = [
        _entry("김신규", 2_500_000, match=MatchStatus.NEW_HIRE_SUSPECTED),
        _entry("이퇴사", 3_000_000, match=MatchStatus.RESIGNATION_SUSPECTED),
    ]
    adv = build_advisory(entries, "2026-04", "테스트상사", today=TODAY)

    titles = [a["title"] for a in adv["alerts"]]
    assert any("자격취득" in t for t in titles)
    assert any("자격상실" in t for t in titles)
    # 다음달 15일 = 2026-05-15, today 2026-05-16 → D+1 지연 → danger 정렬 최상단
    acq = next(a for a in adv["alerts"] if "자격취득" in a["title"])
    assert acq["due"] == "2026-05-15"
    assert acq["d_day"] == -1
    assert acq["severity"] == "danger"
    assert adv["alerts"][0]["severity"] == "danger"  # 긴급순 정렬


def test_durunuri_candidates_only_low_pay_new_hires():
    entries = [
        _entry("저보수신규", 2_000_000, match=MatchStatus.NEW_HIRE_SUSPECTED),
        _entry("고보수신규", 3_500_000, match=MatchStatus.NEW_HIRE_SUSPECTED),
        _entry("기존직원", 2_100_000),
    ]
    adv = build_advisory(entries, "2026-04", "소상공인", today=TODAY)
    cand = adv["durunuri"]["candidates"]
    assert [c["name"] for c in cand] == ["저보수신규"]
    # 200만 × 1.8% × 80% = 28,800 (상한 37,720 미만)
    assert cand[0]["est_support"] == 28_800
    assert adv["durunuri"]["eligible_size"] is True  # wage 3명 < 10


def test_durunuri_size_limit_excludes_large_client():
    entries = [
        _entry(f"직원{i}", 2_000_000) for i in range(10)
    ] + [_entry("신규저보수", 2_000_000, match=MatchStatus.NEW_HIRE_SUSPECTED)]
    adv = build_advisory(entries, "2026-04", "중견기업", today=TODAY)
    assert adv["durunuri"]["eligible_size"] is False
    assert "10인 이상" in adv["durunuri"]["note"]


def test_daily_and_business_triggers():
    entries = [
        _entry("일용A", 150_000, income_type=IncomeType.DAILY),
        _entry("프리랜서B", 2_000_000, income_type=IncomeType.BUSINESS),
    ]
    adv = build_advisory(entries, "2026-04", "노무제공처", today=TODAY)
    trigs = " ".join(t["trigger"] for t in adv["triggers"])
    assert "일용직" in trigs
    assert "사업소득" in trigs
    assert adv["summary"]["daily"] == 1
    assert adv["summary"]["business"] == 1
    # 노무제공자 알림은 다음달 말일(2026-05-31) 기한
    biz = next(a for a in adv["alerts"] if "노무제공자" in a["title"])
    assert biz["due"] == "2026-05-31"


def test_reference_knowledge_present_with_citations():
    adv = build_advisory([], "2026-04", "빈거래처", today=TODAY)
    ref = adv["reference"]
    assert "근로복지공단" in ref["source"]
    assert ref["deadlines"] and all("basis" in d for d in ref["deadlines"])
    assert any("출퇴근재해" in x["value"] for x in ref["rates_2026"])
    assert ref["durunuri"]["basis"].startswith("p.")
    # 데이터가 없어도 연도정산 안내는 항상 노출
    assert any("연도정산" in a["title"] for a in adv["alerts"])
