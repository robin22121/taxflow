"""위하고T 화면 조작 — Playwright로 에이전트 전용 크롬 프로필을 띄워 급여자료 엑셀을 올린다.

⚠️ 로그인만 로그인 화면 DOM 조사로 선택자를 채웠다(실계정 로그인 실측 전).
   수임처 검색·업로드는 화면 실측 전이라 NotImplementedError로 멈춰
   서버에 FAILED로 회신되므로 잘못된 업로드는 일어나지 않는다.
"""

from __future__ import annotations

from pathlib import Path

WEHAGO_URL = "https://www.wehagot.com"  # 위하고 T (세무회계사무소용)
LOGIN_WAIT_MS = 60_000  # QR 추가 인증이 뜨면 사람이 처리할 시간
LOGIN_FORM_WAIT_MS = 15_000

# 로그인 화면에 보이는 문구 → 실패 사유 (위하고 번들의 한국어 문구)
_LOGIN_FAILURE_HINTS = {
    "아이디 또는 비밀번호가 올바르지 않습니다": "아이디 또는 비밀번호가 올바르지 않음",
    "자동입력 방지": "자동입력 방지 문자(캡차) 요구",
    "QR코드": "QR 추가 인증 요구",
}


class WehagoError(Exception):
    """위하고 작업 실패 — 해당 작업만 FAILED로 회신하고 다음 작업으로 넘어간다."""


class LoginFailed(WehagoError):
    """로그인 실패 — 재시도하면 계정이 잠길 수 있어 에이전트 자체를 멈춘다."""


class CompanyMismatch(WehagoError):
    """사업자번호로 연 수임처가 요청한 거래처와 다르다 — 업로드하지 않는다."""


class WehagoUploader:
    def __init__(
        self, user_id: str, password: str, profile_dir: Path, headless: bool = False
    ) -> None:
        self._user_id = user_id
        self._password = password
        self._profile_dir = profile_dir
        self._headless = headless
        self._playwright = None
        self._context = None
        self._page = None

    def __enter__(self) -> WehagoUploader:
        from playwright.sync_api import sync_playwright

        self._playwright = sync_playwright().start()
        # 설치된 크롬을 쓰되 직원 프로필과 섞이지 않게 전용 프로필 폴더를 쓴다.
        self._context = self._playwright.chromium.launch_persistent_context(
            str(self._profile_dir), channel="chrome", headless=self._headless
        )
        pages = self._context.pages
        self._page = pages[0] if pages else self._context.new_page()
        return self

    def __exit__(self, *exc: object) -> None:
        if self._context:
            self._context.close()
        if self._playwright:
            self._playwright.stop()

    def ensure_logged_in(self) -> None:
        """로그인 상태가 아니면 ID/PW로 로그인한다. 실패하면 LoginFailed (재시도 금지)."""
        from playwright.sync_api import TimeoutError as PlaywrightTimeout

        page = self._page
        # 로그인 안 된 상태로 메인에 가면 위하고가 #/login 으로 보낸다.
        page.goto(f"{WEHAGO_URL}/#/main")
        id_input = page.locator("#inputId")
        try:
            id_input.wait_for(state="visible", timeout=LOGIN_FORM_WAIT_MS)
        except PlaywrightTimeout:
            if "#/login" not in page.url:
                return  # 전용 프로필에 세션이 남아 있다
            self._save_failure_screenshot()
            raise LoginFailed("로그인 화면이 열리지 않음") from None

        # React 입력칸이라 fill()로는 값이 반영되지 않을 수 있어 한 글자씩 친다.
        id_input.press_sequentially(self._user_id)
        page.locator("#inputPw").press_sequentially(self._password)
        page.locator(".login_form button.WSC_LUXButton").click()
        try:
            page.wait_for_url(lambda url: "#/login" not in url, timeout=LOGIN_WAIT_MS)
        except PlaywrightTimeout:
            self._save_failure_screenshot()
            raise LoginFailed(self._login_failure_reason()) from None

    def _login_failure_reason(self) -> str:
        visible_text = self._page.locator("body").inner_text()
        for hint, reason in _LOGIN_FAILURE_HINTS.items():
            if hint in visible_text:
                return reason
        return "로그인 화면에서 넘어가지 않음"

    def _save_failure_screenshot(self) -> None:
        # 원인 확인용으로 PC에만 남긴다 (서버로 보내지 않는다). 입력칸은 가린다.
        page = self._page
        page.screenshot(
            path=str(self._profile_dir.parent / "login-failed.png"),
            mask=[page.locator("#inputId"), page.locator("#inputPw")],
        )

    def open_company(self, business_number: str) -> tuple[str, str]:
        """수임처를 사업자번호로 검색해 연다. 검색 결과가 정확히 1건이 아니면 CompanyMismatch.

        Returns:
            화면에 표시된 (상호, 사업자번호) — 호출자가 요청값과 대조한다.
        """
        raise NotImplementedError("위하고 수임처 검색 화면 실측 후 구현")

    def upload_payroll(self, xlsx_path: Path, period: str) -> str:
        """급여자료입력 메뉴에서 귀속연월을 맞추고 엑셀을 올린다.

        Returns:
            화면의 업로드 결과 메시지. 오류 메시지가 뜨면 WehagoError.
        """
        raise NotImplementedError("위하고 급여자료입력 엑셀 업로드 화면 실측 후 구현")
