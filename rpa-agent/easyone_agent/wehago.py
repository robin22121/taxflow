"""위하고T 화면 조작 — 노트북에 미리 띄워 둔 크롬에 CDP로 붙어 급여자료 엑셀을 올린다.

크롬은 `rpa-agent/scripts/start-chrome.ps1`(Windows) / `start-chrome.sh`(macOS)이
원격 디버깅 포트를 열어 실행하고, 에이전트는 `connect_over_cdp`로만 붙는다
(에이전트가 브라우저 프로세스를 관리하지 않는다).

로그인·수임처 목록·수임처정보 화면은 2026-09-23 실측(§9-2 후속)으로 셀렉터를 확정했다.
급여자료입력 · SmartA 사원자료 엑셀변환 화면은 추가 실측 필요 (NotImplementedError).
"""

from __future__ import annotations

import re
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
_COND_BAR = "div.basic_condition"  # div.item 순서: 귀속연월·구분·지급일·지급일 코드도움·정렬
# 합계 열은 위하고가 다시 계산하므로 연결하지 않아도 된다
_TOTAL_COLUMNS = {"지급액계", "공제액계", "차인지급액"}
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
        id_input.press_sequentially(self._user_id, delay=key_delay_ms("wehago"))
        think("wehago")
        page.locator("#inputPw").press_sequentially(self._password, delay=key_delay_ms("wehago"))
        think("wehago")
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

    def open_payroll_screen(self, business_number: str, period: str) -> tuple[str, str]:
        """위하고 T 메인 담당 수임처 → [급여] → SmartA 메인 → 급여자료입력 (2026-09-25 실측).

        수임처는 사업자번호(하이픈 없는 10자리)로 검색해 정확히 1건일 때만 연다.
        [급여]는 SmartA 를 새 탭으로 열고, 메뉴의 급여자료입력은 그 탭 안에서 바뀐다.
        오래된 SmartA 탭은 세션이 끊겨 있을 수 있어(`#/login/?type=expired`) 닫고 새로 연다.

        Returns:
            (위하고 상호, 사업자번호) — 호출자가 작업의 거래처와 대조한다.
        """
        page = self._page
        for other in list(self._context.pages):
            if other is not page and "smarta.wehagot.com" in other.url:
                other.close()
        self._smarta_page = None

        page.goto(f"{WEHAGO_URL}/#/main")
        self._dismiss_splash()
        self._wait_for_no_dimmed()
        search = page.locator("input[placeholder*='사업자등록번호']").first
        search.wait_for(state="visible", timeout=SIDEBAR_WAIT_MS)
        search.fill(normalize_business_number(business_number))
        search.press("Enter")
        page.wait_for_timeout(1_000)
        rows = page.locator("li:has(p.company_num)")
        if rows.count() != 1:
            raise CompanyNotFound(
                f"위하고 T 담당 수임처 검색 결과가 정확히 1건이 아닙니다 ({rows.count()}건)"
            )
        row = rows.first
        name = row.locator(".company_name a").first.inner_text().strip()
        number = _clean_business_number(row.locator("p.company_num").inner_text())

        with self._context.expect_page(timeout=UPLOAD_WAIT_MS) as new_tab:
            row.locator("button.btn_quick", has_text=re.compile(r"^급여$")).click()
        smarta = new_tab.value
        smarta.wait_for_load_state()
        menu = smarta.locator(f"a#{_PAYROLL_MENU_ID}.text_link")
        menu.wait_for(state="visible", timeout=UPLOAD_WAIT_MS)
        menu.click()
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
        self._payroll_select_period(page, period, pay_date)
        page.locator(_COND_BAR).get_by_role("button", name="조회").click()
        self._wait_for_no_dimmed(page)
        page.wait_for_timeout(1_000)  # 그리드가 조회 결과로 바뀔 시간

        existing = _grid_total(self._payroll_totals(page))
        if existing and not replace_existing:
            raise WehagoError(
                f"위하고에 이미 입력된 급여자료가 있습니다 (지급일 {pay_date.isoformat()}, "
                f"지급액 계 {existing:,}원) — 덮어쓰지 않음"
            )

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
        mapping = self._payroll_map_headers(dialog)
        unmapped = _unmapped_amount_columns(mapping)
        if unmapped or not commit:
            self._payroll_cancel_upload(page, dialog)
        if unmapped:
            raise WehagoError(f"위하고 수당·공제 미등록: {', '.join(unmapped)}")
        if not commit:
            return f"점검 완료 — 매핑 {sum(1 for m in mapping if m['wehago'])}개 열 (저장 안 함)"

        # 매핑 칸마다 숨은 알림 [확인] 버튼이 있어 보이는 버튼만 고른다
        dialog.get_by_role("button", name="확인", exact=True).click()
        self._payroll_convert(page)

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
        exclude.wait_for(state="visible", timeout=UPLOAD_WAIT_MS)
        if "데이터가 없습니다" not in link.inner_text():
            exclude.get_by_role("button", name="취소", exact=True).click()
            link.get_by_role("button", name="취소(Esc)").click()
            raise WehagoError("위하고 사원과 연결되지 않은 엑셀 사원이 있습니다 (사원코드 확인) — 변환 취소")
        exclude.get_by_role("button", name="확인", exact=True).click()
        # 같은 지급일의 기존 급여를 지우고 올린다는 확인 — 기존 급여 여부는 조회 직후 이미 확인했다
        overwrite = page.locator("div._isDialog:visible", has_text="삭제후 업로드됩니다")
        overwrite.wait_for(state="visible", timeout=UPLOAD_WAIT_MS)
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
        """귀속연월(월만 입력) → 지급일 입력 → 그때마다 뜨는 팝업 처리.

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
            items.nth(0).locator("div.fake_inputbox").click()
            page.keyboard.type(month)
            page.keyboard.press("Enter")
            self._payroll_handle_popup(page, pay_date)
        # 팝업에서 [추가입력]을 누르면 지급일 칸이 비어 직접 입력을 기다린다
        for _ in range(2):
            if _fake_text(items.nth(2)) == want_date:
                break
            items.nth(2).locator("div.fake_inputbox").click()
            page.keyboard.type(pay_date.strftime("%Y%m%d"))
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
                    dialog.locator("button", has_text="확인").click()
                    raise WehagoError(
                        f"위하고에 이미 입력된 급여자료가 있습니다 (지급일 {wanted}, "
                        f"{row.get('num')}명) — 덮어쓰지 않음"
                    )
                grid.evaluate(_REALGRID_SET_CURRENT_JS, i)
                dialog.locator("button", has_text="확인").click()
                return
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
        dialog.get_by_role("button", name="취소", exact=True).click()
        notice = page.locator("div._isDialog:visible", has_text="변환이 취소되었습니다")
        notice.wait_for(state="visible", timeout=5_000)
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
            header.locator("th").first.click()
        if header.locator("th, td").nth(1).evaluate(_BG_JS) != _SELECTED_BG:
            raise WehagoError("엑셀업로드 제목행 선택 실패")
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


def _fake_text(item) -> str:
    """위하고 조회조건 칸(fake_inputbox)에 표시된 값."""
    return item.locator("span.fakeinput").first.inner_text().strip()


@dataclass(frozen=True, slots=True)
class _ExcelTotals:
    headcount: int
    gross: int  # 지급액계 합
    nontaxable: int  # 식대·자가운전·육아수당 합


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
