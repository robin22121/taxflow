"""자동 업데이트 확인 — 노트북의 git 작업 트리가 origin보다 뒤처졌는지만 본다.

실제 git pull·uv sync는 이 모듈이 하지 않는다. 돌고 있는 파이썬 프로세스가 자기
소스를 git pull하면 이미 임포트된 모듈과 디스크 상태가 어긋나기 때문이다. 대신
새 버전이 있으면 `runner.run_forever`가 "update_available"로 깨끗이 종료하고,
그 바깥의 `scripts/run-agent.ps1`가 종료 코드를 보고 git pull·uv sync·재실행을 맡는다
(크레덴셜은 Windows 자격 증명 관리자에만 있으므로 이 과정에 전혀 관여하지 않는다).
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

AGENT_DIR = Path(__file__).resolve().parents[1]


def update_available(repo_dir: Path = AGENT_DIR, timeout_sec: float = 15.0) -> bool:
    """origin에 현재 브랜치보다 새 커밋이 있으면 True.

    네트워크가 끊겼거나 git 명령이 실패해도 예외를 올리지 않고 False를 돌려준다 —
    업데이트 확인 실패가 작업 처리 루프를 멈추게 하면 안 된다.
    """
    try:
        branch = _git(repo_dir, "rev-parse", "--abbrev-ref", "HEAD", timeout_sec=timeout_sec)
        subprocess.run(
            ["git", "fetch", "--quiet", "origin", branch],
            cwd=repo_dir,
            timeout=timeout_sec,
            check=True,
            capture_output=True,
            text=True,
        )
        local = _git(repo_dir, "rev-parse", "HEAD", timeout_sec=timeout_sec)
        remote = _git(repo_dir, "rev-parse", f"origin/{branch}", timeout_sec=timeout_sec)
        return local != remote
    except Exception:
        logger.warning("업데이트 확인 실패 — 네트워크 또는 git 상태 문제로 보고 현재 버전으로 계속합니다", exc_info=True)
        return False


def _git(repo_dir: Path, *args: str, timeout_sec: float) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo_dir,
        timeout=timeout_sec,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()
