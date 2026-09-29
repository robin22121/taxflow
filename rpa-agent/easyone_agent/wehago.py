"""위하고T 화면 조작 — 노트북에 미리 띄워 둔 크롬에 CDP로 붙어 급여자료 엑셀을 올린다.

크롬은 `rpa-agent/scripts/start-chrome.ps1`(Windows) / `start-chrome.sh`(macOS)이
원격 디버깅 포트를 열어 실행하고, 에이전트는 `connect_over_cdp`로만 붙는다
(에이전트가 브라우저 프로세스를 관리하지 않는다).

로그인·수임처 목록·수임처정보·급여자료입력·사원자료 엑셀변환(§12) 화면은
2026-09-23~25 실측으로 셀렉터를 확정했다. 사원자료 엑셀변환은 구현은 됐으나
실제 노트북에서 끝까지 실행해 검증하는 절차가 아직 남아 있다 (export_employees 참고).
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from easyone_agent.company import normalize_business_number
from easyone_agent.pace import key_delay_ms, think

WEHAGO_URL = "https://www.wehagot.com"  # 위하고 T (세무회계사무소용)
TAXAGENT_URL = f"{WEHAGO_URL}/tedge/#/taxagent"  # 세무대리인 수임처 관리
LOGIN_WAIT_MS = 60_000  # QR 추가 인증이 뜨면 사람이 처리할 시간
LOGIN_FORM_WAIT_MS = 15_000
SIDEBAR_WAIT_MS = 15_000
RIGHT_PANE_WAIT_MS = 10_000
DIMMED_WAIT_MS = 10_000  # 로딩 오버레이(div.dimmed)가 사라질 때까지
UPLOAD_WAIT_MS = 30_000

# SmartA 급여자료입력 (2026-09-24 실측)
_PAY_KIND = "2. 급여+상여"  # 급여자료입력 구분 — 새로 연 화면은 비어 있다가 귀속연월 입력 후 채워진다
_PAYROLL_MENU_ID = "SWSA0101"  # 급여자료입력 화면 코드 = SmartA 메뉴 링크 id
_PAYROLL_SCREEN = f"/smarta/humanresource/{_PAYROLL_MENU_ID}"

# SmartA 사원등록 → 사원자료 엑셀변환 (§12, 2026-09-23 실측)
_EMPLOYEE_REGISTER_MENU_ID = "SWPM0108"  # 사원등록 화면 코드 = SmartA 메뉴 링크 id
_MORE_MENU_POPOVER = "div.LUX_basic_popover.popover_funtion"  # 화면 우측 상단 더보기(⋮) 아이콘 (43×32)
_MORE_MENU_POPUP = "div.resultbx"  # 더보기 팝오버 컨테이너
_EMPLOYEE_EXPORT_ITEM = "dl:has(dt:text-is('엑셀')) dd:text-is('사원자료 엑셀변환')"
_COND_BAR = "div.basic_condition"  # div.item 순서: 귀속연월·구분·지급일·지급일 코드도움·정렬

# SmartA 사업소득자료입력 → 엑셀서식 불러오기 (§13-3, 2026-09-28 실측)
_BUSINESS_INCOME_MENU_ID = "SWBU0102"  # 사업소득자료입력 화면 코드
_MORE_BUTTON = "button#collect"  # 더보기(⋮) — 급여자료입력과 같은 id, 실제 HTML로 확인됨
_EXCEL_UPLOAD_MENU_ITEM = "엑셀서식 불러오기"  # 더보기 메뉴 항목 (공백 있음)
_EXCEL_UPLOAD_CONFIRM_BUTTON = "엑셀서식불러오기"  # 옵션 다이얼로그 최종 버튼 (공백 없음 — 항목명과 다름, 실측 확인)
# 합계 열은 위하고가 다시 계산하므로 연결하지 않아도 된다
_TOTAL_COLUMNS = {"지급액계", "공제액계", "차인지급액"}
_EMPLOYEE_GRID = "Left_grid"  # 왼쪽 사원 목록 (cd_emp 사원코드 · nm_krname 이름)
_TOTALS_GRID = "Right_top_grid"  # 오른쪽 위 전체 사원 급여항목 합계 (nm_allow·fg_tax·am_tax)
_ALLOWANCE_GRID = "Mid_left_grid"  # 가운데 [급여항목] 그리드 (수당명 nm_allow·비과세코드 cd_freeref·비과세 한도 am_tflimit)
# 이지원천 업로드 양식의 비과세 수당 열 → (위하고 비과세 코드, 이지원천 제목)
# 식대 P01 식사대, 자가운전 H03 자가운전보조금, 육아수당 Q02 출산·6세 이하 보육 (2026-09-25 실측)
_NONTAXABLE_COLUMNS = {"H": ("P01", "식대"), "I": ("H03", "자가운전"), "J": ("Q02", "육아수당")}
_EXCEL_HEADER_ROWS = 2  # 이지원천 양식은 2단 병합 헤더 — 3행부터 사원 데이터
_REQUIRED_COLUMNS = {"사원코드", "사원명"}  # 위하고 필수 연결 (사원번호·성명)
_SELECTED_BG = "rgb(233, 245, 255)"  # 엑셀업로드 ① 제목행으로 선택된 칸 배경
_BG_JS = "(e) => getComputedStyle(e).backgroundColor"

# RealGrid(캔버스)는 DOM으로 행을 읽을 수 없어 React 소유 컴포넌트의 _gridView 로 읽는다
_REALGRID_VIEW_JS = """
    const fk = Object.keys(el).find(k => k.startsWith('__reactInternalInstance'));
    const gv = el[fk]._currentElement._owner._instance._gridView;
