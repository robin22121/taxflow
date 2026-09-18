# certificate-server (Phase 1.5)

`plan/17-certificate-issuance.md` §3-9 — 이지원천 서버 시뮬. **맥북**에서 실행.
에이전트는 Windows PC (`rpa/certificate-agent/`) 에서 실행하며 이 서버를 폴링한다.

## 설정 + 실행

```
cd rpa/certificate-server
uv venv
uv sync
uv run uvicorn certificate_server.main:app --host 0.0.0.0 --port 8100
```

- Swagger: `http://localhost:8100/docs`
- 사무실 LAN IP 확인: `ipconfig getifaddr en0` — Windows 에이전트 `setup` 에 넣는다.

## 에이전트 등록 (관리자 CLI)

```
uv run python -m certificate_server.admin_cli register --name "Windows-김연호"
# 출력의 token 을 Windows setup 에 그대로 입력. 이 화면에서만 볼 수 있음.

uv run python -m certificate_server.admin_cli list
uv run python -m certificate_server.admin_cli revoke <agent_id>
```

## 흐름 (사용자 API)

```
POST /api/user/issue-requests   {cert_type, business_number, options}
GET  /api/user/issue-requests
GET  /api/user/issue-requests/{id}
GET  /api/user/issue-requests/{id}/download
```

## 저장물

- `./db.sqlite` — 잡·이력 (git-ignore)
- `./storage/{file_id}.{png|pdf}` — 발급 파일 (git-ignore, **개인정보 포함**)

Phase 2 에서 PostgreSQL + NHN Object Storage 로 교체. 서버 코드는 그대로 유지, 저장소 어댑터만 교체 예정.
