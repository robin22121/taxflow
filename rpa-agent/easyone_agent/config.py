"""에이전트 설정 — 비밀값(토큰·위하고/홈택스/위택스 ID/PW)은 Windows 자격 증명 관리자(keyring)에만 둔다."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

KEYRING_SERVICE = "easyonechon-rpa"
SECRET_AGENT_TOKEN = "agent_token"
SECRET_WEHAGO_ID = "wehago_id"
SECRET_WEHAGO_PASSWORD = "wehago_password"
SECRET_HOMETAX_ID = "hometax_id"
SECRET_HOMETAX_PASSWORD = "hometax_password"
SECRET_HOMETAX_TAX_AGENT_ID = "hometax_tax_agent_id"
SECRET_HOMETAX_TAX_AGENT_PASSWORD = "hometax_tax_agent_password"
SECRET_WETAX_ID = "wetax_id"
SECRET_WETAX_PASSWORD = "wetax_password"
SECRET_HOMETAX_CERT_PASSWORD = "hometax_cert_password"  # 홈택스 로그인용 세무법인 공동인증서 비밀번호


@dataclass(frozen=True, slots=True)
class AgentConfig:
    api_base_url: str
    poll_interval_sec: float
    workdir: Path  # 받은 급여파일을 업로드 동안만 두는 곳 — 처리 후 바로 지운다
    screenshot_dir: Path  # 로그인 실패·오류 스크린샷 (입력칸 마스킹 후 저장)
    chrome_profile_dir: Path  # start-chrome 스크립트가 CDP 크롬을 띄울 때 쓰는 프로필
    cdp_url: str  # 노트북 크롬의 원격 디버깅 URL — start-chrome로 미리 띄워 둔 인스턴스에 붙는다


def load_config() -> AgentConfig:
    home = Path(os.environ.get("EASYONE_AGENT_HOME", Path.home() / ".easyone-agent"))
    return AgentConfig(
        api_base_url=os.environ.get("EASYONE_API_BASE_URL", "https://api.easyonechon.co.kr"),
        poll_interval_sec=float(os.environ.get("EASYONE_POLL_INTERVAL_SEC", "5")),
        workdir=home / "work",
        screenshot_dir=home / "screenshots",
        chrome_profile_dir=home / "chrome-profile",
        cdp_url=os.environ.get("EASYONE_CDP_URL", "http://127.0.0.1:9222"),
    )


def get_secret(name: str) -> str:
    import keyring

    value = keyring.get_password(KEYRING_SERVICE, name)
    if not value:
        raise RuntimeError(
            f"자격 증명 '{name}'이 없습니다. 먼저 `python -m easyone_agent setup`을 실행하세요."
        )
    return value


def get_secret_optional(name: str) -> str | None:
    """설정 안 된 자격 증명은 None을 돌려준다."""
    import keyring

    return keyring.get_password(KEYRING_SERVICE, name)


def set_secret(name: str, value: str) -> None:
    import keyring

    keyring.set_password(KEYRING_SERVICE, name, value)
