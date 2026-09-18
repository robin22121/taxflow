# 홈택스 증명발급 자동화 (증명발급 메뉴)

> 2026-09-17 신설. 이지원천 사이드바에 **"증명발급"** 메뉴를 별도로 만들고,
> 사용자가 증명원 종류와 대상을 골라 **[발급요청]** 을 누르면 자동화가 홈택스에서 PDF를 회수한다.
> 담당자가 PDF를 검토한 뒤 **[이메일 · 문자 · 팩스 · 다운로드]** 중 원하는 액션으로 발송한다.
>
> 개발은 **Phase 1 (시뮬레이션 · 스탠드얼론 스크립트)** 로 시작한다.
> - 실행 기기: **개발자 개인 PC** (지금 사용 중인 컴퓨터). 자동화 전용 노트북 사용 안 함.
> - 홈택스 계정: **개발자 본인이 가지고 있는 별도의 개인사업자** 아이디 로그인 (아이디 + 비밀번호 + 생년월일 추가인증). 공동인증서는 필수 경로에서 제외 — 증명원 종류에 따라 요구되면 그때 실측.
> - PDF 저장: **로컬 폴더**. 이지원천 서버·DB·UI 통합 없음.
> - 목표: 홈택스 로그인 → 즉시발급증명 메뉴 → 발급 → PDF 회수까지의 셀렉터·타이밍·팝업을 실코드로 확인. 첫 대상은 **사업자등록증명 1건**, 이후 우선순위 순서(§1 표)대로 확장.
>
> **Phase 2 (프로덕션 · 실제 시스템 흐름)** 는 Phase 1 결과를 그대로 이식하되
> 로그인 앞단(개인사업자 아이디 → **세무사 대리 아이디 + 세무대리 관리번호**),
> 대상 선택(단일 → **수임처 지정**),
> 실행 기기(개인 PC → **자동화 전용 노트북**, `plan/16-wehago-rpa.md` §8-2),
> 저장(로컬 → **이지원천 서버 오브젝트 스토리지**),
> 후속 액션(로컬 확인 → **이지원천 UI + 알림 + 발송 액션**)만 교체한다.
> 발급 함수·PDF 검증·메뉴 조작 코드는 재사용.

## 결정 히스토리

| 일자 | 결정 | 배경 |
|------|------|------|
| 2026-09-17 | 본 문서 신설 — 이지원천에 "증명발급" 메뉴 별도, 담당자 확인 후 이메일 · 팩스 · 문자 · 다운로드 액션 선택 (Phase 2 프로덕션 스코프) | 사무소 실무에서 사업자등록증명·납세증명은 상시 반복 발급 업무. 신고 워크플로우와 축이 달라 별도 메뉴 필요 |
| 2026-09-17 | Phase 1 스코프 축소 — **개발자 개인 PC + 개인사업자 아이디 로그인 + 로컬 PDF 저장 + 이지원천 통합 없음**. 자동화 노트북·세무대리 관리번호·서버 업로드는 Phase 2 | 사용자 정정: "시험삼아 및 시뮬레이션용이야, 별도의 노트북을 사용하지 않고 지금 현재 내가 쓰고 있는 이 컴퓨터를 이용할거야". 인프라 세팅(BitLocker·자격 증명 관리자·세무사 아이디 조달·세무대리 관리번호) 없이 발급 흐름 자체를 먼저 검증 |
| 2026-09-18 | Phase 1.5 목표를 **2단계**로 확정 — (1) 사용자 개인사업자 아이디 로그인으로 Windows 에이전트 → 사업자등록증명 발급 성공, (2) 성공 후 **세무사 아이디·비밀번호 + 공동인증서 로그인** 구현. 증명원은 사업자등록증명 1종만 | 사용자 지시. 공동인증서 로그인은 원래 Phase 2 였으나, 세무사 대리 로그인이 실제 운영 경로이므로 Phase 1.5 안에서 미리 실측한다 |
| 2026-09-17 | 대상 증명원 12종 확정, 우선순위 7종 명시. 납세증명은 **기타용만**(대금수령용 제외). 소득금액·부가세 과표증명은 기간 옵션 필요. Phase 1 첫 대상 = 사업자등록증명(옵션 없음) | 홈택스 즉시발급증명 카탈로그 확인 후 사용자 지시. 옵션 없는 것부터 착수해 파이프라인 먼저 완성 후 옵션 처리 추가 |

## §1. 대상 증명원 (홈택스 즉시발급 12종)

**우선순위 (사용자 지정, 발급 빈도 순)**

| 순위 | 증명원 | 로그인 유형 | 옵션 |
|-----|--------|-----------|------|
| 1 | 사업자등록증명 | 개인사업자·법인사업자 | 없음 — Phase 1 첫 대상 |
| 2 | 납세증명서 (기타용) | 개인·법인사업자 | 유효기간(기본 30일) |
| 3 | 납부내역증명 (납세사실증명) | 개인·개인사업자·법인사업자 | 기간(사용목적별 자동 계산 또는 수동) |
| 4 | 소득금액증명 | 개인 | **필요 연도** — 최근 1년 / 3년 / 5년 프리셋 + 사용자 기간 입력 |
| 5 | 부가가치세 과세표준증명 | 개인사업자·법인사업자 | **기간** (예: 2026년 1기 확정) |
| 6 | 부가가치세 면세사업자 수입금액증명 | 개인사업자·법인사업자 | 기간 |
| 7 | 폐업사실증명 | 개인·법인사업자 | 없음 |

**확장 대상 (초기 릴리즈 후 사용자 요구에 따라 순차 추가)**

| 증명원 | 로그인 유형 | 옵션 |
|--------|-----------|------|
| 휴업사실증명 | 개인·법인사업자 | 없음 |
| 표준재무제표증명 (개인·법인) | 개인사업자·법인사업자 | 신고 귀속 사업연도 |
| 사업자단위과세적용 종된사업장 증명 (전체) | 개인사업자·법인사업자 | 없음 |
| 소득확인증명서 (청년우대형주택청약 가입·과세특례용) | 개인 | 신청 사유 |
| 납세증명서 (대금수령용) | 개인·법인사업자 | 유효기간·발주처 정보 — **초기 릴리즈 제외**(사용자 지시: 기타용만) |

