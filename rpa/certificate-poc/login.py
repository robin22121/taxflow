"""Step 2 — 홈택스 아이디 로그인 자동화 (thin wrapper).

hometax_login.login() 을 호출해 로그인만 수행하고 결과를 캡처한다.
발급 흐름은 issue.py 참조.

실행: uv run python login.py
"""

from __future__ import annotations

from pathlib import Path

from playwright.sync_api import Page, sync_playwright

from hometax_login import login, prompt_credentials

OUT = Path(__file__).parent / "out"
OUT.mkdir(exist_ok=True)


def capture(page: Page, tag: str) -> None:
    try:
        page.screenshot(path=str(OUT / f"login_{tag}.png"), full_page=True)
        (OUT / f"login_{tag}.html").write_text(page.content(), encoding="utf-8")
        print(f"[+] captured login_{tag}.png / .html")
    except Exception as exc:
        print(f"[!] capture {tag} failed: {exc.__class__.__name__}")


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
        page = context.new_page()

        login(page, creds)
        capture(page, "final")

        print()
        print("=" * 60)
        print("[+] 로그인 완료. 화면 확인 후 Enter 로 종료.")
        print("=" * 60)
        input()

        context.close()
        browser.close()


if __name__ == "__main__":
    main()
