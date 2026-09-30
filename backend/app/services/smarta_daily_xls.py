"""SmartA 일용직급여자료입력 일괄등록 엑셀(.xls) 생성.

더존 SmartA 인사급여 > 일용직급여자료입력 메뉴가 Excel DATA를 자동 변환할 때 읽는 서식.
원본 서식(ilyongjig_excel_2022.xls, 2026-09-30 사용자가 실제로 받아 컬럼 분석)을 그대로
재현한다. BIFF(.xls) 포맷이라 openpyxl로는 쓸 수 없어 xlwt를 사용한다.

사업소득(`smarta_business_xls.py`)과 달리 이 서식엔 귀속년월·지급년월일 컬럼이 없다 —
화면의 조회조건(지급기간)으로 대상 월을 정하고, 엑셀은 그 달의 일자별 데이터만 담는다.

이지원천은 일용소득을 "월 합계 1건"(PayrollEntry.total_amount)으로만 다루고 일자별
내역을 저장하지 않는다 — 원본 서식의 "만근공수" 특수 입력(일자를 99로 입력하면 근무시간
(정상·연장)·지급액(연장) 항목은 업로드되지 않고, "공수"(근로일수)·지급액(정상)만으로
한 사람당 한 줄 업로드된다는 안내문 규칙, 2026-09-30 확인)을 그대로 활용해 이 차이를
메운다. `PayrollEntry.work_days`가 이 "공수" 값이다.
"""

from __future__ import annotations

import logging
from io import BytesIO

import xlwt

from app.models.payroll import PayrollEntry
from app.services.smarta_business_xls import _rrn_digits

logger = logging.getLogger(__name__)


TITLE_ROW = (
    " 일용직급여자료입력     ※ 본 서식은 SmartA 인사급여 일용직급여자료입력 메뉴로 "
    "Excel DATA를 자동 변환하기 위한 서식입니다."
)

GUIDE_ROW = "\n".join([
    "◈ 일용직급여자료입력으로 엑셀을 변환하기전 일용직사원등록의 사원정보를 먼저 작업하셔야 합니다.",
    "◈ 일자와 주민등록번호는 반드시 기재하셔야 합니다. 변환시 일용직사원등록의 주민등록번호로 인식하여 변환이 됩니다.",
    "◈ 일자를 입력시에는 반드시 해당 근무월(귀속월)의 일자를 입력해 주십시오 예) 2015년 1월 1일 일 경우 -> 1(○) , 2015.01.01 (X), 01.01 (X)",
    "◈ 동일한 일자에 중복해서 입력할 경우에는 가장 처음 입력한 데이타를 변환하여 줍니다. (같은 일자에 동일한 사원을 중복해서 입력하지 말아주십시오.)",
    "◈ 주민등록번호를 입력할때에는 ' : / ? -\"등 특수문자를 제외하고 입력하세요. 예) (-)없이 숫자 13자리로 입력합니다.",
    "◈ 고용보험,국민연금,건강보험,소득세,지방소득세는 엑셀 변환시 선택에 따라 사원등록정보,소득세율에 따라 재계산이 가능합니다.",
    "◈ 근무시간은 소수점 둘째자리까지 입력가능합니다.",
    "◈ 만근공수는 업로드 대상 사원의 일자를 '99'로 입력 후 업로드를 하시면 됩니다. (만근공수는 근무시간(정상,연장),지급액 (연장) 항목은 업로드되지 않습니다.)",
    "◈ 만근공수를 업로드하는 경우 \"공수\" 항목에 데이터가 입력되어 있지 않았다면 만근공수 전체 데이터가 업로드 되지 않습니다. (만근공수 입력 시 \"공수\" 항목은 필수입력 사항입니다.)",
    "",
    "▣ 본서식을 변형하여 사용시 일용직 사원등록 메뉴로 변환되지 않을수 있습니다.",
])

# 원본 서식 3~4행(2행 헤더) 그대로 — B열부터, A열은 일련번호(무제목)
COLUMNS_ROW1 = [
    "일자", "근무\n여부", "사원명", "주민등록번호", "현장(코드)", "공수",
    "근무시간", "", "지급액", "", "기타비과세", "고용보험", "국민연금",
    "건강보험", "장기요양보험", "소득세", "지방소득세",
]
COLUMNS_ROW2 = ["", "", "", "", "", "", "정상", "연장", "정상", "연장", "", "", "", "", "", "", ""]

_MANKUN_DAY = 99  # "만근공수" 특수 일자값 — 근무시간·지급액(연장)은 업로드 안 됨, 공수 필수

_HEADER_ROW1 = 2  # 0-indexed. 0=제목, 1=안내문, 2~3=헤더(2행), 4~=데이터
_HEADER_ROW2 = 3


