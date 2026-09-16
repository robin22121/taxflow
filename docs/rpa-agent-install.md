# 자동화 노트북 설치 가이드 (위하고 RPA 에이전트)

이 문서는 이지원천 위하고 T RPA 에이전트를 **자동화 전용 노트북**에 처음 설치하고 PoC 1(로그인·봇 감지 실측)까지 돌리는 절차를 담는다. 실행 배경·정책은 `plan/16-wehago-rpa.md` 참고.

> **주의.** 이 노트북에는 위하고·홈택스·위택스 아이디·비밀번호·세무법인 공동인증서 비밀번호가 저장된다. 사무소 밖으로 반출하지 말고, 이 노트북 계정에만 자동화 프로그램을 두어야 한다 (`plan/16-wehago-rpa.md` §8-2).

---

## 0. 준비물

- Windows 10 (22H2 이상) 또는 Windows 11 노트북 1대
- 사무소 인터넷 연결 (사내 프록시가 있다면 관리자에게 위하고/홈택스/위택스·GitHub·Python·PyPI 접속 허용 요청)
- **세무사 사무소 소유의 자동화 전용 아이디**
  - 위하고 T (`www.wehagot.com`) — 아이디·비밀번호
  - 홈택스 (`hometax.go.kr`) — 아이디·비밀번호 + 세무대리 관리번호·비밀번호
  - 위택스 (`wetax.go.kr`) — 세무대리인 아이디·비밀번호
- **세무법인 공동인증서** — 노트북에 미리 설치되어 있어야 함 (인증서 관리 도구에서 목록에 뜨는 상태)
- **이지원천 에이전트 토큰** — 관리자 계정에서 `POST /api/v1/rpa/agents` 로 발급받아 안전한 채널(회사 메신저 DM 등)로 전달받는다. 발급 시 한 번만 노출되며 분실 시 재발급 필요.

---

## 1. Windows 보안 조건 (필수)

`plan/16-wehago-rpa.md` §8-2 조건. 하나라도 어기면 로컬 암호화 저장 방침이 무너진다.

| 항목 | 설정 위치 | 확인 방법 |
|------|-----------|----------|
| **BitLocker 디스크 암호화** | 설정 → 개인 정보 및 보안 → 장치 암호화 | "장치 암호화: 켜짐" |
| **Windows 로그인 비밀번호** | 설정 → 계정 → 로그인 옵션 → 비밀번호 | 비밀번호 로그인 필수, PIN·지문 병용 가능 |
| **자동 로그온 끄기** | `netplwiz` → "사용자 이름과 암호를 입력해야…" 체크 | 재부팅 시 비밀번호 화면이 뜬다 |
| **자동화 전용 Windows 계정 1개** | 설정 → 계정 → 다른 사용자 → 이 PC에 다른 사용자 추가 | 개인용 계정과 분리 (Windows 자격증명 관리자는 계정별로 격리됨) |
| **절전·자동 재부팅 끄기** | 설정 → 시스템 → 전원 → 화면·절전 → "안 함" / Windows Update → 활성 시간 조정 | 무인 실행 중 세션이 끊기지 않는다 |

크롬은 기본 설치돼 있으면 그대로. 없으면 `google.com/chrome` 에서 설치.

---

## 2. Python 설치

1. `python.org/downloads/windows` → "Python 3.12.x" 이상 인스톨러 다운로드 (권장: 3.12)
2. 설치 시 **"Add python.exe to PATH"** 체크 → "Install Now"
3. 확인:
   ```powershell
   python --version
   # Python 3.12.x
   ```

---

## 3. uv 설치 (Python 패키지 매니저)

에이전트는 uv로 의존성을 관리한다.

