# 액션 아이템 + 백로그

> plan.md §5, §5.5 분리본. 디자인 항목은 `09-design.md`에 분리.

**체크 표기**: `- [x]` ✅ **구현완료** · `- [ ]` 🟡 **부분** · `- [ ]` ⚠️ **미구현/미완료**

---

## 1. 즉시 (1~2주차)

- [x] **국세청 공식 서식 분석 완료** (v2.1) ✅
  - 원천징수이행상황신고서 A코드 체계 (A01~A99) 매핑
  - 간이지급명세서 4종 (근로/사업/기타/일용) 컬럼 구조 파악
  - 사업소득 업종코드 40종 확보 (940100~940929)
  - 결과: research.md 3.4절, `04-excel-outputs.md`에 반영
- [x] **SmartA 급여대장 양식 분석 완료** (v3.0) ✅
  - 실제 양식(주식회사법인-202604.xlsx) 기반 24컬럼 구조 파악
  - 2행 헤더 (병합셀), 수당 5항목, 공제 12항목, 합계행 구조 확인
  - 결과: `02-data-model.md`, `04-excel-outputs.md` 반영
- [ ] **조명신 사무소 실제 데이터 수집** (30~50건) — ⚠️ **미완료** (운영 과제)
  - 카톡·통화·엑셀 샘플 → AI 파싱 정확도 벤치마크
- [ ] **개인정보보호 법무 자문** — ⚠️ **미완료** (외부 자문)
  - 주민번호 수집·처리 절차 검토
  - Claude API 송신 데이터 마스킹 정책 검토
- [ ] **SmartA 자동화 정책 확인** — ⚠️ **미완료** (외부 확인)
  - 약관에서 자동화 관련 조항 점검
- [ ] **NHN Cloud 계정 셋업 + KR1/KR2 리전 확보** — ⚠️ **미완료** (현재 Render+Vercel 운영, 2026-06-05 NHN Cloud 채택 결정. 결정 맥락은 [`10-privacy-security.md` §3](10-privacy-security.md))
  - NHN Cloud Instance + Docker Compose · RDB for PostgreSQL · Object Storage · Secure Key Manager 활성화
  - NHN Cloud Notification(자체 알림톡) 또는 기존 Aligo 유지 — 카카오비즈니스 채널/발신프로필 인증은 클라우드와 무관, 그대로 진행
  - 카카오비즈니스 알림톡 채널·템플릿 등록 시작 (심사 기간 고려)

---

## 2. 3~8주차

- [x] Claude API 파싱 프로토타입 ✅ (`ai_parser.py` 정식 구현 — Gemini/Claude)
- [x] Next.js 대시보드 골격 + 카카오 알림톡 발송 연동 ✅
- [x] 거래처 응답 수신·파싱·검증 루프 ✅
- [x] SmartA 급여대장 양식 엑셀 자동 생성기 ✅ (`payroll_excel.py`, `GET /filings/{id}/payroll-excel`)
- [ ] **급여(임금)명세서 자동 교부 기능** (v2.2, 번들 피처) — 🟡 **부분 완료**
  - 근로기준법 제48조 양식 급여명세서 생성기 ✅ (`payslip_excel.py`, 직원별 시트, `GET /filings/{id}/payslips`, 다운로드 버튼)
  - 직원 연락처(Employee 마스터) 기반 알림톡/SMS 자동 발송 ⚠️ 미구현 (채널 stub·첨부 미지원)
  - 세무사 대시보드에서 "명세서 발송" 버튼 또는 승인 시 자동 발송 옵션 ⚠️ 미구현
- [x] **마스터 임포트 기능 개발** ✅
  - Backend: `POST /clients/{id}/import-payroll`
  - SmartA 급여대장 양식 컬럼 자동 매핑 + 자유 양식 지원
  - 프론트엔드 임포트 UI (`/dashboard/clients/[id]`)
- [x] **확장 샘플 데이터 생성** (`scripts/seed.py` 확장) ✅
  - 거래처 7곳, 직원 45명, 4개월 급여 이력
  - 8가지 시나리오 커버 (정상 매칭 ~ 모호한 입력)
  - 비정형 메시지 샘플 8건 (`test_messages/`)
- [x] **데이터 모델 보강** (국세청 서식 + SmartA 양식 기반, v3.0) ✅
  - Client에 `is_corporation` 필드 (법인/개인 구분 → A01/A02 분류)
  - Employee에 `business_type_code` (사업소득 업종코드 940xxx)
  - PayrollEntry에 SmartA 급여대장 24컬럼 대응 필드 전체 반영
  - 사업소득 업종코드 마스터 테이블 (40종) 시드 데이터
- [x] **간이지급명세서 엑셀 생성기** ✅
  - `simple_statement_excel.py` (근로소득 + 사업소득)
  - `GET /filings/{id}/statement-wage`, `GET /filings/{id}/statement-business`
  - 프론트엔드 다운로드 버튼 추가
  - 후속 확장 ✅: 4대보험 신고서 3종(`insurance_excel.py`) + 통합 워크북(`/insurance-combined`) + 급여명세서(`payslip_excel.py`, `/payslips`)
