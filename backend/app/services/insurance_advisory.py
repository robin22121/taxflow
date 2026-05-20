"""산재·고용보험 부과·정산 실무 어드바이저 — 노무사 수준 선제 안내.

근거: 근로복지공단 「산재·고용보험 가입 및 부과업무 실무편람 2026」(238p).
국민연금 EDI 가이드북이 다루지 못하던 **근로복지공단 관할(산재·고용)** 영역을
거래처(사업주)에게 세무사가 노무사 수준으로 선제 안내하기 위한 지식·판정 로직.

설계 원칙 (기존 insurance_excel 과 동일):
- 스키마 변경 없음 — 기존 PayrollEntry / Employee 필드만 사용.
- 분류 기준은 insurance_excel.py 와 동일하게 맞춤(취득/상실/변경 일관성).
- 모든 수치·기한에 실무편람 페이지(p.N) 인용 — 추측 금지.

산출물(JSON 직렬화 가능 dict):
- alerts   : 거래처 데이터로 감지한 신고기한·정산 D-day 알림(긴급순 정렬)
- durunuri : 두루누리 사회보험료 지원 후보 + 예상 지원액
- triggers : 세무사 → 거래처 선제 안내 트리거(신규입사·퇴사·보수변동·일용직 등)
- reference: 화면 접이식 "산재·고용보험 실무 가이드"용 정적 지식(기한표·요율·지원·과태료)
"""

from __future__ import annotations

import calendar
from datetime import date

from app.models.payroll import IncomeType, MatchStatus, PayrollEntry

# ── 2026 핵심 상수 (실무편람 인용) ───────────────────────────────────────────
DURUNURI_PAY_CEILING = 2_700_000  # 두루누리 월평균보수 상한(미만) (p.6, p.78)
DURUNURI_SIZE_LIMIT = 10  # 두루누리 근로자 피보험자 수(미만) (p.6, p.78)
DURUNURI_WORKER_MAX = 37_720  # 근로자 1인 월 최대 지원(사업주21,160+근로자16,560) (p.6, p.78)
EI_TOTAL_RATE = 0.018  # 실업급여 노·사 합계요율 0.9%+0.9% (p.7, p.40)
DURUNURI_SUPPORT_RATE = 0.80  # 고용보험료 80% 지원 (p.6, p.78)

_REPORT_BY_15TH = "고용한(이직한) 달의 다음 달 15일까지"


def _next_month_15th(period: str) -> date:
    """귀속월(YYYY-MM) → 자격취득·상실·근로내용확인 신고기한(다음 달 15일)."""
    y, m = (int(x) for x in period.split("-"))
    y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return date(y, m, 15)


def _next_month_end(period: str) -> date:
    """귀속월 → 노무제공자 월 보수액 신고기한(다음 달 말일) (p.4, p.115)."""
    y, m = (int(x) for x in period.split("-"))
    y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return date(y, m, calendar.monthrange(y, m)[1])


def _in_period(d: date | None, period: str) -> bool:
    return d is not None and d.strftime("%Y-%m") == period


def _is_acquisition(e: PayrollEntry, period: str) -> bool:
    emp = e.employee
    return e.match_status == MatchStatus.NEW_HIRE_SUSPECTED or (
        emp is not None and _in_period(emp.hired_at, period)
    )


def _is_loss(e: PayrollEntry, period: str) -> bool:
    emp = e.employee
    return e.match_status == MatchStatus.RESIGNATION_SUSPECTED or (
        emp is not None and _in_period(emp.resigned_at, period)
    )


def _is_change(e: PayrollEntry, period: str) -> bool:
    if e.prev_amount is None or e.prev_amount == e.total_amount:
        return False
    return not (_is_acquisition(e, period) or _is_loss(e, period))


