"""SmartA 사업소득자료입력 일괄등록 엑셀(.xls) 생성.

더존 SmartA 인사급여 > 사업소득자료입력 메뉴가 Excel DATA를 자동 변환할 때 읽는 서식.
원본 서식(saup_excel.xls)의 컬럼 배치·안내문·소득구분 목록을 그대로 재현한다.

BIFF(.xls) 포맷이라 openpyxl로는 쓸 수 없어 xlwt를 사용한다.
간이지급명세서(`simple_statement_excel.py`)와는 별개 산출물 —
이쪽은 SmartA 업로드용, 저쪽은 홈택스 제출용이다.
"""

from __future__ import annotations

import logging
import re
from io import BytesIO

import xlwt

from app.models.business_type import BUSINESS_TYPE_CODES
from app.models.payroll import PayrollEntry
from app.services.crypto import decrypt_rrn

logger = logging.getLogger(__name__)


TITLE_ROW = (
    " 사업소득자료입력     ※ 본 서식은 SmartA 인사급여 사업소득자료입력 메뉴로 "
    "Excel DATA를 자동 변환하기 위한 서식입니다."
)

GUIDE_ROW = "\n".join([
    "◈ 사업소득자료입력으로 엑셀 데이터를 반영하기 전 사업소득자입력의 사원정보를 먼저 작업하셔야 합니다.",
    "◈ 귀속월, 지급월일, 소득자명, 주민등록번호, 소득구분은 반드시 기재하셔야 합니다."
    " 변환시 사업소득자입력의 주민(외국인)등록번호로 인식하여 변환이 됩니다.",
    "◈ 주민등록번호를 입력할 때에는 ' : / ? -\"등 특수문자를 제외하고 입력하여 주십시오.",
    "◈ 소득세와 지방소득세는 입력한 지급총액과 세율에 따라 자동 계산되어 반영되며, 직접 수정 가능합니다.",
    "◈ 세액계는 소득세와 지방소득세 금액을 합산하여 자동반영되며, 직접 수정 가능합니다.",
    "◈ 차인지급액은 지급총액에서 세액계 금액을 차감한 금액으로 자동반영되며, 직접 수정 가능합니다.",
    "◈ 연말정산 여/부 체크는 방문판매원,보험설계,음료배달 를 제외한 다른 소득구분을 여로 체크하셔도 부로 반영됩니다.",
    "◈ 입력한 주민(외국인)등록번호가 사업소득자입력에 없을경우 자동으로 소득자등록을 합니다.",
    "◈ 사업소득자 자동등록시 내외국인구분을 입력합니다."
    " 0.내국인1.외국인이 입력이 되어있지 않으면 내국인으로 등록됩니다.",
    "◈ 예술인/노무제공자(특고) 등록에 '여'로 입력된 사업소득자만 필요경비 및 고용보험료 가 계산됩니다.",
])

# A열은 일련번호(무제목), B열부터 14개 항목 — 원본 서식 3행과 동일
COLUMNS = [
    "귀속년월",
    "지급년월일",
    "소득자명",
    "주민등록번호",
    "기본주소",
    "상세주소",
    "소득구분",
    "영수일자",
    "지급총액",
    "세율(%)",
    "소득세",
    "지방소득세",
    "내.외국인구분",
    "연말정산",
]

# 원본 서식 IV열(255)의 소득구분 드롭다운 목록 — 순서 그대로
INCOME_TYPE_LIST = [
    "병의원", "저술가", "화가관련", "작곡가", "배우", "모델", "가수", "성악가",
    "1인미디어콘텐츠창작자", "연예보조", "자문/고문", "바둑기사", "꽃꽂이교사",
    "학원강사", "직업운동가", "봉사료수취자", "보험설계", "음료배달", "방판/외판",
    "기타인적용역자", "다단계판매", "기타모집수당", "간병인", "대리운전", "캐디",
    "목욕관리사", "행사도우미", "심부름용역", "퀵서비스", "물품배달",
    "학습지방문강사", "교육교구방문강사", "대여제품방문점검원", "대출모집인",
    "신용카드회원모집인", "방과후강사", "소프트웨어프리랜서", "관광통역안내사",
    "어린이통학버스기사", "중고자동차판매원",
]

