"""잡 실행 — 홈택스 발급 실행.

첫 스캐폴드에서는 Phase 1 코드가 완전 자동화되기 전까지 두 가지 모드 지원:

- `dummy`: 실제 홈택스 접속 없이 placeholder PNG 반환. 서버-에이전트 통신·저장 흐름 검증용.
- `phase1`: rpa/certificate-poc/ 의 hometax_login 을 재사용해 실제 로그인·[출력] 팝업 캡처.
           카탈로그→신청→발급 단계는 Phase 1 자동화 완료 후 붙임.

기본값은 CERT_AGENT_MODE 환경변수 (`dummy` | `phase1`).
"""

from __future__ import annotations

import base64
import os
import sys
import time
from pathlib import Path

from certificate_agent.config import AgentConfig

MODE = os.environ.get("CERT_AGENT_MODE", "dummy")

DUMMY_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk"
    "+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)


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


def execute_phase1(job: dict, cfg: AgentConfig) -> tuple[bytes, str, str, str]:
    """Phase 1 코드 재사용 — 실제 홈택스 로그인·[출력] 팝업 캡처.

    현재 카탈로그→신청→발급 단계는 미완이므로, 사용자가 이미 발급해둔
    이력의 첫 [출력] 버튼을 자동 클릭해 결과 PNG 를 확보한다.
    """
    _sys_path_add_phase1()
    from playwright.sync_api import sync_playwright  # noqa: WPS433

    from hometax_login import HometaxCredentials, login  # type: ignore

    creds = HometaxCredentials(
        user_id=cfg.hometax_id,
        user_pw=cfg.hometax_pw,
        rrn_prefix=cfg.hometax_rrn_prefix,
        rrn_suffix=cfg.hometax_rrn_suffix,
    )

    OUT = Path(__file__).resolve().parent.parent / "work"
    OUT.mkdir(exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=100)
        context = browser.new_context(
            accept_downloads=True,
            locale="ko-KR",
            timezone_id="Asia/Seoul",
            viewport={"width": 1440, "height": 900},
        )

        captured: list[bytes] = []

        def on_popup(popup) -> None:
            try:
                popup.wait_for_load_state("domcontentloaded", timeout=15000)
                time.sleep(4.0)
                png = OUT / "popup.png"
                popup.screenshot(path=str(png), full_page=True, timeout=10000)
                captured.append(png.read_bytes())
            except Exception as exc:  # noqa: BLE001
                print(f"[!] popup capture failed: {exc}")

        context.on("page", on_popup)

        page = context.new_page()
        login(page, creds)
        time.sleep(2.0)

        # 홈 → 카탈로그
        page.locator("#taKndSvcAllA3").click(timeout=10000)
        time.sleep(3.0)

        # ⚠️ 카탈로그→신청→발급 자동화 미완: 결과 조회 페이지의 첫 이력 [출력]으로 대체
        # (사용자가 미리 발급해둔 이력이 있어야 성공)
        # TODO: Phase 1 완전 자동화 후 여기서 신청→발급 클릭 추가
        FIRST_OUTPUT_BTN = "#mf_txppWframe_gen_cvaInf_0_btn_cvaDcumGranMthdNm"
        try:
            page.locator(FIRST_OUTPUT_BTN).click(timeout=10000)
        except Exception:
            # 카탈로그에 머물러 있으면 결과 조회 페이지로 이동 시도
            pass

        # 팝업 이벤트 처리 tick
        for _ in range(30):
            page.wait_for_timeout(500)
            if captured:
                break

        context.close()
        browser.close()

    if not captured:
        raise RuntimeError("popup capture failed — 사용자 이력 확인 필요")

    return captured[0], "cert.png", "image/png", "phase1 popup captured"


def execute(job: dict, cfg: AgentConfig) -> tuple[bytes, str, str, str]:
    """(file_bytes, filename, mime, message)"""
    if MODE == "phase1":
        return execute_phase1(job, cfg)
    return execute_dummy(job, cfg)