- **국문/영문**: 대부분 국·영문 동시 제공. 옵션에 언어 선택 추가.
- **로그인 유형**: 개인 로그인 vs 사업자 로그인이 증명원마다 다름. Phase 1은 개인사업자 아이디 하나로 커버되는 것부터.
- **자주찾는 민원** 표시가 붙은 종류는 홈택스 첫 화면 바로가기에서 진입 가능 — 셀렉터가 안정적일 가능성 (실측 후 확정).

## §2. 범위 밖 (전체 스코프)

- 지방세납세증명 (위택스 소관) — 별도 검토.
- 4대보험 자격득실확인서 (국민연금·건강보험 공단 EDI/포털) — `plan/06-insurance.md` Phase 3 이후.
- 신청·처리형 증명 (양도소득 등 즉시발급 아닌 것) — 별도 상태 관리 필요, 스코프 제외.
- 팩스 자동발송 (게이트웨이 연동) — 문서에는 포함하되 구현은 Phase 3.

## §3. Phase 1 — 시뮬레이션 스탠드얼론 스크립트

### 3-1. 스코프 원칙

- **이지원천의 어떤 것도 건드리지 않는다.** 백엔드 서버·프론트엔드 UI·DB 스키마·`rpa-agent` 배포판 코드 변경 없음. 완전 별개 디렉토리에서 Playwright 스크립트만 돌린다.
- **개발자 개인 자산으로만 실행한다.** 개인 PC, 개발자 본인이 보유한 개인사업자 홈택스 계정. 사무소 노트북·세무사 아이디·수임처 데이터 접근 없음.
- **결과물은 로컬에만 남긴다.** PDF는 스크립트 옆 `./out/` 폴더 (git-ignore). 어떤 형태로도 서버 전송 없음.
- **목표는 "이 흐름이 자동화 가능한가"에 대한 답을 얻는 것.** 프로덕션 품질(에러 처리·재시도·모니터링)은 신경 쓰지 않는다.

### 3-2. 실행 환경

- 개발자 개인 PC (macOS · Windows 어느 쪽이든 가능. 프로덕션이 Windows이므로 **Windows에서 최소 1회 검증** 권장)
- Python 3.11+, Playwright + Chromium (headed 모드 — 개발 중 관찰용)
- **공동인증서 필요 없음** (아이디 로그인 사용). 개인사업자 로그인이 인증서를 요구하는 종류에 부딪히면 그때 인증서 자동 입력 실측을 Phase 1 후반에 추가.
- 저장 위치: 스크립트 실행 폴더의 `./out/{yyyymmdd_hhmmss}_{cert_type}.pdf`

### 3-3. Phase 1 대상 (착수 순서)

1. **사업자등록증명** — 옵션 없음. 로그인·메뉴 진입·발급·PDF 회수 파이프라인 검증 목적.
2. **납세증명서 (기타용)** — 유효기간 옵션 (기본 30일) 처리 검증.
3. **소득금액증명** — 연도/기간 옵션 UI(달력·프리셋) 처리 검증.
4. **부가가치세 과세표준증명** — 기간(반기·과세연도) 옵션 처리 검증.
5. **납부내역증명 · 부가세 면세증명 · 폐업사실증명** — 셀렉터·옵션 매핑 추가.
6. **국문/영문 토글** — 언어 선택 셀렉터 확인.

Phase 1은 **1~4까지가 완료 판정 최소선**. 5~6은 여유 있으면 같이.

### 3-4. 로그인 정보 취급

- **아이디·비밀번호·생년월일 추가인증** 값은 **스크립트에 하드코딩 금지, 파일 저장 금지, 환경변수 금지, git 추적 금지**.
- 실행마다 콘솔 입력 (`getpass.getpass()` — 화면 미표시).
- 실행 로그·스크린샷·NOTES.md 어디에도 실제 값 기록 금지.
- 사용자가 대화에 노출한 자격증명은 이 대화 기록에 남으므로 Phase 1 검증 종료 후 **비밀번호 변경** 권장.
- 생년월일이 실제 인격 정보이므로 로그에도 마스킹(`YYMMDD-*******`).

### 3-5. 흐름 (사업자등록증명 예시)

```
[개발자 PC · 로컬 실행]
 ① python issue.py --type business_registration
    콘솔 입력: 홈택스 아이디 · 비밀번호 · 생년월일(추가인증)
 ② Playwright 헤디드 크롬 실행 → https://www.hometax.go.kr/
 ③ [로그인] → 사업자 로그인(또는 개인 로그인) 탭 → 아이디 로그인 → 아이디·비밀번호 입력
 ④ 생년월일 추가인증 창 감지 → 값 입력 → 로그인 완료
 ⑤ 로그인 성공 확인 (상단 표시 대기)
 ⑥ 국세증명·사업자등록·세금관련 신청/신고 > 즉시발급증명 > 사업자등록증명 진입
 ⑦ [신청하기] → [발급하기] → [출력하기]
 ⑧ PDF 다운로드 이벤트 캡처 → ./out/{ts}_business_registration.pdf 저장
 ⑨ pdf_verify.py로 사업자번호·상호·발급일자 추출 → 콘솔 출력 (개인정보는 마스킹)
 ⑩ 스크립트 종료 (브라우저는 열어두어 개발자가 눈으로 확인)
```

- ⑦의 [출력하기]가 브라우저 인쇄 대화상자를 열면 Playwright로 다루기 어려움 — 이 경우 페이지에 PDF 링크가 실제로 있는지, 아니면 `window.print`인지 실측 후 대응.
- ⑥의 메뉴가 WebSquare 페이지 내 레이어인지 새 탭인지 확인 (`plan/16-wehago-rpa.md` §9-2에서 홈택스 신고 메뉴는 WebSquare 레이어).

### 3-6. 산출물

- `rpa/certificate-poc/` 신설 (기존 `rpa/poc-security/`, `rpa-agent/`와 별개)
  - `README.md` — 실행 방법, git-ignore 규칙, 실행 후 비밀번호 변경 안내
  - `.gitignore` — `out/`, `*.pdf`, `NOTES.local.md` 강제 제외
  - `issue.py` — 메인 진입점 (`--type` 인자로 증명원 선택)
  - `hometax_login.py` — 로그인 헬퍼 (아이디 로그인 + 추가인증 창 처리)
  - `menu_navigate.py` — 즉시발급증명 카탈로그 진입 · 종류별 라우팅
  - `certificates/` — 종류별 발급 함수 (`business_registration.py`, `tax_clearance.py`, `income_amount.py`, `vat_base.py`, …)
  - `pdf_verify.py` — PDF 텍스트 추출 → 사업자번호·상호·발급일 확인 (개인정보 마스킹)
  - `NOTES.md` — 실측 노트 (커밋 대상, 개인정보·자격증명 절대 미포함)