```powershell
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

새 PowerShell 창을 열어 확인:

```powershell
uv --version
# uv 0.5.x
```

---

## 4. Git 설치 (없으면)

`git-scm.com` 에서 "Git for Windows" 인스톨러 다운받아 기본값으로 설치. 확인:

```powershell
git --version
```

---

## 5. 코드 다운로드

에이전트 코드를 노트북에 클론한다. 전체 리포지토리는 약 3 MB — frontend/backend 소스도 함께 받지만 노트북에서는 실행되지 않는다 (`rpa-agent/`만 도는 구조).

```powershell
cd $env:USERPROFILE
git clone https://github.com/robin22121/taxflow.git
cd taxflow\rpa-agent
```

업데이트는 `git pull`.

---

## 6. Python 의존성 설치

```powershell
uv sync
uv run playwright install chromium
```

`uv sync`는 `httpx`·`playwright`·`keyring`·`pytest`를 자동 설치한다. `playwright install`은 CDP 연결 시에도 Playwright가 부팅 시 확인하므로 필요.

테스트로 확인:

```powershell
uv run pytest -q
# 25 passed in 0.1s
```

---

## 7. 크롬 실행 (CDP 포트 열기)

에이전트는 노트북에 **미리 띄워 둔** 크롬에 원격 디버깅 프로토콜(CDP)로 붙는다. 직접 크롬을 실행하지 않는다.

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start-chrome.ps1
```

이 스크립트가 하는 일:
- `chrome.exe` 를 찾아 실행 (`Program Files` 또는 `LOCALAPPDATA` 순서로 탐색)
- `--remote-debugging-port=9222`
- `--user-data-dir=%USERPROFILE%\.easyone-agent\chrome-profile` (개인 크롬과 분리)
- 이미 9222 포트가 열려 있으면 재실행 없이 그대로 사용

옵션:
- 포트 바꾸기: `-Port 9223`
- 다른 프로필: `-ProfileDir "D:\rpa-profile"`
- 크롬 경로 지정: `-ChromePath "C:\Chromium\chrome.exe"`

**주의.** 이 크롬을 닫으면 CDP 연결이 끊긴다. 무인 실행 중에는 창을 최소화만 하고 닫지 말 것.

---

## 8. 인증서·수동 로그인 (홈택스만, 첫 실행 전)

홈택스는 아이디 로그인 뒤 **공동인증서 팝업**이 뜬다. 이 팝업(DreamSecurity 계열)은 Windows 네이티브 다이얼로그라 브라우저 자동화 밖의 영역이다.

지금 방식은 setup에서 저장한 공동인증서 비밀번호를 에이전트가 자동 입력하는 흐름을 시도하되, **첫 로그인은 사람이 직접** 크롬에서 홈택스 → 아이디 로그인 → 인증서 선택 → 비밀번호 입력 → 세무대리 관리번호 로그인까지 완료해 두면 크롬 프로필에 세션이 남아 이후 자동화가 편해진다.

위택스는 세무대리인 아이디·비밀번호만으로 로그인 가능 (인증서 불필요).

---

## 9. 자격증명 저장 (setup)

`start-chrome.ps1` 로 크롬이 뜬 상태에서, 별도 PowerShell 창을 열고:

```powershell
cd $env:USERPROFILE\taxflow\rpa-agent
uv run python -m easyone_agent setup
```

입력 순서:

1. **이지원천 에이전트 토큰** (관리자에게서 받은 값)
2. 위하고 아이디
3. 위하고 비밀번호
4. (선택 y/N) 홈택스 아이디
5. (선택 y/N) 홈택스 비밀번호
6. (선택 y/N) 홈택스 세무대리 관리번호
7. (선택 y/N) 홈택스 세무대리 비밀번호
8. (선택 y/N) 홈택스 공동인증서 비밀번호
9. (선택 y/N) 위택스 아이디
10. (선택 y/N) 위택스 비밀번호

모두 **Windows 자격 증명 관리자(DPAPI 암호화)** 에 저장된다. 파일·서버·클라우드에는 저장되지 않는다.

비밀번호가 바뀌면 `setup`을 다시 실행해 해당 항목만 갱신.

토큰이 유출되거나 노트북 분실 시:
- 관리자 계정에서 `DELETE /api/v1/rpa/agents/{id}` — 토큰 즉시 폐기
- 위하고·홈택스·위택스 비밀번호 즉시 변경

---

## 10. PoC 1 실행 (로그인·봇 감지 확인)

```powershell
uv run python .\scripts\poc1_login_check.py --session-wait 300
```

