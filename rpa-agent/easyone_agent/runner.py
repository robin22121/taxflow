"""작업 처리 루프 — 서버에 작업을 묻고, 위하고에 올리고, 결과를 회신한다."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from pathlib import Path

from easyone_agent.api import (
    IMPORT_ALL,
    IMPORT_CLIENT,
    MONTHLY_PRODUCTION,
    WEHAGO_BUSINESS_INPUT,
    EasyoneApi,
    Job,
)
from easyone_agent.company import company_matches
from easyone_agent.import_runner import process_import
from easyone_agent.logmask import mask_text
from easyone_agent.pace import job_gap_sec
from easyone_agent.wehago import CompanyMismatch, LoginFailed, WehagoError, WehagoUploader

WEHAGO_PAYROLL_INPUT = "WEHAGO_PAYROLL_INPUT"

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
    if job.kind == MONTHLY_PRODUCTION:
        return _process_monthly_production_job(api, uploader, job)
    if job.kind == WEHAGO_PAYROLL_INPUT:
        return _process_payroll_input_job(api, uploader, job, workdir)
    if job.kind == WEHAGO_BUSINESS_INPUT:
        return _process_business_input_job(api, uploader, job, workdir)
    _report(api, job.id, False, f"[미구현] '{job.kind}' 작업은 아직 자동화가 없습니다 — 수동으로 처리하세요.")
    return True


def _process_payroll_input_job(api: EasyoneApi, uploader: WehagoUploader, job: Job, workdir: Path) -> bool:
    xlsx_path = workdir / f"{job.id}.xlsx"
    try:
        if job.pay_date is None:
            raise WehagoError("지급일이 없어 위하고 급여자료입력 조회를 할 수 없습니다")
        xlsx_path.write_bytes(api.download_payroll_excel(job.id))
        uploader.ensure_logged_in()
        found_name, found_number = uploader.open_payroll_screen(job.business_number, job.period)
        if not company_matches(job.business_name, job.business_number, found_name, found_number):
            raise CompanyMismatch(
                f"위하고 수임처가 다릅니다: 요청 {job.business_name}({job.business_number}), "
                f"화면 {found_name}({found_number})"
            )
        message = uploader.upload_payroll(xlsx_path, job.period, job.pay_date)
    except LoginFailed as e:
        _report(api, job.id, False, f"위하고 로그인 실패: {e}")
        raise
    except Exception as e:
        logger.exception("작업 실패 %s", job.id)
        if not isinstance(e, WehagoError):
            capture = getattr(uploader, "save_failure_screenshot", None)
            if capture:
                capture(f"failed-{job.id}")
        _report(api, job.id, False, failure_message(e, uploader))
    else:
        _report(api, job.id, True, message)
    finally:
        # 급여파일은 개인정보라 PC에 남기지 않는다.
        xlsx_path.unlink(missing_ok=True)
    return True


def _process_business_input_job(api: EasyoneApi, uploader: WehagoUploader, job: Job, workdir: Path) -> bool:
    """사업소득자료입력(SmartA SWBU0102) 자동입력 — 게이트 1 (plan/16 §13-3-4).

    `_process_payroll_input_job`과 같은 구조지만 지급일 없이 귀속연월만 필요하다
    (`upload_business_income`이 `pay_date` 인자를 받지 않음, §13-3 실기 확인).
    """
    xlsx_path = workdir / f"{job.id}-business.xlsx"
    try:
        xlsx_path.write_bytes(api.download_business_income_excel(job.id))
        uploader.ensure_logged_in()
        found_name, found_number = uploader.open_business_income_screen(job.business_number)
        if not company_matches(job.business_name, job.business_number, found_name, found_number):
            raise CompanyMismatch(
                f"위하고 수임처가 다릅니다: 요청 {job.business_name}({job.business_number}), "
                f"화면 {found_name}({found_number})"
            )
        message = uploader.upload_business_income(job.period, xlsx_path)
    except LoginFailed as e:
        _report(api, job.id, False, f"위하고 로그인 실패: {e}")
        raise
    except Exception as e:
        logger.exception("작업 실패 %s", job.id)
        if not isinstance(e, WehagoError):
            capture = getattr(uploader, "save_failure_screenshot", None)
            if capture:
                capture(f"failed-{job.id}")
        _report(api, job.id, False, failure_message(e, uploader))
    else:
        _report(api, job.id, True, message)
    finally:
        xlsx_path.unlink(missing_ok=True)
    return True


def failure_message(e: Exception, uploader: object) -> str:
    """사무소 사용자가 읽을 실패 안내 — 어느 단계였는지, 위하고에 저장됐는지, 다음에 할 일.

    WehagoError 는 이미 사람이 읽을 문장이다. 그 밖의 오류(화면 대기 시간 초과 등)는
    기술 메시지 대신 단계·저장 여부로 풀어 쓰고, 기술 정보는 괄호에 짧게만 남긴다.
    """
    step = getattr(uploader, "step", "")
    where = f"[{step}] " if step else ""
    if isinstance(e, WehagoError):
        return f"{where}{e}"
    if getattr(uploader, "may_have_saved", False):
        saved = "위하고에 저장됐을 수 있으니 급여자료입력 화면에서 확인한 뒤 필요하면 다시 전송하세요."
    else:
        saved = "위하고에는 저장되지 않았습니다. 잠시 후 다시 전송하고, 반복되면 담당자에게 알려 주세요."
    # 실패 순간 화면에 안 닫힌 안내 팝업이 남아있으면 원인 파악이 훨씬 빨라진다 (§1-5 "두더지잡기").
    has_dialog = getattr(uploader, "has_open_dialog", None)
    dialog_hint = " 화면에 안 닫힌 안내 팝업(공지·2차 인증 등)이 떠 있었을 수 있습니다." if has_dialog and has_dialog() else ""
    return (
        f"{where}위하고 화면이 예상과 달라 멈췄습니다 (응답 지연 또는 화면 변경).{dialog_hint} {saved} "
        f"(기술 정보: {type(e).__name__})"
    )


def _process_monthly_production_job(api: EasyoneApi, uploader: WehagoUploader, job: Job) -> bool:
    """제작(게이트 2) — 현재는 위하고 마감(원천세·사업소득·지방세)까지만 자동화
    (plan/16 §4-4 ⑨-a·⑨-b·⑩-a).

    전자신고 파일 제작(F4, ⑨-c·⑩-b)은 Windows 전용 위하고 로컬 모듈이 필요해 이 macOS
    에이전트에서는 못 한다. 홈택스(⑪)·위택스(⑫)는 아직 자동화가 없다. 지방세 마감은
    아직 실제 화면으로 실측하지 못한 최초 실행이라 실패할 수 있다(close_local_tax_payment
    docstring 참고) — 이후 단계는 완료 메시지에서 수동 처리를 안내한다.
    """
    # 중간에 실패해도 그 전까지 성공한 단계는 남긴다 — §4-1 "명세서 추가입력 포함 완료 판정"
    # (2026-10-01 결정: close_business_income_report의 "새로불러오기"가 명세서 추가입력을
    # 충족한다고 보고, 이 단계가 실제 성공했는지를 step_progress로 서버에 남긴다).
    step_progress: dict[str, str] = {}
    try:
        uploader.ensure_logged_in()
        wht_text = uploader.close_wht_return(job.business_number, job.period)
        step_progress["wehago_income_tax"] = "done"
        biz_text = uploader.close_business_income_report(job.business_number, job.period)
        step_progress["wehago_business_income"] = "done"
        local_text = uploader.close_local_tax_payment(job.business_number, job.period)
        step_progress["wehago_local_tax"] = "done"
    except LoginFailed as e:
        _report(api, job.id, False, f"위하고 로그인 실패: {e}")
        raise
    except Exception as e:
        logger.exception("제작(마감) 실패 %s", job.id)
        if not isinstance(e, WehagoError):
            capture = getattr(uploader, "save_failure_screenshot", None)
            if capture:
                capture(f"failed-{job.id}")
        _report(api, job.id, False, failure_message(e, uploader), step_progress=step_progress)
    else:
        _report(
            api,
            job.id,
            True,
            f"위하고 마감 완료 — 원천세: {wht_text} / 사업소득: {biz_text} / 지방세: {local_text}. "
            "전자신고 파일 제작(F4)·홈택스·위택스 신고는 아직 자동화되지 않아 "
            "Windows 노트북·수동으로 진행하세요.",
            step_progress=step_progress,
        )
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


def _report(
    api: EasyoneApi,
    job_id: str,
    succeeded: bool,
    message: str,
    step_progress: dict[str, str] | None = None,
) -> None:
    try:
        # 서버 감사 로그에도 비밀번호·주민번호는 남기지 않는다 (§8-1).
        api.report(job_id, succeeded, mask_text(message)[:2000], step_progress=step_progress)
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
        # 작업을 끝냈으면 사람 속도로 쉬었다가 다음 작업을 받는다 (위하고는 신중하게, §8-4).
        sleep(job_gap_sec("wehago") if processed else poll_interval_sec)
