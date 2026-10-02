"""원천징수 전자신고(SWER0101) 파일 제작 수동 테스트 스크립트 (2026-10-02).

`WehagoUploader.produce_wht_efile`을 실행 작업 큐 없이 바로 호출해본다 — 지급기간
입력부터 [전자신고 파일 제작(Enter)] 클릭까지 전부 시도하고, 맥에서 막히면
WehagoError로 그 자리에서 알려준다.

실행 (먼저 scripts/start-chrome.ps1 로 크롬 띄우고 위하고에 로그인한 상태):
    uv run python scripts/produce_wht_efile.py --business 2240238407 --period 2026-09 --password abc12345
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# 이 프로젝트는 easyone_agent를 설치 패키지로 등록하지 않는다(pyproject.toml에 빌드
# 설정 없음) — 스크립트를 직접 실행하면 그 디렉토리(scripts/)만 sys.path에 잡혀
# "ModuleNotFoundError: No module named 'easyone_agent'"가 난다(2026-10-02 실기
# 확인). 상위(rpa-agent/) 디렉토리를 직접 추가해 실행 위치·방식과 무관하게 동작하게 한다.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from easyone_agent.config import (
    SECRET_WEHAGO_ID,
    SECRET_WEHAGO_PASSWORD,
    get_secret,
    load_config,
)
from easyone_agent.wehago import WehagoUploader


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--business", required=True, help="사업자번호 (하이픈 있어도 됨)")
    parser.add_argument("--period", required=True, help="지급연월 YYYY-MM")
    parser.add_argument("--password", required=True, help="변환파일 비밀번호 (영문 소문자+숫자 8~15자)")
    args = parser.parse_args()

    config = load_config()
    with WehagoUploader(
        user_id=get_secret(SECRET_WEHAGO_ID),
        password=get_secret(SECRET_WEHAGO_PASSWORD),
        cdp_url=config.cdp_url,
        screenshot_dir=config.screenshot_dir,
    ) as uploader:
        uploader.ensure_logged_in()
        result = uploader.produce_wht_efile(args.business, args.period, args.password)
        print(result)


if __name__ == "__main__":
    main()
