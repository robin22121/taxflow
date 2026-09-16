"""로그·문자열 마스킹 — 비밀번호·주민번호·저장된 자격증명 값이 로그·화면에 새지 않게 한다.

`plan/16-wehago-rpa.md` §8-2 조건 (로그·스크린샷에 비밀번호·주민번호 기록 금지).
자격증명은 setup 시 keyring에 저장되며 여기서 실시간으로 읽어 로그 문자열에서 지운다.

로그 스트림에만 적용된다. 예외 메시지·서버 회신에도 같은 규칙을 통과시키려면
`mask_text()`를 명시적으로 호출한다.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterable

# 주민번호: 6자리 - 7자리, 또는 붙여 쓴 13자리. 앞 8자리(생년월일·성별)까지 남기고 나머지 마스킹.
_RRN_HYPHEN = re.compile(r"(\d{6})-(\d{7})")
_RRN_PLAIN = re.compile(r"(?<!\d)(\d{6})(\d{7})(?!\d)")

# 사업자번호(3-2-5)는 로그에 남겨도 된다 (수임처 대조·감사에 필요). 마스킹 안 함.


def mask_text(text: str, extra_secrets: Iterable[str] = ()) -> str:
    """로그·회신 문자열에서 비밀정보를 지운다.

    extra_secrets: keyring에서 실시간으로 읽은 비밀번호·아이디. 있으면 리터럴로 치환.
    """
    if not text:
        return text
    for secret in extra_secrets:
        if secret and len(secret) >= 4 and secret in text:
            text = text.replace(secret, "***")
    text = _RRN_HYPHEN.sub(r"\1-*******", text)
    text = _RRN_PLAIN.sub(r"\1*******", text)
    return text


class SecretMaskingFilter(logging.Filter):
    """로그 메시지·args에서 비밀정보를 지우는 필터. 루트 핸들러에 붙인다."""

    def __init__(self, secret_provider) -> None:
        super().__init__()
        self._secret_provider = secret_provider

    def filter(self, record: logging.LogRecord) -> bool:
        secrets = tuple(self._secret_provider())
        # args가 있으면 로거가 % 포매팅으로 msg에 끼워 넣는다 — args도 훑는다.
        if record.args:
            record.args = tuple(
                mask_text(a, secrets) if isinstance(a, str) else a for a in record.args
            )
        if isinstance(record.msg, str):
            record.msg = mask_text(record.msg, secrets)
        return True


def _keyring_secrets() -> tuple[str, ...]:
    """저장된 자격증명(비밀번호 계열)만 골라서 반환. 아이디는 감사에 남겨도 되므로 제외."""
    from easyone_agent.config import (
        SECRET_HOMETAX_CERT_PASSWORD,
        SECRET_HOMETAX_PASSWORD,
        SECRET_HOMETAX_TAX_AGENT_PASSWORD,
        SECRET_WEHAGO_PASSWORD,
        SECRET_WETAX_PASSWORD,
        get_secret_optional,
    )

    keys = (
        SECRET_WEHAGO_PASSWORD,
        SECRET_HOMETAX_PASSWORD,
        SECRET_HOMETAX_TAX_AGENT_PASSWORD,
        SECRET_HOMETAX_CERT_PASSWORD,
        SECRET_WETAX_PASSWORD,
    )
    return tuple(v for v in (get_secret_optional(k) for k in keys) if v)


def configure_logging(level: int = logging.INFO) -> None:
    """루트 로거에 포맷·마스킹 필터를 세팅한다. `__main__`에서 한 번만 호출."""
    logging.basicConfig(
        level=level, format="%(asctime)s %(levelname)s [%(name)s] %(message)s"
    )
    root = logging.getLogger()
    # 기존 필터 중복 부착 방지
    if not any(isinstance(f, SecretMaskingFilter) for f in root.filters):
        root.addFilter(SecretMaskingFilter(_keyring_secrets))
    for handler in root.handlers:
        if not any(isinstance(f, SecretMaskingFilter) for f in handler.filters):
            handler.addFilter(SecretMaskingFilter(_keyring_secrets))
