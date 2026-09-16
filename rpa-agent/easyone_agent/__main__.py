"""사용법:
    python -m easyone_agent setup   # 토큰·위하고·홈택스·위택스 자격증명을 Windows 자격 증명 관리자에 저장
    python -m easyone_agent run     # 작업 대기·처리 루프 시작
    python -m easyone_agent login-test  # 작업 한 건을 받아 위하고 로그인만 해 보고 끝낸다

노트북 크롬은 먼저 `scripts/start-chrome.ps1` 로 CDP 포트를 열어 실행해 두어야 한다.
"""

from __future__ import annotations

import argparse
import getpass
import logging
import sys

from easyone_agent.api import EasyoneApi
from easyone_agent.config import (
    SECRET_AGENT_TOKEN,
    SECRET_HOMETAX_CERT_PASSWORD,
    SECRET_HOMETAX_ID,
    SECRET_HOMETAX_PASSWORD,
    SECRET_HOMETAX_TAX_AGENT_ID,
    SECRET_HOMETAX_TAX_AGENT_PASSWORD,
    SECRET_WEHAGO_ID,
    SECRET_WEHAGO_PASSWORD,
    SECRET_WETAX_ID,
    SECRET_WETAX_PASSWORD,
    AgentConfig,
    get_secret,
    load_config,
    set_secret,
)
from easyone_agent.runner import run_forever, run_login_test
from easyone_agent.wehago import WehagoUploader


def _prompt_secret(name: str, secret_key: str, hidden: bool) -> None:
    prompt = f"{name} ({secret_key}) 을(를) 저장/갱신하시겠습니까? [y/N]: "
    if input(prompt).strip().lower() != "y":
        return
    value = getpass.getpass(f"{name}: ") if hidden else input(f"{name}: ").strip()
    if value:
        set_secret(secret_key, value)


def _setup() -> None:
    set_secret(SECRET_AGENT_TOKEN, getpass.getpass("이지원천 에이전트 토큰: ").strip())
    set_secret(SECRET_WEHAGO_ID, input("위하고 아이디: ").strip())
    set_secret(SECRET_WEHAGO_PASSWORD, getpass.getpass("위하고 비밀번호: "))

    print("\n홈택스·위택스 자격증명 (건너뛰려면 Enter — 미보유 시 나중에 갱신 가능)")
    _prompt_secret("홈택스 아이디", SECRET_HOMETAX_ID, hidden=False)
    _prompt_secret("홈택스 비밀번호", SECRET_HOMETAX_PASSWORD, hidden=True)
    _prompt_secret("홈택스 세무대리 관리번호", SECRET_HOMETAX_TAX_AGENT_ID, hidden=False)
    _prompt_secret("홈택스 세무대리 비밀번호", SECRET_HOMETAX_TAX_AGENT_PASSWORD, hidden=True)
    _prompt_secret("홈택스 공동인증서 비밀번호", SECRET_HOMETAX_CERT_PASSWORD, hidden=True)
    _prompt_secret("위택스 아이디", SECRET_WETAX_ID, hidden=False)
    _prompt_secret("위택스 비밀번호", SECRET_WETAX_PASSWORD, hidden=True)

    print("\nWindows 자격 증명 관리자에 저장했습니다.")


def _uploader(config: AgentConfig) -> WehagoUploader:
    return WehagoUploader(
        user_id=get_secret(SECRET_WEHAGO_ID),
        password=get_secret(SECRET_WEHAGO_PASSWORD),
        cdp_url=config.cdp_url,
        screenshot_dir=config.screenshot_dir,
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
    sub.add_parser("setup", help="토큰·위하고/홈택스/위택스 자격증명 저장")
    sub.add_parser("run", help="작업 처리 시작")
    sub.add_parser("login-test", help="작업 한 건으로 위하고 로그인만 확인")
    args = parser.parse_args(argv)

    from easyone_agent.logmask import configure_logging

    configure_logging(logging.INFO)
    if args.command == "setup":
        _setup()
        return 0
    if args.command == "login-test":
        return _login_test()
    return _run()


if __name__ == "__main__":
    sys.exit(main())
