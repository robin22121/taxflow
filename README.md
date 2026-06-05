# TaxFlow AI (세무톡)

세무사무소를 위한 원천세 업무 AI 자동화 SaaS — Phase 1 MVP.

- 사업 배경 / 시장 분석: [`research.md`](./research.md)
- 단계별 로드맵 / MVP 설계: [`plan.md`](./plan.md)

## 구조

```
taxflow/
├── backend/          # FastAPI + SQLAlchemy + Claude API
├── frontend/         # Next.js 15 dashboard
├── docker-compose.yml  # Postgres + Redis (dev)
└── .env.example
```

## 빠른 시작

### 1. 환경 변수

```bash
cp .env.example backend/.env
# ANTHROPIC_API_KEY 만 채우면 dev로 충분 (DB는 SQLite fallback)
```

### 2. 백엔드

```bash
cd backend
uv sync
uv run alembic upgrade head
uv run python -m app.scripts.seed   # 시드 데이터 생성
uv run uvicorn app.main:app --reload --port 8000
```

기본 로그인: `admin@example.com` / `admin1234!`

### 3. 프론트엔드

```bash
cd frontend
npm run dev
# http://localhost:3000
```

### 4. (선택) Postgres·Redis로 전환

```bash
docker compose up -d
# .env 의 DATABASE_URL 을 postgresql+asyncpg://... 로 변경
cd backend && uv run alembic upgrade head
```

## 백엔드 테스트

```bash
cd backend
uv run pytest
```

54개 테스트 통과:
- AI 파서 (`test_ai_parser.py`) — 가짜 Anthropic 클라이언트로 파이프라인 검증, **PII 마스킹 검증**
- 매칭 엔진 (`test_matching.py`) — fuzzy 매칭, 이상치, 신규/퇴사 분류
- 원천세 계산 (`test_tax_calc.py`) — 근로/사업/기타/일용
- 위하고T 엑셀 생성 (`test_wehago_excel.py`)
- PII 마스킹 (`test_pii.py`) — 주민번호·사업자번호·카드번호
- 파일 인테이크 (`test_file_intake.py`) — 엑셀/CSV/오디오/이미지
- 객체 스토리지 (`test_storage.py`) — 로컬 fallback
- STT 어댑터 (`test_stt.py`) — stub + CLOVA shape
- API 통합 스모크 (`test_api_smoke.py`) — 로그인, 대시보드, 엑셀 다운로드, 공개 토큰

## 인프라 (NHN Cloud 기반)

운영은 **NHN Cloud (한국 리전)** 를 메인으로 가정해서 모듈을 구성 (2026-06-05 결정 — 주민번호 국내보관 의무. 결정 맥락·이전 절차는 [`plan/10-privacy-security.md` §3](plan/10-privacy-security.md) 참고):

| 영역 | 운영 (NHN Cloud) | 개발/대체 |
|------|------------------|---------|
| 컴퓨트 | NHN Cloud Instance + Docker Compose (1인 운영 가성비) — 향후 NHN Kubernetes Service 확장 가능 | 로컬 uvicorn |
| DB | NHN Cloud RDB for PostgreSQL (매니지드 백업) | SQLite (aiosqlite) |
| 캐시·큐 | NHN Cloud Memcached / Redis | docker-compose redis |
| 객체 저장 | NHN Cloud Object Storage (S3 호환) | LocalFileStorage (`backend/data/uploads/`) |
| 알림톡 | NHN Cloud Notification (자체) 또는 Aligo (외부 SaaS) | stub |
| 이메일 | NHN Cloud Email 또는 Resend (외부 SaaS) | SendGrid / stub |
| STT | CLOVA Speech (외부 호출) 또는 NHN Cloud Speech-to-Text | StubSTT (테스트용 canned 응답) |
| 시크릿 | NHN Cloud Secure Key Manager | `.env` |
| 인증 | NHN Cloud IAM + JWT | JWT 단독 |

각 어댑터는 환경변수만 채우면 자동 활성화 (코드 수정 불필요). 자세한 인프라 비교·결정 근거는 `research.md` §4 + [`plan/10-privacy-security.md` §3](plan/10-privacy-security.md) 참고.

## 핵심 흐름

1. 세무사가 대시보드에서 "이번 달 원천세 자료 요청"
2. 거래처에 알림톡 발송 (개별 토큰 URL 포함)
3. 거래처 응답 (URL 입력 / 카톡 텍스트 / 엑셀·이미지 / 이메일 / 통화 녹음)
4. Claude AI가 텍스트·표·이미지·음성을 정형화 + 직원 매칭
5. 신규/이상치 자동 후속 질문
6. 세무사 검증 → 위하고T 표준 엑셀 다운로드

자세한 내용은 [`plan.md`](./plan.md) 참고.
