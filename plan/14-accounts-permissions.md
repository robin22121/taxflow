# 사무소 계정·권한 — 세무사(OWNER) / 담당직원(STAFF) 분리

> 2026-09-13 작성 (코드 진단 기준 커밋 `55cb63a`). **상태: 설계안 — §9 결정 대기 2건.**
> 한 세무사사무소 안에서 직원 여럿이 **각자 담당 거래처의 원천세를 독립적으로** 처리하고,
> 세무사는 **사무소 전 거래처의 신고 현황**을 볼 수 있어야 한다.
> 사업주(거래처 사장님) 접근은 본 문서 범위 밖 — 로그인 없이 상설 링크+PIN으로 확정([`12-owner-portal.md`](12-owner-portal.md) §4).

---

## 1. 요구사항

| # | 요구 | 비고 |
|---|------|------|
| R1 | 직원마다 **개인 계정**으로 로그인 | 공용 계정 금지 (§8 1인 1계정) |
| R2 | 직원은 **자기 담당 거래처만** 조회·수정 | 담당 아닌 거래처는 존재 자체가 보이지 않음 |
| R3 | 세무사는 **사무소 전 거래처** 조회·수정 + 신고 현황 한눈에 | 핵심은 편집권보다 **가시성** (§7) |
| R4 | 세무사가 직원 계정 생성·퇴사처리·담당 배정 | 직원 자가 가입 금지 |
| R5 | 휴가 대직·퇴사 인수인계 | 재배정으로 처리 (§4) |
| R6 | 누가 어느 거래처·주민번호를 봤는지 기록 | 법정 접속기록 (§8) |

---

## 2. 현재 구현 진단

**사무소 단위 격리까지는 구현, 사무소 내부 직원별 분리는 전무.**

| 항목 | 현재 | 위치 |
|------|------|------|
| 테넌트 | `TaxOffice`(사무소). `User.tax_office_id`로 소속 | `backend/app/models/user.py:13`, `models/tax_office.py:23` |
| 역할 | `is_admin`, `is_superadmin` 불리언뿐. **`is_admin`은 권한 분기에 한 번도 쓰이지 않음**(표시용) | `models/user.py:18`, `api/auth.py:83,162,197` |
| 담당 배정 | **없음.** `Client`는 `tax_office_id`만 보유 | `models/client.py:21` |
| 로그인 ID | `users.email` 컬럼에 **사업자번호** 저장 → 사실상 사무소당 계정 1개 | `api/auth.py:80` |
| 인증 | JWT(HS256) Bearer, access 60분 / refresh 14일. `get_current_user`는 토큰 클레임이 아니라 **DB의 User를 매 요청 조회**(→ 권한 변경 즉시 반영되는 좋은 구조) | `core/security.py:29-54`, `core/deps.py:24` |
| 스코핑 | 자동화 없음. 엔드포인트마다 `x.tax_office_id != user.tax_office_id` **수동 비교 37곳** (filings 26 · clients 7 · imports 2 · collect 1 · employee_changes 1) | `api/filings.py:132…1328`, `api/clients.py:247…687` 등 |
| 공용 가드 | `require_same_office` 정의만 있고 **호출처 0건**(dead code) | `core/deps.py:43` |
| 프론트 | 토큰 `localStorage`, Next.js middleware 라우트 보호 없음 | `frontend/src/lib/api.ts:5-21` |

### 2.1 구조상 주의점 — `MonthlyFiling`은 거래처 단위가 아니다

`MonthlyFiling`은 **사무소 × 귀속월 공용 컨테이너**(`uq_filing_office_period`, `models/monthly_filing.py:25`)이고,
거래처 단위는 그 아래 `CollectionSession`(`models/collection.py:37`)·`PayrollEntry`다.
따라서 filings API 26곳은 "신고 건 소유권 체크"만으로는 STAFF 분리가 되지 않는다 — **신고 건 안의 행을 거래처 기준으로 걸러야** 한다(§5.2).

---

## 3. 역할 모델 — 2단계로 시작

`users.is_admin`(불리언) → `users.role`(enum)로 흡수.

| role | 거래처 범위 | 직원 계정 관리 | 담당 배정 | 사무소 설정 |
|------|------------|:---:|:---:|:---:|
| `OWNER` (세무사/대표) | 사무소 **전체** | ✅ | ✅ | ✅ |
| `STAFF` (담당직원) | **배정된 거래처만** | ❌ | ❌ | ❌ |