- **비산출물**: 서버 API 스펙, DB 마이그레이션, 프론트 컴포넌트, 배포 문서, 자동화 노트북 세팅 가이드 — 모두 Phase 2로 미룸.

### 3-7. Phase 1에서 확인할 실측 질문

이 답들이 Phase 2 설계 확정 전에 있어야 함. `plan/16-wehago-rpa.md` §9 홈택스 관련 질문과 중첩되는 것은 결과 공유.

1. **아이디 로그인만으로 12종 발급이 다 되는가?** 개인 로그인 필요 종류(소득금액), 사업자 로그인 필요 종류(사업자등록증명·부가세) 사이에 로그아웃/재로그인이 필요한가? 홈택스 "간편전환" 있는가?
2. **어떤 종류에서 공동인증서를 요구하는가?** (예: 소득금액증명은 개인 인증서 요구 가능성) — 요구되면 Phase 1 후반에 `plan/16-wehago-rpa.md` §3-1 인증서 자동 입력 방식 실측을 여기서 먼저 진행.
3. **즉시발급증명 카탈로그 페이지의 종류별 링크 셀렉터가 안정적인가?** 자주찾는 민원 목록 vs 통합검색 결과 어느 쪽이 더 안정적인가?
4. **각 증명원 발급 화면이 WebSquare 페이지 내 레이어인가, 새 탭·iframe인가?**
5. **[출력하기] 버튼 동작** — PDF 다운로드 이벤트인가, 브라우저 인쇄 대화상자(`window.print`)인가, K Upload 계열 별도 모듈인가.
6. **발급일자·유효기간을 화면 DOM에서 읽을 수 있는가, 아니면 PDF에서만 추출 가능한가.**
7. **PDF에 텍스트 레이어가 있는가** (`pypdf`로 사업자번호 추출 가능 여부). 없으면 OCR 필요 → Phase 2에서 결정.
8. **연속 발급 rate-limit** — 짧은 시간에 같은 종류 여러 번 발급 시 홈택스가 제한하는가.
9. **국문/영문 토글의 UI 위치** — 발급 화면 상단인지, 종류 선택 시점인지.

### 3-8. Phase 1 완료 판정

- 우선순위 4종 (사업자등록증명 · 납세증명서 기타용 · 소득금액증명 · 부가세 과표증명)을 스크립트 1회 실행으로 각각 로컬에 발급·저장.
- PDF에서 사업자번호·상호·발급일자 추출 (마스킹된 형태로) 콘솔 확인.
- §3-7 실측 질문 9개에 대해 NOTES.md에 확인된 답이 적혀 있음.
- 위 3개 조건이면 Phase 2 착수 가능.

## §3-9. Phase 1.5 — 2대 분리 시뮬레이션 (본체 PC ↔ 별도 노트북)

> 2026-09-18 재구성. 초기 계획(맥미니 = 서버, 맥북 = 에이전트)은 맥북 macOS 13 arm64 의 Playwright chromium 미지원 이슈로 취소.
> 실제 구성은 **맥북 = 이지원천 서버 시뮬**, **Windows PC = 자동화 전용 노트북 시뮬**. 맥미니(개발 PC)는 편집·git push 에만 사용.

Phase 1의 로컬 스크립트가 사업자등록증명 발급을 성공한 뒤 곧바로 이지원천 프로덕션으로 가지 않고,
프로덕션 구조(서버 + 자동화 노트북 분리)를 사용자 로컬 자산 2대로 시뮬레이션한다.
목적은 통신 방향·잡 큐·자격증명 관리·PDF 업로드 흐름을 실제로 동작시키고, Phase 2에서 로그인 앞단·저장소·기기 SKU 만 갈아 끼워도 되게 만드는 것.

### 3-9-1. 역할·기기·통신 방향

```
┌─────────────────── 사무실 Wi-Fi ────────────────────┐
│                                                    │
│  [맥북 = "이지원천 서버" 시뮬]                      │
│    - macOS + FastAPI + SQLite + 로컬 파일 저장     │
│    - http://192.168.x.x:8100 (내부망)              │
│    - 인입: 사용자 발급 요청, 에이전트 폴링·업로드  │
│    - 발신: 없음 (에이전트에 접속하지 않음)         │
│                                                    │
│              ↑ 5초 폴링 (아웃바운드 HTTP)          │
│                                                    │
│  [Windows PC = "자동화 전용 노트북" 시뮬]           │
│    - Windows + Playwright chromium + Phase 1 코드  │
│    - Windows 자격 증명 관리자 (keyring 자동 사용)  │
│    - 폴링 → 잡 pick → 홈택스 로그인·발급 → 업로드  │
│                                                    │
└────────────────────────────────────────────────────┘

[맥미니]  개발용 PC — 코드 편집·git push 만. 실행 없음.
```

- **통신은 Windows → 맥북 한 방향**. 맥북은 Windows 에 접속하지 않는다. Phase 2 프로덕션(사무실 방화벽 인바운드 개방 불필요) 과 동일한 방향.
- 초기에는 **HTTP + 사무실 Wi-Fi 로컬 IP** (자체 서명 인증서 세팅 번거로움 회피). Phase 2 전에 HTTPS 로 교체.
- 로그인 계정은 여전히 **사용자 개인 사업자** (세무사 대리 로그인은 Phase 2).
- **Windows PC = Phase 2 프로덕션의 노트북 시뮬** — BitLocker·Windows 자격증명 관리자·nProtect 같은 실제 환경 요소를 미리 밟는다.

### 3-9-2. 파일 구조

기존 `rpa/certificate-poc/` (Phase 1) 은 그대로 두고, 옆에 두 개 신설.

