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

> 출처: 주민번호 수집·관리 평가. 설계(research.md 4.10 / §6 8항)는 타당. 인프라 갭(G1)은 2026-08-31 **NHN Cloud 백엔드·DB 이관**으로 대부분 해소, 남은 **설계와 현 운영(NHN Cloud 백엔드/DB + Vercel 프론트) 사이 갭**(Secure Key Manager·LLM 스크러빙 등)이 핵심. 실데이터 투입 전 차단 게이트(G1~G4) + 구현 보강(G5~G6) + 심화 과제(A/B/C).

### 2.1 실데이터 투입 차단 게이트 (선결)

- [x] **G1. 인프라 불일치 해소** — 🟡 **부분 완료** (2026-08-31 **NHN Cloud 백엔드·DB 이관 완료** — 아래 §3 참고)
  - research.md는 NCP KMS 전제(research.md:285-289, 414)였으나 1인 운영·국내보관·운영 편의성 종합 검토 결과 **NHN Cloud 메인**으로 변경
  - ✅ 국내 리전 이관 완료: 백엔드·DB가 NHN Cloud KR1(vm-node + RDS for PostgreSQL 17)에서 구동 → "세무 데이터 국내 처리 의무"(research.md:280) 충족 (해외 Render 싱가포르 리전 이탈)
  - ⚠️ 잔여: 주민번호 암호화 키가 아직 **vm-node `.env` 환경변수**에 있음 — **NHN Cloud Secure Key Manager** 통합은 미완(향후 하드닝). 현재 키 위치·관리 주체는 §3에 명문화
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

## 3. 인프라 이전 — Render → NHN Cloud (2026-06-05 결정 / 2026-08-31 이관 완료)

> G1(인프라 불일치 해소)을 클로징하는 결정. 주민번호 **국내보관 의무**가 직접 동기. 1인 운영자 기준 운영 편의성과 비용을 함께 고려해 NHN Cloud 한국 리전으로 단일화. 백엔드·DB 이관은 2026-08-31 완료(§3.5).

### 3.1 결정 사항 (2026-06-05 결정 → 2026-08-31 실배포 반영)

- **메인 인프라**: **NHN Cloud (한국 리전, KR1)** — homi 인계 세트. 이전 research.md 4.2의 NCP 메인 가정을 대체
- **컴퓨트**: **NHN Cloud Instance(vm-node, Ubuntu 24.04)** — systemd로 uvicorn(FastAPI) 상시 구동 + nginx 리버스 프록시. Docker Compose·Kubernetes(NHN NKS)는 미채택(1인 운영 단순화), 향후 트래픽 증가 시 확장
- **DB**: **NHN Cloud RDS for PostgreSQL 17** (매니지드) — PII 미보유 메타데이터·계정 위주. 기본 스키마 `rds`
- **TLS/도메인**: 백엔드 `api.easyonechon.co.kr` → vm-node nginx에서 **Let's Encrypt(certbot)** 종료·자동 갱신. External LB는 앞단에 존재하나 백엔드 공개 경로는 vm-node 직접(LB 우회)
- **프론트**: **Vercel 유지** — `NEXT_PUBLIC_API_BASE_URL`만 새 백엔드로 재배선(백엔드/DB만 NHN, vm-node엔 프론트 미배치)
- **객체 저장**: 현재 **미도입** — 업로드는 vm-node 로컬 디스크. NHN Cloud Object Storage(S3 호환) 전환은 향후 과제(만료 정책 포함)
- **암호화 키 관리**: 현재 주민번호 암호화 키는 **vm-node `.env`**. **NHN Cloud Secure Key Manager** 통합은 향후 하드닝(코드는 KCMVP 검증 모듈을 우회하지 않음)
- **알림톡/SMS**: 카카오 비즈채널 인증은 클라우드와 무관. **Aligo 환경변수 그대로 사용**(발신 허용 IP 등록 대기), 향후 NHN Cloud Notification 통합 선택지 보유
- **이메일**: **Resend 유지**(외부 SaaS, 도메인 verified). NHN Cloud Email 통합은 옵션
- **AI 호출**: Anthropic Claude(현 운영, `AI_PROVIDER=anthropic`)/Gemini는 외부 SaaS, 국외이전 동의 + 마스킹 정책으로 처리 (G3·G8 별도 대응)
- **배포/CI/CD**: 현재 로컬 코드 → `tar`+SSH → vm-node `/opt/taxflow` → `systemctl restart` 수동 배포. GitHub Actions → NHN Container Registry(NCR) 자동화는 향후 과제(Render git push 자동배포 대체 예정)

