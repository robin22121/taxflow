"""에이전트 설정 — 비밀값(토큰·위하고 ID/PW)은 Windows 자격 증명 관리자(keyring)에만 둔다."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

KEYRING_SERVICE = "easyonechon-rpa"
SECRET_AGENT_TOKEN = "agent_token"
SECRET_WEHAGO_ID = "wehago_id"
SECRET_WEHAGO_PASSWORD = "wehago_password"


@dataclass(frozen=True, slots=True)
class AgentConfig:
    api_base_url: str
    poll_interval_sec: float
    workdir: Path  # 받은 급여파일을 업로드 동안만 두는 곳 — 처리 후 바로 지운다
    chrome_profile_dir: Path  # 직원 크롬과 분리된 에이전트 전용 프로필


def load_config() -> AgentConfig:
    home = Path(os.environ.get("EASYONE_AGENT_HOME", Path.home() / ".easyone-agent"))
    return AgentConfig(
        api_base_url=os.environ.get("EASYONE_API_BASE_URL", "https://api.easyonechon.co.kr"),
        poll_interval_sec=float(os.environ.get("EASYONE_POLL_INTERVAL_SEC", "5")),
        workdir=home / "work",
        chrome_profile_dir=home / "chrome-profile",
    )


def get_secret(name: str) -> str:
    import keyring

    value = keyring.get_password(KEYRING_SERVICE, name)
    if not value:
        raise RuntimeError(
            f"자격 증명 '{name}'이 없습니다. 먼저 `python -m easyone_agent setup`을 실행하세요."
        )
    return value


def set_secret(name: str, value: str) -> None:
    import keyring

    keyring.set_password(KEYRING_SERVICE, name, value)