```
rpa/
├── certificate-poc/            # Phase 1 (개인 PC 스탠드얼론)
│   ├── hometax_login.py        # ← Phase 1.5 에서 재사용
│   ├── issue.py                # ← 발급 함수만 뽑아 재사용
│   └── ...
├── certificate-server/         # Phase 1.5 신설 (맥북에서 실행)
│   ├── pyproject.toml
│   ├── certificate_server/
│   │   ├── __init__.py
│   │   ├── main.py             # FastAPI 앱
│   │   ├── db.py               # SQLite 엔진·세션
│   │   ├── models.py           # SQLAlchemy (Agent, IssueRequest, Job, File)
│   │   ├── schemas.py          # pydantic
│   │   ├── auth.py             # X-Agent-Token 검증
│   │   ├── storage.py          # ./storage/ 파일 저장·조회
│   │   ├── admin_cli.py        # 에이전트 등록·토큰 발급·폐기
│   │   ├── routes_user.py      # 사용자 API (요청·이력·다운로드)
│   │   └── routes_agent.py     # 에이전트 API (잡 폴링·결과 업로드)
│   ├── storage/                # .gitignore (증명원 PDF/PNG)
│   ├── db.sqlite               # .gitignore
│   └── README.md
└── certificate-agent/          # Phase 1.5 신설 (Windows PC 에서 실행)
    ├── pyproject.toml
    ├── certificate_agent/
    │   ├── __init__.py
    │   ├── __main__.py         # CLI (`setup` · `run` · `show` · `clear`)
    │   ├── config.py           # keyring 접근 (Windows 자격 증명 관리자/DPAPI)
    │   ├── api.py              # 서버 HTTP 클라이언트 (httpx)
    │   ├── runner.py           # 폴링 루프 · 잡 상태 전이
    │   └── issue_flow.py       # certificate-poc/ 코드 재사용해 발급 실행
    └── README.md
```

- `certificate-agent/certificate_agent/issue_flow.py` 는 `rpa/certificate-poc/hometax_login.py` 를 **상대 import 하거나 별도 패키지로 설치**해 그대로 사용. 발급 함수(카탈로그 이동·[출력] 클릭·팝업 캡처) 도 Phase 1 코드를 함수로 뽑아 공유.
- `certificate-poc/` 를 얇은 라이브러리로 만들려면 `pyproject.toml` 에 `[project]` 메타를 이미 넣어뒀으니 `uv add ../certificate-poc` 로 로컬 의존 가능. 혹은 `hometax_login.py` 를 `rpa/common/` 로 옮겨 세 프로젝트가 참조.

### 3-9-3. 데이터 모델 (SQLite)

**`agents`** — 에이전트 등록

| 컬럼 | 타입 | 비고 |
|------|------|------|
| id | uuid | PK |
| name | str | 사무소가 붙이는 이름 (예: "Windows-김연호") |
| token_hash | str (unique) | SHA-256 (발급 시 1회 노출) |
| created_at · last_seen_at · revoked_at | datetime | |

**`issue_requests`** — 사용자 요청 (게이트 1)

| 컬럼 | 타입 | 비고 |
|------|------|------|
| id | uuid | PK |
| cert_type | enum | BUSINESS_REGISTRATION · TAX_CLEARANCE_ETC · INCOME_AMOUNT · VAT_BASE · … |
| options | JSON | 기간·연도·유효기간·언어 |
| business_number | str | 발급 대상 사업자번호 (Phase 1.5 는 사용자 본인 사업자) |
| status | enum | REQUESTED · RUNNING · ISSUED · FAILED · CANCELED |
| requested_at · updated_at | datetime | |
| result_file_id | uuid FK | ↓ certificate_files |
| failure_reason | str | |

**`jobs`** — 에이전트 실행 잡

| 컬럼 | 타입 | 비고 |
|------|------|------|
| id | uuid | PK |
| issue_request_id | uuid FK | |
| agent_id | uuid FK, nullable | claim 시 채움 |
| status | enum | PENDING · CLAIMED · RUNNING · SUCCEEDED · FAILED |
| claimed_at · finished_at | datetime | |
| result_message | str | 성공/실패 요약 |

**`certificate_files`** — 저장된 파일 참조

| 컬럼 | 타입 | 비고 |
|------|------|------|
| id | uuid | PK |
| filename | str | 상대 경로 (`./storage/{id}.pdf` or `.png`) |
| mime | str | `application/pdf` or `image/png` |
| sha256 | str | 무결성 |
| issued_at | datetime | 홈택스 발급일 (PDF 텍스트 추출 시 채움) |
| valid_until | date | 유효기간 (해당 종류만) |

### 3-9-4. API 스펙 (얇게)

**사용자 API** (`/api/user`, 인증 최소 — Phase 1.5 는 로컬)

| 메서드·경로 | 용도 |
|------------|------|
| `POST /issue-requests` | 발급 요청 등록 (게이트 1) |
| `GET /issue-requests` | 이력 리스트 |
| `GET /issue-requests/{id}` | 상세 + 파일 상태 |
| `GET /issue-requests/{id}/download` | 파일 다운로드 (완료 건) |

**에이전트 API** (`/api/agent`, 헤더 `X-Agent-Token` 필수)

| 메서드·경로 | 용도 |
|------------|------|
| `POST /agents` | 에이전트 자체 등록 (관리자가 토큰 발급) |
| `GET /jobs/next` | 5초 폴링 — 대기 잡 반환 (PENDING → CLAIMED) |
| `POST /jobs/{id}/heartbeat` | RUNNING 상태 갱신 (선택) |
| `POST /jobs/{id}/result` | multipart: (파일 + JSON 메타) 업로드 |

**잡 상태 머신**
```
PENDING → CLAIMED → RUNNING → SUCCEEDED
                            → FAILED
                            → CANCELED
```

- `CLAIMED` 후 15분 응답 없으면 서버가 `FAILED` 로 되돌리고 재폴링 대상.
- 같은 `issue_request_id` 에 대기·진행 중 잡 중복 금지 (Phase 2 게이트 1 규칙 재사용).

### 3-9-5. 실행 흐름 (사업자등록증명 예)

