# 11. NHN Cloud 풀배포 계획 (Render+Vercel → NHN Cloud 단일 vm-node)

> 작성 기준일: 2026-08-31
> 대상 인프라: homi 인계 NHN Cloud KR1 (`homi/easyone`)
> 목적: 현재 Render(백엔드+DB)+Vercel(프론트) 라이브를 NHN Cloud 인프라 한 세트로 풀배포

---

## 0. 현황 요약 (계획의 전제)

### 현 라이브 토폴로지 (`render.yaml` 기준)
| 구성 | 위치 | 비고 |
|------|------|------|
| 백엔드 FastAPI | Render web (starter, singapore) | `alembic upgrade head` 빌드, uvicorn, `/healthz`, 업로드 `/data/uploads` 1GB 디스크 |
| DB PostgreSQL | Render Postgres (free) | |
| 프론트 Next.js | Vercel | `taxflow-gamma.vercel.app`, `easyonechon.co.kr` |
| Redis | **prod 미사용** | docker-compose(로컬 dev)에만 존재. 프로덕션 render.yaml엔 없음 |
| 오브젝트 스토리지 | prod 미사용 | 업로드는 로컬 디스크(`/data/uploads`)로 처리 |
| 워커/큐 | 없음 | 단일 web 서비스 |

### 타깃 NHN 인프라 (인계 받은 것 = 전부)
| 리소스 | 값 | 상태(2026-08-31 점검) |
|--------|-----|------|
| vm-node (공인) | `133.186.134.144` / 내부 `10.110.20.11` | Ubuntu 24.04.3, 4GB/50GB, nginx 1.24 active, uptime 53일 |
| External LB | 공인 `133.186.152.242` / VIP `10.110.20.50` | TLS 종료(self-signed) → vm-node:80, HTTP 301→HTTPS 200 |
| RDS PostgreSQL | private `10.110.50.100:5432` | v17.6, `appdb`/`dbadmin`, **빈 DB(테이블 0)** |
| Redis | **없음** | 신규 필요 시 vm-node에 설치 |
| 오브젝트 스토리지 | **없음** | 업로드는 vm-node 로컬 디스크 사용 |

**핵심 제약**: 백엔드 + 프론트 + (필요시)Redis를 **vm-node 단 한 대**에 nginx 리버스 프록시 뒤로 모두 올린다. LB는 앞단 TLS 종료용.

---

## ⚠️ Phase 0 — 사전 결정 & 시크릿 준비 (BLOCKING, 여기부터 승인 필요)

아래 결정이 나기 전엔 Phase 2 이후를 실행하지 않는다. Phase 1(스키마)만 결정 무관하게 선행 가능.

### 0-A. 최상위 결정: 이 환경의 성격
- [ ] **(A) 신규/스테이징 환경** — 빈 DB로 시작, Render 라이브는 그대로 유지. → 데이터 마이그레이션 불필요. **권장(리스크 최소)**
- [ ] **(B) Render 대체(운영 이관)** — 기존 라이브 데이터를 이 RDS로 옮기고 도메인 컷오버.
  - 추가 작업: Render DB `pg_dump` → RDS `pg_restore`, **`RRN_ENCRYPTION_KEY`를 기존 운영 키와 반드시 동일하게** 설정(주민번호 복호화), DNS 컷오버, 롤백 계획.

> ⚠️ (B)일 때 RRN 키가 다르면 기존 암호화된 주민번호를 복호화 못 함 → 데이터 손상. 이 결정이 가장 중요.

### 0-B. 프론트엔드 호스팅 방식
- [ ] **(1) vm-node에 직접 배포** — Node 설치, `next build`, systemd로 `127.0.0.1:3000` 구동. 완전 자립.
- [ ] **(2) Vercel 유지** — 프론트는 Vercel에 두고 `NEXT_PUBLIC_API_BASE_URL`만 새 백엔드로. 가장 간단하나 Vercel 의존 유지.