# ── 화면 접이식 "실무 가이드" 정적 지식 (근로복지공단 2026 실무편람) ──────────
REFERENCE = {
    "source": "근로복지공단 「산재·고용보험 가입 및 부과업무 실무편람 2026」",
    "channel": "고용·산재보험 토탈서비스 https://total.comwel.or.kr · 고객센터 1588-0075",
    "deadlines": [
        {"item": "보험관계 성립신고", "due": "성립일(최초 근로자 채용일)부터 14일 이내", "basis": "p.2·p.26"},
        {"item": "근로자 고용신고 / 피보험자격 취득신고", "due": "고용한 달의 다음 달 15일까지", "basis": "p.2·p.26·p.36"},
        {"item": "근로자 자격상실 / 피보험자격 상실신고", "due": "이직한 달의 다음 달 15일까지", "basis": "p.2·p.41"},
        {"item": "일용근로자 근로내용확인신고서", "due": "지급한 달의 다음 달 15일까지(월별 각각)", "basis": "p.2·p.44"},
        {"item": "노무제공자 월 보수액 신고(실보수 직종)", "due": "노무제공한 달의 다음 달 말일까지", "basis": "p.4·p.115"},
        {"item": "전보·휴직·정보변경 신고", "due": "사유발생일부터 14일 이내", "basis": "p.2·p.46~48"},
        {"item": "보수총액신고(연도정산)", "due": "매년 3월 15일까지 → 4월분 보험료에 정산 합산고지", "basis": "p.2·p.56~58"},
        {"item": "보험관계 소멸신고·소멸 보수총액신고", "due": "소멸일부터 14일 이내", "basis": "p.2·p.28~29"},
        {"item": "(건설·벌목) 개산·확정보험료 신고·납부", "due": "매년 3월 31일까지", "basis": "p.5·p.81~83"},
    ],
    "rates_2026": [
        {"item": "고용보험 실업급여", "value": "근로자 0.9% + 사업주 0.9% (계 1.8%)", "basis": "p.7·p.40"},
        {"item": "고용안정·직업능력개발(사업주)", "value": "150인 미만 0.25% / 우선지원 0.45% / ~1,000인 0.65% / 1,000인↑ 0.85%", "basis": "p.7·p.40"},
        {"item": "산재보험료율", "value": "업종별 5~185‰, 평균 14.1‰ + 출퇴근재해 0.6‰(전 업종)", "basis": "p.7·p.8"},
        {"item": "임금채권부담금", "value": "0.9‰ (2026.1.1.부터 0.6→0.9‰ 인상)", "basis": "p.7·p.47·p.86"},
        {"item": "예술인·노무제공자 고용보험", "value": "각 0.8% (계 1.6%), 노·사 1/2씩 부담", "basis": "p.100·p.130"},
        {"item": "보수의 범위", "value": "소득세법상 근로소득 − 비과세(식대·자가운전·보육수당 등 산재·고용 전부 미부과)", "basis": "p.38·p.205~209"},
    ],
    "durunuri": {
        "title": "두루누리 사회보험료 지원",
        "rules": [
            "대상: 근로자 피보험자 10인 미만 사업 + 월평균보수 270만원 미만",
            "지원: 고용보험료의 80% (근로자 1인 월 최대 37,720원), 최대 36개월",
            "요건: 신청일 직전 1년간 고용·국민연금 자격취득 이력 없는 신규가입자",
            "제외: 전년도 재산 과세표준 6억원↑ 또는 종합소득 4,300만원↑",
        ],
        "basis": "p.6·p.78~82",
    },
    "penalties": [
        {"item": "보험관계·보수총액 미신고/거짓", "value": "1차 100 / 2차 200 / 3차↑ 300만원", "basis": "p.164"},
        {"item": "고용·고용종료 미신고(지연 포함)", "value": "1명당 3만원(거짓 5만원), 100만원 한도", "basis": "p.164"},
        {"item": "연체금", "value": "납부기한 후 일할 가산, 최대 5% 이내", "basis": "p.166"},
        {"item": "산재 미가입 중 재해", "value": "지급 보험급여의 50% 징수(보험료 미납 중 재해 10%)", "basis": "p.167~168"},
    ],
    "agency": (
        "개인세무사는 고용노동부 인가교육(4시간, 한국세무사회 무료) 이수 후 "
        "보험사무대행기관 인가 가능. 상시근로자 30명 미만 사업장은 무료 대행 "
        "(보험관계·자격취득상실·월보수·근로내용확인·보수총액 신고 대행 가능, "
        "산재 급여청구·실업급여 신청은 대행 불가). 수임신고는 수임일부터 14일 이내."
    ),
    "agency_basis": "p.9·p.170~175·p.191",
}


