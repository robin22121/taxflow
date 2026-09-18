"""Step 3 — 사업자등록증명 [출력] → PDF 뷰어 자동 캡처.

로그인 자동 → 카탈로그·결과 페이지 각각 자동 이동·캡처(셀렉터 확보) →
결과 화면의 첫 이력 [출력] 버튼을 스크립트가 직접 클릭 → clipreport 팝업의
initial 스크린샷·HTML 저장.

발급 신청(신청→발급)은 다음 iteration. 지금은 이미 발급된 이력의 [출력]만.

실행: uv run python issue.py
"""

from __future__ import annotations

import select
import sys
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
    try:
        page.screenshot(path=str(OUT / f"issue_{tag}.png"), full_page=True, timeout=5000)
        (OUT / f"issue_{tag}.html").write_text(page.content(), encoding="utf-8")
        print(f"[+] captured issue_{tag}.png / .html")
    except Exception as exc:
        print(f"[!] capture {tag} failed: {exc.__class__.__name__}: {exc}")


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
        print("[관찰] 브라우저에서 직접 다음을 진행:")
        print("  1. 카탈로그에서 사업자등록증명 클릭")
        print("  2. [신청하기] → [발급하기] → [출력하기]")
        print("  3. clipreport 팝업이 뜨면 그 상태 유지")
        print()
        print("팝업이 뜨면 스크립트가 자동 캡처합니다.")
        print("완료 후 Enter로 종료 (팝업 닫지 마세요).")
        print("=" * 60)

        # sync Playwright 콜백은 API 호출 시점에만 처리됨.
        # input() 대기 중엔 팝업 이벤트가 지연되므로 tick 루프 + stdin 감지.
        while True:
            try:
                page.wait_for_timeout(500)
            except Exception:
                break
            if select.select([sys.stdin], [], [], 0)[0]:
                sys.stdin.readline()
                break

        capture(page, "05_final_main")

        print()
        print(f"[+] 팝업 캡처 성공: {len(popup_captured)}건")
        for f in popup_captured:
            print(f"    {f}")

        context.close()
        browser.close()


if __name__ == "__main__":
    main()
