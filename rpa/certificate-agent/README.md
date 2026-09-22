# certificate-agent (Phase 1.5)

`plan/17-certificate-issuance.md` §3-9 — 자동화 전용 노트북 시뮬. **Windows PC**에서 실행.
서버는 맥북(`rpa/certificate-server/`)에서 실행하며 이 에이전트가 폴링한다.

## 설정 (Windows PowerShell / CMD)

```
git clone https://github.com/robin22121/taxflow.git C:\taxflow
cd C:\taxflow\rpa\certificate-agent
uv venv
uv sync
uv run playwright install chromium
```

## 최초 1회 — 자격증명 등록

```
uv run python -m certificate_agent setup
```

프롬프트 순서:
1. 서버 URL (`http://<맥북 LAN IP>:8100`)
2. 에이전트 토큰 (맥북 admin CLI 에서 발급)
3. 홈택스 아이디
4. 홈택스 비밀번호
5. 2차 인증 주민번호 앞 6자리
6. 2차 인증 주민번호 뒤 1자리

모두 **Windows 자격 증명 관리자**(keyring 이 DPAPI 백엔드 자동 사용)에 저장됨. 파일·환경변수 저장 없음.

- `python -m certificate_agent show` — 마스킹된 저장 상태 확인
- `python -m certificate_agent clear` — 전부 삭제

## 실행 — 폴링 루프

기본 모드는 `dummy` (실제 홈택스 접속 없이 placeholder PNG 반환). 서버-에이전트 통신·저장 흐름을 먼저 검증한 뒤 실제 발급 모드로 전환.

```
# 통신 흐름만 검증 (홈택스 접속 없음)
uv run python -m certificate_agent run

# 실제 홈택스 로그인·[출력] 팝업 캡처
CERT_AGENT_MODE=phase1 uv run python -m certificate_agent run
```

`phase1` 모드는 `../certificate-poc/hometax_login.py` 를 `sys.path` 로 재사용.
카탈로그→신청→발급 자동화가 완성되기 전까지는 이미 발급해둔 이력의 첫 [출력]을 클릭해 결과 PNG 를 얻는다.

## 개발 모드 — 로그인해 둔 Chrome 에 부착

매번 로그인하지 않고 발급 구간만 반복할 때. 서버·`setup` 불필요, 맥북·Windows 공통.
Playwright 번들 chromium 대신 **시스템 Google Chrome** 을 쓴다.

```
uv run python -m certificate_agent chrome                    # CDP :9222 로 Chrome 실행 → 홈택스 직접 로그인 (창 유지)
uv run python -m certificate_agent attach --biz <사업자번호>  # 사업자등록증명 발급 → work/<ts>_cert.pdf
uv run python -m certificate_agent attach --biz <사업자번호> --rrn-disclosed   # 주민번호 공개
uv run python -m certificate_agent attach --cert TAX_CLEARANCE_ETC            # 납세증명서(기타용) — 로그인 납세자 기준
uv run python -m certificate_agent snap --tag <이름>          # 지금 화면 HTML·PNG → work/
```

- 끝나도 브라우저·로그인 유지. 코드 수정 후 `attach` 만 다시 실행.
- 전용 프로필 `work/chrome-profile/` 에 홈택스 쿠키가 남는다 (커밋 제외, 외부 복사 금지).
- 근거·구조: `plan/17-certificate-issuance.md` §3-9-7-3

## 이지원천 연동 — 증명원 발급 메뉴 (plan/17 §4-9)

이지원천 상단 `증명원 발급` 팝업에서 요청한 건을 받아 발급한다. 지금은 개발 경로(로그인해 둔 Chrome 부착)만.

```
uv run python -m certificate_agent chrome     # 홈택스 직접 로그인 (창 유지)
EASYONE_AGENT_TOKEN=rpa_... uv run python -m certificate_agent easyone --server https://api.easyonechon.co.kr \
    --save-dir "D:\이지원천\증명원"
```

- 토큰은 이지원천 에이전트 토큰(`POST /api/v1/rpa/agents`, `rpa_` 로 시작). 위하고 에이전트와 같은 토큰을 써도 작업은 섞이지 않는다 (증명원은 `/api/v1/certificates/agent/claim` 전용).
- 원본: `{save-dir}/{거래처}/{YYYYMMDD_HHMMSS}_{증명원}.pdf`. 서버에는 발송용 사본만 올라가고 30일 뒤 삭제된다.
- 이지원천에서 [폴더 열어 확인]을 누르면 다음 폴링(5초) 때 이 PC 에서 탐색기(Finder)가 저장 파일을 선택한 채 열린다.

## 흐름

```
[맥북 서버]          [Windows 에이전트]
                     ← 5초 폴링 GET /api/agent/jobs/next
잡 반환 (CLAIMED) →
                     execute_dummy / execute_phase1 (Phase 1 재사용)
                     ← POST /api/agent/jobs/{id}/result (multipart)
저장 + ISSUED
```
