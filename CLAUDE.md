# TaxFlow / 이지원천 — 프로젝트 작업 가이드

## 작업 시작 전 필독 문서

작업을 시작하기 전에 **반드시 아래 문서를 우선 정독**한다.

1. **`research.md`** — 시장·기술·리스크 분석 근거 ("왜 이렇게 가는가")
2. **`plan.md`** — 실행 계획 인덱스 (목차 + 워크플로우 다이어그램 + 로드맵 요약 + 분할 문서 목록)
3. **사용자가 요청한 작업과 관련된 `plan/*.md`** — 기능별 상세 설계

`plan.md`가 너무 방대해 기능별로 `plan/` 하위 문서로 분할되어 있다 (전체 목록·결번은 `plan.md` 인덱스 기준). 문서끼리 값이 다를 때는 **`plan/00-decisions.md`(현재 확정 사실)를 우선**하고, 거기 없으면 코드를 확인한다. **사용자 요청에 매칭되는 분할 문서만 선택적으로 읽는다** (전체 정독 금지 — 토큰 낭비).

### 분할 문서 매핑 (요청 키워드 → 파일)

| 요청 키워드 | 우선 정독 파일 |
|------------|---------------|
| 워크플로우, 로드맵, Phase 1~4, 자동화 단계 | `plan/01-workflow-roadmap.md` |
| 데이터 모델, Employee, PayrollEntry, 스키마 | `plan/02-data-model.md` |
| AI 파싱, 매칭, 후속 질문, Gemini/Claude | `plan/03-ai-parsing.md` |
| 엑셀 생성, SmartA 급여대장, 간이지급명세서, 급여명세서 | `plan/04-excel-outputs.md` |
| 마스터 임포트, 시드, 샘플 데이터 | `plan/05-master-import.md` |
| 4대보험, EDI, 자격취득/상실, 보수월액 | `plan/06-insurance.md` |
| 가격, GTM, 마일스톤, 사업 | `plan/07-business.md` |
| 액션 아이템, TODO, 백로그, 구현 상태 | `plan/08-action-items.md` |
| 디자인, 와이어프레임, UI 컴포넌트, 상단 메뉴·탭 | `plan/09-design.md` (메뉴 현황은 `plan/00-decisions.md`) |
| 현재 확정 사실, 결정 충돌, "어느 문서가 맞나" | `plan/00-decisions.md` |
| NHN 배포, 이관, 운영 서버, 재배포 | `plan/11-nhn-cloud-deploy.md` |
| 사업주 포털, 거래처 사장님 화면, 포털 PIN·링크 | `plan/12-owner-portal.md` |
| 알림톡, SMS, 알리고, 카카오 템플릿 심사 | `plan/13-messaging-activation.md` |
| 계정·권한, OWNER/STAFF, 담당 배정, 접속기록 | `plan/14-accounts-permissions.md` |
| 신고 릴레이, 홈택스 일괄 전송, 접수증·납부서 배송 | `plan/15-filing-relay.md` |
| 위하고 RPA, 이지원 노트북, 게이트, 원천세 자동화 | `plan/16-wehago-rpa.md` |
| 증명발급, 홈택스 증명원 | `plan/17-certificate-issuance.md` |
| 카카오 인바운드, 고객 문의 수신 | `plan/18-kakao-inbound.md` |
| 위하고 공식 가이드, 연말정산·사회보험 메뉴 | `plan/24-wehago-official-guide-catalog.md` |
| 세법 정합성, 요율·한도 검증 | `plan/25-tax-law-compliance-checklist.md` |
| 상태 정의, AI 에이전트 권한 3단 (백로그) | `plan/26-status-and-agent-permissions.md` |
| 주민번호, RRN, 보안, 개인정보, 암호화 | `plan/10-privacy-security.md` |
| 근로자 포털, 외국인 노동자, 다국어 화면, PIN·상설 링크(근로자) | `plan/19-worker-portal.md` (개요) |
| 근로자 급여명세서 확인, 이의제기, WageAcknowledgment | `plan/20-worker-payslip.md` |
| 근로계약서, EmploymentContract, E-9, 모국어 요약 | `plan/21-worker-contract.md` |
| 출근·근태, 연장근로, AttendanceRecord, OvertimeRequest, 시간외수당 | `plan/22-worker-attendance.md` |
| 세무사 세팅, 사무소 도입·온보딩, 노트북 설치, 수당·공제 등록 | `plan/23-세무사세팅.md` |
| 세금계산서 발급 대행, 발급 요청 폼, 사장님 발급, 부가상품 | `plan/28-invoice-issuance.md` |

요청이 모호하면 `plan.md` 인덱스에서 해당 영역을 찾아 1~2개 파일만 선택적으로 읽는다. 매칭이 어렵거나 여러 영역에 걸치는 경우, **읽기 전에 사용자에게 어떤 분할 문서를 봐야 할지 확인**한다 (토큰 절약).

## 사용자에게 질문하는 방식

- **결정 질문을 묶어 던지지 않는다.** 2~3개를 한꺼번에 `AskUserQuestion`으로 물으면 흐름이 끊긴다. 특히 사용자가 이미 진행 결정을 내린 뒤라면 더 그렇다.
- **기본값으로 진행이 원칙.** 합리적 default를 골라 그대로 밀고, 진행 도중 정말 막히면 그때 한 개씩 묻는다.
- **정말 물을 땐 가장 블로킹한 한 개만** 단일 질문으로.
- **묻기 전에 내 가정을 한 번 더 의심한다.** 특히 한국 세무·금융 같은 로컬 도메인은 사용자의 실무 경험이 LLM 일반 지식보다 정확할 가능성이 높다 (예: "홈택스는 인증서 필수" 같은 잘못된 가정).

## 그 외

- 코드 검토 규칙·Karpathy Guidelines는 사용자 글로벌 CLAUDE.md(`~/.claude/CLAUDE.md`)를 따른다.
- 프론트엔드: Next.js 16.2.4 — `frontend/AGENTS.md` "training data와 다른 버전" 경고 참고, 새 라우트 추가 시 `frontend/node_modules/next/dist/docs/01-app/` 우선 정독.
- 백엔드: FastAPI + SQLAlchemy 2.0, AI 프로바이더는 `AI_PROVIDER=gemini|anthropic`으로 전환.
