"""홈택스 로그인 스캐폴드 — 페이지 도달·아이디 입력까지.

`plan/16-wehago-rpa.md` §4-4·§9-2. 공동인증서 팝업(DreamSecurity)은 브라우저 밖 다이얼로그라
Playwright로 처리할 수 없다. 이 모듈은 브라우저 안에서 진행 가능한 부분(아이디/PW 입력 →
"공동인증서로 로그인" 트리거)까지만 담당하고, 인증서 선택창은 사람이 미리 로그인해 세션을
남겨두는 흐름이 전제다 (docs/rpa-agent-install.md §8).

파일변환신고 화면·K Upload는 실측 후 구현 (§9-2 촬영 목록 6번).

2026-09-28 실측 추가 (개발 중간 단계, `plan/16-wehago-rpa.md` §3-5 — 이 맥북에서 로그인된
홈택스 세션에 CDP로 붙어 서도(224-02-38407, 더미 수임처) 사업자번호로 실측):
- 일용ㆍ간이지급명세서 통합 작성 화면(`open_simplified_statement_screen` 이하) — 사업자번호
  조회까지 실제 동작 확인.
- 원천세 신고(원천징수이행상황신고서) [정기신고](직접작성) 화면은 진입(`open_wht_filing_screen`
  이하) 카드 클릭까지만 실측했다. 그 다음 화면(안내 팝업 닫기 이후)은 실제 정부 신고 화면으로
  더 들어가는 조작이라 이 세션에서는 진행하지 않았다 — 사람이 직접 이어서 실측해야 한다.
- 원천세 신고 [파일변환신고](위하고T 등에서 제작한 신고서 파일을 그대로 올리는 방식,
  `open_file_conversion_filing_screen`·`select_conversion_file` 이하) — 화면 진입, [파일선택]
  버튼이 여는 네이티브 파일 선택창을 Playwright `expect_file_chooser`로 가로채 파일 첨부까지
  실제 동작 확인(테스트용 샘플 파일로 검증, `tests/fixtures/wht_filing_sample_224-02-38407.csv`
  — 국세청 전산매체 제출요령의 정확한 레코드 포맷을 확인하지 못해 만든 임시 샘플이라 실제 파일
  형식과 다를 수 있다). **[파일검증하기]부터는 실제 정부 신고 화면을 더 진행시키는 조작이라
  자동화 환경 안전 정책상 진행하지 않았다** — 사람이 직접 눌러야 한다.

**이 모듈은 어떤 함수도 지급명세서·원천세 신고서의 "제출/신고" 버튼을 클릭하지 않는다.**
그 버튼들의 셀렉터는 참고용으로만 아래 `_DO_NOT_CLICK_SUBMIT_SELECTORS` 에 기록해 두고,
실제 제출은 사람이 화면에서 최종 확인 후 누른다 (신고서 홈택스 제출 전까지만 구현하라는
요청에 따른 경계).
"""

from __future__ import annotations

import platform
import subprocess
import time
from pathlib import Path
from urllib.parse import urlsplit

HOMETAX_LOGIN_URL = (
    "https://hometax.go.kr/websquare/websquare.html?w2xPath=/ui/pp/index.xml"
)
HOMETAX_MAIN_URL = "https://hometax.go.kr"
LOGIN_FORM_WAIT_MS = 15_000
LOGIN_WAIT_MS = 60_000
CHROME_LAUNCH_TIMEOUT_SEC = 15  # 새로 띄운 크롬이 CDP 포트를 열 때까지 기다리는 한도
HUMAN_LOGIN_WAIT_SEC = 300  # 공동인증서 창에서 사람이 로그인을 끝낼 때까지 기다리는 한도

# scripts/start-chrome.sh·.ps1과 같은 후보 경로 — 새로 창을 열 때도 같은 설치 크롬을 쓴다
_CHROME_PATH_CANDIDATES = {
    "Darwin": ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"],
    "Windows": [
        r"%ProgramFiles%\Google\Chrome\Application\chrome.exe",
        r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe",
        r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe",
    ],
}

# 2026-09-28 실측(hometax_login.py 아이디 로그인 경로)에서 확인된 버튼 — 로그인 페이지의
# 기본 탭(금융·공동 인증)을 그대로 둔 채(탭 전환 없이) 누르면 공동인증서 선택 팝업이 뜬다.
_CERT_LOGIN_BUTTON = "a.logingbtn[title='로그인']"

