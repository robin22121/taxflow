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

# SmartA 사업소득자료입력(SWBU0102) → 엑셀서식 불러오기 (§13-3, 2026-09-28·30 실측)
# 기본 카테고리 밖에 있어 카테고리 클릭이 먼저 필요하다 — 메뉴 항목 실제 id는 화면
# 코드가 아니라 내부 생성 숫자라 텍스트로 찾는다 (2026-09-30 Chrome Recorder 녹화 확인).
_BUSINESS_INCOME_CATEGORY = "사업소득관리 / 기타(이자 / 배당)소득관리"
_BUSINESS_INCOME_MENU_LABEL = "사업소득자료입력"
_BUSINESS_INCOME_REPORT_MENU_LABEL = "거주자 사업소득간이지급명세서"  # SWHM0103 — 같은 카테고리, 같은 id 문제
_MORE_BUTTON = "button#collect"  # 더보기(⋮) — 급여자료입력과 같은 id, 실제 HTML로 확인됨
_EXCEL_UPLOAD_MENU_ITEM = "엑셀서식 불러오기"  # 더보기 메뉴 항목 (공백 있음)
_EXCEL_UPLOAD_CONFIRM_BUTTON = "엑셀서식불러오기"  # 옵션 다이얼로그 최종 버튼 (공백 없음 — 항목명과 다름, 실측 확인)

# SmartA 기타소득자료입력(SWET0102) — 같은 "사업소득관리..." 카테고리 (2026-09-30 실측).
# 이 화면은 button#collect 더보기가 없고, 화면 우측 상단 스프라이트 아이콘에 **클릭이 아니라
# 마우스 오버(hover)** 해야 캐스케이드 메뉴("설정/연동/편집/기타/기능모음")가 열린다 — 그 중
# "기능모음 > 엑셀서식 불러오기"가 있다(사용자가 실제 화면 hover 스크린샷으로 확인).
_OTHER_INCOME_MENU_LABEL = "기타소득자료입력"
_HOVER_MENU_ICON = 'span[style*="-129px"][style*="-505px"]'

# SmartA 일용직급여자료입력 (2026-09-30 사용자 Chrome Recorder 녹화 확인)
# 사업소득과 달리 카테고리 클릭 없이 바로 메뉴가 보였다 — 메뉴 링크 실제 id도 내부 생성
# 숫자(예: "444100101000007", 사업소득 카테고리의 "4441002..."와 접두어가 다름)라
# 기본 카테고리("근로소득관리 / 연말정산관리") 안의 서브메뉴로 추정된다. 텍스트로 찾는다.
_DAILY_INCOME_MENU_LABEL = "일용직 급여자료입력"  # 공백 있음 — 실측 텍스트 그대로
_DAILY_INCOME_REPORT_MENU_LABEL = "일용근로소득지급명세"  # SWSA0108, 2026-09-30 Chrome Recorder 녹화
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