# 국세청 업종코드 → SmartA 소득구분 라벨. 40종 1:1 대응.
CODE_TO_INCOME_TYPE = {
    "851101": "병의원",
    "940100": "저술가",
    "940200": "화가관련",
    "940301": "작곡가",
    "940302": "배우",
    "940303": "모델",
    "940304": "가수",
    "940305": "성악가",
    "940306": "1인미디어콘텐츠창작자",
    "940500": "연예보조",
    "940600": "자문/고문",
    "940901": "바둑기사",
    "940902": "꽃꽂이교사",
    "940903": "학원강사",
    "940904": "직업운동가",
    "940905": "봉사료수취자",
    "940906": "보험설계",
    "940907": "음료배달",
    "940908": "방판/외판",
    "940909": "기타인적용역자",
    "940910": "다단계판매",
    "940911": "기타모집수당",
    "940912": "간병인",
    "940913": "대리운전",
    "940914": "캐디",
    "940915": "목욕관리사",
    "940916": "행사도우미",
    "940917": "심부름용역",
    "940918": "퀵서비스",
    "940919": "물품배달",
    "940920": "학습지방문강사",
    "940921": "교육교구방문강사",
    "940922": "대여제품방문점검원",
    "940923": "대출모집인",
    "940924": "신용카드회원모집인",
    "940925": "방과후강사",
    "940926": "소프트웨어프리랜서",
    "940927": "관광통역안내사",
    "940928": "어린이통학버스기사",
    "940929": "중고자동차판매원",
}

_RATE_BY_CODE = {code: rate for code, _name, _desc, rate in BUSINESS_TYPE_CODES}

_DEFAULT_CODE = "940909"  # 기타인적용역자

_HEADER_ROW = 2  # 0-indexed. 0=제목, 1=안내문, 2=헤더, 3~=데이터
_INCOME_TYPE_COL = 255


def _rrn_digits(encrypted: bytes | None) -> str:
    """주민번호 복호화 후 숫자만 남긴다 (서식 안내: 특수문자 제외)."""
    if not encrypted:
        return ""
    try:
        return re.sub(r"\D", "", decrypt_rrn(encrypted))
    except Exception:  # noqa: BLE001
        logger.warning("RRN 복호화 실패 — 빈칸 처리")
        return ""


def _yyyymm(period: str) -> str:
    """'2025-11' → '202511'."""
    return period.replace("-", "")


def _yyyymmdd(value) -> str:
    return value.strftime("%Y%m%d") if value else ""


def generate_smarta_business_xls(entries: list[PayrollEntry], period: str) -> bytes:
    """사업소득 항목을 SmartA 일괄등록 .xls로 변환.

    Args:
        entries: income_type=BUSINESS인 PayrollEntry 리스트. employee가 eager-load되어야 함.
        period: "YYYY-MM"

    Note:
        기본주소·상세주소는 Employee에 해당 필드가 없어 빈칸으로 나간다.
        서식상 필수 항목이 아니며, SmartA는 소득자 자동등록 시 주소 없이도 처리한다.
        내외국인구분·연말정산도 빈칸이면 각각 내국인·부로 처리된다.
    """
    wb = xlwt.Workbook(encoding="utf-8")
    ws = wb.add_sheet("Sheet1")

    header_style = xlwt.easyxf(
        "font: bold on; align: horiz center, vert center;"
        " borders: left thin, right thin, top thin, bottom thin"
    )

    ws.write(0, 0, TITLE_ROW)
    ws.write(1, 0, GUIDE_ROW)
    for offset, name in enumerate(COLUMNS, start=1):
        ws.write(_HEADER_ROW, offset, name, header_style)

    row = _HEADER_ROW + 1
    written = 0
    for entry in entries:
        emp = entry.employee
        if not emp:
            continue
        code = entry.business_type_code or emp.business_type_code or _DEFAULT_CODE
        paid_on = _yyyymmdd(entry.payment_date)

        ws.write(row, 0, written + 1)
        ws.write(row, 1, _yyyymm(period))
        ws.write(row, 2, paid_on)
        ws.write(row, 3, emp.name)
        ws.write(row, 4, _rrn_digits(emp.rrn_encrypted))
        ws.write(row, 5, "")  # 기본주소 — 모델에 필드 없음
        ws.write(row, 6, "")  # 상세주소 — 모델에 필드 없음
        ws.write(row, 7, CODE_TO_INCOME_TYPE.get(code, CODE_TO_INCOME_TYPE[_DEFAULT_CODE]))
        ws.write(row, 8, paid_on)
        ws.write(row, 9, entry.total_amount)
        ws.write(row, 10, _RATE_BY_CODE.get(code, 3))
        ws.write(row, 11, entry.income_tax)
        ws.write(row, 12, entry.local_tax)
        ws.write(row, 13, "")  # 내.외국인구분 — 빈칸이면 내국인
        ws.write(row, 14, "")  # 연말정산 — 빈칸이면 부
        row += 1
        written += 1

    # 원본 서식과 동일하게 IV열에 소득구분 목록을 둔다 (입력 보조용)
    for offset, label in enumerate(INCOME_TYPE_LIST):
        ws.write(_HEADER_ROW + 1 + offset, _INCOME_TYPE_COL, label)

    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


__all__ = ["generate_smarta_business_xls"]
