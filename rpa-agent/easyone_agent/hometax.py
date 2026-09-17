"""홈택스 로그인 스캐폴드 — 페이지 도달·아이디 입력까지.

`plan/16-wehago-rpa.md` §4-4·§9-2. 공동인증서 팝업(DreamSecurity)은 브라우저 밖 다이얼로그라
Playwright로 처리할 수 없다. 이 모듈은 브라우저 안에서 진행 가능한 부분(아이디/PW 입력 →
"공동인증서로 로그인" 트리거)까지만 담당하고, 인증서 선택창은 사람이 미리 로그인해 세션을
남겨두는 흐름이 전제다 (docs/rpa-agent-install.md §8).

파일변환신고 화면·K Upload는 실측 후 구현 (§9-2 촬영 목록 6번).
"""

from __future__ import annotations

from pathlib import Path

HOMETAX_LOGIN_URL = (
    "https://hometax.go.kr/websquare/websquare.html?w2xPath=/ui/pp/index.xml"
)
HOMETAX_MAIN_URL = "https://hometax.go.kr"
LOGIN_FORM_WAIT_MS = 15_000
LOGIN_WAIT_MS = 60_000


class HometaxError(Exception):
    """홈택스 작업 실패 — 해당 거래처만 FAILED로 회신."""


class HometaxLoginFailed(HometaxError):
    """홈택스 로그인 실패 — 계정 잠금 방지 위해 에이전트 정지."""


class HometaxCertRequired(HometaxError):
    """공동인증서 팝업이 필요하다 — 사람이 미리 세션을 남겨두었어야 한다."""


class HometaxSession:
    """CDP로 붙은 크롬 컨텍스트에서 홈택스 페이지를 조작한다.

    사용:
        with WehagoUploader(...) as w:  # start-chrome로 띄운 크롬에 붙음
            hometax = HometaxSession(w._context, user_id=..., password=...)
            hometax.ensure_logged_in()
    """

    def __init__(
        self,
        context,  # playwright BrowserContext (WehagoUploader가 이미 CDP로 붙어 있음)
        user_id: str,
        password: str,
        tax_agent_id: str | None,
        tax_agent_password: str | None,
        cert_password: str | None,
        screenshot_dir: Path,
    ) -> None:
        self._context = context
        self._user_id = user_id
        self._password = password
        self._tax_agent_id = tax_agent_id
        self._tax_agent_password = tax_agent_password
        self._cert_password = cert_password
        self._screenshot_dir = screenshot_dir
        self._page = None

    def open(self) -> None:
        """홈택스 새 탭을 연다. 위하고와 분리된 탭에서 조작한다."""
        page = self._context.new_page()
        page.goto(HOMETAX_LOGIN_URL, wait_until="domcontentloaded")
        self._page = page

    def ensure_logged_in(self) -> None:
        """세션이 살아 있는지 확인. 없으면 아이디/PW 입력까지만 진행한다.

        인증서 팝업 이후(세무대리 관리번호)는 사람이 최초 1회 완료한 세션을 재활용한다.
        인증서 세션이 만료된 경우 HometaxCertRequired를 던져 자동 재로그인을 시도하지 않는다.
        """
        if self._page is None:
            self.open()
        assert self._page is not None
        page = self._page

        # 로그인 상태 판정 — 실측 후 정확한 셀렉터 확정 (§9-2 촬영 목록 4)
        # 임시: '로그아웃' 버튼이 보이면 로그인됨으로 간주
        try:
            if page.get_by_text("로그아웃", exact=False).count() > 0:
                return
        except Exception:
            pass

        # 아이디/PW 입력 필드는 홈택스 WebSquare 프레임 안에 있을 수 있다 (실측 필요)
        raise NotImplementedError(
            "홈택스 로그인 자동화 셀렉터는 실측 후 구현 — "
            "지금은 사람이 크롬에서 직접 로그인해 세션을 남겨두어야 한다 "
            "(docs/rpa-agent-install.md §8)."
        )

    def save_failure_screenshot(self, name: str) -> None:
        if self._page is None:
            return
        self._screenshot_dir.mkdir(parents=True, exist_ok=True)
        self._page.screenshot(path=str(self._screenshot_dir / f"hometax-{name}.png"))

    def close(self) -> None:
        if self._page is not None:
            self._page.close()
            self._page = None