def generate_smarta_daily_xls(entries: list[PayrollEntry], period: str) -> bytes:
    """일용소득 항목을 SmartA 일용직급여자료입력 "만근공수" 방식으로 변환.

    Args:
        entries: income_type=DAILY인 PayrollEntry 리스트. employee가 eager-load되어야 함.
        period: "YYYY-MM" — 이 서식 자체엔 귀속월 컬럼이 없다(화면 조회조건으로 결정).
            현재는 문서화 목적으로만 받고 실제로 쓰진 않는다.

    Note:
        work_days(공수)가 없는 건(None)은 만근공수 필수 입력 규칙("공수" 항목 필수)을
        만족 못 해 업로드 시 반영되지 않으므로, 여기서도 건너뛰고 로그만 남긴다 —
        호출자가 "일수 미입력" 안내를 사용자에게 보여줄 수 있도록 스킵된 사람 수를 반환한다.
    """
    wb = xlwt.Workbook(encoding="utf-8")
    ws = wb.add_sheet("Sheet1")

    header_style = xlwt.easyxf(
        "font: bold on; align: horiz center, vert center;"
        " borders: left thin, right thin, top thin, bottom thin"
    )

    ws.write_merge(0, 0, 0, 17, TITLE_ROW)
    ws.write_merge(1, 1, 0, 17, GUIDE_ROW)
    # 원본 서식은 "근무시간"·"지급액"(가로 2칸 병합, 2행)을 빼고 나머지 모든 헤더가 2~3행
    # 세로 병합이다 — 더존 엑셀변환기가 이 병합 구조로 컬럼을 식별하는 것으로 보여
    # (2026-09-30 실측: 병합 없이 올리면 API는 SUCCESS를 반환해도 데이터가 전혀 반영되지
    # 않음) 원본과 동일하게 재현한다.
    ws.write_merge(_HEADER_ROW1, _HEADER_ROW2, 0, 0, "", header_style)  # 일련번호(무제목)
    for offset, name in enumerate(COLUMNS_ROW1, start=1):
        if offset in (7, 9):  # 근무시간·지급액 — 가로 2칸, 1행짜리 헤더
            ws.write_merge(_HEADER_ROW1, _HEADER_ROW1, offset, offset + 1, name, header_style)
        elif offset in (8, 10):  # 근무시간·지급액의 두 번째 칸(연장) — 이미 위에서 병합됨
            continue
        else:
            ws.write_merge(_HEADER_ROW1, _HEADER_ROW2, offset, offset, name, header_style)
    for offset, name in enumerate(COLUMNS_ROW2, start=1):
        if offset in (7, 8, 9, 10):  # 정상/연장 (근무시간·지급액 하위 칸)
            ws.write(_HEADER_ROW2, offset, name, header_style)

    row = _HEADER_ROW2 + 1
    written = 0
    skipped_no_work_days = 0
    for entry in entries:
        emp = entry.employee
        if not emp:
            continue
        if not entry.work_days:
            skipped_no_work_days += 1
            logger.warning(
                "일용소득 근로일수(공수) 미입력 — 업로드에서 제외: entry_id=%s", entry.id
            )
            continue

        ws.write(row, 0, written + 1)
        ws.write(row, 1, _MANKUN_DAY)  # 일자 — 만근공수
        ws.write(row, 2, "")  # 근무여부 — 만근공수는 불필요
        ws.write(row, 3, emp.name)
        ws.write(row, 4, _rrn_digits(emp.rrn_encrypted))
        ws.write(row, 5, "")  # 현장(코드) — 모델에 필드 없음, 단일 현장 가정
        ws.write(row, 6, entry.work_days)  # 공수 — 만근공수 필수
        ws.write(row, 7, "")  # 근무시간 정상 — 만근공수는 업로드 안 됨
        ws.write(row, 8, "")  # 근무시간 연장 — 만근공수는 업로드 안 됨
        ws.write(row, 9, entry.total_amount)  # 지급액 정상
        ws.write(row, 10, "")  # 지급액 연장 — 만근공수는 업로드 안 됨
        ws.write(row, 11, entry.non_taxable or 0)  # 기타비과세
        ws.write(row, 12, entry.employment_insurance)
        ws.write(row, 13, entry.national_pension)
        ws.write(row, 14, entry.health_insurance)
        ws.write(row, 15, entry.longterm_care)
        ws.write(row, 16, entry.income_tax)
        ws.write(row, 17, entry.local_tax)
        row += 1
        written += 1

    if skipped_no_work_days:
        logger.warning(
            "일용소득 엑셀 생성 — 근로일수 미입력으로 %d명 제외 (총 %d명 중)",
            skipped_no_work_days, len(entries),
        )

    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


__all__ = ["generate_smarta_daily_xls"]
