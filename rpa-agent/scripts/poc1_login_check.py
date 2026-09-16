"""PoC 1 — 노트북 크롬 CDP 연결 + 위하고·홈택스·위택스 자동 로그인·봇 감지 확인.

`plan/16-wehago-rpa.md` §9 진행 순서 표의 PoC 1 판정 기준:
  통과 → CDP 확정 / 실패 → 노트북 익스텐션

측정 대상 (각 사이트별):
  1. 로그인 페이지 도달 가능 여부
  2. `navigator.webdriver` 값 (자동화 감지 흔적)
  3. 자동화 표시 문자열("자동화 소프트웨어에 의해 제어") 유무
  4. 캡차·차단 문구 스캔
  5. 위하고만 실제 자동 로그인 시도 → 성공/실패 (홈택스는 공동인증서 필요·위택스는 셀렉터 실측 전이라 페이지 도달까지만)
  6. 세션 유지 시간 실측 (선택: `--session-wait` 초 뒤 로그인 상태 재확인)

실행 순서:
  1. scripts/start-chrome.ps1 로 크롬을 CDP 포트로 띄운다
  2. 크롬에서 홈택스 공동인증서·세무대리 관리번호 로그인은 사람이 미리 완료 (선택)
  3. `python scripts/poc1_login_check.py [--session-wait 300]`

리포트는 `~/.easyone-agent/screenshots/poc1-<timestamp>.json`에 저장한다.
스크린샷은 실패 케이스만 (비밀번호·아이디 입력칸 마스킹).
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

# scripts/ 는 패키지가 아니라 스탠드얼론 실행용이라 rpa-agent 루트를 sys.path에 넣는다
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from easyone_agent.config import (
    SECRET_HOMETAX_ID,
    SECRET_WEHAGO_ID,
    SECRET_WEHAGO_PASSWORD,
    SECRET_WETAX_ID,
    get_secret,
    get_secret_optional,
    load_config,
)
from easyone_agent.logmask import configure_logging
from easyone_agent.wehago import (
    CdpConnectFailed,
    LoginFailed,
    WehagoUploader,
)

logger = logging.getLogger("poc1")

HOMETAX_LOGIN_URL = "https://hometax.go.kr/websquare/websquare.html?w2xPath=/ui/pp/index.xml"
WETAX_LOGIN_URL = "https://www.wetax.go.kr/main.do"

BOT_HINTS = (
    "자동화 소프트웨어",
    "자동입력 방지",
    "보안문자",
    "캡차",
    "captcha",
    "접근이 차단",
    "비정상적인 접근",
)


@dataclass
class SiteReport:
    name: str
    reached: bool = False
    navigator_webdriver: object = None
    bot_hints_found: list[str] = field(default_factory=list)
    login_attempted: bool = False
    login_ok: bool | None = None
    error: str | None = None


@dataclass
class Poc1Report:
    started_at: str
    cdp_url: str
    sites: list[SiteReport]
    session_wait_sec: int
    session_recheck: dict = field(default_factory=dict)


def _scan_bot_hints(text: str) -> list[str]:
    lowered = text.lower()
    return [h for h in BOT_HINTS if h.lower() in lowered]


def _probe_page(page, url: str, name: str, screenshot_dir: Path) -> SiteReport:
    report = SiteReport(name=name)
    try:
        page.goto(url, timeout=30_000, wait_until="domcontentloaded")
        report.reached = True
        report.navigator_webdriver = page.evaluate("() => navigator.webdriver")
        # 일부 사이트는 초기 로딩 지연 — 잠깐 기다린 뒤 스캔
        page.wait_for_timeout(2_000)
        body_text = page.locator("body").inner_text(timeout=5_000)
        report.bot_hints_found = _scan_bot_hints(body_text)
        if report.bot_hints_found:
            screenshot_dir.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(screenshot_dir / f"poc1-{name}-bot-hint.png"))
    except Exception as e:
        report.error = f"{type(e).__name__}: {e}"
    return report


def _try_wehago_login(uploader: WehagoUploader, report: SiteReport) -> None:
    report.login_attempted = True
    try:
        uploader.ensure_logged_in()
    except LoginFailed as e:
        report.login_ok = False
        report.error = f"LoginFailed: {e}"
        return
    except Exception as e:
        report.login_ok = False
        report.error = f"{type(e).__name__}: {e}"
        return
    report.login_ok = True


def _session_recheck(page, url: str) -> dict:
    """세션 유지 시간 실측용 재확인 — url 로 갔을 때 로그인 페이지로 튀는지 확인."""
    try:
        page.goto(url, timeout=30_000, wait_until="domcontentloaded")
        return {"final_url": page.url, "reached": True}
    except Exception as e:
        return {"reached": False, "error": f"{type(e).__name__}: {e}"}


def run(session_wait_sec: int) -> int:
    config = load_config()
    logger.info("PoC 1 시작 — CDP %s", config.cdp_url)

    wehago_id = get_secret(SECRET_WEHAGO_ID)
    wehago_pw = get_secret(SECRET_WEHAGO_PASSWORD)

    report = Poc1Report(
        started_at=datetime.now().isoformat(timespec="seconds"),
        cdp_url=config.cdp_url,
        sites=[],
        session_wait_sec=session_wait_sec,
    )

    try:
        with WehagoUploader(
            user_id=wehago_id,
            password=wehago_pw,
            cdp_url=config.cdp_url,
            screenshot_dir=config.screenshot_dir,
        ) as uploader:
            page = uploader._page  # 스탠드얼론 스크립트라 내부 페이지 재사용

            # 위하고
            wehago_report = _probe_page(
                page, "https://www.wehagot.com/#/login", "wehago", config.screenshot_dir
            )
            if wehago_report.reached and not wehago_report.bot_hints_found:
                _try_wehago_login(uploader, wehago_report)
            report.sites.append(wehago_report)

            # 홈택스
            hometax_report = _probe_page(page, HOMETAX_LOGIN_URL, "hometax", config.screenshot_dir)
            if get_secret_optional(SECRET_HOMETAX_ID):
                hometax_report.login_attempted = False  # 공동인증서 필요, 로그인 시도 안 함
            report.sites.append(hometax_report)

            # 위택스
            wetax_report = _probe_page(page, WETAX_LOGIN_URL, "wetax", config.screenshot_dir)
            if get_secret_optional(SECRET_WETAX_ID):
                wetax_report.login_attempted = False  # 세무대리인 로그인 셀렉터 실측 전
            report.sites.append(wetax_report)

            # 세션 유지 실측 (선택)
            if session_wait_sec > 0:
                logger.info("세션 유지 실측: %d초 대기 후 재확인", session_wait_sec)
                time.sleep(session_wait_sec)
                report.session_recheck = {
                    "wehago": _session_recheck(page, "https://www.wehagot.com/#/main"),
                }

    except CdpConnectFailed as e:
        logger.error("CDP 연결 실패: %s", e)
        report.sites.append(SiteReport(name="cdp", error=str(e)))
        _save_report(report, config.screenshot_dir)
        return 2

    _save_report(report, config.screenshot_dir)
    _print_summary(report)
    return 0 if _passed(report) else 1


def _passed(report: Poc1Report) -> bool:
    """판정: 3개 사이트 모두 reached=True + 봇 감지 없음 + navigator.webdriver 미노출 + 위하고 로그인 성공."""
    for site in report.sites:
        if site.name == "cdp":
            return False
        if not site.reached:
            return False
        if site.bot_hints_found:
            return False
        if site.navigator_webdriver:
            return False
    wehago = next((s for s in report.sites if s.name == "wehago"), None)
    return wehago is not None and wehago.login_ok is True


def _save_report(report: Poc1Report, screenshot_dir: Path) -> None:
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    ts = report.started_at.replace(":", "").replace("-", "")
    path = screenshot_dir / f"poc1-{ts}.json"
    path.write_text(
        json.dumps(asdict(report), indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    logger.info("리포트 저장: %s", path)


def _print_summary(report: Poc1Report) -> None:
    print()
    print(f"PoC 1 결과 — 판정: {'통과 (CDP 확정)' if _passed(report) else '실패 (익스텐션 폴백 검토)'}")
    print(f"CDP: {report.cdp_url}")
    for site in report.sites:
        line = (
            f"  [{site.name}] reached={site.reached} webdriver={site.navigator_webdriver} "
            f"bot_hints={site.bot_hints_found} login={site.login_ok}"
        )
        if site.error:
            line += f" error={site.error}"
        print(line)
    if report.session_recheck:
        print(f"세션 재확인 ({report.session_wait_sec}s 후): {report.session_recheck}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="poc1_login_check", description=__doc__)
    parser.add_argument(
        "--session-wait",
        type=int,
        default=0,
        help="위하고 로그인 후 N초 대기하고 세션이 유지되는지 재확인 (0=생략)",
    )
    args = parser.parse_args(argv)
    configure_logging(logging.INFO)
    return run(args.session_wait)


if __name__ == "__main__":
    sys.exit(main())