```
[맥북 사용자]
 ① POST /api/user/issue-requests
    body: {cert_type: BUSINESS_REGISTRATION, business_number: "..."}
    → issue_request(REQUESTED) + job(PENDING) 생성
        ▼
[Windows 에이전트]
 ② GET /api/agent/jobs/next (X-Agent-Token) — 5초 폴링
    → job(CLAIMED) 반환
 ③ 상태 RUNNING 전이
 ④ hometax_login(page, creds) — Phase 1 코드
 ⑤ #taKndSvcAllA3 클릭 (홈 → 카탈로그)
 ⑥ 사업자등록증명 링크 클릭 (Phase 1 관찰로 셀렉터 확보 후)
 ⑦ [신청]→[발급]→[출력] 자동 클릭
 ⑧ clipreport 팝업 캡처 (Phase 1 tick 루프)
 ⑨ PDF 저장 시도 (CDP Page.printToPDF) 실패 시 PNG
 ⑩ POST /api/agent/jobs/{id}/result (multipart)
        │
        ▼
[맥북 서버]
 ⑪ 파일 저장 → certificate_files 레코드
 ⑫ issue_request(ISSUED) + job(SUCCEEDED)
        ▲
 ⑬ GET /api/user/issue-requests/{id}/download ⇐ 사용자 다운로드
```

### 3-9-6. 자격증명·인증

**Windows 에이전트 자격증명 저장** — Windows 자격 증명 관리자 (`keyring` 라이브러리가 자동으로 DPAPI 백엔드 사용)

- `python -m certificate_agent setup` 실행 시 대화형으로 입력받아 자격 증명 관리자에 저장:
  - `easyone-cert-agent / hometax_id`
  - `easyone-cert-agent / hometax_pw`
  - `easyone-cert-agent / hometax_rrn_prefix`
  - `easyone-cert-agent / hometax_rrn_suffix`
  - `easyone-cert-agent / agent_token`
  - `easyone-cert-agent / server_url` (예: `http://192.168.1.10:8100`)
- 파일 저장 금지 (Phase 2 프로덕션 노트북 정책과 동일).
- Phase 2 로 갈 때는 **저장 위치·코드 무변경** — Windows 자격 증명 관리자를 그대로 씀. 세무사 대리 로그인용 값(관리번호 등)만 추가.

**서버 인증** — `X-Agent-Token`

- 관리자가 서버 CLI 로 토큰 발급 → 1회 노출 → Windows PC 에서 `setup` 시 입력.
- 서버는 SHA-256 해시만 저장. 토큰 유출 시 `DELETE /api/agent/agents/{id}` 로 즉시 폐기.

### 3-9-7. 개발·실행 명령 (사무실 Wi-Fi 로컬)

**맥북 (이지원천 서버 시뮬)**

```
cd ~/w/taxflow/rpa/certificate-server   # 저장 경로는 사용자 자유
uv venv && uv sync
uv run uvicorn certificate_server.main:app --host 0.0.0.0 --port 8100
# Swagger: http://localhost:8100/docs
# 사무실 LAN IP 확인: ipconfig getifaddr en0
```

에이전트 등록·토큰 발급 (같은 맥북, 새 터미널):
```
cd ~/w/taxflow/rpa/certificate-server
uv run python -m certificate_server.admin_cli register --name "Windows-김연호"
# 출력의 token 을 Windows setup 에 입력. 1회만 노출.
```

**Windows PC (에이전트) — 최초 1회**

PowerShell 또는 CMD:
```
git clone https://github.com/robin22121/taxflow.git C:\taxflow
cd C:\taxflow\rpa\certificate-agent
uv venv
uv sync
uv run playwright install chromium
uv run python -m certificate_agent setup
```

setup 프롬프트 순서:
1. 서버 URL — `http://<맥북 LAN IP>:8100`
2. 에이전트 토큰 — 맥북에서 발급받은 값
3. 홈택스 아이디 · 비밀번호 · 2차 인증 주민번호 앞6/뒤1

모두 **Windows 자격 증명 관리자** 에 저장 (파일 없음).

**Windows PC — 상시 실행**

```
cd C:\taxflow\rpa\certificate-agent
uv run python -m certificate_agent run
# 5초마다 GET /api/agent/jobs/next
```

**맥북 (사용자 요청 테스트)**

```
curl -X POST http://localhost:8100/api/user/issue-requests \
  -H 'Content-Type: application/json' \
  -d '{"cert_type":"BUSINESS_REGISTRATION","business_number":"..."}'
```

### 3-9-7-1. 착수 순서 (2026-09-18 작업)

증명원은 **사업자등록증명 1종만**. 로그인 경로를 두 단계로 나눠 진행한다.

**1단계 — 개인사업자 아이디 로그인 (현재)**

1. Windows PC ↔ 맥북 연결 확인 (`setup` → `dummy` 모드 1회 왕복 성공)
2. `CERT_AGENT_MODE=phase1` — 사용자 개인사업자 아이디·비밀번호·주민번호 앞6/뒤1 로 홈택스 로그인
3. 즉시발급증명 카탈로그 → 사업자등록증명 → [신청]→[발급]→[출력] 자동 클릭 → 파일 회수 → 맥북 업로드

**2단계 — 세무사 아이디 + 공동인증서 로그인 (1단계 성공 후)**

- 원래 Phase 2 스코프였으나, 실제 운영 경로가 세무사 대리 로그인이므로 Phase 1.5 에서 미리 실측한다.
- 추가 자격증명 (`setup` 확장): `hometax_cert_path` (인증서 파일 경로 또는 저장소 위치), `hometax_cert_pw`.
- **인증서 선택 창·비밀번호 입력은 Playwright 로 조작 가능** (2026-09-18 사용자 확인). 이 부분은 미지수가 아니다.
- 남은 실측 대상: 공동인증서 로그인이 **브라우저 확장·nProtect 등 별도 모듈**을 요구하는지, 인증서를 어느 저장 위치(하드디스크·브라우저 인증서 저장소)에서 읽는지 (`plan/16-wehago-rpa.md` §3-1 과 결과 공유).
- 세무대리 관리번호·수임처 다중 선택은 이 단계에서도 **범위 밖** — Phase 2.

### 3-9-8. Phase 1.5 완료 판정

1. 맥북에서 `POST /api/user/issue-requests` 로 발급 요청 → 202 응답 + issue_request_id
2. Windows 에이전트 로그에 `[+] job claimed: {id}` → `[+] login ok` → `[+] popup captured` → `[+] uploaded`
3. 맥북 `GET /api/user/issue-requests/{id}` 상태 `ISSUED`
4. 맥북 `GET /api/user/issue-requests/{id}/download` 로 사업자등록증명 파일 획득
5. 위 흐름이 사용자 조작 없이 (setup 이후) 반복 가능

