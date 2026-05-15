"""4대 보험 신고서 엑셀 생성 — 자격취득·자격상실·보수월액 변경.

기획안 "4대 보험 업무 자동화" M3(4대 보험 신고서 자동 생성) 실현.
4insure 통합포털 업로드/공단 EDI 활용을 위한 표준 엑셀.
원천세 간이지급명세서(simple_statement_excel)와 별개 산출물.

판정 기준 (기존 모델 필드만 사용 — 스키마 변경 없음):
- 자격취득: match_status=NEW_HIRE_SUSPECTED 또는 입사일이 귀속월에 속함
- 자격상실: match_status=RESIGNATION_SUSPECTED 또는 퇴사일이 귀속월에 속함
- 보수월액 변경: 전월 금액(prev_amount)과 당월 총지급액이 다름 (취득·상실 제외)

통합(combined): 위 3종을 한 워크북 3시트로 — "4대보험 통합" 다운로드용.
"""

from __future__ import annotations

import logging
from datetime import date
from io import BytesIO
from typing import NamedTuple

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from app.models.payroll import MatchStatus, PayrollEntry
from app.services.crypto import decrypt_rrn
from app.services.tax_calc import calculate_social_insurance

logger = logging.getLogger(__name__)


class _SheetPayload(NamedTuple):
    title: str
    columns: list[str]
    widths: list[int]
    rows: list[list]
    sum_cols: list[int]


def _safe_decrypt_rrn(encrypted: bytes | None) -> str:
    if not encrypted:
        return ""
    try:
        return decrypt_rrn(encrypted)
    except Exception:  # noqa: BLE001
        logger.warning("RRN 복호화 실패 — 마스킹 처리")
        return "******-*******"


def _in_period(d: date | None, period: str) -> bool:
    return d is not None and d.strftime("%Y-%m") == period