- `is_superadmin`(서버 운영자, 사무소 무소속)은 현행 유지 — 사무소 역할 체계와 별개 축.
- `OWNER` 복수 허용(동업 세무사). 단 **마지막 OWNER의 강등·비활성화는 금지**.
- 백필: `is_admin=True` → `OWNER`, 그 외 → `STAFF`. 현재 실사용 계정은 전부 가입 시 생성된 대표 계정이므로 사실상 전원 `OWNER`.
- **권한 판정은 DB User 기준 유지** — JWT에 role을 넣어 판정하지 않는다. 강등·퇴사가 다음 요청부터 즉시 반영된다(현 `get_current_user` 구조 그대로).

### 3.1 거부안 — 중간관리자(`MANAGER`) 선도입

실장급(전체 조회·수정 가능, 계정관리 불가) 역할은 **실제 요구가 확인될 때 추가**한다(§9-a).
enum 값 하나 추가로 확장 가능하므로 지금 넣을 이유가 없고, 넣으면 권한 매트릭스와 테스트가 즉시 1.5배가 된다.

---

## 4. 담당 배정 모델 — 단일 FK

```
clients.assigned_user_id   FK → users.id, nullable, index
client_assignment_history  (client_id, from_user_id, to_user_id, changed_by, changed_at)  -- append-only
```

- **1거래처 1담당.** 휴가 대직·퇴사 인수인계는 OWNER가 `assigned_user_id`를 바꾸는 것으로 처리.
- `assigned_user_id IS NULL` = **미배정** → STAFF에게 안 보이고 OWNER에게만 보임.
  OWNER 대시보드에 **"미배정 거래처 N건"** 경고 — 신규 거래처 방치 방지.
- 이력 테이블은 인수인계 추적 + **접근권한 부여·변경 내역 보관 의무**(§8) 증빙을 겸한다.

### 4.1 거부안 — M:N `client_assignments(client_id, user_id, role)`

- 이 제품은 **원천세 한 종목**만 다룬다 → "급여는 A, 부가세는 B" 같은 종목별 공동담당이 발생하지 않음.
- 대직·인수인계는 재배정으로 충분.
- M:N은 "최종 책임자가 누구인가"가 모호해지고, 모든 스코핑 쿼리가 서브쿼리/조인으로 바뀐다.
- **단, 한 거래처를 두 명이 동시에 보는 실무가 확인되면(§9-b) 이 안으로 전환.** 전환 비용은 §5 게이트 함수 내부만 바뀌도록 설계해 최소화한다.

---

## 5. 스코핑 강제 — 판정을 한 곳으로 모은다

**본 설계의 핵심.** 현재 37곳 수동 비교에 "담당자 조건"을 각각 얹으면 누락이 반드시 발생한다
(이미 공용 가드 `require_same_office`가 아무도 안 쓰는 dead code가 된 것이 그 증거).

### 5.1 게이트 함수 (`core/deps.py`)

```python
def visible_clients(user: User) -> Select:
    """user가 볼 수 있는 거래처 select. 목록·집계 쿼리는 전부 이것에서 출발."""
    q = select(Client).where(Client.tax_office_id == user.tax_office_id)
    if user.role == UserRole.STAFF:
        q = q.where(Client.assigned_user_id == user.id)
    return q

async def get_scoped_client(client_id: str, user=Depends(get_current_user), db=Depends(get_db)) -> Client:
    """단건 거래처 의존성. 사무소 불일치·담당 아님 모두 404."""
```

- **403이 아니라 404** — 남의 거래처 ID의 존재 여부 자체를 노출하지 않는다.
- 하위 테이블(`PayrollEntry`, `CollectionSession`, `Employee` …)에 **담당자 컬럼을 복제하지 않는다.** 항상 `client` 경유로 필터 — 복제하면 재배정 때 동기화 버그가 난다.
- §4.1 M:N 전환 시 이 두 함수 내부만 바뀐다.

### 5.2 엔드포인트 유형별 적용