### 3-9-9. Phase 1.5 → Phase 2 교체 지점

| 축 | Phase 1.5 | Phase 2 |
|-----|-----------|---------|
| 서버 스택 | 맥북 FastAPI + SQLite + 로컬 파일 | 이지원천 백엔드 + PostgreSQL + NHN Object Storage |
| 에이전트 실행 기기 | Windows PC (개발자 사양) | 사무소 자동화 전용 노트북 (Windows + BitLocker 강제) |
| 자격증명 저장 | Windows 자격 증명 관리자 (DPAPI) | 동일 (그대로) |
| 로그인 계정 | 사용자 개인사업자 | 세무사 대리 + 세무대리 관리번호 |
| 대상 사업자 | 사용자 본인 사업자 하나 | 수임처 다중 선택 |
| 통신 | HTTP (사무실 LAN) | HTTPS (인터넷) + 인증서 |
| PDF 저장 | `./storage/{id}.png` (또는 pdf) | NHN Object Storage + 서명 URL |
| 발급 함수 | `certificate-poc/` 재사용 | 동일 함수 그대로 이식 |

Phase 1.5 에이전트 실행 기기를 처음부터 Windows 로 잡았기 때문에 자격증명 저장·Playwright chromium·홈택스 nProtect 등
Windows 고유 환경을 미리 밟는다. Phase 2 로 갈 때 갈아 끼우는 축은 **서버 스택·로그인 앞단·저장소·통신 프로토콜** 넷.
`hometax_login.py` · 발급 함수 · tick 루프 기반 팝업 캡처는 Phase 1 → 1.5 → 2 로 그대로 옮겨간다.

## §4. Phase 2 — 프로덕션 (실제 시스템 흐름)

Phase 1이 확인해준 셀렉터·타이밍·인증서 처리 방식을 그대로 가져와 이지원천 시스템에 통합.

### 4-1. Phase 1 → Phase 2 교체 지점

| 축 | Phase 1 | Phase 2 |
|-----|---------|---------|
| 실행 기기 | 개발자 개인 PC | 사무소 자동화 전용 노트북 (`plan/16-wehago-rpa.md` §8-2) |
| 홈택스 계정 | 개발자 본인 개인사업자 아이디 | 세무사 대리 아이디 + 세무법인 공동인증서 + 세무대리 관리번호 |
| 대상 선택 | 단일 (본인 사업자) | 수임업체 지정 (검색·다중 선택) — 세무대리 화면에서 사업자번호 검색 → 화면 상호 대조 (`plan/16-wehago-rpa.md` §4-2 규칙) |
| PDF 저장 | 로컬 `./out/` | 이지원천 서버 오브젝트 스토리지 (NHN) + 로컬 즉시 삭제 |
| 트리거 | 개발자 콘솔 실행 | 이지원천 UI [발급요청] 버튼 → 서버 잡 큐 → 노트북 에이전트 폴링 |
| 결과 통지 | 콘솔·로컬 파일 | 이지원천 알림 → 담당자 검토 → 발송 액션 |
| 자격 증명 저장 | 실행마다 콘솔 입력 | Windows 자격 증명 관리자 (DPAPI) + BitLocker (`plan/16-wehago-rpa.md` §8-2) |
| 자동화 함수 (로그인 후) | `menu_navigate`, `certificates/*`, `pdf_verify` | **재사용** (Phase 1과 동일) |

### 4-2. 통합 사용자 흐름 (Phase 2)

```
[이지원천 · 사이드바 → "증명발급"]
 ① 발급 요청 화면 — 대상(수임업체 검색·다중 선택) + 증명원 종류(체크박스) + 옵션
 ② [발급요청] 클릭 ── 게이트 1
        │ 서버: certificate_issues 레코드 + rpa_jobs (kind=CERTIFICATE_ISSUE) 등록
        ▼
[자동화 전용 노트북]
 ③ 세무사 대리 로그인 + 세무대리 관리번호 (`plan/16-wehago-rpa.md` §4-4 ⑪ 재사용)
 ④ 대리 대상 사업자 선택 (사업자번호 검색 → 상호 대조)
 ⑤ 즉시발급증명 메뉴 → 종류 선택 → 옵션 입력 → 발급 → PDF 다운 (Phase 1 함수 재사용)
 ⑥ PDF 유효성 검증 (사업자번호·상호·발급일자를 요청 스냅샷과 대조)
 ⑦ 서버 업로드 (multipart) → 로컬 파일 즉시 삭제
        │ 서버: certificate_issues.status = ISSUED, pdf_object_key 채움
        ▼
[이지원천 · 담당자 알림]
 ⑧ 발급 이력 화면에서 PDF 확인 (미리보기 + 다운로드)
 ⑨ [발송] 클릭 ── 액션 게이트
    - 이메일 / 문자(알림톡+포털링크) / 팩스(Phase 3) / 다운로드
        │ 서버: certificate_deliveries 기록
        ▼
[완료] 발급·발송 이력 화면 (재발송 · 재발급 버튼)
```

- **게이트 1 (발급요청)**: 사용자 명시 클릭. 사무소당 동시 실행 1건 · 큐잉.
- **액션 게이트 (발송)**: 담당자 검토 후 명시 클릭. 자동 발송 없음.
- 알림·재발송·부재 시 인계는 `plan/16-wehago-rpa.md` §4-3 규칙 재사용.

### 4-3. UI

**사이드바 위치** — "세무" 그룹 하위, "원천세" 메뉴 아래 **"증명발급"** 추가. 배지: 미확인 발급 완료 건 수.

**발급 요청 화면**

