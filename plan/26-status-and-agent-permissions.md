# 26. 상태 정의 2계층 & AI 에이전트 권한 3단 (백로그)

**상태**: 백로그 (미구현, 나중에 반영 예정)
**출처**: AX 정석 강의 2강(자동화 대시보드) 분석 대화 중 도출한 설계 참고안
**영향받는 문서**: `plan/02-data-model.md`, `plan/03-ai-parsing.md`, `plan/10-privacy-security.md`, `plan/15-filing-relay.md`, `plan/16-wehago-rpa.md`, `plan/20-worker-payslip.md`, `plan/21-worker-contract.md`

## 배경

기존 TaxFlow 설계에는 다음 두 가지가 명시적으로 정리되어 있지 않음:

1. 엔티티별 상태값이 단일 계층으로 표현되어, 파이프라인 뷰(요약)와 워크리스트(운영)를 동시에 만족시키기 어려움.
2. AI 파서(Gemini/Claude)와 지원이(RPA 노트북)가 어떤 액션을 어떤 조건에서 실행할 수 있는지의 정책이 명문화되어 있지 않음. RRN·EDI·홈택스 같은 민감/법적 액션의 통제 지점이 코드 흐름에 흩어져 있을 위험.

이 문서는 두 이슈에 대한 설계안을 백로그로 기록한다. 지금 구현하지 않음.

---

## A. 상태 정의 2계층

### 개념

- **큰 단계 (status_stage)**: 이 레코드가 전체 흐름의 어느 구간에 있는가. 5개 내외.
- **세부 상태 (status_detail)**: 그 구간 안에서 지금 정확히 뭘 하고 있거나 뭘 기다리는가.
- **자동 전이**: 파일 반입, 시간 경과, 외부 응답 파싱 등 트리거로 사람 손 없이 상태를 옮기는 규칙.

큰 단계는 칸반/파이프라인 뷰의 열이 되고, 세부 상태는 카드 배지·리마인더 트리거·워크리스트 필터가 된다.

### 엔티티별 상태 매트릭스

#### 지급명세·원천세 신고서 (이지원천 실제 로직 반영)

##### 엔티티 개괄 (개별 지급명세 × WithholdingReport 이원화)

원천세 신고서 하나에는 여러 종류의 지급명세가 통합된다:

- 근로소득 (`PayrollEntry`)
- 일용소득 (`DailyLaborEntry`)
- 사업소득 (`BusinessIncomeEntry`)
- 기타소득 (`OtherIncomeEntry`)
- 퇴직소득 (`SeveranceEntry`)

**엔티티 이원화**:
- **개별 지급명세** (근로자 또는 지급 건별) — `초안`·`확정`·`위하고 전송` 단계는 자기 자신의 상태.
- **WithholdingReport** (사업장 × 신고월, 1건) — `제작`·`고객송부` 단계는 이 상위 신고건의 상태이고, 개별 지급명세는 view로만 반영.

**데이터 관계 요약**:
- 사업장 A의 2026-03분 → WithholdingReport 1건 생성 (사업장 × 신고월 unique)
- 이 신고건에 근로자 20명의 `PayrollEntry` + 일용직 5명의 `DailyLaborEntry` + 프리랜서 2명의 `BusinessIncomeEntry` 등이 링크됨
- 개별 지급명세의 위하고 전송 완료 시 WithholdingReport에 "완료된 지급명세"로 등록
- WithholdingReport의 `지급명세_수집중` → `위하고입력_확인_대기` 전이는 **링크된 모든 지급명세가 위하고 전송_완료**일 때만 발생

##### 담당자 3번 확인 지점

| 확인 번호 | 시점 | 위치 | 확인 대상 |
|---|---|---|---|
| [확인1] | 위하고 전송 전 | 확정 단계 `승인_완료` 자체 | 개별 지급명세의 금액·항목 정합성 |
| [확인2] | 위하고 입력 완료 → 원천세 신고서 작성 착수 | 제작 단계 진입 게이트 | 위하고에 실제 입력된 값이 이지원천과 일치하는지 |
| [확인3] | 원천세 신고서 작성 완료 → 홈택스 신고 실행 | 제작 단계 마지막 게이트 | 신고서 최종본이 맞는지 (공동인증서 서명 물리 개입) |

##### 개별 지급명세 상태 매트릭스 (PayrollEntry 등)

**① 초안 — 고객이 원시데이터 전송**

| 세부 상태 | 진입 조건 | 다음 조치 |
|---|---|---|
| 자료요청_대기 | 매월 자료 요청일 도래 시 자동 발송 | 카톡/이메일/SMS 발송, D+2·D+4 리마인더 |
| 자료수신_완료 | 고객이 카톡·이메일·업로드로 응답 | AI 파싱 자동 트리거 |
| AI파싱_중 | Gemini/Claude 실행 중 | — |
| AI파싱_완료 | 파싱 성공, 근로자 매칭 성공 | 확정 단계로 자동 이동 |
| 추가질문_대기 | 파싱했으나 필드 부족 | AI가 후속 질문 자동 발송 |
| 매칭_실패 | 근로자 마스터에 없거나 이름·RRN 불일치 | 담당자 알림, 사람이 매칭 |

