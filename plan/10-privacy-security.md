# 개인정보(주민번호) 보안 + 추후 결정·심화 검토

> plan.md §6, §7 분리본. 실데이터 투입 전 차단 게이트 + 보안 구현 보강 + 향후 리서치 영역.

---

## 1. 추후 결정·심화 검토 영역

기획서 이후 더 깊이 파볼 후보:

1. ~~위하고T 일괄등록 양식 상세 분석~~ → **SmartA 급여대장 양식 분석 완료** (v3.0)
2. ~~Phase 1 프로토타입 코드 시작~~ → **완료** (v2.1에서 MVP 코드 구현)
3. **SmartA RPA 에이전트 아키텍처 설계** (Phase 2 대비) — pywinauto 컨트롤 접근성 사전 테스트 필수
4. **이 기획서를 Word/PDF로 정리해서 산출물로 받기**
5. **근로소득 간이세액표 정밀 구현** — 현재 `tax_calc.py`는 근사 계산 (+-3%), NTS 공식 엑셀 테이블 로딩 방식으로 교체 필요
6. **간이지급명세서 HWP 서식 → 엑셀/PDF 변환** — 국세청 HWP 원본을 프로그래밍적으로 채워서 출력하는 방식 검토 (hwplib 등)
7. **사업소득 업종코드 40종 데이터 모델 내장** — 고정 참조 테이블 + 세율 분기 로직

---

## 2. 개인정보(주민번호) 보안 향후계획

> 출처: 주민번호 수집·관리 평가. 설계(research.md 4.10 / §6 8항)는 타당하나 **설계와 현 운영(Render+Vercel) 사이 갭**이 핵심. 실데이터 투입 전 차단 게이트(G1~G4) + 구현 보강(G5~G6) + 심화 과제(A/B/C).

### 2.1 실데이터 투입 차단 게이트 (선결)

- [ ] **G1. 인프라 불일치 해소** — ⚠️ 미완료 (최우선, 2026-06-05 **NHN Cloud 채택 결정** — 아래 §3 참고)
  - research.md는 NCP KMS 전제(research.md:285-289, 414)였으나 1인 운영·국내보관·운영 편의성 종합 검토 결과 **NHN Cloud 메인**으로 변경
  - 주민번호 암호화 키는 **NHN Cloud Secure Key Manager** 에 보관 (현재 Render+Vercel 운영, 미셋업 → 계획한 키 관리 체계 부재)
  - 해외 리전(Render 싱가포르) 시 "세무 데이터 국내 처리 의무"(research.md:280) 충돌 소지
  - 조치: 실RRN 투입 전 NHN Cloud 이관 + Secure Key Manager 활성화, 현재 암호화 키 위치·관리 주체 명문화
- [ ] **G2. 개인정보 처리위탁 구조 정리 + 법무 자문** — ⚠️ 미완료
  - 핵심은 동의가 아니라 위탁사슬: 거래처(처리자) → 세무사 → 이지원천(수탁자). 개인정보보호법 제26조 위탁계약·관리감독·고지, 제24조의2(RRN 동의수집 불가, 세무대리 법령근거 의존) 정리
- [ ] **G3. LLM 송신 전 RRN 스크러빙 단계 신설** — ⚠️ 미구현
  - "Claude API 주민번호 비전송" 원칙(research.md:312) 대비, AI 파싱(`03-ai-parsing.md`)이 raw_text/엑셀/OCR을 그대로 prompt 투입 → 비전송이 코드로 미보장. Gemini 메인 경로도 동일 적용
- [ ] **G4. 평문 수집 채널 RRN 탐지·격리** — ⚠️ 미구현
  - 보안 입력 URL 외 카톡/이메일/업로드로 들어온 평문 RRN이 메시지 저장소·로그에 잔존 → `_ingest_message()` 진입점에서 RRN 탐지 시 즉시 암호화/마스킹

### 2.2 구현 레벨 보강

- [ ] **G5. RPA 부산물 차단 가드** (Phase 2, `01-workflow-roadmap.md` Phase 2) — ⚠️ 계획 미반영
  - pywinauto SmartA 자동입력 시 스크린샷·로그·클립보드 OFF, 복호화값 메모리 즉시 폐기, 임시파일 금지
- [ ] **G6. 출력물 평문 주민번호 관리** — ⚠️ 미반영
  - `simple_statement_excel.py`·`insurance_excel.py` 생성 파일 저장 암호화·다운로드 링크 만료·로컬 잔존 제거

### 2.3 심화 과제 (다음 작업 후보 — 착수 전 코드 열람 허락 필요)

- [ ] **A. 코드 검증** — `backend/` 실제 주민번호 저장·암호화·LLM 송신 경로가 설계대로인지 실측 (G1·G3·G4 확인)
- [ ] **B. LLM 마스킹 파이프라인 설계** — `_ingest_message()` ~ `ai_parser.py` 사이 RRN 스크러빙 구체 설계 (G3·G4)
- [ ] **C. 위탁 구조 + 동의/고지 문안 골격** — 거래처-세무사-이지원천 3자 흐름 (G2)

> 우선순위: **G1·G2 = 실데이터 게이트**(미해소 시 실RRN 처리 불가), **G3·G4 = 구현 누수 최다 지점**.

