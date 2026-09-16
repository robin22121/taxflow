from __future__ import annotations

import logging

from easyone_agent.logmask import SecretMaskingFilter, mask_text


def test_mask_text_hyphen_rrn():
    assert mask_text("주민번호 900101-1234567 확인") == "주민번호 900101-******* 확인"


def test_mask_text_plain_rrn():
    assert mask_text("입력 9001011234567 저장") == "입력 900101******* 저장"


def test_mask_text_rrn_at_boundaries():
    # 앞에 다른 숫자가 붙어 있으면 주민번호로 보지 않는다 (사업자번호 등 오탐 방지)
    assert mask_text("금액 39001011234567원") == "금액 39001011234567원"


def test_mask_text_business_number_kept():
    # 사업자번호(3-2-5)는 감사·대조에 필요하므로 남긴다
    assert mask_text("사업자 123-45-67890") == "사업자 123-45-67890"


def test_mask_text_extra_secret_replaced():
    assert mask_text("PW=Secret123 실패", extra_secrets=("Secret123",)) == "PW=*** 실패"


def test_mask_text_ignores_short_secret():
    # 3자 이하 자격증명은 흔한 부분문자열이라 무시 (오탐 방지)
    assert mask_text("PW=ab 실패", extra_secrets=("ab",)) == "PW=ab 실패"


def test_mask_text_empty_returns_empty():
    assert mask_text("") == ""


def test_secret_masking_filter_applies_to_record():
    filt = SecretMaskingFilter(lambda: ("Secret123",))
    record = logging.LogRecord(
        name="test", level=logging.INFO, pathname="", lineno=0,
        msg="로그인 실패 PW=%s 주민번호 %s", args=("Secret123", "900101-1234567"),
        exc_info=None,
    )
    assert filt.filter(record) is True
    assert record.msg == "로그인 실패 PW=%s 주민번호 %s"
    assert record.args == ("***", "900101-*******")


def test_secret_masking_filter_masks_msg_string():
    filt = SecretMaskingFilter(lambda: ("Secret123",))
    record = logging.LogRecord(
        name="test", level=logging.INFO, pathname="", lineno=0,
        msg="Secret123 저장됨", args=(), exc_info=None,
    )
    filt.filter(record)
    assert record.msg == "*** 저장됨"
