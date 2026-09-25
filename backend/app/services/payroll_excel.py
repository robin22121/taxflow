"""급여대장 엑셀 생성 — 위하고T 업로드용 실측 양식.

양식 참조: (임시)주식회사 동문-202511.xlsx (위하고T 업로드 실사용 원본)
  Row 1: 사원코드 | 사원명 | 부서 | 직급 | 직종 | 수당(merged F~K) | 공제(merged L~U) | 차인지급액
  Row 2:                                     | 기본급 | 상여 | 식대 | 자가운전 | 육아수당 | 지급액계
                                              | 국민연금 | 건강보험 | 고용보험 | 장기요양보험료
                                              | 소득세 | 지방소득세 | 학자금상환액
                                              | 정산보험료 | 월세지원금 | 공제액계
  Row 3~: data rows

합계행은 넣지 않는다 — 위하고T [엑셀 불러오기]가 A열 "합계"를 사원코드로 읽어
사원코드연결 팝업에 미연결 사원으로 띄운다 (2026-09-23 서도 실측).
사원코드는 위하고 사원코드여야 한다 — 위하고가 이 코드로 사원을 연결하므로,
코드가 없는 사원을 순번 등으로 채우면 다른 사원에게 급여가 들어갈 수 있다.

"""

from __future__ import annotations

from io import BytesIO
from typing import Iterable

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from app.models.payroll import PayrollEntry
from app.services.tax_calc import calculate_withholding_tax


class PayrollExcelError(ValueError):
    pass


# ── styles (원본 실측: 맑은 고딕 9pt, 행높이 21, 열너비 14) ──
_HEADER_FONT = Font(name="맑은 고딕", size=9, bold=True)
_DATA_FONT = Font(name="맑은 고딕", size=9)
_GROUP_FILL = PatternFill("solid", fgColor="FFFF99")   # 1행 그룹 헤더
_SUB_FILL = PatternFill("solid", fgColor="99CCFF")     # 2행 항목 헤더
_CENTER = Alignment(horizontal="center", vertical="center")
_LEFT = Alignment(horizontal="left", vertical="center")
_RIGHT = Alignment(horizontal="right", vertical="center")
_THIN_BORDER = Border(
    left=Side(style="thin", color="B3B3B3"),
    right=Side(style="thin", color="B3B3B3"),
    top=Side(style="thin", color="B3B3B3"),
    bottom=Side(style="thin", color="B3B3B3"),
)
_NUM_FMT = "#,##0"
_TEXT_FMT = "@"

# Column mapping (1-indexed) — 위하고T 실측 22컬럼
# A=사원코드 B=사원명 C=부서 D=직급 E=직종
# F=기본급 G=상여 H=식대 I=자가운전 J=육아수당 K=지급액계
# J열은 원본 양식의 "육아"를 실무에서 위하고에 가장 흔히 등록하는 이름 "육아수당"(비과세 Q02)으로 바꿨다 —
# 위하고 엑셀업로드는 제목과 같은 이름의 수당만 자동 연결한다 (plan/23 §5-2, 2026-09-25)
# L=국민연금 M=건강보험 N=고용보험 O=장기요양보험료
# P=소득세 Q=지방소득세 R=학자금상환액 S=정산보험료 T=월세지원금 U=공제액계
# V=차인지급액

COL_COUNT = 22
_INFO_COL_COUNT = 5          # A~E: 텍스트 컬럼
_ALLOWANCE_LAST_COL = 11     # K: 지급액계
_DEDUCTION_LAST_COL = 21     # U: 공제액계

#: 2행 항목 헤더 (F열부터 V열까지 순서대로)
ITEM_HEADERS: list[str] = [
    "기본급", "상여", "식대", "자가운전", "육아수당", "지급액계",
    "국민연금", "건강보험", "고용보험", "장기요양보험료",
    "소득세", "지방소득세", "학자금상환액", "정산보험료", "월세지원금", "공제액계",
]


def _ensure_taxes(entry: PayrollEntry) -> tuple[int, int]:
    if entry.income_tax is not None and entry.local_tax is not None:
        return entry.income_tax, entry.local_tax
    tax = calculate_withholding_tax(
        income_type=entry.income_type,
        taxable_amount=entry.taxable or (entry.total_amount - entry.non_taxable),
        dependents=entry.dependents or 1,
    )
    return tax.income_tax, tax.local_tax


def payroll_breakdown(entry: PayrollEntry) -> dict[str, int]:
    """PayrollEntry를 위하고T 급여대장 항목으로 분해한다.

    급여대장 엑셀·급여명세서·대시보드가 같은 값을 보이도록 이 함수 하나만 쓴다.
    """
    income_tax, local_tax = _ensure_taxes(entry)

    bonus = entry.bonus_amount or 0
    meal = entry.meal_amount or 0
    car = entry.car_amount or 0
    childcare = entry.childcare_amount or 0

    # 기본급 = 총지급액 - 상여 - 비과세수당 (상여·비과세는 총지급액에 이미 포함)
    base_salary = max(entry.total_amount - bonus - meal - car - childcare, 0)

    national_pension = entry.national_pension or 0
    health_insurance = entry.health_insurance or 0
    employment_insurance = entry.employment_insurance or 0
    longterm_care = entry.longterm_care or 0
    student_loan = entry.student_loan or 0
    settlement_insurance = entry.settlement_insurance or 0
    rent_support = entry.rent_support or 0

    deduction_total = (
        national_pension + health_insurance + employment_insurance + longterm_care
        + income_tax + local_tax + student_loan + settlement_insurance + rent_support
    )
    # 총지급액은 언제나 total_amount (상여·비과세는 그 내부 분해이므로 재가산 금지)
    gross = entry.total_amount

    return {
        "기본급": base_salary,
        "상여": bonus,
        "식대": meal,
        "자가운전": car,
        "육아수당": childcare,
        "지급액계": gross,
        "국민연금": national_pension,
        "건강보험": health_insurance,
        "고용보험": employment_insurance,
        "장기요양보험료": longterm_care,
        "소득세": income_tax,
        "지방소득세": local_tax,
        "학자금상환액": student_loan,
        "정산보험료": settlement_insurance,
        "월세지원금": rent_support,
        "공제액계": deduction_total,
        "차인지급액": gross - deduction_total,
    }


