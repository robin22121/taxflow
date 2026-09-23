"""위하고T 화면 조작 — 노트북에 미리 띄워 둔 크롬에 CDP로 붙어 급여자료 엑셀을 올린다.

크롬은 `rpa-agent/scripts/start-chrome.ps1`(Windows) / `start-chrome.sh`(macOS)이
원격 디버깅 포트를 열어 실행하고, 에이전트는 `connect_over_cdp`로만 붙는다
(에이전트가 브라우저 프로세스를 관리하지 않는다).

로그인·수임처 목록·수임처정보 화면은 2026-09-23 실측(§9-2 후속)으로 셀렉터를 확정했다.
급여자료입력 · SmartA 사원자료 엑셀변환 화면은 추가 실측 필요 (NotImplementedError).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from easyone_agent.company import normalize_business_number

WEHAGO_URL = "https://www.wehagot.com"  # 위하고 T (세무회계사무소용)
TAXAGENT_URL = f"{WEHAGO_URL}/tedge/#/taxagent"  # 세무대리인 수임처 관리
LOGIN_WAIT_MS = 60_000  # QR 추가 인증이 뜨면 사람이 처리할 시간
LOGIN_FORM_WAIT_MS = 15_000
SIDEBAR_WAIT_MS = 15_000
RIGHT_PANE_WAIT_MS = 10_000
DIMMED_WAIT_MS = 10_000  # 로딩 오버레이(div.dimmed)가 사라질 때까지

# 로그인 화면에 보이는 문구 → 실패 사유 (위하고 번들의 한국어 문구)
_LOGIN_FAILURE_HINTS = {
    "아이디 또는 비밀번호가 올바르지 않습니다": "아이디 또는 비밀번호가 올바르지 않음",
    "자동입력 방지": "자동입력 방지 문자(캡차) 요구",
    "QR코드": "QR 추가 인증 요구",
}

# 로그인 직후·화면 진입 시 뜨는 안내 팝업들 — 모두 같은 dialog 클래스에 [닫기] 버튼
# (2차 인증 안내·노란우산공제 안내 등 서비스 프로모션)
_SPLASH_DIALOG = "div.LUX_basic_dialog:visible"

# 수임처정보 화면의 우측 '기본정보' 탭 th 라벨 → 표준 필드
_READ_COMPANY_LABELS = {
    "사업자등록번호 / 종사업장번호": "business_number_raw",
    "회사구분": "corporation_type",
    "소득구분": "income_type",
    "업종코드": "business_class_code",
    "업태/업종": "business_type",
    "전화번호": "phone",
    "사업장 주소": "business_address",
    "개업/폐업 년월일": "opened_closed_at",
    "수임여부": "tax_agency_status",
    "수임 일자": "tax_agency_started_at",
}


class WehagoError(Exception):
    """위하고 작업 실패 — 해당 작업만 FAILED로 회신하고 다음 작업으로 넘어간다."""


class LoginFailed(WehagoError):
    """로그인 실패 — 재시도하면 계정이 잠길 수 있어 에이전트 자체를 멈춘다."""


class CompanyMismatch(WehagoError):
    """사업자번호로 연 수임처가 요청한 거래처와 다르다 — 업로드하지 않는다."""


class CompanyNotFound(WehagoError):
    """검색 결과가 0건이거나 정확히 1건이 아니다."""


class CdpConnectFailed(Exception):
    """노트북 크롬에 CDP로 붙지 못했다 — start-chrome 스크립트가 안 돌고 있을 가능성."""


class WehagoUploader:
    def __init__(self, user_id: str, password: str, cdp_url: str, screenshot_dir: Path) -> None:
        self._user_id = user_id
        self._password = password
        self._cdp_url = cdp_url
        self._screenshot_dir = screenshot_dir
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None

    def __enter__(self) -> WehagoUploader:
        from playwright.sync_api import Error as PlaywrightError, sync_playwright

        self._playwright = sync_playwright().start()
        try:
            self._browser = self._playwright.chromium.connect_over_cdp(self._cdp_url)
        except PlaywrightError as e:
            self._playwright.stop()
            self._playwright = None
            raise CdpConnectFailed(
                f"노트북 크롬({self._cdp_url})에 연결하지 못했습니다. "
                "먼저 scripts/start-chrome.ps1 로 크롬을 실행하세요."
            ) from e
        # start-chrome이 만든 기본 컨텍스트를 그대로 쓴다 (프로필·쿠키·확장이 살아 있음).
        contexts = self._browser.contexts
        self._context = contexts[0] if contexts else self._browser.new_context()
        pages = self._context.pages
        self._page = pages[0] if pages else self._context.new_page()
        return self

    def __exit__(self, *exc: object) -> None:
        # 크롬은 start-chrome가 관리한다. 에이전트는 CDP 연결만 끊는다 (브라우저 종료 X).
        if self._browser:
            self._browser.close()
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
                self._dismiss_splash()
                return  # 크롬 프로필에 세션이 남아 있다
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
        self._dismiss_splash()

    def _login_failure_reason(self) -> str:
        visible_text = self._page.locator("body").inner_text()
        for hint, reason in _LOGIN_FAILURE_HINTS.items():
            if hint in visible_text:
                return reason
        return "로그인 화면에서 넘어가지 않음"

    def _save_failure_screenshot(self) -> None:
        # 원인 확인용으로 PC에만 남긴다 (서버로 보내지 않는다). 입력칸은 가린다.
        page = self._page
        self._screenshot_dir.mkdir(parents=True, exist_ok=True)
        page.screenshot(
            path=str(self._screenshot_dir / "login-failed.png"),
            mask=[page.locator("#inputId"), page.locator("#inputPw")],
        )

    def _dismiss_splash(self) -> None:
        """로그인 후·화면 진입 시 뜨는 안내 팝업(2차 인증·노란우산공제 등)을 모두 닫는다.

        같은 `div.LUX_basic_dialog` 클래스에 [닫기] 버튼이 여러 개인 경우가 있어
        보이는 dialog가 없어질 때까지 마지막 [닫기] 버튼을 반복 클릭한다.
        """
        page = self._page
        for _ in range(5):
            dialog = page.locator(_SPLASH_DIALOG).first
            if dialog.count() == 0:
                return
            # 마지막 '닫기' 버튼이 대체로 dismiss 역할 (2차 인증 dialog는 [닫기]·[설정하기]·[닫기(X)] 3개)
            close_buttons = dialog.locator("button:has-text('닫기')")
            if close_buttons.count() == 0:
                return  # 닫기 버튼이 없는 경우는 화면을 조작하지 않는다
            close_buttons.last.click(force=True)
            page.wait_for_timeout(400)

    def open_company(self, business_number: str) -> tuple[str, str]:
        """수임처를 사업자번호로 검색해 연다. 검색 결과가 정확히 1건이 아니면 CompanyNotFound."""
        self._goto_taxagent_and_search(business_number)
        items = self._page.locator("li.is_linkbtn")
        n = items.count()
        if n != 1:
            hint = self._page.locator("p.search_result_text").inner_text() if n else ""
            raise CompanyNotFound(
                f"수임처 검색 결과가 정확히 1건이 아닙니다 ({n}건). {hint}".strip()
            )
        name = items.first.inner_text().strip().splitlines()[0].strip()
        self._select_company(items.first, name)
        return self._read_company_basic_pair()

    def upload_payroll(self, xlsx_path: Path, period: str) -> str:
        """급여자료입력 메뉴에서 귀속연월을 맞추고 엑셀을 올린다.

        Returns:
            화면의 업로드 결과 메시지. 오류 메시지가 뜨면 WehagoError.
        """
        # TODO: 급여자료입력 화면 실측 후 구현 (SmartA 진입 경로·컬럼 매칭 UI·업로드 결과 메시지)
        raise NotImplementedError("위하고 급여자료입력 엑셀 업로드 화면 실측 후 구현")

    # --- 위하고 → 이지원천 가져오기 (plan/16 §12, import_runner.WehagoImportSource) ---

    def list_companies(self) -> list[tuple[str, str]]:
        """수임처관리(/tedge/#/taxagent) 왼쪽 목록 전체 → (상호, 사업자번호).

        사이드바 항목(li.is_linkbtn)에는 회사명만 있고 사업자번호는 우측 pane에 있어
        하나씩 클릭해 사업자번호를 읽는다. 수백 곳을 처리하려면 시간이 걸리므로
        import_runner 는 수임처 단위로 진행률·중간 결과를 서버에 보낸다.
        """
        from playwright.sync_api import TimeoutError as PlaywrightTimeout

        page = self._page
        self._goto_taxagent()
        self._clear_search()
        try:
            page.locator("li.is_linkbtn").first.wait_for(state="visible", timeout=SIDEBAR_WAIT_MS)
        except PlaywrightTimeout:
            # 담당 수임처가 0곳이면 사이드바가 비어 있다 (오류 아님)
            return []

        names = self._sidebar_company_names()
        result: list[tuple[str, str]] = []
        for name in names:
            items = page.locator("li.is_linkbtn").filter(has_text=name)
            if items.count() == 0:
                continue
            try:
                self._select_company(items.first, name)
                number = self._read_business_number()
            except WehagoError:
                continue  # 한 곳이 실패해도 다음 곳 계속
            result.append((name, number))
        return result

    def read_company(self, business_number: str) -> dict[str, Any]:
        """수임처정보 [기본정보] 탭 — 상호·사업자번호·대표자·업태/업종·사업장 주소·전화번호.

        대표자 주민번호도 화면에 보이지만 가져오지 않는다 (이지원천에 필요 없음).
        """
        self._goto_taxagent_and_search(business_number)
        items = self._page.locator("li.is_linkbtn")
        if items.count() == 0:
            raise CompanyNotFound(f"수임처를 찾지 못했습니다: {business_number}")
        name = items.first.inner_text().strip().splitlines()[0].strip()
        self._select_company(items.first, name)
        return self._read_company_basic()

    def export_employees(self, business_number: str, workdir: Path) -> Path:
        """SmartA 사원등록(SWPM0108) → 추가기능(⋮) → [사원자료 엑셀변환] 다운로드 파일.

        위하고 T 담당 수임처 대시보드에서 [급여] 버튼을 클릭하면 새 탭에 SmartA 가 열리는데
        (SSO 토큰 sao 를 포함한 URL), 그 진입 경로 실측 전이라 NotImplementedError.

        캡처 완료된 사실 (2026-09-23):
        - SmartA URL: `smarta.wehagot.com/#/smarta/humanresource/SWPM0108?sao=...&cno=<CNO>&cd_com=<CDCOM>&gisu=<PERIOD>&yminsa=<YEAR>&...`
        - 트리거: 상단 우측 `div.LUX_basic_popover.popover_funtion` (43×32 아이콘)
        - 팝오버 컨테이너: `div.resultbx` (position:absolute, z-index:45)
        - 항목: `dl:has(dt:text-is('엑셀')) dd:text-is('사원자료 엑셀변환')`
        - 다운로드 파일명: `<회사명>_사원등록_<YYYYMMDD>.xlsx` (기본 Downloads 폴더)
        - Playwright download 이벤트가 잡히지 않으므로 폴더 감시 방식으로 수신해야 함
        """
        # TODO: 담당 수임처 대시보드 → SmartA 진입 → 사원등록 이동 → 엑셀변환 클릭 → Downloads 감시
        raise NotImplementedError("위하고 T → SmartA 사원자료 엑셀변환 경로 실측 후 구현")

    # ---- 내부 헬퍼 ----

    def _goto_taxagent(self) -> None:
        """수임처관리 화면으로 이동. 이미 그 URL이면 재로드해 필터·상태를 초기화."""
        page = self._page
        if "/tedge/#/taxagent" in page.url:
            page.reload()
        else:
            page.goto(TAXAGENT_URL)
        self._dismiss_splash()
        self._wait_for_no_dimmed()

    def _clear_search(self) -> None:
        """수임처 검색창 비우기 (SPA 상태에 이전 필터가 남을 수 있음)."""
        page = self._page
        search = page.locator("input[placeholder*='사업자번호']").first
        if search.count() == 0:
            return
        try:
            search.wait_for(state="visible", timeout=SIDEBAR_WAIT_MS)
        except Exception:
            return
        if search.input_value():
            search.fill("")
            search.press("Enter")
            self._wait_for_no_dimmed()

    def _goto_taxagent_and_search(self, business_number: str) -> None:
        """수임처관리 화면으로 이동 → 사업자번호로 검색.

        위하고 검색은 하이픈 있는 사업자번호(예: 224-02-38407)를 매칭 못 한다 (실측).
        하이픈 없는 10자리 숫자로 정규화해서 넣는다.
        """
        page = self._page
        if "/tedge/#/taxagent" not in page.url:
            self._goto_taxagent()
        self._dismiss_splash()
        self._wait_for_no_dimmed()
        search = page.locator("input[placeholder*='사업자번호']").first
        search.wait_for(state="visible", timeout=SIDEBAR_WAIT_MS)
        search.fill("")
        search.press_sequentially(normalize_business_number(business_number))
        search.press("Enter")
        self._wait_for_no_dimmed()

    def _select_company(self, item, expected_name: str) -> None:
        """사이드바 항목을 클릭하고 우측 pane이 전환될 때까지 대기.

        (1) 오버레이 정리 → (2) 이전 pane 값 스냅샷 → (3) 클릭 →
        (4) 사이드바 .selected 이동 → (5) 우측 pane 사업자번호 값이 이전과 달라짐.
        pane 로딩이 끝나기 전에 읽으면 이전 회사 데이터를 그대로 읽는 레이스가 있다.
        """
        from playwright.sync_api import TimeoutError as PlaywrightTimeout

        self._wait_for_no_dimmed()
        try:
            item.wait_for(state="visible", timeout=SIDEBAR_WAIT_MS)
        except PlaywrightTimeout:
            raise WehagoError(f"사이드바에서 항목을 찾지 못했습니다: {expected_name}") from None
        selected = self._page.locator("li.is_linkbtn.selected").first
        already = selected.count() and expected_name in selected.inner_text()
        if already:
            # 이미 선택돼 있으면 pane 값이 비-빈이 될 때까지만 확인.
            self._wait_for_pane_non_empty()
            return
        # 전환 감지: 이전 pane 값을 기억해 두고, 클릭 후 그 값과 다른 비-빈 값이 될 때까지 대기.
        prev_number = self._current_pane_business_number()
        # 로딩 오버레이(div.dimmed)가 클릭을 가로챌 수 있어 pointer intercept 체크 우회.
        item.click(force=True)
        try:
            self._page.locator(
                f"li.is_linkbtn.selected:has-text({_js_string(expected_name)})"
            ).first.wait_for(state="visible", timeout=RIGHT_PANE_WAIT_MS)
        except PlaywrightTimeout:
            pass
        self._wait_for_no_dimmed()
        try:
            self._page.wait_for_function(
                """(prev) => {
                    const th = [...document.querySelectorAll('tr th')].find(
                        el => el.innerText.trim().includes('사업자등록번호')
                    );
                    if (!th) return false;
                    const tr = th.closest('tr');
                    const td = tr && tr.querySelector('td');
                    if (!td) return false;
                    const v = td.innerText.trim();
                    return v !== '' && (prev === '' || v !== prev);
                }""",
                arg=prev_number,
                timeout=RIGHT_PANE_WAIT_MS,
            )
        except PlaywrightTimeout:
            pass  # 값이 정말 이전과 같거나 비었을 수 있음

    def _wait_for_pane_non_empty(self) -> None:
        """우측 pane 사업자번호 td 가 비-빈 값이 될 때까지 (초기 로딩 대기)."""
        from playwright.sync_api import TimeoutError as PlaywrightTimeout

        try:
            self._page.wait_for_function(
                """() => {
                    const th = [...document.querySelectorAll('tr th')].find(
                        el => el.innerText.trim().includes('사업자등록번호')
                    );
                    if (!th) return false;
                    const tr = th.closest('tr');
                    const td = tr && tr.querySelector('td');
                    return td && td.innerText.trim() !== '';
                }""",
                timeout=RIGHT_PANE_WAIT_MS,
            )
        except PlaywrightTimeout:
            pass

    def _current_pane_business_number(self) -> str:
        """지금 우측 pane에 표시된 사업자번호 (전환 감지용 스냅샷). 없으면 빈 문자열."""
        return self._page.evaluate(
            """() => {
                const th = [...document.querySelectorAll('tr th')].find(
                    el => el.innerText.trim().includes('사업자등록번호')
                );
                if (!th) return '';
                const tr = th.closest('tr');
                const td = tr && tr.querySelector('td');
                return td ? td.innerText.trim() : '';
            }"""
        )

    def _wait_for_no_dimmed(self) -> None:
        """로딩 오버레이(div.dimmed)가 사라질 때까지 대기. 클릭 인터셉트 방지."""
        from playwright.sync_api import TimeoutError as PlaywrightTimeout

        try:
            self._page.locator("div.dimmed:visible").wait_for(
                state="hidden", timeout=DIMMED_WAIT_MS
            )
        except PlaywrightTimeout:
            # 오버레이가 끝나지 않으면 그대로 진행 — 클릭 실패로 상위에서 잡힌다
            pass

    def _sidebar_company_names(self) -> list[str]:
        """사이드바에 보이는 회사명 리스트. 항목 텍스트의 첫 줄이 회사명이다."""
        items = self._page.locator("li.is_linkbtn")
        names: list[str] = []
        for i in range(items.count()):
            text = items.nth(i).inner_text().strip()
            first_line = text.splitlines()[0].strip() if text else ""
            if first_line:
                names.append(first_line)
        return names

    def _read_company_basic(self) -> dict[str, Any]:
        """우측 pane [기본정보] 탭 — th 라벨 → td 값을 딕셔너리로 반환."""
        page = self._page
        page.locator("th:has-text('사업자등록번호')").first.wait_for(
            state="visible", timeout=RIGHT_PANE_WAIT_MS
        )
        # 페이지 이동 없이 한 번에 라벨·값을 딕셔너리로 뽑는다 (반복 중 DOM 재렌더 회피).
        pairs: dict[str, str] = page.evaluate(
            """() => {
                const out = {};
                for (const tr of document.querySelectorAll('tr')) {
                    const th = tr.querySelector('th');
                    const td = tr.querySelector('td');
                    if (!th || !td) continue;
                    const label = (th.innerText || '').trim();
                    if (!label) continue;
                    out[label] = (td.innerText || '').trim();
                }
                return out;
            }"""
        )

        business_number = _clean_business_number(pairs.get("사업자등록번호 / 종사업장번호", ""))
        representative = _split_before_slash(pairs.get("대표자이름 /주민등록번호", ""))
        # 회사명은 사이드바의 선택된 li에서 읽는다 (우측 pane에는 회사명이 표 밖에 있음)
        selected = page.locator("li.is_linkbtn.selected").first
        selected_text = selected.inner_text().strip() if selected.count() else ""
        business_name = selected_text.splitlines()[0].strip() if selected_text else ""

        return {
            "business_name": business_name,
            "business_number": business_number,
            "representative": representative,
            "business_type": pairs.get("업태/업종", "") or None,
            "business_class_code": pairs.get("업종코드", "") or None,
            "business_address": pairs.get("사업장 주소", "") or None,
            "phone": pairs.get("전화번호", "") or None,
        }

    def _read_company_basic_pair(self) -> tuple[str, str]:
        """(회사명, 사업자번호)만 뽑는다 (open_company용)."""
        basics = self._read_company_basic()
        return basics["business_name"], basics["business_number"]

    def _read_business_number(self) -> str:
        """우측 pane에서 사업자번호만 읽는다 (list_companies 중 반복 호출용)."""
        page = self._page
        page.locator("th:has-text('사업자등록번호')").first.wait_for(
            state="visible", timeout=RIGHT_PANE_WAIT_MS
        )
        raw = page.evaluate(
            """() => {
                const th = [...document.querySelectorAll('tr th')].find(
                    el => el.innerText.trim().includes('사업자등록번호')
                );
                if (!th) return '';
                const tr = th.closest('tr');
                const td = tr && tr.querySelector('td');
                return td ? td.innerText.trim() : '';
            }"""
        )
        return _clean_business_number(raw)


def _clean_business_number(value: str) -> str:
    """사업자번호 표시값에서 '/종사업장번호', 공백 등을 정리하고 하이픈 유지."""
    if not value:
        return ""
    head = value.split("/")[0].strip()
    return re.sub(r"\s+", "", head)


def _split_before_slash(value: str) -> str | None:
    """'엄순덕 / 600915-2323614' → '엄순덕'. 주민번호 부분은 버린다."""
    if not value:
        return None
    return value.split("/")[0].strip() or None


def _js_string(value: str) -> str:
    """Playwright 텍스트 셀렉터에 넣을 JS 문자열 리터럴로 인용."""
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'