---

## 3. 인프라 이전 결정 — Render → NHN Cloud (2026-06-05)

> G1(인프라 불일치 해소)을 클로징하는 결정. 주민번호 **국내보관 의무**가 직접 동기. 1인 운영자 기준 운영 편의성과 비용을 함께 고려해 NHN Cloud 한국 리전으로 단일화.

### 3.1 결정 사항

- **메인 인프라**: **NHN Cloud (한국 리전, KR1/KR2)**. 이전 research.md 4.2의 NCP 메인 가정을 대체
- **컴퓨트**: **NHN Cloud Instance + Docker Compose** (1인 운영자 가성비 우선). Kubernetes(NHN NKS)는 보류, 향후 트래픽 증가 시 확장
- **DB**: NHN Cloud RDB for PostgreSQL (매니지드 백업) — PII 미보유 메타데이터·계정 위주
- **객체 저장**: NHN Cloud Object Storage (S3 호환) — `backend/data/uploads/` 로컬 디스크 대체. 산출물 단기 보관 + 만료 정책 적용
- **암호화 키 관리**: **NHN Cloud Secure Key Manager** (NCP KMS 자리 대체). 주민번호 암호화 키는 여기 보관, 코드는 KCMVP 검증 모듈을 우회하지 않음
- **알림톡/SMS**: 카카오 비즈채널 인증은 클라우드와 무관. 현재 `render.yaml`의 **Aligo 환경변수 그대로 사용**, 향후 NHN Cloud Notification 통합 선택지 보유
- **이메일**: 현재 Resend 유지(외부 SaaS, 무관). NHN Cloud Email 통합은 옵션
- **AI 호출**: Claude/Gemini는 외부 SaaS, 국외이전 동의 + 마스킹 정책으로 처리 (G3·G8 별도 대응)
- **CI/CD**: GitHub Actions → NHN Cloud Container Registry(NCR) → SSH/registry pull 자동 배포 (Render git push 자동배포 대체)

### 3.2 결정 사유

1. **주민번호 국내보관 의무** (개인정보보호법 §24의2 + §28의8) — 현재 Render 싱가포르 리전 저장은 위반 소지. 국내 리전 클라우드로 즉시 이전 필요
2. **1인 운영자 부담 최소화** — 매니지드 K8s/PaaS-like 옵션(NHN Container Platform, NCP NKS) 대신 단일 VM + Docker Compose로 운영 단순화
3. **NHN Cloud 선택 사유** — 한국 IDC + 매니지드 PostgreSQL/Object Storage/Secure Key Manager 풀스택, 단일 콘솔·청구서로 1인 관리 용이, NHN Cloud Notification(알림톡) 자체 서비스 통합 옵션
4. **NCP 미채택 사유** — 기능 차이 미미. NHN Cloud의 콘솔 UX·관리 편의성, 1인 운영 친화도가 미세 우위라 판단 (카카오비즈 인증·Aligo 호환은 NCP와 동일하게 가능)

### 3.3 거부된 옵션

- **Render 유지 + 국외이전 동의로 우회**: 주민번호는 §24의2로 동의 만능 아님, 세무사 업무 특수성 고려 시 위험. 보류
- **NCP 메인 (기존 research.md 가정)**: 기능 충분하나 1인 운영 친화도에서 NHN Cloud 미세 우위. 백업 후보
- **단순 IaaS(KT Cloud / 가비아)**: 매니지드 부족, 1인 운영자에게 부담 큼
- **하이브리드(Render + 국내 KMS 별도)**: 키만 국내 두고 데이터 본체는 국외 → 컴플라이언스 효과 약함

### 3.4 효과 (G1~G6 게이트와의 관계)

- **G1**: 본 결정으로 클로징 경로 확보 — Secure Key Manager 활성화 + 이전 완료 시 해소
- **G2 (위탁계약·법무 자문)**: 그대로 진행. 위탁계약서에 처리 인프라가 NHN Cloud(한국)임 명시
- **G3·G4 (LLM 스크러빙·평문 RRN 탐지)**: 인프라 이전과 무관, **선행 또는 병행 작업**. AI 호출 시 국외이전(Anthropic/Google) 잔존
- **G5 (RPA 부산물)**: Phase 2 사안, 그대로 유효
- **G6 (출력물 평문 RRN)**: Object Storage 만료 정책으로 일부 자동화 가능

### 3.5 이전 절차 개요 (상세는 §5)

1. NHN Cloud 계정 + KR1/KR2 리전 확보
2. RDB for PostgreSQL · Object Storage · Secure Key Manager · Container Registry 활성화
3. `backend/` 코드의 LocalFileStorage → S3 호환 Object Storage 어댑터 교체
4. DB 마이그레이션 (`pg_dump` → 신규 RDB `pg_restore`)
5. `render.yaml` 환경변수를 NHN 인스턴스 `.env`로 이전 (시크릿은 Secure Key Manager에서 fetch)
6. GitHub Actions 배포 파이프라인 구성 (NCR push → SSH pull)
7. 도메인 DNS 전환 (`easyonechon.co.kr` → NHN 인스턴스), Caddy 자동 HTTPS
8. Render 인스턴스·DB·디스크 정리 (마지막 단계, 데이터 검증 완료 후)