def _build_headers(ws) -> None:
    """Write 2-row merged header matching the 위하고T 급여대장 template."""
    row1 = {1: "사원코드", 2: "사원명", 3: "부서", 4: "직급", 5: "직종",
            6: "수당", 12: "공제", 22: "차인지급액"}

    for col, val in row1.items():
        ws.cell(1, col, val)
    for offset, val in enumerate(ITEM_HEADERS):
        ws.cell(2, 6 + offset, val)

    # A1:A2 ~ E1:E2 — 정보 컬럼 세로 병합
    for c in range(1, _INFO_COL_COUNT + 1):
        ws.merge_cells(start_row=1, start_column=c, end_row=2, end_column=c)
    # F1:K1 — "수당"
    ws.merge_cells(start_row=1, start_column=6, end_row=1, end_column=_ALLOWANCE_LAST_COL)
    # L1:U1 — "공제"
    ws.merge_cells(start_row=1, start_column=12, end_row=1, end_column=_DEDUCTION_LAST_COL)
    # V1:V2 — "차인지급액" 세로 병합
    ws.merge_cells(start_row=1, start_column=COL_COUNT, end_row=2, end_column=COL_COUNT)

    for r in (1, 2):
        ws.row_dimensions[r].height = 21
        for c in range(1, COL_COUNT + 1):
            cell = ws.cell(r, c)
            cell.font = _HEADER_FONT
            # 정보 컬럼·차인지급액은 세로병합이라 1행 색(FFFF99)으로 통일
            merged_vertical = c <= _INFO_COL_COUNT or c == COL_COUNT
            cell.fill = _GROUP_FILL if (r == 1 or merged_vertical) else _SUB_FILL
            cell.alignment = _CENTER
            cell.border = _THIN_BORDER


def _data_row(entry: PayrollEntry) -> list:
    """Build a data row from PayrollEntry. 사원코드는 호출 전에 검사됨."""
    emp = entry.employee
    b = payroll_breakdown(entry)

    return [
        emp.employee_code,           # A: 사원코드 (위하고 사원코드)
        emp.name or entry.raw_name,  # B: 사원명
        emp.department or "",        # C: 부서
        emp.position or "",          # D: 직급
        emp.job_type or "",          # E: 직종
        *(b[h] for h in ITEM_HEADERS),   # F~U: 수당·공제 항목
        b["차인지급액"],              # V: 차인지급액
    ]


def generate_payroll_excel(
    entries: Iterable[PayrollEntry],
    period: str,
    client_name: str = "",
) -> bytes:
    """PayrollEntry 리스트를 위하고T 급여대장 엑셀(bytes)로 변환."""
    if not _is_valid_period(period):
        raise PayrollExcelError(f"period 형식이 올바르지 않음: {period!r} (YYYY-MM 필요)")

    entries = list(entries)
    if not entries:
        raise PayrollExcelError("엔트리가 없어 엑셀을 생성할 수 없습니다")
    no_code = [
        (e.employee.name if e.employee else None) or e.raw_name
        for e in entries
        if not (e.employee and (e.employee.employee_code or "").strip())
    ]
    if no_code:
        raise PayrollExcelError(
            f"위하고 사원코드가 없는 사원이 있어 급여대장을 만들 수 없습니다: {', '.join(no_code)}. "
            "사원 정보에 위하고 사원코드를 입력하세요."
        )

    wb = Workbook()
    ws = wb.active
    ws.title = f"{client_name}-{period}" if client_name else f"급여대장-{period}"

    _build_headers(ws)

    for r, entry in enumerate(entries, start=3):
        ws.append(_data_row(entry))
        ws.row_dimensions[r].height = 21
        for c in range(1, COL_COUNT + 1):
            cell = ws.cell(r, c)
            cell.font = _DATA_FONT
            cell.border = _THIN_BORDER
            if c > _INFO_COL_COUNT:
                cell.number_format = _NUM_FMT
                cell.alignment = _RIGHT
            else:
                cell.number_format = _TEXT_FMT
                cell.alignment = _LEFT

    # Column widths — 원본은 전 컬럼 14
    for c in range(1, COL_COUNT + 1):
        ws.column_dimensions[get_column_letter(c)].width = 14

    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _is_valid_period(period: str) -> bool:
    if not period or len(period) != 7 or period[4] != "-":
        return False
    try:
        y, m = int(period[:4]), int(period[5:])
    except ValueError:
        return False
    return 2000 <= y <= 2100 and 1 <= m <= 12


__all__ = ["ITEM_HEADERS", "PayrollExcelError", "generate_payroll_excel", "payroll_breakdown"]
