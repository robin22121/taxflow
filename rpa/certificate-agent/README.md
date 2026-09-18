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

## 흐름

```
[맥북 서버]          [Windows 에이전트]
                     ← 5초 폴링 GET /api/agent/jobs/next
잡 반환 (CLAIMED) →
                     execute_dummy / execute_phase1 (Phase 1 재사용)
                     ← POST /api/agent/jobs/{id}/result (multipart)
저장 + ISSUED
```
