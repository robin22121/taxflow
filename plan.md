# 이지원천 — 실행 계획 (인덱스)

> 세무 업무 AI 자동화 플랫폼 **이지원천** 사업기획서 v3.3의 실행 계획 인덱스.
> 시장·기술·리스크 분석 근거는 `research.md`, 기능별 상세 설계는 아래 `plan/*.md`를 참고.

---

## 분할 문서 목록

| 파일 | 다루는 영역 |
|------|------------|
| [`plan/01-workflow-roadmap.md`](plan/01-workflow-roadmap.md) | 통합 워크플로우 + Phase 1~4 로드맵 |
| [`plan/02-data-model.md`](plan/02-data-model.md) | 핵심 데이터 모델 (SmartA 24컬럼 기준) |
| [`plan/03-ai-parsing.md`](plan/03-ai-parsing.md) | AI 파싱·매칭 엔진·후속 질문 자동 발송 |
| [`plan/04-excel-outputs.md`](plan/04-excel-outputs.md) | SmartA 급여대장 엑셀 + 간이지급명세서·급여명세서 등 출력 양식 |
| [`plan/05-master-import.md`](plan/05-master-import.md) | 마스터 임포트 흐름 + 샘플 데이터 전략 |
| [`plan/06-insurance.md`](plan/06-insurance.md) | 4대보험 관리 UI·신고서 3종·EDI 가이드북 분석 |
| [`plan/07-business.md`](plan/07-business.md) | 사업화·재무 계획 (마일스톤·가격·GTM) |
| [`plan/08-action-items.md`](plan/08-action-items.md) | 액션 아이템 + 백로그 (진행 상태) |
| [`plan/09-design.md`](plan/09-design.md) | 디자인 와이어프레임 구현 A/B/C |
| [`plan/10-privacy-security.md`](plan/10-privacy-security.md) | 개인정보(주민번호) 보안 + 추후 결정·심화 검토 |
| [`plan/11-beta-funnel.md`](plan/11-beta-funnel.md) | 베타 모객 퍼널 — 저마찰 직접 가입(이메일 아이디·상호) + 혜택 문구(카카오·사업자검증은 후속) |

---

## 핵심 워크플로우 (한눈에)

```
[전체 프로세스]
고객 원시데이터 → 신고서 양식 변환 → 더존 SmartA 입력 → 홈택스 전자신고 → 접수증·납부서 자동 발송
       ▲                  ▲                ▲              ▲                  ▲
       │                  │                │              │                  │
   AI 자동수집         AI 표준화      RPA 에이전트       SmartA 내장기능      알림톡·문자 자동전달
   (Phase 1)        (Phase 1)         (Phase 2)        (Phase 2)          (Phase 2~3)
```

세부 워크플로우 [0]~[8] 단계는 `plan/01-workflow-roadmap.md` §1.2 참고.

---

## 단계별 로드맵 요약

| Phase | 기간 | 핵심 산출물 | 상세 |
|-------|------|------------|------|
| **Phase 1** | 0~6개월 | 다채널 자료수집 + SmartA 급여대장 엑셀 자동 생성 + 급여명세서 번들 | [`plan/01-workflow-roadmap.md`](plan/01-workflow-roadmap.md) |
| **Phase 2** | 6~12개월 | SmartA RPA 에이전트(pywinauto) + 접수증·납부서 자동 발송 | [`plan/01-workflow-roadmap.md`](plan/01-workflow-roadmap.md) |
| **Phase 3** | 12~18개월 | 입·퇴사 자동화 + 4대보험 EDI RPA + 지급명세서 자동화 | [`plan/01-workflow-roadmap.md`](plan/01-workflow-roadmap.md), [`plan/06-insurance.md`](plan/06-insurance.md) |
| **Phase 4** | 18~24개월 | 부가세·종합소득세·법인세 보조 + 4대보험 인텔리전스 | [`plan/01-workflow-roadmap.md`](plan/01-workflow-roadmap.md) |

---

## 핵심 의사결정 (v3.3 시점)

1. **자동화 경로**: SmartA 급여대장 엑셀 양식 활용 (더존 API 협상·RPA 풀스택 폐기)
2. **데이터 서식**: SmartA 24컬럼 양식이 데이터 저장·화면·엑셀 다운로드의 단일 기준
3. **차별화 포인트**: 1단계(고객 소통·자료 수집) AI 자동화 — 블랙피그/혜움이 못 푼 영역
4. **공동인증서**: 세무사 PC 로컬에서 처리 (클라우드 사용 불가)
5. **인프라**: NHN Cloud 메인 (한국 리전, 2026-06-05 결정 — 현재 Render+Vercel에서 이전 예정). 결정 근거·이전 절차는 [`plan/10-privacy-security.md` §3](plan/10-privacy-security.md) 참고
6. **민감정보**: LLM에 주민번호 비전송 — 마스킹·NHN Cloud Secure Key Manager 내부 복호화
7. **회신 수집**: "거래처 → 세무사 직원 → 이지원천" 카톡 1순위 → 이메일 → URL 폼, 단일 `_ingest_message()` 합류
8. **AI 프로바이더**: Gemini Flash 2.5 메인 / Claude Sonnet 폴백
9. **4대보험**: Phase 1에서 엑셀 3종(자격취득/상실/보수월액변경) + 별도 사이드바 메뉴, EDI 자동신고는 Phase 2~3

근거 분석은 `research.md`, 세부 결정 맥락은 각 분할 문서 참고.
