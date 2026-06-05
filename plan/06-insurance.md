# 4대보험 관리 — 별도 메뉴 + 월별신고 탭

> plan.md §3.8 분리본. 국민연금 EDI 가이드북 정독 결과 반영. v3.3에서 "별도 사이드바 메뉴 승격" 결정.

---

## 1. UI/UX 컨셉

기존 *월별신고* 페이지의 거래처 상세에서 원천세/4대보험을 탭 전환하던 구조에 더해, **별도 사이드바 메뉴 "4대보험"으로 승격** (v3.3, 제품 오너 결정).

```
[월별신고 페이지] → 거래처 목록(세션 카드) → 거래처 클릭 → 거래처 상세
        ├─ 탭 ①  [원천세 관리]   = 기존 급여데이터 관리
        │        · AI 추출 결과(이름·금액, 행 클릭 시 세부 펼침)
        │        · SmartA 급여대장 엑셀 / 간이지급명세서 / 급여명세서 다운로드
        │
        └─ 탭 ②  [4대보험 관리]  = 그 달 리포트할 신고서 내역
                 · 자격취득 대상자  (NEW_HIRE_SUSPECTED 또는 입사일 귀속월)
                 · 자격상실 대상자  (RESIGNATION_SUSPECTED 또는 퇴사일 귀속월)
                 · 보수월액 변경 대상자 (전월 대비 변동 — 국민연금은 20%↑만)
                 · [4대보험 통합 다운로드] (3시트 단일 워크북, 기존 구현)
                 · EDI 제출 상태/가이드 (Phase 2~3)
```

[별도 메뉴 "4대보험"]: `/dashboard/insurance` — 월(filing) 선택 → 거래처별 자격취득/상실/변경 건수 카드 + 통합 다운로드 버튼 + 거래처 상세 탭 진입 링크.

두 탭 모두 **동일 거래처·동일 귀속월(MonthlyFiling/CollectionSession)** 데이터에서 파생 — 신규 스키마 불필요(기존 `PayrollEntry`/`Employee`). 4대보험 탭은 기존 `insurance_excel.py`(자격취득/상실/보수월액변경) 결과를 거래처별로 화면 표기 + 다운로드.

---

## 2. 국민연금 EDI 가이드북 분석 반영

### (a) 운영 모델 — EDI 업무대행서비스 (가이드북 p125~132)

세무사사무소가 **업무대행기관**(세무사·회계사·노무사·경영지도사·행정사·변호사)으로 **1인 업무대행기관번호**(사업자등록번호10+구분코드9, 11자리) 발급 → 업무대행기관 지정 → 위탁사업장(거래처) 등록(거래처 서명 받은 *별지4호* 신청서 첨부) → 업무대행기관 공동인증서로 EDI 로그인 후 **'사업장 전환'**으로 위탁사업장별 신고. 무료·24시간·비회원제. 범위: 자격취득/상실/내용변경/기준소득월액변경 등 모든 신고·처리결과 확인.

→ **우리 제품의 4대보험 자동화는 이 업무대행 구조 위에서 동작** (Phase 2~3 RPA/파일 대량신고 대상).

### (b) 신고서 필드·코드 (양식 정합용)

- **자격취득**: 소득월액(비과세 제외)·취득일·**취득부호**·취득월납부여부·특수직종·직역연금부호.
  - 취득부호 = `01`18세이상당연 `03`18세미만 `09`전입 `11`대학강사 `12`월60h미만신청 `14`일용·단시간 `15`상실취소
- **자격상실**: 상실일·초일취득상실자 납부여부·**상실부호**(`3` 사용관계종료=통상 퇴사)·당해연도 보수총액·산정월수·전년도 보수총액·산정월수(전년 연말정산 미실시 시)
- **기준소득(보수)월액 변경**:
  - 국민연금은 **20% 이상 변동 시에만** + **근로자 동의서 필수**
  - 기준소득월액 한도 **400,000 ~ 6,370,000원** (2025.7~2026.6)
  - 건강/고용/산재는 변경 시마다 가능
- **이직확인서(고용보험)**: 취득일·피보험단위 산정대상기간(180일)·임금내역·평균/통상임금·1일 소정근로시간·상실사유 구분코드·구체적 사유
- **신고서 처리결과**: 신고일·접수번호·서식명·처리상태(정상/오류)·확인여부

### (c) 파일 대량신고

