"""SmartA 사업소득자료입력 .xls 생성기 테스트 (in-memory, no DB).

기준 서식: saup_excel.xls — A열 일련번호 + 14개 항목, IV열(255) 소득구분 40종.
"""

from datetime import date
from types import SimpleNamespace

from app.models.business_type import BUSINESS_TYPE_CODES
from app.services.smarta_business_xls import (
    CODE_TO_INCOME_TYPE,
    COLUMNS,
    INCOME_TYPE_LIST,
    _yyyymm,
    _yyyymmdd,
    generate_smarta_business_xls,
)

# OLE2 Compound Document 매직 — 진짜 BIFF(.xls)인지 확인용
_OLE2_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"


def _entry(name, *, code="940903", total=1_000_000, income_tax=30_000, local_tax=3_000):
    return SimpleNamespace(
        employee=SimpleNamespace(
            name=name, rrn_encrypted=None, business_type_code=None
        ),
        business_type_code=code,
        payment_date=date(2025, 11, 25),
        total_amount=total,
        income_tax=income_tax,
        local_tax=local_tax,
    )


def test_columns_match_smarta_template():
    assert COLUMNS == [
        "귀속년월", "지급년월일", "소득자명", "주민등록번호",
        "기본주소", "상세주소", "소득구분", "영수일자",
        "지급총액", "세율(%)", "소득세", "지방소득세",
        "내.외국인구분", "연말정산",
    ]


def test_income_type_list_has_40_unique_labels():
    assert len(INCOME_TYPE_LIST) == 40
    assert len(set(INCOME_TYPE_LIST)) == 40


def test_every_business_type_code_maps_to_a_template_label():
    """업종코드 마스터와 SmartA 소득구분이 1:1로 대응해야 한다."""
    master_codes = {code for code, _n, _d, _r in BUSINESS_TYPE_CODES}

    assert set(CODE_TO_INCOME_TYPE) == master_codes
    assert set(CODE_TO_INCOME_TYPE.values()) == set(INCOME_TYPE_LIST)


def test_period_and_date_formatting():
    assert _yyyymm("2025-11") == "202511"
    assert _yyyymmdd(date(2025, 11, 25)) == "20251125"
    assert _yyyymmdd(None) == ""


def test_generates_real_xls_binary():
    blob = generate_smarta_business_xls([_entry("김프리")], period="2025-11")

    assert blob.startswith(_OLE2_MAGIC)


def test_entry_without_employee_is_skipped():
    orphan = _entry("무매칭")
    orphan.employee = None

    blob = generate_smarta_business_xls([orphan], period="2025-11")

    assert blob.startswith(_OLE2_MAGIC)


def test_unknown_business_code_falls_back_to_기타인적용역자():
    entry = _entry("김프리", code="999999")

    # 매핑에 없는 코드는 기본값으로 떨어져야 하며 예외를 내지 않는다
    assert generate_smarta_business_xls([entry], period="2025-11").startswith(_OLE2_MAGIC)
    assert CODE_TO_INCOME_TYPE["940909"] == "기타인적용역자"


def test_봉사료수취자_uses_5_percent_rate():
    rates = {code: rate for code, _n, _d, rate in BUSINESS_TYPE_CODES}

    assert rates["940905"] == 5
    assert rates["940903"] == 3
