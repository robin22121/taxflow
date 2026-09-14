"""위하고T 화면 조작 — Playwright로 에이전트 전용 크롬 프로필을 띄워 급여자료 엑셀을 올린다.

⚠️ 선택자(버튼·입력칸 위치)는 아직 비어 있다. 위하고 화면 실측 후 채운다
   (plan/16-wehago-rpa.md §7). 실측 전에는 각 단계가 NotImplementedError로 멈춰
   서버에 FAILED로 회신되므로 잘못된 업로드는 일어나지 않는다.
"""

from __future__ import annotations

from pathlib import Path

WEHAGO_URL = "https://www.wehago.com"


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
        raise NotImplementedError("위하고 로그인 화면 실측 후 구현")

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
