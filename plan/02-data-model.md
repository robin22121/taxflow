# 핵심 데이터 모델

> plan.md §3.1 분리본. SmartA 급여대장 24컬럼 양식 기준으로 설계된 데이터 모델 개념도.

---

## 개념도

```
세무사사무소
   │
   └── 거래처 (Client)
         │  ├── 사업자번호, 법인/개인 구분 (원천징수이행상황신고서 A01/A02 분류용)
         │
         ├── 직원/소득자 마스터 (Employee)
         │     ├── 사원코드, 사원명, 부서, 직급, 직종
         │     ├── 주민번호(암호화), 입사일, 퇴사일
         │     ├── 소득구분 (근로/사업/기타/일용/퇴직)
         │     └── 사업소득 업종코드 (940100~940929, 사업소득자인 경우)
         │
         ├── 사업소득 업종코드 마스터 (BusinessTypeCode) [참조 테이블]
         │     ├── 코드 (940100, 940302, 940906 등 40종)
         │     ├── 종목명 (저술가, 배우, 보험설계사 등)
         │     └── 기본 세율 (3% / 20% / 5%)
         │
         └── 월별 신고 (MonthlyFiling)
               │
               ├── 수집 세션 (CollectionSession)
               │     ├── 발송 알림톡 기록
               │     ├── 응답 수신 로그 (카톡/통화/엑셀)
               │     └── AI 파싱 결과
               │
               ├── 직원별 인건비 항목 (PayrollEntry) — SmartA 급여대장 양식 기준
               │     │
               │     │  [인적사항]
               │     ├── 사원코드 (employee_code)
               │     ├── 사원명 (name)
               │     ├── 부서 (department)
               │     ├── 직급 (position)
               │     ├── 직종 (job_type)
               │     │
               │     │  [수당]
               │     ├── 기본급 (base_salary)
               │     ├── 상여 (bonus)
               │     ├── 식대 (meal_allowance) — 비과세
               │     ├── 자가운전보조금 (car_allowance) — 비과세
               │     ├── 육아수당 (childcare_allowance) — 비과세
               │     ├── 지급액계 (total_payment) — 자동 합산
               │     │
               │     │  [공제]
               │     ├── 국민연금 (national_pension)
               │     ├── 건강보험 (health_insurance)
               │     ├── 고용보험 (employment_insurance)
               │     ├── 장기요양보험료 (long_term_care)
               │     ├── 소득세 (income_tax)
               │     ├── 지방소득세 (local_income_tax)
               │     ├── 학자금상환액 (student_loan_repayment)
               │     ├── 연말정산소득세 (year_end_income_tax)
               │     ├── 연말정산지방소득세 (year_end_local_tax)
               │     ├── 중도정산소득세 (mid_term_income_tax)
               │     ├── 중도정산지방소득세 (mid_term_local_tax)
               │     ├── 공제액계 (total_deduction) — 자동 합산
               │     │
               │     │  [결과]
               │     ├── 차인지급액 (net_payment) — 지급액계 - 공제액계
               │     │
               │     │  [매칭·검증]
               │     ├── 직원 매칭 결과 (MATCHED / NEW / RESIGNED / AMBIGUOUS)
               │     ├── 소득구분 (WAGE/BUSINESS/OTHER/DAILY/RETIREMENT)
               │     ├── 국세청 A코드 (A01~A99)
               │     └── 검증 상태
               │
               └── 출력 양식 (OutputReport)
                     ├── SmartA 급여대장 엑셀 (Phase 1 — 24컬럼, 첨부 양식 동일)
                     ├── 급여(임금)명세서 — 직원별 PDF+이미지 (Phase 1, 번들)
                     ├── 간이지급명세서 — 근로소득 (Phase 1)
                     ├── 간이지급명세서 — 사업소득 (Phase 1)
                     ├── 간이지급명세서 — 기타소득 (Phase 3)
                     ├── 일용근로소득 지급명세서 (Phase 3)
                     └── 원천징수이행상황신고서 (Phase 2~3)
```

> **v3.0 변경**: SmartA 급여대장 양식(24컬럼) 기준으로 데이터 모델 전면 재설계.
> PayrollEntry가 수당 항목별(기본급/상여/식대/자가운전보조금/육아수당) + 공제 항목별(4대보험+세금+정산항목) 개별 저장.
> 대시보드 화면 표시 구조와 엑셀 다운로드 양식이 SmartA 급여대장과 1:1 대응.

> **v2.2 변경**: NAHAGO(나하고) 분석 결과 반영 — 급여명세서 자동 교부 번들 피처 추가.

## 관련 문서

- 엑셀 출력 양식: `04-excel-outputs.md`
- 마스터 임포트 흐름: `05-master-import.md`
- 4대보험 데이터 재사용: `06-insurance.md`
