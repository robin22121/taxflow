"""잡 실행 — 홈택스 사업자등록증명 발급.

- `dummy`: 실제 홈택스 접속 없이 placeholder PNG 반환. 서버-에이전트 통신·저장 흐름 검증용.
- `phase1`: rpa/certificate-poc/ 의 hometax_login 을 재사용해 로그인 후
           신청 → 작성완료 → 접수 → 결과조회 → 출력 팝업 → PDF 회수까지 전부 자동.

셀렉터 근거는 plan/17-certificate-issuance.md §3-7-1 (2026-09-18 Windows 실측).
기본값은 CERT_AGENT_MODE 환경변수 (`dummy` | `phase1`).
"""

from __future__ import annotations

import base64
import os
import re
import sys
import time
from pathlib import Path

from certificate_agent.config import AgentConfig

MODE = os.environ.get("CERT_AGENT_MODE", "dummy")

DUMMY_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk"
    "+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)

# 사업자등록증명 발급 신청 화면 (전체메뉴 앵커 #a_4315010800 과 같은 곳)
BUSINESS_REG_URL = (
    "https://hometax.go.kr/websquare/websquare.html"
    "?w2xPath=/ui/pp/index_pp.xml&menuCd=UTEABGA0A021"
)

# --- 신청 화면 셀렉터 ---
SEL_TAXPAYER_CL_BSNO = "#mf_txppWframe_pfm_UTECAAA0Z001_rad_pfbPsenNtplAplcCl_input_1"
SEL_BSNO = "#mf_txppWframe_pfm_UTECAAA0Z001_sbx_pfbPsenNtplBsno"
SEL_KOREAN_CERT = "#mf_txppWframe_rad_englCvaAplnYn_input_0"
SEL_USE_PURPOSE = "#mf_txppWframe_sbx_cvaDcumUseUsgCd"
SEL_SUBMIT_ORG = "#mf_txppWframe_sbx_cvaDcumSbmsOrgnClCd"
SEL_RRN_OPEN = "#mf_txppWframe_pfm_UTECAAA0Z002_rad_cvaAplnRecptResNoOpYn_input_0"
SEL_RRN_HIDDEN = "#mf_txppWframe_pfm_UTECAAA0Z002_rad_cvaAplnRecptResNoOpYn_input_1"
SEL_RECEIVE_METHOD = "#mf_txppWframe_pfm_UTECAAA0Z002_sbx_cvaAplnRecptMthd"
SEL_WRITE_DONE = "#mf_txppWframe_btn_wrtCmpl"

# --- 모달·결과조회 셀렉터 ---
SEL_MODAL_SUBMIT = "#mf_txppWframe_UTECAAA0A016_wframe_btn_sbms"  # "신청하시겠습니까?" → 신청하기
SEL_MODAL_CONFIRM = "input[id*='_wframe_btn_confirm'][value='확인']"  # "정상적으로 접수되었습니다"
SEL_GOTO_RESULT = "#mf_txppWframe_btn_cvaTrtRsltInqr"  # 민원처리결과 조회
SEL_RESULT_SEARCH = "#mf_txppWframe_btn_search"  # 조회
SEL_FIRST_PRINT = "#mf_txppWframe_gen_cvaInf_0_btn_cvaDcumGranMthdNm"  # 첫 행 [출력]
SEL_WARN_YES = "#mf_txppWframe_UTECAAP0A024_wframe_btn_yes"  # 위·변조 경고 → 예 (팝업)

# --- 납세증명서(기타용) 신청 화면 (2026-09-22 맥북 실측) ---
# 납세자 구분은 로그인 주체로 고정(disabled)되고 사업자 선택 드롭다운이 없다.
SEL_TC_USE_ETC = "#mf_txppWframe_rad_use_input_1"  # 사용목적: 기타 (기본 선택)
SEL_TC_WRITE_DONE = "#mf_txppWframe_btn_apln"  # 작성완료 (사업자등록증명과 id 다름)

USE_PURPOSE_LABEL = "기타"
SUBMIT_ORG_LABEL = "기타"
RECEIVE_METHOD_LABEL = "인터넷발급(프린터출력)"


def _digits(s: str) -> str:
    return re.sub(r"\D", "", s or "")


def _sys_path_add_phase1() -> None:
    here = Path(__file__).resolve().parent.parent.parent  # rpa/
    p1 = str((here / "certificate-poc").resolve())
    if p1 not in sys.path:
        sys.path.insert(0, p1)


