# 이지원천 — 실행 계획 (인덱스)

> 세무 업무 AI 자동화 플랫폼 **이지원천** 사업기획서 v3.3의 실행 계획 인덱스.
> 시장·기술·리스크 분석 근거는 `research.md`, 기능별 상세 설계는 아래 `plan/*.md`를 참고.

---

## 분할 문서 목록

| 파일 | 다루는 영역 |
|------|------------|
| [`plan/00-decisions.md`](plan/00-decisions.md) | **현재 확정 사실 (결정 레지스트리)** — 인프라·메뉴·인증·게이트·보안 등 문서 간 충돌이 잦은 결정을 한 표로. 값이 바뀌면 여기를 먼저 고친다 |
| [`plan/01-workflow-roadmap.md`](plan/01-workflow-roadmap.md) | 통합 워크플로우 + Phase 1~4 로드맵 |
| [`plan/02-data-model.md`](plan/02-data-model.md) | 핵심 데이터 모델 (초기 기획은 SmartA 24컬럼, 구현은 위하고T 22컬럼 — `plan/00-decisions.md`) |
| [`plan/03-ai-parsing.md`](plan/03-ai-parsing.md) | AI 파싱·매칭 엔진·후속 질문 자동 발송 |
| [`plan/04-excel-outputs.md`](plan/04-excel-outputs.md) | SmartA 급여대장 엑셀 + 간이지급명세서·급여명세서 등 출력 양식 |
| [`plan/05-master-import.md`](plan/05-master-import.md) | 마스터 임포트 흐름 + 샘플 데이터 전략 |
| [`plan/06-insurance.md`](plan/06-insurance.md) | 4대보험 관리 UI·신고서 3종·EDI 가이드북 분석 |
| [`plan/07-business.md`](plan/07-business.md) | 사업화·재무 계획 (마일스톤·가격·GTM) |
| [`plan/08-action-items.md`](plan/08-action-items.md) | 액션 아이템 + 백로그 (진행 상태) |
| [`plan/09-design.md`](plan/09-design.md) | 디자인 와이어프레임 구현 A/B/C |
| [`plan/10-privacy-security.md`](plan/10-privacy-security.md) | 개인정보(주민번호) 보안 + 추후 결정·심화 검토 |
| [`plan/11-nhn-cloud-deploy.md`](plan/11-nhn-cloud-deploy.md) | NHN Cloud 이관·배포 런북 (실행 현황이 기준, Phase 0~5 계획은 이력) |
| [`plan/12-owner-portal.md`](plan/12-owner-portal.md) | 사업주 포털 (거래처 사장님용 무료 화면) — B2C 피벗 기각 근거·인증 모델 |
| [`plan/13-messaging-activation.md`](plan/13-messaging-activation.md) | 알림톡·SMS 발송 활성화 (Aligo IP 등록 + 카카오 템플릿 심사·코드 변경) |
| [`plan/14-accounts-permissions.md`](plan/14-accounts-permissions.md) | 사무소 계정·권한 — 세무사(OWNER)/담당직원(STAFF) 분리, 거래처 담당 배정, 스코핑 게이트, 접속기록 |
| [`plan/15-filing-relay.md`](plan/15-filing-relay.md) | 세무사 신고 릴레이 — 위하고 뒤에 붙는 홈택스 일괄 전송 + 접수증·납부서 거래처 자동 배송 (Phase 4+ 확장 후보) |
| [`plan/16-wehago-rpa.md`](plan/16-wehago-rpa.md) | 위하고 T·홈택스·위택스 원천세 자동화 RPA — 직원 전송 → 자동화 전용 노트북(세무사 전용 아이디)이 급여 입력·원천세 작업 → 제작 → 발송 확정 (확인 게이트 3개, `plan/00-decisions.md`) → 홈택스·위택스 신고 → 접수증·납부서 포털 반영 (약관 검토·안전장치·실측 과제) |
| [`plan/17-certificate-issuance.md`](plan/17-certificate-issuance.md) | 홈택스 증명발급 자동화 — "증명발급" 전용 화면 신설(상단 탭·사이드바 아님), 12종 즉시발급 대상, 담당자 검토 후 이메일·문자·팩스·다운로드 발송 (Phase 1 개발자 PC 스탠드얼론 → Phase 2 자동화 노트북·세무사 대리 로그인) |
| [`plan/18-kakao-inbound.md`](plan/18-kakao-inbound.md) | 카카오 인바운드(고객 문의 수신) 대안 검토 — §9 채택·기각 결정이 기준, §4~8은 후보 카탈로그(이력) |
| [`plan/19-worker-portal.md`](plan/19-worker-portal.md) | **근로자 포털 — 개요·인증·다국어 공유 기반** (사업주 포털 자매). 외국인 노동자 대상 급여·계약·근태 화면 묶음 |
| [`plan/20-worker-payslip.md`](plan/20-worker-payslip.md) | 근로자 급여명세서 교환·확인·이의제기 (근로기준법 §48 이행 채널) |
| [`plan/21-worker-contract.md`](plan/21-worker-contract.md) | 근로계약서 발급·다국어 요약·근로자 열람 (외국인고용법 모국어 요건) |
| [`plan/22-worker-attendance.md`](plan/22-worker-attendance.md) | 출근·연장근로 기록·근로자 이의제기 (사업주 입력 vs 근로자 대조) |
| [`plan/23-세무사세팅.md`](plan/23-세무사세팅.md) | **세무사 세팅** — 사무소 도입 시 기본 세팅 체크리스트 (자동화 노트북 설치·알리고 문자·카카오 채널·수임처별 위하고 사원·수당·공제 맞추기) |
| [`plan/24-wehago-official-guide-catalog.md`](plan/24-wehago-official-guide-catalog.md) | 위하고 T 공식 가이드 카탈로그 (연말정산·사회보험 등 자동화 범위 판단 자료) |
| [`plan/25-tax-law-compliance-checklist.md`](plan/25-tax-law-compliance-checklist.md) | **세법 준수 체크리스트** — 계산·서식 코드가 최신 법령·공식서식과 일치하는지 항목별 추적 (기능 버그 아닌 법령 정합성 검증용) |
| [`plan/26-status-and-agent-permissions.md`](plan/26-status-and-agent-permissions.md) | **[백로그]** 상태 정의 2계층(큰 단계 + 세부 상태) & AI 에이전트/RPA 권한 3단(direct/approval/denied) 설계안 — plan/02·03·10·16 반영 후보 |
| *(plan/27)* | 결번 — 사용처·사유 미기록. 새 문서는 29번부터 부여 |
| [`plan/28-invoice-issuance.md`](plan/28-invoice-issuance.md) | **[백로그·Phase 3+]** 세금계산서 발급 대행 — 사업주 포털 요청 → 세무사 승인 → 자동화 노트북(이지원) 홈택스 발급 → 담당자 최종 확인 → 사장님 발송. 접점·이탈방어 최강 트랙, 인증서 다계정 관리·법적 책임 경계 선결 |