**② 확정 — 대시보드상 금액 승인/승인 취소 ([확인1] 지점)**

| 세부 상태 | 진입 조건 | 다음 조치 |
|---|---|---|
| 검토_대기 | 초안 파싱 완료 후 이상 없음 | 담당자 검토 |
| 이상값_감지 | 지난달 대비 편차 30%+, 계약 불일치 등 자동 플래그 | 담당자가 원본 확인 후 승인/반려 |
| 승인_완료 | 담당자 [확인1] 통과 (확정 버튼) | 위하고 전송 단계로 자동 이동 |
| 승인_취소 | 확정 후 담당자가 취소, 또는 근로자 이의 접수 | 초안으로 되돌리며 사유 기록 |

**③ 위하고 전송 — 이지원천 데이터를 위하고T로 자동입력**

| 세부 상태 | 진입 조건 | 다음 조치 |
|---|---|---|
| 전송_대기 | 확정 승인 완료 | 지원이(RPA) 스케줄러가 배치 실행 |
| 전송_중 | 지원이가 위하고T 조작 중 | — |
| 전송_완료 | 위하고T 입력 성공 확인 | WithholdingReport에 완료 등록 → 제작 단계 조건 검사 |
| 전송_실패_재시도 | DOM 오류·일시 실패 | 자동 재시도 (최대 N회) |
| 전송_실패_사람개입 | 반복 실패 or 데이터 오류 | 담당자 알림, 수동 처리 or 확정 취소 |

**④ 제작·⑤ 고객송부 — WithholdingReport 진척 view**

개별 지급명세는 자기 상태가 아니라 상위 WithholdingReport의 세부 상태를 그대로 표시.

##### WithholdingReport 상태 매트릭스 (사업장 × 신고월)

**④ 제작 단계**

| 세부 상태 | 진입 조건 | 다음 조치 |
|---|---|---|
| 지급명세_수집중 | 사업장 내 지급명세 종류 중 일부가 위하고 전송 미완료 | 자동 대기. 남은 지급명세 종류·건수 목록 표시 |
| 위하고입력_확인_대기 | 사업장 내 모든 종류 지급명세가 위하고 전송_완료 | **[확인2]** 담당자 검토 — 위하고 실제 입력값 대조 |
| 신고서_작성_중 | [확인2] 통과 | 지원이(RPA)가 위하고에서 원천세 신고서 자동 생성 |
| 신고서_작성_완료 | 위하고에서 신고서 생성 완료 | [확인3] 대기로 전환 |
| 홈택스전송_승인_대기 | 신고서 최종본 준비 완료 | **[확인3]** 담당자 최종 검토 — 승인 시 홈택스 전송 예약 |
| 홈택스_전송_중 | [확인3] 통과 (공동인증서 서명 물리 개입) | 지원이 RPA가 홈택스 조작 |
| 홈택스_신고_완료 | 홈택스 접수 응답 확인 | 고객송부 단계로 자동 이동 |
| 홈택스_신고_반려 | 홈택스 반려 응답 파싱 | 사유별로 관련 개별 지급명세 확정 취소 or 신고서 재작성 |

**⑤ 고객송부 단계**

| 세부 상태 | 진입 조건 | 다음 조치 |
|---|---|---|
| 접수증_수신_대기 | 홈택스 신고 완료 후 접수증·납부서 자동 조회 대기 | 지원이 RPA가 D+0~D+1 조회 |
| 접수증_수신_완료 | 접수증·납부서 파일 확보 | 담당자 최종 확인 대기 |
| 담당자_확인_대기 | 세무사 직원 검수 대기 | 확인 후 발송 승인 |
| 발송_대기 | 확인 완료 | 알림톡·SMS·이메일 자동 발송 |
| 발송_완료 | 발송 성공 | 고객 열람 대기 |
| 발송_실패 | 카톡 미도달·번호 오류 등 | 대체 채널 재시도 or 담당자 알림 |
| 종결 | 고객 링크 열람 or D+7 무응답 자동 종결 | 잠금 (수정 불가, 조회 전용) |

##### 되돌림(역방향) 전이 규칙

- **확정 → 초안**: 승인 취소, 근로자 이의 접수, 원본 데이터 오류 발견
- **위하고 전송 실패 → 확정 취소**: 데이터 오류가 원인일 때 (RPA 문제면 자동 재시도)
- **홈택스 반려 → 재작성**: 반려 사유에 따라 관련 개별 지급명세 확정 취소 or 신고서 재작성
- **모든 되돌림은 감사기록에 사유와 함께 기록**

