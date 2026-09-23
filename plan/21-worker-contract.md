# 근로계약서 발급 · 근로자 열람

> 2026-09-21 초안. 사업주가 근로계약서를 **발급·업로드**하고, 근로자가 자국어 요약으로 **열람·확인**하는 흐름.
> 개요·인증·다국어 파이프라인은 [`19-worker-portal.md`](19-worker-portal.md) 참조.

---

## 1. 목적

- 근로기준법 §17 근로조건 명시 의무의 **디지털 이행 채널**
- 외국인고용법상 **모국어 표기 근로계약서** 요건 충족(요약 자국어 렌더링)
- 계약 미교부 분쟁 예방 — 열람 로그가 교부 증거로 기능

---

## 2. 화면 — 근로자 근로계약서 열람

### 2.1 요약 뷰

```
근로계약서 · 2026-01-15 체결

  고용주    Hanul 식품 (김한을)
  직위      제조 라인 작업자
  기간      2026-01-15 ~ 2028-01-14 (2년)
  근무시간  주 40시간 (월-금 9:00-18:00, 휴게 1시간)
  임금      월 2,300,000원 (기본급 2,200,000 + 식대 76,000 + …)
  연장수당  시간당 통상임금 × 1.5
  야간수당  시간당 통상임금 × 2.0 (22:00-06:00)
  휴일수당  시간당 통상임금 × 1.5
  비자      E-9 (2028-01-14 만료)
  4대보험   국민연금·건강·고용·산재 가입

  [Tiếng Việt로 보기 ▼]      [PDF 원본 다운로드]

  ⚠ 계약서 원본을 확인했나요?
     ● 예, 확인했습니다
     ○ 원본을 받지 못했어요 (사업주에게 문의)
                                    [제출]
```

### 2.2 렌더링 원칙

- 요약은 `EmploymentContract`의 구조화 필드에서 자동 생성.
- **원본 PDF는 번역하지 않음** — 법적 문서는 한국어 원본. 요약만 자국어.
- 요약 자국어 번역은 계약서 등록 시점에 Gemini로 미리 생성해 저장(`translated_summary_json`).
- 신규 언어 추가 시 재번역 작업이 필요하므로 §3 참고.

### 2.3 확인 로그

- 최초 열람 시 `ContractView` 레코드 생성.
- "예, 확인했습니다" 제출 시 `ContractView.acknowledged=true`.
- "원본을 받지 못했어요" 제출 시 사업주 포털에 알림.

---

## 3. 사업주 포털 — 계약서 발급·관리

### 3.1 표준 양식 자동 생성

3종 표준 양식 지원:

| 양식 | 대상 | 근거 |
|------|------|------|
| **REGULAR** | 정규 근로자 (한국인) | 노동부 표준근로계약서 |
| **HOURLY** | 시급/일용 근로자 | 노동부 단시간·기간제 표준 양식 |
| **FOREIGN_E9** | 비전문 취업(E-9) 외국인 | 고용노동부 외국인근로자 표준근로계약서 |

사업주가 양식 선택 → 근로자 정보(이름·주민번호·직위·임금·근무시간 등) 자동 채움 → PDF 생성 → 근로자 포털 자동 배포.

### 3.2 계약서 업로드 (외부 작성 케이스)

이미 서류로 작성한 계약서가 있는 경우 PDF 업로드. 백엔드가:
1. OCR + LLM 파싱으로 구조화 필드 추출 → `EmploymentContract` 저장
2. 요약 자국어 번역 생성 → `translated_summary_json` 저장
3. 원본 PDF는 그대로 보관

**파싱 정확도가 불확실한 항목**은 사업주에게 재확인 요청. AI 파싱 오류 시 사업주가 수동 편집 가능.

### 3.3 계약 만료 알림

- E-9 비자 등 기간 있는 계약은 만료 30일 전 사업주에게 갱신 알림.
- 갱신 계약 등록 시 이전 계약은 `superseded_by`로 링크 유지.

---

## 4. 데이터 모델

### 4.1 `EmploymentContract` 신설

```
EmploymentContract
├── id (PK)
├── employee_id (FK Employee)
├── client_id (FK Client)
├── contract_type (REGULAR | HOURLY | DAILY | FOREIGN_E9 | FOREIGN_H2 | ...)
├── source (GENERATED | UPLOADED)
├── start_date, end_date (nullable — 정규는 end_date null)
├── weekly_hours
├── monthly_wage_krw (기본 임금)
├── overtime_multiplier (기본 1.5)
├── night_multiplier (기본 2.0)
├── holiday_multiplier (기본 1.5)
├── visa_type (외국인 한정: E-9, H-2, F-4, ...)
├── visa_expires_at (nullable)
├── worker_locale (근로자 모국어 코드 — 화면 렌더링용)
├── insurance_flags (JSON: 국민연금/건강/고용/산재 가입 여부)
├── original_pdf_url (Object Storage)
├── original_pdf_uploaded_at
├── translated_summary_json (JSONB: {vi: {…}, th: {…}, …})
├── superseded_by (FK EmploymentContract, nullable — 갱신 시)
├── created_at, updated_at
```