def build_advisory(
    entries: list[PayrollEntry],
    period: str,
    client_name: str,
    *,
    today: date | None = None,
) -> dict:
    """거래처의 귀속월 데이터로 산재·고용보험 선제 안내를 생성한다.

    entries 는 해당 거래처·귀속월의 **전 소득구분** PayrollEntry (일용·사업소득 포함).
    """
    today = today or date.today()
    by15 = _next_month_15th(period)
    by_end = _next_month_end(period)
    d_by15 = (by15 - today).days

    acq = [e for e in entries if e.income_type == IncomeType.WAGE and _is_acquisition(e, period)]
    loss = [e for e in entries if e.income_type == IncomeType.WAGE and _is_loss(e, period)]
    chg = [e for e in entries if e.income_type == IncomeType.WAGE and _is_change(e, period)]
    daily = [e for e in entries if e.income_type == IncomeType.DAILY]
    biz = [e for e in entries if e.income_type == IncomeType.BUSINESS]
    wage_count = sum(1 for e in entries if e.income_type == IncomeType.WAGE)

    alerts: list[dict] = []

    def _add(cond, *, title, detail, due, d_day, basis, severity):
        if cond:
            alerts.append({
                "title": title, "detail": detail,
                "due": due.isoformat(), "d_day": d_day,
                "basis": basis, "severity": severity,
            })

    sev15 = "danger" if d_by15 < 0 else ("warn" if d_by15 <= 7 else "info")
    _add(
        acq,
        title=f"자격취득(고용)신고 — {len(acq)}명",
        detail=(
            f"신규 입사 {len(acq)}명: (산재)근로자 고용신고·(고용)피보험자격 취득신고를 "
            f"{_REPORT_BY_15TH} 제출. 최초 가입 사업장이면 보험관계 성립신고(성립일 14일 내)를 "
            "동시에 해야 당월 보험료가 적기 산정됩니다."
        ),
        due=by15, d_day=d_by15, basis="p.2·p.26·p.36", severity=sev15,
    )
    _add(
        loss,
        title=f"자격상실(고용종료)신고 + 퇴직정산 — {len(loss)}명",
        detail=(
            f"퇴사 {len(loss)}명: 자격상실(고용종료)신고를 {_REPORT_BY_15TH} 제출하고, "
            "신고서에 연간 보수총액을 기재해 퇴직정산하세요. 정산보험료가 그 달 보험료를 초과하면 "
            "2등분되어 다음 달까지 합산고지됩니다."
        ),
        due=by15, d_day=d_by15, basis="p.2·p.41·p.58~60", severity=sev15,
    )
    _add(
        daily,
        title=f"일용근로자 근로내용확인신고서 — {len(daily)}명",
        detail=(
            f"일용직 {len(daily)}명: 근로내용확인신고서를 월별로 각각, {_REPORT_BY_15TH} 제출. "
            "사업자등록번호 기재 시 국세청 일용근로소득지급명세서로 갈음됩니다."
        ),
        due=by15, d_day=d_by15, basis="p.2·p.44~45", severity=sev15,
    )
    _add(
        chg,
        title=f"월평균보수 변경 검토 — {len(chg)}명",
        detail=(
            f"보수 변동 {len(chg)}명: 월평균보수 변경신고는 임의이나, 미신고 시 차액은 "
            "다음연도 3월 15일 보수총액신고 또는 퇴직정산으로 정산됩니다(국민연금은 20%↑ 변동 시에만 변경 가능)."
        ),
        due=by15, d_day=d_by15, basis="p.69", severity="info",
    )

    d_biz = (by_end - today).days
    _add(
        biz,
        title=f"노무제공자(특고)·사업소득 {len(biz)}명 — 보험관계 확인",
        detail=(
            f"사업소득 지급 {len(biz)}명: 보험설계사·택배·화물·SW프리랜서 등 노무제공자 18개 직종에 "
            "해당하면 근로자와 **별도 관리번호**로 성립신고(14일 내)하고 실보수 직종은 월 보수액을 "
            "다음 달 말일까지 신고, 보험료는 사업주·종사자 각 1/2 원천공제합니다."
        ),
        due=by_end, d_day=d_biz,
        basis="p.4·p.110~115·p.128~134",
        severity="warn" if d_biz <= 7 else "info",
    )

    # 연도정산(보수총액신고) — 매년 3.15. 귀속연도 기준으로 D-day 계산.
    yr = today.year
    ann_due = date(yr, 3, 15)
    if today > ann_due:
        ann_due = date(yr + 1, 3, 15)
    d_ann = (ann_due - today).days
    alerts.append({
        "title": "연도정산 — 전년도 보수총액신고",
        "detail": (
            "매년 3월 15일까지 전년도 근로자별 보수총액을 신고하면 정산결과가 4월분 월별보험료에 "
            "합산고지됩니다(초과 시 4·5월 2분할). 미신고 시 직권조사부과·두루누리 지원 제한이 발생할 수 있습니다."
        ),
        "due": ann_due.isoformat(), "d_day": d_ann,
        "basis": "p.2·p.56~58", "severity": "warn" if 0 <= d_ann <= 21 else "info",
    })

    _sev = {"danger": 0, "warn": 1, "info": 2}
    alerts.sort(key=lambda a: (_sev[a["severity"]], a["d_day"]))

    # ── 두루누리 후보 ─────────────────────────────────────────────────────
    durunuri_candidates = [
        {
            "name": e.raw_name,
            "monthly_pay": e.total_amount,
            "est_support": min(
                int(round(e.total_amount * EI_TOTAL_RATE * DURUNURI_SUPPORT_RATE)),
                DURUNURI_WORKER_MAX,
            ),
        }
        for e in acq
        if 0 < e.total_amount < DURUNURI_PAY_CEILING
    ]
    size_ok = wage_count < DURUNURI_SIZE_LIMIT
    durunuri = {
        "eligible_size": size_ok,
        "size": wage_count,
        "candidates": durunuri_candidates,
        "est_monthly_total": sum(c["est_support"] for c in durunuri_candidates),
        "note": (
            "월평균보수 270만원 미만 신규 입사자 기준 추정. 실제 지원은 근로자 10인 미만 사업 + "
            "신청일 직전 1년 미가입 신규가입자 요건 충족 시(재산 6억·종합소득 4,300만원 제외)."
            + ("" if size_ok else " ⚠ 현재 거래처 근로자 수가 10인 이상으로 추정되어 두루누리 대상에서 제외될 수 있습니다.")
        ),
        "basis": "p.6·p.78~82",
    }

    # ── 세무사 → 거래처 선제 안내 트리거 ─────────────────────────────────
    triggers: list[dict] = []
    if acq:
        triggers.append({
            "trigger": f"신규 입사 {len(acq)}명 감지",
            "advice": "자격취득신고 다음 달 15일까지. 사업장 최초 가입 시 보험관계 성립신고(14일) 누락하면 과태료 100만원~ 및 미가입 중 재해 시 산재급여 50% 징수.",
            "basis": "p.26·p.164·p.167",
        })
    if loss:
        triggers.append({
            "trigger": f"퇴사 {len(loss)}명 감지",
            "advice": "자격상실신고 시 보수총액 기재로 퇴직정산. 이후 인센티브 추가지급 등 변동 시 고용종료자 보수총액 수정신고 필요.",
            "basis": "p.41·p.58~60",
        })
    if chg:
        triggers.append({
            "trigger": f"보수 변동 {len(chg)}명 감지",
            "advice": "월평균보수 변경신고 검토(임의). 미신고분은 연도정산·퇴직정산으로 자동 정산되나, 미리 반영하면 정산 추가징수 부담을 줄일 수 있음.",
            "basis": "p.69",
        })
    if daily:
        triggers.append({
            "trigger": f"일용직 {len(daily)}명 사용",
            "advice": "근로내용확인신고서를 월별로 각각 다음 달 15일까지. 일용직은 월 60시간 미만이어도 신고대상.",
            "basis": "p.44~45",
        })
    if biz:
        triggers.append({
            "trigger": f"사업소득 지급 {len(biz)}명",
            "advice": "노무제공자(특고) 18개 직종 해당 여부 확인 — 해당 시 별도 성립·월보수신고, 보험료 노·사 1/2 원천공제.",
            "basis": "p.110~115·p.128~134",
        })
    if durunuri_candidates and size_ok:
        triggers.append({
            "trigger": f"소규모 사업장 저보수 신규 입사 {len(durunuri_candidates)}명",
            "advice": f"두루누리 사회보험료 지원 신청 안내 — 고용보험료 80%, 1인 월 최대 37,720원(추정 월 {durunuri['est_monthly_total']:,}원), 최대 36개월.",
            "basis": "p.78~82",
        })
    if today.month in (1, 2, 3):
        triggers.append({
            "trigger": "연초(1~3월) — 연도정산 시즌",
            "advice": "3월 15일까지 전년도 보수총액신고. 미신고 시 직권조사부과·두루누리 지원 제한. 정산결과는 4월분 보험료 합산.",
            "basis": "p.56~58",
        })

    return {
        "client_name": client_name,
        "period": period,
        "summary": {
            "acquisition": len(acq),
            "loss": len(loss),
            "change": len(chg),
            "daily": len(daily),
            "business": len(biz),
            "wage_count": wage_count,
        },
        "alerts": alerts,
        "durunuri": durunuri,
        "triggers": triggers,
        "reference": REFERENCE,
    }
