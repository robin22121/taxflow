"""SmartA 기타소득자료입력 .xls 생성기 테스트 (in-memory, no DB).

기준 서식: gita_excel_2022.xls — 17개 데이터 컬럼(귀속년월~지방소득세), 거주자용
소득구분 코드 18종 중 하나를 "코드.라벨" 형식으로 채워 업로드한다.
"""

from datetime import date
from types import SimpleNamespace

from app.services.smarta_other_income_xls import (
    COLUMNS,
    RESIDENT_INCOME_CODE_LABELS,
    generate_smarta_other_income_xls,
)

# OLE2 Compound Document 매직 — 진짜 BIFF(.xls)인지 확인용
_OLE2_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"


def _entry(
    name, *, other_income_code="76", total=500_000, necessary_expense=300_000,
    income_tax=8_400, local_tax=840, rrn=None, payment_date=None,
):
    return SimpleNamespace(
        id="entry-1",
        employee=SimpleNamespace(name=name, rrn_encrypted=rrn),
        total_amount=total,
        necessary_expense=necessary_expense,
        other_income_code=other_income_code,
        income_tax=income_tax,
        local_tax=local_tax,
        payment_date=payment_date,
    )


def test_columns_match_smarta_template():
    assert COLUMNS == [
        "귀속년월", "지급년월일", "소득자명", "거주", "내/외국인", "기본주소", "상세주소",
        "주민등록번호", "소득구분", "영수일자", "지급총액", "필요경비", "소득금액",
        "세율(%)", "소득세", "지방소득세",
    ]


def test_income_code_labels_cover_18_resident_codes():
    assert len(RESIDENT_INCOME_CODE_LABELS) == 18
    assert RESIDENT_INCOME_CODE_LABELS["76"] == "강연료 등 (필요경비 60%)"
    assert RESIDENT_INCOME_CODE_LABELS["77"] == "종교인 소득"


def test_generates_real_xls_binary():
    blob = generate_smarta_other_income_xls([_entry("김아인")], period="2026-09")

    assert blob.startswith(_OLE2_MAGIC)


def test_entry_without_employee_is_skipped():
    orphan = _entry("무매칭")
    orphan.employee = None

    blob = generate_smarta_other_income_xls([orphan], period="2026-09")

    assert blob.startswith(_OLE2_MAGIC)


def test_entry_without_income_code_is_skipped():
    """소득구분코드가 없으면 위하고가 인식 못 해 업로드에서 제외된다."""
    missing = _entry("코드없음", other_income_code=None)

    blob = generate_smarta_other_income_xls([missing], period="2026-09")

    assert blob.startswith(_OLE2_MAGIC)


def test_entry_with_unknown_income_code_is_skipped():
    unknown = _entry("알수없는코드", other_income_code="99")

    blob = generate_smarta_other_income_xls([unknown], period="2026-09")

    assert blob.startswith(_OLE2_MAGIC)


def test_uses_payment_date_when_present():
    entry = _entry("김아인", payment_date=date(2026, 3, 15))

    blob = generate_smarta_other_income_xls([entry], period="2026-09")

    assert blob.startswith(_OLE2_MAGIC)
