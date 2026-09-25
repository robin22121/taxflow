"""사이트별 사람 속도 — plan/16-wehago-rpa.md §8-4.

위하고는 사설 업체라 느리고 신중하게, 홈택스·위택스는 다른 업체들도 스크래핑·자동화를
흔히 하므로 신속하게 돈다 (2026-09-25 사용자 결정).
"""

from __future__ import annotations

import random
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

Site = Literal["wehago", "hometax", "wetax"]


@dataclass(frozen=True)
class Pace:
    think_sec: tuple[float, float]  # 화면 단계 사이 대기
    gap_sec: tuple[float, float]  # 같은 사이트 작업과 작업 사이
    key_delay_ms: tuple[int, int]  # 한 글자 입력 간격


PACE: dict[Site, Pace] = {
    "wehago": Pace(think_sec=(0.5, 2.0), gap_sec=(5.0, 15.0), key_delay_ms=(50, 150)),
    "hometax": Pace(think_sec=(0.5, 1.0), gap_sec=(3.0, 7.0), key_delay_ms=(30, 80)),
    "wetax": Pace(think_sec=(0.5, 1.0), gap_sec=(3.0, 7.0), key_delay_ms=(30, 80)),
}


def think(site: Site, sleep: Callable[[float], None] = time.sleep) -> None:
    sleep(random.uniform(*PACE[site].think_sec))


def job_gap_sec(site: Site) -> float:
    return random.uniform(*PACE[site].gap_sec)


def key_delay_ms(site: Site) -> int:
    return random.randint(*PACE[site].key_delay_ms)