# 지급명세ㆍ자료ㆍ공익법인 > 일용·간이지급명세/사업장제공자 과세자료 제출명세(매월·반기)/
# 소득부인 > 직접작성 제출 (2026-09-28 실측, 메뉴 트리 코드는 세션 무관 고정값)
SIMPLIFIED_STATEMENT_MENU_CD = "4401100000"

# 세금신고 > 원천세 신고 > 일반신고 (2026-09-28 실측)
WHT_FILING_MENU_CD = "4106010000"

# 홈택스 메뉴는 `?menuCd=...` 직접 URL 이동이 먹히지 않는다 — 메인(index4)으로 튕긴다
# (2026-09-28 실측). 대신 헤더에 항상 숨어 있는 `#menuAtag_{메뉴코드}` 앵커를 JS로 클릭해야
# WebSquare 내부 라우팅(`tmIdx`/`tm2lIdx`/`tm3lIdx` 방식 URL)을 제대로 태운다.

# (지급)명세서 선택 드롭다운의 실제 옵션 문자열 — WebSquare가 value==text로 씀 (2026-09-28 실측)
class StatementKind:
    DAILY_WAGE = "일용근로소득 지급명세서"
    SIMPLIFIED_WAGE = "간이지급명세서(근로소득)"
    SIMPLIFIED_BUSINESS = "간이지급명세서(거주자의 사업소득)"  # 사용자 요청의 "사업"
    SIMPLIFIED_OTHER = "간이지급명세서(거주자의 기타소득)"  # 사용자 요청의 "기타"
    WORKPLACE_PROVIDER = "사업장 제공자 등의 과세자료 제출명세서"
    YEAR_END_BUSINESS = "간이지급명세서(연말정산 사업소득)"
    NONRESIDENT_BUSINESS = "간이지급명세서(비거주자의 사업소득)"


# 제출구분 라디오 순서 (mf_txppWframe_rtnClDetailCd_input_0/1/2, 2026-09-28 실측)
class FilingType:
    REGULAR = 0  # 정기신고
    AMENDED = 1  # 수정신고
    LATE = 2  # 기한후신고


# 참고용 — 이 파일의 어떤 메서드도 아래 버튼을 클릭하지 않는다 (§ 상단 경계 설명 참조)
_DO_NOT_CLICK_SUBMIT_SELECTORS = {
    "간이지급명세서 제출하기": "#mf_txppWframe_btnSbms",
    "간이지급명세서 제출전 미리보기": "#mf_txppWframe_btnSbms_20_01",
    # 원천세 신고서(정기신고 직접작성) 자체 제출 버튼은 안내 팝업 다음 화면부터라 아직 실측 못함.
    "파일변환신고 파일검증하기": "#mf_txppWframe_pf_UTERNAAZ0Z11_btn_cenSts",
    "파일변환신고 제출하러 가기": "#mf_txppWframe_pf_UTERNAAZ0Z11_btn_rigSts",
}


class HometaxError(Exception):
    """홈택스 작업 실패 — 해당 거래처만 FAILED로 회신."""


class HometaxLoginFailed(HometaxError):
    """홈택스 로그인 실패 — 계정 잠금 방지 위해 에이전트 정지."""


class HometaxCertRequired(HometaxError):
    """공동인증서 팝업이 필요하다 — 사람이 미리 세션을 남겨두었어야 한다."""


class ChromeLaunchFailed(HometaxError):
    """CDP 크롬이 없어 새로 띄우려 했지만 실행 파일을 못 찾았거나 포트가 열리지 않았다."""


def _is_hometax_main_url(url: str) -> bool:
    """홈택스 본 화면 탭인지 — 보안 모듈 창(sesw.hometax.go.kr)은 제외한다."""
    return "hometax.go.kr" in url and "sesw." not in url


def _find_chrome_executable() -> str:
    import os

    system = platform.system()
    candidates = [os.path.expandvars(p) for p in _CHROME_PATH_CANDIDATES.get(system, [])]
    for path in candidates:
        if Path(path).exists():
            return path
    raise ChromeLaunchFailed(f"Google Chrome 실행 파일을 찾지 못했습니다 (확인한 경로: {candidates})")


