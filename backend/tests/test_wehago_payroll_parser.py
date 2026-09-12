"""위하고T 22컬럼 급여대장 결정론적 파서 테스트.

LLM 컬럼 매핑 오류로 4대보험 값이 뒤엉키는 문제((주)창원 2026-08 사건)를 해결하기 위해
추가된 파서. 시그니처 매치 시 결정론적으로 파싱, 아니면 None 반환.
"""

from io import BytesIO

from openpyxl import Workbook

from app.models.payroll import IncomeType, MatchStatus
from app.services.matching import EmployeeMaster, reconcile_wehago
from app.services.wehago_payroll_parser import (
    WehagoPayrollRow,
    parse_wehago_workbook,
)


_ITEM_HEADERS = [
    "기본급", "상여", "식대", "자가운전", "육아", "지급액계",
    "국민연금", "건강보험", "고용보험", "장기요양보험료",
    "소득세", "지방소득세", "학자금상환액", "정산보험료", "월세지원금", "공제액계",
]


def _wehago_bytes(data_rows: list[list]) -> bytes:
    """위하고T 22컬럼 실측 헤더를 그대로 재현한 xlsx 를 만든다."""
    wb = Workbook()
    ws = wb.active
    ws.title = "테스트"

    # 1행: 그룹 헤더 (병합은 검사에 영향 없음 — 값만 있으면 됨)
    ws.cell(1, 1, "사원코드")
    ws.cell(1, 2, "사원명")
    ws.cell(1, 3, "부서")
    ws.cell(1, 4, "직급")
    ws.cell(1, 5, "직종")
    ws.cell(1, 6, "수당")
    ws.cell(1, 12, "공제")
    ws.cell(1, 22, "차인지급액")

    # 2행: 세부 항목
    for offset, header in enumerate(_ITEM_HEADERS):
        ws.cell(2, 6 + offset, header)

    for r in data_rows:
        ws.append(r)

    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_parses_valid_wehago_workbook():
    blob = _wehago_bytes([
        # 사원코드, 사원명, 부서, 직급, 직종,
        # 기본급, 상여, 식대, 자가운전, 육아, 지급액계,
        # 국민연금, 건강보험, 고용보험, 장기요양, 소득세, 지방소득세,
        # 학자금, 정산보험료, 월세지원금, 공제액계, 차인지급액
        ["1", "백재봉", "", "대표이사", "",
         2_100_000, 0, 200_000, 200_000, 0, 2_500_000,
         91_440, 74_440, 0, 9_640, 22_740, 2_270,
         0, 0, 0, 200_530, 2_299_470],
        ["2", "김연호", "", "과장", "",
         2_300_000, 0, 200_000, 0, 0, 2_500_000,
         99_000, 81_530, 20_700, 10_550, 9_660, 960,
         0, 0, 0, 222_400, 2_277_600],
    ])
    rows = parse_wehago_workbook(blob)
    assert rows is not None
    assert len(rows) == 2
    assert rows[0].name == "백재봉"
    assert rows[0].national_pension == 91_440
    assert rows[0].health_insurance == 74_440
    assert rows[0].employment_insurance == 0
    assert rows[0].longterm_care == 9_640
    assert rows[0].income_tax == 22_740
    assert rows[0].local_tax == 2_270
    assert rows[0].total_amount == 2_500_000
    # 두 번째 행도 값이 원본대로 (컬럼 시프트 없음) 유지되는지 확인
    assert rows[1].name == "김연호"
    assert rows[1].national_pension == 99_000
    assert rows[1].health_insurance == 81_530
    assert rows[1].employment_insurance == 20_700
    assert rows[1].longterm_care == 10_550


def test_skips_sum_row():
    blob = _wehago_bytes([
        ["1", "백재봉", "", "대표이사", "",
         2_100_000, 0, 0, 0, 0, 2_100_000,
         91_440, 74_440, 0, 9_640, 22_740, 2_270,
         0, 0, 0, 200_530, 1_899_470],
        # 합계 행 — 스킵되어야 함
        ["합계", "", "", "", "",
         2_100_000, 0, 0, 0, 0, 2_100_000,
         91_440, 74_440, 0, 9_640, 22_740, 2_270,
         0, 0, 0, 200_530, 1_899_470],
    ])
    rows = parse_wehago_workbook(blob)
    assert rows is not None
    assert len(rows) == 1
    assert rows[0].name == "백재봉"


def test_returns_none_for_non_wehago_workbook():
    wb = Workbook()
    ws = wb.active
    ws.append(["성명", "지급액"])
    ws.append(["김연호", 1_000_000])
    buf = BytesIO()
    wb.save(buf)
    assert parse_wehago_workbook(buf.getvalue()) is None


