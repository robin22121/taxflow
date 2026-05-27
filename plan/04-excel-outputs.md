# SmartA 엑셀 + 출력 양식

> plan.md §3.3, §3.5 분리본. SmartA 급여대장 양식 엑셀 생성 + 간이지급명세서·급여명세서·4대보험 신고서 등 출력 양식 전반.

---

## 1. SmartA 급여대장 엑셀 생성 (의사 코드)

SmartA 급여대장 양식에 맞춘 24컬럼 구성:

```python
# SmartA 급여대장 표준 컬럼 (24컬럼, 2행 헤더)
SMARTA_HEADER_ROW1 = {
    "A1:A2": "사원코드",
    "B1:B2": "사원명",
    "C1:C2": "부서",
    "D1:D2": "직급",
    "E1:E2": "직종",
    "F1:K1": "수당",       # 병합
    "L1:W1": "공제",       # 병합
    "X1:X2": "차인지급액",
}

SMARTA_HEADER_ROW2 = [
    # F~K: 수당 세부
    "기본급", "상여", "식대", "자가운전보조금", "육아수당", "지급액계",
    # L~W: 공제 세부
    "국민연금", "건강보험", "고용보험", "장기요양보험료",
    "소득세", "지방소득세", "학자금상환액",
    "연말정산소득세", "연말정산지방소득세",
    "중도정산소득세", "중도정산지방소득세", "공제액계",
]

def generate_smarta_excel(
    payroll_entries: list[PayrollEntry],
    period: str
) -> bytes:
    """
    AI가 정형화한 데이터를 SmartA 급여대장 양식 엑셀로 변환
    - 수당 항목별 분리 (기본급, 상여, 식대, 자가운전보조금, 육아수당)
    - 공제 항목별 분리 (4대보험 + 세금 + 정산항목)
    - SmartA 양식 100% 호환 (24컬럼, 2행 헤더, 하단 합계행)
    """
    workbook = openpyxl.Workbook()
    ws = workbook.active

    # 2행 헤더 구성 (SmartA 병합셀 구조 그대로 재현)
    write_merged_headers(ws, SMARTA_HEADER_ROW1)
    write_sub_headers(ws, row=2, start_col=6, headers=SMARTA_HEADER_ROW2)

    # 데이터 행 (3행부터)
    for entry in payroll_entries:
        ws.append([
            entry.employee_code,       # A: 사원코드
            entry.name,                # B: 사원명
            entry.department,          # C: 부서
            entry.position,            # D: 직급
            entry.job_type,            # E: 직종
            # --- 수당 ---
            entry.base_salary,         # F: 기본급
            entry.bonus,               # G: 상여
            entry.meal_allowance,      # H: 식대
            entry.car_allowance,       # I: 자가운전보조금
            entry.childcare_allowance, # J: 육아수당
            entry.total_payment,       # K: 지급액계
            # --- 공제 ---
            entry.national_pension,    # L: 국민연금
            entry.health_insurance,    # M: 건강보험
            entry.employment_insurance,# N: 고용보험
            entry.long_term_care,      # O: 장기요양보험료
            entry.income_tax,          # P: 소득세
            entry.local_income_tax,    # Q: 지방소득세
            entry.student_loan_repayment,  # R: 학자금상환액
            entry.year_end_income_tax,     # S: 연말정산소득세
            entry.year_end_local_tax,      # T: 연말정산지방소득세
            entry.mid_term_income_tax,     # U: 중도정산소득세
            entry.mid_term_local_tax,      # V: 중도정산지방소득세
            entry.total_deduction,     # W: 공제액계
            entry.net_payment,         # X: 차인지급액
        ])

    # 합계행
    append_summary_row(ws, payroll_entries)

    return save_to_bytes(workbook)
```

구현체: `backend/app/services/payroll_excel.py`, 엔드포인트 `GET /filings/{id}/payroll-excel`.

---

## 2. 출력 양식 다양화 설계 (국세청 서식 기반)

> 국세청 공식 서식 분석 결과(research.md 3.4절)에 따라, SmartA 급여대장 엑셀 1종 외에 간이지급명세서 등 추가 출력이 필요.

### Phase 1에서 생성하는 출력물

**1. SmartA 급여대장 양식 엑셀** (핵심 산출물, `smarta_excel.py` / `payroll_excel.py`)
- SmartA 급여대장 양식 호환 (24컬럼, 2행 헤더, 병합셀, 하단 합계행)
- 수당 5항목 + 공제 12항목 + 차인지급액 구조
- 세무사가 다운로드 → SmartA에 업로드하면 바로 급여대장 반영

**2. 간이지급명세서 (근로소득)** — 별지 제24호의4서식(1)
- 대상: `income_type=WAGE` 항목
- 주요 컬럼: 귀속연월, 성명, 주민등록번호, 근무기간, 급여, 상여, 비과세, 소득세, 지방소득세
- 구현: `simple_statement_excel.py`, `GET /filings/{id}/statement-wage`

**3. 급여(임금)명세서** — 근로기준법 제48조 (번들 피처)
- 대상: 모든 `income_type` (WAGE 중심)
- 주요 항목: 임금 구성항목(기본급·수당·상여), 계산방법, 공제내역(소득세·지방소득세·4대보험), 실지급액
- 생성 시점: 세무사 승인 완료 후 자동 생성
- 발송 채널: 알림톡 > SMS > 이메일 (기존 채널 재활용)
- 구현: `payslip_excel.py`, `GET /filings/{id}/payslips` (직원별 시트, 자동 발송은 미구현)
- **NAHAGO 대비 차별점**: 수임처 사장님·직원이 앱 설치 불필요, 세무사 신고 시 자동 교부

**4. 간이지급명세서 (거주자의 사업소득)** — 별지 제24호의4서식(2)
- 대상: `income_type=BUSINESS` 항목
- 주요 컬럼: 귀속연월, **업종코드**, 성명, 주민등록번호, 지급액, 세율(3%), 소득세, 지방소득세
- 구현: `simple_statement_excel.py`, `GET /filings/{id}/statement-business`

**4-2. 4대 보험 신고서 3종** (구현 완료 — `insurance_excel.py`)
- 자격취득 / 자격상실 / 보수월액 변경 — 자세한 내용은 `06-insurance.md`
- API: `GET /filings/{id}/insurance-acquisition|loss|change`, 통합 `GET /filings/{id}/insurance-combined`(3시트 단일 워크북)
- **통합 다운로드 UX**: "엑셀다운로드"는 무조건 통합 — 미수신/미확인/의심 시 경고창 후 **원천세 일괄(단일 파일) + 4대보험 통합(단일 파일·3시트)** 동시 다운로드

### Phase 3 이후 추가 출력물

**5. 간이지급명세서 (기타소득)** — 소득종류, 필요경비율 적용 필요
**6. 일용근로소득 지급명세서** — 일용직 근무일수·일일비과세(15만원) 처리
**7. 원천징수이행상황신고서** — A코드별 합산, SmartA가 자동 생성하므로 참고용

### 소득구분 코드 매핑 테이블

| TaxFlow IncomeType | 국세청 A코드 | 세율 | 간이지급명세서 |
|---------------------|------------|------|---------------|
| WAGE | A01 (법인) / A02 (개인) | 간이세액표 | 근로소득용 |
| DAILY | A03 | 6% (15만원 초과분) | 일용근로소득용 |
| BUSINESS | A25 | 3% (기본) | 사업소득용 |
| OTHER | A42 | 20% (기본) | 기타소득용 |
| RETIREMENT | A22 | 퇴직소득세 테이블 | 별도 |
