# 출근 · 연장근로 · 근태 기록

> 2026-09-21 초안. 사업주가 일별 근태(정규/연장/야간/휴일)를 기록하고,
> 근로자가 열람·이의제기하는 흐름. 개요·인증·다국어 파이프라인은 [`19-worker-portal.md`](19-worker-portal.md) 참조.

---

## 1. 목적

- 연장근로 미지급 분쟁의 근원인 **근태 기록 부재/불일치** 해결
- 근로자가 실시간 대조 가능한 원장 제공 → 미불 인지 리드타임 며칠→즉시
- `PayrollEntry` 산정 시 근태 데이터가 **1차 소스**가 되도록 파이프라인 연결

---

## 2. 화면 — 근로자 근태 뷰

```
9월 근태 · 기준일 21일 · Tiếng Việt로 보기 ▼

이번 달 요약
   정규   152h
   연장    14h
   야간     6h
   휴일     8h

날짜      정규   연장   야간   휴일   상태
9/01 월   8:00   -      -     -     [일치]
9/02 화   8:00   1:30   -     -     [이의]  ← 사업주 1:30, 근로자 3:00
9/03 수   8:00   2:00   -     -     [일치]
...

⚠ 이의제기 중: 1건
```

### 2.1 상태 배지

| 상태 | 의미 |
|------|------|
| **일치** | 사업주 값만 있거나, 사업주·근로자 값이 같음 |
| **이의** | 근로자가 다른 값으로 이의제기 |
| **미확인** | 사업주 값이 없음 (근로자 셀프리포트만 있는 경우 — Phase 3) |

### 2.2 이의제기 흐름 — 셀프리포트 없이 (Phase 1.5 default)

근로자는 사업주 값에 **동의 여부만 표시**. "다르다"면 짧은 사유 + 실제 근무한 시간을 입력.

```
9/02 화 · 이의제기

  사업주 기록:  연장 1:30
  실제 근무한 시간을 입력해주세요:
     정규 [8:00]  연장 [3:00]  야간 [   ]  휴일 [   ]

  사유 (선택):
     [실제로는 20시까지 일했는데 1시간 30분만 기록됨]

                                    [제출]
```

제출 시:
- `AttendanceRecord.worker_regular_hours`, `worker_overtime_hours` 등 저장
- `status=DISPUTED`
- 사업주 포털에 알림

### 2.3 셀프리포트 흐름 — Phase 3 확장

근로자가 매일 근무 시간을 자기 입력(체크인/체크아웃). 사업주 승인 대기 상태로 큐잉. Phase 1.5에는 미포함.

---

## 3. 화면 — 사업주 근태 입력

### 3.1 월별 표

```
2026-09 근태 · Hanul 식품

직원        정규   연장   야간   휴일   상세
Nguyen A    152h   14h    6h     8h    [편집]
Rina        160h   -      -      -     [편집]
김철수      160h   4h     -      8h    [편집]

  [ + 근로자 추가 ]           [ 전월 동일 근무 ]
```

### 3.2 일별 편집

```
Nguyen A · 2026-09-02 편집

  정규 [8:00]  연장 [1:30]  야간 [   ]  휴일 [   ]

  근로자 이의: "실제로는 20시까지 일했는데 1시간 30분만 기록됨"

  ● 근로자 값(3:00) 반영     ○ 내 값(1:30) 유지 + 사유 회신

                                    [저장]
```

- 사업주가 근로자 이의를 받아들이면 `resolved_value` = 근로자 값.
- 유지 시 사업주 회신 사유가 근로자에게 전달.

### 3.3 "전월 동일 근무" 원탭

전월 근태 데이터를 이번 달 동일 요일에 복제. 사업주 포털 급여 입력의 UX 원칙([`12-owner-portal.md`](12-owner-portal.md) §3.2)과 동일.

---

## 4. `PayrollEntry`와의 연결

월 마감 시 `AttendanceRecord`가 `PayrollEntry` 산정 입력이 된다.

```
resolved_hours = coalesce(resolved_value, employer_value)
연장수당 = 통상시급 × resolved_overtime_hours × overtime_multiplier
야간수당 = 통상시급 × resolved_night_hours × night_multiplier
휴일수당 = 통상시급 × resolved_holiday_hours × holiday_multiplier
```

`overtime_multiplier` 등은 `EmploymentContract`에서 조회([`21-worker-contract.md`](21-worker-contract.md) §4.1).

이 산정 로직은 Phase 2에서 정식 구현. Phase 1.5는 근태 기록·이의 흐름까지만.

---

## 5. 데이터 모델

### 5.1 `AttendanceRecord` 신설

```
AttendanceRecord
├── id (PK)
├── employee_id (FK Employee)
├── client_id (FK Client)
├── work_date (date, UNIQUE with employee_id)
│
├── employer_regular_hours (decimal(4,2))
├── employer_overtime_hours (decimal(4,2))
├── employer_night_hours (decimal(4,2))
├── employer_holiday_hours (decimal(4,2))
├── employer_entered_at
│
├── worker_regular_hours (decimal(4,2), nullable)
├── worker_overtime_hours (decimal(4,2), nullable)
├── worker_night_hours (decimal(4,2), nullable)
├── worker_holiday_hours (decimal(4,2), nullable)
├── worker_reported_at (nullable)
├── worker_dispute_note_original (text, nullable)
├── worker_dispute_note_ko (text, nullable)
├── worker_dispute_locale (varchar(8), nullable)
│
├── status (MATCHED | DISPUTED | EMPLOYER_ONLY | WORKER_ONLY)
├── resolved_regular_hours (decimal(4,2), nullable)
├── resolved_overtime_hours (decimal(4,2), nullable)
├── resolved_night_hours (decimal(4,2), nullable)
├── resolved_holiday_hours (decimal(4,2), nullable)
├── resolved_by (사업주 계정 ID, nullable)
├── resolved_at (nullable)
├── employer_response (text, nullable)   -- 근로자 이의 유지 시 회신
└── created_at, updated_at
```

