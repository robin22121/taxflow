# AI 파싱 + 매칭 + 후속 질문

> plan.md §3.2, §3.4 분리본. 카톡/이메일 비정형 텍스트 → 구조화 데이터, 매칭 결과 → 후속 질문 자동 발송.

---

## AI 파싱 핵심 로직 (의사 코드)

```python
async def parse_payroll_message(
    raw_text: str,
    client_id: str,
    previous_month_data: dict,
    employee_master: list[Employee]
) -> PayrollParsingResult:
    """
    카톡/이메일 텍스트 → 구조화된 인건비 데이터 + 매칭 결과
    """
    prompt = f"""
    아래는 세무사 거래처가 보낸 이번 달 인건비 자료입니다.

    [거래처 직원 마스터]
    {employee_master}

    [이전 달 데이터]
    {previous_month_data}

    [이번 달 메시지]
    {raw_text}

    다음 JSON 형식으로 반환:
    {{
      "matched_employees": [
        {{"name": str, "employee_id": str, "amount": int,
          "change_from_prev": int, "change_reason": str | null}}
      ],
      "new_hire_suspected": [
        {{"name": str, "amount": int, "needs_confirmation": true}}
      ],
      "resignation_suspected": [
        {{"employee_id": str, "name": str, "reason": "이번달 누락"}}
      ],
      "ambiguous_items": [
        {{"raw_text": str, "issue": str}}
      ],
      "relative_references": [
        {{"text": "저번달과 동일", "applied": true}}
      ]
    }}
    """
    response = await claude_client.messages.create(
        model="claude-sonnet-4-5",
        messages=[{"role": "user", "content": prompt}]
    )
    return validate_and_parse(response)
```

매칭 엔진 동작 조건과 임계값:

- 기존 직원 매칭: rapidfuzz 85점 이상
- 이상치 감지: 전월 대비 1.5배 이상 변동 + 30만원 이상
- **전제 조건**: 직원 마스터 + 전월 급여 이력이 DB에 있어야 정상 작동 (없으면 `NEW_HIRE_SUSPECTED` 폭주)
- 마스터/전월 이력 확보 흐름은 `05-master-import.md` 참고

상대 표현 처리:
- `"저번달과 똑같아요"` → 전월 PayrollEntry 그대로 복사
- `"김연호만 10만원 인상, 나머지 동일"` → 부분 적용

LLM 송신 전 RRN/주민번호 스크러빙은 게이트 G3, 파일에 함께 실려온 RRN을 서버가 결정론적으로 뽑아 암호화 저장하는 것은 게이트 G4로 처리 — 두 층이 동시에 성립하는 원칙은 `10-privacy-security.md` §2.0 참고. AI 파서의 입력·출력 스키마엔 RRN 필드를 두지 않고, 반입 지점에서 만든 `{이름 → rrn_last4, rrn_encrypted}` 맵을 파싱 결과에 서버 사이드채널로 병합해 UI에 프리필한다. AI 프로바이더는 Gemini Flash 2.5 메인, Claude Sonnet 폴백 (research.md §4.4).

---

## 후속 질문 자동 발송

신규 의심자가 감지되면 한 번에 묶어서 발송:

```
"확인이 필요한 사항이 있습니다

1. 박민수님 — 신규 입사자이신가요?
   맞다면 아래 안전 입력 폼에서 주민번호·입사일을 입력해주세요:
   https://taxflow.ai/secure/abc123

2. 김연호님 — 전월 100만원 → 이번달 200만원으로 증가했어요.
   상승 사유를 알려주세요. (보너스/급여인상/기타)

3. 이영수님 — 이번달 자료에서 누락되었어요. 퇴사하셨나요?"
```

- 채널 우선순위: 카카오 알림톡 > SMS > 이메일 (기존 채널 재활용)
- 주민번호는 본문에 받지 않고 보안 입력 URL(개별 토큰)로 분리

---

## 신규직원 감지 시 사무소 사용자 팝업 (2026-09-30 제안)

위 "후속 질문 자동 발송"은 **거래처 사장님**에게 신규 입사 여부를 확인받는 흐름이다. 이와
별개로, `new_hire_suspected` 항목이 있는 급여명세를 **사무소 사용자**(세무사·직원)가
검토·승인하는 화면(`filings/[id]` 검토 대상 섹션)에서, 해당 항목을 열람하거나 승인하려 할 때
별도 팝업을 띄운다:

> "이지원천과 위하고에 신규직원등록해야합니다"

팝업의 "사원정보로 이동" 버튼 클릭 시 "원천세 신고 > 사원정보 등록/변경"
(`/dashboard/employee-changes`, `08-action-items.md` 2026-09-30 상단 메뉴 개편 항목)로 이동한다.

- **차단 지점 (2026-09-30 정정)** — 실제 차단은 §4-1/§4-7(전송 게이트, 거래처 단위)이 아니라
  **원천세관리 화면에서 해당 항목(직원)의 '승인' 버튼을 누르는 시점**에 건다.
  `new_hire_suspected`인 항목은 이지원천 사원 마스터에 매칭되는 직원이 등록되기 전까지
  승인 자체가 막힌다(팝업 안내 후 승인 버튼 비활성화, 또는 클릭 시 팝업을 띄우고 승인
  처리를 막음) — 건별로, 해당 소득자가 매칭될 때까지 반복적으로 걸린다.
- **기존 §4-7과의 관계** (`16-wehago-rpa.md` "사원등록 안내(자동화 제외)") — 기존 설계는
  **전송(게이트 1) 단계**에서 이지원천의 입·퇴사 변동 데이터를 기준으로 "위하고 사원등록
  완료" 체크를 확인·차단하는, **거래처 단위의 별개 안전망**이다(§4-1 표, §4-7). 이번 승인
  단계 차단과는 독립적으로 계속 작동 — AI가 놓친 케이스나 위하고 쪽 등록 누락을 게이트 1에서
  한 번 더 잡아준다. 두 장치 중 하나만 있으면 되는 게 아니라 이중 안전망으로 유지한다.
- **추가 설계 필요 (미확정)** — 이 팝업을 계기로 이지원천 `Employee` 마스터와 거래처
  (`Client`) 정보를 실제로 어떻게 갱신할지: 팝업에서 바로 인라인 등록 폼을 띄울지, 아니면
  "사원정보 등록/변경" 화면으로 이동만 시키고 등록은 사용자가 별도로 진행할지, 등록 완료
  여부를 다시 이 항목·§4-1의 "위하고 사원등록 완료" 체크와 어떻게 연동할지는 아직 결정되지
  않았다.
