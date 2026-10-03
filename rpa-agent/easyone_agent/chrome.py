"""CDP 크롬 보장 — 이미 떠 있으면 그대로 쓰고, 없으면 전용 프로필로 띄운다.

맥(이미 로그인해 둔 크롬)과 윈도우 노트북(아무것도 없는 상태)을 같은 흐름으로 다루기 위한
것이다. 크롬을 띄우는 방법 자체(`launch_chrome`)는 `TaxAgentLogin`과 공유한다.
"""

from __future__ import annotations

import socket
import time
from pathlib import Path
from urllib.parse import urlsplit

from easyone_agent.hometax import CHROME_LAUNCH_TIMEOUT_SEC, ChromeLaunchFailed, launch_chrome


def cdp_port_open(cdp_url: str) -> bool:
    """CDP 디버깅 포트가 열려 있는지 — TCP 연결만 본다 (크롬에 붙지 않는다)."""
    parts = urlsplit(cdp_url)
    try:
        with socket.create_connection((parts.hostname or "127.0.0.1", parts.port or 9222), timeout=1):
            return True
    except OSError:
        return False


def ensure_chrome(
    cdp_url: str,
    profile_dir: Path,
    timeout_sec: float = CHROME_LAUNCH_TIMEOUT_SEC,
    sleep=time.sleep,
    monotonic=time.monotonic,
) -> bool:
    """CDP 크롬이 없으면 띄우고 포트가 열릴 때까지 기다린다. 새로 띄웠으면 True.

    이미 열려 있으면 아무것도 하지 않는다 — 그 크롬의 프로필·로그인 세션을 그대로 쓴다.
    """
    if cdp_port_open(cdp_url):
        return False
    launch_chrome(cdp_url, profile_dir)
    deadline = monotonic() + timeout_sec
    while monotonic() < deadline:
        if cdp_port_open(cdp_url):
            return True
        sleep(0.5)
    raise ChromeLaunchFailed(f"새로 띄운 크롬({cdp_url})의 디버깅 포트가 열리지 않았습니다")
