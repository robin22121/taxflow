from __future__ import annotations

from pathlib import Path

import pytest

from easyone_agent.hometax import ChromeLaunchFailed, _find_chrome_executable


def test_find_chrome_executable_returns_existing_candidate(monkeypatch, tmp_path):
    fake_chrome = tmp_path / "chrome"
    fake_chrome.touch()
    monkeypatch.setattr(
        "easyone_agent.hometax._CHROME_PATH_CANDIDATES",
        {"Darwin": [str(fake_chrome)]},
    )
    monkeypatch.setattr("easyone_agent.hometax.platform.system", lambda: "Darwin")
    assert _find_chrome_executable() == str(fake_chrome)


def test_find_chrome_executable_raises_when_missing(monkeypatch, tmp_path):
    missing = tmp_path / "does-not-exist"
    monkeypatch.setattr(
        "easyone_agent.hometax._CHROME_PATH_CANDIDATES",
        {"Darwin": [str(missing)]},
    )
    monkeypatch.setattr("easyone_agent.hometax.platform.system", lambda: "Darwin")
    with pytest.raises(ChromeLaunchFailed):
        _find_chrome_executable()