```
[증명발급 > 새 요청]
┌────────────────────────────────────────────────┐
│ 대상  [수임업체 검색] [다중 선택 O]             │
│      선택: (주)가나 · 나다상사 · ...            │
├────────────────────────────────────────────────┤
│ 증명원 종류 (12종 카탈로그)                    │
│  [x] 사업자등록증명                            │
│  [ ] 납세증명서 (기타용)                       │
│       └ 유효기간: 30일                          │
│  [ ] 납부내역증명 (납세사실증명)               │
│       └ 기간: [2025-01-01] ~ [2025-12-31]      │
│  [ ] 소득금액증명                              │
│       └ 연도: [최근 1년 ▼] (최근 3년/5년/기간) │
│  [ ] 부가가치세 과세표준증명                   │
│       └ 과세기간: [2026년 1기 확정 ▼]         │
│  [ ] 부가가치세 면세사업자 수입금액증명        │
│       └ 기간: [_______________]                │
│  [ ] 폐업사실증명                              │
│  ─ 확장 대상 (Phase 2 후반~3) ────────────────  │
│  [ ] 휴업사실증명 · 표준재무제표증명 · ...     │
│  국문 [x]  영문 [ ]                            │
├────────────────────────────────────────────────┤
│ 요청 메모 (선택) [_____________________]       │
│                        [취소]  [발급 요청 ▶]   │
└────────────────────────────────────────────────┘
```

- 다중 대상 × 다중 종류 = 카티션 곱 (예: 수임처 3개 × 증명원 2종 = 6건).
- 대상별 로그인 유형(개인/사업자)이 다른 증명원이 섞이면 노트북 실행에서 순차 처리(개인 로그인 필요한 것 묶고 → 사업자 로그인 것 묶어서 세션 전환 최소화).
- 요청 즉시 발급 이력 리스트로 이동. 상태 실시간 표시.

**발급 이력 리스트**

| 컬럼 | 내용 |
|------|------|
| 요청일시 | 게이트 1 클릭 시각 |
| 대상 | 상호 (사업자번호) |
| 증명원 | 종류 · 주요 옵션 |
| 상태 | 요청 · 진행중 · 완료 · 실패 (실패는 사유·수동 안내) |
| 발급일자 · 유효기간 | 완료 건에 표시 (기타용 30일 등) |
| PDF | 미리보기 · 다운로드 |
| 발송 | 최근 발송 수단·수신자·시각 (중복 발송 경고) |
| 액션 | [발송] [재발급] [수동 처리 안내] |

- 필터: 상태 · 대상 · 증명원 종류 · 기간. 검색: 상호 · 사업자번호 · 요청 메모.
- **재발급 버튼**: 유효기간 만료 임박·만료 시 강조 배지. 원클릭으로 같은 옵션 재요청.

**발송 다이얼로그** — 탭 **이메일 · 문자 · 팩스 · 다운로드**. 팩스는 초기 disabled + "Phase 3 예정" 툴팁. 수신자·본문·템플릿 편집.

### 4-4. 아키텍처

`plan/16-wehago-rpa.md` §3 아키텍처와 동일 노트북·동일 크롬 인스턴스 공유. 세무사 대리 아이디·인증서 PW·관리번호는 이미 저장돼 있으므로 자격 증명 관리자에 항목 추가 없음.

- `rpa-agent/easyone_agent/` 에 새 잡 핸들러 `certificate.py`
  - `login_hometax_delegate()` — 원천세 RPA와 공유
  - `select_delegate_target(biz_no)` — 대리 대상 사업자 선택
  - `menu_navigate` · `certificates/*` · `pdf_verify` — **Phase 1에서 이식**
- 원천세 신고 잡과 동시 실행 방지 — `rpa_jobs` claim에 mutex 추가.

### 4-5. 데이터 모델

`rpa_jobs.kind` 확장

- `CERTIFICATE_ISSUE` (payload: `target_client_id`, `cert_type`, `options`, `login_mode`).

**신설 `certificate_issues`**

| 컬럼 | 타입 | 비고 |
|------|------|------|
| id | UUID | PK |
| tax_office_id | FK | 사무소 |
| target_client_id | FK Client | 수임업체 |
| requester_id | FK User | 요청자 |
| cert_type | enum | BUSINESS_REGISTRATION · TAX_CLEARANCE_ETC · TAX_PAYMENT_HISTORY · INCOME_AMOUNT · VAT_BASE · VAT_EXEMPT_INCOME · BUSINESS_CLOSURE · … |
| options | JSON | 기간·연도·유효기간·언어(KO/EN) 등 종류별 |
| rpa_job_id | FK rpa_jobs | |
| status | enum | REQUESTED · RUNNING · ISSUED · FAILED · CANCELED |
| issued_at | datetime | 홈택스 발급일시 (PDF 추출) |
| valid_until | date | 유효기간 (해당 종류만) |
| pdf_object_key | string | 오브젝트 스토리지 키 |
| pdf_sha256 | string | 무결성 검증 |
| business_number_snapshot | string | 발급 시점 사업자번호 (PDF 대조) |
| business_name_snapshot | string | 발급 시점 상호 |
| language | enum | KO / EN |
| failure_reason | string | |
| created_at · updated_at | | |

**신설 `certificate_deliveries`**

| 컬럼 | 타입 | 비고 |
|------|------|------|
| id | UUID | PK |
| certificate_issue_id | FK | |
| channel | enum | EMAIL · SMS_ALIMTALK · SMS_ONLY · FAX · DOWNLOAD |
| recipients | JSON | 이메일/전화/팩스번호 리스트 |
| body_template_used | string | |
| sent_by_user_id | FK User | |
| sent_at | datetime | |
| status | enum | QUEUED · SUCCEEDED · FAILED |
| provider_message_id | string | 게이트웨이 참조 |
| failure_reason | string | |

- PDF는 NHN Object Storage. 접근은 짧은 만료(기본 5분)의 서명 URL.
- `Client.last_certificate_issued_at` 요약 필드.

### 4-6. API (`/api/v1/certificates`)

| 메서드·경로 | 인증 | 용도 |
|------------|------|------|
| `POST /issue-requests` | 사용자 | 게이트 1 — 발급 요청 등록 |
| `GET /issues?...` | 사용자 | 발급 이력 리스트 |
| `GET /issues/{id}` | 사용자 | 상세 (PDF 서명 URL) |
| `POST /issues/{id}/cancel` | 사용자 | 대기·진행중 취소 |
| `POST /issues/{id}/re-issue` | 사용자 | 재발급 (유효기간 만료 대응) |
| `POST /issues/{id}/deliver` | 사용자 | 액션 게이트 — 발송 실행 |
| `GET /issues/{id}/deliveries` | 사용자 | 발송 이력 |
| `POST /agent/jobs/{job_id}/certificate-result` | 에이전트 | PDF 업로드 + 메타 회신 |

### 4-7. 담당자 발송 액션

