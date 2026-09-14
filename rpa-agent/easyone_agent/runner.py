"""작업 처리 루프 — 서버에 작업을 묻고, 위하고에 올리고, 결과를 회신한다."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from pathlib import Path

from easyone_agent.api import EasyoneApi
from easyone_agent.company import company_matches
from easyone_agent.wehago import CompanyMismatch, LoginFailed, WehagoUploader

logger = logging.getLogger(__name__)


def process_one(api: EasyoneApi, uploader: WehagoUploader, workdir: Path) -> bool:
    """작업이 있으면 한 건 처리하고 True를 돌려준다.

    어떤 실패든 서버에 FAILED로 회신한다. 단 LoginFailed는 계정 잠금을 막기 위해
    회신 뒤 호출자에게 다시 올린다.
    """
    job = api.claim()
    if job is None:
        return False

    logger.info("작업 시작 %s %s %s", job.id, job.business_name, job.period)
    xlsx_path = workdir / f"{job.id}.xlsx"
    try:
        xlsx_path.write_bytes(api.download_payroll_excel(job.id))
        uploader.ensure_logged_in()
        found_name, found_number = uploader.open_company(job.business_number)
        if not company_matches(job.business_name, job.business_number, found_name, found_number):
            raise CompanyMismatch(
                f"위하고 수임처가 다릅니다: 요청 {job.business_name}({job.business_number}), "
                f"화면 {found_name}({found_number})"
            )
        message = uploader.upload_payroll(xlsx_path, job.period)
    except LoginFailed as e:
        _report(api, job.id, False, f"위하고 로그인 실패: {e}")
        raise
    except Exception as e:
        logger.exception("작업 실패 %s", job.id)
        _report(api, job.id, False, f"{type(e).__name__}: {e}")
    else:
        _report(api, job.id, True, message)
    finally:
        # 급여파일은 개인정보라 PC에 남기지 않는다.
        xlsx_path.unlink(missing_ok=True)
    return True


def _report(api: EasyoneApi, job_id: str, succeeded: bool, message: str) -> None:
    try:
        api.report(job_id, succeeded, message[:2000])
    except Exception:
        # 회신이 실패해도 서버가 시간 초과로 FAILED 처리하므로 루프는 계속 돈다.
        logger.exception("결과 회신 실패 %s", job_id)


def run_forever(
    api: EasyoneApi,
    uploader: WehagoUploader,
    workdir: Path,
    poll_interval_sec: float,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    """작업을 계속 처리한다. LoginFailed가 나면 멈춘다 — 틀린 비밀번호로 반복하면 계정이 잠긴다."""
    workdir.mkdir(parents=True, exist_ok=True)
    while True:
        try:
            processed = process_one(api, uploader, workdir)
        except LoginFailed:
            logger.error("위하고 로그인 실패로 에이전트를 멈춥니다. 자격 증명 확인 후 다시 실행하세요.")
            return
        except Exception:
            # 서버 연결 끊김 등 — 잠시 뒤 다시 묻는다.
            logger.exception("작업 요청 실패")
            processed = False
        if not processed:
            sleep(poll_interval_sec)