def _write_sheet(ws: Worksheet, p: _SheetPayload) -> None:
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill("solid", fgColor="1B4F72")
    center = Alignment(horizontal="center", vertical="center")

    ws.append(p.columns)
    for col_idx in range(1, len(p.columns) + 1):
        cell = ws.cell(row=1, column=col_idx)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = center

    for row in p.rows:
        ws.append(row)

    for i, w in enumerate(p.widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w

    # 금액 컬럼(=sum_cols) 천단위 콤마 표기
    n_rows = len(p.rows)
    for col in p.sum_cols:
        for r in range(2, n_rows + 2):
            ws.cell(row=r, column=col).number_format = "#,##0"

    if p.sum_cols and p.rows:
        n = len(p.rows)
        summary: list = [""] * len(p.columns)
        summary[0] = "합계"
        for col in p.sum_cols:
            summary[col - 1] = sum(
                ws.cell(row=r, column=col).value or 0 for r in range(2, n + 2)
            )
        ws.append(summary)
        for col_idx in range(1, len(p.columns) + 1):
            ws.cell(row=n + 2, column=col_idx).font = Font(bold=True)
        for col in p.sum_cols:
            ws.cell(row=n + 2, column=col).number_format = "#,##0"


def _single(p: _SheetPayload) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = p.title
    _write_sheet(ws, p)
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# 자격취득 신고서
# ---------------------------------------------------------------------------

_ACQUISITION_COLUMNS = [
    "일련번호",
    "성명",
    "주민등록번호",
    "자격취득일",
    "월보수액",
    "국민연금",
    "건강보험",
    "장기요양",
    "고용보험",
    "비고",
]


def _acquisition_payload(entries: list[PayrollEntry], period: str) -> _SheetPayload:
    rows: list[list] = []
    idx = 1
    for entry in entries:
        emp = entry.employee
        if not emp:
            continue
        is_new = (
            entry.match_status == MatchStatus.NEW_HIRE_SUSPECTED
            or _in_period(emp.hired_at, period)
        )
        if not is_new:
            continue
        si = calculate_social_insurance(entry.total_amount, entry.income_type)
        rows.append([
            idx,
            emp.name,
            _safe_decrypt_rrn(emp.rrn_encrypted),
            emp.hired_at.isoformat() if emp.hired_at else "",
            entry.total_amount,
            si.national_pension,
            si.health_insurance,
            si.longterm_care,
            si.employment_insurance,
            "신규취득",
        ])
        idx += 1
    return _SheetPayload(
        "자격취득신고서",
        _ACQUISITION_COLUMNS,
        [8, 12, 18, 14, 14, 12, 12, 12, 12, 12],
        rows,
        [5, 6, 7, 8, 9],
    )


def generate_acquisition_report(entries: list[PayrollEntry], period: str) -> bytes:
    """4대 보험 자격취득 신고서 엑셀 (단일 시트)."""
    return _single(_acquisition_payload(entries, period))


# ---------------------------------------------------------------------------
# 자격상실 신고서
# ---------------------------------------------------------------------------

_LOSS_COLUMNS = [
    "일련번호",
    "성명",
    "주민등록번호",
    "자격상실일",
    "상실부호",
    "당월보수총액",
    "비고",
]


def _loss_payload(entries: list[PayrollEntry], period: str) -> _SheetPayload:
    rows: list[list] = []
    idx = 1
    for entry in entries:
        emp = entry.employee
        if not emp:
            continue
        is_loss = (
            entry.match_status == MatchStatus.RESIGNATION_SUSPECTED
            or _in_period(emp.resigned_at, period)
        )
        if not is_loss:
            continue
        rows.append([
            idx,
            emp.name,
            _safe_decrypt_rrn(emp.rrn_encrypted),
            emp.resigned_at.isoformat() if emp.resigned_at else "",
            "3 (퇴직)",
            entry.total_amount,
            "",
        ])
        idx += 1
    return _SheetPayload(
        "자격상실신고서",
        _LOSS_COLUMNS,
        [8, 12, 18, 14, 14, 14, 12],
        rows,
        [6],
    )


def generate_loss_report(entries: list[PayrollEntry], period: str) -> bytes:
    """4대 보험 자격상실 신고서 엑셀 (단일 시트).

    상실부호 3 = 사용관계 종료(퇴직). 실제 사유 분기는 Phase 2 RPA 단계 과제.
    """
    return _single(_loss_payload(entries, period))


# ---------------------------------------------------------------------------
# 보수월액 변경 신고서
# ---------------------------------------------------------------------------

_CHANGE_COLUMNS = [
    "일련번호",
    "성명",
    "주민등록번호",
    "변경전 보수월액",
    "변경후 보수월액",
    "증감",
    "변경월",
    "비고",
]


def _change_payload(entries: list[PayrollEntry], period: str) -> _SheetPayload:
    rows: list[list] = []
    idx = 1
    for entry in entries:
        emp = entry.employee
        if not emp:
            continue
        if entry.prev_amount is None or entry.prev_amount == entry.total_amount:
            continue
        is_acq_or_loss = (
            entry.match_status
            in (MatchStatus.NEW_HIRE_SUSPECTED, MatchStatus.RESIGNATION_SUSPECTED)
            or _in_period(emp.hired_at, period)
            or _in_period(emp.resigned_at, period)
        )
        if is_acq_or_loss:
            continue
        rows.append([
            idx,
            emp.name,
            _safe_decrypt_rrn(emp.rrn_encrypted),
            entry.prev_amount,
            entry.total_amount,
            entry.total_amount - entry.prev_amount,
            period,
            "",
        ])
        idx += 1
    return _SheetPayload(
        "보수월액변경신고서",
        _CHANGE_COLUMNS,
        [8, 12, 18, 16, 16, 12, 10, 12],
        rows,
        [4, 5, 6],
    )


def generate_remuneration_change_report(
    entries: list[PayrollEntry], period: str
) -> bytes:
    """4대 보험 보수월액 변경 신고서 엑셀 (단일 시트)."""
    return _single(_change_payload(entries, period))


# ---------------------------------------------------------------------------
# 통합 (3시트 단일 워크북)
# ---------------------------------------------------------------------------


def generate_combined_insurance_report(
    entries: list[PayrollEntry], period: str
) -> bytes:
    """4대 보험 통합 — 자격취득·자격상실·보수월액변경을 한 워크북 3시트로."""
    payloads = [
        _acquisition_payload(entries, period),
        _loss_payload(entries, period),
        _change_payload(entries, period),
    ]
    wb = Workbook()
    for i, p in enumerate(payloads):
        ws = wb.active if i == 0 else wb.create_sheet()
        ws.title = p.title
        _write_sheet(ws, p)
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


__all__ = [
    "generate_acquisition_report",
    "generate_combined_insurance_report",
    "generate_loss_report",
    "generate_remuneration_change_report",
]
