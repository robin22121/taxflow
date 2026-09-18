"""Step 1 — 홈택스 로그인·발급 흐름 자동 관찰 스크립트.

브라우저를 열고 사용자가 직접 로그인·발급까지 조작한다.
스크립트는 백그라운드에서 URL 이동·새 탭·팝업·다운로드·다이얼로그를 자동 기록한다.
종료 시 out/session_log.md · out/last_page.html · out/*.png 을 저장한다.

실행: uv run python explore.py
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from playwright.sync_api import (
    BrowserContext,
    Dialog,
    Download,
    Frame,
    Page,
    sync_playwright,
)

OUT = Path(__file__).parent / "out"
OUT.mkdir(exist_ok=True)
DOWNLOADS = OUT / "downloads"
DOWNLOADS.mkdir(exist_ok=True)

log_entries: list[str] = []
tab_ids: dict[Page, int] = {}
capture_counts: dict[int, int] = {}


def log(msg: str) -> None:
    ts = dt.datetime.now().strftime("%H:%M:%S")
    entry = f"[{ts}] {msg}"
    print(entry)
    log_entries.append(entry)


def capture(page: Page, tab_id: int, tag: str) -> None:
    """HTML dump + 스크린샷. HTML 이 셀렉터 추출에 중요하므로 먼저 받는다."""
    if page.is_closed():
        log(f"TAB#{tab_id} CAPTURE {tag} skipped (closed)")
        return
    try:
        html_path = OUT / f"tab{tab_id}_{tag}.html"
        html_path.write_text(page.content(), encoding="utf-8")
        log(f"TAB#{tab_id} HTML {tag}: {html_path.name}")
    except Exception as exc:
        log(f"TAB#{tab_id} HTML {tag} failed: {exc.__class__.__name__}")
    try:
        png = OUT / f"tab{tab_id}_{tag}.png"
        page.screenshot(path=str(png), timeout=15000)
        log(f"TAB#{tab_id} CAPTURE {tag}: {png.name}")
    except Exception as exc:
        log(f"TAB#{tab_id} CAPTURE {tag} failed: {exc.__class__.__name__}")


def register_page(page: Page, tab_id: int) -> None:
    tab_ids[page] = tab_id
    capture_counts[tab_id] = 0
    log(f"TAB#{tab_id} OPENED: {page.url or '(blank)'}")

    def on_nav(frame: Frame) -> None:
        if frame == page.main_frame:
            log(f"TAB#{tab_id} NAV: {frame.url}")
            # 각 탭의 첫 실체 URL 로드 시 자동 캡처 (about:blank 제외)
            if capture_counts[tab_id] == 0 and not frame.url.startswith("about:"):
                capture_counts[tab_id] = 1
                try:
                    page.wait_for_load_state("domcontentloaded", timeout=3000)
                except Exception:
                    pass
                capture(page, tab_id, "initial")

    def on_popup(popup: Page) -> None:
        new_id = len(tab_ids) + 1
        register_page(popup, new_id)

    def on_download(download: Download) -> None:
        target = DOWNLOADS / f"tab{tab_id}_{download.suggested_filename}"
        try:
            download.save_as(str(target))
            log(f"TAB#{tab_id} DOWNLOAD: {download.suggested_filename} → {target.name}")
        except Exception as exc:
            log(f"TAB#{tab_id} DOWNLOAD (save failed: {exc}): {download.suggested_filename} url={download.url}")

    def on_dialog(dialog: Dialog) -> None:
        msg = dialog.message.replace("\n", " ")[:200]
        log(f"TAB#{tab_id} DIALOG type={dialog.type} message={msg!r}")
        try:
            dialog.dismiss()
        except Exception:
            pass

    def on_close() -> None:
        log(f"TAB#{tab_id} CLOSED")

    page.on("framenavigated", on_nav)
    page.on("popup", on_popup)
    page.on("download", on_download)
    page.on("dialog", on_dialog)
    page.on("close", on_close)


def on_context_page(context: BrowserContext, page: Page) -> None:
    if page in tab_ids:
        return
    new_id = len(tab_ids) + 1
    register_page(page, new_id)


def dump_last_screens(context: BrowserContext) -> None:
    for page in list(context.pages):
        tab_id = tab_ids.get(page, 0)
        capture(page, tab_id, "last")


def main() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=100)
        context = browser.new_context(
            accept_downloads=True,
            locale="ko-KR",
            timezone_id="Asia/Seoul",
            viewport={"width": 1440, "height": 900},
        )
        context.on("page", lambda page: on_context_page(context, page))

        page = context.new_page()
        register_page(page, 1)

        page.goto("https://www.hometax.go.kr/", wait_until="domcontentloaded")

        print()
        print("=" * 60)
        print("브라우저에서 직접 로그인·발급 흐름을 진행하세요.")
        print()
        print("  1. 로그인 (아이디 · 비번 · 생년월일 추가인증)")
        print("  2. 국세증명·사업자등록·세금관련 신청/신고")
        print("     → 즉시발급증명 → 사업자등록증명")
        print("  3. [신청하기] → [발급하기] → [출력하기]")
        print("  4. PDF 다운 여부·인쇄 대화상자 여부 확인")
        print()
        print("스크립트가 URL 이동·팝업·다운로드·다이얼로그를 자동 기록합니다.")
        print("완료되면 이 터미널에서 Enter → 마지막 화면들을 캡처하고 종료합니다.")
        print("=" * 60)
        print()

        try:
            input()
        except KeyboardInterrupt:
            log("KEYBOARD INTERRUPT")

        dump_last_screens(context)

        session_log = OUT / "session_log.md"
        header = [
            "# Session Log",
            f"start: (실행 시각)",
            f"end: {dt.datetime.now().isoformat(timespec='seconds')}",
            "",
            "## Events",
            "",
        ]
        session_log.write_text("\n".join(header + log_entries), encoding="utf-8")
        print(f"\n[+] Session log → {session_log}")
        print(f"[+] Screenshots · HTML → {OUT}")
        print(f"[+] Downloads → {DOWNLOADS}")

        context.close()
        browser.close()


if __name__ == "__main__":
    main()
