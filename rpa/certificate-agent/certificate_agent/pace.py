"""홈택스 사람 속도 — plan/16-wehago-rpa.md §8-4.

홈택스는 다른 업체들도 스크래핑·자동화를 흔히 하므로 신속하게 돈다 (2026-09-25 사용자 결정).
위하고 에이전트 `rpa-agent/easyone_agent/pace.py` 의 "hometax" 값과 같게 유지한다.
"""

from __future__ import annotations

import random
import time

THINK_SEC = (0.5, 1.0)  # 화면 단계 사이 대기
GAP_SEC = (3.0, 7.0)  # 작업과 작업 사이 (최대 7초)
KEY_DELAY_MS = (30, 80)  # 한 글자 입력 간격


def think() -> None:
    time.sleep(random.uniform(*THINK_SEC))


def job_gap() -> None:
    time.sleep(random.uniform(*GAP_SEC))


def key_delay_ms() -> int:
    return random.randint(*KEY_DELAY_MS)
