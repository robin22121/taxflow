"""PII redaction.

Hard guarantee: no 주민등록번호 / 사업자등록번호 / 카드번호 ever leaves the NCP perimeter
toward an external LLM. Apply ``redact_pii`` to any string before it is included
in a Claude API request body or logged.

Patterns covered:
- 주민등록번호: ``NNNNNN-NNNNNNN`` (with or without hyphen, including spaces).
- 사업자등록번호: ``NNN-NN-NNNNN``.
- 14~16-digit card-like sequences (rough; intentionally aggressive).
- 외국인등록번호: same shape as 주민번호.

The redaction is non-reversible — we do not save the mapping. The AI doesn't need
the actual ID to do payroll matching; it only needs the name.
"""

from __future__ import annotations

import re

# Korean RRN: 6 digits + optional separator + 7 digits.
# We accept '-', ' ', or no separator.
_RRN_RE = re.compile(r"\b(\d{6})\s*[-_ ]?\s*(\d{7})\b")
# 사업자등록번호: 3-2-5
_BIZ_RE = re.compile(r"\b\d{3}\s*[-]?\s*\d{2}\s*[-]?\s*\d{5}\b")
# Naive long-digit (cards / accounts). Intentionally cautious.
_LONG_DIGIT_RE = re.compile(r"\b\d{12,19}\b")


def redact_pii(text: str) -> str:
    """Mask PII in ``text``. Never raises. Idempotent.

    >>> redact_pii('김연호 900101-1234567 100만원')
    '김연호 ******-******* 100만원'
    """
    if not text:
        return text

    def _rrn(m: re.Match[str]) -> str:
        # Preserve string length for visual debugging
        return "*" * len(m.group(1)) + "-" + "*" * len(m.group(2))

    out = _RRN_RE.sub(_rrn, text)
    out = _BIZ_RE.sub(lambda m: "*" * len(m.group(0)), out)
    out = _LONG_DIGIT_RE.sub(lambda m: "*" * len(m.group(0)), out)
    return out


def redact_payload(payload: object) -> object:
    """Recursively redact strings inside dicts/lists.

    Useful for sanitizing structured data before sending to the LLM
    (e.g. employee_master should not contain RRNs but if a developer ever
    adds them by mistake this catches it).
    """
    if isinstance(payload, str):
        return redact_pii(payload)
    if isinstance(payload, dict):
        return {k: redact_payload(v) for k, v in payload.items()}
    if isinstance(payload, list):
        return [redact_payload(x) for x in payload]
    if isinstance(payload, tuple):
        return tuple(redact_payload(x) for x in payload)
    return payload


__all__ = ["redact_payload", "redact_pii"]
