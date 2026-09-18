"""홈택스 아이디 로그인 헬퍼.

- 콘솔에서 자격증명 입력 (파일·환경변수 저장 없음)
- 홈택스 아이디 로그인 + 2차 인증(주민번호 앞6자리·뒤1자리) 자동 처리
- login.py · issue.py 등 여러 스크립트에서 재사용
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from getpass import getpass

from playwright.sync_api import Page


@dataclass
class HometaxCredentials:
    user_id: str
    user_pw: str
    rrn_prefix: str  # 주민번호 앞 6자리
    rrn_suffix: str  # 주민번호 뒤 1자리 (성별)


def prompt_credentials() -> HometaxCredentials:
    return HometaxCredentials(
        user_id=input("홈택스 아이디: ").strip(),
        user_pw=getpass("비밀번호: "),
        rrn_prefix=getpass("2차 인증 주민번호 앞 6자리: ").strip(),
        rrn_suffix=getpass("2차 인증 주민번호 뒤 1자리 (성별): ").strip(),
    )


def login(page: Page, creds: HometaxCredentials) -> None:
    """홈택스 메인 → 아이디 로그인 → 2차 인증까지 자동 완료.

    성공 시 페이지가 홈택스 개인/사업자 홈 (index_pp.xml, 로그인 상태) 에 도달.
    """
    page.goto("https://www.hometax.go.kr/", wait_until="domcontentloaded")
    time.sleep(2.0)

    # 헤더 [로그인] → 로그인 페이지
    page.get_by_role("link", name="로그인").first.click()
    time.sleep(1.5)

    # 로그인 페이지 default 탭은 '금융·공동 인증' → '아이디 로그인' 탭 선택
    page.locator("a[title='아이디 로그인']").first.click()
    time.sleep(1.0)

    id_field = page.locator("input[name='iptUserId']:visible").first
    id_field.wait_for(state="visible", timeout=10000)
    id_field.fill(creds.user_id)
    page.locator("input[name='iptUserPw']:visible").first.fill(creds.user_pw)

    # 로그인 버튼 (간편인증과 클래스 공유해 title로 좁힘)
    page.locator("a.logingbtn[title='로그인']").click()

    # 2차 인증 팝업 자동 처리 (WebSquare change/blur 이벤트 대응)
    jumin1 = page.locator("input[name='iptUserJuminNo1']:visible").first
    jumin1.wait_for(state="visible", timeout=10000)
    jumin1.click()
    jumin1.press_sequentially(creds.rrn_prefix, delay=80)
    jumin1.press("Tab")

    jumin2 = page.locator("input[name='iptUserJuminNo2']:visible").first
    jumin2.click()
    jumin2.press_sequentially(creds.rrn_suffix, delay=80)
    jumin2.press("Tab")
    time.sleep(0.5)

    page.locator(
        "#mf_txppWframe_UTXPPABC12_wframe .sec_loginbtn input[value='확인']"
    ).click()
    time.sleep(3.0)
