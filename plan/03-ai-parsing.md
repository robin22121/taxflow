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

LLM 송신 전 RRN/주민번호 스크러빙은 별도 게이트(G3)로 처리 — `10-privacy-security.md` 참고. AI 프로바이더는 Gemini Flash 2.5 메인, Claude Sonnet 폴백 (research.md §4.4).

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