---

## 핵심 워크플로우 (한눈에)

```
[전체 프로세스]
고객 원시데이터 → 급여 표준화·승인 → 위하고 T 입력(급여·원천세·지방세) → 홈택스·위택스 신고 → 접수증·납부서 포털·문자
       ▲                  ▲                      ▲                             ▲                    ▲
       │                  │                      │                             │                    │
   AI 자동수집         AI 표준화          자동화 노트북 RPA            자동화 노트북 RPA        포털·알림톡·문자
   (Phase 1)        (Phase 1)              (Phase 2)                    (Phase 2)             (Phase 2~3)
```

세부 워크플로우 [0]~[8] 단계는 `plan/01-workflow-roadmap.md` §1.2 참고.

---

## 단계별 로드맵 요약

| Phase | 기간 | 핵심 산출물 | 상세 |
|-------|------|------------|------|
| **Phase 1** | 0~6개월 | 다채널 자료수집 + SmartA 급여대장 엑셀 자동 생성 + 급여명세서 번들 | [`plan/01-workflow-roadmap.md`](plan/01-workflow-roadmap.md) |
| **Phase 2** | 6~12개월 | 자동화 노트북 RPA (위하고 T 급여·원천세·지방세 → 홈택스·위택스 신고) + 접수증·납부서 포털 반영·발송 | [`plan/01-workflow-roadmap.md`](plan/01-workflow-roadmap.md), [`plan/16-wehago-rpa.md`](plan/16-wehago-rpa.md) |
| **Phase 3** | 12~18개월 | 입·퇴사 자동화 + 4대보험 EDI RPA + 지급명세서 자동화 | [`plan/01-workflow-roadmap.md`](plan/01-workflow-roadmap.md), [`plan/06-insurance.md`](plan/06-insurance.md) |
| **Phase 4** | 18~24개월 | 부가세·종합소득세·법인세 보조 + 4대보험 인텔리전스 | [`plan/01-workflow-roadmap.md`](plan/01-workflow-roadmap.md), [`plan/15-filing-relay.md`](plan/15-filing-relay.md) |