| 유형 | 대상 | 적용 방식 |
|------|------|----------|
| **거래처 단건** | `api/clients.py` 7곳, `api/imports.py` 2곳 | `client_id` 파라미터 → `Depends(get_scoped_client)`로 교체 |
| **거래처 목록** | `select(Client)` 사무소 필터: `api/clients.py:79`, `api/filings.py:137,562,1338`, `api/employee_changes.py:82` | `visible_clients(user)`에서 출발 |
| **신고 건 조회(컨테이너)** | `MonthlyFiling` 사무소 필터: `api/clients.py:108,192,514`, `api/filings.py:95,117` | 사무소 필터 유지. 이후 붙는 거래처 행만 visible 집합으로 제한 |
| **거래처 생성** | 단건 `api/clients.py:92`, 일괄 `api/clients.py:213` | STAFF가 등록 → **본인에게 자동 배정**. OWNER가 등록 → 미배정(§4) |
| **세션 단건** | filings `/{filing_id}/sessions/{session_id}/…` 6개 (request · confirm-with-client · attachments GET/DELETE · attachments/raw · timeline · events DELETE), `api/collect.py:71` | `session.client_id`로 게이트 |
| **엔트리 단건** | filings `/{filing_id}/entries/{entry_id}` PATCH·DELETE, `api/employee_changes.py:67` | 해당 행의 `client_id`로 게이트 |
| **신고 건 집계·일괄** | filings `/dashboard`, `/entries`, `/entries/resign`, `/request`, `/invite`, 엑셀 2종(`wehago-excel`·`payroll-excel`), 간이지급명세서 2종(`statement-wage`·`statement-business`), 4대보험 5종(`insurance-acquisition`·`-loss`·`-change`·`-combined`·`-summary`), `/unified-download`, `/payslips` | 결과 행·발송 대상을 **visible 거래처 집합으로 필터**. STAFF의 일괄 발송·다운로드는 자기 담당분만 |
| **신고 건 생성·목록** | filings `POST ""`, `GET ""` | 컨테이너는 사무소 공용 → STAFF도 허용 |

> 집계·일괄 엔드포인트가 거래처 파라미터를 받는지는 **구현 착수 시 엔드포인트별로 확인**한다(본 진단은 라우트 목록 수준).

### 5.3 세션 인증 경로가 아닌 곳 — 변경 없음

- **카카오 웹훅**: `KakaoUserBinding.tax_office_id`로 사무소 결정(`api/webhooks.py:645-648`). 들어온 자료는 거래처 매칭 후 저장되므로 **자연히 담당 STAFF에게 노출**된다.
  단 거래처 매칭 실패분(`kakao_pending_messages`, 사무소 단위)은 담당자가 없다 → **OWNER 전용 "미분류함"**으로 둔다.
- **사업주 포털**(`api/public_collect.py`): 토큰이 곧 스코프. 영향 없음.
  포털 토큰 재발급·열람로그 확인([`12-owner-portal.md`](12-owner-portal.md) §4.5)은 해당 거래처 담당 STAFF와 OWNER 모두 가능.

### 5.4 회귀 테스트 (필수)

- STAFF-A 토큰으로 STAFF-B 담당 거래처의 client/session/entry ID를 **직접 호출 → 전부 404**
- STAFF 토큰으로 집계·다운로드 호출 → 결과에 타 담당 거래처 행 **0건**
- 재배정 직후 이전 담당자 접근 → 404
- OWNER → 미배정 포함 전 거래처 조회 가능

---

## 6. 로그인 ID · 계정 수명주기

### 6.1 로그인 ID

`users.email` 컬럼은 이미 "자유 문자열 전역 유니크"이므로 의미를 **로그인 ID**로 승격하고(컬럼명 변경은 선택),
연락처는 별도 컬럼 `contact_email`, `phone`으로 분리한다.

| 계정 | 로그인 ID | 이유 |
|------|----------|------|
| 대표(기존 OWNER) | **사업자번호 그대로** | 마이그레이션 불필요, 기존 사용자 영향 0 |
| 직원(STAFF·추가 OWNER) | **개인 휴대폰 번호** | 업무용 이메일 없는 직원 수용, 외울 것 없음, 임시비번·재설정 SMS 수신처 = 로그인 ID라 오입력 없음(Aligo 실발송 검증 완료 — [`13-messaging-activation.md`](13-messaging-activation.md)) |