def execute_dummy(job: dict, cfg: AgentConfig) -> tuple[bytes, str, str, str]:
    """실제 홈택스 접속 없이 즉시 dummy PNG 반환."""
    time.sleep(1.0)
    data = base64.b64decode(DUMMY_PNG_B64)
    msg = f"dummy mode: cert_type={job['cert_type']} biz={job['business_number']}"
    return data, "cert_dummy.png", "image/png", msg


WORK = Path(__file__).resolve().parent.parent / "work"

MENU_ANCHOR = "#a_4315010800"  # 전체메뉴 > 즉시발급 증명 > 사업자등록증명


def _dump(page, tag: str) -> str:
    """화면을 HTML·PNG 로 남긴다 (실패 지점·셀렉터 수집). 저장 경로 반환."""
    WORK.mkdir(exist_ok=True)
    stem = WORK / f"{tag}_{int(time.time())}"
    try:
        stem.with_suffix(".html").write_text(page.content(), encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    try:
        page.screenshot(path=str(stem.with_suffix(".png")), timeout=15000)
    except Exception:  # noqa: BLE001
        pass
    return str(stem)


def _click_apply_for(page, title: str) -> None:
    """카탈로그에서 제목이 일치하는 행의 [신청하기] 를 누른다.

    조상 탐색(ancestor::)으로 잡으면 목록 밖의 같은 텍스트(전체메뉴 앵커·바로가기)에
    걸려 목록 전체 컨테이너를 잡고 첫 행을 눌러버린다(2026-09-18: 납부내역증명이
    눌려 간편인증 요구 화면으로 빠짐). 행 버튼을 직접 순회해 제목을 확인한다.
    """
    buttons = page.locator("input[id*='_gen_cvaInf_'][id$='_btn_apln']")
    page.wait_for_selector("input[id*='_gen_cvaInf_'][id$='_btn_apln']", timeout=20000)
    seen: list[str] = []
    for i in range(buttons.count()):
        btn = buttons.nth(i)
        row = btn.locator("xpath=ancestor::li[1]")
        if row.count() == 0:
            continue
        text = row.inner_text().replace("\n", " ").strip()
        seen.append(text[:30])
        if title in text:
            btn.click(timeout=15000)
            return
    raise RuntimeError(f"카탈로그에 '{title}' 행 없음. 보이는 행: {seen}")


def _goto_application(page, spec: dict) -> None:
    """카탈로그에서 spec["title"] 행의 신청 화면으로 진입.

    실제 경로(2026-09-18 사용자 확인):
      상단 '증명·등록·신청·사업장현황' → 드롭다운 [국세 민원 서류 찾기]
      → 카탈로그 목록에서 '사업자등록증명' 행의 [신청하기]

    로그인 직후 화면에는 전체메뉴 앵커(#a_4315010800)가 DOM 에 없으므로 상단 메뉴를
    먼저 열어야 한다. 구분자가 화면마다 ·/ㆍ/･ 로 달라 '사업장현황' 만 매칭한다.
    카탈로그 행 id(gen_cvaInf_{n})는 순서가 고정이 아니라 제목으로 행을 찾는다.
    """
    try:
        # 스크롤이 내려가 있으면 헤더가 축소되며 GNB 가 숨는다 (부착 모드에서 흔함)
        page.evaluate("window.scrollTo(0, 0)")
        time.sleep(0.5)
        page.get_by_text(re.compile("사업장현황")).first.click(timeout=15000)
        time.sleep(2.5)
        print("[+] 상단 메뉴 열림")

        page.get_by_text(re.compile("국세 ?민원 ?서류 ?찾기")).first.click(timeout=15000)
        time.sleep(4.0)
        print(f"[+] 카탈로그 도달. url={page.url}")

        _click_apply_for(page, spec["title"])
        time.sleep(4.0)
        print(f"[+] {spec['title']} 신청 화면. url={page.url}")
    except Exception as exc:  # noqa: BLE001
        if spec["type"] != "BUSINESS_REGISTRATION":  # 폴백 경로는 사업자등록증명 전용
            raise
        print(f"[!] 메뉴 경로 실패({exc.__class__.__name__}: {exc}) — 폴백 시도")
        for label, action in (
            ("전체메뉴 앵커", lambda: page.locator(MENU_ANCHOR).first.click(timeout=10000)),
            ("menuCd 직행", lambda: page.goto(BUSINESS_REG_URL, wait_until="domcontentloaded")),
        ):
            try:
                action()
                time.sleep(4.0)
                print(f"[*] {label} 후 url={page.url}")
                if page.locator(spec["ready"]).count() > 0:
                    break
            except Exception as exc2:  # noqa: BLE001
                print(f"[!] {label} 실패: {exc2.__class__.__name__}")

    if page.locator(spec["ready"]).count() == 0:
        path = _dump(page, "fail_nav")
        raise RuntimeError(
            f"신청 화면 진입 실패. url={page.url} title={page.title()!r} dump={path}"
        )


def _pick_business_number(page, wanted: str) -> str:
    """사업자등록번호 드롭다운에서 요청된 사업자를 고른다. 선택된 라벨 반환."""
    target = _digits(wanted)
    options = page.locator(f"{SEL_BSNO} option").all_text_contents()
    for label in options:
        if _digits(label) == target:
            page.select_option(SEL_BSNO, label=label)
            return label
    available = ", ".join(o for o in options if _digits(o))
    raise RuntimeError(f"사업자등록번호 {wanted} 없음. 계정 보유: [{available}]")


def _choose_radio(page, selector: str, label: str) -> None:
    """WebSquare 라디오 선택.

    실제 <input> 은 화면 밖에 숨기고 <label> 만 보여주는 구조라 일반 클릭이
    "element is outside of the viewport" 로 실패한다. label 클릭 → DOM 이벤트
    디스패치 순으로 폴백한다.
    """
    if page.locator(selector).is_checked():
        print(f"[+] {label} (이미 선택됨)")
        return

    elem_id = selector.lstrip("#")
    attempts = (
        ("직접 클릭", lambda: page.locator(selector).click(timeout=5000)),
        ("label 클릭", lambda: page.locator(f"label[for='{elem_id}']").click(timeout=5000)),
        ("이벤트 디스패치", lambda: page.locator(selector).dispatch_event("click")),
    )
    for how, action in attempts:
        try:
            action()
            if page.locator(selector).is_checked():
                print(f"[+] {label} ({how})")
                return
        except Exception as exc:  # noqa: BLE001
            print(f"[*] {label} {how} 실패: {exc.__class__.__name__}")
    raise RuntimeError(f"{label} 선택 실패 (selector={selector})")


def _click_soft(page, selector: str, label: str) -> None:
    """이미 기본값으로 맞아 있는 항목 — 비활성·미표시여도 흐름을 막지 않는다."""
    try:
        page.locator(selector).click(timeout=5000)
    except Exception as exc:  # noqa: BLE001
        print(f"[*] {label} 클릭 건너뜀 ({exc.__class__.__name__}) — 기본값 사용")


def _fill_application(page, job: dict) -> str:
    """신청 화면을 채우고 [작성완료] 까지. 선택된 사업자 라벨 반환.

    납세자 구분(주민/사업자)은 disabled 로 렌더되며 사업자등록번호가 이미 선택돼
    있다. 발급유형도 한글증명이 기본이고 사업자 선택 전에는 숨어 있다(nodis).
    둘 다 강제로 누르지 않는다.
    """
    time.sleep(1.0)

    picked = _pick_business_number(page, job["business_number"])
    print(f"[+] 사업자 선택: {picked}")
    time.sleep(2.0)  # 상호·대표자명 자동 채움 · 하위 항목 노출 대기

    _click_soft(page, SEL_KOREAN_CERT, "발급유형 한글증명")
    page.select_option(SEL_USE_PURPOSE, label=USE_PURPOSE_LABEL)
    page.select_option(SEL_SUBMIT_ORG, label=SUBMIT_ORG_LABEL)
    _choose_rrn_and_receive(page, job)

    page.locator(SEL_WRITE_DONE).click(timeout=10000)
    return picked


def _choose_rrn_and_receive(page, job: dict) -> None:
    """주민등록번호 공개여부(요청 옵션) + 수령방법. 두 증명원 화면에서 id 가 같다."""
    rrn_disclosed = bool((job.get("options") or {}).get("rrn_disclosed", False))
    _choose_radio(
        page,
        SEL_RRN_OPEN if rrn_disclosed else SEL_RRN_HIDDEN,
        f"주민등록번호 {'공개' if rrn_disclosed else '비공개'}",
    )
    page.select_option(SEL_RECEIVE_METHOD, label=RECEIVE_METHOD_LABEL)
    time.sleep(0.5)


def _fill_tax_clearance(page, job: dict) -> str:
    """납세증명서(기타용) 신청 화면을 채우고 [작성완료] 까지.

    납세자 구분이 로그인 주체(개인 로그인 → 주민등록번호)로 고정돼 있어 사업자를
    고르지 않는다. 발급유형은 한글증명이 기본값.
    """
    time.sleep(1.0)
    _choose_radio(page, SEL_TC_USE_ETC, "사용목적 기타")
    page.select_option(SEL_SUBMIT_ORG, label=SUBMIT_ORG_LABEL)
    _choose_rrn_and_receive(page, job)

    page.locator(SEL_TC_WRITE_DONE).click(timeout=10000)
    return "로그인 납세자"


CERT_SPECS = {
    "BUSINESS_REGISTRATION": {"title": "사업자등록증명", "ready": SEL_BSNO, "fill": _fill_application},
    "TAX_CLEARANCE_ETC": {"title": "납세증명서(기타용)", "ready": SEL_TC_WRITE_DONE, "fill": _fill_tax_clearance},
}


def _capture_popup(context, page) -> tuple[bytes, str, str]:
    """[출력] → 위·변조 경고 [예] → clipreport 팝업에서 PDF(실패 시 PNG) 회수."""
    page.locator(SEL_FIRST_PRINT).click(timeout=20000)
    time.sleep(1.5)

    with context.expect_page(timeout=30000) as popup_info:
        page.locator(SEL_WARN_YES).click(timeout=15000)
    popup = popup_info.value

    popup.wait_for_load_state("domcontentloaded", timeout=30000)
    time.sleep(5.0)  # 리포트 뷰어 렌더 대기
    print(f"[+] 팝업: {popup.url}")

    # 인쇄 대화상자를 띄우지 않고 CDP 로 바로 PDF 생성
    try:
        cdp = context.new_cdp_session(popup)
        res = cdp.send("Page.printToPDF", {"printBackground": True, "preferCSSPageSize": True})
        return base64.b64decode(res["data"]), "cert.pdf", "application/pdf"
    except Exception as exc:  # noqa: BLE001
        print(f"[!] printToPDF 실패, PNG 로 대체: {exc.__class__.__name__}: {exc}")
        png = popup.screenshot(full_page=True, timeout=20000)
        return png, "cert.png", "image/png"
    finally:
        # 부착 모드는 브라우저를 닫지 않으므로 뷰어 팝업이 쌓이지 않게 닫는다
        popup.close()


def issue_certificate(context, page, job: dict) -> tuple[bytes, str, str, str]:
    """로그인된 홈택스 탭에서 신청 → 발급 → 출력 팝업 → 파일 회수.

    로그인 방식(자동 로그인 / 이미 로그인된 브라우저에 부착)과 무관한 공통 구간.
    증명원별로 다른 것은 카탈로그 제목·신청 화면 채우기뿐이고, 접수 모달
    (UTECAAA0A016)부터 출력까지는 같다.
    """
    spec = CERT_SPECS.get(job["cert_type"])
    if spec is None:
        raise RuntimeError(f"미지원 cert_type: {job['cert_type']} (지원: {list(CERT_SPECS)})")
    spec = {**spec, "type": job["cert_type"]}

    _goto_application(page, spec)

    picked = spec["fill"](page, job)

    # "신청하시겠습니까?" → 신청하기
    page.locator(SEL_MODAL_SUBMIT).click(timeout=20000)
    time.sleep(2.0)
    # "정상적으로 접수되었습니다" → 확인. 납세증명은 이 모달 없이 완료 화면으로 바로 간다
    _click_soft(page, SEL_MODAL_CONFIRM, "접수 확인 모달")
    print("[+] 접수 완료")
    time.sleep(2.0)

    page.locator(SEL_GOTO_RESULT).click(timeout=20000)
    time.sleep(3.0)
    page.locator(SEL_RESULT_SEARCH).click(timeout=20000)
    time.sleep(3.0)

    # 첫 행(최신 접수)이 방금 신청한 증명원인지 확인 — 다른 증명원을 출력하지 않게
    first_row = page.locator(SEL_FIRST_PRINT).locator("xpath=ancestor::li[1]").inner_text(timeout=20000)
    if spec["title"] not in first_row:
        raise RuntimeError(f"결과조회 첫 행이 {spec['title']} 아님: {first_row[:80]!r}")

    data, filename, mime = _capture_popup(context, page)
    return data, filename, mime, f"issued for {picked}"


def _find_hometax_page(context):
    """부착한 브라우저에서 홈택스 본 탭을 고른다 (clipreport 뷰어 팝업 제외)."""
    candidates = [
        pg for pg in context.pages
        if "hometax.go.kr" in pg.url and "sesw.hometax.go.kr" not in pg.url
    ]
    if not candidates:
        urls = [pg.url for pg in context.pages]
        raise RuntimeError(f"홈택스 탭 없음. 열린 탭: {urls}")
    page = candidates[-1]
    page.bring_to_front()
    if page.get_by_text("로그아웃").count() == 0:
        print("[!] '로그아웃' 버튼이 안 보임 — 로그인 상태가 아닐 수 있음")
    return page


MIN_WINDOW_WIDTH = 1600  # 1200px 에선 홈택스가 상단 메뉴를 접어 '사업장현황' 이 안 보인다 (2026-09-22 실측)


def _ensure_wide_window(page) -> None:
    """부착한 창이 좁으면 넓힌다. 좁은 창에선 _goto_application 의 상단 메뉴 경로가 막힌다."""
    if page.evaluate("innerWidth") >= MIN_WINDOW_WIDTH:
        return
    cdp = page.context.new_cdp_session(page)
    wid = cdp.send("Browser.getWindowForTarget")["windowId"]
    cdp.send("Browser.setWindowBounds", {
        "windowId": wid,
        "bounds": {"windowState": "normal", "width": MIN_WINDOW_WIDTH, "height": 1000},
    })
    time.sleep(1.0)
    print(f"[*] 창 폭을 {MIN_WINDOW_WIDTH}px 로 넓힘")


def execute_attached(job: dict, cdp_url: str) -> tuple[bytes, str, str, str]:
    """개발용 — 사용자가 이미 로그인해 둔 Chrome 에 CDP 로 붙어 발급.

    로그인 단계를 매번 건너뛰어 발급 구간만 빠르게 반복한다. 브라우저·탭은
    사용자 것이므로 닫지 않고 연결만 끊는다 (with 블록 종료 시 disconnect).
    """
    from playwright.sync_api import sync_playwright  # noqa: WPS433

    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(cdp_url)
        context = browser.contexts[0]
        page = _find_hometax_page(context)
        print(f"[+] 부착: {page.url}")
        _ensure_wide_window(page)
        try:
            return issue_certificate(context, page, job)
        except Exception as exc:  # noqa: BLE001
            path = _dump(page, "fail_attach")
            raise RuntimeError(f"{exc.__class__.__name__}: {exc} | dump={path}") from exc


def execute_phase1(job: dict, cfg: AgentConfig) -> tuple[bytes, str, str, str]:
    """홈택스 로그인 → 사업자등록증명 신청 → 발급 → 출력 팝업 → 파일 회수."""
    _sys_path_add_phase1()
    from playwright.sync_api import sync_playwright  # noqa: WPS433

    from hometax_login import HometaxCredentials, login  # type: ignore

    creds = HometaxCredentials(
        user_id=cfg.hometax_id,
        user_pw=cfg.hometax_pw,
        rrn_prefix=cfg.hometax_rrn_prefix,
        rrn_suffix=cfg.hometax_rrn_suffix,
    )

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=100)
        context = browser.new_context(
            accept_downloads=True,
            locale="ko-KR",
            timezone_id="Asia/Seoul",
            viewport={"width": 1440, "height": 900},
        )
        try:
            page = context.new_page()
            login(page, creds)
            print("[+] login ok")
            time.sleep(2.0)

            return issue_certificate(context, page, job)
        except Exception as exc:  # noqa: BLE001
            path = _dump(page, "fail_flow")
            raise RuntimeError(f"{exc.__class__.__name__}: {exc} | dump={path}") from exc
        finally:
            context.close()
            browser.close()


def execute(job: dict, cfg: AgentConfig) -> tuple[bytes, str, str, str]:
    """(file_bytes, filename, mime, message)"""
    if MODE == "phase1":
        return execute_phase1(job, cfg)
    return execute_dummy(job, cfg)