### 0-C. 도메인 & TLS
- [ ] 이 환경에 붙일 도메인: `easyonechon.co.kr`(운영 이관 시) / 서브도메인(예: `nhn.easyonechon.co.kr`, 스테이징) / IP만 사용(임시)
- [ ] TLS: LB self-signed → 공인 인증서 교체. Let's Encrypt(vm-node nginx 종료로 전환) or NHN LB 인증서 등록. **도메인 확정 후 진행.**

### 0-D. AI 프로바이더
- [ ] `AI_PROVIDER=anthropic`(현 운영) or `gemini`. 해당 API 키 확보.

### 0-E. Redis 필요 여부
- 현 prod가 Redis 미사용이므로 **기본은 미설치**. 코드가 런타임에 Redis를 강제하는지 1회 확인 후, 필요시에만 vm-node에 `redis-server` 설치(`127.0.0.1:6379`).

### 0-F. 시크릿 체크리스트 (배포 전 확보)
| 키 | 확보 방법 | 상태 |
|----|-----------|------|
| `DATABASE_URL` | `postgresql+asyncpg://dbadmin:<pw>@10.110.50.100:5432/appdb` (pw는 인계 env) | ✅ 보유 |
| `RRN_ENCRYPTION_KEY` | 신규: `openssl rand -base64 32` / 이관(B): **기존 운영 키 재사용** | ❗결정 |
| `APP_SECRET_KEY` | `openssl rand -base64 32` | 생성 |
| `JWT_SECRET` | `openssl rand -base64 32` | 생성 |
| `ANTHROPIC_API_KEY`/`GEMINI_API_KEY` | 기존 운영 키 | ❗필요 |
| 이메일/알림톡/SMS 키 | 초기엔 `stub`로 시작 가능 | 후순위 |

---

## Phase 1 — DB 스키마 적용 (최저 리스크, 선행 가능)

목표: 빈 RDS에 alembic 8개 마이그레이션 적용. **결정 A/B와 무관하게 지금 실행 가능**(단 B면 restore가 이를 대체).

1. SSH 로컬 포트포워딩 터널로 private RDS 접근:
   ```bash
   ssh -i keys/iac-vm-node-homi-easyone.pem -o IdentitiesOnly=yes \
       -L 15432:10.110.50.100:5432 ubuntu@133.186.134.144 -N &
   ```
2. 로컬 backend에서 마이그레이션:
   ```bash
   cd backend
   export DATABASE_URL='postgresql+asyncpg://dbadmin:<pw>@localhost:15432/appdb'
   # (get_settings가 요구하는 최소 env: DATABASE_URL, RRN_ENCRYPTION_KEY 등 더미 포함 필요할 수 있음)
   alembic upgrade head
   ```
   - **verify**: `alembic current` == head, `\dt`로 테이블 생성 확인, 8개 마이그레이션 반영.
3. 참조 데이터 시드(선택): `business_type_codes` 등 **wipe 없는** 시드만. ⚠️ `python -m app.scripts.seed`는 **DB를 wipe**하므로 운영엔 실행 금지.

> 대안: 로컬 의존성 설치가 번거로우면 Phase 2에서 vm-node에 코드 올린 뒤 vm-node에서 `alembic upgrade head` 실행(RDS 직접 도달). 이 경우 Phase 1을 Phase 2 뒤로 미룸.

---

## Phase 2 — 백엔드 런타임 (vm-node)

목표: vm-node에서 uvicorn(FastAPI)을 `127.0.0.1:8000`으로 systemd 상시 구동.

1. 런타임 설치: Python 3.12(현 운영 3.12.8), `python3-venv`, `postgresql-client`(설치됨).
2. 코드 배치: 저장소 clone 또는 배포 아티팩트 복사 → `/opt/taxflow`(backend rootDir). 배포 사용자/권한 정리.
3. venv + `pip install -r backend/requirements.txt`.
4. 시크릿 파일 `/etc/taxflow/taxflow.env`(root:600, git 미포함) — Phase 0-F 값 + `APP_ENV=prod`, `APP_DEBUG=false`, `APP_BASE_URL`, `APP_PUBLIC_URL`, `CORS_EXTRA_ORIGINS`.
5. 업로드 디렉토리 `/data/uploads`(또는 `/var/lib/taxflow/uploads`) 생성·권한.
6. (스키마 미적용 시) `alembic upgrade head` 실행.
7. systemd 유닛 `taxflow-backend.service`: `EnvironmentFile=/etc/taxflow/taxflow.env`, `ExecStart=.../uvicorn app.main:app --host 127.0.0.1 --port 8000`, `Restart=always`.
   - **verify**: `curl -s 127.0.0.1:8000/healthz` == 200, `systemctl status` active.

