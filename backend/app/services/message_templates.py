"""발송 템플릿 레지스트리 (plan/13-messaging-activation.md §3.6·§5.4).

- SMS 본문: 사무소가 발송 화면에서 수정 가능. ``{변수}`` 를 서버가 치환한다.
- 알림톡 본문: 카카오 심사 승인 문구와 **글자 하나까지 일치**해야 하므로 수정 불가.
  세목과 무관한 범용 템플릿 1종(T4 ``FILING_NOTICE``)만 두고 ``#{변수}`` 로 세목을 바꾼다.
"""

from __future__ import annotations

from dataclasses import dataclass

TAX_TYPE_LABELS: dict[str, str] = {
    "WITHHOLDING": "원천세",
    "VAT": "부가가치세",
    "INCOME": "종합소득세",
    "CORPORATE": "법인세",
}

# 알림톡 T4 — 심사 제출 문구. 변경 시 사무소별 재심사가 필요하다.
FILING_NOTICE_ALIMTALK_CODE = "FILING_NOTICE"
FILING_NOTICE_ALIMTALK_BODY = (
    "[#{사무소명}]\n"
    "\n"
    "안녕하세요, #{거래처명} 대표님.\n"
    "#{세목} 신고기간이 다가와 안내드립니다.\n"
    "\n"
    "· 신고·납부기한: #{신고기한}\n"
    "· 준비자료: #{준비자료}\n"
    "\n"
    "자료를 준비해 보내주시면 신고를 진행하겠습니다.\n"
    "\n"
    "문의는 #{사무소명}으로 연락 주세요."
)


@dataclass(frozen=True, slots=True)
class FilingNoticeTemplate:
    code: str
    tax_type: str
    prep_items: str  # 알림톡 #{준비자료}
    sms_body: str

    @property
    def label(self) -> str:
        return f"{TAX_TYPE_LABELS[self.tax_type]} 신고안내"


def _sms(prep: str) -> str:
    return (
        "[{사무소명}]\n"
        "\n"
        "안녕하세요, {거래처명} {대표자}대표님.\n"
        "{세목} 신고기간이 다가와 안내드립니다.\n"
        "\n"
        "· 신고·납부기한: {신고기한}\n"
        f"· 준비자료: {prep}\n"
        "\n"
        "자료를 준비해 보내주시면 신고를 진행하겠습니다.\n"
        "감사합니다."
    )


_PREP = {
    "WITHHOLDING": "해당 월 급여·일용·사업소득 지급내역",
    "VAT": "카드·현금영수증 등 세금계산서 외 매출·매입 증빙",
    "INCOME": "사업 경비 증빙, 금융·연금·기타소득 자료, 부양가족 변동사항",
    "CORPORATE": "결산 자료(재고·미지급비용 등), 가지급금·가수금 내역",
}

FILING_NOTICE_TEMPLATES: dict[str, FilingNoticeTemplate] = {
    tax_type: FilingNoticeTemplate(
        code=f"FILING_NOTICE_{tax_type}",
        tax_type=tax_type,
        prep_items=prep,
        sms_body=_sms(prep),
    )
    for tax_type, prep in _PREP.items()
}


def fill(template: str, values: dict[str, str], *, alimtalk: bool = False) -> str:
    """``{키}`` (SMS) 또는 ``#{키}`` (알림톡) 치환. 없는 값은 빈 문자열."""
    out = template
    for key, value in values.items():
        out = out.replace(f"#{{{key}}}" if alimtalk else f"{{{key}}}", value or "")
    return out