- **이메일** — 발신 도메인 SPF·DKIM. 첨부: 발급 PDF + (옵션) 커버레터.
- **문자 (알림톡 우선 · SMS 폴백)** — 알림톡 템플릿 신설, 링크는 사장님 포털 다운로드 페이지 (30일 수명, `plan/12-owner-portal.md`). 첨부는 항상 링크형.
- **팩스** (Phase 3) — 게이트웨이 후보: 팩스투메일 · 아이팩스 · LG유플러스 팩스 API. 초기엔 다운로드 후 수동.
- **다운로드** — 즉시 서명 URL. 여러 건 ZIP (`{상호}_{증명원}_{발급일}.pdf`).
- 발송 결과는 `certificate_deliveries.status`. 재발송 버튼 상시 노출.

### 4-8. 안전장치

| 위험 | 장치 |
|------|------|
| 엉뚱한 사업자 증명원 발급 | 대리 대상 선택 후 상호·사업자번호 대조 (`plan/16-wehago-rpa.md` §4-2) |
| 다운받은 PDF가 요청과 다름 | PDF 텍스트에서 사업자번호·상호·발급일자 추출 후 요청 스냅샷 대조 (Phase 1 `pdf_verify.py` 재사용) |
| 만료된 증명원 오발송 | 발급 이력에 `valid_until` 표시, 만료·임박 시 발송 버튼 경고 배지 |
| 이메일 오수신 | 발송 다이얼로그 수신자 확인 체크박스 + 최근 발송 이력 노출 (중복 경고) |
| 인증서 · PW 유출 | `plan/16-wehago-rpa.md` §8-2 노트북 보안 조건 |
| 대량 요청 rate-limit | 사무소당 동시 실행 1건 · 큐잉. Phase 1 §3-7 8번 결과로 상한 조정 |
| 개인 로그인·사업자 로그인 잦은 전환으로 세션 끊김 | 요청 큐를 로그인 유형별로 묶어서 배치 처리 |
| PDF 서버 저장의 개인정보 위험 | 오브젝트 스토리지 서버측 암호화 + 짧은 서명 URL + 접근 로그 |
| 발송 실패 은폐 | 리스트 상태 배지, 실패 시 담당자 알림 재발송 |
| Phase 1 개발자 계정 데이터가 Phase 2 큐에 섞임 | `login_mode` 필드로 실행 시 검증 (`OWNER_SANDBOX` vs `DELEGATE`), 서버는 `OWNER_SANDBOX`를 프로덕션 큐에 넣지 않음 |
| 소득금액증명 등 개인 인증서 요구 | Phase 1 §3-7 2번 결과로 결정 — 필요 시 세무법인 명의 대리 발급 가능 여부 실측(대개 세무대리 관리번호로 커버) |

## §5. 로드맵

| Phase | 기간 | 산출물 | 종속 |
|-------|------|--------|------|
| **1 (시뮬레이션)** | 1~2주 · 개발자 혼자 | `rpa/certificate-poc/` + 우선순위 4종 로컬 발급 + NOTES.md 실측 결과 9개 | 개발자 개인 PC · 개인사업자 홈택스 계정 (기존 보유) |
| **1.5 (2대 분리 시뮬)** | 1~2주 | 맥북 얇은 서버 + Windows 에이전트 + HTTP(사무실 LAN) 폴링 + 로컬 PDF 저장 (사용자 개인 사업자 발급) | Phase 1 완료 · 사용자 소유 Windows PC |
| **2 (프로덕션)** | 4~8주 | 사이드바 "증명발급" 메뉴 · 세무사 대리 로그인 · 우선순위 7종 · 이메일 · 문자 · 다운로드 발송 | Phase 1 완료 · `plan/16-wehago-rpa.md` Phase 2 배포 (세무사 대리 로그인·자동화 노트북·자격 증명 관리자 공유) · `plan/13-messaging-activation.md` 알림톡 심사 · 이메일 게이트웨이 결정 |
| **3 (확장)** | 후속 | 팩스 자동발송 · 확장 대상 4종 (휴업·표준재무제표·종된사업장·소득확인) · 자동 재발급(만료 30일 전 알림 + 원클릭) · 반복 예약 | 사용자 요구 데이터 · 팩스 게이트웨이 선정 |

- Phase 2는 원천세 RPA(`plan/16-wehago-rpa.md`) Phase 2 배포 이전엔 시작하지 않는다 (세무사 대리 로그인 모듈·자동화 노트북·자격 증명 관리자 세팅 공유).

## §6. 후속 검토·미결정

- **이메일 게이트웨이 선택** — SendGrid · AWS SES · NHN Cloud Email. 사무소 도메인 SPF·DKIM 셋업 가이드 필요.
- **오브젝트 스토리지 위치** — NHN Object Storage 신규 버킷 · 접근 정책. 기존 이지원천 파일 저장 위치 재확인 후 재사용/신설.
- **PDF 텍스트 추출 라이브러리** — `pypdf` vs `pdfplumber`. Phase 1 §3-7 7번 결과로 결정.
- **알림톡 템플릿 심사** — 카카오 심사 필요. `plan/13-messaging-activation.md` 프레임에 새 템플릿 등록.
- **팩스 게이트웨이** — Phase 3 진입 시 3사 견적 · 커버시트 자동 생성 방식.
- **자동 재발급 스케줄** — 납세증명(30일 유효)·기타 만료 있는 증명 정기 재발급. 반복 예약(월 1회) UI 도입 여부.
- **감사 로그 보관 기간** — `plan/10-privacy-security.md` 최소 보관 원칙에 따라 결정.
- **원천세 RPA와의 큐 우선순위** — 원천세 마감(월 10일) 직전 증명발급이 몰릴 때 원천세 우선 정책.
- **Phase 1 자격증명 갱신** — 대화 노출된 개발자 계정 비밀번호는 Phase 1 검증 종료 후 반드시 변경. 인증서를 사용하는 종류가 실측되면 그 인증서도 갱신.
- **Phase 1 커밋 위치** — `rpa/certificate-poc/`를 정식 리포에 둘지, 별도 private 리포로 뺄지 결정. 어느 쪽이든 `.gitignore` 로 실행 결과·PDF·로컬 노트 강제 제외.
- **국문/영문 발급 UI 시점** — 요청 화면에서 언어 선택할지, 발송 시점에 언어 선택할지 (다국어 수신자 대비).