#### EmploymentContract (근로계약서)

| 큰 단계 | 세부 상태 | 자동 전이 |
|---|---|---|
| 초안 | 파일_없음 / AI_초안_생성 / 검토_중 | AI 파서 완료 시 AI_초안_생성 |
| 서명 | 서명_요청_발송 / 근로자_확인 / 서명_완료 | 발송 D+3 미확인 리마인더, D+7 관리자 알림 |
| 유효 | 유효 / 조건_변경_대기 | 급여 인상·직군 변경 이벤트 발생 시 조건_변경_대기 |
| 종료 | 만료 / 중도해지 / 재계약_대기 | 계약 종료일 D+0 자동 만료 |

#### WageAcknowledgment (근로자 급여명세서 확인)

| 큰 단계 | 세부 상태 | 자동 전이 |
|---|---|---|
| 발송 | 발송_대기 / 발송_완료 / 발송_실패 | 발송 스케줄 |
| 확인 | 미확인_D+n / 확인_완료 | D+3, D+5, D+7 리마인더, D+7 관리자 알림 |
| 이의처리 | 이의_접수 / 검토_중 / 조치_완료 / 재발송 | 조치_완료 → 관련 PayrollEntry의 재작성_요청 트리거 |
| 종결 | 수용_종결 / 이의_종결 | D+14 무이의 시 수용_종결 자동 |

#### 4대보험 EDI 신고

| 큰 단계 | 세부 상태 | 자동 전이 |
|---|---|---|
| 준비 | 정보_수집 / 계약서_연결_대기 / 검증_통과 | 계약서 서명_완료 + 급여 확정 시 검증_통과 자동 |
| 제출 | 전송_대기 / 전송_완료 / 전송_실패 | RPA 스케줄 트리거 |
| 승인 | 심사_중 / 반려 / 승인 | EDI 응답 파싱 자동 |
| 종결 | 종결 | 승인 확인 후 종결 |

### 데이터 모델 (엔티티 공통 컬럼)

```
status_stage         # enum, 큰 단계
status_detail        # enum, 세부 상태 (stage에 종속)
status_reason        # 반려/실패 사유 (nullable)
stage_entered_at
detail_entered_at
next_action_due_at   # 리마인더 스케줄러가 참조
next_action_hint     # UI 노출용 힌트 문구
```

전이 유효성은 `allowed_transitions` 테이블로 강제. 서비스 레이어의 전이 함수만 status를 UPDATE 할 수 있게 하고, 임의 UPDATE는 DB 레벨에서 차단.

### 마이그레이션 순서 (기존 단일 status 컬럼이 있는 경우)

1. `status_stage`, `status_detail` 추가 (nullable)
2. 백필 스크립트로 기존 `status` → (stage, detail) 매핑
3. 서비스 레이어에서 새 필드 우선 사용, 구 `status`는 읽기 전용 view로 유지
4. 안정화 후 구 컬럼 드롭

### 화면별 활용

- **관리자 홈**: `stage_entered_at` 기준 "정체된 건" 카드 (예: 확정 단계에서 3일 이상 머문 PayrollEntry)
- **파이프라인 칸반**: 큰 단계를 세로 열로 사용
- **워크리스트**: `next_action_due_at <= today AND status_detail IN (미확인_D+n, 검증_실패, 정정_필요, ...)` 필터
- **근로자 포털**: 큰 단계만 노출 ("확정됨", "지급 완료"). 세부 상태 노출 금지.

---

## B. AI 에이전트 권한 3단

### 개념

- **direct**: 에이전트가 쓰면 즉시 확정
- **approval_required**: 에이전트는 제안만, 사람 승인 후 확정
- **denied**: API 자체가 해당 리소스에 접근 거부

`AuditLog`는 세 등급 무관 전량 기록. RRN 등 민감 필드는 raw 대신 sha256 + last4 저장 (plan/10 정합).

### 데이터 모델

```
PermissionPolicy
  actor_type            # 'rpa_notebook' | 'ai_parser' | 'user'
  actor_id              # nullable (전역 정책이면 null)
  resource              # 'payroll_entry.finalize' 등 dotted key
  action                # 'read' | 'write' | 'delete'
  level                 # 'direct' | 'approval_required' | 'denied'
  confidence_threshold  # nullable, ai_parser 전용
  effective_from, effective_until
  reason                # 감사용 사유 문자열

ApprovalRequest
  id
  actor_type, actor_id
  resource_type, resource_id
  action
  proposed_change     # JSON (before → after)
  confidence          # nullable, 파서일 때
  status              # 'pending' | 'approved' | 'rejected' | 'expired'
  requested_at
  resolved_at, resolved_by, resolved_reason
  reminder_count

AuditLog
  actor_type, actor_id
  resource_type, resource_id
  action, before, after
  approval_id           # nullable — direct 반영이면 null
  at
```

