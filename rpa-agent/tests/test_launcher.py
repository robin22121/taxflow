from __future__ import annotations

import pytest

from easyone_agent import launcher
from easyone_agent.hometax import HometaxLoginFailed
from easyone_agent.wehago import LoginFailed


class FakeUploader:
    def __init__(self, calls: list[str], login_error: Exception | None = None) -> None:
        self.calls = calls
        self.login_error = login_error

    def __enter__(self):
        self.calls.append("uploader_enter")
        return self

    def __exit__(self, *exc):
        self.calls.append("uploader_exit")

    def ensure_logged_in(self) -> None:
        self.calls.append("wehago_login")
        if self.login_error:
            raise self.login_error


class FakeHometax:
    def __init__(self, calls: list[str], login_error: Exception | None = None) -> None:
        self.calls = calls
        self.login_error = login_error

    def open(self) -> None:
        self.calls.append("hometax_open")

    def ensure_logged_in(self) -> None:
        self.calls.append("hometax_login")
        if self.login_error:
            raise self.login_error


def _start(calls, uploader_error=None, hometax_error=None, reason="update_available"):
    return launcher.start(
        ensure_chrome=lambda: calls.append("chrome"),
        open_uploader=lambda: FakeUploader(calls, uploader_error),
        make_hometax=lambda uploader: FakeHometax(calls, hometax_error),
        run_agent=lambda uploader: (calls.append("run"), reason)[1],
    )


def test_start_runs_steps_in_order_and_returns_run_reason():
    calls: list[str] = []
    assert _start(calls) == "update_available"
    assert calls == [
        "chrome", "uploader_enter", "wehago_login", "hometax_open", "hometax_login", "run", "uploader_exit",
    ]


@pytest.mark.parametrize(
    "kwargs, last_call",
    [
        ({"uploader_error": LoginFailed("위하고")}, "wehago_login"),
        ({"hometax_error": HometaxLoginFailed("홈택스")}, "hometax_login"),
    ],
)
def test_login_failure_stops_before_run(kwargs, last_call):
    calls: list[str] = []
    assert _start(calls, **kwargs) == launcher.LOGIN_FAILED
    assert "run" not in calls
    assert calls[-2] == last_call and calls[-1] == "uploader_exit"