# 로그인 직후·화면 진입 시 뜨는 안내 팝업들 — 모두 [닫기] 버튼이 있다
# (2차 인증 안내·노란우산공제 안내 등 서비스 프로모션이 div.LUX_basic_dialog, "DJ Bank"류
# 은행 상품 광고가 div[id^=common_pop_dialog] — 2026-09-30 실기 확인. 후자를 못 닫으면
# 메인화면 "전체" 탭 클릭이 막혀 수임처 검색 자체가 실패한다.
# "WEHAGO 소식" 모음 팝업(div.mainDialog2__main)도 같은 문제 — 2026-09-30 재확인, 이건
# 마지막 DOM상 [닫기] 버튼이 숨겨진 "하루 동안 보지 않기" 바 쪽이라 `_dismiss_splash`가
# 마지막 *보이는* [닫기] 버튼을 고르도록 함께 고쳤다.)
_SPLASH_DIALOG = (
    "div.LUX_basic_dialog:visible, div[id^='common_pop_dialog']:visible, "
    "div.mainDialog2__main:visible, div.mainDialog__item:visible"
)

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

        # 이전 작업이 남긴 탭(SmartA·홈택스 탭, 빈 URL 유령 탭 등)이 있으면 문제를 일으킨다
        # (2026-09-29 실측: 빈 URL 탭이 pages[0]으로 잡혀 "Page.goto: Frame has been detached"
        # 발생 — 위하고 전송·제작 등 새 작업을 시작할 때마다 위하고 T 메인 화면 탭 하나만
        # 남기고 나머지는 전부 닫아 항상 같은 깨끗한 상태에서 시작한다).
        self.step = "이전 작업 탭 정리"
        pages = self._context.pages
        main_page = next((pg for pg in pages if pg.url.startswith(WEHAGO_URL)), None)
        keep = main_page or (pages[0] if pages else self._context.new_page())
        for pg in list(self._context.pages):
            if pg is not keep:
                try:
                    pg.close()
                except Exception:
                    pass
        self._page = keep
        self._page.bring_to_front()
        # 재사용한 탭은 해시 라우팅 SPA라 URL이 같으면 goto만으로는 리액트 상태(검색창에
        # 남은 이전 사업자번호 등)가 안 지워진다 — 강제로 새로고침해 완전히 초기화한다.
        if main_page is not None:
            self._page.reload(wait_until="load")
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

    def _dismiss_splash(self, page=None) -> None:
        """로그인 후·화면 진입 시 뜨는 안내 팝업(2차 인증·노란우산공제·WEHAGO 소식 등)을 모두 닫는다.

        같은 dialog에 [닫기] 버튼이 여러 개인 경우가 있어 보이는 dialog가 없어질 때까지
        **마지막으로 보이는** [닫기] 버튼을 반복 클릭한다 (2차 인증 dialog는 [닫기]·
        [설정하기]·[닫기(X)] 3개 모두 보임 → 마지막). "WEHAGO 소식" 팝업(`mainDialog2__main`)은
        DOM상 마지막 [닫기]가 "하루 동안 보지 않기" 바 쪽인데 숨겨져 있어(2026-09-30 실측)
        DOM 순서 그대로 `.last`를 쓰면 안 보이는 버튼을 눌러 안 닫혔다 — 보이는 것 중
        마지막으로 바꿔 두 경우 다 맞춘다.

        `page`를 안 주면 메인 페이지(`self._page`)를 본다 — SmartA는 별도 탭이라 자기만의
        안내 팝업을 따로 띄울 수 있어(2026-10-02 실기, 급여자료입력 조회조건 입력 중 캘린더
        클릭이 막힘), 그 탭에서 확인하려면 `self._smarta_page`를 넘겨야 한다.
        """
        page = page or self._page
        for _ in range(5):
            dialog = page.locator(_SPLASH_DIALOG).first
            if dialog.count() == 0:
                return
            close_buttons = dialog.locator("button:has-text('닫기')")
            visible = [i for i in range(close_buttons.count()) if close_buttons.nth(i).is_visible()]
            if not visible:
                return  # 보이는 닫기 버튼이 없는 경우는 화면을 조작하지 않는다
            close_buttons.nth(visible[-1]).click(force=True)
            page.wait_for_timeout(400)

    def has_open_dialog(self) -> bool:
        """지금 화면에 `_dismiss_splash`가 못 닫은 안내 팝업이 떠 있는지 — 실패 메시지용.

        클릭·대기가 원인 모를 타임아웃으로 멈췄을 때, 새로 생긴(아직 코드가 모르는) 팝업이
        범인인지 바로 구분할 수 있게 한다 (2026-10-02, §1-5 "두더지잡기" 대응 — 실패 메시지로
        원인 파악 사이클을 줄인다). 페이지가 이미 닫혔거나 확인 중 오류가 나도 실패 메시지
        작성을 막으면 안 되므로 조용히 False를 반환한다.
        """
        try:
            return self._page.locator(_SPLASH_DIALOG).first.is_visible()
        except Exception:
            return False

    @staticmethod
    def _skip_if_already_finalized(page, active_label: str, undo_label: str) -> str | None:
        """조회 직후 이미 완료(마감) 처리된 화면인지 확인 — 맞으면 건드리지 않고 건너뛴다.

        위하고는 완료·마감 화면마다 "완료"/"마감" 버튼이 이미 처리된 상태에서는
        "완료해제"/"마감해제"로 바뀐다. 이 상태를 모르고 그대로 업로드·마감을 진행하면
        이미 확정된 자료 위에 덮어쓰거나(§4-2 "replace_existing" 원칙과 충돌), 정규식으로
        느슨하게 버튼을 찾다가 의도치 않게 [마감해제]를 눌러 이미 끝난 신고를 되돌릴
        위험이 있다(2026-10-02 close_local_tax_payment에서 발견). 그래서 작업을 시작하기
        전에 반드시 먼저 확인한다 — 사용자 요청(2026-10-02): "자료입력 화면에 접근하자마자
        완료/마감 여부를 확인해서, 이미 처리됐으면 더 진행하지 않고 바로 스킵·다음 작업으로".

        버튼이 아직 안 그려졌을 때 섣불리 "없다"고 판단하지 않도록(close_wht_return에서
        발견된 렌더링 타이밍 문제) active_label을 포함하는 버튼이 뜰 때까지 먼저 기다린다.

        이 대기 자체가 타임아웃나면(2026-10-02 실패 사례) 화면이 완전히 멈춘 것일 수도 있지만,
        이미 처리된 화면이라 버튼 렌더링이 늦어 걸리는 경우도 있었다 — 포기하기 전에 "해제" 버튼이
        떠 있는지 한 번 더 가볍게 확인해, 있으면 원인 불명의 TimeoutError 대신 "이미 처리된 건이
        있다"는 바로 알아볼 수 있는 안내로 바꾼다 (사용자 요청, 2026-10-02).

        Returns:
            이미 처리돼 있으면 건너뜀 안내 메시지(성공으로 회신해 다음 작업을 막지 않는다),
            아직이면 None — 호출자가 평소대로 진행한다.

        Raises:
            WehagoError: 대기 중 타임아웃났는데 "해제" 버튼은 이미 떠 있는 경우 — 진짜로
                이미 처리된 건이 있다는 뜻이라 일반 TimeoutError 대신 사람이 읽을 메시지로 바꾼다.
        """
        from playwright.sync_api import TimeoutError as PlaywrightTimeout

        try:
            page.locator("button", has_text=re.compile(re.escape(active_label))).first.wait_for(
                state="visible", timeout=UPLOAD_WAIT_MS
            )
        except PlaywrightTimeout:
            if page.get_by_role("button", name=undo_label, exact=True).count():
                raise WehagoError(
                    f"위하고 T에 {active_label} 처리된 건이 이미 있습니다. 확인하세요 "
                    f"(다시 입력하려면 위하고에서 [{undo_label}] 후 재시도)."
                ) from None
            raise
        active_btn = page.get_by_role("button", name=active_label, exact=True)
        undo_btn = page.get_by_role("button", name=undo_label, exact=True)
        if undo_btn.count() and not active_btn.count():
            return f"이미 {active_label} 처리되어 있습니다 (건너뜀 — 다시 하려면 위하고에서 [{undo_label}] 후 재시도)"
        return None

    @staticmethod
    def _dismiss_notice(page) -> None:
        """SmartA 메뉴에 처음 들어갈 때 가끔 뜨는 1회성 공지(예: "국민연금 기준소득월액
        상/하한액 변경 안내")를 닫는다 (2026-09-29 실측 — 신규 등록한 거래처의 급여자료입력
        화면에서 처음 발견).

        `_dismiss_splash`(로그인 splash, [닫기] 버튼)와 달리 이 공지는 [확인] 버튼을 쓰고
        발생 맥락도 다르다. 진짜 공지인지 판별하려고 "다음부터 이 창을 띄우지 않음" 체크박스
        문구가 있는 팝업만 대상으로 삼는다 — 마감 완료 등 업무상 중요한 확인 다이얼로그를
        잘못 닫지 않기 위해서다.
        """
        # div:visible has_text는 조상 div까지 다 걸려(2026-09-29 실기: 22개) 어떤 게 실제
        # 보이는 버튼인지 알 수 없다 — get_by_role은 접근성 이름으로 바로 유일한 버튼을 찾는다.
        if page.locator("div:visible", has_text="다음부터 이 창을 띄우지 않음").count() == 0:
            return
        confirm = page.get_by_role("button", name="확인", exact=True)
        if confirm.count() and confirm.first.is_visible():
            confirm.first.click()
            page.wait_for_timeout(300)

    def _click_dismissing_notice(self, page, locator) -> None:
        """공지 팝업이 뜨는 타이밍이 애매해(사전 dismiss 이후에도 뜬 적 있음, 2026-09-29)
        클릭이 막히면(타임아웃) 한 번 닫고 재시도한다."""
        from playwright.sync_api import TimeoutError as PlaywrightTimeout

        try:
            locator.click(timeout=10_000)
        except PlaywrightTimeout:
            self._dismiss_notice(page)
            locator.click(timeout=UPLOAD_WAIT_MS)

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
        # 2차 인증 안내 등 일부 팝업은 메인화면 진입 직후가 아니라 약간 늦게(애니메이션 등으로)
        # 뜬다 — 위 첫 _dismiss_splash() 체크 시점엔 아직 없어서 못 닫고 넘어갈 수 있다
        # (2026-10-02 실기 확인, "2차 인증을 설정해 보세요" 팝업이 검색을 막음). 검색 직전에
        # 한 번 더 확인한다.
        self._dismiss_splash()
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
        self._dismiss_notice(smarta)
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
        self._ensure_data_entry_unlocked(page)

        self.step = "완료 여부 확인"
        already = self._skip_if_already_finalized(page, "완료", "완료해제")
        if already is not None:
            return already

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

        # 변환 후에도 화면 상단 [완료] 버튼을 눌러야 확정된다 — 안 누르면 그리드 자체에는
        # 보여도 다른 메뉴(원천세 마감 조회 등)에서 이 급여자료를 찾지 못한다
        # (2026-09-30, 사용자가 위하고 화면에서 직접 확인해 알려준 버튼 — WSC_LUXButton, "완료").
        # [완료] 클릭 뒤 "현재 입력하는 급여등을 완료하시겠습니까?" 확인 다이얼로그가 한 번 더
        # 뜬다(2026-09-30 사용자 스크린샷 실측) — [확인]까지 눌러야 실제로 완료 처리된다.
        self.step = "급여자료 완료 처리"
        think("wehago")
        page.get_by_role("button", name="완료", exact=True).click()
        confirm = page.locator("div._isDialog:visible", has_text="현재 입력하는 급여등을 완료하시겠습니까?")
        confirm.wait_for(state="visible", timeout=UPLOAD_WAIT_MS)
        think("wehago")
        confirm.get_by_role("button", name="확인", exact=True).click()
        self._wait_for_no_dimmed(page)

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
        """수임처정보 [기본정보] 탭 — 상호·사업자번호·대표자·업태/업종·사업장 주소·전화번호·
        관할세무서("수임기업 담당세무서", 2026-09-30 추가 — 지방세 신고 등에 쓰임).

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

    def open_business_income_screen(self, business_number: str) -> tuple[str, str]:
        """수임처 → SmartA 사업소득자료입력(SWBU0102) 진입 (§13-3, 2026-09-30 실측 확정).

        급여자료입력과 달리 기본 카테고리("근로소득관리 / 연말정산관리") 밖에 있다 —
        "사업소득관리 / 기타(이자 / 배당)소득관리" 카테고리를 먼저 클릭해야 오른쪽에
        서브메뉴 목록(`div.right_menu`)이 새로 뜨고, 그 안에서 "사업소득자료입력"을
        클릭해야 화면이 열린다. 이 서브메뉴 항목의 실제 id는 화면 코드(SWBU0102)가
        아니라 내부 생성 숫자(예: "444100202000004")라 `a#{code}.text_link`로는 못
        찾는다 — 텍스트로 찾는다(사용자 Chrome Recorder 녹화로 확인, 2026-09-30).

        Returns:
            (위하고 상호, 사업자번호) — 호출자가 작업의 거래처와 대조한다 (`open_payroll_screen`과
            동일한 안전장치, §4-2).
        """
        smarta, name, number = self._open_smarta(business_number)
        self._smarta_page = smarta
        self._open_business_category_menu(smarta, _BUSINESS_INCOME_MENU_LABEL)
        return name, number

    def _open_business_category_menu(self, smarta, menu_label: str) -> None:
        """"사업소득관리 / 기타(이자 / 배당)소득관리" 카테고리 안의 화면 진입 공통 로직.

        이 카테고리의 서브메뉴(`div.right_menu`) 항목은 화면 코드가 아니라 내부 생성
        숫자 id를 쓴다(예: "444100202000004") — `a#{code}.text_link`로는 못 찾아 텍스트로
        찾는다(사용자 Chrome Recorder 녹화로 확인, 2026-09-30). `_open_closing_menu`의
        id 기반 방식은 이 카테고리엔 안 맞는다 — SWBU0102·SWHM0103 둘 다 같은 문제였다.
        """
        self.step = f"사업소득관리 카테고리 열기 ({menu_label})"
        category = smarta.get_by_text(_BUSINESS_INCOME_CATEGORY, exact=True)
        try:
            category.wait_for(state="visible", timeout=5_000)
        except Exception:
            smarta.locator(self._ALL_MENU_BUTTON).click()
            category.wait_for(state="visible", timeout=UPLOAD_WAIT_MS)
        think("wehago")
        category.click()
        self.step = f"{menu_label} 메뉴 클릭"
        menu = smarta.get_by_text(menu_label, exact=True)
        menu.wait_for(state="visible", timeout=UPLOAD_WAIT_MS)
        think("wehago")
        menu.click()
        self._dismiss_notice(smarta)

    def _business_income_page(self):
        """SmartA 사업소득자료입력(SWBU0102) 탭 — open_business_income_screen 이 연 탭."""
        if self._smarta_page is None or self._smarta_page.is_closed():
            raise WehagoError("사업소득자료입력 화면이 열려 있지 않습니다 (open_business_income_screen 먼저 호출)")
        self._smarta_page.bring_to_front()
        return self._smarta_page

    def _business_income_select_period(self, page, period: str) -> None:
        """지급년월(달력에서 월 선택) → 구분("0. 전체" 확정) → [조회] (2026-09-30 실측 확정).

        사용자 Chrome Recorder 녹화 + 실기 실행으로 확인 — 엑셀서식 불러오기 전에 반드시
        필요한 선행 단계다(이전 추정과 달리 조회 없이는 처리되지 않는다). 연월 입력칸
        자체는 건드리지 않고 달력 아이콘(`div.fakebutton`)만 클릭해 팝업을 연다 —
        `_payroll_select_period`와 완전히 같은 위젯(`div.date_tbl td.date_day button`).
        연도 이동은 실측된 적 없어 SmartA 귀속 연도와 다른 연도로 조회해야 하는 경우는
        아직 지원하지 않는다.
        """
        self.step = "지급년월 입력"
        year, month = period.split("-")
        want_period = f"{year}.{month}"
        items = page.locator("#SearchMain").locator("div.item")
        if _fake_text(items.nth(0)) != want_period:
            # 연월 입력칸(fake_inputbox) 자체는 건드리지 않는다 — 달력 아이콘(fakebutton)만
            # 클릭해 팝업을 연 뒤 월 버튼을 고른다 (`_payroll_select_period`와 동일 패턴,
            # 2026-09-30 사용자 확인).
            # ⚠️ 이 필드는 fake_inputbox·fakebutton이 DOM에 중복 렌더링된다(2026-10-01
            # 실기 HTML로 확인 — 같은 div.item 안에 fakebutton이 2개). .first 없이
            # 클릭하면 어느 걸 눌러야 할지 모호해 클릭이 씹히고(화면 변화 없음) 이후
            # 달력 팝업 대기에서 타임아웃났다.
            think("wehago")
            items.nth(0).locator("div.fakebutton").first.click()
            months = page.locator("div.date_tbl td.date_day button")
            months.first.wait_for(state="visible", timeout=5_000)
            think("wehago")
            months.filter(has_text=re.compile(rf"^{int(month)}월$")).click()

        self.step = "구분 확인"
        if _fake_text(items.nth(1)) != "0. 전체":
            think("wehago")
            items.nth(1).locator("span.fakeinput").click()
            page.keyboard.type("0")
            think("wehago")
            page.keyboard.press("Tab")

        self.step = "조회"
        think("wehago")
        page.locator("#SearchMain").get_by_role("button", name="조회", exact=True).click()
        self._wait_for_no_dimmed(page)

    def upload_business_income(
        self, period: str, xlsx_path: Path, *, replace_existing: bool = False,
    ) -> str:
        """사업소득자료입력(SWBU0102) → 지급년월 조회 → 더보기 → 엑셀서식 불러오기 → [완료]
        (§13-3, 2026-09-30 서도 더미 수임처·김태호 1,000,000원 건으로 **실기 검증 완료** —
        소득세 30,000/지방소득세 3,000/차인지급액 967,000까지 화면에서 확인함).

        캡처 완료된 사실:
        - 더보기 버튼 실제 HTML: `<button class="WSC_LUXButton" id="collect">` (급여자료입력과 동일 id)
        - 메뉴 항목: "엑셀서식 불러오기" (기능모음 섹션, 공백 있음)
        - 옵션 다이얼로그: "불러오기 방법선택"(기존 데이터 삭제하고 불러오기 / 기존 데이터
          삭제안하고 추가불러오기) · "소액징수부"(포함/미포함) 라디오 → [엑셀서식불러오기]
          버튼(공백 없음) 클릭 시 OS 파일선택창
        - 완료 팝업: "엑셀 불러오기가 완료되었습니다. ※마감(완료)월의 데이터는 반영되지
          않습니다." + [확인]
        - 엑셀 반영 뒤 화면 상단 [완료]까지 눌러야 확정된다 — 안 누르면 그리드엔 보여도
          다른 메뉴(원천세 마감 조회 등)에서 이 자료를 찾지 못한다(급여자료입력과 동일
          패턴). [완료] → "해당 월의 데이터를 완료하시겠습니까?" 확인 다이얼로그 → [확인]
          → "완료되었습니다." 안내 → [확인]. 완료 후 버튼이 [완료 해제]로 바뀐다.
        - 형식 오류 시(예: 지급연월일 "2026.9.25"처럼 0 미패딩) 별도 오류 문구가 뜬다 —
          정확한 문구는 미확보, 완료 팝업에 "완료"가 없으면 실패로 간주해 원문을 그대로 회신한다

        SmartA 사업소득자료입력 탭이 이미 열려 있어야 한다 (`open_business_income_screen` 먼저 호출).

        Args:
            period: "YYYY-MM" 지급년월 — 조회 조건에 입력한다.
            xlsx_path: `generate_smarta_business_xls`로 만든 업로드용 엑셀.
            replace_existing: True면 "기존 데이터 삭제하고 불러오기", False(기본)면
                "기존 데이터 삭제안하고 추가불러오기" — 데이터 손실 방지가 기본값
                (§4-2 `upload_payroll`의 `replace_existing` 원칙과 동일).

        Returns:
            완료 팝업의 원문 메시지.

        Raises:
            WehagoError: 화면이 열려 있지 않거나, 조회·더보기 메뉴·옵션 다이얼로그·파일선택창·
                완료 팝업 중 하나라도 예상과 다르거나, 위하고가 입력 오류를 회신함.
        """
        smarta = self._business_income_page()
        self._business_income_select_period(smarta, period)
        self._ensure_data_entry_unlocked(smarta)

        self.step = "완료 여부 확인"
        already = self._skip_if_already_finalized(smarta, "완료", "완료해제")
        if already is not None:
            return already

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

        # 엑셀만 올리고 끝내면 그리드엔 보여도 다른 메뉴(원천세 마감 조회 등)에서 이 자료를
        # 찾지 못한다 — 급여자료입력과 동일하게 화면 상단 [완료]까지 눌러야 확정된다
        # (2026-09-30 실기 확인: [완료] → "해당 월의 데이터를 완료하시겠습니까?" 확인
        # 다이얼로그 → [확인] → "완료되었습니다." 안내 → [확인]. 완료 후 버튼이
        # [완료 해제]로 바뀐다).
        self.step = "사업소득자료 완료 처리"
        think("wehago")
        smarta.get_by_role("button", name="완료", exact=True).click()
        confirm = smarta.locator("div:visible", has_text="해당 월의 데이터를 완료하시겠습니까?").last
        confirm.wait_for(state="visible", timeout=UPLOAD_WAIT_MS)
        think("wehago")
        smarta.get_by_role("button", name="확인", exact=True).click()
        done = smarta.locator("div:visible", has_text="완료되었습니다").last
        done.wait_for(state="visible", timeout=UPLOAD_WAIT_MS)
        think("wehago")
        smarta.get_by_role("button", name="확인", exact=True).click()
        self._wait_for_no_dimmed(smarta)
        return text

    def open_daily_income_screen(self, business_number: str) -> tuple[str, str]:
        """수임처 → SmartA 일용직급여자료입력 진입 (2026-09-30 Chrome Recorder 녹화 확인).

        사업소득자료입력과 달리 카테고리 클릭 없이 바로 메뉴가 보였다 — 기본 카테고리
        ("근로소득관리 / 연말정산관리") 안의 서브메뉴로 추정된다. 그래도 혹시 카테고리가
        안 보이는 세션 상태를 대비해 `_ALL_MENU_BUTTON` 폴백은 넣어둔다.

        Returns:
            (위하고 상호, 사업자번호) — 호출자가 작업의 거래처와 대조한다 (`open_payroll_screen`과
            동일한 안전장치, §4-2).
        """
        smarta, name, number = self._open_smarta(business_number)
        self._smarta_page = smarta
        self.step = "일용직 급여자료입력 메뉴 클릭"
        menu = smarta.get_by_text(_DAILY_INCOME_MENU_LABEL, exact=True)
        try:
            menu.wait_for(state="visible", timeout=5_000)
        except Exception:
            smarta.locator(self._ALL_MENU_BUTTON).click()
            menu.wait_for(state="visible", timeout=UPLOAD_WAIT_MS)
        think("wehago")
        menu.click()
        self._dismiss_notice(smarta)
        return name, number

    def _daily_income_page(self):
        """SmartA 일용직급여자료입력 탭 — open_daily_income_screen 이 연 탭."""
        if self._smarta_page is None or self._smarta_page.is_closed():
            raise WehagoError("일용직급여자료입력 화면이 열려 있지 않습니다 (open_daily_income_screen 먼저 호출)")
        self._smarta_page.bring_to_front()
        return self._smarta_page

    def _daily_income_select_period(self, page, period: str) -> None:
        """귀속년월 + 지급년월(별도 칸 둘 다 필수) → [조회] (2026-09-30 실기 확인).

        사업소득과 달리 이 화면은 **귀속년월과 지급년월이 별도 칸**이다(조회조건 순서:
        귀속년월 → 지급년월 → 현장 → 부서 → 프로젝트 → 구분). 둘 다 같은 달로 채운다 —
        전월 근무·당월 지급처럼 두 값이 달라야 하는 경우는 아직 지원하지 않는다.

        ⚠️ 한쪽만 "이미 값이 맞으면 스킵"하는 방어 체크를 했더니, 다른 쪽 달력을
        건드리는 동안 이 칸의 표시값이 깨지는 현상을 실기에서 확인했다(원인 미상 —
        두 칸이 같은 달력 팝업 상태를 공유하는 것으로 추정). 그래서 두 칸 다 **매번
        무조건** 달력을 다시 클릭해 채운다 — 연월 입력칸 자체는 건드리지 않고
        `div.fakebutton` 아이콘만 클릭한다(`_business_income_select_period`와 동일 위젯).
        """
        self.step = "귀속년월·지급년월 입력"
        _year, month = period.split("-")
        month_pattern = re.compile(rf"^{int(month)}월$")
        items = page.locator("#SearchMain").locator("div.item")
        for idx in (0, 1):  # 0=귀속년월, 1=지급년월
            field = items.nth(idx)
            think("wehago")
            field.locator("div.fakebutton").click()
            months = page.locator("div.date_tbl td.date_day button")
            months.first.wait_for(state="visible", timeout=5_000)
            think("wehago")
            months.filter(has_text=month_pattern).click()

        self.step = "조회"
        think("wehago")
        page.locator("#SearchMain").get_by_role("button", name="조회", exact=True).click()
        self._wait_for_no_dimmed(page)

    def upload_daily_income(
        self, period: str, xlsx_path: Path, *, replace_existing: bool = False,
    ) -> str:
        """일용직급여자료입력 → 지급년월 조회 → 더보기 → 엑셀서식 불러오기 → [완료].

        ⚠️ **엑셀 업로드 다이얼로그 자체는 실기 녹화가 없다** — 2026-09-30 사용자 녹화는
        수동 그리드 입력(만근공수 아닌 방식)을 보여줬을 뿐이다. 더보기 메뉴에 "엑셀서식
        내려받기/엑셀서식 불러오기"가 있다는 사실만 §13-2에서 이미 확인됐고, 옵션
        다이얼로그·완료 팝업 구조는 사업소득(`upload_business_income`)과 같은 더존
        SmartA 계열이라는 추정으로 그대로 재사용했다. **실행 전 테스트 수임처로 반드시
        검증할 것** — 특히 "소액징수부" 같은 옵션이 이 화면에도 있는지는 미확인.

        `generate_smarta_daily_xls`(만근공수 방식, 일자=99)로 만든 엑셀을 올린다 —
        PayrollEntry.work_days(공수)가 없는 사람은 그 함수가 이미 걸러낸다.

        SmartA 일용직급여자료입력 탭이 이미 열려 있어야 한다 (`open_daily_income_screen` 먼저 호출).

        Args:
            period: "YYYY-MM" 지급년월 — 조회 조건에 입력한다.
            xlsx_path: `generate_smarta_daily_xls`로 만든 업로드용 엑셀.
            replace_existing: True면 "기존 데이터 삭제하고 불러오기", False(기본)면
                "기존 데이터 삭제안하고 추가불러오기" — 사업소득과 같은 기본값 원칙.

        Returns:
            완료 팝업의 원문 메시지.

        Raises:
            WehagoError: 화면이 열려 있지 않거나, 조회·더보기 메뉴·옵션 다이얼로그·파일선택창·
                완료 팝업 중 하나라도 예상과 다르거나, 위하고가 입력 오류를 회신함.
        """
        smarta = self._daily_income_page()
        self._daily_income_select_period(smarta, period)
        self._ensure_data_entry_unlocked(smarta)

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
            raise WehagoError(f"일용소득 엑셀서식 불러오기 실패 — 위하고 응답: {text}")

        # ⚠️ 2026-09-30 실기 확인: 위하고가 위 팝업에서 "완료"(SUCCESS, resultCode S001)를
        # 반환해도 실제로는 근무일수·지급액이 전혀 반영되지 않는 경우가 있었다(만근공수·
        # 일반 일자 방식 모두, 서식 병합 구조를 원본과 동일하게 맞춰도 재현됨 — 원인 미해결,
        # plan/16-wehago-rpa.md §13-2 참고). 팝업 문구만 믿고 [완료] 처리로 넘어가면 빈
        # 데이터를 "완료"로 잠가버리는 조용한 실패가 되므로, 재조회 응답의 근무일수·지급액
        # 필드를 직접 확인해 실제로 반영됐는지 검증한다.
        self.step = "업로드 결과 검증"
        think("wehago")
        with smarta.expect_response(
            lambda r: "swsa0107/salary/page" in r.url and r.request.method == "GET",
            timeout=UPLOAD_WAIT_MS,
        ) as resp_info:
            smarta.get_by_role("button", name="조회", exact=True).click()
        try:
            payload = resp_info.value.json()
        except Exception:
            payload = {}
        left_list = payload.get("left_list") or []

        def _has_data(row: dict) -> bool:
            return row.get("yn_gongsu") == "1" or any(
                float(row.get(key) or 0) != 0
                for key in ("cnt_workday", "sum_dutyall", "am_dapay", "cnt_dapay")
            )

        if not any(_has_data(row) for row in left_list):
            raise WehagoError(
                '엑셀서식 불러오기가 "완료" 응답을 반환했지만 재조회 결과 근무일수·지급액이 '
                "반영되지 않았습니다 — 위하고 쪽 원인 확인이 필요합니다 "
                "(plan/16-wehago-rpa.md §13-2). [완료] 처리를 하지 않고 중단합니다."
            )

        self.step = "일용소득자료 완료 처리"
        think("wehago")
        smarta.get_by_role("button", name="완료", exact=True).click()
        confirm = smarta.locator("div:visible", has_text="완료하시겠습니까").last
        confirm.wait_for(state="visible", timeout=UPLOAD_WAIT_MS)
        think("wehago")
        smarta.get_by_role("button", name="확인", exact=True).click()
        # 사업소득(upload_business_income)과 달리 이 화면은 [확인] 클릭 후 별도의
        # "완료되었습니다." 성공 팝업이 뜨지 않는다 — [완료]가 즉시 [완료해제]로 바뀐다
        # (2026-09-30 실기 확인). 토글 완료를 기다려 성공을 판단한다.
        smarta.get_by_role("button", name="완료해제", exact=True).wait_for(
            state="visible", timeout=UPLOAD_WAIT_MS
        )
        self._wait_for_no_dimmed(smarta)
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
    _WHT_EFILE_MENU_ID = "SWER0101"
    _LOCAL_TAX_PAYMENT_MENU_ID = "SWTA0112"
    _LOCAL_TAX_EFILE_MENU_ID = "SWER0109"

    # 메뉴 ID → 전체메뉴 왼쪽 카테고리 라벨 (2026-09-29 실측: SWTA0101 확정,
    # SWER0101·SWTA0112·SWER0109는 SWTA0101과 같은 "세무신고관리..." 카테고리일 것으로
    # 추정 — plan/16 §4-4 표에서도 넷 다 원천세/지방세 신고 계열이라 같이 묶여 있었다,
    # 실측으로 재확인 필요). "사업소득관리..." 카테고리(SWBU0101·SWBU0102·SWHM0103)는
    # 이 id 기반 방식이 안 맞아(서브메뉴 항목이 내부 생성 숫자 id) 여기 넣지 않는다 —
    # `_open_business_category_menu`(텍스트 기반)를 대신 쓴다 (2026-09-30 확인).
    _CLOSING_MENU_CATEGORY = {
        "SWTA0101": "세무신고관리 / 전자신고 / AI원천세",
        "SWER0101": "세무신고관리 / 전자신고 / AI원천세",
        "SWTA0112": "세무신고관리 / 전자신고 / AI원천세",
        "SWER0109": "세무신고관리 / 전자신고 / AI원천세",
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
        # open_payroll_screen과 동일 — 실패 시 save_failure_screenshot이 이 탭을 캡처하게 한다
        # (2026-09-30: 이걸 빠뜨려서 마감 실패 스크린샷이 엉뚱한 메인 탭을 찍은 버그 발견).
        self._smarta_page = smarta
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
        self._dismiss_notice(smarta)
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

        # 신고구분(정기/기한후) — 기한(다음달 10일) 지나서 신고하면 기한후신고로 조회해야
        # 소득세 등 계산값이 나온다(정기신고로 조회하면 지급액만 보이고 소득세가 빈칸).
        # items.nth(2) — 귀속기간(0)·지급기간(1) 다음 칸. 이 칸에서 Enter를 누르면 그 자체가
        # [조회]를 겸한다(2026-09-30 사용자 실측) — 그래서 별도로 [조회] 버튼을 누르지 않는다.
        # Tab으로는 선택이 확정되지 않고 정기신고로 되돌아간다 — 반드시 Enter.
        self.step = "원천세 신고구분 확인"
        report_type = items.nth(2)
        code = _report_type_code(period)
        think("wehago")
        report_type.locator("span.fakeinput").click()
        if _fake_text(report_type).split(".", 1)[0].strip() != code:
            smarta.keyboard.type(code)
        think("wehago")
        smarta.keyboard.press("Enter")

        # 위 Enter가 조회를 겸하면서 "저장된 데이터를 불러오시겠습니까?" 확인창이 뜬다
        # (이전에 이 신고서를 열었던 임시저장이 있을 때) — 항상 최신 급여자료를 반영해야
        # 하므로 [취소](새로불러오기)를 누른다.
        from playwright.sync_api import TimeoutError as PlaywrightTimeout

        self.step = "원천세 저장된 데이터 확인"
        saved_prompt = smarta.locator("div._isDialog:visible", has_text="저장된 데이터를 불러오시겠습니까")
        try:
            saved_prompt.wait_for(state="visible", timeout=5_000)
        except PlaywrightTimeout:
            pass
        else:
            think("wehago")
            saved_prompt.get_by_role("button", name="취소", exact=True).click()

        self._wait_for_no_dimmed(smarta)

        # 조회 조건이 누락되면 알럿이 뜬다 — 있으면 즉시 실패로 간주 (재입력 로직은 아직 없음)
        alert = smarta.locator("div:visible", has_text="조회조건에 누락되거나 잘못된 내역이 있습니다")
        if alert.count():
            alert.get_by_role("button", name="확인", exact=True).click()
            raise WehagoError("원천세 조회 조건이 올바르지 않습니다 (귀속기간/지급기간 확인 필요)")

        self.step = "원천세 마감 여부 확인"
        # 이미 마감된 신고서는 [마감] 대신 [마감해제] 버튼으로 바뀐다(2026-09-29 문서화,
        # 2026-09-30 실측 재현) — 다른 마감·완료 화면과 같은 공용 헬퍼로 통일한다
        # (렌더링 타이밍 보호 포함, 2026-10-02).
        already = self._skip_if_already_finalized(smarta, "마감", "마감해제")
        if already is not None:
            return already

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

    def open_other_income_screen(self, business_number: str) -> tuple[str, str]:
        """수임처 → SmartA 기타소득자료입력(SWET0102) 진입 (2026-09-30 실측).

        사업소득(SWBU0102)과 같은 "사업소득관리 / 기타(이자 / 배당)소득관리" 카테고리라
        `_open_business_category_menu`를 그대로 재사용한다.

        Returns:
            (위하고 상호, 사업자번호) — 호출자가 작업의 거래처와 대조한다.
        """
        smarta, name, number = self._open_smarta(business_number)
        self._smarta_page = smarta
        self._open_business_category_menu(smarta, _OTHER_INCOME_MENU_LABEL)
        return name, number

    def _other_income_page(self):
        """SmartA 기타소득자료입력 탭 — open_other_income_screen 이 연 탭."""
        if self._smarta_page is None or self._smarta_page.is_closed():
            raise WehagoError("기타소득자료입력 화면이 열려 있지 않습니다 (open_other_income_screen 먼저 호출)")
        self._smarta_page.bring_to_front()
        return self._smarta_page

    def _other_income_select_period(self, page, period: str) -> None:
        """지급년월(단일 필드) → [조회] (2026-09-30 실측).

        조회조건이 지급년월 하나뿐이다(`#SearchMain` item 1개) — 사업소득(`_COND_BAR`,
        div.fakebutton 위젯)과 달리 일용근로소득지급명세(SWSA0108)와 같은
        `div.fake_inputbox > div > span` 위젯을 쓴다.
        """
        self.step = "지급년월 입력"
        item = page.locator("#SearchMain").locator("div.item").first
        think("wehago")
        item.locator("div.fake_inputbox > div > span").first.click()
        months = page.locator("div.date_tbl td.date_day button")
        months.first.wait_for(state="visible", timeout=UPLOAD_WAIT_MS)
        month = int(period.split("-")[1])
        think("wehago")
        months.filter(has_text=re.compile(rf"^{month}월$")).click()
        think("wehago")
        page.locator("#SearchMain").get_by_role("button", name="조회", exact=True).click()
        self._wait_for_no_dimmed(page)

    def upload_other_income(
        self, period: str, xlsx_path: Path, *, replace_existing: bool = False,
    ) -> str:
        """기타소득자료입력(SWET0102) → 지급년월 조회 → 엑셀서식 불러오기 (2026-09-30 실측).

        ⚠️ **엑셀 업로드 옵션 다이얼로그까지만 실기 확인됨** — 실제 파일 업로드·완료 처리는
        아직 검증하지 못했다(엑셀 생성기·실제 다운로드 템플릿 미확보). [완료] 버튼 처리
        흐름은 사업소득/일용소득과 같은 패턴으로 추정만 하고 아직 코드에 넣지 않았다 —
        호출자가 화면에서 직접 [완료]까지 눌러야 한다.

        이 화면은 `button#collect` 더보기가 없다 — 화면 우측 상단 스프라이트 아이콘
        (`_HOVER_MENU_ICON`)에 **클릭이 아니라 마우스 오버**해야 "설정/연동/편집/기타/
        기능모음" 캐스케이드 메뉴가 열리고, 그 안 "기능모음 > 엑셀서식 불러오기"를 눌러야
        한다(사용자가 실제 hover 상태 스크린샷으로 확인, 2026-09-30). 옵션 다이얼로그
        자체는 사업소득·일용소득과 완전히 같은 구조("불러오기 방법선택" 라디오 +
        [엑셀서식불러오기]/[취소]).

        SmartA 기타소득자료입력 탭이 이미 열려 있어야 한다 (`open_other_income_screen` 먼저 호출).

        Args:
            period: "YYYY-MM" 지급년월.
            xlsx_path: 업로드용 엑셀 — 이 화면 전용 생성기는 아직 없다.
            replace_existing: True면 "기존 데이터 삭제하고 불러오기", False(기본)면
                "기존 데이터 삭제안하고 추가불러오기".

        Returns:
            완료 팝업의 원문 메시지.

        Raises:
            WehagoError: 화면이 열려 있지 않거나, 조회·hover 메뉴·옵션 다이얼로그·파일선택창·
                완료 팝업 중 하나라도 예상과 다르거나, 위하고가 입력 오류를 회신함.
        """
        smarta = self._other_income_page()
        self._other_income_select_period(smarta, period)
        self._ensure_data_entry_unlocked(smarta)

        self.step = "기능모음 메뉴 열기 (hover)"
        think("wehago")
        smarta.locator(_HOVER_MENU_ICON).first.hover()
        smarta.wait_for_timeout(300)  # 캐스케이드 메뉴 렌더 대기
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
            raise WehagoError(f"기타소득 엑셀서식 불러오기 실패 — 위하고 응답: {text}")
        return text

    def close_business_income_report(self, business_number: str, period: str) -> str:
        """거주자사업소득간이지급명세서(SWHM0103) 새로불러오기 → 마감 (§4-4 ⑨-b).

        2026-09-30 서도·김태호 건으로 **전 구간 실기 검증 완료** (새로불러오기 확인창 →
        마감 확인(enter) 모달 → "마감이 완료되었습니다." 까지 자동 실행 성공).

        2026-09-29 Playwright Inspector 녹화 + 2026-09-30 Chrome Recorder 녹화로 실측.
        SWTA0101과 달리 지급기간이 연/월 낱개 칸이 아니라 "달력 열기" → 팝업에서 월 버튼
        클릭 방식이다 (`_payroll_select_period`의 귀속연월 캘린더와 같은 패턴, 연도는
        SmartA 귀속 연도로 고정돼 별도 선택 안 함). "신고구분"은 기본값 "1. 정기신고"를
        그대로 둔다(§4-8 정기신고만 자동화 원칙과 일치, 2026-09-30 화면 확인).

        화면 진입은 사업소득자료입력(SWBU0102)과 같은 "사업소득관리..." 카테고리라 같은
        id 문제가 있다 — `_open_business_category_menu`로 텍스트 기반 진입한다(기존
        `_open_closing_menu`의 `a#SWHM0103.text_link` 검색은 이 카테고리엔 안 맞는다).

        **[새로불러오기]가 조회 다음·마감 전에 반드시 필요하다** (2026-09-30 사용자
        Chrome Recorder 녹화로 확인 — 이전엔 이 단계가 없어 "마감할 데이터가 존재하지
        않습니다"가 계속 떴을 가능성이 높다). 클릭하면 "OO월 사원 및 사업소득자료입력에
        입력된 소득을 모두 불러 오시겠습니까?" 확인창이 뜨고 [확인]을 눌러야 사업소득
        자료입력(SWBU0102)에 이미 입력된 소득이 이 화면 그리드로 들어온다.

        [마감] → 확인(enter) 모달 다음, 사업소득자료입력과 이 화면 데이터가 안 맞으면
        "오류항목" 모달(표: Code·사원명·오류내용, [강제마감]/[취소(esc)])이 뜬다
        (2026-09-29 실측: 인원수·총지급액 불일치로 실제 발생 확인). §8-1 원칙과 동일하게
        **[강제마감]은 절대 누르지 않는다** — 데이터 정합성 문제는 사람이 사업소득자료입력을
        고친 뒤 다시 시도해야 한다.

        Returns:
            정상 마감 시 완료 팝업의 원문 텍스트. 이미 마감된 달이면(버튼이 [마감해제]로
            바뀐 상태) 새로 마감하지 않고 "이미 마감되어 있습니다 (건너뜀)"을 돌려준다.

        Raises:
            WehagoError: "오류항목" 모달이 떴음(§8-1 — 강제마감 금지, 사업소득자료입력 재확인 필요).
        """
        smarta, _name, _number = self._open_smarta(business_number)
        self._smarta_page = smarta
        self._open_business_category_menu(smarta, _BUSINESS_INCOME_REPORT_MENU_LABEL)

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

        self.step = "사업소득 간이지급명세서 새로불러오기"
        think("wehago")
        smarta.get_by_role("button", name="새로불러오기", exact=True).click()
        reload_confirm = smarta.locator(
            "div._isDialog:visible", has_text="사원 및 사업소득자료입력에 입력된 소득을 모두 불러 오시겠습니까?"
        )
        # 이미 최신 상태(예: 직전에 한 번 불러왔거나 마감 후 재실행)면 확인창 없이 그냥
        # 넘어가는 것으로 보인다(2026-09-30 실기 확인) — 새 데이터가 있을 때만 뜨는 듯.
        try:
            reload_confirm.wait_for(state="visible", timeout=5_000)
        except Exception:
            pass
        else:
            think("wehago")
            reload_confirm.get_by_role("button", name="확인", exact=True).click()
            self._wait_for_no_dimmed(smarta)

        self.step = "사업소득 마감 여부 확인"
        # 이미 마감된 달은 버튼이 [마감해제]로 바뀐다(재실행 판별용, close_wht_return과 동일
        # 원칙) — 이 경우 새로 마감할 필요 없이 이미 끝난 것으로 간주하고 건너뛴다
        # (2026-09-30 실기 확인: 사용자가 같은 달을 수동으로 먼저 마감해 둔 상태에서 발견).
        # 버튼이 아직 안 그려졌을 때 섣불리 판단하지 않도록 렌더링을 먼저 기다린다
        # (2026-10-02 close_wht_return에서 발견된 동일 타이밍 문제).
        already = self._skip_if_already_finalized(smarta, "마감", "마감해제")
        if already is not None:
            return already
        self.step = "사업소득 마감"
        think("wehago")
        smarta.get_by_role("button", name="마감", exact=True).click()

        from playwright.sync_api import TimeoutError as PlaywrightTimeout

        # 사업소득자료입력에 데이터가 없는 거래처(대부분 — 근로소득만 자동화 대상) — 실패 아님,
        # 건너뛴다 (§4-4 ⑨-b, 2026-09-30 사용자 스크린샷으로 문구·단일 [확인] 버튼 실측 확정).
        # 5초로는 너무 짧아 렌더 지연 때 놓쳤다(같은 사용자 스크린샷) — 확인모달 대기와 같은
        # UPLOAD_WAIT_MS로 늘린다. 대다수 작업이 이 경로라 지연 비용보다 놓치는 게 더 나쁘다.
        no_data = smarta.locator("div:visible", has_text="마감할 데이터가 존재하지 않습니다")
        try:
            no_data.wait_for(state="visible", timeout=UPLOAD_WAIT_MS)
        except PlaywrightTimeout:
            pass
        else:
            think("wehago")
            smarta.get_by_role("button", name="확인", exact=True).click()
            return "마감할 데이터가 존재하지 않습니다 (건너뜀)"

        self.step = "사업소득 마감 확인 모달"
        confirm = smarta.get_by_role("button", name="확인(enter)", exact=True)
        confirm.wait_for(state="visible", timeout=UPLOAD_WAIT_MS)
        think("wehago")
        confirm.click()

        self.step = "사업소득 마감 결과 확인"
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

        # 정상 마감 완료 팝업: "마감이 완료되었습니다." + [확인] (2026-09-30 서도·김태호
        # 건으로 실기 검증 완료 — 새로불러오기까지 포함한 전 구간 자동 실행 성공).
        result = smarta.locator("div._isDialog:visible", has_text="완료")
        result.wait_for(state="visible", timeout=UPLOAD_WAIT_MS)
        text = result.inner_text().strip()
        think("wehago")
        result.get_by_role("button", name="확인", exact=True).click()
        return text

    def close_daily_income_report(self, business_number: str, period: str) -> str:
        """일용근로소득지급명세(SWSA0108) 전체소득 불러오기 → 마감 (2026-09-30 실기 검증).

        사업소득(SWHM0103)과 달리 카테고리 클릭이 필요 없다(`open_daily_income_screen`과
        같은 기본 카테고리). 조회조건도 단일 "지급기간"(`#SearchMain` items 순서:
        구분·지급기간·신고구분·차수) 하나뿐이라 `_business_income_select_period`의
        `_COND_BAR`(div.basic_condition)가 아니라 `#SearchMain`을 쓴다.

        [전체소득 불러오기]는 사업소득의 [새로불러오기]와 같은 역할 — "전체사원의 일용직
        급여자료입력에 입력된 소득을 불러오시겠습니까?" 확인 후 눌러야 일용직급여자료입력
        (SWSA0107)의 [완료]된 데이터가 이 화면 그리드로 들어온다. 안 누르면 조회해도
        "데이터가 없습니다"로 보인다(2026-09-30 실기 확인 — 데이터가 실제로 있는데도).

        [마감] 클릭 시 인원수 확인("N명의 사원을 마감하시겠습니까?") → 법적 고지
        디스클레이머("지급명세서 신고" + [확인(Tab)]) 순서로 진행된다.

        "오류항목" 모달(예: "납세지관할 세무서코드가 비어있습니다" — 회사 등록정보에
        세무서코드가 없을 때, 2026-09-30 실기 확인)이 뜨면 §8-1 원칙대로 **[강제마감]을
        절대 누르지 않는다** — 사용자가 한 번은 이 특정 오류에 한해 강제마감을 지시했으나
        (2026-09-30), 이후 "강제마감 금지, 오류메시지 사용자에게 알릴 것"으로 번복했다
        (같은 날) — 어떤 오류 문구든 강제마감하지 않고 그대로 표면화한다.

        Returns:
            정상 마감 후 완료 팝업의 원문 텍스트, 또는 "이미 마감되어 있습니다"/
            "지급할 데이터가 없습니다" 등 건너뜀 사유.

        Raises:
            WehagoError: "오류항목" 모달이 떴음(강제마감 금지 — 오류 내용을 사용자에게
                그대로 전달하고, 원인(예: 세무서코드 미등록 등 회사 마스터데이터 설정)을
                사용자가 위하고에서 직접 확인·수정한 뒤 재시도해야 한다).
        """
        smarta, _name, _number = self._open_smarta(business_number)
        self._smarta_page = smarta
        self.step = "일용근로소득지급명세 메뉴 클릭"
        menu = smarta.get_by_text(_DAILY_INCOME_REPORT_MENU_LABEL, exact=True)
        try:
            menu.wait_for(state="visible", timeout=5_000)
        except Exception:
            smarta.locator(self._ALL_MENU_BUTTON).click()
            menu.wait_for(state="visible", timeout=UPLOAD_WAIT_MS)
        think("wehago")
        menu.click()
        self._dismiss_notice(smarta)

        self.step = "일용근로소득지급명세 조회 조건 입력"
        items = smarta.locator("#SearchMain").locator("div.item")
        period_item = items.nth(1)  # 0=구분·1=지급기간·2=신고구분·3=차수
        think("wehago")
        # div.fake_inputbox 자체가 아니라 그 안의 span을 클릭해야 달력이 열린다
        # (2026-09-30 실기 확인 — div 전체를 클릭하면 포커스만 잡히고 팝업이 안 뜬다).
        period_item.locator("div.fake_inputbox > div > span").first.click()
        months = smarta.locator("div.date_tbl td.date_day button")
        months.first.wait_for(state="visible", timeout=UPLOAD_WAIT_MS)
        month = int(period.split("-")[1])
        think("wehago")
        months.filter(has_text=re.compile(rf"^{month}월$")).click()
        think("wehago")
        smarta.locator("#SearchMain").get_by_role("button", name="조회", exact=True).click()
        self._wait_for_no_dimmed(smarta)

        self.step = "일용근로소득지급명세 전체소득 불러오기"
        think("wehago")
        smarta.get_by_role("button", name="전체소득 불러오기", exact=True).click()
        reload_confirm = smarta.locator(
            "div._isDialog:visible", has_text="일용직 급여자료입력에 입력된 소득을"
        )
        try:
            reload_confirm.wait_for(state="visible", timeout=5_000)
        except Exception:
            pass
        else:
            think("wehago")
            reload_confirm.get_by_role("button", name="확인", exact=True).click()
            self._wait_for_no_dimmed(smarta)

        self.step = "일용근로소득지급명세 마감"
        if smarta.get_by_role("button", name="마감해제", exact=True).count():
            return "이미 마감되어 있습니다 (건너뜀)"
        think("wehago")
        smarta.get_by_role("button", name="마감", exact=True).click()

        from playwright.sync_api import TimeoutError as PlaywrightTimeout

        no_data = smarta.locator("div:visible", has_text="마감할 데이터가 존재하지 않습니다")
        try:
            no_data.wait_for(state="visible", timeout=UPLOAD_WAIT_MS)
        except PlaywrightTimeout:
            pass
        else:
            think("wehago")
            smarta.get_by_role("button", name="확인", exact=True).click()
            return "마감할 데이터가 존재하지 않습니다 (건너뜀)"

        self.step = "일용근로소득지급명세 마감 인원 확인"
        count_confirm = smarta.locator("div._isDialog:visible", has_text="마감하시겠습니까")
        count_confirm.wait_for(state="visible", timeout=UPLOAD_WAIT_MS)
        think("wehago")
        count_confirm.get_by_role("button", name="확인", exact=True).click()

        self.step = "일용근로소득지급명세 마감 법적고지"
        disclaimer = smarta.locator("div._isDialog:visible", has_text="지급명세서 신고")
        disclaimer.wait_for(state="visible", timeout=UPLOAD_WAIT_MS)
        think("wehago")
        disclaimer.get_by_role("button", name="확인(Tab)", exact=True).click()

        self.step = "일용근로소득지급명세 마감 결과 확인"
        error_dialog = smarta.locator("div._isDialog:visible", has_text="오류항목")
        try:
            error_dialog.wait_for(state="visible", timeout=UPLOAD_WAIT_MS)
        except PlaywrightTimeout:
            error_dialog = None
        if error_dialog is not None:
            # §8-1 원칙: 강제마감 금지 — 오류 내용을 그대로 사용자에게 전달한다
            # (예: "납세지관할 세무서코드가 비어있습니다" — 회사 마스터데이터 설정 문제는
            # 사용자가 위하고에서 직접 등록해야 한다, 2026-09-30 확인 사례).
            rows = [r.strip() for r in error_dialog.locator("table tr").all_inner_texts() if r.strip()]
            think("wehago")
            error_dialog.get_by_role("button", name="취소(esc)", exact=True).click()
            raise WehagoError(
                "일용근로소득지급명세 마감 오류 (강제마감 금지 — 오류 내용을 확인하고 위하고에서 "
                "직접 수정 후 재시도 필요): " + " / ".join(rows)
            )

        # 이 화면은 완료 팝업이 없다 — 마감(또는 강제마감) 성공 시 같은 화면에 머문 채
        # [마감] 버튼이 [마감해제]로 바로 바뀐다(일용직급여자료입력의 [완료]→[완료해제]와
        # 같은 패턴, 2026-09-30 실기 확인 — Chrome Recorder 녹화의 마지막 "navigate"
        # 스텝은 화면 자체의 동작이 아니라 사용자가 별도로 메뉴를 나간 것이었다).
        self.step = "일용근로소득지급명세 마감 완료 대기"
        try:
            smarta.get_by_role("button", name="마감해제", exact=True).wait_for(
                state="visible", timeout=UPLOAD_WAIT_MS
            )
        except PlaywrightTimeout:
            raise WehagoError("일용근로소득지급명세 마감 결과를 확인할 수 없습니다 — 화면 상태 확인 필요")
        return "마감 완료"

    def _select_local_tax_district(self, smarta, business_address: str | None) -> None:
        """지방세 마감 전 "법정동"(취급청) 선택 — 안 하면 [마감] 버튼이 비활성 상태로 막힌다.

        2026-10-02 사용자가 보내준 실제 HTML로 확인: `<th>법정동</th>` 같은 라벨 태그가
        아예 없다(이전 버전은 이 라벨을 찾다가 못 찾아 조용히 건너뛰었다 — 실기에서
        "법정동 입력 안 함" 증상으로 재현). 칸 자체(`div.LS_ngh_input2`)만 있고, 비어
        있을 때 placeholder 텍스트 "법정동코드, 법정동명으로 검색"이 들어있어 이걸로
        찾는다 — 선택되면 실제 값으로 바뀌어 더는 이 텍스트가 안 걸리므로, 선택 전/후
        모두 "placeholder 텍스트가 보이는 칸을 찾을 수 있는가"로 상태를 판단한다.

        코드도움 열기: `button.WSC_LUXButton`(돋보기 아이콘) 클릭 → "법정동 코드도움"
        다이얼로그. "찾을 내용" 표시(`div.LS_ngh_input2`)를 더블클릭해야 진짜
        `<input>`이 나타남(다른 화면의 `_type_fresh`와 같은 fake-표시 패턴) → 검색어
        입력 → [확인(enter)] (2026-10-02 사용자가 보내준 실제 다이얼로그 HTML로 구조
        재확인 완료).

        ⚠️ `div.fake_inputbox` 안에서만 버튼을 찾던 버전은 칸이 비어 있을 때의 구조만
        가정한 것이라, 값이 이미 있는 상태(아래 참고)에서는 그 래퍼가 없어 버튼을 못
        찾고 타임아웃났다(2026-10-02 사용자가 해당 상태의 버튼 HTML을 직접 보내
        확인) — `field` 범위 안에서 `fake_inputbox` 제약 없이 버튼을 찾도록 완화.

        ⚠️ 조회 직후 이 칸이 비동기로(저장된 초안 등) 늦게 채워질 수 있다 — 비어 있다고
        판단해 버튼을 눌렀는데 그 사이 이미 값이 채워지면서 다이얼로그가 안 뜨고
        타임아웃나는 경우를 실기로 확인(2026-10-02, 전혀 다른 지역의 기존 선택값이
        남아 있던 사례). 이 경우 타임아웃을 실패로 보지 않고 "이미 채워졌다"로 보고
        건너뛴다.

        ⚠️ `district_search_term`으로 만든 "구+동"/"읍(면)+리" 두 단계 검색어로 결과가
        1건으로 좁혀질 것으로 기대하고 짰다 — 실제로 안 좁혀지면 이 함수가 그대로
        실패할 수 있다(레코더는 캔버스 그리드 수동 선택을 못 담는다, §13-3-4와 동일한
        한계).

        이미 선택돼 있으면(재실행, 이미 마감 등) 건드리지 않고 건너뛴다.
        """
        from playwright.sync_api import TimeoutError as PlaywrightTimeout

        placeholder = re.compile("법정동")
        field = smarta.locator("div.LS_ngh_input2", has_text=placeholder).first
        if field.count() == 0:
            return  # 이미 값이 선택돼 있거나(placeholder 텍스트가 안 보임) 화면에 없음 — 건너뜀

        search_term = district_search_term(business_address)
        if not search_term:
            raise WehagoError(
                "지방세 취급청(법정동) 선택에 필요한 거래처 주소가 없거나 "
                "행정구역을 알아볼 수 없습니다 — 거래처 상세에서 사업장 주소를 확인하세요."
            )

        self.step = "지방세 취급청(법정동) 코드도움 열기"
        think("wehago")
        field.locator("button.WSC_LUXButton").first.click()
        dialog = smarta.locator("div._isDialog:visible", has_text="법정동 코드도움")
        try:
            dialog.wait_for(state="visible", timeout=UPLOAD_WAIT_MS)
        except PlaywrightTimeout:
            if smarta.locator("div.LS_ngh_input2", has_text=placeholder).count() == 0:
                return  # 버튼 클릭 사이 다른 값이 비동기로 채워져 다이얼로그가 안 뜬 것 — 건너뜀
            raise

        self.step = "지방세 취급청(법정동) 검색"
        search_display = dialog.locator("div.LS_ngh_input2").first
        think("wehago")
        search_display.dblclick()
        # dialog.locator("input")로 다이얼로그 전체에서 찾으면 "찾을 내용"보다 먼저
        # 캔버스 그리드(RealGrid)의 숨은 키보드 캡처용 input(aria-hidden, id가
        # "..._line")이 걸려 거기로 타이핑된다 — 보이는 "찾을 내용" 칸은 계속 비어
        # 보이는 증상으로 실기 재현(2026-10-02). search_display 범위 안에서만 찾는다.
        search_input = search_display.locator("input").first
        _type_fresh(search_input, search_term)
        think("wehago")
        dialog.get_by_role("button", name="확인(enter)", exact=True).click()
        self._wait_for_no_dimmed(smarta)

        if smarta.locator("div.LS_ngh_input2", has_text=placeholder).count() > 0:
            raise WehagoError(
                f"지방세 취급청(법정동) 선택 실패 — 검색어 '{search_term}'로 결과를 "
                "좁히지 못했습니다 (여러 건이거나 0건일 수 있음). 위하고에서 직접 선택 후 재시도하세요."
            )

    def _select_local_tax_period(self, smarta, item, period: str) -> None:
        """지방세 귀속년월·지급년월 — `_fill_closing_period`(숫자 타이핑)와 다른 위젯이다.

        2026-10-02 사용자가 보내준 실제 HTML로 확인: 연(年) 칸은 `tabindex="-1"`의
        비활성·읽기전용 표시라 SmartA 귀속 연도에 고정돼 있고 건드릴 수 없다(이전 버전은
        존재하지도 않는 "연도 선택" 단계를 기다리다 멈췄다 — 실패 스크린샷에서 연은
        이미 맞고 월만 빈 채로 계속 멈춰 있던 게 그 증거). 월만 작은 버튼
        (`button.WSC_LUXButton`)을 눌러 여는 목록에서 고른다.

        `item`에는 월 버튼이 1개(귀속년월)거나 2개(지급년월 — 시작~종료)일 수 있어
        안에 있는 버튼 전부를 같은 월로 채운다.

        ⚠️ `.count()`는 Playwright에서 대기 없이 그 순간의 개수를 바로 반환한다 —
        화면 전환 직후 조건바가 아직 안 그려진 상태에서 바로 세면 0건으로 나와 버튼을
        하나도 못 찾고 그냥 지나칠 수 있다(2026-10-02 실기에서 발견 — 아무 것도 안
        열고 바로 [조회]를 눌러버림). 세기 전에 첫 버튼이 보일 때까지 기다린다.
        """
        _, month = period.split("-")
        buttons = item.locator("button.WSC_LUXButton:visible")
        buttons.first.wait_for(state="visible", timeout=UPLOAD_WAIT_MS)
        for i in range(buttons.count()):
            self._pick_local_tax_month(smarta, buttons.nth(i), month)

    def _pick_local_tax_month(self, smarta, button, month: str) -> None:
        month_num = str(int(month))
        wanted = {month_num, f"{int(month):02d}", f"{month_num}월", f"{int(month):02d}월"}
        display = button.locator("xpath=preceding-sibling::div[@tabindex='0']").first
        if display.inner_text().strip() in wanted:
            return  # 이미 값이 맞음 — 건너뜀

        self.step = "지방세 귀속/지급년월 — 월 선택"
        think("wehago")
        button.click()
        option = smarta.locator(
            "li:visible, button:visible", has_text=re.compile(rf"^0*{month_num}\s*월?$")
        )
        try:
            option.first.wait_for(state="visible", timeout=UPLOAD_WAIT_MS)
        except Exception:
            raise WehagoError(
                f"지방세 귀속/지급년월에서 '{month}월'을 고르는 목록을 찾지 못했습니다 "
                "— 버튼을 눌렀을 때 뜨는 화면을 캡처해 알려주세요."
            )
        think("wehago")
        option.first.click()

        if display.inner_text().strip() not in wanted:
            raise WehagoError(f"지방세 귀속/지급년월 — '{month}월' 선택이 반영되지 않았습니다.")

    def close_local_tax_payment(
        self, business_number: str, period: str, *, business_address: str | None = None
    ) -> str:
        """지방소득세특별징수납부서(SWTA0112) 마감 (§4-4 ⑩-a).

        ⚠️ 부분 실측 — 귀속년월·지급년월 입력(`_select_local_tax_period`)은 사용자가
        보내준 실제 HTML로 확인했지만, 그 뒤 마감 버튼 라벨이 정말 "마감(F3)"인지,
        완료·오류 모달 문구는 close_wht_return을 본떠 추정한 것이라 아직 실행 검증
        전이다. 처음 실행해서 어긋나면 화면을 캡처해 알려줘야 고칠 수 있다.

        Args:
            business_address: 거래처 주소 — 취급청(법정동) 코드도움 검색어를 만드는 데 쓴다
                (`district_search_term`). 없으면 이 단계는 건너뛴다(자료 없는 거래처 등).

        Returns:
            완료 모달의 원문 텍스트.

        Raises:
            WehagoError: "마감 오류리스트"가 뜸 — §8-1 원칙대로 강제마감하지 않고 중단한다.
        """
        smarta, _name, _number = self._open_closing_menu(
            business_number, self._LOCAL_TAX_PAYMENT_MENU_ID
        )

        self.step = "지방세 조회 조건 입력"
        items = smarta.locator(_COND_BAR).locator("div.item")
        self._select_local_tax_period(smarta, items.nth(0), period)  # 귀속년월
        self._select_local_tax_period(smarta, items.nth(1), period)  # 지급년월(시작~종료)

        think("wehago")
        smarta.get_by_role("button", name="조회", exact=True).click()
        self._wait_for_no_dimmed(smarta)

        self._select_local_tax_district(smarta, business_address)

        self.step = "지방세 마감 여부 확인"
        # 이미 마감된 신고서는 [마감] 대신 [마감해제] 버튼으로 바뀐다 — 다른 마감·완료
        # 화면과 같은 공용 헬퍼로 통일한다(렌더링 타이밍 보호 포함, close_wht_return·
        # close_business_income_report와 동일 원칙, 2026-10-02).
        already = self._skip_if_already_finalized(smarta, "마감", "마감해제")
        if already is not None:
            return already
        self.step = "지방세 마감"
        think("wehago")
        smarta.get_by_role("button", name="마감", exact=True).click()

        from playwright.sync_api import TimeoutError as PlaywrightTimeout

        # [마감] 클릭 직후 제출 서식 목록("마감 리스트" — 납부서/영수필 통지서·계산서/명세서
        # 등 제출여부 O 행들)을 보여주는 다이얼로그가 먼저 뜬다. 여기서 [마감(F3)]을 한 번
        # 더 눌러야 실제 마감이 진행된다(2026-10-02 사용자 실기 확인) — 다른 마감 화면에는
        # 없는 이 화면만의 중간 확인 단계.
        self.step = "지방세 마감 리스트 확인"
        close_list = smarta.locator("div._isDialog:visible", has_text="마감 리스트")
        try:
            close_list.wait_for(state="visible", timeout=5_000)
        except PlaywrightTimeout:
            pass
        else:
            think("wehago")
            close_list.get_by_role("button", name="마감(F3)", exact=True).click()

        self.step = "지방세 마감 결과 확인"
        error_dialog = smarta.locator("div._isDialog:visible", has_text="마감 오류리스트")
        try:
            error_dialog.wait_for(state="visible", timeout=5_000)
        except PlaywrightTimeout:
            error_dialog = None
        if error_dialog is not None:
            # §8-1 원칙: 데이터 정합성 오류는 강제마감 금지, 취소하고 실패로 회신한다.
            rows = error_dialog.locator("table tr").all_inner_texts()
            think("wehago")
            cancel = error_dialog.get_by_role("button", name=re.compile("취소"))
            cancel.click()
            raise WehagoError(
                "지방세 마감 오류 (강제마감 금지 — 원천세 마감 결과 재확인 필요): "
                + " / ".join(r.strip() for r in rows if r.strip())
            )

        confirm = smarta.locator("div._isDialog:visible", has_text="원천징수 신고")
        try:
            confirm.wait_for(state="visible", timeout=UPLOAD_WAIT_MS)
        except PlaywrightTimeout:
            pass
        else:
            think("wehago")
            confirm.get_by_role("button", name="확인(enter)", exact=True).click()

        self.step = "지방세 마감 완료 대기"
        result = smarta.locator("div._isDialog:visible", has_text="완료")
        result.wait_for(state="visible", timeout=UPLOAD_WAIT_MS)
        text = result.inner_text().strip()
        think("wehago")
        result.get_by_role("button", name="확인", exact=True).click()
        return text

    def _select_efile_client(self, smarta, business_number: str) -> None:
        """원천징수 전자신고(SWER0101) "수임처" — 회사 코드도움에서 사업자번호로 검색해 선택.

        법정동 코드도움(§13-3-8)과 같은 컴포넌트(찾을 내용 입력 + 확인(enter)) 구조로
        추정해 같은 방식을 쓴다 — "찾을 내용" input도 다이얼로그 전체에서 찾으면 RealGrid
        캔버스의 숨은 키보드캡처용 input에 걸릴 위험이 있어(2026-10-02 법정동에서 발견한
        버그와 동일) 검색 필드 컨테이너 범위 안에서만 찾는다. 하이픈 없는 10자리로 검색
        (`wehago-t-dom-facts` 메모리 — 위하고 검색은 하이픈 매칭 안 됨). ⚠️ 미실측 —
        처음 실행해서 어긋나면(버튼·다이얼로그 구조가 다르면) 화면을 캡처해 알려줄 것.
        """
        field = smarta.locator(_COND_BAR).locator("div.item", has_text=re.compile("수임처")).first
        think("wehago")
        field.locator("button.WSC_LUXButton").first.click()
        dialog = smarta.locator("div._isDialog:visible", has_text="회사 코드도움")
        dialog.wait_for(state="visible", timeout=UPLOAD_WAIT_MS)

        search_display = dialog.locator("div.LS_ngh_input2").first
        think("wehago")
        search_display.dblclick()
        search_input = search_display.locator("input").first
        _type_fresh(search_input, normalize_business_number(business_number))
        think("wehago")
        dialog.get_by_role("button", name="확인(enter)", exact=True).click()
        self._wait_for_no_dimmed(smarta)

    def produce_wht_efile(self, business_number: str, period: str, password: str) -> str:
        """원천징수 전자신고(SWER0101) 파일 제작 (§13-3-9 분석 기반 구현, 2026-10-02).

        지급기간 입력 → 수임처 선택(코드도움) → 조회 → [제작(F4)] → "변환파일 비밀번호"
        입력 → [전자신고 파일 제작(Enter)]까지 전부 시도한다. plan/16 §3-5에 "맥에서는
        제작을 할 수 없다"는 안내가 뜬다고 이미 기록돼 있어 마지막 클릭 이후 거기서
        막힐 가능성이 높다 — 그 경우를 명확한 WehagoError로 구분해 표면화한다(사용자
        요청: "맥이라서 안 되는 직전까지만" — 실제로 끝까지 시도해서 정확히 어디서
        막히는지 확인하는 것이 목적).

        Args:
            password: 변환파일 비밀번호 — 위하고 쪽 제약은 영문 소문자+숫자 8~15자로
                추정(사용자 Chrome Recorder 녹화에서 7자리 입력 시 거부되고 8자리로
                재입력한 흔적으로 추정, 미확정).

        Returns:
            완료 모달의 원문 텍스트 — 만약 성공한다면 §3-5의 "맥 미지원" 기록을 뒤집는
            새 발견이므로 plan 문서도 함께 갱신해야 한다.

        Raises:
            WehagoError: 맥 미지원 안내가 뜸, 또는 그 밖의 예상과 다른 화면.

        ⚠️ 미실측 — 지급기간 위젯이 SWTA0112와 같다는 것과 수임처 코드도움 다이얼로그
        구조는 화면 분석(§13-3-9)·녹화로 추정한 것이라 조회조건 입력까지는 비교적
        확실하지만, [제작(F4)] 이후 모달·버튼 셀렉터(`get_by_placeholder`,
        "전자신고 파일 제작(Enter)" 버튼명)는 사용자가 보내준 레코딩의 aria 셀렉터를
        그대로 믿고 짠 것이라 실행 검증 전이다.
        """
        from playwright.sync_api import TimeoutError as PlaywrightTimeout

        smarta, _name, _number = self._open_closing_menu(business_number, self._WHT_EFILE_MENU_ID)

        self.step = "전자신고 지급기간 입력"
        items = smarta.locator(_COND_BAR).locator("div.item")
        self._select_local_tax_period(smarta, items.nth(0), period)  # 지급기간(시작~종료)

        self.step = "전자신고 수임처 선택"
        self._select_efile_client(smarta, business_number)

        self.step = "전자신고 조회"
        think("wehago")
        smarta.get_by_role("button", name="조회", exact=True).click()
        self._wait_for_no_dimmed(smarta)

        self.step = "전자신고 제작 모달 열기"
        think("wehago")
        # "제작(F4)" 버튼이 화면에 2개 있다 — #saosnb 쪽은 다른 화면과 공유하는 장식용/
        # 비활성 버튼으로 보이고, 실제 동작은 id="onHandleMake"가 한다(2026-10-02 사용자
        # 실기: role 기반 셀렉터가 strict mode violation으로 2개에 걸림, 에러 메시지로
        # 두 요소의 id를 직접 확인).
        smarta.locator("#onHandleMake").click()
        modal = smarta.locator("div._isDialog:visible", has_text="전자신고 파일 제작")
        modal.wait_for(state="visible", timeout=UPLOAD_WAIT_MS)

        self.step = "전자신고 변환파일 비밀번호 입력"
        # 레코딩의 aria 셀렉터(`aria/비밀번호를 입력해주세요.` + `aria/[role="textbox"]`)는
        # HTML placeholder 속성이 아니라 접근성 이름(accessible name) 매칭이었다 —
        # get_by_placeholder는 placeholder 속성만 보기 때문에 못 찾아 타임아웃났다
        # (2026-10-02 사용자 실기 확인). 레코딩이 실제로 쓴 role+접근성 이름 조합으로 교체.
        pw_input = modal.get_by_role("textbox", name="비밀번호를 입력해주세요.")
        _type_fresh(pw_input, password)

        self.step = "전자신고 파일 제작 실행"
        think("wehago")
        modal.get_by_role("button", name="전자신고 파일 제작(Enter)", exact=True).click()

        self.step = "전자신고 결과 확인 — 맥 지원 여부"
        mac_block = smarta.locator("div:visible", has_text="맥에서는 제작을 할 수 없습니다")
        try:
            mac_block.wait_for(state="visible", timeout=8_000)
        except PlaywrightTimeout:
            mac_blocked = False
        else:
            mac_blocked = True
        if mac_blocked:
            raise WehagoError(
                "전자신고 파일 제작 — 맥에서는 지원되지 않습니다(plan/16 §3-5 기존 기록과 "
                "일치). Windows PC에서 같은 화면을 열어 [제작(F4)]부터 다시 진행하세요."
            )

        self.step = "전자신고 완료 대기"
        result = smarta.locator("div._isDialog:visible", has_text="완료")
        result.wait_for(state="visible", timeout=UPLOAD_WAIT_MS)
        text = result.inner_text().strip()
        think("wehago")
        result.get_by_role("button", name="확인", exact=True).click()
        return text

    # ------------------------------------------------------------------
    # 소득자 명단 읽기 (plan/16 §13-3-5, 2026-09-30) — RealGrid `_gridView`를 직접 읽는다.
    # 사업소득자등록(SWBU0101)엔 엑셀 다운로드가 없다(실측 확인, 우측 상단 메뉴에
    # "엑셀 내려받기" 없음) — `_REALGRID_ROWS_JS`(이미 급여자료입력 그리드에서 쓰던 패턴)로
    # 화면 UI 조작 없이 캔버스 그리드 전체 행을 그대로 뽑는다.
    # ------------------------------------------------------------------

    def list_business_income_earners(self, business_number: str) -> list[dict[str, Any]]:
        """사업소득자등록(SWBU0101) 전체 명단 — 읽기 전용.

        반환값은 backend `wehago_import.ImportedEmployee`(income_type="BUSINESS")에 바로
        넣을 수 있는 dict 리스트다. 실측 필드(2026-09-30, `#Leftgird`): `cd_buemp`(위하고
        사원코드) · `nm_krname`(이름) · `no_social`(주민번호, 하이픈 없음) ·
        `cd_income`(사업소득 업종코드) · `da_retire`(퇴사일, 빈 문자열이면 재직중).

        진입은 `_open_closing_menu`(id 기반)가 아니라 `open_business_income_screen`과 같은
        "사업소득관리 / 기타(이자 / 배당)소득관리" 카테고리 공통 로직(`_open_business_category_menu`)을
        쓴다 — 이 카테고리는 서브메뉴가 화면코드가 아니라 내부 생성 숫자 id라 텍스트로 찾아야 한다.
        """
        smarta, _name, _number = self._open_smarta(business_number)
        self._smarta_page = smarta
        self._open_business_category_menu(smarta, "사업소득자등록")
        self.step = "사업소득자 명단 읽기"
        think("wehago")
        rows = smarta.locator("#Leftgird").evaluate(_REALGRID_ROWS_JS)
        return _parse_business_income_rows(rows)

    def list_other_income_earners(self, business_number: str) -> list[dict[str, Any]]:
        """기타(이자/배당)소득자등록(SWET0101) 전체 명단 — 읽기 전용.

        `list_business_income_earners`와 같은 방식(RealGrid 직접읽기, 같은 카테고리)이지만
        그리드 id(`#Leftgrid`)·필드명(`cd_etemp` 등)이 다르다 — `_parse_other_income_rows`
        참고. 반환값은 `income_type="BUSINESS"`가 아니라 `"OTHER"`이고, `business_type_code`는
        보내지 않는다(사업소득 전용 필드라 재사용하지 않기로 함, §13-3-4).
        """
        smarta, _name, _number = self._open_smarta(business_number)
        self._smarta_page = smarta
        self._open_business_category_menu(smarta, "기타(이자/배당)소득자등록")
        self.step = "기타소득자 명단 읽기"
        think("wehago")
        rows = smarta.locator("#Leftgrid").evaluate(_REALGRID_ROWS_JS)
        return _parse_other_income_rows(rows)

    def list_daily_workers(self, business_number: str) -> list[dict[str, Any]]:
        """일용직 사원등록(SWSA0107) 전체 명단 — 읽기 전용.

        "근로소득관리 / 연말정산관리"가 기본 카테고리라 `_open_smarta_menu`(id 기반)로
        바로 들어간다(사업소득관리 카테고리의 `_open_business_category_menu`와 다름).
        `_parse_daily_worker_rows` 참고 — 그리드 id `#Tab1_left_grid`, `income_type="DAILY"`,
        `business_type_code`는 안 보낸다.
        """
        smarta, _name, _number = self._open_smarta_menu(
            business_number, self._DAILY_WORKER_REGISTER_MENU_ID
        )
        self.step = "일용직 사원 명단 읽기"
        think("wehago")
        rows = smarta.locator("#Tab1_left_grid").evaluate(_REALGRID_ROWS_JS)
        return _parse_daily_worker_rows(rows)

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

    _OTHER_INCOME_REGISTER_MENU_ID = "SWET0101"  # 실측 확인 (2026-09-30, list_other_income_earners)

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

        진입은 `_open_closing_menu`가 아니라 사업소득과 같은 `_open_business_category_menu`를
        써야 한다(§13-3-4에서 `list_business_income_earners` 만들 때 같은 문제로 확인).
        """
        smarta, _name, _number = self._open_smarta(business_number)
        self._smarta_page = smarta
        self._open_business_category_menu(smarta, "기타(이자/배당)소득자등록")

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

    _DAILY_WORKER_REGISTER_MENU_ID = "SWSA0107"  # 실측 확인 (2026-09-30, list_daily_workers)

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

        진입은 "근로소득관리 / 연말정산관리"가 기본 카테고리라 `_open_smarta_menu`(id 기반)면
        충분하다 — `open_daily_income_screen`과 같은 근거(§13-3-4에서 `list_daily_workers`
        만들 때 재확인).
        """
        smarta, _name, _number = self._open_smarta_menu(
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
        # 화면 진입 직후 바로 닫아도(_open_smarta_menu) 이 공지 팝업이 그 다음에 뜨는 경우가
        # 있어(2026-09-29 실기: 첫 시도 실패) 실제로 클릭하기 직전에 한 번 더 확인한다.
        # SmartA는 메인 페이지와 별개 탭이라 "2차 인증" 같은 안내 모달을 따로 띄울 수 있다
        # (2026-10-02 실기 — 캘린더 클릭이 원인불명 타임아웃, _dismiss_splash가 메인 페이지만
        # 보고 있어 못 닫았을 가능성).
        self._dismiss_notice(page)
        self._dismiss_splash(page)
        year, month = period.split("-")
        want_period, want_date = f"{year}.{month}", pay_date.strftime("%Y.%m.%d")
        items = page.locator(_COND_BAR).locator("div.item")
        if _fake_text(items.nth(0)) != want_period:
            # 귀속연월은 키보드 입력이 먹히지 않는 경우가 있어(2026.03 으로 들어감, 2026-09-27 실측)
            # 달력 아이콘 → 월 버튼으로 고른다. 달력의 연도는 SmartA 귀속 연도로 고정.
            # fake_inputbox·fakebutton 중복 렌더 가능성도 있어(2026-10-02 사업소득 화면에서
            # 실측) .first로 명시한다.
            think("wehago")
            self._click_dismissing_notice(page, items.nth(0).locator("div.fakebutton").first)
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

    def _ensure_data_entry_unlocked(self, page) -> bool:
        """자료입력 화면이 [완료] 상태(버튼이 [완료 해제]/[완료해제]로 바뀜)면 눌러서 푼다.

        2026-10-01 실기로 발견: 기타소득자료입력에서 이미 [완료] 처리된 달은 "엑셀서식
        불러오기" 메뉴를 클릭해도 화면이 전혀 반응하지 않는다(다이얼로그도 안 뜨고 DOM도
        안 바뀜) — [완료] 상태에서 하위 편집 기능이 비활성화되기 때문으로 보인다. 재시도가
        아니라 먼저 [완료 해제]를 눌러 잠금을 풀어야 업로드가 진행된다(사용자 실측 확인).

        이 "완료"는 신고서 마감(close_wht_return 등의 [마감])과는 **다른 개념**이다 —
        단순히 "이 화면 데이터입력 다 끝남" 표시일 뿐 국세청에 제출되는 상태가 아니므로
        자동으로 풀고 계속 진행해도 안전하다고 판단했다(2026-10-01). 반면 [마감]은 실제
        신고 상태라 자동으로 풀지 않고 지금처럼 건너뛴다(close_wht_return 등 §4-4 참고) —
        화면마다 버튼 레이블 공백이 다르다(실기로 "완료 해제"/"완료해제" 둘 다 확인).

        [완료 해제] 클릭 뒤 "완료를 해제하시겠습니까?" 확인 다이얼로그(❓ 아이콘 +
        [취소]/[확인])가 한 번 더 뜬다 — 사용자가 실기로 확인, [확인]까지 눌러야 실제로
        풀린다. 이 다이얼로그를 처리 안 하면 화면 전체를 가리는 모달이라 이후 어떤 클릭도
        막혀버린다(2026-10-01 실기 확인).

        Returns:
            실제로 해제 버튼을 눌렀으면 True.
        """
        for label in ("완료 해제", "완료해제"):
            btn = page.get_by_role("button", name=label, exact=True)
            if btn.count() and btn.first.is_visible():
                self.step = f"[{label}] 눌러 잠금 해제"
                think("wehago")
                btn.first.click()
                confirm = page.locator("div._isDialog:visible", has_text="완료를 해제하시겠습니까?")
                confirm.wait_for(state="visible", timeout=UPLOAD_WAIT_MS)
                think("wehago")
                confirm.get_by_role("button", name="확인", exact=True).click()
                self._wait_for_no_dimmed(page)
                return True
        return False

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
            # 이전엔 "phone"이라는 이름으로 반환해 API 스키마(contact_phone)와 안 맞아 한 번도
            # 저장된 적이 없었다 (2026-09-30 발견·수정) — 키 이름을 스키마와 맞춘다.
            "contact_phone": pairs.get("전화번호", "") or None,
            # "원주 세무서"처럼 " 세무서" 접미사가 붙어 온다 (2026-09-30 실측, 서도 → 원주 세무서).
            "tax_jurisdiction": pairs.get("수임기업 담당세무서", "") or None,
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


def _parse_business_income_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """사업소득자등록(SWBU0101) `#Leftgird`의 `_REALGRID_ROWS_JS` 결과 → 임포트 페이로드.

    빈 자리표시 행(신규 입력용 마지막 빈 줄, `cd_buemp`/`nm_krname` 둘 다 빈 문자열)은
    제외한다. `WehagoUploader.list_business_income_earners`에서만 쓴다 — 브라우저 없이
    단위 테스트하려고 분리했다.
    """
    out: list[dict[str, Any]] = []
    for r in rows:
        code = str(r.get("cd_buemp") or "").strip()
        name = str(r.get("nm_krname") or "").strip()
        if not code or not name:
            continue
        rrn = str(r.get("no_social") or "").strip()
        resigned_at = None
        resigned_raw = str(r.get("da_retire") or "").strip()
        if resigned_raw:
            try:
                resigned_at = date.fromisoformat(resigned_raw[:10])
            except ValueError:
                resigned_at = None
        income_code = str(r.get("cd_income") or "").strip()
        out.append(
            {
                "employee_code": code,
                "name": name,
                "rrn": rrn or None,
                "resigned_at": resigned_at,
                "income_type": "BUSINESS",
                "business_type_code": income_code or None,
            }
        )
    return out


def _parse_other_income_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """기타(이자/배당)소득자등록(SWET0101) `#Leftgrid`의 `_REALGRID_ROWS_JS` 결과 → 임포트 페이로드.

    사업소득 그리드(`_parse_business_income_rows`)와 필드가 다르다(2026-09-30 실측):
    `cd_etemp`(위하고 사원코드, 사업소득의 `cd_buemp`와 다른 이름) · `nm_krname`(이름) ·
    `no_social`(주민번호) · `cd_income`(소득구분 코드, 2자리 — 예: "69") · 퇴사일 필드
    자체가 없다(이자/배당·기타소득자는 재직 개념이 없다). 빈 자리표시 행은 `cd_etemp`가
    이미 다음 코드로 채워져 있어도 `nm_krname`이 비어 있으면 걸러낸다(사업소득과 다른 점).

    `cd_income`은 굳이 안 옮긴다 — `Employee.business_type_code`는 사업소득 업종코드
    (940xxx) 전용 필드라 `tax_calc.py`/`smarta_business_xls.py`가 그 형식을 가정한다.
    기타소득 코드를 저장할 Employee 필드가 따로 없으니(§13-3-4), 코드가 필요해지면
    새 필드를 추가하는 게 맞다 — 지금은 명단(이름·주민번호)만 동기화한다.
    """
    out: list[dict[str, Any]] = []
    for r in rows:
        name = str(r.get("nm_krname") or "").strip()
        if not name:
            continue
        code = str(r.get("cd_etemp") or "").strip()
        rrn = str(r.get("no_social") or "").strip()
        out.append(
            {
                "employee_code": code,
                "name": name,
                "rrn": rrn or None,
                "income_type": "OTHER",
            }
        )
    return out


def _parse_daily_worker_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """일용직 사원등록(SWSA0107) `#Tab1_left_grid`의 `_REALGRID_ROWS_JS` 결과 → 임포트 페이로드.

    필드(2026-09-30 실측): `cd_emp`(위하고 사원코드, 다른 화면과 달리 0-padding 없이
    "1") · `nm_emp`(이름, 다른 화면의 `nm_krname`과 다른 키) · `no_social`(주민번호) ·
    `age`(자동계산, 안 옮김) · `fg_forg`(외국인 여부, 안 옮김). 입사일·퇴사일은 이 왼쪽
    그리드가 아니라 오른쪽 상세 패널에 있어 여기선 못 읽는다 — 명단(이름·주민번호)만
    동기화한다.
    """
    out: list[dict[str, Any]] = []
    for r in rows:
        name = str(r.get("nm_emp") or "").strip()
        if not name:
            continue
        code = str(r.get("cd_emp") or "").strip()
        rrn = str(r.get("no_social") or "").strip()
        out.append(
            {
                "employee_code": code,
                "name": name,
                "rrn": rrn or None,
                "income_type": "DAILY",
            }
        )
    return out


def _report_type_code(period: str, today: date | None = None) -> str:
    """원천세 신고구분 코드 — 귀속월 다음달 10일(정기신고 기한)이 지났으면 기한후신고.

    "0. 정기신고"/"2. 기한후신고" 두 가지만 다룬다 — 수정신고 계열(1·3)은 자동화 범위 밖
    (사용자 지시로 2026-09-30 추가, plan/16 §4-8 "수정신고·기한후신고 초기 제외"를 넘어선
    실무 요구 — 반영 필요).
    """
    year, month = (int(x) for x in period.split("-"))
    deadline_month, deadline_year = month + 1, year
    if deadline_month > 12:
        deadline_month, deadline_year = 1, year + 1
    deadline = date(deadline_year, deadline_month, 10)
    return "2" if (today or date.today()) > deadline else "0"


_ADMIN_SUFFIXES = (
    "특별자치시", "특별자치도", "광역시", "특별시", "자치구",
    "시", "군", "구", "읍", "면", "동", "리",
)  # 길이 긴 접미사부터 — "서울특별시"가 "시"보다 "특별시"로 먼저 잘려야 한다


def district_search_term(address: str | None) -> str | None:
    """지방세 마감 전 취급청/법정동 코드도움 검색어 — 주소 끝에서 두 행정구역명만 쓴다.

    시/군 등 상위 단위 종류로 분기하지 않는다 — 주소를 공백 기준 토큰화해 행정구역
    접미사(시/군/구/읍/면/동/리 등)로 끝나는 토큰만 골라 접미사를 떼고, **맨 뒤 두 개**를
    공백으로 이어붙인다. 이러면 "시-구-동"이든 "군-읍-리"든 같은 규칙으로 처리되고,
    드물게 더 긴 사슬(예: 시 다음에 군)이 와도 끝에서 두 단계만 보므로 깨지지 않는다
    (2026-10-02 사용자 설명 — 예: "종로구 청운동" → "종로 청운", "횡성군 횡성읍 읍상리" →
    "횡성 읍상"). 단일 토큰으로 검색하면 결과가 여러 건 나올 수 있어(코드도움 팝업이
    정확히 1건으로 좁혀져야 선택이 안전하다) 두 단계를 같이 넣어 좁힌다.

    Returns:
        검색어, 또는 행정구역으로 인식되는 토큰이 2개 미만이면 None(호출자가 건너뛰어야 함).
    """
    if not address:
        return None
    admin_tokens: list[str] = []
    for token in address.split():
        for suffix in _ADMIN_SUFFIXES:
            if token.endswith(suffix) and len(token) > len(suffix):
                admin_tokens.append(token[: -len(suffix)])
                break
    if len(admin_tokens) < 2:
        return None
    return " ".join(admin_tokens[-2:])


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
