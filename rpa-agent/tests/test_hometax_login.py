from __future__ import annotations

import pytest

from easyone_agent.hometax import HUMAN_LOGIN_WAIT_SEC, HometaxLoginFailed, HometaxSession
from easyone_agent.wehago import WEHAGO_URL, _split_tabs


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def monotonic(self) -> float:
        return self.now

    def sleep(self, sec: float) -> None:
        self.now += sec


class FakeText:
    def __init__(self, page: "FakePage") -> None:
        self.page = page

    def count(self) -> int:
        return 1 if self.page.logged_in() else 0


class FakeButton:
    def __init__(self, page: "FakePage") -> None:
        self.page = page

    @property
    def first(self) -> "FakeButton":
        return self

    def is_visible(self) -> bool:
        return self.page.button_visible

    def wait_for(self, state: str, timeout: int) -> None:
        if not self.page.button_visible:
            raise TimeoutError

    def click(self) -> None:
        self.page.clicks += 1


class FakePage:
    def __init__(self, clock: Clock, url: str = "https://www.hometax.go.kr/", logged_in_at: float | None = None):
        self.clock = clock
        self.url = url
        self.logged_in_at = logged_in_at  # 이 시각부터 로그인 상태 (None이면 끝내 로그인 안 됨)
        self.button_visible = True
        self.clicks = 0
        self.closed = False

    def logged_in(self) -> bool:
        if self.logged_in_at is None:
            return False
        if self.logged_in_at == 0:
            return True  # 처음부터 로그인된 세션
        # 그 외에는 [로그인]을 누른 뒤 지정 시각이 지나야 로그인된다 (사람이 인증서 창을 끝낸 것처럼)
        return self.clicks > 0 and self.clock.now >= self.logged_in_at

    def get_by_text(self, text: str, exact: bool = False) -> FakeText:
        return FakeText(self)

    def locator(self, selector: str) -> FakeButton:
        return FakeButton(self)

    def goto(self, url: str, wait_until: str = "load") -> None:
        pass


class FakeContext:
    def __init__(self, pages: list[FakePage]) -> None:
        self.pages = pages

    def new_page(self) -> FakePage:
        page = FakePage(Clock(), url="about:blank")
        self.pages.append(page)
        return page


def _session(page: FakePage) -> HometaxSession:
    session = HometaxSession(
        FakeContext([page]), user_id="", password="", tax_agent_id=None,
        tax_agent_password=None, cert_password=None, screenshot_dir=None,
    )
    session._page = page
    return session


def test_already_logged_in_skips_login_popup():
    clock = Clock()
    page = FakePage(clock, logged_in_at=0)
    _session(page).ensure_logged_in(sleep=clock.sleep, monotonic=clock.monotonic)
    assert page.clicks == 0


def test_opens_cert_popup_then_waits_until_logged_in():
    clock = Clock()
    page = FakePage(clock, logged_in_at=20)
    _session(page).ensure_logged_in(sleep=clock.sleep, monotonic=clock.monotonic)
    assert page.clicks == 1


def test_raises_when_login_not_completed_in_time():
    clock = Clock()
    page = FakePage(clock, logged_in_at=None)
    with pytest.raises(HometaxLoginFailed):
        _session(page).ensure_logged_in(sleep=clock.sleep, monotonic=clock.monotonic)
    assert page.clicks == 1
    assert clock.now >= HUMAN_LOGIN_WAIT_SEC


def test_open_reuses_existing_hometax_tab_and_ignores_security_window():
    clock = Clock()
    security = FakePage(clock, url="https://sesw.hometax.go.kr/xyz")
    main = FakePage(clock, url="https://hometax.go.kr/websquare/websquare.html")
    context = FakeContext([security, main])
    session = HometaxSession(
        context, user_id="", password="", tax_agent_id=None,
        tax_agent_password=None, cert_password=None, screenshot_dir=None,
    )
    session.open()
    assert session._page is main
    assert len(context.pages) == 2  # 새 탭을 만들지 않았다


def test_split_tabs_never_closes_tax_site_tabs():
    clock = Clock()
    hometax = FakePage(clock, url="https://hometax.go.kr/x")
    wetax = FakePage(clock, url="https://www.wetax.go.kr/y")
    blank = FakePage(clock, url="about:blank")
    wehago = FakePage(clock, url=f"{WEHAGO_URL}/#/main")
    stale = FakePage(clock, url="https://smarta.wehago.com/old")
    main_page, keep, to_close = _split_tabs([hometax, blank, wehago, wetax, stale])
    assert main_page is wehago and keep is wehago
    assert to_close == [blank, stale]


def test_split_tabs_asks_for_new_page_when_only_tax_tabs_exist():
    clock = Clock()
    hometax = FakePage(clock, url="https://hometax.go.kr/x")
    main_page, keep, to_close = _split_tabs([hometax])
    assert main_page is None and keep is None and to_close == []