- [x] **세율 계산 로직 보강** (`tax_calc.py`) ✅
  - 사업소득 업종별 세율 분기 (3% / 20% / 5%)
  - 기타소득 필요경비율 적용
  - `income_type_to_a_code()` 함수 추가 (법인/개인 분기)
- [x] **다채널 수집 웹훅 엔드포인트** ✅
  - 카카오 i 오픈빌더 웹훅 (`POST /webhooks/kakao`)
  - SendGrid Inbound Parse 웹훅 (`POST /webhooks/email`)
  - 발신자 → Client → 활성 세션 자동 매칭 → `_ingest_message()` 파이프라인 합류
- [x] **거래처 연락처 편집 + 단일 초대장 발송** ✅
  - `PATCH /clients/{id}` (연락처 수정), `POST /clients/{id}/invite` (단일 발송)
  - 거래처 상세 페이지 "연락처 편집" 모달 + "초대장 발송" 버튼
  - `send_invite_to_client()` 헬퍼로 일괄/단일 발송 로직 통합 (filings.py와 공유)
  - 알림톡 stub 상태에서 SMS+이메일 폴백 자동 동작
- [ ] **거래처 연락처/초대장 후속 확장** — ⚠️ **미완료**
  - 편집 모달에 추가 필드: `business_name`, `representative`, `is_corporation`
  - 특정 월 발송: `POST /clients/{id}/invite?filing_id=` 쿼리 지원
  - 발송 이력 보기: `CollectionEvent` 조회 API + 거래처 상세에서 채널별 성공 이력 표시
  - 재발송 확인: `invite_sent=true`인 거래처에는 모달로 "이미 발송됨, 재발송하시겠습니까?" 확인
- [ ] NKS 클러스터 + GitHub Actions → Container Registry 배포 파이프라인 — ⚠️ **미완료** (현재 Render+Vercel 자동배포로 대체)

---

## 3. 9~12주차

- [ ] 조명신 사무소 실전 적용·피드백 — ⚠️ **미완료**
- [ ] 외부 베타 세무사 1~2곳 모집 — ⚠️ **미완료**
- [ ] ISMS-P / CSAP 인증 사전 준비 (보안 정책·로그·감사 체크리스트 작성) — ⚠️ **미완료**

---

## 4. 백로그 (추후 진행)

### [ ] 개별 세무사사무소 발신번호로 SMS 발송 — ⚠️ **미구현**
- **현재**: `ALIGO_SMS_SENDER` 환경변수 하나로 고정 (프로덕트 번호)
- **목표**: 거래처에 문자 발송 시, 해당 거래처를 수임한 세무사사무소 번호로 발송
- **구현 방향**:
  1. `TaxOffice.phone` 필드 활용 (이미 존재)
  2. SMS 발송 시 `sender` 파라미터를 `TaxOffice.phone`으로 동적 전달
  3. `TaxOffice.phone`이 없으면 기존 `ALIGO_SMS_SENDER`로 fallback
- **전제조건**: Aligo에 각 세무사사무소 번호를 발신번호로 사전 등록 (수동, 개수 제한 없음)
- **영향 범위**: `invite.py`, `confirmation.py`의 `get_sms_channel()` 호출부에 sender 오버라이드 추가

### [ ] 비밀번호 찾기 (이메일 인증) — ⚠️ **미구현**
- **현재**: 비밀번호 분실 시 복구 수단 없음
- **목표**: 로그인 페이지에서 사업자번호 입력 → 등록된 이메일로 인증코드/링크 발송 → 새 비밀번호 설정
- **구현 방향**:
  1. Backend: `POST /auth/forgot-password` (이메일 발송), `POST /auth/reset-password` (토큰 검증 + 비밀번호 변경)
  2. Frontend: `/forgot-password` 페이지 (사업자번호 입력 → 이메일 확인 → 새 비밀번호)
  3. DB: 리셋 토큰 저장 (만료시간 포함)
- **전제조건**: SendGrid 이메일 채널 이미 구축됨 (`channels/email.py`)

### [ ] 카카오 챗봇 AI 파싱 결과 전송 — 🟡 **조건부 (오픈빌더 AI 챗봇 전환 대기)**
- **현재 동작**: 자료 수신 시 즉시 "✅ {거래처} 자료가 접수되었습니다." **접수 ack만** 응답, 파싱은 백그라운드(결과는 대시보드에서 확인)
- **2단계(접수 안내→분석 결과) 콜백 코드 준비됨** (`_process_and_respond(callback_url=)` + `_callback_ingest_kakao()`, `webhooks.py`) — 단 **오픈빌더 봇을 "AI 챗봇"으로 전환**(카카오 승인 영업일 1~2일)해야 `callbackUrl`이 유입되어 2회 응답 동작. 전환 전까지는 접수 ack만
- 안내 문구: "이 채팅방에서 직접 입력" → "챗봇에게 메시지 입력·파일첨부해야 자료가 전송됩니다"
- 별도 알림톡 템플릿 발송 불필요(콜백 시 같은 채팅방으로 결과 전달)
