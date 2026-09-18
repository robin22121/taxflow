"""Step 3 — 사업자등록증명 [출력] → PDF 뷰어 자동 캡처.

로그인 자동 → 카탈로그·결과 페이지 각각 자동 이동·캡처(셀렉터 확보) →
결과 화면의 첫 이력 [출력] 버튼을 스크립트가 직접 클릭 → clipreport 팝업의
initial 스크린샷·HTML 저장.

발급 신청(신청→발급)은 다음 iteration. 지금은 이미 발급된 이력의 [출력]만.

실행: uv run python issue.py
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

from hometax_login import login, prompt_credentials

OUT = Path(__file__).parent / "out"
OUT.mkdir(exist_ok=True)

CATALOG_URL = (
    "https://hometax.go.kr/websquare/websquare.html"
    "?w2xPath=/ui/pp/index_pp.xml&menuCd=UTEABGA0A021"
)
RESULT_URL = (
    "https://hometax.go.kr/websquare/websquare.html"
    "?w2xPath=/ui/pp/index_pp.xml&menuCd=UTECAAB0A001"
)

# 결과 조회 화면의 첫 이력 [출력] 버튼 (issue_tab1_last.html 분석)
FIRST_OUTPUT_BTN = "#mf_txppWframe_gen_cvaInf_0_btn_cvaDcumGranMthdNm"


def capture(page: Page, tag: str) -> None:
    """HTML 먼저 (셀렉터 추출용), 스크린샷은 실패해도 진행.

    WebSquare 화면은 full_page 스크린샷이 자주 타임아웃되므로 viewport 만 찍는다.
    """
    if page.is_closed():
        print(f"[!] capture {tag} skipped (page closed)")
        return
    try:
        (OUT / f"issue_{tag}.html").write_text(page.content(), encoding="utf-8")
        print(f"[+] html  issue_{tag}.html")
    except Exception as exc:
        print(f"[!] html {tag} failed: {exc.__class__.__name__}: {exc}")
    try:
        page.screenshot(path=str(OUT / f"issue_{tag}.png"), timeout=15000)
        print(f"[+] png   issue_{tag}.png")
    except Exception as exc:
        print(f"[!] png {tag} failed: {exc.__class__.__name__}: {exc}")


class Console:
    """stdin 을 백그라운드로 읽는다 — Enter=캡처 요청, q=종료.

    sync Playwright 는 API 호출 중에만 이벤트를 처리하므로 메인은 tick 을 돌려야 한다.
    select.select(sys.stdin) 은 Windows 에서 소켓만 받아 OSError 가 나므로 스레드로 대체.
    """

    def __init__(self) -> None:
        self.done = threading.Event()
        self.captures = 0
        threading.Thread(target=self._reader, daemon=True).start()

    def _reader(self) -> None:
        while True:
            try:
                line = input()
            except Exception:
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


def watch_navigation(page: Page) -> None:
    """menuCd 가 바뀔 때마다 그 화면을 자동 덤프 (셀렉터 수집용)."""
    seen: set[str] = set()
    counter = [0]

    def on_nav(frame) -> None:
        if frame != page.main_frame:
            return
        url = frame.url
        if url in seen or url.startswith("about:"):
            return
        seen.add(url)
        counter[0] += 1
        menu = url.split("menuCd=")[-1] if "menuCd=" in url else "nomenu"
        print(f"[*] 화면 전환 감지 → {menu}")
        page.wait_for_timeout(2500)
        capture(page, f"nav{counter[0]:02d}_{menu}")

    page.on("framenavigated", on_nav)


def main() -> None:
    creds = prompt_credentials()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=100)
        context = browser.new_context(
            accept_downloads=True,
            locale="ko-KR",
            timezone_id="Asia/Seoul",
            viewport={"width": 1440, "height": 900},
        )

        popup_captured: list[str] = []

        def on_popup(popup: Page) -> None:
            print(f"[+] popup opened: {popup.url or '(blank)'}")
            try:
                popup.wait_for_load_state("domcontentloaded", timeout=15000)
                # SVG 렌더링·리포트 데이터 로드 대기
                time.sleep(4.0)
                png = OUT / "issue_popup_initial.png"
                popup.screenshot(path=str(png), full_page=True, timeout=10000)
                (OUT / "issue_popup_initial.html").write_text(
                    popup.content(), encoding="utf-8"
                )
                popup_captured.append(str(png))
                print(f"[+] popup screenshot → {png.name}")
                # 잠시 열어둔 채 관찰
                time.sleep(2.0)
            except Exception as exc:
                print(f"[!] popup capture failed: {exc.__class__.__name__}: {exc}")

        context.on("page", on_popup)

        page = context.new_page()
        watch_navigation(page)
        login(page, creds)
        time.sleep(2.0)
        capture(page, "01_login_done")

        # 홈 → 카탈로그 이동 (WebSquare 세션 유지 위해 goto 대신 메뉴 클릭)
        print("[*] 홈 → '즉시발급 국세증명' 바로가기 클릭")
        try:
            page.locator("#taKndSvcAllA3").click(timeout=10000)
            time.sleep(3.0)
            capture(page, "02_catalog")
            print(f"[+] 카탈로그 도달. url={page.url}")
        except Exception as exc:
            print(f"[!] 카탈로그 이동 실패: {exc.__class__.__name__}: {exc}")

        print()
        print("=" * 60)
        print("[관찰] 브라우저에서 한 단계씩 진행하고, 매 단계마다 이 창에서 Enter.")
        print()
        print("  1. 카탈로그에서 사업자등록증명 클릭   → Enter")
        print("  2. [신청하기] 클릭                    → Enter")
        print("  3. [발급하기] 클릭                    → Enter")
        print("  4. [출력하기] 클릭 (팝업 뜸)          → Enter")
        print()
        print("WebSquare 는 하위 화면을 URL 변경 없이 로드하므로 자동 감지가 안 된다.")
        print("Enter 를 칠 때마다 그 시점 화면의 HTML·PNG 를 저장한다.")
        print("끝나면 q + Enter 로 종료 (팝업은 닫지 마세요).")
        print("=" * 60)

        # sync Playwright 콜백은 API 호출 시점에만 처리됨.
        # input() 으로 막으면 팝업·네비 이벤트가 전부 지연되므로 tick 루프를 돌린다.
        console = Console()
        step = 0
        while not console.done.is_set():
            try:
                page.wait_for_timeout(500)
            except Exception:
                break
            if console.take_request():
                step += 1
                print(f"[*] 수동 캡처 {step}")
                capture(page, f"step{step:02d}")

        capture(page, "05_final_main")

        print()
        print(f"[+] 팝업 캡처 성공: {len(popup_captured)}건")
        for f in popup_captured:
            print(f"    {f}")

        context.close()
        browser.close()


if __name__ == "__main__":
    main()