시나리오:
1. 위하고 T 로그인 페이지 열기 → `navigator.webdriver` 값·봇 감지 문구 검사 → 자동 로그인 시도
2. 홈택스 로그인 페이지 열기 → 봇 감지 신호만 검사 (인증서 팝업 자동 조작은 별도 검토 중이므로 로그인 시도는 하지 않음)
3. 위택스 로그인 페이지 열기 → 봇 감지 신호만 검사
4. 5분 대기 후 세션 유지 여부 재확인 (`--session-wait 300`)

결과 리포트: `%USERPROFILE%\.easyone-agent\screenshots\poc1-YYYYMMDDTHHMMSS.json`
스크린샷 (봇 감지 트리거된 경우만): 같은 폴더에 `poc1-<사이트>-bot-hint.png`

리포트 예:

```json
{
  "started_at": "2026-09-17T14:23:11",
  "cdp_url": "http://127.0.0.1:9222",
  "sites": [
    {"name":"wehago","reached":true,"navigator_webdriver":false,"bot_hints_found":[],"login_ok":true},
    {"name":"hometax","reached":true,"navigator_webdriver":false,"bot_hints_found":[]},
    {"name":"wetax","reached":true,"navigator_webdriver":false,"bot_hints_found":[]}
  ],
  "session_wait_sec":300,
  "session_recheck":{"wehago":{"final_url":"...#/main","reached":true}}
}
```

**판정 (§9)**
- 3개 사이트 모두 `reached=true` + `bot_hints_found=[]` + `navigator_webdriver=false` + 위하고 `login_ok=true` → **PoC 1 통과, CDP 방식 확정**
- 하나라도 실패 → 노트북 크롬 익스텐션 방식으로 전환 검토 (`plan/16-wehago-rpa.md` §3-1)

---

## 11. 문제 해결

| 증상 | 원인 · 대응 |
|------|-------------|
| `노트북 크롬(http://127.0.0.1:9222)에 연결하지 못했습니다` | `start-chrome.ps1` 이 안 돌고 있음 → 실행. 방화벽이 로컬 포트를 막지는 않는지 확인 |
| `자격 증명 'wehago_password'이 없습니다` | `python -m easyone_agent setup` 을 아직 안 돌림 |
| 위하고 로그인 실패 (`아이디 또는 비밀번호가 올바르지 않음`) | **재시도 금지** — 계정 잠금 위험. setup 다시 실행해 정확히 저장 |
| 위하고 로그인 실패 (`자동입력 방지`·`QR 추가 인증`) | 사람이 크롬에서 직접 한 번 로그인해 세션 남기고 재시도. PoC 1 리포트에는 실패로 기록 |
| `navigator.webdriver=true` 로 나옴 | Playwright 부팅 시 CDP 연결이 아니라 새 브라우저를 띄운 것일 수 있음 → `start-chrome.ps1`으로 미리 크롬 실행되어 있는지 확인 |
| Windows Defender가 `chrome.exe` 원격 디버깅을 차단 | 예외 등록 또는 로컬 정책 조정. 사무소 IT팀 협조 필요 |
| Playwright chromium 다운로드가 느림 | 사내 프록시 문제일 수 있음. `HTTPS_PROXY` 환경변수로 우회 |

---

## 12. 매일 실행 흐름 (PoC 1 통과 후)

정식 운영 단계로 넘어가면:

```powershell
# 아침 첫 실행 (또는 재부팅 후)
powershell -ExecutionPolicy Bypass -File .\scripts\start-chrome.ps1
uv run python -m easyone_agent run
```

`easyone_agent run`은 이지원천 서버에 5초마다 폴링하며 작업이 들어오면 자동으로 처리한다. 로그인 실패가 발생하면 계정 잠금 방지를 위해 자체 정지 (§8-1).

Windows 작업 스케줄러에 등록해 부팅 시 자동 실행하는 방법은 별도 문서 예정.

---

## 참고

- 정책·설계: `plan/16-wehago-rpa.md` (§8-2 노트북 보안 조건 / §9 PoC 진행 순서 / §10 구현 상태)
- 코드: `rpa-agent/easyone_agent/` (`config.py`·`wehago.py`·`runner.py`·`logmask.py`)
- 실행 스크립트: `rpa-agent/scripts/start-chrome.ps1`·`poc1_login_check.py`