- 국민연금 EDI는 **[파일신고업로드] = 엑셀 대량신고 + [파일사양서]** 를 공식 제공(자격취득/상실 등)
- → 일괄/RPA 자동신고의 **공식 경로 존재 확인**
- ⚠️ 단 **파일사양서(엑셀 컬럼 레이아웃) 본문은 가이드북에 없고 EDI 포털에서 별도 다운로드** → 정확한 컬럼 규격 미확보(추측 금지). 보수월액변경은 웹EDI 매뉴얼에 일괄 레이아웃이 일부 문서화됨(research.md §8 참고)

---

## 3. 로드맵 매핑

- **Phase 1 (구현 완료/예정)**: 4대보험 관리 탭 + 신고서 3종 화면 표기·통합 다운로드 (기존 `insurance_excel.py` 재사용, UI 추가)
- **Phase 2~3**: EDI 업무대행 기반 **파일 대량신고(엑셀) 자동 업로드 + 처리결과 회수**. 전제: 업무대행기관번호 발급 + 파일사양서 확보 + 공동인증서 로컬 처리(에이전트)

---

## 4. 미확보 갭 (정직)

- 국민연금 EDI **파일사양서**(엑셀 대량신고 컬럼·자릿수) — 포털 다운로드 필요, 미확보
- 취득부호/상실부호 **전체 코드표** — 가이드북엔 주요 부호만(취득 01~15 일부, 상실 3 등). 전체표는 공단 서식/포털 확인 필요
- `edi_guide.pdf`는 **국민연금 EDI 전용** — 건강/고용/산재는 국민연금 입력값 자동 표출 구조이나, 기관별 고유 항목·사양서는 각 공단 확인 필요

---

## 5. v3.3 갱신 (2026-05-20 — 상세화 스코프·코드 실측)

### 확정 스코프 (4종 모두 진행)

1. **대상자별 상세 필드 확장**(행 펼침): (b)항 신고서 필드 노출 — 취득/상실부호·취득일/상실일·보수월액(비과세 제외)·4대보험 사용자부담분·변경전/후·사유
2. **보수월액변경 판정 정교화**: 국민연금 20%↑만 + 근로자 동의서 안내 + 한도 400K~6,370K, 건강/고용/산재는 변경 시마다. 보험별 분리
3. **EDI 제출 상태·가이드 섹션 신설**: "Phase 2~3" 자리표시를 (a)(b)(c) 기반 화면 안내로(업무대행 구조·파일 대량신고 경로·미확보 갭 정직 표기)
4. **별도 사이드바 메뉴 승격**: `dashboard/layout.tsx` `NAV_ITEMS`에 "4대보험" 추가 + 신규 라우트

### 코드 실측 제약 (정직 — 미확보 갭에 추가)

- **Employee 모델 미보유 컬럼**: 취득부호·상실부호·특수직종·직역연금·생년월일·주소·외국인·대표자여부. 현재 모델은 `name·rrn_encrypted·rrn_last4·employee_code·business_type_code·hired_at·resigned_at·status`만. → **본 단계에서 DB 마이그레이션 비진행**. 모델 미보유 코드값은 화면 "기본값/—" + 엑셀/EDI 단계 확정으로 정직 표기
- **산재보험은 `tax_calc.calculate_social_insurance`에 없음** — 반환 `SocialInsurance`는 국민연금·건강보험·장기요양·고용보험 4종만. 보수월액변경 엑셀은 산재를 `cur` 그대로 사용. 화면 상세 패널도 4종만 정확 노출
- **판정 로직 프론트/백엔드 이중화**: 프론트 `InsuranceTab`엔 국민연금 20% 규칙 **없음**(`prev≠cur`만), 백엔드 `_change_payload`엔 있음 → 화면/엑셀 분류가 어긋남. 단일화 필요 (D1)
- **`PayrollEntryOut`에 employee 필드 없음** (hired_at/resigned_at/rrn_last4 등) → 화면 상세 표기 데이터 부재

### 설계 결정 (확정 — 2026-05-20)

- **(D1) 데이터 공급: JSON 요약 엔드포인트 신설** ✅
  - `/filings/{filing_id}/insurance-summary?client_id=` (GET) — 자격취득/상실/보수월액변경 분류 + 대상자별 상세 필드(취득/상실일·보수월액(비과세 제외)·4대보험 사용자부담분·변경전/후·사유·NPS 20% 판정·한도 체크) JSON 반환
  - 구현 방식: `insurance_excel.py`의 payload 빌더를 두 단계로 분리 — (1) 구조화된 `InsuranceTarget` dataclass 빌더(공유 분류·판정 단일 소스) → (2) 엑셀 어댑터가 이를 _SheetPayload로 변환. 엑셀 출력 컬럼·머신 포맷은 동일 유지(회귀 없음)