- `translated_summary_json`은 언어별 요약 필드 캐시.
- `source=GENERATED`는 우리 시스템에서 생성한 표준 양식, `UPLOADED`는 사업주가 올린 외부 계약서.

### 4.2 `ContractView` 신설

```
ContractView
├── id (PK)
├── contract_id (FK EmploymentContract)
├── employee_id (FK Employee)
├── first_viewed_at
├── acknowledged (bool, default false)
├── acknowledged_at (nullable)
├── original_missing_reported (bool, default false)
├── original_missing_reported_at (nullable)
└── locale_at_view (varchar(8))     -- 열람 시점 언어
```

한 `EmploymentContract`당 최대 1건.

---

## 5. 근로자 서명 처리 — 결정 필요

3가지 옵션 중 초안 default는 A. 상세는 [`19-worker-portal.md`](19-worker-portal.md) 공통 결정과 연동.

| 옵션 | 내용 | 트레이드오프 |
|------|------|------------|
| A | 열람 확인 로그만 (`ContractView.acknowledged=true`) | 구현 최단. 법적 효력 약함. MVP |
| B | 근로자 포털에서 "확인" 클릭 + 타임스탬프 서명 | 기록성 있음. 전자서명법 요건 미충족 가능 |
| C | 전자서명 서비스(모두싸인·이지사인 등) 연동 | 법적 효력 확실. 비용·리드타임. Phase 3+ 후보 |

**Phase 1.5는 A**, Phase 2에 B 도입 여지, C는 Phase 3+.

---

## 6. 백엔드 · API

### 6.1 근로자용

| 메서드 | 경로 | 목적 |
|--------|------|------|
| GET | `/w/{token}/contracts` | 자기 계약서 목록 (현행 + 이전) |
| GET | `/w/{token}/contracts/{id}` | 요약 뷰 (자국어) |
| GET | `/w/{token}/contracts/{id}/pdf` | 원본 PDF 다운로드 |
| POST | `/w/{token}/contracts/{id}/acknowledge` | 확인 |
| POST | `/w/{token}/contracts/{id}/report-missing` | "원본 못 받음" 신고 |

### 6.2 사업주용

| 메서드 | 경로 | 목적 |
|--------|------|------|
| POST | `/o/{client_token}/contracts/generate` | 표준 양식 생성 (body: employee_id, type, terms) |
| POST | `/o/{client_token}/contracts/upload` | 외부 계약서 업로드 (PDF) |
| GET | `/o/{client_token}/contracts` | 목록 |
| PATCH | `/o/{client_token}/contracts/{id}` | 파싱 결과 수정 |
| POST | `/o/{client_token}/contracts/{id}/supersede` | 갱신 계약 생성 |

### 6.3 세무사용

기존 대시보드에 계약서 열람 · 만료 임박 카드 추가.

---

## 7. 구현 단계

### Phase 1.5

- [ ] `EmploymentContract` · `ContractView` 스키마
- [ ] 근로자 포털 계약서 요약 뷰 + 열람 로그
- [ ] 사업주 포털 계약서 업로드 (PDF만, 파싱 없음 — 사업주 직접 필드 입력)
- [ ] 요약 자국어 번역(등록 시점 배치)

### Phase 2

- [ ] 계약서 OCR + LLM 파싱 (업로드 시 필드 자동 추출)
- [ ] 표준 양식 3종 자동 생성 PDF
- [ ] E-9 만료 30일 전 알림

### Phase 3+

- [ ] 전자서명 연동 (§5 옵션 C)
- [ ] 계약서 개정 이력 추적 UI

---

## 8. 결정 필요

| 번호 | 항목 | 초안 default | 대안 |
|------|------|-------------|------|
| C1 | 서명 처리 방식 | §5 A (열람 로그만) | B (확인 버튼) / C (전자서명) |
| C2 | 표준 양식 범위 | REGULAR·HOURLY·FOREIGN_E9 3종 | 노동부 표준 양식 그대로만 |
| C3 | 계약서 파싱 정확도 임계값 | 95% 미만 필드는 사업주 재확인 요청 | 임계값 없이 사업주 전수 검수 |
| C4 | 원본 PDF 저장 위치 | NHN Object Storage | Hancom Docs 등 문서관리 서비스 연동 |
| C5 | 계약서 갱신 시 이전 계약 근로자 조회 가능 여부 | 조회 가능 (권익 보호) | 최신 계약만 |

공통 결정 사항은 [`19-worker-portal.md`](19-worker-portal.md) §8.

---

## 9. 관련 문서

- 개요: [`19-worker-portal.md`](19-worker-portal.md)
- 데이터 모델: [`02-data-model.md`](02-data-model.md)
- AI 파싱: [`03-ai-parsing.md`](03-ai-parsing.md)
- 사업주 포털: [`12-owner-portal.md`](12-owner-portal.md)
- 개인정보 · 보안: [`10-privacy-security.md`](10-privacy-security.md)
