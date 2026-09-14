# 위하고 급여 업로드 RPA (사무실 PC 에이전트)

> 2026-09-14 결정. 세무사 승인 후 이지원천의 **위하고 전송** 버튼 → 같은 사무실 Windows PC의
> 에이전트가 위하고T에 급여대장 엑셀을 업로드. 홈택스 자동신고(별도 노트북)는 후속 단계.

---

## 1. 왜 RPA를 다시 꺼내나 — 기존 결정과의 관계

`research.md` §3.2와 `plan.md` 핵심 결정 1은 "더존 API 협상·RPA 풀스택 폐기, 공식 엑셀 양식 활용"이었다.
이번 RPA는 그 결정을 뒤집지 않고 **범위를 좁혀** 얹는다.

- 입력 경로는 여전히 **위하고T 공식 급여자료 엑셀 업로드** 기능이다 (양식 리스크 없음)
- 자동화하는 것은 "로그인 → 수임처 열기 → 파일 올리기" **클릭뿐**이다
- 남는 리스크는 화면 변경 하나 → 실패 시 FAILED 회신 + 세무사 수동 업로드로 즉시 우회 가능
- 위하고 급여 입력용 공개 API는 확인되지 않음 (2026-09 웹 조사)

## 2. 확정된 운영 조건 (사용자 확인)

| 항목 | 결정 |
|------|------|
| 위하고 로그인 | ID/PW |
| 실행 PC | 세무사 사무실 별도 Windows PC — 직원이 이지원천을 쓰는 **같은 PC** |
| 브라우저 | 크롬 |
| 수임처 찾기 | **사업자번호** 검색 |
| 대조 | 업로드 직전 회사명 대조 |
| 실행 방식 | 세무사 승인 후 버튼 |
| 동시 사용 | 작업 중 직원은 위하고 사용 금지 |
| 홈택스 신고 | 별도 노트북에서 홈택스 RPA (후속, 같은 에이전트 구조 재사용) |

## 3. 구조 — 에이전트가 서버에 작업을 묻는다 (폴링)

```
[이지원천 화면] 세무사 승인 → 직원 '위하고 전송' 클릭
      │  POST /api/v1/rpa/wehago-uploads   (사용자 JWT)
      ▼
[NHN 서버] rpa_jobs 에 PENDING 등록 (사업자번호·상호 스냅샷)
      ▲  POST /agent/claim  (5초마다, X-Agent-Token)
      │  GET  /agent/jobs/{id}/payroll-excel
      │  POST /agent/jobs/{id}/result
[사무실 PC 에이전트] 전용 크롬 → 위하고 로그인 → 사업자번호로 수임처 → 상호 대조 → 업로드
```

- PC → 서버 **나가는 HTTPS만** 사용. 사무실 방화벽 개방·포트포워딩 불필요 (브라우저가 이미 쓰는 경로)
- **공유폴더 방식 기각**: 서버가 사무실 폴더에 직접 쓰는 건 불가능. "크롬 다운로드 폴더 감시" 변형은
  결과 회신 불가·승인 우회·파일명에 사업자번호 의존·중복 실행·개인정보 파일 잔존 문제로 기각

## 4. 데이터 모델 (`backend/app/models/rpa.py`, 마이그레이션 `a1c3e5f7b9d2`)

**`rpa_agents`** — 사무실 PC 에이전트
- `tax_office_id`, `name`, `token_hash`(SHA-256, unique), `last_seen_at`, `revoked_at`
- 토큰 원문(`rpa_…`)은 발급 응답에서 한 번만 노출

**`rpa_jobs`** — 거래처 × 신고월 작업 한 건
- `kind`(`WEHAGO_PAYROLL_UPLOAD`), `status`(PENDING/RUNNING/SUCCEEDED/FAILED/CANCELED)
- `monthly_filing_id`, `client_id`, `period`, `business_number`·`business_name`(등록 시점 스냅샷)
- `requested_by_user_id`, `agent_id`, `claimed_at`, `finished_at`, `result_message`

## 5. API (`backend/app/api/rpa.py`, prefix `/api/v1/rpa`)

| 메서드·경로 | 인증 | 설명 |
|------------|------|------|
| `POST /agents` | 사무소 관리자 | 에이전트 토큰 발급 (응답에 token 1회) |
| `GET /agents` | 사용자 | 에이전트 목록·마지막 접속 |
| `DELETE /agents/{id}` | 사무소 관리자 | 토큰 폐기 |
| `POST /wehago-uploads` | 사용자 | `{filing_id, client_ids}` → 거래처별 PENDING 작업 |
| `GET /jobs?filing_id=` | 사용자 | 작업 상태 목록 (화면 배너·결과 표시용) |
| `POST /jobs/{id}/cancel` | 사용자 | PENDING만 취소 |
| `POST /agent/claim` | 에이전트 | 작업 1건 가져가기 (`{"job": … \| null}`) |
| `GET /agent/jobs/{id}/payroll-excel` | 에이전트 | 급여대장 엑셀 (`generate_payroll_excel`) |
| `POST /agent/jobs/{id}/result` | 에이전트 | `{status: SUCCEEDED\|FAILED, message}` |