- `status` 자동 계산: 값 대조 결과.
- 이의 자유 텍스트는 급여명세서와 동일하게 원문 + 한국어 번역 병기.

### 5.2 `OvertimeRequest` 신설 (연장근로 승인 별도 관리)

```
OvertimeRequest
├── id (PK)
├── attendance_id (FK AttendanceRecord)
├── requested_by (EMPLOYER | WORKER)
├── requested_overtime_hours (decimal(4,2))
├── requested_night_hours (decimal(4,2))
├── reason (text, nullable)
├── status (PENDING | APPROVED | REJECTED)
├── approved_by (사업주 계정 ID, nullable)
├── approved_at (nullable)
└── created_at
```

- 주 52시간 상한 체크·특별연장근로 신청 등 노동법 컴플라이언스는 **Phase 3+ 확장 후보**. Phase 1.5는 승인/거부 상태만.
- Phase 1.5는 `AttendanceRecord.employer_*` 필드 직접 편집만 지원. `OvertimeRequest`는 Phase 2에 도입.

---

## 6. 배포 · 알림

### 6.1 근로자에게

- 사업주가 이의를 반영/거부하면 근로자 포털 홈에 카드 표시 + 국제 SMS 알림.
- 월말 근태 마감 시 "이번 달 근태를 확인해주세요" 알림.

### 6.2 사업주에게

- 근로자 이의제기 즉시 사업주 포털에 알림 카드.
- 월말 마감일까지 근태 미입력 근로자가 있으면 대시보드 상단에 배지.

---

## 7. 백엔드 · API

### 7.1 근로자용

| 메서드 | 경로 | 목적 |
|--------|------|------|
| GET | `/w/{token}/attendance?month=YYYY-MM` | 월별 근태 |
| POST | `/w/{token}/attendance/{date}/dispute` | 이의제기 (body: hours, note, locale) |
| DELETE | `/w/{token}/attendance/{date}/dispute` | 이의 철회 |

### 7.2 사업주용

| 메서드 | 경로 | 목적 |
|--------|------|------|
| GET | `/o/{client_token}/attendance?month=YYYY-MM` | 월별 표 |
| PUT | `/o/{client_token}/attendance/{employee_id}/{date}` | 일별 입력·수정 |
| POST | `/o/{client_token}/attendance/copy-previous?month=YYYY-MM` | 전월 동일 복제 |
| POST | `/o/{client_token}/attendance/{id}/resolve` | 이의 처리 (accept_worker \| retain_employer + response) |
| GET | `/o/{client_token}/attendance/disputes` | 미해결 이의 목록 |

### 7.3 세무사용

기존 대시보드에 월 마감 미입력 · 이의 통계 카드 추가.

---

## 8. 구현 단계

### Phase 1.5

- [ ] `AttendanceRecord` 스키마
- [ ] 사업주 포털 월별 근태 표 · 일별 편집 · "전월 동일" CTA
- [ ] 근로자 포털 근태 뷰 · 이의제기
- [ ] 이의 처리 흐름 (사업주 accept/retain)
- [ ] 이의 자유 텍스트 한국어 번역

### Phase 2

- [ ] `PayrollEntry` 산정 시 `resolved_hours` 참조 연결
- [ ] 월말 마감 알림 자동화
- [ ] `OvertimeRequest` 도입 (승인 워크플로우)

### Phase 3+

- [ ] 근로자 셀프리포트(체크인/체크아웃)
- [ ] 주 52시간 · 특별연장근로 컴플라이언스 체크
- [ ] 근태·급여 연동 자동 계산 대시보드

---

## 9. 결정 필요

| 번호 | 항목 | 초안 default | 대안 |
|------|------|-------------|------|
| A1 | 근로자 셀프리포트 초기 스코프 포함 여부 | Phase 3+ (미포함) | Phase 1.5부터 |
| A2 | 근태 입력 단위 | 시간·분 (15분 단위) | 30분 단위 / 자유 입력 |
| A3 | 이의제기 후 자동 처리 정책 | 사업주가 명시적 처리 필요 | 7일 무응답 시 근로자 값으로 자동 확정 |
| A4 | 근태 마감일 | 월말일 23:59 | 다음달 5일 |
| A5 | 주 52시간 초과 경고 | Phase 3+ (경고만) | Phase 2에 즉시 도입 |
| A6 | 야간·휴일 단가 배수 | `EmploymentContract`에서 조회 | 사업주 포털에서 매월 설정 |

공통 결정 사항은 [`19-worker-portal.md`](19-worker-portal.md) §8.

---

## 10. 관련 문서

- 개요: [`19-worker-portal.md`](19-worker-portal.md)
- 급여명세서: [`20-worker-payslip.md`](20-worker-payslip.md)
- 근로계약서: [`21-worker-contract.md`](21-worker-contract.md)
- 데이터 모델: [`02-data-model.md`](02-data-model.md)
- 사업주 포털: [`12-owner-portal.md`](12-owner-portal.md)
- 4대보험(추후 연동): [`06-insurance.md`](06-insurance.md)