- 이직 대응: 전역 유니크를 **활성 계정 한정 부분 유니크 인덱스**(`WHERE is_active`)로 바꿔, 퇴사 처리된 번호로 다른 사무소 계정을 만들 수 있게 한다.
- 로그인 실패 N회 시 일시 잠금(§8) — 포털 PIN 잠금(`client.py:32-34`)과 같은 패턴 재사용.

#### 6.1.1 거부안 — 사무소 인가코드(`short_code`) 접두 아이디 (예: `A3K9QZ-kim`)

**`short_code`는 사실상 비밀번호다.** 카카오 채널에 `등록 {코드}`를 보내면 추가 인증 없이 해당 사무소로 바인딩되고
이후 급여자료를 그 사무소 거래처로 넣을 수 있다(`api/webhooks.py:623-650`).
로그인 ID에 박으면 화면·로그·스크린샷으로 코드가 퍼진다.

> 📌 **별도 리스크 기록(본 문서 범위 밖)**: 인가코드 유출 시 타인이 사무소에 급여자료를 주입할 수 있다.
> 인가코드 재발급 기능 / 바인딩 목록·해제 UI를 [`10-privacy-security.md`](10-privacy-security.md) 검토 대상에 올릴 것.

### 6.2 계정 생성 — 자가 가입 금지

1. OWNER가 대시보드 "직원 추가"에서 이름·휴대폰·역할 입력
2. 임시 비밀번호 SMS 발송 (또는 초대 링크 — `SecureToken`에 `purpose="STAFF_INVITE"` 추가해 재사용)
3. 최초 로그인 시 **비밀번호 변경 강제** (`users.must_change_password`)
4. 담당 거래처 배정 (§4)

기존 `POST /auth/register`(사무소 + 대표 동시 생성)는 **사무소 가입 전용**으로 유지.

### 6.3 퇴사·비활성화

- **삭제하지 않고 `is_active=False`** — 접속기록·배정이력·`employee_change_requests.reviewed_by` 무결성 유지.
- 비활성화 즉시: 담당 거래처 전부 **미배정 전환** + OWNER 알림 + 배정이력 기록.
- `get_current_user`가 이미 `is_active`를 확인하므로 발급된 refresh 토큰도 다음 요청부터 무효.

### 6.4 프론트엔드

- `/me` 응답에 `role` 포함 → 직원관리·담당배정·미분류함 메뉴는 OWNER에게만 표시.
- **UI 숨김은 편의일 뿐, 권한은 백엔드가 강제**한다(§5).

---

## 7. 세무사 현황 보드 (OWNER 전용)

R3의 실체는 "전 거래처 편집권"보다 **"지금 어디가 막혀 있나"를 한눈에 보는 것**이다. 권한 모델을 복잡하게 만드는 대신 여기에 투자한다.

- **거래처 × 귀속월 매트릭스** — 셀 = 신고 진행 상태(요청전 / 수집중 / 검토대기 / 확정 / 제출완료)
- 담당자 컬럼 + **담당자별 필터·진행률**
- 상단 경고: 미배정 거래처 N건 · 신고기한 D-3 이내 미확정 N건 · 미분류 카톡 N건
- `MonthlyFiling`이 이미 사무소×귀속월 단위라 집계 쿼리가 자연스럽다

---

## 8. 개인정보 — 접근권한·접속기록

담당자 스코핑은 UX 기능이 아니라 **법정 안전성 확보조치의 이행 수단**이다.
「개인정보의 안전성 확보조치 기준」(개인정보보호위원회 고시) 기준으로 본 설계와 연결되는 의무:

| 의무 | 본 설계의 대응 | 현재 |
|------|---------------|------|
| 업무에 필요한 **최소 범위**로 접근권한 차등 부여 | §3 역할 + §5 담당자 스코핑 | ❌ 사무소 전원 전체 접근 |
| 개인정보취급자별 **계정 발급, 공유 금지** | §6 직원별 개인 계정 | ❌ **사무소 공용 계정 구조** |
| 인사이동·퇴직 시 **지체 없이 권한 변경·말소** | §6.3 비활성화 + 자동 미배정 | ❌ |
| 권한 부여·변경·말소 **내역 보관(3년)** | §4 `client_assignment_history` + 계정 변경 로그 | ❌ |
| 일정 횟수 인증 실패 시 **접근 제한** | §6.1 로그인 잠금 | ❌ |
| **접속기록 보관**(주민번호 등 고유식별정보 처리 시 **2년**) + 정기 점검 | §8.1 `access_log` | ❌ 없음 |