### 등록 게이트 (`POST /wehago-uploads`)
1. 사업자번호 없는 거래처 → 409 (엉뚱한 수임처에 올릴 위험)
2. 미승인 급여항목이 있는 거래처 → 409 (통합 다운로드와 같은 기준)
3. 자료 없는 거래처 → 409
4. 같은 신고·거래처에 PENDING/RUNNING 작업이 있으면 → 409 (중복 업로드 방지)

## 6. 안전장치

| 위험 | 장치 |
|------|------|
| 다른 회사에 업로드 | 사업자번호로 검색 → 결과 정확히 1건 → 화면 상호·사업자번호를 스냅샷과 대조((주)/주식회사·공백 무시). 하나라도 어긋나면 업로드 안 함 |
| 위하고 계정 동시 사용 → 세션 끊김 | 사무소당 RUNNING 1건만 (`claim`이 다른 RUNNING 있으면 null) + 화면 배너(프론트 과제) |
| 비밀번호 오류 반복 → 계정 잠금 | `LoginFailed` 1회에 에이전트 **자체 정지** |
| 에이전트 멈춤·PC 재부팅 | RUNNING 15분 초과 → FAILED. 같은 에이전트가 결과 없이 다시 claim → 재시작으로 보고 FAILED. 메시지에 "위하고 실제 반영 여부 확인" 안내 |
| 등록 후 승인 해제 | 엑셀 내려주기 직전에 승인·자료 재검사 |
| 급여파일 PC 잔존 | 처리 후 즉시 삭제 (`finally`) |
| 자격증명 유출 | 위하고 ID/PW·에이전트 토큰은 **Windows 자격 증명 관리자**에만. 서버에는 토큰 해시만 |
| PC 분실 | `DELETE /agents/{id}`로 즉시 폐기 |
| 직원 크롬과 섞임 | Playwright `launch_persistent_context` 전용 프로필 |

## 7. 미확정 — 위하고 화면 실측 과제

에이전트의 `ensure_logged_in` / `open_company` / `upload_payroll`은 아직 `NotImplementedError`.
실측 전에는 모든 작업이 FAILED로 회신되므로 오업로드는 없다.

- [ ] 로그인: 새 기기 인증·캡차·비밀번호 오류 잠금 횟수, 세션 만료 시간
- [ ] 수임처 검색: 사업자번호 입력 형식(하이픈), 결과 목록 구조, 수임처 전환 방식
- [ ] 급여자료입력 엑셀 업로드: 메뉴 경로, 귀속연월·지급일·급여구분 선택 위치
- [ ] 컬럼 매칭 설정이 **저장되는지** (수임처마다 다시 해야 하면 난이도 급상승)
- [ ] 22컬럼의 2행 병합 헤더·**합계행**을 제대로 읽는지 (합계행이 사원으로 읽히면 RPA용 파일에서 제외 필요)
- [ ] 수임처에 자가운전·육아·정산보험료·월세지원금 항목이 등록 안 돼 있을 때 동작
- [ ] 같은 달 재업로드 시 덮어쓰기/중복/차단 여부, 마감된 달 동작
- [ ] 성공·실패 메시지 표시 방식 (에이전트가 판독해 `result_message`로 회신)
- [ ] 파일 선택이 웹 input인지 윈도우 대화상자인지 (전자면 Playwright만으로 충분)

### 실측 진행 방식 — Windows PC에 Claude Code 임시 설치 (2026-09-14 선택)
- 설치: PowerShell `irm https://claude.ai/install.ps1 | iex` (Git for Windows는 선택)
- **테스트용 더미 수임처만** 열어둔 상태에서 진행 — 실제 거래처 급여가 화면에 뜨면 LLM으로 전송된다
- 위하고 ID/PW는 Claude에게 입력시키지 않고 **사람이 직접** 로그인 (Playwright 창에서)
- 끝나면 `/logout` 후 `%USERPROFILE%\.claude`, `%USERPROFILE%\.claude.json` 삭제·프로그램 제거

## 8. Windows PC 환경 체크

- 절전·화면잠금·자동 업데이트 재부팅 끄기
- 원격접속(RDP)으로 관리한다면 창을 닫아도 세션이 유지되는지 확인 (크롬이 화면 세션에 붙어 있음)
- 키보드보안·백신 프로그램이 자동 입력을 막는지
- 에이전트 상시 실행: 작업 스케줄러 "로그온 시 실행" (패키징은 후속)

## 9. 구현 상태

- [x] 설계 문서 (본 문서)
- [x] 서버: 모델·마이그레이션·API·테스트 (`backend/tests/test_rpa_wehago_upload.py`)
- [x] 에이전트 뼈대: 폴링 루프·서버 클라이언트·수임처 대조·자격증명 저장 (`rpa-agent/`)
- [ ] 위하고 화면 실측 → `rpa-agent/easyone_agent/wehago.py` 선택자 구현
- [ ] 프론트: 신고 상세의 **위하고 전송** 버튼(거래처 선택 모달 재사용), 진행 배너, 결과·실패 사유 표시, 에이전트 발급·폐기 화면
- [ ] 프로덕션 마이그레이션 `a1c3e5f7b9d2` 적용 (DB 변경 — 적용 전 사용자 확인)
- [ ] 에이전트 설치 패키징 (작업 스케줄러 등록)
- [ ] 후속: 홈택스 자동신고 에이전트 (별도 노트북, 공동인증서 로컬) — `plan/15-filing-relay.md`와 연결
