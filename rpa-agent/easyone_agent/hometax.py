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

from pathlib import Path

HOMETAX_LOGIN_URL = (
    "https://hometax.go.kr/websquare/websquare.html?w2xPath=/ui/pp/index.xml"
)
HOMETAX_MAIN_URL = "https://hometax.go.kr"
LOGIN_FORM_WAIT_MS = 15_000
LOGIN_WAIT_MS = 60_000

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