- **(D2) 별도 메뉴 화면: 월 → 거래처별 목록** ✅
  - 상단 `NAV_ITEMS`에 "4대보험" 추가 → `/dashboard/insurance` 라우트. 월(filing) 선택 → 거래처별 자격취득/상실/변경 건수 카드 + 통합 다운로드 버튼 + 기존 거래처 상세 탭 진입 링크. `useFilings/useClients` + 신규 요약 엔드포인트 재사용

### 기술 메모

- `frontend/package.json` next **16.2.4** + `frontend/AGENTS.md` "training data와 다른 버전" 경고 → 새 라우트 추가 시 `frontend/node_modules/next/dist/docs/01-app/` 우선 정독

### 정독 위치 (다음 세션 핸드오프)

- `frontend/src/app/dashboard/filings/[id]/page.tsx:835-932` `InsuranceTab` (acq=NEW_HIRE_SUSPECTED only · loss=RESIGNATION_SUSPECTED only · chg=prev≠cur, 20% 규칙 누락)
- `frontend/src/lib/types.ts:137-166` `PayrollEntry` (employee 객체 없음, employee_id만)
- `frontend/src/app/dashboard/layout.tsx:12-15` `NAV_ITEMS`
- `backend/app/services/insurance_excel.py` (payload 빌더 3종 + 통합 워크북; 보수월액 머신 포맷 16컬럼)
- `backend/app/models/employee.py` Employee · `backend/app/models/payroll.py:22-89` PayrollEntry/MatchStatus
- `backend/app/api/filings.py:603-635` GET entries · `:886-1006` 4대보험 4개 라우트 · `_wage_entries_for_filing` (WAGE+employee_id, selectinload(employee))
- `backend/app/schemas/filings.py:47-77` `PayrollEntryOut` (employee 미포함)
- `backend/app/services/tax_calc.py:251-273` `calculate_social_insurance` → `SocialInsurance(np/hi/ei/ltc)` (산재 없음)

---

### 3.9 거래처별 지급항목·4대보험 기본 세팅 (Per-Client Payroll Defaults)

> 거래처관리 메뉴에서 **업체별 지급항목 기본금액 + 4대보험 적용 정책**을 설정.
> 고객이 매월 보내는 원시파일이 항목별로 값을 명시하지 않아도, 거래처 세팅값으로 자동 채워서 급여명세서를 생성한다.

#### 배경 — 왜 거래처별로 다른가

- **식대·자가운전·육아수당은 회사 정책에 따라 고정값이 다름**:
  거래처 A는 식대 매월 100,000원, 거래처 B는 식대 200,000원(비과세 한도)
- **4대보험도 사업장별로 적용/감면 정책이 상이**:
  두루누리 사회보험료 지원(10인 미만), 산재보험 업종별 요율, 일부 가입 면제 사업장
- **현재 구현 한계**: `backend/app/api/collect.py`의 비과세 처리 로직(L270~309)이
  "전월 데이터를 복사" 또는 "AI 추출값" 두 가지만 사용 →
  최초 신고이거나 원시파일에 항목이 누락된 경우 0원으로 처리되어 비과세 손실.

#### 세팅값 적용 우선순위 (Iron Rule)

```
[1순위] 고객이 제출한 이번달 원시파일에 해당 항목 값이 있음
        → 원시파일 값을 그대로 사용 (AI 파서가 추출한 cand.meal_amount 등)

[2순위] 원시파일에 값이 없음 (None 또는 누락)
        → 거래처 세팅값(ClientPayrollDefault)을 적용

[기본값] 거래처 세팅값을 처음 만들 때 자동으로 채워주는 추천값
        - 지급항목: 세법상 비과세 한도 최대치 (식대 200,000 / 자가운전 200,000 / 육아수당 200,000)
        - 4대보험: tax_calc.py의 현행 요율로 계산된 금액 (월 급여 기준)
        - 세무사가 거래처 정책에 맞춰 수정 가능
```

> **기존 "전월 데이터 복사" 로직 폐기**: 거래처 세팅값이 명시적 기본값을 제공하므로,
> 전월 PayrollEntry에서 비과세 항목을 복사해오던 fallback은 제거 또는 후순위로 강등.

#### 데이터 모델