def launch_chrome(cdp_url: str, profile_dir: Path) -> None:
    """전용 프로필 + 디버깅 포트로 설치된 크롬을 띄운다 (scripts/start-chrome.*와 같은 옵션).

    Playwright `launch()`는 자동화 흔적이 남아 쓰지 않는다(plan/16 §8-4). 띄운 뒤 CDP 포트가
    열릴 때까지의 대기는 호출자 몫이다.
    """
    chrome = _find_chrome_executable()
    profile_dir.mkdir(parents=True, exist_ok=True)
    port = urlsplit(cdp_url).port or 9222
    subprocess.Popen(
        [
            chrome,
            f"--remote-debugging-port={port}",
            f"--user-data-dir={profile_dir}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-features=BlockThirdPartyCookies,PrivacySandboxSettings4",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


class TaxAgentLogin:
    """세무사 아이디로 홈택스 공동인증서 로그인 화면까지 연다 — 이지원 노트북 전용.

    1) CDP 크롬(`cdp_url`)이 이미 떠 있으면 그 크롬에 새 탭을 열어 홈택스로 이동한다.
    2) 없으면 `scripts/start-chrome.sh`·`.ps1`과 같은 옵션(전용 프로필 + 디버깅 포트)으로
       설치된 크롬을 새로 띄운다(=새 창) — Playwright `launch()`로 띄우면 자동화 흔적이
       남으므로 쓰지 않는다(`plan/16-wehago-rpa.md` §8-4, `wehago.py` `CdpConnectFailed`와
       같은 원칙). 새로 띄운 뒤에는 결국 같은 CDP로 붙는다.
    3) 로그인 페이지 기본 탭(금융·공동 인증, 탭 전환 없이 그대로)에서 [로그인] 버튼을 눌러
       공동인증서 선택 팝업을 띄운다.

    인증서 선택(OS 다이얼로그)·인증서 비밀번호 입력은 브라우저 밖이라 Playwright가 다룰 수
    없다 — 이 클래스는 그 팝업을 띄우는 지점까지만 책임진다(`HometaxSession` 상단 문서와
    같은 경계).
    """

    def __init__(self, cdp_url: str, profile_dir: Path) -> None:
        self._cdp_url = cdp_url
        self._profile_dir = profile_dir
        self._playwright = None
        self._browser = None
        self._page = None

    def __enter__(self) -> "TaxAgentLogin":
        from playwright.sync_api import sync_playwright

        self._playwright = sync_playwright().start()
        self._browser = self._connect_or_launch()
        contexts = self._browser.contexts
        context = contexts[0] if contexts else self._browser.new_context()
        self._page = context.new_page()
        return self

    def __exit__(self, *exc: object) -> None:
        # CDP로 붙은 경우든 새로 띄운 경우든 크롬 자체는 끄지 않는다 — 연결만 끊는다
        # (인증서 선택은 사람이 이 창에서 이어서 완료해야 하므로 닫으면 안 된다).
        if self._browser:
            self._browser.close()
        if self._playwright:
            self._playwright.stop()

    def _connect_or_launch(self):
        from playwright.sync_api import Error as PlaywrightError

        try:
            return self._playwright.chromium.connect_over_cdp(self._cdp_url)
        except PlaywrightError:
            pass  # CDP 크롬이 없음 — 새로 띄운다

        launch_chrome(self._cdp_url, self._profile_dir)

        deadline = time.monotonic() + CHROME_LAUNCH_TIMEOUT_SEC
        last_error: Exception | None = None
        while time.monotonic() < deadline:
            try:
                return self._playwright.chromium.connect_over_cdp(self._cdp_url)
            except PlaywrightError as e:
                last_error = e
                time.sleep(0.5)
        raise ChromeLaunchFailed(
            f"새로 띄운 크롬({self._cdp_url})에 연결하지 못했습니다"
        ) from last_error

    def open_cert_login(self) -> None:
        """홈택스 로그인 페이지로 이동해 [로그인] 버튼을 눌러 공동인증서 선택 팝업을 띈다."""
        assert self._page is not None
        self._page.goto(HOMETAX_LOGIN_URL, wait_until="domcontentloaded")
        button = self._page.locator(_CERT_LOGIN_BUTTON)
        button.wait_for(state="visible", timeout=LOGIN_FORM_WAIT_MS)
        button.click()


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
        """홈택스 탭을 준비한다. 이미 열려 있는 홈택스 탭(이전 실행이 남긴 로그인 세션)이 있으면
        새로 열지 않고 재사용한다 — 실행할 때마다 탭이 쌓이지 않게. 위하고와는 다른 탭에서 조작한다."""
        existing = next((pg for pg in self._context.pages if _is_hometax_main_url(pg.url)), None)
        if existing is not None:
            self._page = existing
            return
        page = self._context.new_page()
        page.goto(HOMETAX_LOGIN_URL, wait_until="domcontentloaded")
        self._page = page

    def _is_logged_in(self) -> bool:
        try:
            return self._page.get_by_text("로그아웃", exact=False).count() > 0
        except Exception:
            return False

    def ensure_logged_in(
        self,
        poll_sec: float = 1.0,
        sleep=time.sleep,
        monotonic=time.monotonic,
    ) -> None:
        """로그인돼 있으면 그대로 통과하고, 아니면 공동인증서 로그인 팝업을 띄워 로그인 완료를 기다린다.

        - 이미 로그인된 세션(예: 맥에서 이전에 로그인해 둔 크롬)은 입력 없이 통과한다.
        - 로그인 순서는 아이디 → 공동인증서 선택 + 인증서 비밀번호 → 세무대리 관리번호
          (plan/17 §3-9-7-4)이고 Playwright로 조작 가능하다고 확인돼 있다. 그러나 각 단계의
          셀렉터를 아직 실측하지 못해 자동 입력은 구현하지 않았다. 지금은 인증서 팝업을 띄우는
          데까지만 하고, 사람이 이어서 끝낼 때까지 `HUMAN_LOGIN_WAIT_SEC` 동안 기다린다.
          시간 안에 끝나지 않으면 HometaxLoginFailed — 재시도하지 않는다(계정 잠금 방지,
          plan/16 §8-3). 셀렉터가 확정되면 이 대기 자리에 단계별 입력을 넣는다.
        """
        if self._page is None:
            self.open()
        assert self._page is not None
        page = self._page

        # 이미 열려 있던 탭이거나 방금 연 탭이거나, 로그인 표시("로그아웃")나 [로그인] 버튼이
        # 렌더링될 때까지 잠깐 기다린다 (WebSquare는 domcontentloaded 뒤에 그린다).
        deadline = monotonic() + LOGIN_FORM_WAIT_MS / 1000
        while monotonic() < deadline:
            if self._is_logged_in():
                return
            if self._login_button_visible():
                break
            sleep(0.5)
        if self._is_logged_in():
            return

        if not self._login_button_visible():
            page.goto(HOMETAX_LOGIN_URL, wait_until="domcontentloaded")
        button = page.locator(_CERT_LOGIN_BUTTON)
        try:
            button.wait_for(state="visible", timeout=LOGIN_FORM_WAIT_MS)
        except Exception as e:
            raise HometaxLoginFailed("홈택스 로그인 화면이 열리지 않음") from e
        button.click()

        deadline = monotonic() + HUMAN_LOGIN_WAIT_SEC
        while monotonic() < deadline:
            if self._is_logged_in():
                return
            sleep(poll_sec)
        raise HometaxLoginFailed(
            f"홈택스 로그인이 {HUMAN_LOGIN_WAIT_SEC}초 안에 끝나지 않았습니다 "
            "(공동인증서 선택·비밀번호·세무대리 관리번호 입력 필요 — 자동 입력은 셀렉터 실측 전)"
        )

    def _login_button_visible(self) -> bool:
        try:
            return self._page.locator(_CERT_LOGIN_BUTTON).first.is_visible()
        except Exception:
            return False

    # ------------------------------------------------------------------
    # 일용ㆍ간이지급명세서 (거주자의 사업소득/기타소득 포함) — 2026-09-28 실측
    # ------------------------------------------------------------------

    def _click_menu(self, menu_cd: str) -> None:
        """헤더에 숨어 있는 `#menuAtag_{menu_cd}` 앵커를 JS로 클릭해 메뉴를 이동한다.

        메뉴 화면 진입은 로그인된 홈택스 안에서의 단순 페이지 이동이라 최종 신고/제출과
        무관하다 — 경계는 각 화면의 "제출/신고" 버튼(상단 문서·`_DO_NOT_CLICK_SUBMIT_SELECTORS`)
        부터다.
        """
        assert self._page is not None
        found = self._page.evaluate(
            f"() => {{ const a = document.querySelector('#menuAtag_{menu_cd}'); "
            f"if (a) a.click(); return !!a; }}"
        )
        if not found:
            raise HometaxError(f"메뉴 앵커(#menuAtag_{menu_cd})를 찾지 못함 — 로그인 상태 확인 필요")
        self._page.wait_for_timeout(1500)

    def open_simplified_statement_screen(self) -> None:
        """일용ㆍ간이지급명세서 통합 작성 화면으로 이동한다 (직접작성 제출).

        이 화면 하나에서 (지급)명세서 선택 드롭다운으로 일용근로소득ㆍ간이지급명세서(사업소득)ㆍ
        간이지급명세서(기타소득) 등을 모두 다룬다 (`StatementKind` 참고).
        """
        if self._page is None:
            self.open()
        assert self._page is not None
        self._click_menu(SIMPLIFIED_STATEMENT_MENU_CD)
        self._page.locator("#mf_txppWframe_edtWhtxRperNo").wait_for(
            state="visible", timeout=LOGIN_FORM_WAIT_MS
        )

    def verify_business_number(self, business_number: str) -> str:
        """사업자(주민)등록번호를 입력하고 [확인]을 눌러 상호/성명을 조회한다.

        WebSquare 입력칸이라 fill()은 값이 반영되지 않을 수 있어 한 글자씩 친다
        (wehago.py `_type_fresh`와 동일한 이유). 조회 결과가 비어 있으면 등록되지 않은
        사업자번호로 보고 HometaxError를 던진다 — 실측 중 더미 사업자번호(예: 224-02-38407,
        서도)는 실제로 조회에 성공했다(국세청 실제 등록 사업자였다).
        """
        assert self._page is not None, "open_simplified_statement_screen() 먼저 호출"
        digits = "".join(ch for ch in business_number if ch.isdigit())
        field = self._page.locator("#mf_txppWframe_edtWhtxRperNo")
        field.click()
        field.press("ControlOrMeta+a")
        field.press("Backspace")
        field.type(digits, delay=50)
        self._page.click("#mf_txppWframe_btnWhtxRperNoChk")
        self._page.wait_for_timeout(1500)
        name = self._page.locator("#mf_txppWframe_edtTxprNm").input_value()
        if not name:
            raise HometaxError(
                f"사업자(주민)등록번호 조회 실패 — 등록되지 않았거나 형식이 잘못됨: {business_number}"
            )
        return name

    def select_statement_kind(self, kind: str) -> None:
        """(지급)명세서 선택 드롭다운 — `StatementKind` 상수를 넘긴다.

        선택을 바꾸면 화면이 사업자(주민)등록번호 등 입력값을 초기화한다(2026-09-28 실측) —
        `verify_business_number`는 이 메서드 다음에 호출한다.
        """
        assert self._page is not None
        self._page.select_option("#mf_txppWframe_mateKndCd", kind)
        self._page.wait_for_timeout(500)

    def select_filing_type(self, filing_type: int) -> None:
        """제출구분 라디오 — `FilingType` 상수를 넘긴다."""
        assert self._page is not None
        self._page.locator(f"#mf_txppWframe_rtnClDetailCd_input_{filing_type}").check()

    # ------------------------------------------------------------------
    # 원천세 신고 (원천징수이행상황신고서) — 2026-09-28 실측, 진입 화면까지만
    # ------------------------------------------------------------------

    def open_wht_filing_screen(self) -> None:
        """세금신고 > 원천세 신고 > 일반신고 진입 화면으로 이동한다."""
        if self._page is None:
            self.open()
        assert self._page is not None
        self._click_menu(WHT_FILING_MENU_CD)
        # get_by_text는 화면 곳곳의 숨은 접근성 라벨(span)까지 집어 헷갈린다 (2026-09-28 실측) —
        # 실제 보이는 카드 제목(class="w2group tit")만 골라 기다린다.
        self._page.wait_for_function(
            """() => [...document.querySelectorAll('.w2group.tit')]
                .some(el => el.textContent.trim() === '정기신고' && el.offsetParent !== null)""",
            timeout=LOGIN_FORM_WAIT_MS,
        )

    def start_regular_filing(self) -> None:
        """[정기신고] 카드를 클릭한다 — 원천징수이행상황신고서 작성 화면 진입 직전까지만.

        클릭 직후 "2026년 09월 지급분을 신고하는 작성화면입니다" 같은 안내 팝업이 뜬다.
        그 팝업을 닫고 실제 신고서 작성 화면(사업자번호·귀속월·A코드별 금액 입력 등)으로
        들어가는 부분은 2026-09-28 세션에서 실측하지 못했다 — 실제 정부 신고 화면으로 더
        들어가는 조작이라 자동화 환경의 안전 정책상 더 진행하지 않았다. 사람이 직접 화면을
        보면서 이어서 실측해야 한다 (§ 상단 문서 참조).
        """
        assert self._page is not None, "open_wht_filing_screen() 먼저 호출"
        card_id = self._page.evaluate(
            """() => {
                for (const el of document.querySelectorAll('[id^="mf_txppWframe"].w2group.tit, [id^="mf_txppWframe"] .w2group.tit')) {
                    if (el.textContent.trim() === '정기신고') {
                        const a = el.closest('a');
                        return a ? a.id : null;
                    }
                }
                return null;
            }"""
        )
        if not card_id:
            raise HometaxError("[정기신고] 카드를 찾지 못함 — 화면 구조가 바뀌었을 수 있음")
        self._page.click(f"#{card_id}")
        raise NotImplementedError(
            "[정기신고] 카드 클릭까지만 실측됨. 이어지는 안내 팝업 닫기·실제 신고서 작성 "
            "화면(사업자번호·귀속월·A코드별 금액 입력)은 사람이 직접 실측 후 구현해야 한다."
        )

    def open_file_conversion_filing_screen(self) -> None:
        """[파일변환신고] 카드를 클릭한다 — 위하고T 등에서 제작한 신고서 파일을 그대로 업로드하는 방식.

        `open_wht_filing_screen()`을 먼저 호출해야 한다. 이 화면의 신고구분ㆍ신고종류ㆍ신고서종류
        드롭박스는 기본값이 이미 정기(확정)ㆍ정기신고ㆍ원천징수이행상황신고서라 별도로 건드리지
        않는다(2026-09-28 실측).
        """
        assert self._page is not None, "open_wht_filing_screen() 먼저 호출"
        card_id = self._page.evaluate(
            """() => {
                for (const el of document.querySelectorAll('[id^="mf_txppWframe"].w2group.tit, [id^="mf_txppWframe"] .w2group.tit')) {
                    if (el.textContent.trim() === '파일변환신고') {
                        const a = el.closest('a');
                        return a ? a.id : null;
                    }
                }
                return null;
            }"""
        )
        if not card_id:
            raise HometaxError("[파일변환신고] 카드를 찾지 못함 — 화면 구조가 바뀌었을 수 있음")
        self._page.click(f"#{card_id}")
        self._page.locator("#mf_txppWframe_pf_UTERNAAZ0Z11_btn_selFileB").wait_for(
            state="visible", timeout=LOGIN_FORM_WAIT_MS
        )

    def select_conversion_file(self, file_path: str) -> None:
        """[파일선택] 버튼을 눌러 신고서 파일(위하고T 등에서 제작한 파일)을 첨부한다.

        [파일선택]은 네이티브 파일 선택창을 여는 버튼이라(page.locator로 잡히는 `<input type=file>`이
        DOM에 없음, 2026-09-28 실측) Playwright의 `expect_file_chooser`로 가로채야 한다.

        **여기서 멈춘다.** 파일 첨부 다음 단계인 [파일검증하기]ㆍ[제출하러 가기]는 이 메서드가
        호출하지 않는다 (`_DO_NOT_CLICK_SUBMIT_SELECTORS` 참조) — 실제 정부 신고 화면을 더
        진행시키는 조작이라 사람이 직접 눌러야 한다.
        """
        assert self._page is not None, "open_file_conversion_filing_screen() 먼저 호출"
        with self._page.expect_file_chooser(timeout=LOGIN_FORM_WAIT_MS) as fc_info:
            self._page.click("#mf_txppWframe_pf_UTERNAAZ0Z11_btn_selFileB")
        fc_info.value.set_files(file_path)
        self._page.wait_for_timeout(1000)

    def save_failure_screenshot(self, name: str) -> None:
        if self._page is None:
            return
        self._screenshot_dir.mkdir(parents=True, exist_ok=True)
        self._page.screenshot(path=str(self._screenshot_dir / f"hometax-{name}.png"))

    def close(self) -> None:
        if self._page is not None:
            self._page.close()
            self._page = None
