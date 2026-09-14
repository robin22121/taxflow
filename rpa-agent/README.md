# 이지원천 RPA 에이전트 (사무실 Windows PC)

세무사 화면에서 **위하고 전송**을 누르면, 이 에이전트가 같은 PC에서 위하고T에 접속해
거래처 급여대장 엑셀을 업로드하고 결과를 이지원천에 회신한다. 설계는 `plan/16-wehago-rpa.md`.

> ⚠️ 현재는 뼈대 단계다. 위하고 화면 조작(`easyone_agent/wehago.py`)은 화면 실측 전이라
> 모든 작업이 `NotImplementedError`로 **FAILED 회신**된다 — 잘못된 업로드는 일어나지 않는다.

## 요구사항

- Windows 10 이상, 크롬 설치, Python 3.12+
- 사무실 PC에서 `https://api.easyonechon.co.kr`로 HTTPS 접속 가능 (방화벽 개방 불필요)

## 설치

```powershell
py -m pip install httpx playwright keyring
```

크롬은 PC에 설치된 것을 쓰므로 `playwright install`로 브라우저를 따로 받을 필요는 없다.

## 최초 설정

1. 사무소 관리자 계정으로 에이전트 토큰 발급 — `POST /api/v1/rpa/agents` (`{"name": "사무실 위하고 PC"}`).
   응답의 `token`은 **한 번만** 보인다. (발급 화면은 프론트 작업 전이라 당분간 API 문서 `/docs`에서 호출)
2. 토큰과 위하고 ID/PW를 Windows 자격 증명 관리자에 저장:

   ```powershell
   py -m easyone_agent setup
   ```

## 실행

```powershell
py -m easyone_agent run
```

- 에이전트 전용 크롬 창이 뜬다. 직원 크롬과 프로필이 분리돼 있다.
- **에이전트가 도는 동안 직원은 같은 위하고 계정으로 로그인하지 않는다** (세션이 끊겨 작업이 실패한다).
- 위하고 로그인에 실패하면 계정 잠금을 막기 위해 에이전트가 스스로 멈춘다.

환경변수(선택): `EASYONE_API_BASE_URL`, `EASYONE_POLL_INTERVAL_SEC`(기본 5), `EASYONE_AGENT_HOME`(기본 `%USERPROFILE%\.easyone-agent`).

## PC 분실·교체 시

관리자 계정으로 `DELETE /api/v1/rpa/agents/{id}` — 해당 토큰이 즉시 막힌다.

## 테스트 (개발용)

```powershell
py -m pip install pytest
py -m pytest
```