def _build_workbook_with_altered_header(index: int, replacement: str) -> bytes:
    """지정된 2행 헤더 항목만 다른 값으로 대체한 위하고T 스키마 xlsx 를 만든다."""
    wb = Workbook()
    ws = wb.active
    ws.cell(1, 1, "사원코드")
    ws.cell(1, 2, "사원명")
    ws.cell(1, 3, "부서")
    ws.cell(1, 4, "직급")
    ws.cell(1, 5, "직종")
    ws.cell(1, 6, "수당")
    ws.cell(1, 12, "공제")
    ws.cell(1, 22, "차인지급액")
    headers = list(_ITEM_HEADERS)
    headers[index] = replacement
    for offset, h in enumerate(headers):
        ws.cell(2, 6 + offset, h)
    # 데이터 행 1개 — 시그니처 통과와 데이터 유무를 구분하기 위함
    ws.append(["1", "홍길동", "", "", "",
               2_000_000, 0, 0, 0, 0, 2_000_000,
               90_000, 70_000, 18_000, 9_000, 20_000, 2_000,
               0, 0, 0, 200_000, 1_800_000])
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_accepts_extended_header_prefix():
    """접두 매칭 관용성: '국민연금료' 처럼 접미가 붙어도 국민연금 열로 인식."""
    blob = _build_workbook_with_altered_header(index=6, replacement="국민연금료")
    rows = parse_wehago_workbook(blob)
    assert rows is not None
    assert rows[0].national_pension == 90_000


def test_returns_none_when_header_is_wildly_different():
    """헤더가 실질적으로 다른 스키마면 폴백 신호로 None."""
    blob = _build_workbook_with_altered_header(index=6, replacement="완전히다른항목")
    assert parse_wehago_workbook(blob) is None


def test_handles_comma_formatted_integers():
    """실측 파일에서 합계 행은 '15,700,000' 처럼 문자열로 저장되기도 한다."""
    blob = _wehago_bytes([
        ["1", "백재봉", "", "대표이사", "",
         "2,100,000", 0, 200_000, 200_000, 0, "2,500,000",
         "91,440", "74,440", 0, 9_640, 22_740, 2_270,
         0, 0, 0, 200_530, 2_299_470],
    ])
    rows = parse_wehago_workbook(blob)
    assert rows is not None
    assert rows[0].total_amount == 2_500_000
    assert rows[0].national_pension == 91_440


# ── reconcile_wehago ───────────────────────────────────────────────────────


def _row(name, code="1", amount=2_500_000, np=91_440, hi=74_440, ei=18_900, ltc=9_640):
    return WehagoPayrollRow(
        employee_code=code, name=name,
        department="", position="", job_type="",
        base_salary=amount - 400_000, bonus=0, meal_amount=200_000,
        car_amount=200_000, childcare_amount=0, total_amount=amount,
        national_pension=np, health_insurance=hi,
        employment_insurance=ei, longterm_care=ltc,
        income_tax=22_740, local_tax=2_270,
        student_loan=0, settlement_insurance=0, rent_support=0,
        deduction_total=0, net_payment=0,
    )


def test_reconcile_wehago_preserves_insurance_values():
    """LLM 우회 경로에서는 원본 4대보험 값이 그대로 candidate 에 남아야 한다."""
    row = _row("백재봉", code="1")
    result = reconcile_wehago(
        [row],
        master=[EmployeeMaster(id="e1", name="백재봉", employee_code="1")],
        previous_month={"e1": 2_500_000},
    )
    assert len(result.entries) == 1
    c = result.entries[0]
    assert c.employee_id == "e1"
    assert c.match_status == MatchStatus.MATCHED
    assert c.income_type == IncomeType.WAGE
    assert c.national_pension == 91_440
    assert c.health_insurance == 74_440
    assert c.employment_insurance == 18_900
    assert c.longterm_care == 9_640
    # non_taxable 은 3개 비과세 항목 합
    assert c.non_taxable == 400_000


def test_reconcile_wehago_marks_unmatched_as_new_hire():
    row = _row("최은영", code="99")
    result = reconcile_wehago(
        [row],
        master=[EmployeeMaster(id="e1", name="백재봉", employee_code="1")],
        previous_month={"e1": 2_500_000},
    )
    # 매치 실패 → NEW_HIRE_SUSPECTED
    entries_by_name = {e.raw_name: e for e in result.entries}
    assert entries_by_name["최은영"].match_status == MatchStatus.NEW_HIRE_SUSPECTED
    assert entries_by_name["최은영"].employee_id is None
    # 마스터의 백재봉은 이번 달 언급 안 됨 → UNCONFIRMED
    assert entries_by_name["백재봉"].match_status == MatchStatus.UNCONFIRMED
    assert entries_by_name["백재봉"].total_amount == 0


def test_reconcile_wehago_zero_insurance_stays_zero():
    """대표이사처럼 국민연금·고용보험이 0으로 명시된 케이스가 0으로 보존돼야 한다.

    reconcile() 는 None → 거래처 defaults 로 채우지만, 위하고T 경로는 0을 그대로 보존.
    """
    row = _row("대표", code="1", np=0, ei=0)
    result = reconcile_wehago(
        [row],
        master=[EmployeeMaster(id="e1", name="대표", employee_code="1")],
        previous_month={},
    )
    c = result.entries[0]
    assert c.national_pension == 0
    assert c.employment_insurance == 0