> 조문·보관기간은 현행 고시 기준 요약. G2(위탁구조 법무 자문) 때 함께 확인한다.
> 현재 공용 계정 구조 자체가 위 의무와 충돌하므로, **본 문서 1~2단계는 실데이터 투입 게이트(G1·G2)와 같은 급**으로 다룬다.

### 8.1 `access_log`

```
access_log (id, at, user_id, tax_office_id, ip, action, client_id, subject_employee_id, endpoint)
action ∈ VIEW | EDIT | DOWNLOAD | DECRYPT_RRN | LOGIN | LOGIN_FAILED
```

- **로깅 훅 지점 = §5 게이트.** 게이트가 한 곳으로 모이면 거래처 단위 조회 기록이 자동으로 따라온다 — 단일 게이트의 두 번째 이득.
- **주민번호 복호화 함수와 RRN 평문 포함 다운로드**(엑셀·명세서, [`10-privacy-security.md`](10-privacy-security.md) G6)는 게이트와 별개로 **반드시 명시 로깅**.
- 보관 2년, OWNER 대시보드에서 조회 가능. 이 테이블은 [`10-privacy-security.md`](10-privacy-security.md) 게이트 목록에 **신규 항목으로 편입 제안**(번호는 편입 시 부여).

---

## 9. 결정 대기 (사무소 실무 확인 필요)

- [ ] **(a) 중간관리자 계층이 실제로 필요한가** — 예: 실장이 전 거래처를 보되 직원 계정은 못 만드는 구조. "예"면 `MANAGER` 추가(§3.1)
- [ ] **(b) 한 거래처를 두 명이 같이 보는 경우가 실제로 있는가** — "예"면 §4를 M:N으로 전환(§4.1). 대직은 해당 없음(재배정으로 처리)

둘 다 "아니오"면 본 문서 설계 그대로 진행.

---

## 10. 구현 단계

| 단계 | 내용 | 검증 기준 |
|:---:|------|----------|
| **1** | 마이그레이션: `users.role`(+백필), `users.phone/contact_email/must_change_password`, `clients.assigned_user_id`, `client_assignment_history` | 기존 대표 계정 로그인·전 거래처 조회가 **변경 전과 동일** |
| **2** | `visible_clients` / `get_scoped_client` 도입, §5.2 표의 37곳 전환, `require_same_office` 제거 | §5.4 회귀 테스트 전부 통과 |
| **3** | 직원 초대·비활성화 API + 화면, 로그인 잠금, 최초 비번 변경 | 신규 STAFF가 미배정 거래처 0건 조회 / 비활성화 즉시 401 |
| **4** | 담당 배정 UI (거래처 목록 일괄 변경) + 미분류함 OWNER 전용화 | 재배정 후 이전 담당자 404, 이력 1행 생성 |
| **5** | `access_log` + RRN 복호화·다운로드 명시 로깅 | STAFF 조회 1회 → 로그 1행, 복호화 → `DECRYPT_RRN` 행 |
| **6** | OWNER 현황 보드 (§7) | 담당자 필터·미배정 경고 동작 |

- 1·2단계는 **사용자 체감 변화 없이** 먼저 배포 가능(전원 OWNER 백필이므로). 스코핑 누락 위험이 가장 큰 구간이라 분리 배포한다.
- 마이그레이션은 로컬 dev DB 드리프트 주의 — 사본에 stamp 후 격리 검증, 운영 alembic 체인 확인 후 적용.

---

## 관련 문서

- 데이터 모델 개념도: [`02-data-model.md`](02-data-model.md) — "세무사사무소 → 거래처" 사이에 사용자·담당 배정 추가 반영 필요
- 주민번호 보안 게이트: [`10-privacy-security.md`](10-privacy-security.md) — §8 접속기록 편입, §6.1.1 인가코드 리스크
- 사업주 포털 인증 모델: [`12-owner-portal.md`](12-owner-portal.md) §4
- SMS 발송: [`13-messaging-activation.md`](13-messaging-activation.md)