```
Client (기존)
  └─ ClientPayrollDefault (1:1, 신규)
        │  [지급항목 기본금액 — 직원 전원 공통 적용]
        ├─ meal_default          (default: 200,000  — 비과세 한도)
        ├─ car_default           (default: 200,000)
        ├─ childcare_default     (default: 200,000)
        │
        │  [4대보험 적용 정책]
        ├─ apply_national_pension (default: True)
        ├─ apply_health_insurance (default: True)
        ├─ apply_employment_insurance (default: True)
        ├─ apply_longterm_care   (default: True)
        │
        │  [요율 오버라이드 — null이면 tax_calc.py 시스템 요율 사용]
        ├─ nps_rate_override     (default: null  → 0.045)
        ├─ hi_rate_override      (default: null  → 0.03545)
        ├─ ltc_rate_override     (default: null  → 0.1295 of HI)
        ├─ ei_rate_override      (default: null  → 0.009)
        │
        │  [두루누리 등 정부 지원]
        └─ govt_support_note     (자유 텍스트, 메모용)
```

> 직원별로 다른 식대/4대보험 금액이 필요한 경우는 우선순위 [1순위]로 처리
> (원시파일에 직원별 명시값이 있으면 그대로 사용) — 거래처 세팅은 어디까지나 "기본값".

#### 적용 지점 (collect.py / imports.py)

`backend/app/api/collect.py` L284~309 의 분기를 다음으로 교체:

```python
defaults = client.payroll_default  # ClientPayrollDefault, 없으면 시스템 기본값 객체

# 지급항목: 원시파일 값 우선, 없으면 거래처 세팅
meal = cand.meal_amount if cand.meal_amount is not None else defaults.meal_default
car = cand.car_amount if cand.car_amount is not None else defaults.car_default
childcare = cand.childcare_amount if cand.childcare_amount is not None else defaults.childcare_default

# 4대보험: 원시파일 값 우선, 없으면 거래처 세팅 요율로 계산
si = calculate_social_insurance_with_overrides(
    monthly_wage=taxable,
    income_type=cand.income_type,
    overrides=defaults,  # rate overrides + apply flags
)
si_np = cand.np_amount if cand.np_amount is not None else (si.national_pension if defaults.apply_national_pension else 0)
# ... 동일 패턴으로 hi/ei/ltc
```

> AI 파서 스키마(`cand`)에 `np_amount`, `hi_amount`, `ei_amount`, `ltc_amount` 필드 추가 필요 —
> 현재 파서는 4대보험 금액을 추출하지 않음.

#### API 설계

| 메서드 | 경로 | 용도 |
|--------|------|------|
| `GET` | `/clients/{id}/payroll-default` | 현재 세팅값 조회 (없으면 시스템 기본값으로 채워서 반환) |
| `PUT` | `/clients/{id}/payroll-default` | 세팅값 저장/갱신 (upsert) |
| `POST` | `/clients/{id}/payroll-default/reset` | 시스템 기본값(비과세 한도 + 현행 요율)으로 리셋 |

#### UI — 거래처관리 메뉴

`/dashboard/clients/[id]` 상세 페이지에 **"기본 세팅"** 탭 추가 (또는 모달):

```
[기본 세팅 탭]

▣ 비과세 지급항목 기본금액
  식대            [  200,000 ] 원   (세법상 비과세 한도: 200,000)
  자가운전보조금  [  200,000 ] 원   (세법상 비과세 한도: 200,000)
  육아수당        [  200,000 ] 원   (세법상 비과세 한도: 200,000)

▣ 4대보험 적용
  ☑ 국민연금       요율: [ 4.5    ]%  (시스템 기본 4.5%)
  ☑ 건강보험       요율: [ 3.545  ]%  (시스템 기본 3.545%)
  ☑ 장기요양       요율: [12.95   ]%  (건강보험료 대비, 기본 12.95%)
  ☑ 고용보험       요율: [ 0.9    ]%  (시스템 기본 0.9%)

▣ 비고
  [정부지원 등 메모 자유 입력...]

  [ 시스템 기본값으로 리셋 ]    [ 저장 ]
```

#### 산출물 영향

- **급여(임금)명세서**: 비과세 항목·4대보험 금액이 거래처 정책대로 일관되게 표시됨
- **SmartA 급여대장 엑셀**: 식대/자가운전/육아수당 컬럼이 0원으로 비지 않음
- **간이지급명세서 (근로소득)**: 비과세 합계가 정확해져 과세소득 계산 신뢰성 향상

#### 마이그레이션

- 새 테이블 `client_payroll_defaults` 추가 (Alembic 마이그레이션 1건)
- 기존 거래처는 첫 조회 시 시스템 기본값으로 자동 시드 (lazy creation)
- 직원 마스터 임포트(`POST /clients/{id}/import-payroll`) 직후 세팅값 자동 생성 옵션

---
