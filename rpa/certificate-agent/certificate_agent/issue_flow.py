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


def _fill_application(page, job: dict) -> str:
    """신청 화면을 채우고 [작성완료] 까지. 선택된 사업자 라벨 반환."""
    page.wait_for_selector(SEL_BSNO, timeout=30000)
    time.sleep(1.0)

    # 납세자 구분 = 사업자등록번호 (기본값이지만 명시)
    page.locator(SEL_TAXPAYER_CL_BSNO).click(timeout=10000)
    time.sleep(0.5)

    picked = _pick_business_number(page, job["business_number"])
    print(f"[+] 사업자 선택: {picked}")
    time.sleep(1.5)  # 상호·대표자명 자동 채움 대기

    page.locator(SEL_KOREAN_CERT).click(timeout=10000)
    page.select_option(SEL_USE_PURPOSE, label=USE_PURPOSE_LABEL)
    page.select_option(SEL_SUBMIT_ORG, label=SUBMIT_ORG_LABEL)

    # 주민등록번호 공개여부 — 요청 옵션이 유일한 사용자 선택 항목
    rrn_disclosed = bool((job.get("options") or {}).get("rrn_disclosed", False))
    page.locator(SEL_RRN_OPEN if rrn_disclosed else SEL_RRN_HIDDEN).click(timeout=10000)
    print(f"[+] 주민등록번호 {'공개' if rrn_disclosed else '비공개'}")

    page.select_option(SEL_RECEIVE_METHOD, label=RECEIVE_METHOD_LABEL)
    time.sleep(0.5)

    page.locator(SEL_WRITE_DONE).click(timeout=10000)
    return picked


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

            page.goto(BUSINESS_REG_URL, wait_until="domcontentloaded")
            time.sleep(3.0)

            picked = _fill_application(page, job)

            # "신청하시겠습니까?" → 신청하기
            page.locator(SEL_MODAL_SUBMIT).click(timeout=20000)
            time.sleep(2.0)
            # "정상적으로 접수되었습니다" → 확인
            page.locator(SEL_MODAL_CONFIRM).click(timeout=20000)
            print("[+] 접수 완료")
            time.sleep(2.0)

            page.locator(SEL_GOTO_RESULT).click(timeout=20000)
            time.sleep(3.0)
            page.locator(SEL_RESULT_SEARCH).click(timeout=20000)
            time.sleep(3.0)

            data, filename, mime = _capture_popup(context, page)
            return data, filename, mime, f"issued for {picked}"
        finally:
            context.close()
            browser.close()


def execute(job: dict, cfg: AgentConfig) -> tuple[bytes, str, str, str]:
    """(file_bytes, filename, mime, message)"""
    if MODE == "phase1":
        return execute_phase1(job, cfg)
    return execute_dummy(job, cfg)
