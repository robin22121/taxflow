"""위하고 수임처 대조 — 사업자번호와 상호가 모두 같아야 같은 회사로 본다."""

from __future__ import annotations

import re

_LEGAL_FORMS = ("주식회사", "유한회사", "합자회사", "합명회사", "(주)", "(유)", "(합)", "㈜")


def normalize_business_number(value: str) -> str:
    return re.sub(r"\D", "", value or "")


def normalize_company_name(value: str) -> str:
    """법인 형태 표기((주)·주식회사 등)와 공백만 걷어낸다. 그 외 글자는 그대로 비교한다."""
    name = value or ""
    for form in _LEGAL_FORMS:
        name = name.replace(form, "")
    return re.sub(r"\s+", "", name)


def company_matches(
    expected_name: str, expected_number: str, found_name: str, found_number: str
) -> bool:
    number = normalize_business_number(expected_number)
    name = normalize_company_name(expected_name)
    return (
        bool(number)
        and bool(name)
        and number == normalize_business_number(found_number)
        and name == normalize_company_name(found_name)
    )
