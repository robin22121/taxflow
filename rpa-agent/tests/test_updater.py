from __future__ import annotations

import subprocess
from pathlib import Path

from easyone_agent.updater import update_available


class _FakeCompleted:
    def __init__(self, stdout: str = "") -> None:
        self.stdout = stdout


def test_update_available_true_when_origin_ahead(tmp_path: Path, monkeypatch):
    calls: list[list[str]] = []

    def fake_run(cmd: list[str], **kwargs):
        calls.append(cmd)
        if "--abbrev-ref" in cmd:
            return _FakeCompleted("main\n")
        if cmd[-1] == "HEAD":
            return _FakeCompleted("aaa111\n")
        if cmd[-1] == "origin/main":
            return _FakeCompleted("bbb222\n")
        return _FakeCompleted("")

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert update_available(tmp_path) is True
    assert ["git", "fetch", "--quiet", "origin", "main"] in calls


def test_update_available_false_when_up_to_date(tmp_path: Path, monkeypatch):
    def fake_run(cmd: list[str], **kwargs):
        if cmd[-1] == "HEAD" and "--abbrev-ref" not in cmd:
            return _FakeCompleted("aaa111\n")
        if cmd[-1] == "origin/main":
            return _FakeCompleted("aaa111\n")
        if "--abbrev-ref" in cmd:
            return _FakeCompleted("main\n")
        return _FakeCompleted("")

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert update_available(tmp_path) is False


def test_update_available_false_on_network_error(tmp_path: Path, monkeypatch):
    def fake_run(cmd: list[str], **kwargs):
        raise subprocess.TimeoutExpired(cmd, 15.0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert update_available(tmp_path) is False
