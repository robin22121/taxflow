"""SmartA 기타소득자료입력 일괄등록 엑셀(.xls) 생성.

더존 SmartA 10 급여관리 > 기타소득자료입력 메뉴가 Excel DATA를 자동 변환할 때 읽는
서식. 원본 서식(gita_excel_2022.xls, 2026-09-30 사용자가 실제로 받아 컬럼 분석)을
그대로 재현한다. BIFF(.xls) 포맷이라 openpyxl로는 쓸 수 없어 xlwt를 사용한다.

원본 서식은 17개 데이터 컬럼(A~Q) 뒤에 드롭다운 값 참조용 목록 컬럼(R~V, 병합 밖)이
붙어 있다 — 내/외국인·거주·소득구분(거주자용 17종·비거주자용 11종) 코드 목록. 이
파일은 그 목록 중 **거주자용 코드**만 다룬다(영세사업장 기본값 우선 원칙 —
[[feedback-default-heavy-small-biz]] — 비거주자 기타소득자는 훨씬 드물고, 현재
`PayrollEntry`/`Employee`에 거주구분·내외국인 필드 자체가 없어 항상 거주자·
내국인으로 가정한다).
"""

from __future__ import annotations

import logging
from datetime import date
from io import BytesIO

import xlwt

from app.models.payroll import PayrollEntry
from app.services.smarta_business_xls import _rrn_digits

logger = logging.getLogger(__name__)


TITLE_ROW = (
    " 기타소득자료입력     ※ 본 서식은 SmartA 10 급여관리 기타소득자료입력 메뉴로 "
    "Excel DATA를 자동 변환하기 위한 서식입니다."
)

GUIDE_ROW = "\n".join([
    "◈ 기타소득자료입력으로 엑셀 데이터를 반영하기 전 기타소득자입력의 사원정보가 있는 경우는 해당소득자로 반영되며, 소득자가 존재하지 않는 경우 자동으로 추가됩니다.",
    "",
    "◈ 귀속월, 지급월일, 소득자명, 거주, 내/외국인, 주민등록번호, 소득구분은 반드시 기재하셔야 합니다. 변환시 기타소득자입력의 주민(외국인)등록번호로 인식하여 변환이 됩니다.",
    "◈ 주민등록번호를 입력할 때에는 ' : / ? -\"등 특수문자를 제외하고 숫자 13자리를 입력하여 주십시오. ",
    "◈ 소득금액은 지급총액에서 필요경비를 차감하여 자동 산정되며, 업로드시에는 지급총액과 필요경비가 업로드 됩니다.",
    "◈ 소득세와 지방소득세는 지급총액에서 필요경비를 차감한 소득금액을 세율에 따라 자동 계산되어 반영되며, 직접 수정 가능합니다.",
    "◈ 세액계는 소득세와 지방소득세 금액을 합산하여 자동반영되며, 직접 수정 가능합니다.",
    "◈ 차인지급액은 소득금액에서 세액계 금액을 차감한 금액으로 자동반영되며, 직접 수정 가능합니다.",
    "",
    "▣ 본서식을 변형하여 사용시 기타소득자료입력 메뉴로 변환되지 않을 수 있습니다.",
])

COLUMNS = [
    "귀속년월", "지급년월일", "소득자명", "거주", "내/외국인", "기본주소", "상세주소",
    "주민등록번호", "소득구분", "영수일자", "지급총액", "필요경비", "소득금액",
    "세율(%)", "소득세", "지방소득세",
]

# 거주자용 소득구분 코드 → 라벨 (원본 서식 col20, 2026-09-30 실측). 비거주자용(col21,
# 40번대)은 아직 안 다룬다 — 필요해지면 여기에 별도 매핑을 추가한다.
RESIDENT_INCOME_CODE_LABELS: dict[str, str] = {
    "60": "필요경비 없는 기타소득",
    "61": "주식매수선택권 행사이익",
    "62": "그 밖에 필요경비 있는 기타소득(64/68/69/71~77/79제외)",
    "63": "소기업소상공인공제부금해지 소득",
    "64": "서화.골동품 양도소득(필요경비80(90)%)",
    "65": "직무발명보상금(비과세한도 초과분)",
    "68": "비과세기타소득",
    "69": "분리과세기타소득",
    "71": "상금 및 부상(필요경비 80%)",
    "72": "광업권 등(필요경비 60%)",
    "73": "지역권 등(필요경비 60%)",
    "74": "주택입주지체상금(필요경비 80%)",
    "75": "원고료 등(필요경비 60%)",
    "76": "강연료 등 (필요경비 60%)",
    "77": "종교인 소득",
    "78": "사례금",
    "79": "자문료 등 (필요경비 60%)",
    "80": "통신판매 대여 소득(필요경비 60%%)",
}

