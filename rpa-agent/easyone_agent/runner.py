"""작업 처리 루프 — 서버에 작업을 묻고, 위하고에 올리고, 결과를 회신한다."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from pathlib import Path

from easyone_agent.api import IMPORT_ALL, IMPORT_CLIENT, EasyoneApi, Job
from easyone_agent.company import company_matches
from easyone_agent.import_runner import process_import
from easyone_agent.logmask import mask_text
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
    if job.kind in (IMPORT_ALL, IMPORT_CLIENT):
        return _process_import_job(api, uploader, job, workdir)
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


def _process_import_job(api: EasyoneApi, uploader: WehagoUploader, job: Job, workdir: Path) -> bool:
    try:
        succeeded, message = process_import(api, uploader, job, workdir)
    except LoginFailed as e:
        _report(api, job.id, False, f"위하고 로그인 실패: {e}")
        raise
    except Exception as e:
        logger.exception("가져오기 실패 %s", job.id)
        _report(api, job.id, False, f"{type(e).__name__}: {e}")
    else:
        _report(api, job.id, succeeded, message)
    return True


def login_test_one(api: EasyoneApi, uploader: WehagoUploader) -> bool | None:
    """로그인 테스트 — 작업을 한 건 받아 위하고 로그인만 해 보고 회신한다.

    급여파일은 받지 않고 업로드도 하지 않는다. 업로드가 없었으므로 로그인에 성공해도
    SUCCEEDED가 아니라 FAILED로 회신해 작업 기록에 '전송 완료'가 남지 않게 한다.

    Returns:
        작업이 없으면 None, 있으면 로그인 성공 여부.
    """
    job = api.claim()
    if job is None:
        return None

    logger.info("로그인 테스트 시작 %s", job.id)
    try:
        uploader.ensure_logged_in()
    except Exception as e:
        logger.exception("로그인 테스트 실패 %s", job.id)
        _report(api, job.id, False, f"[로그인 테스트] 위하고 로그인 실패 — {type(e).__name__}: {e}")
        return False
    logger.info("로그인 테스트 성공 %s", job.id)
    _report(api, job.id, False, "[로그인 테스트] 위하고 로그인 성공 — 급여 업로드는 하지 않음")
    return True


def run_login_test(
    api: EasyoneApi,
    uploader: WehagoUploader,
    poll_interval_sec: float,
    sleep: Callable[[float], None] = time.sleep,
) -> bool:
    """작업이 들어올 때까지 기다렸다가 한 건만 로그인 테스트하고 끝낸다."""
    while True:
        try:
            result = login_test_one(api, uploader)
        except Exception:
            logger.exception("작업 요청 실패")
            result = None
        if result is not None:
            return result
        sleep(poll_interval_sec)


def _report(api: EasyoneApi, job_id: str, succeeded: bool, message: str) -> None:
    try:
        # 서버 감사 로그에도 비밀번호·주민번호는 남기지 않는다 (§8-1).
        api.report(job_id, succeeded, mask_text(message)[:2000])
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