---

## 핵심 의사결정 (v3.3 시점)

1. **자동화 경로**: SmartA 급여대장 엑셀 양식 활용 (더존 API 협상·RPA 풀스택 폐기) → **2026-09-15 갱신**: 서버 경유 RPA는 계속 폐기, 위하고 T·홈택스·위택스 원천세 처리는 **자동화 전용 노트북 RPA**로 범위를 좁혀 도입 (공식 엑셀 업로드 기능을 쓰고 클릭만 자동화, 사원등록 제외). 상세 [`plan/16-wehago-rpa.md`](plan/16-wehago-rpa.md)
2. **데이터 서식**: 위하고T 급여대장 양식이 데이터 저장·화면·엑셀 다운로드의 단일 기준. 초기 기획은 SmartA 24컬럼이었으나 **구현은 22컬럼** (2026-10-03 코드 확인, `plan/00-decisions.md`)
3. **차별화 포인트**: 1단계(고객 소통·자료 수집) AI 자동화 — 블랙피그/혜움이 못 푼 영역
4. **공동인증서·로그인 정보**: 클라우드 서버 사용·저장 불가 → 사무소 로컬 기기에서만 처리. 2026-09-15부터 위하고·홈택스·위택스 로그인 정보는 **자동화 전용 노트북에만 암호화 저장**(VeraCrypt). 홈택스 공동인증서 비밀번호도 노트북에만 저장해 자동 로그인하기로 2026-09-25 결정했으나 **구현 전** ([`plan/16-wehago-rpa.md`](plan/16-wehago-rpa.md) §8, 현황은 `plan/00-decisions.md`)
5. **인프라**: NHN Cloud 메인 (한국 리전, 2026-06-05 결정 → 2026-08-31 백엔드·DB 이관 완료). 백엔드/DB는 NHN Cloud(vm-node + RDS for PostgreSQL 17), 프론트는 Vercel 유지. 결정 근거·이관 현황은 [`plan/10-privacy-security.md` §3](plan/10-privacy-security.md), 배포 런북은 [`plan/11-nhn-cloud-deploy.md`](plan/11-nhn-cloud-deploy.md) 참고
6. **민감정보**: LLM에 주민번호 비전송 — 마스킹·주민번호 암호화 키는 NHN Cloud 내부(현재 vm-node `.env`, 향후 Secure Key Manager)에서만 복호화
7. **회신 수집**: "거래처 → 세무사 직원 → 이지원천" 카톡 1순위 → 이메일 → URL 폼, 단일 `_ingest_message()` 합류
8. **AI 프로바이더**: 코드 기본값은 Gemini Flash 2.5 / Claude Sonnet 폴백, **운영은 `AI_PROVIDER=anthropic`** (`AI_PROVIDER` 환경변수로 전환, `plan/00-decisions.md`)
9. **4대보험**: Phase 1에서 엑셀 3종(자격취득/상실/보수월액변경) + 세무사 상단 탭 메뉴(사이드바 아님), EDI 자동신고는 Phase 2~3
10. **사업주 포털**: 개인사업자 직접 과금(B2C 피벗)은 기각 — 세무사법·유닛이코노믹스·채널 자기잠식. 대신 거래처 사장님용 **무료 화면을 세무사 상품에 번들**. 인증은 **OTP 없이 상설 링크(만료 90일, 자동 갱신) + 세무사 발급 PIN**(PIN 게이트는 현재 비활성) — 2026-09-08 "30일 링크만" 결정이 09-10 개정됨. 상세는 [`plan/12-owner-portal.md`](plan/12-owner-portal.md)

근거 분석은 `research.md`, 세부 결정 맥락은 각 분할 문서 참고.