### 3.2 결정 사유

1. **주민번호 국내보관 의무** (개인정보보호법 §24의2 + §28의8) — 이관 전 Render 싱가포르 리전 저장은 위반 소지였음. 국내 리전 클라우드로 이전 필요 → NHN Cloud KR1으로 해소
2. **1인 운영자 부담 최소화** — 매니지드 K8s/PaaS-like 옵션(NHN Container Platform, NKS) 대신 단일 VM(systemd + nginx)으로 운영 단순화
3. **NHN Cloud 선택 사유** — 한국 IDC + 매니지드 PostgreSQL/Object Storage/Secure Key Manager 풀스택, 단일 콘솔·청구서로 1인 관리 용이, NHN Cloud Notification(알림톡) 자체 서비스 통합 옵션
4. **NCP 미채택 사유** — 기능 차이 미미. NHN Cloud의 콘솔 UX·관리 편의성, 1인 운영 친화도가 미세 우위라 판단 (카카오비즈 인증·Aligo 호환은 NCP와 동일하게 가능)

### 3.3 거부된 옵션

- **Render 유지 + 국외이전 동의로 우회**: 주민번호는 §24의2로 동의 만능 아님, 세무사 업무 특수성 고려 시 위험. 보류
- **NCP 메인 (기존 research.md 가정)**: 기능 충분하나 1인 운영 친화도에서 NHN Cloud 미세 우위. 백업 후보
- **단순 IaaS(KT Cloud / 가비아)**: 매니지드 부족, 1인 운영자에게 부담 큼
- **하이브리드(Render + 국내 KMS 별도)**: 키만 국내 두고 데이터 본체는 국외 → 컴플라이언스 효과 약함

### 3.4 효과 (G1~G6 게이트와의 관계)

- **G1**: 2026-08-31 국내 리전 이관 완료로 국내보관 의무 충족(부분 클로징). Secure Key Manager 통합 시 완전 해소
- **G2 (위탁계약·법무 자문)**: 그대로 진행. 위탁계약서에 처리 인프라가 NHN Cloud(한국)임 명시
- **G3·G4 (LLM 스크러빙·평문 RRN 탐지)**: 인프라 이전과 무관, **선행 또는 병행 작업**. AI 호출 시 국외이전(Anthropic/Google) 잔존
- **G5 (RPA 부산물)**: Phase 2 사안, 그대로 유효
- **G6 (출력물 평문 RRN)**: Object Storage 만료 정책으로 일부 자동화 가능

### 3.5 이관 완료 현황 (2026-08-31)

Render→NHN 백엔드·DB 이관은 완료됨. 실행 단계·검증 로그·재배포 방법 상세는 배포 런북 [`11-nhn-cloud-deploy.md`](11-nhn-cloud-deploy.md) 참고.

- ✅ RDS for PostgreSQL 17에 alembic 마이그레이션 적용(16개 테이블). 기존 더미 DB는 폐기(데이터 마이그레이션 불필요, RRN 키 신규 생성)
- ✅ vm-node systemd(uvicorn) + nginx + Let's Encrypt(`api.easyonechon.co.kr`) 구동, LB 경유/실도메인 E2E 로그인 검증
- ✅ Vercel 프론트 `NEXT_PUBLIC_API_BASE_URL` 재배선(캐시 OFF 재배포), CORS 프리플라이트·로그인 정상
- ✅ AI `AI_PROVIDER=anthropic` 활성화, 이메일 Resend verified
- ⚠️ 남은 작업: Aligo 발신 허용 IP 등록, SSH 22 소스 제한·RDS 백업 크론(하드닝), Object Storage·Secure Key Manager 통합, Render 폐기(최종 확인 후)
