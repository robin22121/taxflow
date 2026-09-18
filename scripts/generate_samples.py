"""가상 거래처 5곳 + 직원 마스터 + 2026-01~08 급여대장 샘플 생성.

- 사업자번호: 123-45-67890 ~ 123-45-67894
- 급여대장 양식: 위하고T 22컬럼 (payroll_excel.py와 동일 구조)
- 8월 파일: 사업자별로 다양한 오류 케이스 포함 (파싱·검증 로직 테스트용)

실행:
    uv run python scripts/generate_samples.py
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

ROOT = Path(__file__).resolve().parents[1] / "samples"


# ── SmartA/위하고T 급여대장 22컬럼 정의 ──────────────────────────────
COL_COUNT = 22
INFO_COLS = 5
ITEM_HEADERS = [
    "기본급", "상여", "식대", "자가운전", "육아", "지급액계",
    "국민연금", "건강보험", "고용보험", "장기요양보험료",
    "소득세", "지방소득세", "학자금상환액", "정산보험료", "월세지원금", "공제액계",
]

HEADER_FONT = Font(name="맑은 고딕", size=9, bold=True)
DATA_FONT = Font(name="맑은 고딕", size=9)
SUM_FONT = Font(name="맑은 고딕", size=9, bold=True)
GROUP_FILL = PatternFill("solid", fgColor="FFFF99")
SUB_FILL = PatternFill("solid", fgColor="99CCFF")
SUM_FILL = PatternFill("solid", fgColor="ABCCF8")
CENTER = Alignment(horizontal="center", vertical="center")
LEFT = Alignment(horizontal="left", vertical="center")
RIGHT = Alignment(horizontal="right", vertical="center")
THIN = Border(*(Side(style="thin", color="B3B3B3") for _ in range(4)))
SUM_BORDER = Border(*(Side(style="thin", color="96BBED") for _ in range(4)))


# ── 4대보험·세율 (2026년 근사치, 샘플용) ─────────────────────────────
NP_RATE = 0.045          # 국민연금 4.5%
HI_RATE = 0.03545        # 건강보험 3.545%
LTC_RATE = 0.1295        # 장기요양보험 = 건강보험 × 12.95%
EI_RATE = 0.009          # 고용보험 0.9%


def calc_deductions(taxable: int) -> dict[str, int]:
    """월 과세대상 급여에서 4대보험·세금 산출 (샘플용 근사 계산)."""
    np = int(taxable * NP_RATE)
    hi = int(taxable * HI_RATE)
    ltc = int(hi * LTC_RATE)
    ei = int(taxable * EI_RATE)
    # 소득세: 근사식(과세표준 × 대략적 실효세율)
    if taxable < 2_500_000:
        income_tax = int(taxable * 0.01)
    elif taxable < 4_000_000:
        income_tax = int(taxable * 0.03)
    elif taxable < 6_000_000:
        income_tax = int(taxable * 0.06)
    else:
        income_tax = int(taxable * 0.09)
    local_tax = int(income_tax * 0.1)
    return {
        "국민연금": np,
        "건강보험": hi,
        "고용보험": ei,
        "장기요양보험료": ltc,
        "소득세": income_tax,
        "지방소득세": local_tax,
    }


@dataclass
class Employee:
    code: str
    name: str
    rrn: str
    hired: date
    department: str
    position: str
    job_type: str
    income_type: str        # WAGE / BUSINESS / DAILY
    base_salary: int
    bonus_default: int = 0
    meal: int = 0           # 식대(비과세, 월 20만원 한도)
    car: int = 0            # 자가운전(비과세, 월 20만원 한도)
    childcare: int = 0      # 육아수당(비과세, 월 20만원 한도)
    resigned_at: date | None = None


@dataclass
class Client:
    biz_number: str
    name: str
    representative: str
    phone: str
    email: str | None
    industry: str
    is_corp: bool
    employees: list[Employee] = field(default_factory=list)


# ── 거래처 5곳 ───────────────────────────────────────────────────────
CLIENTS: list[Client] = [
    Client(
        biz_number="123-45-67890",
        name="(주)새싹식품",
        representative="박새싹",
        phone="02-100-1000",
        email="hr@saessak.co.kr",
        industry="식품제조",
        is_corp=True,
        employees=[
            Employee("S001", "김지훈", "870815-1234567", date(2019, 3, 1), "생산", "부장", "생산관리", "WAGE", 4_800_000, 0, 200_000, 0, 0),
            Employee("S002", "이서연", "910502-2345678", date(2020, 7, 1), "생산", "과장", "품질관리", "WAGE", 3_700_000, 0, 200_000, 0, 0),
            Employee("S003", "박민재", "880922-1456789", date(2018, 11, 1), "영업", "차장", "영업", "WAGE", 4_200_000, 0, 200_000, 200_000, 0),
            Employee("S004", "정다은", "930310-2234567", date(2021, 4, 15), "관리", "대리", "회계", "WAGE", 3_100_000, 0, 200_000, 0, 0),
            Employee("S005", "최준호", "950709-1345678", date(2022, 1, 3), "생산", "사원", "생산", "WAGE", 2_600_000, 0, 200_000, 0, 0),
            Employee("S006", "한소영", "960214-2456789", date(2023, 6, 1), "영업", "사원", "영업지원", "WAGE", 2_500_000, 0, 200_000, 0, 200_000),
            Employee("S007", "윤재현", "980601-1234567", date(2024, 3, 1), "생산", "사원", "포장", "WAGE", 2_400_000, 0, 200_000, 0, 0),
            Employee("S008", "장하윤", "990418-2345678", date(2024, 9, 1), "관리", "사원", "총무", "WAGE", 2_300_000, 0, 200_000, 0, 0),
            Employee("S009", "임도훈", "020805-3456789", date(2025, 5, 1), "생산", "사원", "포장", "WAGE", 2_200_000, 0, 200_000, 0, 0),
            Employee("S010", "노예린", "010223-4567890", date(2025, 11, 1), "관리", "사원", "인사", "WAGE", 2_250_000, 0, 200_000, 0, 0),
        ],
    ),
    Client(
        biz_number="123-45-67891",
        name="하늘IT컨설팅",
        representative="김하늘",
        phone="02-200-2000",
        email="admin@haneulit.kr",
        industry="정보통신",
        is_corp=False,
        employees=[
            Employee("H001", "송민수", "850501-1234567", date(2019, 1, 1), "개발", "이사", "PM", "WAGE", 6_500_000, 0, 200_000, 200_000, 0),
            Employee("H002", "오지영", "890712-2345678", date(2020, 3, 1), "개발", "책임", "백엔드", "WAGE", 5_500_000, 0, 200_000, 0, 0),
            Employee("H003", "강태준", "920915-1456789", date(2021, 8, 1), "개발", "선임", "프론트엔드", "WAGE", 4_500_000, 0, 200_000, 0, 0),
            Employee("H004", "문가영", "940627-2234567", date(2022, 11, 1), "개발", "선임", "iOS", "WAGE", 4_200_000, 0, 200_000, 0, 0),
            Employee("H005", "배현우", "970329-1345678", date(2023, 5, 1), "영업", "매니저", "영업", "WAGE", 3_800_000, 0, 200_000, 200_000, 0),
            Employee("H006", "구서희", "990803-2456789", date(2024, 6, 1), "개발", "주임", "QA", "WAGE", 3_200_000, 0, 200_000, 0, 0),
            Employee("H007", "홍성재", "010115-3234567", date(2025, 2, 1), "개발", "사원", "백엔드", "WAGE", 2_800_000, 0, 200_000, 0, 0),
        ],
    ),
    Client(
        biz_number="123-45-67892",
        name="별카페",
        representative="이별하",
        phone="02-300-3000",
        email=None,
        industry="음식점업",
        is_corp=False,
        employees=[
            Employee("B001", "차예은", "930206-2234567", date(2020, 5, 1), "매장", "점장", "매니저", "WAGE", 3_200_000, 0, 200_000, 0, 0),
            Employee("B002", "송지훈", "960519-1345678", date(2022, 3, 1), "매장", "부점장", "바리스타", "WAGE", 2_700_000, 0, 200_000, 0, 0),
            Employee("B003", "김유리", "980827-2456789", date(2023, 8, 1), "매장", "스텝", "바리스타", "WAGE", 2_400_000, 0, 200_000, 0, 0),
            Employee("B004", "장서준", "000114-3234567", date(2024, 6, 1), "매장", "스텝", "홀서빙", "WAGE", 2_200_000, 0, 200_000, 0, 0),
            Employee("B005", "권미나", "020706-4345678", date(2025, 3, 1), "매장", "스텝", "홀서빙", "DAILY", 1_500_000, 0, 0, 0, 0),
        ],
    ),
    Client(
        biz_number="123-45-67893",
        name="(주)금성물류",
        representative="정금성",
        phone="031-400-4000",
        email="ops@geumseong.co.kr",
        industry="운수업",
        is_corp=True,
        employees=[
            Employee("L001", "김철수", "820418-1234567", date(2015, 2, 1), "운송", "부장", "운송관리", "WAGE", 5_200_000, 0, 200_000, 200_000, 0),
            Employee("L002", "박영수", "860925-1345678", date(2017, 6, 1), "운송", "과장", "운전", "WAGE", 4_100_000, 0, 200_000, 200_000, 0),
            Employee("L003", "최수정", "900303-2456789", date(2019, 9, 1), "관리", "대리", "회계", "WAGE", 3_400_000, 0, 200_000, 0, 0),
            Employee("L004", "이준영", "930712-1234567", date(2020, 11, 1), "운송", "대리", "운전", "WAGE", 3_600_000, 0, 200_000, 200_000, 0),
            Employee("L005", "황보람", "950205-2345678", date(2022, 4, 1), "운송", "사원", "운전", "WAGE", 3_100_000, 0, 200_000, 200_000, 0),
            Employee("L006", "조현우", "970618-1456789", date(2023, 7, 1), "운송", "사원", "운전", "WAGE", 3_000_000, 0, 200_000, 200_000, 0),
            Employee("L007", "신다인", "990921-2234567", date(2024, 10, 1), "관리", "사원", "총무", "WAGE", 2_500_000, 0, 200_000, 0, 0),
            Employee("L008", "유민석", "010507-3345678", date(2025, 6, 1), "운송", "사원", "운전", "WAGE", 2_700_000, 0, 200_000, 200_000, 0),
        ],
    ),
    Client(
        biz_number="123-45-67894",
        name="파랑디자인스튜디오",
        representative="한파랑",
        phone="02-500-5000",
        email="hi@paranddesign.co.kr",
        industry="전문디자인업",
        is_corp=False,
        employees=[
            Employee("D001", "이수민", "880502-2345678", date(2018, 4, 1), "디자인", "실장", "디렉터", "WAGE", 4_800_000, 0, 200_000, 0, 0),
            Employee("D002", "박지원", "920809-2456789", date(2020, 6, 1), "디자인", "선임", "디자이너", "WAGE", 3_800_000, 0, 200_000, 0, 0),
            Employee("D003", "최유진", "950123-2234567", date(2022, 3, 1), "디자인", "주임", "디자이너", "WAGE", 3_100_000, 0, 200_000, 0, 0),
            Employee("D004", "김태윤", "890615-1234567", date(2021, 9, 1), "디자인", "프리랜서", "일러스트", "BUSINESS", 3_500_000, 0, 0, 0, 0),
            Employee("D005", "장아름", "930928-2345678", date(2023, 1, 1), "디자인", "프리랜서", "웹디자인", "BUSINESS", 4_200_000, 0, 0, 0, 0),
            Employee("D006", "홍진호", "000411-3345678", date(2024, 5, 1), "디자인", "사원", "보조", "WAGE", 2_400_000, 0, 200_000, 0, 0),
        ],
    ),
]


# ── 급여대장 시트 렌더링 (payroll_excel.py와 동일 구조) ───────────────
def build_headers(ws) -> None:
    row1 = {1: "사원코드", 2: "사원명", 3: "부서", 4: "직급", 5: "직종",
            6: "수당", 12: "공제", 22: "차인지급액"}
    for col, val in row1.items():
        ws.cell(1, col, val)
    for offset, val in enumerate(ITEM_HEADERS):
        ws.cell(2, 6 + offset, val)

    for c in range(1, INFO_COLS + 1):
        ws.merge_cells(start_row=1, start_column=c, end_row=2, end_column=c)
    ws.merge_cells(start_row=1, start_column=6, end_row=1, end_column=11)
    ws.merge_cells(start_row=1, start_column=12, end_row=1, end_column=21)
    ws.merge_cells(start_row=1, start_column=22, end_row=2, end_column=22)

    for r in (1, 2):
        ws.row_dimensions[r].height = 21
        for c in range(1, COL_COUNT + 1):
            cell = ws.cell(r, c)
            cell.font = HEADER_FONT
            merged_vertical = c <= INFO_COLS or c == COL_COUNT
            cell.fill = GROUP_FILL if (r == 1 or merged_vertical) else SUB_FILL
            cell.alignment = CENTER
            cell.border = THIN


def make_row(emp_code, name, dept, position, job_type,
             base, bonus, meal, car, childcare,
             np, hi, ei, ltc, income_tax, local_tax,
             student_loan=0, settlement_ins=0, rent_support=0) -> list:
    total_pay = base + bonus + meal + car + childcare
    total_ded = np + hi + ei + ltc + income_tax + local_tax + student_loan + settlement_ins + rent_support
    net = total_pay - total_ded
    return [
        emp_code, name, dept, position, job_type,
        base, bonus, meal, car, childcare, total_pay,
        np, hi, ei, ltc, income_tax, local_tax, student_loan, settlement_ins, rent_support, total_ded,
        net,
    ]


def write_sheet(ws, rows: list[list], client_name: str, period: str) -> None:
    ws.title = f"{client_name}-{period.replace('-', '')}"[:31]
    build_headers(ws)

    totals = [0] * (COL_COUNT - INFO_COLS)
    for idx, row in enumerate(rows, start=3):
        ws.append(row)
        ws.row_dimensions[idx].height = 21
        for c in range(1, COL_COUNT + 1):
            cell = ws.cell(idx, c)
            cell.font = DATA_FONT
            cell.border = THIN
            if c > INFO_COLS:
                cell.number_format = "#,##0"
                cell.alignment = RIGHT
                val = row[c - 1]
                if isinstance(val, (int, float)):
                    totals[c - INFO_COLS - 1] += val
            else:
                cell.number_format = "@"
                cell.alignment = LEFT

    sum_row = 3 + len(rows)
    ws.cell(sum_row, 1, "합계")
    ws.merge_cells(start_row=sum_row, start_column=1, end_row=sum_row, end_column=INFO_COLS)
    ws.cell(sum_row, 1).alignment = CENTER
    for c in range(INFO_COLS + 1, COL_COUNT + 1):
        cell = ws.cell(sum_row, c)
        cell.value = totals[c - INFO_COLS - 1]
        cell.number_format = "#,##0"
        cell.alignment = RIGHT
    for c in range(1, COL_COUNT + 1):
        ws.cell(sum_row, c).font = SUM_FONT
        ws.cell(sum_row, c).fill = SUM_FILL
        ws.cell(sum_row, c).border = SUM_BORDER

    for c in range(1, COL_COUNT + 1):
        ws.column_dimensions[get_column_letter(c)].width = 14


def normal_row(emp: Employee) -> list:
    """정상적인 급여 1건 (수당·공제 자동 계산)."""
    base = emp.base_salary
    bonus = emp.bonus_default
    meal, car, childcare = emp.meal, emp.car, emp.childcare
    total_pay = base + bonus + meal + car + childcare
    non_taxable = meal + car + childcare
    taxable = total_pay - non_taxable

    if emp.income_type == "BUSINESS":
        # 사업소득: 3.3% 원천징수만
        income_tax = int(total_pay * 0.03)
        local_tax = int(income_tax * 0.1)
        return make_row(
            emp.code, emp.name, emp.department, emp.position, emp.job_type,
            base, bonus, meal, car, childcare,
            0, 0, 0, 0, income_tax, local_tax,
        )
    if emp.income_type == "DAILY":
        # 일용직: 4대보험 없이 원천세만
        income_tax = max(0, int((total_pay - 150_000) * 0.06 * 0.55))
        local_tax = int(income_tax * 0.1)
        return make_row(
            emp.code, emp.name, emp.department, emp.position, emp.job_type,
            base, bonus, meal, car, childcare,
            0, 0, 0, 0, income_tax, local_tax,
        )

    d = calc_deductions(taxable)
    return make_row(
        emp.code, emp.name, emp.department, emp.position, emp.job_type,
        base, bonus, meal, car, childcare,
        d["국민연금"], d["건강보험"], d["고용보험"], d["장기요양보험료"],
        d["소득세"], d["지방소득세"],
    )


# ── 정상 월(1~7월) 급여대장 ───────────────────────────────────────────
def generate_normal_month(client: Client, period: str) -> list[list]:
    rows = []
    year, month = int(period[:4]), int(period[5:7])
    period_date = date(year, month, 1)
    for emp in client.employees:
        # 아직 입사 전이면 스킵
        if emp.hired > period_date.replace(day=28):
            continue
        # 퇴사 후면 스킵 (샘플에서는 원래 미리 정의된 퇴사자 없음)
        if emp.resigned_at and emp.resigned_at < period_date:
            continue
        rows.append(normal_row(emp))
    return rows


# ── 8월 오류 케이스 ───────────────────────────────────────────────────
def generate_august_errors(client: Client) -> tuple[list[list], list[str]]:
    """사업자별로 다른 오류 케이스를 심은 8월 급여대장을 생성.

    반환: (엑셀 rows, 오류 시나리오 설명 리스트)
    """
    rows: list[list] = []
    notes: list[str] = []

    if client.biz_number == "123-45-67890":  # (주)새싹식품
        # E1. 지급액계 미일치 — 기본급+상여+수당 합과 지급액계 컬럼값이 다름
        e = client.employees[0]  # 김지훈
        r = normal_row(e)
        r[10] = r[10] - 100_000  # 지급액계 강제로 낮춤
        rows.append(r)
        notes.append("김지훈: 지급액계 컬럼이 실제 합보다 10만원 낮음 (합계 불일치)")

        # E2. 이름 오타 — 마스터: 이서연 → 급여: 이서영
        e = client.employees[1]
        r = normal_row(e)
        r[1] = "이서영"
        rows.append(r)
        notes.append("이서영(원본 이서연): 사원명 오타 → 매칭 실패")

        # E3. 4대보험 요율 오류 — 건강보험이 급여의 10% (정상 3.545%)
        e = client.employees[2]
        r = normal_row(e)
        r[12] = int(e.base_salary * 0.10)   # 건강보험 비정상
        r[14] = int(r[12] * 0.1295)         # 장기요양보험도 자동 이상
        rows.append(r)
        notes.append("박민재: 건강보험 요율 이상 (급여의 10%, 정상은 3.545%)")

        # E4. 신규 입사자 — 마스터에 없는 사원코드
        rows.append(make_row(
            "S099", "신입사원", "생산", "사원", "생산",
            2_400_000, 0, 200_000, 0, 0,
            108_000, 85_000, 21_600, 11_000, 24_000, 2_400,
        ))
        notes.append("신입사원(S099): 마스터에 없는 신규 입사자")

        # 나머지 정상
        for emp in client.employees[3:]:
            rows.append(normal_row(emp))

    elif client.biz_number == "123-45-67891":  # 하늘IT컨설팅
        # E1. 사원코드 중복 — H002가 2번 등장
        for emp in client.employees:
            rows.append(normal_row(emp))
        e_dup = client.employees[1]
        r_dup = normal_row(e_dup)
        r_dup[1] = "오지영"  # 같은 사람 재출현 형태
        rows.append(r_dup)
        notes.append("오지영(H002): 사원코드·사원명 중복 등장 2건")

        # E2. 급여 급증 — 송민수 급여 2배 (변동 감지 대상)
        rows[0][5] = 13_000_000     # 기본급
        rows[0][10] = 13_000_000 + rows[0][7] + rows[0][8] + rows[0][9]  # 지급액계 재계산
        rows[0][11] = int(13_000_000 * NP_RATE)
        rows[0][15] = int(13_000_000 * 0.09)
        rows[0][16] = int(rows[0][15] * 0.1)
        rows[0][20] = sum(rows[0][11:20])
        rows[0][21] = rows[0][10] - rows[0][20]
        notes.append("송민수: 급여 2배 급증 (650만 → 1300만)")

        # E3. 소득세 0 — 정상 산출값이 있어야 하는데 누락
        rows[3][15] = 0
        rows[3][16] = 0
        rows[3][20] = sum(rows[3][11:20])
        rows[3][21] = rows[3][10] - rows[3][20]
        notes.append("문가영: 소득세·지방소득세 0원 (정상 산출값 누락)")

    elif client.biz_number == "123-45-67892":  # 별카페
        # E1. 이미 퇴사한 사람이 여전히 지급 대상 — B004 장서준 6월 퇴사 처리 필요
        # (샘플 상 별도 flag는 없이, 별카페 8월 파일에 있으면 안 되는 사람으로 상정)
        for emp in client.employees:
            rows.append(normal_row(emp))
        notes.append("장서준(B004): 6월 퇴사자로 처리해야 하나 8월 명단에 존재")

        # E2. 식대 20만원 초과 → 비과세 한도 초과 (30만원)
        rows[0][7] = 300_000
        rows[0][10] = rows[0][5] + rows[0][6] + 300_000 + rows[0][8] + rows[0][9]
        rows[0][21] = rows[0][10] - rows[0][20]
        notes.append("차예은: 식대 30만원 (비과세 한도 20만원 초과)")

        # E3. 사원명 빈 셀
        rows[2][1] = ""
        notes.append("사원코드 B003: 사원명 빈 셀 (파싱 필수 필드 누락)")

    elif client.biz_number == "123-45-67893":  # (주)금성물류
        # E1. 차인지급액 계산 오류 — 실제 계산값과 다름
        e = client.employees[0]  # 김철수
        r = normal_row(e)
        r[21] = r[21] + 50_000   # 차인지급액만 5만원 부풀림
        rows.append(r)
        notes.append("김철수: 차인지급액이 지급-공제와 5만원 불일치")

        # E2. 지급액계·공제액계·차인지급액 3중 불일치
        e = client.employees[1]  # 박영수
        r = normal_row(e)
        r[10] = r[10] - 50_000
        r[20] = r[20] + 30_000
        r[21] = r[21] - 80_000
        rows.append(r)
        notes.append("박영수: 지급/공제/차인지급 3중 불일치")

        # E3. 급여 급감 — 최수정 절반 이하
        e = client.employees[2]
        r = normal_row(e)
        r[5] = 1_500_000       # 기본급 반토막
        r[10] = 1_500_000 + r[7] + r[8] + r[9]
        r[11] = int(1_500_000 * NP_RATE)
        r[12] = int(1_500_000 * HI_RATE)
        r[15] = int(1_500_000 * 0.01)
        r[16] = int(r[15] * 0.1)
        r[20] = sum(r[11:20])
        r[21] = r[10] - r[20]
        rows.append(r)
        notes.append("최수정: 급여 급감 (340만 → 150만, 무단 감액 의심)")

        # E4. 신다인 누락 (7월까지 있었는데 8월에 사라짐 = 퇴사 후속 질문 대상)
        for emp in client.employees[3:]:
            if emp.code == "L007":
                continue
            rows.append(normal_row(emp))
        notes.append("신다인(L007): 7월까지 지급 이력 있으나 8월 명단 누락 (퇴사 확인 필요)")

    elif client.biz_number == "123-45-67894":  # 파랑디자인스튜디오
        # E1. 사업소득자에게 근로소득 세율 적용 → 4대보험까지 부과된 상태
        e = client.employees[3]  # 김태윤 (BUSINESS)
        r = normal_row(e)
        # BUSINESS인데 강제로 근로소득처럼 4대보험 부과
        d = calc_deductions(e.base_salary)
        r[11] = d["국민연금"]
        r[12] = d["건강보험"]
        r[13] = d["고용보험"]
        r[14] = d["장기요양보험료"]
        r[15] = d["소득세"]
        r[16] = d["지방소득세"]
        r[20] = sum(r[11:20])
        r[21] = r[10] - r[20]
        rows.append(r)
        notes.append("김태윤: 사업소득자인데 4대보험·근로소득세 적용 (소득구분 오분류)")

        # E2. 주민번호 뒷자리 형식 오류 (별도 시트에 반영)
        notes.append("장아름: 주민번호 뒷자리 형식 오류 (마스터 파일 참고)")

        # E3. 이수민 상여 지급 — 지급액계에 상여 반영 안 됨
        e = client.employees[0]
        r = normal_row(e)
        r[6] = 2_000_000        # 상여 200만
        # 지급액계는 상여 반영 없이 그대로 → 불일치
        rows.append(r)
        notes.append("이수민: 상여 200만원 컬럼에 기재됐으나 지급액계에 미반영")

        # 나머지 정상
        for emp in client.employees:
            if emp.code in {"D001", "D004"}:
                continue
            rows.append(normal_row(emp))

    return rows, notes


# ── 파일 생성 ─────────────────────────────────────────────────────────
def write_clients_master() -> Path:
    """5개 거래처 등록용 xlsx."""
    wb = Workbook()
    ws = wb.active
    ws.title = "거래처마스터"
    headers = ["사업자번호", "상호", "대표자", "연락처", "이메일", "업종", "법인/개인"]
    ws.append(headers)
    for c in range(1, len(headers) + 1):
        cell = ws.cell(1, c)
        cell.font = HEADER_FONT
        cell.fill = GROUP_FILL
        cell.alignment = CENTER
        cell.border = THIN
    for cl in CLIENTS:
        ws.append([
            cl.biz_number, cl.name, cl.representative, cl.phone,
            cl.email or "", cl.industry,
            "법인" if cl.is_corp else "개인",
        ])
    for r in range(2, len(CLIENTS) + 2):
        for c in range(1, len(headers) + 1):
            cell = ws.cell(r, c)
            cell.font = DATA_FONT
            cell.border = THIN
            cell.alignment = LEFT
    widths = [15, 22, 12, 16, 26, 14, 10]
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w
    out = ROOT / "clients.xlsx"
    wb.save(out)
    return out


def write_employee_master(client: Client, folder: Path) -> Path:
    wb = Workbook()
    ws = wb.active
    ws.title = "직원마스터"
    headers = [
        "사원코드", "사원명", "주민번호", "입사일", "부서", "직급", "직종",
        "소득구분", "기본급", "식대(비과세)", "자가운전(비과세)", "육아수당(비과세)",
    ]
    ws.append(headers)
    for c in range(1, len(headers) + 1):
        cell = ws.cell(1, c)
        cell.font = HEADER_FONT
        cell.fill = GROUP_FILL
        cell.alignment = CENTER
        cell.border = THIN

    for emp in client.employees:
        rrn = emp.rrn
        # 파랑디자인스튜디오 장아름은 주민번호 뒷자리 형식 오류
        if client.biz_number == "123-45-67894" and emp.code == "D005":
            rrn = "930928-234567X"  # 마지막 자리 문자
        ws.append([
            emp.code, emp.name, rrn, emp.hired.isoformat(),
            emp.department, emp.position, emp.job_type,
            emp.income_type, emp.base_salary, emp.meal, emp.car, emp.childcare,
        ])

    for r in range(2, len(client.employees) + 2):
        for c in range(1, len(headers) + 1):
            cell = ws.cell(r, c)
            cell.font = DATA_FONT
            cell.border = THIN
            if c >= 9:
                cell.number_format = "#,##0"
                cell.alignment = RIGHT
            else:
                cell.alignment = LEFT

    widths = [10, 12, 16, 12, 10, 10, 12, 10, 12, 12, 14, 14]
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w

    out = folder / "employees.xlsx"
    wb.save(out)
    return out


def write_payroll_file(client: Client, period: str, folder: Path,
                       rows: list[list]) -> Path:
    wb = Workbook()
    ws = wb.active
    write_sheet(ws, rows, client.name, period)
    fname = f"{client.name}-{period.replace('-', '')}.xlsx"
    out = folder / fname
    wb.save(out)
    return out


def main() -> None:
    ROOT.mkdir(exist_ok=True)
    print(f"샘플 생성 위치: {ROOT}")

    master_path = write_clients_master()
    print(f"  거래처 마스터: {master_path.relative_to(ROOT.parent)}")

    all_notes: dict[str, list[str]] = {}
    for client in CLIENTS:
        folder = ROOT / client.biz_number
        folder.mkdir(exist_ok=True)

        emp_path = write_employee_master(client, folder)
        print(f"  [{client.name}] 직원마스터: {emp_path.relative_to(ROOT.parent)}")

        for month in range(1, 8):  # 2026-01 ~ 2026-07
            period = f"2026-{month:02d}"
            rows = generate_normal_month(client, period)
            p = write_payroll_file(client, period, folder, rows)
            print(f"  [{client.name}] {period}: {p.name} ({len(rows)}명)")

        # 8월 = 오류 케이스
        rows, notes = generate_august_errors(client)
        p = write_payroll_file(client, "2026-08", folder, rows)
        print(f"  [{client.name}] 2026-08 (오류 포함): {p.name} ({len(rows)}명)")
        all_notes[client.name] = notes

    # 오류 케이스 요약 문서
    readme = ROOT / "README-8월오류케이스.md"
    lines = ["# 2026-08 급여대장 오류 케이스\n"]
    lines.append("각 거래처 8월 파일에 심어진 오류/이상 케이스 목록입니다.\n")
    for name, notes in all_notes.items():
        lines.append(f"\n## {name}\n")
        for n in notes:
            lines.append(f"- {n}")
    readme.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\n오류 케이스 요약: {readme.relative_to(ROOT.parent)}")


if __name__ == "__main__":
    main()
