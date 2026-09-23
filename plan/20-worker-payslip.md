# 급여명세서 교환 · 근로자 확인

> 2026-09-21 초안. 근로자가 자신의 월별 급여명세서를 **다국어로 열람**하고, 실제 수령 여부를
> **확인/이의제기**하는 흐름. 개요·인증·다국어 파이프라인은 [`19-worker-portal.md`](19-worker-portal.md) 참조.
>
> 기존 급여명세서 PDF 생성([`04-excel-outputs.md`](04-excel-outputs.md))과 데이터 모델
> `PayrollEntry`([`02-data-model.md`](02-data-model.md))는 재사용. 본 문서는 **근로자용 프리젠테이션 + 확인 로그**만 다룬다.

---

## 1. 목적

- 근로기준법 §48 급여명세서 교부 의무의 **디지털 이행 채널** 제공
- 근로자가 실제 수령 금액과 명세서의 **일치 여부를 능동 확인**하도록 UX 강제
- 이의제기를 즉시 **사업주에게 이관**해 미불·오지급 분쟁을 조기 발견

---

## 2. 화면 — 근로자 급여명세서 열람 · 확인

```
2026-08 급여명세서                  [Tiếng Việt로 보기 ▼]
─────────────────────────────
지급액                              총 2,436,000원
  기본급         2,200,000
  연장수당         160,000
  식대(비과세)       76,000
공제                                총  252,400원
  국민연금          99,000
  건강보험          87,000
  고용보험          20,700
  소득세            38,000
  지방소득세         3,800
─────────────────────────────
차인지급액                          2,183,600원

이 명세서 내용이 실제 지급받은 금액과 일치합니까?
   ● 예, 일치합니다        ○ 다릅니다 · 이의 있음

                                    [제출]
```

### 2.1 렌더링 원칙

- 원본 데이터는 `PayrollEntry` (SmartA 24컬럼).
- 항목명은 **고정 번역 사전**으로 렌더링([`19-worker-portal.md`](19-worker-portal.md) §5.1).
  숫자·통화는 언어와 무관하게 한국 원화 원본 유지.
- **PDF 원본 링크도 함께 노출** — 근로자가 원한다면 한국어 PDF도 다운로드 가능.

### 2.2 확인 흐름

1. 근로자 최초 진입 시 명세서 자동 렌더링 → `WageAcknowledgment.viewed_at` 기록
2. 근로자가 "일치" 선택 → `acknowledged=true` 저장, 홈 화면 배지 해제
3. 근로자가 "이의" 선택 → 짧은 사유 입력창 노출 (다국어 자유 텍스트), 제출 시:
   - `WageAcknowledgment.disputed=true`, `dispute_note` 저장
   - 사업주 포털에 알림 카드 표시
   - 세무사 대시보드에는 이의 카운트만 노출

### 2.3 이의제기 자유 텍스트 다국어 처리

- 근로자가 자국어로 입력 → 원문 저장
- 백엔드 Gemini 번역 파이프라인이 **한국어 번역**을 병기 저장
- 사업주는 한국어 + 원문 병기로 조회

---

## 3. 사업주 포털에서 보는 뷰

기존 사업주 포털([`12-owner-portal.md`](12-owner-portal.md)) "보관함" 근처에 다음이 추가된다.

### 3.1 이의제기 알림 카드

```
⚠ 이의제기 1건

  Nguyen Van A · 8월 급여명세서
  "8월 15일 연장 2시간 누락된 것 같습니다"
  (원문: "Có lẽ 2 giờ tăng ca vào ngày 15/8 đã bị bỏ sót")
                                    [처리]
```

- "처리" 클릭 → 사업주가 응답(수정 반영 / 사유 회신). 회신은 근로자 포털의 홈에 알림.
- 사업주가 세무사에게 위임(카톡 이관) 옵션도 노출.

### 3.2 월별 확인 통계

```
2026-08 급여명세서 확인 상태 (직원 12명)

  ✓ 확인 완료        9명
  ⏳ 미열람           2명
  ⚠ 이의제기         1명
```

- 세무사 대시보드에도 동일 통계 노출.
- 미열람 근로자에게 재발송(§4) 가능.

---

## 4. 배포 — 급여명세서 알림

지급일 다음 날 자동 발송.

| 순위 | 경로 | 메시지 |
|------|------|--------|
| 1 | 국제 SMS | "8월 급여명세서가 도착했어요. 확인해주세요. https://…" (수신자 언어) |
| 2 | 알림톡 | 동일 메시지, 카톡 사용자 한정 |
| 3 | 사업주 QR 프린트 | 오프라인 폴백 |