---

## Phase 3 — 프론트엔드 (0-B 결정에 따름)

**(1) vm-node 직접 배포 시:**
1. Node LTS 설치, `frontend`에서 `npm ci && npm run build`.
2. `NEXT_PUBLIC_API_BASE_URL` = 백엔드 접근 경로(같은 도메인이면 `/api` 프록시 권장).
3. systemd `taxflow-frontend.service`: `next start -p 3000`(`127.0.0.1:3000`), `Restart=always`.
   - **verify**: `curl -s 127.0.0.1:3000` 200.

**(2) Vercel 유지 시:** Vercel 환경변수의 API base를 새 백엔드 도메인으로, 백엔드 `CORS_EXTRA_ORIGINS`에 Vercel/도메인 추가. vm-node엔 프론트 미배치.

---

## Phase 4 — nginx 리버스 프록시 재구성

목표: placeholder(`vm-node OK`) 제거, 실제 라우팅.

- 라우팅(동일 도메인 방식):
  - `location /` → `http://127.0.0.1:3000`(프론트, 방식1) 또는 정적/Vercel(방식2)
  - `location /api/` (및 백엔드 경로) → `http://127.0.0.1:8000`
  - `X-Forwarded-For/Proto` 헤더 전달(LB가 TLS 종료하므로 `X-Forwarded-Proto=https` 신뢰 설정).
- LB→vm-node는 HTTP 80 유지(현 구성). nginx 80에서 상기 라우팅.
  - **verify**: `curl -k -I https://133.186.152.242/` 실제 앱 응답(200), `/api/healthz` 200, `/healthz` 도달.

---

## Phase 5 — 도메인 & 공인 TLS (0-C 결정 후)

1. DNS: 대상 도메인 A레코드 → LB 공인 IP `133.186.152.242`.
2. 공인 인증서:
   - (a) LB에서 TLS 종료 유지 → NHN LB에 공인 인증서 등록(도메인 소유 검증).
   - (b) 또는 TLS 종료를 vm-node nginx로 이전 + Let's Encrypt(`certbot`) 자동 갱신. LB는 TCP 패스스루로 변경 필요.
3. 앱 URL 갱신: `APP_PUBLIC_URL`, `APP_BASE_URL`, `CORS_EXTRA_ORIGINS`, 프론트 API base.
   - **verify**: `https://<도메인>/` 인증서 유효(브라우저 경고 없음), 로그인 등 정상.

---

## Phase 6 — 보안 하드닝 & 운영 검증

- [ ] **SSH 22 소스 제한**: `iac-vm-node-sg` ingress 22를 `0.0.0.0/0` → 관리자 고정 IP. (인계 문서도 권장)
- [ ] 시크릿 git 미포함 확인(`/etc/taxflow/taxflow.env`, `.env` 커밋 금지).
- [ ] **RDS 백업**: 단일 인스턴스(HA 없음) → NHN RDS 자동 백업/스냅샷 정책 확인 + `pg_dump` 크론(vm-node → 별도 저장소) 병행.
- [ ] **SPOF 인지**: vm-node 1대·RDS 1대 = 단일 장애점. 운영 트래픽 규모에 따라 이중화/HA 승급 검토(비용 트레이드오프).
- [ ] E2E 스모크: 회원가입/로그인, 급여자료 업로드·파싱, 엑셀 산출, 주민번호 암복호화 라운드트립.
- [ ] 로그/모니터링: NHN monitoring agent(설치 확인됨) + 앱 로그 로테이션.

---

## 실행 순서 요약 (우선순위)

