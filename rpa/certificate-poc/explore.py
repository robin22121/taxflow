"""Step 1 — 홈택스 로그인·발급 흐름 자동 관찰 스크립트.

브라우저를 열고 사용자가 직접 로그인·발급까지 조작한다.
스크립트는 백그라운드에서 URL 이동·새 탭·팝업·다운로드·다이얼로그를 자동 기록한다.
종료 시 out/session_log.md · out/last_page.html · out/*.png 을 저장한다.

실행: uv run python explore.py
"""

from __future__ import annotations

import datetime as dt
import threading
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


class Console:
    """stdin 을 백그라운드로 읽는다 — Enter=캡처 요청, q=종료.

    sync Playwright 는 API 호출 중에만 이벤트를 처리한다. input() 으로 막으면
    팝업·네비 이벤트가 전부 밀려 타임스탬프가 뭉개지고 먼저 닫힌 팝업은 놓친다.
    """

    def __init__(self) -> None:
        self.done = threading.Event()
        self.captures = 0
        threading.Thread(target=self._reader, daemon=True).start()

    def _reader(self) -> None:
        while True:
            try:
                line = input()
            except Exception:  # noqa: BLE001
                break
            if line.strip().lower() == "q":
                break
            self.captures += 1
        self.done.set()

    def take_request(self) -> bool:
        if self.captures > 0:
            self.captures -= 1
            return True
        return False


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
        print("브라우저에서 한 단계씩 진행하고, 매 단계마다 이 창에서 Enter.")
        print("Enter 를 칠 때마다 그 시점 화면의 HTML·PNG 를 저장합니다.")
        print("끝나면 q + Enter 로 종료 (팝업·인증서 창은 닫지 마세요).")
        print("=" * 60)
        print()

        console = Console()
        step = 0
        while not console.done.is_set():
            try:
                page.wait_for_timeout(500)
            except Exception:  # noqa: BLE001
                break
            if console.take_request():
                step += 1
                log(f"MANUAL CAPTURE {step}")
                for pg in list(context.pages):
                    capture(pg, tab_ids.get(pg, 0), f"step{step:02d}")

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
