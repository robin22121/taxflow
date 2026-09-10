"""원시자료 우선 규칙 — 비과세 수당과 4대보험.

실제 사고: 급여대장에 육아수당이 0인데 거래처 기본값 20만원이 자동으로 붙어
기본급까지 20만원 깎였다. "항목 없음(None)"과 "0원이라고 적힘(0)"을 구분한다.
"""

from __future__ import annotations

from app.api.collect import _computed_fields
from app.models.payroll import IncomeType
from app.services.matching import PayrollEntryCandidate
from app.services.payroll_defaults import ResolvedPayrollDefaults


def _defaults() -> ResolvedPayrollDefaults:
    """시스템 기본 세팅 — 식대 20만, 자가운전 20만, 육아 0."""
    return ResolvedPayrollDefaults()


def test_system_defaults_match_db_column_defaults():
    """설정 행이 없을 때 쓰는 fallback이 DB 컬럼 기본값과 어긋나면 안 된다."""
    from app.models.client_payroll_default import ClientPayrollDefault

    d = ResolvedPayrollDefaults()
    columns = ClientPayrollDefault.__table__.columns
    assert (d.meal_default, d.car_default, d.childcare_default) == (200_000, 200_000, 0)
    assert columns["meal_default"].default.arg == d.meal_default
    assert columns["car_default"].default.arg == d.car_default
    assert columns["childcare_default"].default.arg == d.childcare_default


def _cand(**kwargs) -> PayrollEntryCandidate:
    base = dict(
        raw_name="백재봉",
        employee_id="e1",
        income_type=IncomeType.WAGE,
        total_amount=2_500_000,
    )
    base.update(kwargs)
    return PayrollEntryCandidate(**base)


# ── 비과세 수당 ────────────────────────────────────────────


def test_zero_in_source_stays_zero():
    """급여대장에 육아 0으로 적혀 있으면 기본값을 얹지 않는다."""
    fields, _tax, _si = _computed_fields(
        _cand(meal_amount=200_000, car_amount=200_000, childcare_amount=0),
        _client(), _defaults(), None,
    )
    assert fields["childcare_amount"] == 0
    assert fields["non_taxable"] == 400_000
    # 기본급 왜곡이 없어야 한다 (총액 250만 - 비과세 40만)
    assert fields["taxable"] == 2_100_000


def test_missing_item_falls_back_to_client_default():
    """카톡처럼 비과세 언급이 아예 없으면(None) 거래처 기본값을 쓴다.

    육아수당 기본값은 0이므로 자동으로 붙지 않는다.
    """
    fields, _tax, _si = _computed_fields(_cand(), _client(), _defaults(), None)
    assert fields["meal_amount"] == 200_000
    assert fields["car_amount"] == 200_000
    assert fields["childcare_amount"] == 0
    assert fields["non_taxable"] == 400_000


def test_partial_source_only_fills_missing_items():
    fields, _tax, _si = _computed_fields(
        _cand(meal_amount=100_000), _client(), _defaults(), None,
    )
    assert fields["meal_amount"] == 100_000       # 원시자료 값
    assert fields["car_amount"] == 200_000        # 언급 없음 → 기본값
    assert fields["childcare_amount"] == 0        # 언급 없음 → 기본값 0


# ── 4대보험 ────────────────────────────────────────────────


def test_source_social_insurance_wins():
    """회사가 이미 적용한 공제액이 있으면 재계산하지 않는다."""
    fields, _tax, _si = _computed_fields(
        _cand(
            meal_amount=200_000, car_amount=200_000, childcare_amount=0,
            national_pension=91_440, health_insurance=74_440,
            employment_insurance=0, longterm_care=9_640,
        ),
        _client(), _defaults(), None,
    )
    assert fields["national_pension"] == 91_440
    assert fields["health_insurance"] == 74_440
    assert fields["employment_insurance"] == 0   # 대표이사 적용 제외
    assert fields["longterm_care"] == 9_640


def test_missing_social_insurance_is_computed():
    fields, _tax, _si = _computed_fields(
        _cand(meal_amount=200_000, car_amount=200_000, childcare_amount=0),
        _client(), _defaults(), None,
    )
    # 과세 2,100,000 × 4.5%
    assert fields["national_pension"] == 94_500
    assert fields["employment_insurance"] > 0


def test_partially_supplied_social_insurance():
    """고용보험만 0으로 적혀 있으면 그것만 존중하고 나머지는 계산한다."""
    fields, _tax, _si = _computed_fields(
        _cand(meal_amount=200_000, car_amount=200_000, childcare_amount=0,
              employment_insurance=0),
        _client(), _defaults(), None,
    )
    assert fields["employment_insurance"] == 0
    assert fields["national_pension"] == 94_500


def _client():
    class _C:
        is_corporation = True
    return _C()
