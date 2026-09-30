"""SmartA 일용직급여자료입력 .xls 생성기 테스트 (in-memory, no DB).

기준 서식: ilyongjig_excel_2022.xls — 2행 헤더(근무시간·지급액이 정상/연장으로 나뉨),
"만근공수"(일자=99) 방식으로 이지원천의 월 합계 1건을 한 줄로 업로드한다.
"""

from types import SimpleNamespace

from app.services.smarta_daily_xls import (
    COLUMNS_ROW1,
    COLUMNS_ROW2,
    generate_smarta_daily_xls,
)

# OLE2 Compound Document 매직 — 진짜 BIFF(.xls)인지 확인용
_OLE2_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"


def _entry(name, *, work_days=10, total=1_500_000, income_tax=40_500, local_tax=4_050, rrn=None):
    return SimpleNamespace(
        id="entry-1",
        employee=SimpleNamespace(name=name, rrn_encrypted=rrn),
        total_amount=total,
        work_days=work_days,
        non_taxable=0,
        employment_insurance=0,
        national_pension=0,
        health_insurance=0,
        longterm_care=0,
        income_tax=income_tax,
        local_tax=local_tax,
    )


def test_columns_match_smarta_template():
    assert COLUMNS_ROW1 == [
        "일자", "근무\n여부", "사원명", "주민등록번호", "현장(코드)", "공수",
        "근무시간", "", "지급액", "", "기타비과세", "고용보험", "국민연금",
        "건강보험", "장기요양보험", "소득세", "지방소득세",
    ]
    assert COLUMNS_ROW2 == ["", "", "", "", "", "", "정상", "연장", "정상", "연장", "", "", "", "", "", "", ""]


def test_generates_real_xls_binary():
    blob = generate_smarta_daily_xls([_entry("김일용")], period="2026-09")

    assert blob.startswith(_OLE2_MAGIC)


def test_entry_without_employee_is_skipped():
    orphan = _entry("무매칭")
    orphan.employee = None

    blob = generate_smarta_daily_xls([orphan], period="2026-09")

    assert blob.startswith(_OLE2_MAGIC)


def test_entry_without_work_days_is_skipped():
    """공수(근로일수)가 없으면 만근공수 필수 입력 규칙을 못 채워 업로드에서 제외된다."""
    missing = _entry("공수없음", work_days=None)

    blob = generate_smarta_daily_xls([missing], period="2026-09")

    assert blob.startswith(_OLE2_MAGIC)
