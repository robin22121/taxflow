"""SmartA 기타소득자료입력 .xlsx 생성기 테스트 (in-memory, no DB).

기준 서식: gita_excel_2022.xlsx — 17개 데이터 컬럼(귀속년월~지방소득세), 거주자용
소득구분 코드 18종 중 하나를 "코드.라벨" 형식으로 채워 업로드한다.

2026-10-01: xlwt(.xls)에서 openpyxl(.xlsx)로 전환 — 사용자가 직접 타이핑해 업로드
성공한 파일을 분석해, 주민등록번호를 정수+커스텀서식("000000-0000000")으로 쓰고
거주/내국인에 "0." 접두사를 붙이지 않아야 한다는 걸 확인했다(smarta_other_income_xls.py
모듈 docstring 참고).
"""

from datetime import date
from io import BytesIO
from types import SimpleNamespace

from openpyxl import load_workbook

from app.services.crypto import encrypt_rrn
from app.services.smarta_other_income_xls import (
    COLUMNS,
    RESIDENT_INCOME_CODE_LABELS,
    generate_smarta_other_income_xls,
)


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


def _load(blob: bytes):
    return load_workbook(BytesIO(blob))["Sheet1"]


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


def test_rrn_written_as_integer_with_custom_format_not_text():
    """2026-10-01 실기: 문자열/BIFF 조합은 전부 업로드 실패, 정수+커스텀숫자서식만 성공."""
    ws = _load(generate_smarta_other_income_xls(
        [_entry("김아인", rrn=encrypt_rrn("9001011234567"), payment_date=date(2026, 9, 26))],
        period="2026-09",
    ))
    cell = ws.cell(row=4, column=9)

    assert cell.value == 9001011234567
    assert isinstance(cell.value, int)
    assert cell.number_format == r"000000\-0000000"


def test_residency_and_nationality_have_no_numeric_prefix():
    """성공한 업로드 파일은 "거주"/"내국인"이지 "0.거주"/"0.내국인"이 아니었다."""
    ws = _load(generate_smarta_other_income_xls([_entry("김아인")], period="2026-09"))

    assert ws.cell(row=4, column=5).value == "거주"
    assert ws.cell(row=4, column=6).value == "내국인"


def test_income_code_keeps_numeric_prefix():
    """소득구분(J열)만 "코드.라벨" 접두사 규칙이 적용된다 — 드롭다운 목록과 일치."""
    ws = _load(generate_smarta_other_income_xls([_entry("김아인", other_income_code="79")], period="2026-09"))

    assert ws.cell(row=4, column=10).value == "79.자문료 등 (필요경비 60%)"


def test_entry_without_employee_is_skipped():
    orphan = _entry("무매칭")
    orphan.employee = None

    ws = _load(generate_smarta_other_income_xls([orphan], period="2026-09"))

    assert ws.cell(row=4, column=4).value is None


def test_entry_without_income_code_is_skipped():
    """소득구분코드가 없으면 위하고가 인식 못 해 업로드에서 제외된다."""
    missing = _entry("코드없음", other_income_code=None)

    ws = _load(generate_smarta_other_income_xls([missing], period="2026-09"))

    assert ws.cell(row=4, column=4).value is None


def test_entry_with_unknown_income_code_is_skipped():
    unknown = _entry("알수없는코드", other_income_code="99")

    ws = _load(generate_smarta_other_income_xls([unknown], period="2026-09"))

    assert ws.cell(row=4, column=4).value is None


def test_uses_payment_date_when_present():
    entry = _entry("김아인", payment_date=date(2026, 3, 15))

    ws = _load(generate_smarta_other_income_xls([entry], period="2026-09"))

    assert ws.cell(row=4, column=2).value == "2026.03"
    assert ws.cell(row=4, column=3).value == "2026.03.15"