미열람 상태로 7일 경과 시 사업주 포털에 재발송 CTA. 재발송은 사업주가 직접 트리거.

---

## 5. 데이터 모델 — `WageAcknowledgment` 신설

```
WageAcknowledgment
├── id (PK)
├── payroll_entry_id (FK PayrollEntry)   [UNIQUE]
├── employee_id (FK Employee)
├── acknowledged (bool, default false)
├── disputed (bool, default false)
├── dispute_note_original (text, nullable)          -- 근로자 자국어 원문
├── dispute_note_ko (text, nullable)                -- 한국어 번역
├── dispute_locale (varchar(8), nullable)           -- 원문 언어 코드
├── viewed_at (timestamp)
├── acknowledged_at (timestamp, nullable)
├── employer_response (text, nullable)              -- 사업주 회신
├── employer_responded_at (timestamp, nullable)
└── created_at, updated_at
```

- 한 `PayrollEntry`당 최대 1건 (UNIQUE 인덱스).
- `acknowledged`와 `disputed`는 상호 배타.
- `dispute_note_ko`는 백엔드 번역 직후 채워지고, 실패 시 원문만 저장.

---

## 6. 백엔드 · API

### 6.1 근로자용

| 메서드 | 경로 | 목적 |
|--------|------|------|
| GET | `/w/{token}/payslips` | 자기 급여명세서 목록 |
| GET | `/w/{token}/payslips/{payroll_entry_id}` | 상세 (자동 `viewed_at`) |
| POST | `/w/{token}/payslips/{payroll_entry_id}/acknowledge` | 일치 확인 |
| POST | `/w/{token}/payslips/{payroll_entry_id}/dispute` | 이의 제출 (body: `note`, `locale`) |

토큰 검증·PIN 게이트는 [`19-worker-portal.md`](19-worker-portal.md) §4.

### 6.2 사업주용

| 메서드 | 경로 | 목적 |
|--------|------|------|
| GET | `/o/{client_token}/payslips/status?month=YYYY-MM` | 월별 확인 통계 |
| GET | `/o/{client_token}/payslips/disputes` | 미해결 이의 목록 |
| POST | `/o/{client_token}/payslips/disputes/{id}/respond` | 이의 회신 |
| POST | `/o/{client_token}/payslips/{payroll_entry_id}/resend` | 알림 재발송 |

### 6.3 세무사용 (기존 대시보드 확장)

| 메서드 | 경로 | 목적 |
|--------|------|------|
| GET | `/api/clients/{id}/payslips/dispute-summary?month=YYYY-MM` | 이의제기 통계 |

---

## 7. 구현 단계

### Phase 1.5

- [ ] `WageAcknowledgment` 스키마
- [ ] 근로자 포털 급여명세서 상세 화면 + 확인/이의 흐름
- [ ] 다국어 항목명 사전 100항목
- [ ] 사업주 포털 이의제기 알림 카드
- [ ] 세무사 대시보드 이의 통계

### Phase 2

- [ ] 지급일 다음 날 자동 알림 발송
- [ ] 미열람 7일 재발송 CTA
- [ ] 이의제기 자유 텍스트 한국어 자동 번역 병기

---

## 8. 결정 필요

| 번호 | 항목 | 초안 default | 대안 |
|------|------|-------------|------|
| P1 | 이의 사유 필수 여부 | 필수 (짧게라도 사유 요구) | 선택 |
| P2 | 이의 후 재발송 대상 | 근로자만 | 세무사에게도 알림 |
| P3 | 미열람 자동 리마인드 주기 | 7일 | 3일 / 없음 |
| P4 | 사업주 회신을 근로자에게 노출하는 형식 | 사업주 원문 그대로 | 사업주 원문 + 자국어 번역 |
| P5 | PDF 원본 다운로드 링크 노출 | 노출 | 자국어 뷰만 노출 |

공통 결정 사항은 [`19-worker-portal.md`](19-worker-portal.md) §8.

---

## 9. 관련 문서

- 개요: [`19-worker-portal.md`](19-worker-portal.md)
- 급여명세서 PDF 생성: [`04-excel-outputs.md`](04-excel-outputs.md)
- 데이터 모델: [`02-data-model.md`](02-data-model.md)
- 사업주 포털: [`12-owner-portal.md`](12-owner-portal.md)
- 메시징: [`13-messaging-activation.md`](13-messaging-activation.md)
