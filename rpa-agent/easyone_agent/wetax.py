"""위택스 세무대리인 로그인 스캐폴드 — 페이지 도달·아이디 입력까지.

`plan/16-wehago-rpa.md` §4-4·§9-2. 위택스는 아이디/PW로만 로그인 가능 (인증서 불필요).
세션 유지 시간이 30분이라 로그인 후 짧은 시간 내에 파일 제출까지 마쳐야 한다 — 실측 시
`page.on("dialog")` 로 브라우저 기본 대화상자를 잡는 흐름 확인 필요.

특별징수 회계파일신고 셀렉터·검증 흐름은 실측 후 구현 (§9-2 촬영 목록 5).
"""

from __future__ import annotations

from pathlib import Path

WETAX_MAIN_URL = "https://www.wetax.go.kr/main.do"
WETAX_TAX_AGENT_LOGIN_URL = "https://www.wetax.go.kr/login/taxAgent.do"  # 실측 후 확정
LOGIN_FORM_WAIT_MS = 15_000
LOGIN_WAIT_MS = 60_000
SESSION_TIMEOUT_MIN = 30  # 위택스 세션 만료 (실측 §9-2)


class WetaxError(Exception):
    """위택스 작업 실패."""


class WetaxLoginFailed(WetaxError):
    """위택스 로그인 실패 — 계정 잠금 방지 위해 에이전트 정지."""


class WetaxSession:
    def __init__(
        self,
        context,  # playwright BrowserContext (CDP 공유)
        user_id: str,
        password: str,
        screenshot_dir: Path,
    ) -> None:
        self._context = context
        self._user_id = user_id
        self._password = password
        self._screenshot_dir = screenshot_dir
        self._page = None

    def open(self) -> None:
        page = self._context.new_page()
        # 위택스는 신고 확인이 브라우저 기본 대화상자로 뜬다 — dialog 핸들러 미리 등록 (실측 후 강화)
        page.on("dialog", lambda d: d.accept())
        page.goto(WETAX_MAIN_URL, wait_until="domcontentloaded")
        self._page = page

    def ensure_logged_in(self) -> None:
        """세무대리인 로그인. 실측 전이라 여기서 멈춘다."""
        if self._page is None:
            self.open()
        assert self._page is not None
        page = self._page

        try:
            if page.get_by_text("로그아웃", exact=False).count() > 0:
                return
        except Exception:
            pass

        raise NotImplementedError(
            "위택스 세무대리인 로그인 셀렉터는 실측 후 구현 — "
            "지금은 사람이 크롬에서 직접 로그인해 세션을 남겨두어야 한다 "
            "(docs/rpa-agent-install.md §8)."
        )

    def save_failure_screenshot(self, name: str) -> None:
        if self._page is None:
            return
        self._screenshot_dir.mkdir(parents=True, exist_ok=True)
        self._page.screenshot(path=str(self._screenshot_dir / f"wetax-{name}.png"))

    def close(self) -> None:
        if self._page is not None:
            self._page.close()
            self._page = None
