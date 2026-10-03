"""원커맨드 시작 — 크롬(CDP) → 위하고 로그인 → 홈택스 로그인 → 작업 대기.

`python -m easyone_agent start`가 쓴다. 맥에서 이미 로그인해 둔 크롬이면 각 단계가 입력 없이
통과하고, 윈도우 노트북처럼 아무것도 없으면 크롬 실행부터 차례로 진행한다. 로그인 실패는
재시도 없이 바로 멈춘다 — 계정 잠금을 막기 위해서다 (plan/16 §8-3).

외부 동작(크롬·로그인·작업 루프)은 인자로 받아 순서와 실패 처리만 이 모듈이 책임진다.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from easyone_agent.hometax import HometaxLoginFailed
from easyone_agent.wehago import LoginFailed

logger = logging.getLogger(__name__)

LOGIN_FAILED = "login_failed"


def start(
    *,
    ensure_chrome: Callable[[], Any],
    open_uploader: Callable[[], Any],
    make_hometax: Callable[[Any], Any],
    run_agent: Callable[[Any], str],
) -> str:
    """순서대로 실행하고 종료 사유를 돌려준다 (`run_agent`의 사유 또는 `LOGIN_FAILED`)."""
    logger.info("1/4 크롬(CDP) 확인")
    ensure_chrome()
    with open_uploader() as uploader:
        try:
            logger.info("2/4 위하고 로그인")
            uploader.ensure_logged_in()
            hometax = make_hometax(uploader)
            logger.info("3/4 홈택스 로그인")
            hometax.open()
            hometax.ensure_logged_in()
        except (LoginFailed, HometaxLoginFailed) as e:
            logger.error("로그인 실패로 시작하지 않습니다: %s", e)
            return LOGIN_FAILED
        logger.info("4/4 작업 대기 시작")
        return run_agent(uploader)