_RESIDENT_LABEL = "0.거주"
_NATIONAL_LABEL = "0.내국인"

_HEADER_ROW = 2  # 0-indexed. 0=제목, 1=안내문, 2=헤더, 3~=데이터


def _yyyymm(d: date) -> str:
    return f"{d.year}.{d.month:02d}"


def _yyyymmdd(d: date) -> str:
    return f"{d.year}.{d.month:02d}.{d.day:02d}"


def generate_smarta_other_income_xls(entries: list[PayrollEntry], period: str) -> bytes:
    """기타소득 항목을 SmartA 기타소득자료입력 서식으로 변환.

    Args:
        entries: income_type=OTHER인 PayrollEntry 리스트. employee가 eager-load되어야 함.
        period: "YYYY-MM" — 문서화 목적. 각 행의 귀속년월·지급년월일은
            `entry.payment_date`(없으면 이 period의 1일)로 채운다.

    Note:
        `other_income_code`가 없거나 `RESIDENT_INCOME_CODE_LABELS`에 없는 코드인 항목은
        위하고가 소득구분을 못 알아봐 업로드에서 제외되므로, 여기서도 건너뛰고 로그만
        남긴다 — 호출자가 "소득구분 미입력" 안내를 사용자에게 보여줄 수 있도록.
    """
    wb = xlwt.Workbook(encoding="utf-8")
    ws = wb.add_sheet("Sheet1")

    header_style = xlwt.easyxf(
        "font: bold on; align: horiz center, vert center;"
        " borders: left thin, right thin, top thin, bottom thin"
    )
    # 주민등록번호 컬럼은 숫자 서식("000000-0000000")이지만, 정수로 쓰면 xlwt가
    # 배정밀도 실수로 저장해 셀 원시값이 "7707281323914.0"처럼 소수점이 붙고,
    # 위하고 파서가 이걸 그대로 자릿수 검사에 써서 "13자리가 아닙니다" 오류가 난다
    # (2026-09-30 실기). 텍스트 서식(@)을 명시해 문자열 "7707281323914"로 쓴다.
    _rrn_style = xlwt.easyxf(num_format_str="@")

    ws.write_merge(0, 0, 0, 16, TITLE_ROW)
    ws.write_merge(1, 1, 0, 16, GUIDE_ROW)
    ws.write(_HEADER_ROW, 0, "", header_style)  # 일련번호(무제목)
    for offset, name in enumerate(COLUMNS, start=1):
        ws.write(_HEADER_ROW, offset, name, header_style)

    year, month = period.split("-")
    default_date = date(int(year), int(month), 1)

    row = _HEADER_ROW + 1
    written = 0
    skipped_no_code = 0
    for entry in entries:
        emp = entry.employee
        if not emp:
            continue
        code = entry.other_income_code
        if not code or code not in RESIDENT_INCOME_CODE_LABELS:
            skipped_no_code += 1
            logger.warning(
                "기타소득 소득구분코드 미입력/미지원 — 업로드에서 제외: entry_id=%s code=%s",
                entry.id, code,
            )
            continue

        pay_date = entry.payment_date or default_date

        ws.write(row, 0, written + 1)
        ws.write(row, 1, _yyyymm(pay_date))  # 귀속년월
        ws.write(row, 2, _yyyymmdd(pay_date))  # 지급년월일
        ws.write(row, 3, emp.name)
        ws.write(row, 4, _RESIDENT_LABEL)  # 거주
        ws.write(row, 5, _NATIONAL_LABEL)  # 내/외국인
        ws.write(row, 6, "")  # 기본주소
        ws.write(row, 7, "")  # 상세주소
        rrn = _rrn_digits(emp.rrn_encrypted)
        ws.write(row, 8, rrn, _rrn_style)
        ws.write(row, 9, f"{code}.{RESIDENT_INCOME_CODE_LABELS[code]}")  # 소득구분
        ws.write(row, 10, _yyyymmdd(pay_date))  # 영수일자
        ws.write(row, 11, entry.total_amount)  # 지급총액
        ws.write(row, 12, entry.necessary_expense or 0)  # 필요경비
        ws.write(row, 13, "")  # 소득금액 — 자동계산
        ws.write(row, 14, "")  # 세율(%) — 자동계산
        ws.write(row, 15, entry.income_tax if entry.income_tax is not None else "")
        ws.write(row, 16, entry.local_tax if entry.local_tax is not None else "")
        row += 1
        written += 1

    if skipped_no_code:
        logger.warning(
            "기타소득 엑셀 생성 — 소득구분코드 미입력/미지원으로 %d명 제외 (총 %d명 중)",
            skipped_no_code, len(entries),
        )

    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


__all__ = ["generate_smarta_other_income_xls", "RESIDENT_INCOME_CODE_LABELS"]
