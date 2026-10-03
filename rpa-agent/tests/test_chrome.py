from __future__ import annotations

from pathlib import Path

import pytest

from easyone_agent import chrome
from easyone_agent.hometax import ChromeLaunchFailed


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def monotonic(self) -> float:
        return self.now

    def sleep(self, sec: float) -> None:
        self.now += sec


def test_ensure_chrome_does_nothing_when_port_already_open(monkeypatch, tmp_path: Path):
    launched = []
    monkeypatch.setattr(chrome, "cdp_port_open", lambda url: True)
    monkeypatch.setattr(chrome, "launch_chrome", lambda *a: launched.append(a))
    assert chrome.ensure_chrome("http://127.0.0.1:9222", tmp_path) is False
    assert launched == []


def test_ensure_chrome_launches_and_waits_for_port(monkeypatch, tmp_path: Path):
    clock = Clock()
    launched = []
    # 처음 두 번은 닫혀 있고(실행 전 확인 + 대기 1회), 그 뒤 열린다.
    answers = iter([False, False, True])
    monkeypatch.setattr(chrome, "cdp_port_open", lambda url: next(answers))
    monkeypatch.setattr(chrome, "launch_chrome", lambda *a: launched.append(a))
    opened = chrome.ensure_chrome(
        "http://127.0.0.1:9222", tmp_path, sleep=clock.sleep, monotonic=clock.monotonic
    )
    assert opened is True
    assert launched == [("http://127.0.0.1:9222", tmp_path)]


def test_ensure_chrome_raises_when_port_never_opens(monkeypatch, tmp_path: Path):
    clock = Clock()
    monkeypatch.setattr(chrome, "cdp_port_open", lambda url: False)
    monkeypatch.setattr(chrome, "launch_chrome", lambda *a: None)
    with pytest.raises(ChromeLaunchFailed):
        chrome.ensure_chrome(
            "http://127.0.0.1:9222", tmp_path, timeout_sec=3, sleep=clock.sleep, monotonic=clock.monotonic
        )


def test_cdp_port_open_is_false_for_closed_port():
    # 포트 1은 보통 아무도 듣지 않는다 — 연결 거절은 예외 없이 False.
    assert chrome.cdp_port_open("http://127.0.0.1:1") is False