```
Phase 0  결정·시크릿           ← 승인 게이트 (0-A RRN 키가 최우선)
  │
Phase 1  DB 스키마 (빈 RDS)     ← 결정 무관 선행 가능 / (B)면 pg_restore로 대체
  │
Phase 2  백엔드 systemd 구동
  │
Phase 3  프론트 (vm-node or Vercel)
  │
Phase 4  nginx 리버스 프록시
  │
Phase 5  도메인 + 공인 TLS
  │
Phase 6  보안 하드닝·백업·E2E
```

## 확정된 결정 (2026-08-31)
1. **(B) 운영 이관** — Render 대체. 단 기존 DB는 전부 더미데이터라 **데이터 마이그레이션 불필요**, RRN 키 새로 생성.
2. **프론트: Vercel 유지** — 백엔드/DB만 NHN. vm-node엔 프론트 미배치.
3. 도메인: **미정** (백엔드용 공인 도메인 필요, 예 `api.easyonechon.co.kr`).
4. `ANTHROPIC_API_KEY`: **미제공** (부팅엔 불필요, AI 파싱 기능 사용 전 필요).

---

## 🟢 실행 현황 (2026-08-31)

### 완료 (검증됨)
- **Phase 1 — DB 스키마**: `alembic upgrade head` → head `f7a8b9c0d1e2`, **16개 테이블 생성**.
  - ⚠️ NHN RDS 기본 스키마가 `public`이 아닌 **`rds`** (dbadmin search_path). 앱·alembic 동일 계정이라 정합성 OK.
- **Phase 2 — 백엔드**: `/opt/taxflow`(backend 코드) + venv(Python 3.12.3) + 의존성 설치.
  - `/opt/taxflow/.env` (600): APP_ENV=prod, 시크릿 3종 생성, DATABASE_URL(asyncpg→RDS), CORS(Vercel 허용), 슈퍼어드민 시드.
  - systemd `taxflow-backend.service` (uvicorn `127.0.0.1:8000`, enable+active). `/healthz` 200.
  - 슈퍼어드민 `robin1q84@gmail.com` 시드됨.
- **Phase 4 — nginx 리버스 프록시**: placeholder 제거, `/`=200 헬스스텁 + 그 외 → `:8000` 프록시.
  - ⚠️ LB 헬스모니터가 `/`→200 기대. 백엔드 `/`는 404라 한때 503 → nginx `location = /` 200 스텁으로 해결.
- **E2E 검증**: LB 경유 `POST /api/v1/auth/login` → **200 + JWT 발급** (RDS 조회+argon2+서명 전구간 동작).

- **Phase 5 — 도메인 + 공인 TLS** ✅ (경로 B: vm-node 직접, LB 우회):
  - 가비아 A레코드 `api.easyonechon.co.kr` → `133.186.134.144` (전파 확인).
  - vm-node 보안그룹 `iac-vm-node-sg` 인바운드 tcp/80·443 `0.0.0.0/0` 개방.
  - nginx `server_name api.easyonechon.co.kr`, certbot `--nginx` → **Let's Encrypt 인증서** (만료 2026-11-29, 자동 갱신 스케줄됨), HTTP→HTTPS 301.
  - `APP_BASE_URL=https://api.easyonechon.co.kr` 갱신, 백엔드 재시작.
  - 검증: `https://api.easyonechon.co.kr/healthz` 200(공인 cert), 실도메인 로그인 200.

### 남은 작업 (사용자 입력/접근 필요)
- **Vercel 재배선**: `NEXT_PUBLIC_API_BASE_URL` → `https://api.easyonechon.co.kr` 후 재배포. (Vercel 접근 필요)
- **AI 키**: `/opt/taxflow/.env`의 `ANTHROPIC_API_KEY` 채우고 `sudo systemctl restart taxflow-backend`.
- **Phase 6 보안**: SSH 22 소스 제한, RDS 자동백업/`pg_dump` 크론. (선택, 권장)
- **Render 폐기**: Vercel 컷오버 확인 후.

### 재배포 방법(현재 방식)
로컬 코드 → `tar | ssh … tar x -C /opt/taxflow` → `sudo systemctl restart taxflow-backend`.
(추후 git 기반 배포로 전환 권장.)
