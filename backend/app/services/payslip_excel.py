"""급여(임금)명세서 엑셀 생성 — 근로기준법 제48조.

직원 1명당 시트 1개. 항목 구성·명칭·금액은 위하고T 급여대장(payroll_excel)과
동일하며(`payroll_breakdown` 공유), 수당 / 공제 / 차인지급액을 세로 명세서
형식으로 출력한다.

기존 PayrollEntry 컬럼만 사용 — 스키마 변경 없음.
RRN은 명세서에 싣지 않음(성명 + 사번으로 식별, PII 노출 최소화).
발송(알림톡/SMS/이메일)은 본 단계 범위 밖 — 다운로드 전용.
"""

from __future__ import annotations

import re
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.worksheet import Worksheet

from app.models.payroll import PayrollEntry
from app.services.payroll_excel import payroll_breakdown

_INVALID_SHEET = re.compile(r"[\[\]:*?/\\]")

_TITLE_FILL = PatternFill("solid", fgColor="1B4F72")
_SECTION_FILL = PatternFill("solid", fgColor="D6E4F0")
_BOLD_WHITE = Font(bold=True, color="FFFFFF", size=13)
_BOLD = Font(bold=True)
_CENTER = Alignment(horizontal="center", vertical="center")
_RIGHT = Alignment(horizontal="right")


def _safe_sheet_title(name: str, used: set[str]) -> str:
    base = _INVALID_SHEET.sub("", name).strip()[:28] or "직원"
    title = base
    i = 2
    while title in used:
        title = f"{base[:25]}_{i}"
        i += 1
    used.add(title)
    return title


#: 위하고T 급여대장과 동일한 항목·순서 (payroll_excel.ITEM_HEADERS 기준)
_PAY_ITEMS = ["기본급", "상여", "식대", "자가운전", "육아"]
_DEDUCTION_ITEMS = [
    "국민연금", "건강보험", "고용보험", "장기요양보험료",
    "소득세", "지방소득세", "학자금상환액", "정산보험료", "월세지원금",
]


def _write_payslip(ws: Worksheet, entry: PayrollEntry, period: str) -> None:
    emp = entry.employee
    client = entry.client
    client_name = client.business_name if client else ""
    pay_date = entry.payment_date.isoformat() if entry.payment_date else ""

    ws.column_dimensions["A"].width = 22
    ws.column_dimensions["B"].width = 18
    ws.column_dimensions["C"].width = 22
    ws.column_dimensions["D"].width = 18

    ws.merge_cells("A1:D1")
    ws["A1"] = "임 금 명 세 서"
    ws["A1"].font = _BOLD_WHITE
    ws["A1"].fill = _TITLE_FILL
    ws["A1"].alignment = _CENTER
    ws.row_dimensions[1].height = 26

    ws.append(["사업장", client_name, "귀속연월", period])
    ws.append(["성명", emp.name if emp else entry.raw_name,
               "사번", (emp.employee_code if emp else "") or ""])
    ws.append(["임금지급일", pay_date, "", ""])
    for r in (2, 3, 4):
        ws.cell(row=r, column=1).font = _BOLD
        ws.cell(row=r, column=3).font = _BOLD

    b = payroll_breakdown(entry)
    pay_items = [(label, b[label]) for label in _PAY_ITEMS]
    deductions = [(label, b[label]) for label in _DEDUCTION_ITEMS]
    deduction_total = b["공제액계"]
    net = b["차인지급액"]

    def _section(header: str) -> None:
        row = ws.max_row + 1
        ws.append([header, "", "", ""])
        ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=4)
        c = ws.cell(row=row, column=1)
        c.font = _BOLD
        c.fill = _SECTION_FILL
        c.alignment = _CENTER

    ws.append([])
    _section("수당")
    for label, amount in pay_items:
        ws.append([label, amount, "", ""])
        ws.cell(row=ws.max_row, column=2).number_format = "#,##0"
        ws.cell(row=ws.max_row, column=2).alignment = _RIGHT
    ws.append(["지급액계", b["지급액계"], "", ""])
    ws.cell(row=ws.max_row, column=1).font = _BOLD
    ws.cell(row=ws.max_row, column=2).font = _BOLD
    ws.cell(row=ws.max_row, column=2).number_format = "#,##0"
    ws.cell(row=ws.max_row, column=2).alignment = _RIGHT

    ws.append([])
    _section("공제")
    for label, amount in deductions:
        ws.append([label, amount, "", ""])
        ws.cell(row=ws.max_row, column=2).number_format = "#,##0"
        ws.cell(row=ws.max_row, column=2).alignment = _RIGHT
    ws.append(["공제액계", deduction_total, "", ""])
    ws.cell(row=ws.max_row, column=1).font = _BOLD
    ws.cell(row=ws.max_row, column=2).font = _BOLD
    ws.cell(row=ws.max_row, column=2).number_format = "#,##0"
    ws.cell(row=ws.max_row, column=2).alignment = _RIGHT

    ws.append([])
    row = ws.max_row + 1
    ws.append(["차인지급액", net, "", ""])
    ws.merge_cells(start_row=row, start_column=2, end_row=row, end_column=4)
    ws.cell(row=row, column=1).font = _BOLD_WHITE
    ws.cell(row=row, column=1).fill = _TITLE_FILL
    nc = ws.cell(row=row, column=2)
    nc.font = Font(bold=True, size=13)
    nc.number_format = "#,##0"
    nc.alignment = _RIGHT
    ws.cell(row=row, column=1).alignment = _CENTER


def generate_payslips(entries: list[PayrollEntry], period: str) -> bytes:
    """근로기준법 §48 임금명세서 — 직원별 시트 단일 워크북.

    Args:
        entries: WAGE PayrollEntry 리스트. employee, client eager-load 필요.
        period: "YYYY-MM"
    """
    wb = Workbook()
    used: set[str] = set()
    valid = [e for e in entries if e.employee is not None]

    if not valid:
        ws = wb.active
        ws.title = "급여명세서"
        ws["A1"] = "임 금 명 세 서"
        ws["A1"].font = _BOLD_WHITE
        ws["A1"].fill = _TITLE_FILL
        ws["A2"] = f"{period} 대상 근로소득 항목이 없습니다."
        ws.column_dimensions["A"].width = 40
        buf = BytesIO()
        wb.save(buf)
        return buf.getvalue()

    for i, entry in enumerate(valid):
        name = entry.employee.name if entry.employee else entry.raw_name
        title = _safe_sheet_title(name, used)
        ws = wb.active if i == 0 else wb.create_sheet()
        ws.title = title
        _write_payslip(ws, entry, period)

    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


__all__ = ["generate_payslips"]