### API 엔드포인트 shape

```
POST /agent/write
  body: { resource, action, payload, confidence? }
  → 200 { status: "applied", audit_id }                  # direct
  → 202 { status: "pending_approval", approval_id }      # approval_required
  → 403 { status: "denied", reason }                     # denied

GET  /approvals?status=pending&assignee=me
POST /approvals/{id}/approve  body: { note? }
POST /approvals/{id}/reject   body: { reason }
POST /approvals/batch-approve body: { ids: [...] }       # 신뢰도 X% 이상 일괄
```

### 액션별 권한 매트릭스 (초안)

| 리소스 / 액션 | 지원이 (RPA) | AI 파서 | 근거 |
|---|---|---|---|
| 조회 (read) | direct | direct | 부작용 없음, 로그만 기록 |
| `payroll_entry.create_draft` | — | direct | 초안은 아무한테도 영향 없음 |
| `payroll_entry.finalize` | approval_required | approval_required | 세무 확정은 세무대리인 책임 |
| `worker.rrn_write` | approval_required | approval_required | plan/10 원칙, 잘못 저장 시 세금 사고 |
| `insurance.edi_submit_acquisition` | approval_required | denied | 외부 시스템 제출은 RPA만, 사람 승인 필수 |
| `insurance.edi_submit_loss` | approval_required | denied | 상동 |
| `hometax.file_submit` | approval_required + 인증서 서명 | denied | 공동인증서 물리 개입 필수 |
| `worker.contract_send` | approval_required | denied | 근로자 대상 커뮤니케이션 |
| `worker.payslip_send` | approval_required | denied | 근로자 대상 커뮤니케이션 |
| `contract.create_draft` | — | direct | 초안, 서명 전엔 무해 |
| `master.register_workplace` | approval_required | approval_required | plan/05 시드 무결성 |

### 신뢰도 기반 자동 승격 (신중하게)

`approval_required` 항목 중 실측 안정성이 검증되면 한시 승격:

```
자동 승격 조건:
- 최근 30일간 해당 (actor, resource) 조합의 승인 요청 ≥ 100건
- 승인율 ≥ 98%
- 거부/롤백 없음
- 리소스가 승격 화이트리스트에 있음

승격 결과:
- PermissionPolicy에 effective_until = now + 90일 임시 정책 추가
- 승격 후에도 랜덤 5% 샘플은 여전히 approval_required (drift 감시)
- 90일 뒤 자동 재평가
```

**영구 제외 (승격 화이트리스트 절대 불가)**:
- `worker.rrn_*`
- `insurance.edi_*`
- `hometax.*`
- `worker.*` (근로자 대상 발송 전체)

### 승인 큐 UX

- 대시보드 홈에 "AI 승인 대기" 위젯 상시 노출
- 처리될 때까지 매일 오전 이메일 리마인더 (강의의 반복 알림 패턴)
- 승인자는 관리자(세무대리인) role, 위임 가능
- 일괄 승인: 신뢰도 X% 이상 + 편차 규칙 통과한 파서 결과는 다중 선택 후 한 번에 승인

### 근로자 포털 관점 특이 사항

근로자가 이의제기하는 순간(WageAcknowledgment 이의_접수) 관련 PayrollEntry의 후속 자동화(예: 다음 달 자동 재사용)는 일시 정지. 이의 종결 전까지 해당 리소스에 대해 `level='denied'`로 강제 오버라이드. plan/20 정책과 결합.

### 규칙 3가지 (신규 액션 도입 시 판별용)

1. **부작용 없는 액션(초안·읽기)** → direct
2. **되돌릴 수 있지만 영향 있는 액션(확정·RRN)** → approval_required, 신뢰도 승격 여지 있음
3. **되돌리기 어렵거나 법적 책임 액션(EDI·홈택스·근로자 발송)** → approval_required, **승격 영구 제외**

---

## 반영 시 진행 순서 (추후)

1. plan/02-data-model.md에 상태 2계층 컬럼 스펙 반영
2. plan/03-ai-parsing.md에 파서별 permission policy 초기값 반영
3. plan/10-privacy-security.md에 RRN·인증서 관련 권한 매트릭스 반영
4. plan/16-wehago-rpa.md, plan/15-filing-relay.md에 RPA용 approval 흐름 반영
5. PermissionPolicy·ApprovalRequest·AuditLog 테이블 마이그레이션
6. `/agent/write` 라우팅 미들웨어 구현
7. 승인 큐 UI (관리자 홈 위젯)
8. 배치: 승인 대기 리마인더, 신뢰도 승격 재평가

각 단계는 별도 액션 아이템으로 plan/08에 등록 예정.
