"""사용법:
    python -m easyone_agent setup   # 에이전트 토큰·위하고 ID/PW를 Windows 자격 증명 관리자에 저장
    python -m easyone_agent run     # 작업 대기·처리 루프 시작
    python -m easyone_agent login-test  # 작업 한 건을 받아 위하고 로그인만 해 보고 끝낸다
"""

from __future__ import annotations

import argparse
import getpass
import logging
import sys

from easyone_agent.api import EasyoneApi
from easyone_agent.config import (
    SECRET_AGENT_TOKEN,
    SECRET_WEHAGO_ID,
    SECRET_WEHAGO_PASSWORD,
    AgentConfig,
    get_secret,
    load_config,
    set_secret,
)
from easyone_agent.runner import run_forever, run_login_test
from easyone_agent.wehago import WehagoUploader


def _setup() -> None:
    set_secret(SECRET_AGENT_TOKEN, getpass.getpass("이지원천 에이전트 토큰: ").strip())
    set_secret(SECRET_WEHAGO_ID, input("위하고 아이디: ").strip())
    set_secret(SECRET_WEHAGO_PASSWORD, getpass.getpass("위하고 비밀번호: "))
    print("Windows 자격 증명 관리자에 저장했습니다.")


def _uploader(config: AgentConfig) -> WehagoUploader:
    return WehagoUploader(
        get_secret(SECRET_WEHAGO_ID),
        get_secret(SECRET_WEHAGO_PASSWORD),
        config.chrome_profile_dir,
    )


def _run() -> int:
    config = load_config()
    api = EasyoneApi(config.api_base_url, get_secret(SECRET_AGENT_TOKEN))
    with _uploader(config) as uploader:
        run_forever(api, uploader, config.workdir, config.poll_interval_sec)
    return 1  # run_forever는 로그인 실패로 멈출 때만 돌아온다


def _login_test() -> int:
    config = load_config()
    api = EasyoneApi(config.api_base_url, get_secret(SECRET_AGENT_TOKEN))
    logging.getLogger(__name__).info("위하고 전송 요청을 기다립니다 (로그인 테스트 — 업로드 안 함)")
    with _uploader(config) as uploader:
        ok = run_login_test(api, uploader, config.poll_interval_sec)
    print("위하고 로그인 성공" if ok else "위하고 로그인 실패 — 위 로그를 확인하세요")
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="easyone_agent")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("setup", help="토큰·위하고 ID/PW 저장")
    sub.add_parser("run", help="작업 처리 시작")
    sub.add_parser("login-test", help="작업 한 건으로 위하고 로그인만 확인")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s [%(name)s] %(message)s"
    )
    if args.command == "setup":
        _setup()
        return 0
    if args.command == "login-test":
        return _login_test()
    return _run()


if __name__ == "__main__":
    sys.exit(main())