"""
_REALGRID_ROWS_JS = f"(el) => {{ {_REALGRID_VIEW_JS} return gv.getDataSource().getJsonRows(0, -1); }}"
_REALGRID_EMPLOYEES_JS = (
    f"(el) => {{ {_REALGRID_VIEW_JS} return gv.getDataSource().getJsonRows(0, -1)"
    ".map(r => [String(r.cd_emp ?? '').trim(), String(r.nm_krname ?? '').trim()]); }"
)
_REALGRID_SET_CURRENT_JS = f"(el, i) => {{ {_REALGRID_VIEW_JS} gv.setCurrent({{itemIndex: i}}); }}"

# 엑셀업로드 팝업 → [{col, excel, wehago, has_amount}] (엑셀 A열부터)
# ③ 매핑표(rowspan_fix)는 병합 없이 열이 맞춰져 있다: 행 0·1 엑셀 제목, 행 2·3 위하고 항목
_READ_MAPPING_JS = r"""
(dlg) => {
  const text = c => {
    if (!c) return '';
    const fake = c.querySelector('.fakeinput');
    return ((fake ? fake.innerText : c.innerText) || '').trim();
  };
  // ③ 매핑표: 첫 칸이 '엑셀양식'인 행 = 엑셀 제목, 'WEHAGO'인 행 = 연결된 위하고 항목 (제목 줄 수만큼)
  const map = [...dlg.querySelector('table.LStbl.rowspan_fix').rows].map(r => [...r.cells]);
  const excelRows = map.filter(r => text(r[0]) === '엑셀양식');
  const wehagoRows = map.filter(r => text(r[0]) === 'WEHAGO');
  // ① 미리보기: 0행 A·B·C 머리글, 1행 제목(제목 한 줄 양식) → 2행부터 사원
  const preview = [...dlg.querySelector('table.LStbl:not(.rowspan_fix)').rows]
    .slice(2).map(r => [...r.cells])
    .filter(cells => cells.length > 2 && cells.every(c => c.colSpan === 1) && text(cells[1]));
  const out = [];
  for (let i = 1; i < excelRows[0].length; i++) {
    const excel = excelRows.map(r => text(r[i])).filter(Boolean).pop() || '';
    if (!excel) continue;
    out.push({
      col: String.fromCharCode(64 + i),
      excel,
      wehago: wehagoRows.map(r => text(r[i])).find(Boolean) || '',
      has_amount: preview.some(cells => {
        const n = Number(text(cells[i]).replace(/,/g, ''));
        return Number.isFinite(n) && n !== 0;
      }),
    });
  }
  return out;
}
"""

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
        self._smarta_page = None  # open_payroll_screen 이 연 급여자료입력 탭
        # 실패 안내용 — 지금 어느 단계인지, 위하고에 저장됐을 수 있는지
        self.step = "준비"
        self.may_have_saved = False

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
        # Playwright 는 붙을 때 크롬 다운로드를 가로채(임시 폴더·무작위 이름·확장자 없음) 사람이
        # 위하고에서 내려받은 엑셀을 못 쓰게 된다 (2026-09-27). 에이전트는 이 기능을 쓰지 않으므로
        # 크롬 기본 다운로드(다운로드 폴더·원래 이름)로 되돌린다.
        try:
            self._browser.new_browser_cdp_session().send(
                "Browser.setDownloadBehavior", {"behavior": "default"}
            )
        except PlaywrightError:
            pass
        return self

    def __exit__(self, *exc: object) -> None:
        # 크롬은 start-chrome가 관리한다. 에이전트는 CDP 연결만 끊는다 (브라우저 종료 X).
        if self._browser:
            self._browser.close()
        if self._playwright:
            self._playwright.stop()

    def ensure_logged_in(self) -> None:
        """로그인 상태가 아니면 ID/PW로 로그인한다. 실패하면 LoginFailed (재시도 금지)."""
        self.step = "위하고 로그인"
        self.may_have_saved = False
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
        # 세션 만료 화면은 이전 아이디가 칸에 남아 있어 먼저 비운다 — 안 비우면 아이디가
        # 두 번 이어 붙어 로그인이 실패한다 (2026-09-27 실측).
        pw_input = page.locator("#inputPw")
        _type_fresh(id_input, self._user_id)
        think("wehago")
        _type_fresh(pw_input, self._password)
        think("wehago")
        # 틀린 값으로 [로그인]을 누르면 실패 횟수가 쌓여 계정이 잠길 수 있다 — 누르기 전에 확인
        if id_input.input_value() != self._user_id or pw_input.input_value() != self._password:
            raise LoginFailed("로그인 칸 입력값이 저장된 아이디·비밀번호와 달라 [로그인]을 누르지 않음")
        page.locator(".login_form button.WSC_LUXButton").click()
        try:
            page.wait_for_url(lambda url: "#/login" not in url, timeout=LOGIN_WAIT_MS)
        except PlaywrightTimeout:
            self._save_failure_screenshot()
            raise LoginFailed(self._login_failure_reason()) from None
        self._dismiss_splash()

    def save_failure_screenshot(self, name: str) -> None:
        """예상 못 한 실패 때 원인 확인용 화면 캡처 — 노트북에만 남긴다 (서버로 보내지 않음)."""
        page = self._smarta_page if self._smarta_page and not self._smarta_page.is_closed() else self._page
        if page is None:
            return
        try:
            self._screenshot_dir.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(self._screenshot_dir / f"{name}.png"))
        except Exception:  # 캡처 실패가 작업 결과 회신을 막으면 안 된다
            pass

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

    def _open_smarta(self, business_number: str):
        """위하고 T 메인 담당 수임처 검색 → [급여] 클릭 → SmartA 새 탭(메인화면) 반환.

        `_open_smarta_menu`(특정 메뉴로 바로 진입)와 `_open_closing_menu`(카테고리 전환이
        필요한 마감·제작 화면)가 공유하는 앞부분이다 (2026-09-25 실측, 2026-09-29 분리).

        수임처는 사업자번호(하이픈 없는 10자리)로 검색해 정확히 1건일 때만 연다.
        [급여]는 SmartA 를 새 탭으로 열고, 메뉴는 그 탭 안에서 바뀐다.
        오래된 SmartA 탭은 세션이 끊겨 있을 수 있어(`#/login/?type=expired`) 닫고 새로 연다.

        Returns:
            (SmartA 탭, 위하고 상호, 사업자번호) — 호출자가 작업의 거래처와 대조한다.
        """
        self.step = "담당 수임처 검색"
        page = self._page
        for other in list(self._context.pages):
            if other is not page and "smarta.wehagot.com" in other.url:
                other.close()
        self._smarta_page = None

        think("wehago")
        page.goto(f"{WEHAGO_URL}/#/main")
        self._dismiss_splash()
        self._wait_for_no_dimmed()
        # 담당 수임처 목록은 탭(전체/T edge 사용/T edge 미사용/개인고객/대시보드)으로 필터링된다.
        # "T edge 사용"이 기본 탭이라 T edge 미가입 수임처는 검색에 안 잡힌다 — "전체"로 전환
        # (explore_closing_screens.py에서 먼저 발견된 문제, 2026-09-29 적용).
        all_tab = page.locator("button.btn_tab", has_text="전체").first
        if all_tab.count():
            all_tab.click()
            page.wait_for_timeout(500)
        search = page.locator("input[placeholder*='사업자등록번호']").first
        search.wait_for(state="visible", timeout=SIDEBAR_WAIT_MS)
        target = normalize_business_number(business_number)
        search.fill(target)
        think("wehago")
        search.press("Enter")
        # 검색 결과가 늦게 걸러질 수 있다 (로그인 직후 목록 로딩) — 사업자번호가 같은 행만 고른다.
        rows = page.locator("li:has(p.company_num)")
        matching: list[int] = []
        for _ in range(20):
            page.wait_for_timeout(500)
            numbers = [normalize_business_number(t) for t in rows.locator("p.company_num").all_inner_texts()]
            matching = [i for i, n in enumerate(numbers) if n == target]
            if matching and len(numbers) == len(matching):
                break  # 검색이 걸러졌다
        if len(matching) != 1:
            raise CompanyNotFound(
                f"위하고 T 담당 수임처에서 사업자번호 {business_number} 가 정확히 1건이 아닙니다 ({len(matching)}건)"
            )
        row = rows.nth(matching[0])
        name = row.locator(".company_name a").first.inner_text().strip()
        number = _clean_business_number(row.locator("p.company_num").inner_text())

        think("wehago")
        with self._context.expect_page(timeout=UPLOAD_WAIT_MS) as new_tab:
            row.locator("button.btn_quick", has_text=re.compile(r"^급여$")).click()
        smarta = new_tab.value
        smarta.wait_for_load_state()
        return smarta, name, number

    def _open_smarta_menu(self, business_number: str, menu_id: str):
        """`_open_smarta` + 지정 메뉴 클릭 (2026-09-25 실측).

        Returns:
            (SmartA 탭, 위하고 상호, 사업자번호) — 호출자가 작업의 거래처와 대조한다.
        """
        smarta, name, number = self._open_smarta(business_number)
        menu = smarta.locator(f"a#{menu_id}.text_link")
        menu.wait_for(state="visible", timeout=UPLOAD_WAIT_MS)
        think("wehago")
        menu.click()
        return smarta, name, number

    def open_payroll_screen(self, business_number: str, period: str) -> tuple[str, str]:
        """수임처 → SmartA 급여자료입력(SWSA0101) 진입 (2026-09-25 실측).

        Returns:
            (위하고 상호, 사업자번호) — 호출자가 작업의 거래처와 대조한다.
        """
        smarta, name, number = self._open_smarta_menu(business_number, _PAYROLL_MENU_ID)
        self.step = "급여자료입력 화면 열기"
        smarta.locator(_COND_BAR).wait_for(state="visible", timeout=UPLOAD_WAIT_MS)

        # 탭 제목 "급여자료입력(2026) - 서도" — 회사·귀속 연도를 한 번 더 확인
        title = smarta.title()
        year = period.split("-")[0]
        if not title.endswith(f"- {name}"):
            raise CompanyMismatch(f"SmartA 화면 회사가 다릅니다: {title} (위하고 T 수임처 {name})")
        if f"({year})" not in title:
            # 귀속 연도 전환 화면은 미실측 — 12월 귀속을 다음 해에 올리는 경우 등
            raise WehagoError(f"SmartA 귀속 연도가 다릅니다: {title} (작업 {period})")
        self._smarta_page = smarta
        return name, number

    def upload_payroll(
        self,
        xlsx_path: Path,
        period: str,
        pay_date: date,
        *,
        commit: bool = True,
        replace_existing: bool = False,
    ) -> str:
        """급여자료입력(SWSA0101) — 조회 → 엑셀 불러오기 → 항목 연결 확인 → 변환 → 대조.

        SmartA 급여자료입력 탭이 이미 열려 있어야 한다 (수임처 → SmartA 진입은 미실측).
        구분은 기본값 '2. 급여+상여'를 그대로 쓴다 (2026-09-24 실측).

        Args:
            period: "YYYY-MM" 귀속연월.
            pay_date: 지급일.
            commit: False면 항목 연결 확인까지만 하고 [취소] — 저장하지 않는 점검용.
            replace_existing: 같은 지급일에 이미 급여가 있어도 지우고 다시 올린다.
                기본은 멈춘다 (위하고는 확인 한 번으로 기존 급여를 지우고 복구할 수 없다).

        Raises:
            WehagoError: 기존 급여 있음, 수당·공제 미등록, 위하고 사원 미연결,
                저장 후 합계 불일치 등.
        """
        page = self._payroll_page()
        self.step = "조회 조건 입력 (귀속연월·구분·지급일)"
        self._payroll_select_period(page, period, pay_date)
        think("wehago")
        page.locator(_COND_BAR).get_by_role("button", name="조회").click()
        self._wait_for_no_dimmed(page)
        page.wait_for_timeout(1_000)  # 그리드가 조회 결과로 바뀔 시간

        self.step = "기존 급여 확인"
        existing = _grid_total(self._payroll_totals(page))
        if existing and not replace_existing:
            raise WehagoError(
                f"위하고에 이미 입력된 급여자료가 있습니다 (지급일 {pay_date.isoformat()}, "
                f"지급액 계 {existing:,}원) — 덮어쓰지 않음"
            )

        # 이지원천 직원과 위하고 사원이 하나라도 다르면(코드·명단·인원) 입력하지 않는다 (2026-09-27 사용자 결정)
        self.step = "사원 대조"
        mismatch = _employee_mismatch(_excel_employees(xlsx_path), self._payroll_employees(page))
        if mismatch:
            raise WehagoError(mismatch)

        self.step = "엑셀 불러오기"
        allowances = self._payroll_allowances(page)
        expected = _excel_totals(xlsx_path, _nontaxable_limits(allowances))
        prepared = xlsx_path.with_name(f"{xlsx_path.stem}-upload.xlsx")
        try:
            missing = _prepare_upload_xlsx(xlsx_path, prepared, allowances)
            if missing:
                raise WehagoError(f"위하고 비과세 수당 미등록: {', '.join(missing)}")
            dialog = self._payroll_open_upload(page, prepared)
        finally:
            prepared.unlink(missing_ok=True)  # 급여파일은 PC에 남기지 않는다
        self.step = "엑셀 항목 연결 확인"
        mapping = self._payroll_map_headers(dialog)
        unmapped = _unmapped_amount_columns(mapping)
        if unmapped or not commit:
            self._payroll_cancel_upload(page, dialog)
        if unmapped:
            raise WehagoError(f"위하고 수당·공제 미등록: {', '.join(unmapped)}")
        if not commit:
            return f"점검 완료 — 매핑 {sum(1 for m in mapping if m['wehago'])}개 열 (저장 안 함)"

        # 매핑 칸마다 숨은 알림 [확인] 버튼이 있어 보이는 버튼만 고른다
        think("wehago")
        dialog.get_by_role("button", name="확인", exact=True).click()
        self.step = "사원코드 연결·저장"
        self._payroll_convert(page)
        self.step = "저장 후 대조"

        think("wehago")
        page.locator(_COND_BAR).get_by_role("button", name="조회").click()
        self._wait_for_no_dimmed(page)
        page.wait_for_timeout(1_000)
        rows = self._payroll_totals(page)
        got = (_grid_total(rows), _grid_total(rows, nontaxable_only=True))
        if got != (expected.gross, expected.nontaxable):
            raise WehagoError(
                f"위하고에 저장됐으나 대조 불일치 (확인 필요) — 지급액 계 위하고 {got[0]:,} / 이지원천 {expected.gross:,}, "
                f"비과세 위하고 {got[1]:,} / 이지원천 {expected.nontaxable:,}"
            )
        return (
            f"급여자료 입력 완료 ({period}, 지급일 {pay_date.isoformat()}) — {expected.headcount}명, "
            f"지급액 계 {expected.gross:,}원, 비과세 {expected.nontaxable:,}원 대조 일치"
        )

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
        """SmartA 사원등록(SWPM0108) → 추가기능(⋮) → [사원자료 엑셀변환] 다운로드 파일 (§12).

        위하고 T 담당 수임처 → [급여] → SmartA 새 탭 → 사원등록(SWPM0108) 진입까지는
        `_open_smarta_menu`(급여자료입력과 공용, 2026-09-25 실측)로 처리한다.

        캡처 완료된 사실 (2026-09-23):
        - 트리거: 상단 우측 `div.LUX_basic_popover.popover_funtion` (43×32 아이콘)
        - 팝오버 컨테이너: `div.resultbx` (position:absolute, z-index:45)
        - 항목: `dl:has(dt:text-is('엑셀')) dd:text-is('사원자료 엑셀변환')`
        - 다운로드 파일명: `<회사명>_사원등록_<YYYYMMDD>.xlsx` (기본 Downloads 폴더)
        - Playwright download 이벤트가 잡히지 않으므로 폴더 감시 방식으로 수신해야 함

        ⚠️ 팝오버 트리거·다운로드 완료 흐름은 아직 실제 환경에서 끝까지 실행해 보지
        않았다 — 이지원 실기에서 1회 검증 필요 (특히 다운로드 폴더 경로와 파일명
        패턴이 실측 노트북·계정에서 그대로인지).

        Args:
            business_number: 대상 거래처 사업자번호.
            workdir: 다운로드한 파일을 옮겨 둘 작업 폴더 — 호출자가 처리 후 지운다.

        Returns:
            workdir 안으로 옮겨진 엑셀 파일 경로.

        Raises:
            WehagoError: 다운로드가 시간 안에 나타나지 않음.
            CompanyNotFound, CompanyMismatch: 수임처 검색 실패 (`_open_smarta_menu`).
        """
        smarta, name, _number = self._open_smarta_menu(business_number, _EMPLOYEE_REGISTER_MENU_ID)

        self.step = "사원자료 엑셀변환"
        downloads_dir = Path.home() / "Downloads"
        before = set(downloads_dir.glob("*.xlsx"))
        popover = smarta.locator(_MORE_MENU_POPOVER).first
        popover.wait_for(state="visible", timeout=UPLOAD_WAIT_MS)
        think("wehago")
        popover.click()
        popup = smarta.locator(_MORE_MENU_POPUP)
        popup.wait_for(state="visible", timeout=UPLOAD_WAIT_MS)
        item = popup.locator(_EMPLOYEE_EXPORT_ITEM)
        think("wehago")
        item.click()

        deadline = time.monotonic() + UPLOAD_WAIT_MS / 1000
        found: Path | None = None
        while time.monotonic() < deadline:
            candidates = {p for p in downloads_dir.glob(f"{name}_사원등록_*.xlsx") if p not in before}
            if candidates:
                found = max(candidates, key=lambda p: p.stat().st_mtime)
                break
            smarta.wait_for_timeout(500)
        if found is None:
            raise WehagoError(
                f"사원자료 엑셀변환 다운로드를 찾지 못했습니다 ({downloads_dir} 감시 시간 초과)"
            )

        workdir.mkdir(parents=True, exist_ok=True)
        dest = workdir / found.name
        found.replace(dest)
        return dest

    def upload_business_income(
        self, business_number: str, xlsx_path: Path, *, replace_existing: bool = False,
    ) -> str:
        """사업소득자료입력(SWBU0102) → 더보기 → 엑셀서식 불러오기 (§13-3, 2026-09-28 실측).

        급여자료입력과 달리 위하고 자체 엑셀 템플릿을 그대로 채워 올려야 하고
        (`app.services.smarta_business_xls.generate_smarta_business_xls`가 이 양식을
        그대로 만든다), 파일 선택 전에 "불러오기 방법선택"·"소액징수부"를 고르는 옵션
        다이얼로그를 한 번 더 거친다. 완료 메시지가 "마감(완료)월의 데이터는 반영되지
        않습니다"라고 안내하는 것으로 보아, 화면에 조회된 기간이 아니라 **엑셀 각 행의
        지급년월일 기준**으로 처리되는 것으로 보인다 — 그래서 이 메서드는 지급년월 조회를
        하지 않는다 (미확정, 실기 검증 필요. 조회가 필요하다고 판명되면 추가해야 한다).

        캡처 완료된 사실 (2026-09-28):
        - 더보기 버튼 실제 HTML: `<button class="WSC_LUXButton" id="collect">` (급여자료입력과 동일 id)
        - 메뉴 항목: "엑셀서식 불러오기" (기능모음 섹션, 공백 있음)
        - 옵션 다이얼로그: "불러오기 방법선택"(기존 데이터 삭제하고 불러오기 / 기존 데이터
          삭제안하고 추가불러오기) · "소액징수부"(포함/미포함) 라디오 → [엑셀서식불러오기]
          버튼(공백 없음) 클릭 시 OS 파일선택창
        - 완료 팝업: "엑셀 불러오기가 완료되었습니다. ※마감(완료)월의 데이터는 반영되지
          않습니다." + [확인]
        - 형식 오류 시(예: 지급연월일 "2026.9.25"처럼 0 미패딩) 별도 오류 문구가 뜬다 —
          정확한 문구는 미확보, 완료 팝업에 "완료"가 없으면 실패로 간주해 원문을 그대로 회신한다

        ⚠️ 아직 실기에서 끝까지 실행해 보지 않았다 — 특히 더보기 팝업 안에서 항목 텍스트로
        바로 클릭되는지(다른 화면처럼 dl/dt/dd 구조일 수 있음), 라디오 선택이 텍스트 클릭으로
        되는지는 검증 필요.

        Args:
            business_number: 대상 거래처 사업자번호.
            xlsx_path: `generate_smarta_business_xls`로 만든 업로드용 엑셀.
            replace_existing: True면 "기존 데이터 삭제하고 불러오기", False(기본)면
                "기존 데이터 삭제안하고 추가불러오기" — 데이터 손실 방지가 기본값
                (§4-2 `upload_payroll`의 `replace_existing` 원칙과 동일).

        Returns:
            완료 팝업의 원문 메시지.

        Raises:
            WehagoError: 더보기 메뉴·옵션 다이얼로그·파일선택창·완료 팝업 중 하나라도
                예상과 다르거나, 위하고가 입력 오류를 회신함.
            CompanyNotFound, CompanyMismatch: 수임처 검색 실패 (`_open_smarta_menu`).
        """
        smarta, _name, _number = self._open_smarta_menu(business_number, _BUSINESS_INCOME_MENU_ID)

        self.step = "더보기 메뉴 열기"
        more = smarta.locator(_MORE_BUTTON)
        more.wait_for(state="visible", timeout=UPLOAD_WAIT_MS)
        think("wehago")
        more.click()
        think("wehago")
        smarta.get_by_text(_EXCEL_UPLOAD_MENU_ITEM, exact=True).click()

        self.step = "엑셀서식 불러오기 옵션 선택"
        dialog = smarta.locator("div._isDialog:visible", has_text="엑셀서식 불러오기")
        dialog.wait_for(state="visible", timeout=UPLOAD_WAIT_MS)
        option_label = (
            "기존 데이터 삭제하고 불러오기" if replace_existing else "기존 데이터 삭제안하고 추가불러오기"
        )
        think("wehago")
        dialog.get_by_text(option_label, exact=True).click()

        self.step = "엑셀 파일 선택"
        with smarta.expect_file_chooser(timeout=UPLOAD_WAIT_MS) as chooser:
            think("wehago")
            dialog.get_by_role("button", name=_EXCEL_UPLOAD_CONFIRM_BUTTON, exact=True).click()
        chooser.value.set_files(str(xlsx_path))

        self.step = "엑셀 불러오기 완료 대기"
        result = smarta.locator("div._isDialog:visible")
        result.wait_for(state="visible", timeout=UPLOAD_WAIT_MS)
        text = result.inner_text().strip()
        think("wehago")
        result.get_by_role("button", name="확인", exact=True).click()
        if "완료" not in text:
            raise WehagoError(f"사업소득 엑셀서식 불러오기 실패 — 위하고 응답: {text}")
        return text

    # ------------------------------------------------------------------
    # 마감·제작 (§4-4, 2026-09-29 실측 진행 중 — 사용자가 크롬 화면을 직접 보며 셀렉터 제공)
    #
    # 급여자료입력·사원등록·사업소득자료입력과 달리 이 5개 화면(SWTA0101·SWHM0103·SWER0101·
    # SWTA0112·SWER0109)은 SmartA 메인화면의 기본 카테고리("근로소득관리 / 연말정산관리")
    # 밖에 있다. SmartA 메인화면은 열리자마자 "전체메뉴" 탭이 이미 보이는 상태고(별도로
    # 열 필요 없음), 왼쪽 카테고리 목록에서 기본으로 "근로소득관리 / 연말정산관리"가 선택돼
    # 있어 그 안의 급여자료입력 등만 처음부터 `a#{id}.text_link`로 렌더링돼 있다 —
    # `_open_smarta_menu`가 카테고리 전환 없이 바로 성공했던 이유. 마감·제작 화면은
    # "세무신고관리 / 전자신고 / AI원천세" 카테고리 라벨을 먼저 클릭해야 해당 앵커가
    # DOM에 나타난다 (`_open_closing_menu` 참고, 2026-09-29 실측 확정).
    #
    # 원천징수이행상황신고서(SWTA0101) 전체 플로우 실측 확정 (2026-09-29, 서도 더미 수임처
    # 2026년 1월 원천세로 끝까지 실행 검증됨):
    # 1. 조회 조건은 귀속기간·지급기간 각각 년/월 4칸을 모두 채워야 한다. 하나라도 비면
    #    "조회조건에 누락되거나 잘못된 내역이 있습니다" 알럿(div, [확인] 버튼)이 뜬다.
    # 2. [조회] 성공 후에만 타이틀바에 텍스트 버튼 [마감]·[불러오기]·[저장]·[역추적 검증]이
    #    나타난다 (아이콘이 아니라 `<button class="WSC_LUXButton"><span>마감</span></button>`,
    #    id 없음 — role/name으로 찾는다).
    # 3. [마감] 클릭 → "원천징수 신고" 제목의 면책 안내 모달, [취소(esc)]/[확인(enter)].
    # 4. [확인] 클릭 → ✅ 아이콘 + "마감 완료!" 텍스트 모달 + [확인] 버튼.
    # 5. 완료 후 [마감] 버튼이 [마감해제]로 바뀐다 (재실행 시 이미 마감됐는지 판별 가능).
    #
    # 귀속기간·지급기간 년/월 4칸(`div[tabindex='0']`, class 없음)의 DOM도 실측 완료
    # (`_fill_closing_period` 참고) — 다만 타이핑 커밋 방식(Tab)이 실제로 반영되는지는
    # 아직 끝까지 실행 검증 못함 (이번 실측 때는 이미 값이 채워진 상태에서 시작함).
    #
    # 아직 미실측: 데이터가 실제로 있을 때의 그리드·[마감] 응답(이번 실측은 빈 데이터 상태로
    # 확인함), SWTA0112·SWER0109 화면 자체.
    #
    # ⚠️ SWER0101(원천징수 전자신고) [제작(F4)]은 맥에서 지원 안 됨 (2026-09-29 실측 확정) —
    # "맥에서는 제작을 할 수 없다"는 안내가 뜬다 (국세청 암호화 정책상 Windows 전용 모듈이
    # 필요한 것으로 추정, plan/16-wehago-rpa.md §3-5 참고). SWER0109(지방세 전자신고)도
    # 같은 제약일 가능성이 높다 — 둘 다 Windows PC에서만 끝까지 실측·검증 가능하다.
    # ------------------------------------------------------------------

    _WHT_RETURN_MENU_ID = "SWTA0101"
    _BUSINESS_INCOME_REPORT_MENU_ID = "SWHM0103"
    _WHT_EFILE_MENU_ID = "SWER0101"
    _LOCAL_TAX_PAYMENT_MENU_ID = "SWTA0112"
    _LOCAL_TAX_EFILE_MENU_ID = "SWER0109"

    # 메뉴 ID → 전체메뉴 왼쪽 카테고리 라벨 (2026-09-29 실측: SWTA0101·SWHM0103 확정,
    # SWER0101·SWTA0112·SWER0109는 SWTA0101과 같은 "세무신고관리..." 카테고리일 것으로
    # 추정 — plan/16 §4-4 표에서도 넷 다 원천세/지방세 신고 계열이라 같이 묶여 있었다,
    # 실측으로 재확인 필요).
    _CLOSING_MENU_CATEGORY = {
        "SWTA0101": "세무신고관리 / 전자신고 / AI원천세",
        "SWHM0103": "사업소득관리 / 기타(이자 / 배당)소득관리",
        "SWER0101": "세무신고관리 / 전자신고 / AI원천세",
        "SWTA0112": "세무신고관리 / 전자신고 / AI원천세",
        "SWER0109": "세무신고관리 / 전자신고 / AI원천세",
        "SWBU0101": "사업소득관리 / 기타(이자 / 배당)소득관리",  # 사업소득자등록
    }
    _ALL_MENU_BUTTON = "button#allmenu"  # "전체메뉴" 패널을 (다시) 여는 버튼 — 실측: 우측 상단 아이콘

    def _open_closing_menu(self, business_number: str, menu_id: str):
        """담당 수임처 → [급여] → SmartA 메인화면 → 해당 카테고리 → 지정 화면.

        메인화면은 열리자마자 전체메뉴가 보이지만 기본 카테고리가 다르므로, 대상 카테고리
        라벨이 바로 보이지 않으면 `_ALL_MENU_BUTTON`을 눌러 패널을 다시 연 뒤 재시도한다
        (2026-09-29 실측 — 사용자가 실제로 이 버튼을 눌러 진입했다. 매번 눌러도 안전한지,
        즉 이미 열려 있을 때 토글로 닫히지는 않는지는 아직 확인 못해 폴백으로만 쓴다).
        """
        category_text = self._CLOSING_MENU_CATEGORY[menu_id]
        smarta, name, number = self._open_smarta(business_number)
        category = smarta.get_by_text(category_text, exact=True)
        try:
            category.wait_for(state="visible", timeout=5_000)
        except Exception:
            smarta.locator(self._ALL_MENU_BUTTON).click()
            category.wait_for(state="visible", timeout=UPLOAD_WAIT_MS)
        think("wehago")
        category.click()
        menu = smarta.locator(f"a#{menu_id}.text_link")
        menu.wait_for(state="visible", timeout=UPLOAD_WAIT_MS)
        think("wehago")
        menu.click()
        return smarta, name, number

    def _fill_closing_period(self, smarta, item, period: str) -> None:
        """귀속기간·지급기간 공용 — `div.item` 안 연/월 4칸(시작연·시작월·종료연·종료월)을 채운다.

        각 칸은 `<input>`이 아니라 `<div tabindex="0">2026</div>` 형태의 커스텀 위젯이라
        (2026-09-29 실측 DOM — class·id 없이 순서로만 구분됨) 포커스를 주고 바로 타이핑한다.
        시작=종료=`period`로 채운다 (매월 정기신고 기준, 반기 등은 미지원).

        연도 칸은 자체에 width가 있어 비어 있어도 보이지만, 월 칸은 감싸는 부모 div에만
        width가 있고 안쪽 tabindex div는 비어 있으면 크기가 0으로 접혀 "안 보이는" 상태가
        된다 (2026-09-29 실기 재현: 월이 빈 채로 화면을 열면 `.click()`이 "element is not
        visible"로 30초 타임아웃). `.click()` 대신 JS `focus()`로 포커스를 줘서 이 문제를
        피한다 — 크기·가시성과 무관하게 포커스 가능한 요소면 동작한다.
        """
        year, month = period.split("-")
        boxes = item.locator("div[tabindex='0']")
        for i, value in enumerate([year, month, year, month]):
            box = boxes.nth(i)
            if box.inner_text().strip() == value:
                continue
            think("wehago")
            box.evaluate("el => el.focus()")
            smarta.keyboard.type(value)
            smarta.keyboard.press("Tab")

    def close_wht_return(self, business_number: str, period: str) -> str:
        """원천징수이행상황신고서(SWTA0101) 마감 (§4-4 ⑨-a, 2026-09-29 실측).

        Args:
            period: "YYYY-MM" 귀속연월 — 귀속기간·지급기간 모두 이 한 달로 채운다
                (반기 신고 등 기간이 다른 경우는 아직 다루지 않는다).

        Returns:
            "마감 완료!" 등 완료 모달의 원문 텍스트.

        Raises:
            WehagoError: 조회 조건이 잘못됐거나, 마감 확인 모달·완료 모달이 예상과 다름.
        """
        smarta, _name, _number = self._open_closing_menu(business_number, self._WHT_RETURN_MENU_ID)

        self.step = "원천세 조회 조건 입력"
        items = smarta.locator(_COND_BAR).locator("div.item")
        self._fill_closing_period(smarta, items.nth(0), period)  # 귀속기간
        self._fill_closing_period(smarta, items.nth(1), period)  # 지급기간

        think("wehago")
        smarta.get_by_role("button", name="조회", exact=True).click()
        self._wait_for_no_dimmed(smarta)

        # 조회 조건이 누락되면 알럿이 뜬다 — 있으면 즉시 실패로 간주 (재입력 로직은 아직 없음)
        alert = smarta.locator("div:visible", has_text="조회조건에 누락되거나 잘못된 내역이 있습니다")
        if alert.count():
            alert.get_by_role("button", name="확인", exact=True).click()
            raise WehagoError("원천세 조회 조건이 올바르지 않습니다 (귀속기간/지급기간 확인 필요)")

        self.step = "원천세 마감"
        think("wehago")
        smarta.get_by_role("button", name="마감", exact=True).click()

        self.step = "원천세 마감 확인 모달"
        confirm = smarta.locator("div._isDialog:visible", has_text="원천징수 신고")
        confirm.wait_for(state="visible", timeout=UPLOAD_WAIT_MS)
        think("wehago")
        confirm.get_by_role("button", name="확인(enter)", exact=True).click()

        self.step = "원천세 마감 완료 대기"
        result = smarta.locator("div._isDialog:visible", has_text="마감 완료!")
        result.wait_for(state="visible", timeout=UPLOAD_WAIT_MS)
        text = result.inner_text().strip()
        think("wehago")
        result.get_by_role("button", name="확인", exact=True).click()
        if "완료" not in text:
            raise WehagoError(f"원천세 마감 실패 — 위하고 응답: {text}")
        return text

    def close_business_income_report(self, business_number: str, period: str) -> str:
        """거주자사업소득간이지급명세서(SWHM0103) 마감 (§4-4 ⑨-b).

        2026-09-29 Playwright Inspector 녹화로 실측. SWTA0101과 달리 지급기간이 연/월 낱개
        칸이 아니라 "달력 열기" → 팝업에서 월 버튼 클릭 방식이다 (`_payroll_select_period`의
        귀속연월 캘린더와 같은 패턴, 연도는 SmartA 귀속 연도로 고정돼 별도 선택 안 함).

        [마감] → 확인(enter) 모달 다음, 사업소득자료입력과 이 화면 데이터가 안 맞으면
        "오류항목" 모달(표: Code·사원명·오류내용, [강제마감]/[취소(esc)])이 뜬다
        (2026-09-29 실측: 인원수·총지급액 불일치로 실제 발생 확인). §8-1 원칙과 동일하게
        **[강제마감]은 절대 누르지 않는다** — 데이터 정합성 문제는 사람이 사업소득자료입력을
        고친 뒤 다시 시도해야 한다.

        Returns:
            정상 마감 시 완료 팝업의 원문 텍스트.

        Raises:
            WehagoError: "오류항목" 모달이 떴음(§8-1 — 강제마감 금지, 사업소득자료입력 재확인 필요).
        """
        smarta, _name, _number = self._open_closing_menu(
            business_number, self._BUSINESS_INCOME_REPORT_MENU_ID
        )

        self.step = "사업소득 간이지급명세서 조회 조건 입력"
        item = smarta.locator(_COND_BAR).locator("div.item").first
        think("wehago")
        item.get_by_text("달력 열기").click()
        months = smarta.locator("div.date_tbl td.date_day button")
        months.first.wait_for(state="visible", timeout=UPLOAD_WAIT_MS)
        month = int(period.split("-")[1])
        think("wehago")
        months.filter(has_text=re.compile(rf"^{month}월$")).click()

        think("wehago")
        smarta.get_by_role("button", name="조회", exact=True).click()
        self._wait_for_no_dimmed(smarta)

        self.step = "사업소득 마감"
        think("wehago")
        smarta.get_by_role("button", name="마감", exact=True).click()

        self.step = "사업소득 마감 확인 모달"
        confirm = smarta.get_by_role("button", name="확인(enter)", exact=True)
        confirm.wait_for(state="visible", timeout=UPLOAD_WAIT_MS)
        think("wehago")
        confirm.click()

        self.step = "사업소득 마감 결과 확인"
        from playwright.sync_api import TimeoutError as PlaywrightTimeout

        error_dialog = smarta.locator("div._isDialog:visible", has_text="오류항목")
        try:
            error_dialog.wait_for(state="visible", timeout=5_000)
        except PlaywrightTimeout:
            error_dialog = None
        if error_dialog is not None:
            # §8-1 원칙: 데이터 정합성 오류는 강제마감 금지, 취소하고 실패로 회신한다.
            rows = error_dialog.locator("table tr").all_inner_texts()
            think("wehago")
            error_dialog.get_by_role("button", name="취소(esc)", exact=True).click()
            raise WehagoError(
                "사업소득 간이지급명세서 마감 오류 (강제마감 금지 — 사업소득자료입력 재확인 필요): "
                + " / ".join(r.strip() for r in rows if r.strip())
            )

        # TODO 실측: 오류 없이 정상 마감됐을 때 완료 팝업의 정확한 문구·구조 — 이번 실측은
        # 오류 케이스만 확인했다 (사업소득자료입력과 데이터가 맞는 거래처로 재검증 필요).
        result = smarta.locator("div._isDialog:visible", has_text="완료")
        result.wait_for(state="visible", timeout=UPLOAD_WAIT_MS)
        text = result.inner_text().strip()
        think("wehago")
        result.get_by_role("button", name="확인", exact=True).click()
        return text

    # ------------------------------------------------------------------
    # 소득자등록 (§4-4 확장 — 사업/기타/일용소득 자동화, 2026-09-29 실측 진행 중)
    #
    # 사업소득자료입력(SWBU0102, `upload_business_income`)은 이미 엑셀 업로드로 구현돼
    # 있지만, 그 전에 위하고에 소득자(사업소득자) 자체가 등록돼 있어야 한다. 이 등록
    # 화면(SWBU0101)은 왼쪽 RealGrid(목록)에서 이름·주민번호·소득구분만 빠르게 입력하면
    # 저장 버튼 없이 바로 반영된다(2026-09-29 실측 확인 — 김태호/770728-1323914로 검증).
    # RealGrid는 캔버스지만 편집 모드에 들어가면 실제 `<input id="Leftgird_line">` 오버레이가
    # 뜨는 구조라 Playwright로 채울 수 있다.
    #
    # ⚠️ 아래 좌표(`position=`)는 실측 세션에서 딱 한 번 관찰된 값을 그대로 옮긴 것이라
    # 화면 크기·스크롤·기존 행 수에 따라 깨질 수 있다 — 급여자료입력 그리드에 쓰는
    # `_REALGRID_SET_CURRENT_JS`(`_gridView.setCurrent`) 방식으로 좌표 없이 셀을 지정하도록
    # 나중에 반드시 바꿔야 한다(이 그리드의 컬럼 필드명을 아직 못 구함 — TODO).
    # 소득구분 코드도움 팝업(`#IncomeGrid`)의 검색/선택 방식도 미확정 — 지금은 이름으로
    # 텍스트 검색되는지, 코드로만 되는지 확인 못했다.
    # ------------------------------------------------------------------

    _BUSINESS_INCOME_REGISTER_MENU_ID = "SWBU0101"

    def register_business_income_earner(
        self, business_number: str, name: str, rrn: str, income_code_label: str,
    ) -> None:
        """사업소득자등록(SWBU0101) — 그리드에 이름·주민번호·소득구분만 입력, 저장 버튼 없음.

        ⚠️ 스켈레톤 — 좌표 기반이라 미검증 상태다 (위 섹션 설명 참고). 실행 전 반드시
        스크린샷으로 확인하고, 실패하면 `_REALGRID_SET_CURRENT_JS` 방식으로 재작성할 것.

        Args:
            income_code_label: 코드도움 팝업(`#IncomeGrid`)에서 찾을 텍스트 (예: "병의원").
                코드(예: "851101")로도 검색되는지는 미확인.
        """
        smarta, _name, _number = self._open_closing_menu(
            business_number, self._BUSINESS_INCOME_REGISTER_MENU_ID
        )

        self.step = "사업소득자 등록 — 이름"
        grid_input = smarta.locator("#Leftgird_line")
        think("wehago")
        grid_input.dblclick(position={"x": 153, "y": 62})  # TODO 실측: 좌표 대신 셀 지정 방식으로
        grid_input.fill(name)
        grid_input.press("Enter")

        self.step = "사업소득자 등록 — 주민번호"
        think("wehago")
        grid_input.dblclick(position={"x": 334, "y": 58})  # TODO 실측: 좌표 대신 셀 지정 방식으로
        grid_input.fill(rrn.replace("-", ""))
        grid_input.press("Enter")

        self.step = "사업소득자 등록 — 소득구분"
        think("wehago")
        grid_input.click(position={"x": 469, "y": 69})  # TODO 실측: 좌표 대신 셀 지정 방식으로
        popup = smarta.locator("#IncomeGrid")
        popup.wait_for(state="visible", timeout=UPLOAD_WAIT_MS)
        think("wehago")
        popup.get_by_text(income_code_label, exact=False).first.dblclick()

    _OTHER_INCOME_REGISTER_MENU_ID = "SWEA0101"  # TODO 실측: 실제 메뉴 ID 확인 필요 (추정)

    def register_other_income_earner(
        self, business_number: str, name: str, rrn: str, income_type_label: str,
    ) -> None:
        """기타(이자/배당)소득자등록 — 그리드 id가 `Leftgrid`(오타 아님, 사업소득 화면의
        `Leftgird`와 다름). 등록 결과(2026-09-29 실측, 김태호/770728-1323914)를 보면
        "소득구분" 칸이 "[69]분리과세기타소득"처럼 코드+라벨로 표시되고 칸 옆에 작은
        아이콘(📋)이 붙어 있어 — 사업소득 쪽(`#IncomeGrid` 코드도움 팝업)과 같은 방식일
        가능성이 높다. `#Leftgrid_dropdown`을 단순 `<select>`로 가정한 아래 코드는
        미검증 추정이다 — 실행 전 실제로 눌러서 팝업이 뜨는지 드롭다운이 열리는지
        먼저 확인할 것.

        ⚠️ 스켈레톤 — 좌표 기반, `_REALGRID_SET_CURRENT_JS` 방식으로 재작성 필요.
        등록 중 `#CODEHELP-FTW_ETEMPCD` 코드도움 팝업이 한 번 더 떴는데(담당자 연결로
        추정) 무슨 용도인지, 필수인지 아직 확인 못했다 — 지금은 건드리지 않는다.
        """
        smarta, _name, _number = self._open_closing_menu(
            business_number, self._OTHER_INCOME_REGISTER_MENU_ID
        )

        self.step = "기타소득자 등록 — 이름"
        grid_input = smarta.locator("#Leftgrid_line")
        think("wehago")
        grid_input.dblclick(position={"x": 178, "y": 51})  # TODO 실측: 좌표 대신 셀 지정 방식으로
        grid_input.fill(name)
        grid_input.press("Tab")

        self.step = "기타소득자 등록 — 주민번호"
        think("wehago")
        grid_input.fill(rrn.replace("-", ""))
        grid_input.press("Tab")

        self.step = "기타소득자 등록 — 소득구분"
        # TODO 실측 미확정: select_option은 추정이다. 실제로는 사업소득처럼 코드도움
        # 팝업(#IncomeGrid류)이 뜰 가능성이 높다 — 그 경우 register_business_income_earner의
        # popup.get_by_text(...).dblclick() 패턴으로 바꿔야 한다.
        think("wehago")
        smarta.locator("#Leftgrid_dropdown").select_option(label=income_type_label)

    _DAILY_WORKER_REGISTER_MENU_ID = "SWPM0109"  # TODO 실측: 실제 메뉴 ID 확인 필요 (추정)

    def register_daily_worker(self, business_number: str, name: str, rrn: str, hired_at: date) -> None:
        """일용직 사원등록 — "근로소득관리 / 연말정산관리" 카테고리, 그리드 id는
        `#Tab1_left_grid_line` (2026-09-28 §12 사원등록/2026-09-29 이 화면 둘 다 "Tab1_left_grid"
        접두어를 씀 — 화면마다 그리드가 여러 개일 때의 공통 명명 규칙으로 보인다).

        등록 결과(2026-09-29 실측, 김태호/770728-1323914)에서 확인된 사실:
        - 그리드에 이름·주민번호만 넣으면 "나이"가 생년월일 기준으로 자동 계산돼 표시된다.
        - 오른쪽 상세 패널이 매우 크다(기본정보·급여정보·4대보험정보·관리항목·부가정보) —
          입사년월일은 기본값(오늘 근처 날짜)이 이미 채워져 있어 원하는 값으로 덮어써야 한다.
        - "급여지급방법"은 코드도움이 아니라 진짜 드롭다운 리스트(0.매일지급/1.일정기간지급).
        - 계좌정보의 예금주는 이름을 넣으면 자동으로 같이 채워진다.

        ⚠️ 스켈레톤 — 좌표 기반, 그리드 컬럼 순서(이름→주민번호)만 확인했고 "나이" 칸
        오른쪽에 더 있을 수 있는 칸(직종 등)은 안 건드렸다. 상세 패널(급여정보·4대보험정보
        등)은 이 메서드가 손대지 않는다 — 필요하면 별도로 채워야 한다.
        """
        smarta, _name, _number = self._open_closing_menu(
            business_number, self._DAILY_WORKER_REGISTER_MENU_ID
        )

        self.step = "일용직 사원등록 — 이름"
        grid_input = smarta.locator("#Tab1_left_grid_line")
        think("wehago")
        grid_input.dblclick(position={"x": 88, "y": 44})  # TODO 실측: 좌표 대신 셀 지정 방식으로
        grid_input.press("Enter")
        grid_input.fill(name)
        grid_input.press("Tab")

        self.step = "일용직 사원등록 — 주민번호"
        think("wehago")
        grid_input.fill(rrn.replace("-", ""))
        grid_input.press("Tab")

        # TODO 실측 미확정: 입사년월일이 오른쪽 상세 패널에 기본값으로 이미 채워져 있어
        # (2026-09-29 관찰: "2026.09.02") 원하는 hired_at 인자로 덮어써야 하는데, 그 입력칸의
        # 정확한 셀렉터를 아직 못 구해 여기서는 손대지 않는다.

    # ---- 내부 헬퍼 ----

    def _payroll_page(self):
        """SmartA 급여자료입력(SWSA0101) 탭 — open_payroll_screen 이 연 탭, 없으면 열려 있는 탭."""
        if self._smarta_page is not None and not self._smarta_page.is_closed():
            self._smarta_page.bring_to_front()
            return self._smarta_page
        for page in self._context.pages:
            if _PAYROLL_SCREEN in page.url:
                page.bring_to_front()
                return page
        raise WehagoError("SmartA 급여자료입력 화면이 열려 있지 않습니다")

    def _payroll_employees(self, page) -> list[tuple[str, str]]:
        """왼쪽 사원 그리드(조회구분 '전체사원_현재') → [(사원코드, 이름)].

        그리드에는 주민번호 열도 있지만 코드·이름만 꺼낸다.
        """
        grid = page.locator(f"#{_EMPLOYEE_GRID}")
        grid.wait_for(state="attached", timeout=UPLOAD_WAIT_MS)
        return [tuple(r) for r in grid.evaluate(_REALGRID_EMPLOYEES_JS)]

    def _payroll_totals(self, page) -> list[dict[str, Any]]:
        """오른쪽 위 [급여항목 합계] 그리드 — 급여가 없으면 빈 목록."""
        grid = page.locator(f"#{_TOTALS_GRID}")
        grid.wait_for(state="attached", timeout=UPLOAD_WAIT_MS)
        rows: list[dict[str, Any]] = grid.evaluate(_REALGRID_ROWS_JS)
        return [{"nm_allow": r.get("nm_allow"), "fg_tax": r.get("fg_tax"), "am_tax": r.get("am_tax")} for r in rows]

    def _payroll_convert(self, page) -> None:
        """엑셀업로드 [확인] 뒤 — 사원코드연결 → 제외 안내 → 기존 급여 삭제 확인 → 변환 끝.

        (2026-09-25 실측) 사원코드연결 표에는 위하고 사원과 연결되지 않은 엑셀 사원이 나온다.
        위하고는 이 사원들을 **빼고** 변환하므로, 한 명이라도 있으면 취소하고 멈춘다.
        """
        link = page.locator("div._isDialog:visible", has_text="사원코드연결")
        link.wait_for(state="visible", timeout=UPLOAD_WAIT_MS)
        exclude = page.locator("div._isDialog:visible", has_text="제외하고 변환됩니다")
        page.wait_for_timeout(1_500)  # 표가 채워질 시간
        if "데이터가 없습니다" not in link.inner_text():
            # 연결 안 된 사원이 있으면 '제외하고 변환' 안내가 뜨지 않는다 (2026-09-27 실측) — 바로 취소
            if exclude.count():
                think("wehago")
                exclude.get_by_role("button", name="취소", exact=True).click()
            think("wehago")
            link.get_by_role("button", name="취소(Esc)").click()
            raise WehagoError(
                "위하고 사원코드연결 화면에 연결되지 않은 사원이 남아 있어 저장하지 않았습니다 "
                "— 이지원천과 위하고의 사원코드·이름을 확인하세요"
            )
        exclude.wait_for(state="visible", timeout=UPLOAD_WAIT_MS)
        think("wehago")
        exclude.get_by_role("button", name="확인", exact=True).click()
        # 같은 지급일의 기존 급여를 지우고 올린다는 확인 — 기존 급여 여부는 조회 직후 이미 확인했다
        overwrite = page.locator("div._isDialog:visible", has_text="삭제후 업로드됩니다")
        overwrite.wait_for(state="visible", timeout=UPLOAD_WAIT_MS)
        think("wehago")
        self.may_have_saved = True  # 이 [확인]부터 위하고 급여가 바뀐다
        overwrite.get_by_role("button", name="확인", exact=True).click()
        page.locator("div._isDialog:visible").first.wait_for(state="hidden", timeout=UPLOAD_WAIT_MS)
        self._wait_for_no_dimmed(page)

    def _payroll_allowances(self, page) -> list[dict[str, Any]]:
        """급여자료입력 가운데 [급여항목] 그리드 → 수임처에 등록된 수당 [{nm_allow, cd_freeref}].

        캔버스(RealGrid)라 DOM으로는 못 읽고, 화면에 이미 받아 둔 그리드 값을 읽는다
        (위하고 서버에 추가 요청 없음). cd_freeref 는 비과세 코드 (식대 P01 등, 과세 수당은 None),
        am_tflimit 는 월 비과세 한도 (식대·육아수당 200,000).
        """
        grid = page.locator(f"#{_ALLOWANCE_GRID}")
        grid.wait_for(state="attached", timeout=UPLOAD_WAIT_MS)
        rows: list[dict[str, Any]] = grid.evaluate(_REALGRID_ROWS_JS)
        return [
            {"nm_allow": r.get("nm_allow"), "cd_freeref": r.get("cd_freeref"), "am_tflimit": r.get("am_tflimit")}
            for r in rows
        ]

    def _payroll_select_period(self, page, period: str, pay_date: date) -> None:
        """귀속연월(달력에서 월 선택) → 구분 → 지급일 입력 → 그때마다 뜨는 팝업 처리.

        귀속연월·지급일을 입력하면 상황에 따라 팝업이 뜬다 (2026-09-24·25 실측):
        - 지급일자가 이미 있는 달: '지급일자' 목록 팝업 (RealGrid) — 기존 지급일 선택 또는 [추가입력]
        - 새 달: '전월데이터를 복사하시겠습니까?' → [아니오] (엑셀로 전체를 올리므로)
        Esc는 쓰지 않는다 — 조회조건 칸에서 Esc를 누르면 값이 지워지고,
        지급일자 팝업에서는 Esc가 [추가입력]이다.
        """
        year, month = period.split("-")
        want_period, want_date = f"{year}.{month}", pay_date.strftime("%Y.%m.%d")
        items = page.locator(_COND_BAR).locator("div.item")
        if _fake_text(items.nth(0)) != want_period:
            # 귀속연월은 키보드 입력이 먹히지 않는 경우가 있어(2026.03 으로 들어감, 2026-09-27 실측)
            # 달력 아이콘 → 월 버튼으로 고른다. 달력의 연도는 SmartA 귀속 연도로 고정.
            think("wehago")
            items.nth(0).locator("div.fakebutton").click()
            months = page.locator("div.date_tbl td.date_day button")
            months.first.wait_for(state="visible", timeout=5_000)
            think("wehago")
            months.filter(has_text=re.compile(rf"^{int(month)}월$")).click()
            self._payroll_handle_popup(page, pay_date)
        if _fake_text(items.nth(1)) != _PAY_KIND:
            # 구분은 한 글자 코드 입력칸 — 새 달은 '1. 급여'로 잡힐 수 있다 (2026-09-27 실측)
            think("wehago")
            items.nth(1).locator("span.fakeinput").click()
            page.keyboard.type(_PAY_KIND[0])
            think("wehago")
            page.keyboard.press("Tab")
            page.wait_for_timeout(500)
            self._payroll_handle_popup(page, pay_date)
        # 팝업에서 [추가입력]을 누르면 지급일 칸이 비어 직접 입력을 기다린다
        for _ in range(2):
            if _fake_text(items.nth(2)) == want_date:
                break
            think("wehago")
            items.nth(2).locator("div.fake_inputbox").click()
            page.keyboard.type(pay_date.strftime("%Y%m%d"))
            think("wehago")
            page.keyboard.press("Enter")
            self._payroll_handle_popup(page, pay_date)
        shown = _fake_text(items.nth(0)), _fake_text(items.nth(1)), _fake_text(items.nth(2))
        if shown != (want_period, _PAY_KIND, want_date):
            raise WehagoError(f"조회조건 입력 실패: 화면 귀속연월·구분·지급일 {shown}")

    def _payroll_handle_popup(self, page, pay_date: date) -> None:
        pay_dates = page.locator("div._isDialog:visible", has_text="지급일자")
        copy_prev = page.locator("div._isDialog:visible", has_text="전월데이터를 복사")
        for _ in range(12):
            if copy_prev.count():
                think("wehago")
                copy_prev.locator("button", has_text="아니오").click()
                return
            if pay_dates.count():
                self._payroll_pick_pay_date(pay_dates.first, pay_date)
                return
            page.wait_for_timeout(250)
        # 팝업 없이 넘어가는 경우

    def _payroll_pick_pay_date(self, dialog, pay_date: date) -> None:
        """지급일자 팝업: 같은 날짜·구분(급+상) 행이 있으면 선택, 없으면 [추가입력].

        이미 금액이 들어간 지급일이면 덮어쓰지 않고 멈춘다 (중복 업로드 방지).
        """
        grid = dialog.locator(".realgrid_z").first
        rows: list[dict[str, Any]] = grid.evaluate(_REALGRID_ROWS_JS)
        wanted = pay_date.isoformat()
        for i, row in enumerate(rows):
            if str(row.get("dt_pay", "")).startswith(wanted) and str(row.get("fg_pay")) == "2":
                if row.get("am_allowpay"):
                    think("wehago")
                    dialog.locator("button", has_text="확인").click()
                    raise WehagoError(
                        f"위하고에 이미 입력된 급여자료가 있습니다 (지급일 {wanted}, "
                        f"{row.get('num')}명) — 덮어쓰지 않음"
                    )
                grid.evaluate(_REALGRID_SET_CURRENT_JS, i)
                think("wehago")
                dialog.locator("button", has_text="확인").click()
                return
        think("wehago")
        dialog.locator("button", has_text="추가입력").click()

    def _payroll_open_upload(self, page, xlsx_path: Path):
        """[엑셀 불러오기] 단축키 Ctrl+U → 파일 선택창을 가로채 파일을 넣는다.

        같은 기능이 오른쪽 위 추가기능 메뉴(button#collect)에도 있지만, 버튼을 누를 때마다
        메뉴가 열리고 닫혀 상태를 알기 어렵다. file input은 이 동작 때 생기므로 미리
        set_input_files 할 수도 없다 (2026-09-25 실측).
        """
        from playwright.sync_api import TimeoutError as PlaywrightTimeout

        # 조회 뒤 사원 그리드(RealGrid)가 포커스를 가져가 단축키를 삼킨다. 조회 데이터가
        # 늦게 오면 blur 뒤에 다시 포커스를 가져가므로 몇 번 반복한다.
        for _ in range(3):
            page.wait_for_timeout(1_000)
            page.evaluate("() => document.activeElement && document.activeElement.blur()")
            think("wehago")
            try:
                with page.expect_file_chooser(timeout=5_000) as chooser:
                    page.keyboard.press("Control+u")
                break
            except PlaywrightTimeout:
                continue
        else:
            raise WehagoError("엑셀 불러오기(Ctrl+U) 파일 선택창이 열리지 않았습니다")
        chooser.value.set_files(str(xlsx_path))
        dialog = page.locator("div._isDialog:visible", has_text="엑셀업로드")
        dialog.wait_for(state="visible", timeout=UPLOAD_WAIT_MS)
        return dialog

    def _payroll_cancel_upload(self, page, dialog) -> None:
        """엑셀업로드 [취소] → '변환이 취소되었습니다.' 알림 [확인]까지 닫는다."""
        think("wehago")
        dialog.get_by_role("button", name="취소", exact=True).click()
        notice = page.locator("div._isDialog:visible", has_text="변환이 취소되었습니다")
        notice.wait_for(state="visible", timeout=5_000)
        think("wehago")
        notice.get_by_role("button", name="확인").click()
        notice.wait_for(state="hidden", timeout=5_000)

    def _payroll_map_headers(self, dialog) -> list[dict[str, Any]]:
        """① 엑셀내역에서 행 번호 1(제목 한 줄)을 제목행으로 지정 → [② 엑셀제목설정] → ③ 매핑 읽기.

        위하고는 **고른 제목 줄 수 = 사원 한 명의 줄 수**로 읽는다. 2단 헤더에서 1·2행을 고르면
        사원 두 줄을 한 명으로 묶어 금액이 밀린다 (2026-09-25 서도 실측 사고). 그래서 올리기 전에
        제목 한 줄 양식으로 바꾸고(_prepare_upload_xlsx) 1행만 고른다.
        행 번호는 누를 때마다 선택이 켜졌다 꺼진다 — 선택되면 제목 칸이 하늘색이 된다.
        위하고는 엑셀 제목과 같은 이름의 사원정보·수당·공제 항목을 자동 연결한다.
        """
        preview = dialog.locator("table.LStbl:not(.rowspan_fix)")
        header = preview.locator("tr").nth(1)
        if header.locator("th, td").nth(1).evaluate(_BG_JS) != _SELECTED_BG:
            think("wehago")
            header.locator("th").first.click()
        if header.locator("th, td").nth(1).evaluate(_BG_JS) != _SELECTED_BG:
            raise WehagoError("엑셀업로드 제목행 선택 실패")
        think("wehago")
        dialog.locator("button", has_text="엑셀제목설정").click()
        dialog.locator("table.LStbl.rowspan_fix .fakeinput", has_text="사원번호").first.wait_for(
            state="visible", timeout=10_000
        )
        return dialog.evaluate(_READ_MAPPING_JS)

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
        search.press_sequentially(normalize_business_number(business_number), delay=key_delay_ms("wehago"))
        think("wehago")
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

    def _wait_for_no_dimmed(self, page=None) -> None:
        """로딩 오버레이(div.dimmed)가 사라질 때까지 대기. 클릭 인터셉트 방지."""
        from playwright.sync_api import TimeoutError as PlaywrightTimeout

        try:
            (page or self._page).locator("div.dimmed:visible").wait_for(
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


def _type_fresh(locator, text: str) -> None:
    """입력칸을 비우고 한 글자씩 친다 (React 입력칸 — fill 은 값이 반영되지 않을 수 있음)."""
    locator.click()
    locator.press("ControlOrMeta+a")
    locator.press("Backspace")
    if locator.input_value():
        locator.fill("")
    locator.press_sequentially(text, delay=key_delay_ms("wehago"))


def _fake_text(item) -> str:
    """위하고 조회조건 칸(fake_inputbox)에 표시된 값."""
    return item.locator("span.fakeinput").first.inner_text().strip()


@dataclass(frozen=True, slots=True)
class _ExcelTotals:
    headcount: int
    gross: int  # 지급액계 합
    nontaxable: int  # 식대·자가운전·육아수당 합


def _excel_employees(path: Path) -> list[tuple[str, str]]:
    """이지원천 업로드 양식의 사원 (사원코드, 이름) — 2단 헤더 아래 A·B열."""
    from openpyxl import load_workbook

    ws = load_workbook(path, read_only=True).active
    out = []
    for row in ws.iter_rows(min_row=_EXCEL_HEADER_ROWS + 1, max_col=2, values_only=True):
        code, name = (str(v).strip() if v is not None else "" for v in row)
        if code:
            out.append((code, name))
    return out


def _employee_mismatch(excel: list[tuple[str, str]], wehago: list[tuple[str, str]]) -> str | None:
    """이지원천 직원(엑셀)과 위하고 사원이 다르면 사용자에게 보낼 설명, 같으면 None.

    사원코드·이름·인원이 모두 같아야 한다. 이름으로 코드를 짐작해 맞추지 않는다 — 다른 사람에게
    급여가 들어가거나 누락된 직원을 놓칠 수 있다 (2026-09-27 사용자 결정).
    """
    by_code = dict(wehago)
    wehago_by_name: dict[str, list[str]] = {}
    for code, name in wehago:
        wehago_by_name.setdefault(name, []).append(code)
    excel_codes = {code for code, _ in excel}

    wrong_code: list[str] = []
    name_differs: list[str] = []
    not_in_wehago: list[str] = []
    for code, name in excel:
        if by_code.get(code) == name:
            continue
        if code in by_code:
            name_differs.append(f"{code}번 이지원천 {name} · 위하고 {by_code[code]}")
        elif name in wehago_by_name:
            wrong_code.append(f"{name}(이지원천 {code} · 위하고 {', '.join(wehago_by_name[name])})")
        else:
            not_in_wehago.append(f"{name}({code})")
    matched_names = {name for code, name in excel if by_code.get(code) == name} | {
        name for code, name in excel if code not in by_code and name in wehago_by_name
    }
    only_wehago = [f"{n}({c})" for c, n in wehago if c not in excel_codes and n not in matched_names]

    parts = []
    if len(excel) != len(wehago):
        parts.append(f"인원: 이지원천 {len(excel)}명 / 위하고 {len(wehago)}명")
    if wrong_code:
        parts.append("사원코드 다름: " + ", ".join(wrong_code))
    if name_differs:
        parts.append("같은 사원코드에 이름이 다름: " + ", ".join(name_differs))
    if not_in_wehago:
        parts.append("위하고에 없음: " + ", ".join(not_in_wehago))
    if only_wehago:
        parts.append("이지원천에 없음(위하고에만 있음): " + ", ".join(only_wehago))
    if not parts:
        return None
    return (
        "이지원천과 위하고 직원 정보가 달라 입력하지 않았습니다 — " + " · ".join(parts)
        + ". 이지원천 직원의 위하고 사원코드와 명단을 위하고와 같게 맞춘 뒤 다시 전송하세요."
    )


def _nontaxable_limits(allowances: list[dict[str, Any]]) -> dict[str, int]:
    """비과세 코드 → 위하고에 등록된 월 비과세 한도 (한도가 없으면 빠짐)."""
    limits: dict[str, int] = {}
    for a in allowances:
        code, limit = a.get("cd_freeref"), a.get("am_tflimit")
        if code and limit:
            limits.setdefault(code, int(limit))
    return limits


def _excel_totals(path: Path, limits: dict[str, int] | None = None) -> _ExcelTotals:
    """이지원천 업로드 양식(2단 헤더)의 인원·지급액계·비과세 합 — 저장 후 위하고 대조 기준.

    위하고는 비과세 수당이 월 한도를 넘으면 넘는 부분을 과세로 나눈다 (식대 250,000 → 비과세
    200,000 + 과세 50,000, 2026-09-25 실측). 그래서 비과세 기대값은 사원별로 한도까지만 센다.
    """
    from openpyxl import load_workbook

    limits = limits or {}
    ws = load_workbook(path, read_only=True).active
    headcount = gross = nontaxable = 0
    for row in ws.iter_rows(min_row=_EXCEL_HEADER_ROWS + 1, values_only=True):
        if not row or row[0] in (None, ""):
            continue
        headcount += 1
        gross += int(row[_col_index("K") - 1] or 0)
        for col, (code, _label) in _NONTAXABLE_COLUMNS.items():
            amount = int(row[_col_index(col) - 1] or 0)
            nontaxable += min(amount, limits[code]) if code in limits else amount
    return _ExcelTotals(headcount, gross, nontaxable)


def _grid_total(rows: list[dict[str, Any]], *, nontaxable_only: bool = False) -> int:
    """[급여항목 합계] 그리드 금액 합. fg_tax '1' 과세, 그 외 비과세 (식대 등 '2')."""
    return sum(
        int(r.get("am_tax") or 0) for r in rows if not nontaxable_only or str(r.get("fg_tax")) != "1"
    )


def _prepare_upload_xlsx(src: Path, dst: Path, allowances: list[dict[str, Any]]) -> list[str]:
    """위하고 [엑셀 불러오기]용 사본 — 제목 한 줄 양식 + 비과세 수당 제목을 위하고 수당명으로.

    1) 제목 한 줄: 2단 병합 헤더를 풀어 사원코드·사원명 등을 2행으로 내리고 1행(수당/공제 묶음)을
       지운다. 위하고는 고른 제목 줄 수를 사원 한 명의 줄 수로 읽기 때문이다 (_payroll_map_headers).
    2) 비과세 수당 제목: 위하고 엑셀업로드는 제목과 같은 이름의 수당만 자동 연결하는데, 수당명은
       사무소가 자유롭게 붙인다 (육아수당 → "보육수당" 등). 비과세 코드는 신고서에 들어가는 값이라
       이름보다 믿을 수 있으므로, 같은 비과세 코드로 등록된 위하고 수당명으로 바꾼다.

    Returns:
        금액이 있는데 위하고에 그 비과세 코드 수당이 없는 항목 — 예: ["육아수당(Q02)"].
        이 경우 dst는 저장하지 않는다 (올리면 그 금액이 빠진다).
    """
    from openpyxl import load_workbook

    names: dict[str, str] = {}
    for a in allowances:
        code = a.get("cd_freeref")
        if code and a.get("nm_allow"):
            names.setdefault(code, a["nm_allow"])  # 같은 코드가 여러 개면 목록 첫 번째
    wb = load_workbook(src)
    ws = wb.active
    missing: list[str] = []
    for col, (code, label) in _NONTAXABLE_COLUMNS.items():
        if code in names:
            ws[f"{col}{_EXCEL_HEADER_ROWS}"] = names[code]
        elif _column_has_amount(ws, col):
            missing.append(f"{label}({code})")
    if missing:
        return missing

    for merged in list(ws.merged_cells.ranges):
        if merged.min_row <= _EXCEL_HEADER_ROWS:
            ws.unmerge_cells(str(merged))
    for col in range(1, ws.max_column + 1):
        if ws.cell(2, col).value in (None, ""):
            ws.cell(2, col).value = ws.cell(1, col).value
    ws.delete_rows(1)
    wb.save(dst)
    return []


def _column_has_amount(ws, col: str) -> bool:
    for (value,) in ws.iter_rows(min_row=_EXCEL_HEADER_ROWS + 1, min_col=_col_index(col),
                                 max_col=_col_index(col), values_only=True):
        if isinstance(value, int | float) and value != 0:
            return True
    return False


def _col_index(col: str) -> int:
    return ord(col) - ord("A") + 1


def _unmapped_amount_columns(mapping: list[dict[str, Any]]) -> list[str]:
    """위하고 항목에 연결되지 않아 문제가 되는 엑셀 열.

    사원코드·사원명은 위하고 필수값이고, 금액이 있는 열은 그대로 올리면 그 금액이 빠진다.
    """
    return [
        m["excel"]
        for m in mapping
        if not m["wehago"]
        and (
            m["excel"] in _REQUIRED_COLUMNS
            or (m["has_amount"] and m["excel"] not in _TOTAL_COLUMNS)
        )
    ]


def _js_string(value: str) -> str:
    """Playwright 텍스트 셀렉터에 넣을 JS 문자열 리터럴로 인용."""
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'
