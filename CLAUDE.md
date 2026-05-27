# TaxFlow / 이지원천 — 프로젝트 작업 가이드

## 작업 시작 전 필독 문서

작업을 시작하기 전에 **반드시 아래 문서를 우선 정독**한다.

1. **`research.md`** — 시장·기술·리스크 분석 근거 ("왜 이렇게 가는가")
2. **`plan.md`** — 실행 계획 인덱스 (목차 + 워크플로우 다이어그램 + 로드맵 요약 + 분할 문서 목록)
3. **사용자가 요청한 작업과 관련된 `plan/*.md`** — 기능별 상세 설계

`plan.md`가 너무 방대해 기능별로 `plan/` 하위 10개 파일로 분할되어 있다. **사용자 요청에 매칭되는 분할 문서만 선택적으로 읽는다** (전체 정독 금지 — 토큰 낭비).

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
| 디자인, 와이어프레임, UI 컴포넌트, 사이드바 | `plan/09-design.md` |
| 주민번호, RRN, 보안, 개인정보, 암호화 | `plan/10-privacy-security.md` |

요청이 모호하면 `plan.md` 인덱스에서 해당 영역을 찾아 1~2개 파일만 선택적으로 읽는다. 매칭이 어렵거나 여러 영역에 걸치는 경우, **읽기 전에 사용자에게 어떤 분할 문서를 봐야 할지 확인**한다 (토큰 절약).

## 그 외

- 코드 검토 규칙·Karpathy Guidelines는 사용자 글로벌 CLAUDE.md(`~/.claude/CLAUDE.md`)를 따른다.
- 프론트엔드: Next.js 16.2.4 — `frontend/AGENTS.md` "training data와 다른 버전" 경고 참고, 새 라우트 추가 시 `frontend/node_modules/next/dist/docs/01-app/` 우선 정독.
- 백엔드: FastAPI + SQLAlchemy 2.0, AI 프로바이더는 `AI_PROVIDER=gemini|anthropic`으로 전환.
