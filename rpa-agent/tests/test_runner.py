from __future__ import annotations

from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest

from easyone_agent.api import MONTHLY_PRODUCTION, WEHAGO_BUSINESS_INPUT, WEHAGO_OTHER_INPUT, Job
from easyone_agent.runner import login_test_one, process_one, run_forever, run_login_test
from easyone_agent.wehago import LoginFailed, WehagoError

JOB = Job(
    id="job1",
    client_id="c1",
    period="2026-08",
    business_number="123-45-67890",
    business_name="(주)하늘식품",
    pay_date=date(2026, 9, 10),
)


class FakeApi:
    def __init__(self, jobs: list[Job], report_error: Exception | None = None) -> None:
        self.jobs = list(jobs)
        self.reports: list[tuple[str, bool, str]] = []
        self.step_progress_by_job: dict[str, dict] = {}
        self.report_error = report_error

    def claim(self) -> Job | None:
        return self.jobs.pop(0) if self.jobs else None

    def download_payroll_excel(self, job_id: str) -> bytes:
        return b"fake-xlsx"

    def download_business_income_excel(self, job_id: str) -> bytes:
        return b"fake-business-xlsx"

    def download_other_income_excel(self, job_id: str) -> bytes:
        return b"fake-other-income-xlsx"

    def report(self, job_id: str, succeeded: bool, message: str, step_progress: dict | None = None) -> None:
        if self.report_error:
            raise self.report_error
        self.reports.append((job_id, succeeded, message))
        if step_progress is not None:
            self.step_progress_by_job[job_id] = step_progress


class FakeUploader:
    def __init__(
        self,
        company: tuple[str, str] = ("주식회사 하늘식품", "1234567890"),
        login_error: Exception | None = None,
        upload_error: Exception | None = None,
        close_wht_error: Exception | None = None,
        close_business_error: Exception | None = None,
        produce_efile_error: Exception | None = None,
    ) -> None:
        self.company = company
        self.login_error = login_error
        self.upload_error = upload_error
        self.close_wht_error = close_wht_error
        self.close_business_error = close_business_error
        self.produce_efile_error = produce_efile_error
        self.uploaded: list[tuple[Path, str, date]] = []
        self.business_uploaded: list[tuple[Path, str]] = []
        self.other_income_uploaded: list[tuple[Path, str]] = []
        self.closed: list[tuple[str, str]] = []
        self.efile_produced: list[tuple[str, str, str]] = []

    def ensure_logged_in(self) -> None:
        if self.login_error:
            raise self.login_error

    def open_payroll_screen(self, business_number: str, period: str) -> tuple[str, str]:
        return self.company

    def upload_payroll(self, xlsx_path: Path, period: str, pay_date: date) -> str:
        assert xlsx_path.read_bytes() == b"fake-xlsx"
        if self.upload_error:
            raise self.upload_error
        self.uploaded.append((xlsx_path, period, pay_date))
        return "3명 업로드 완료"

    def open_business_income_screen(self, business_number: str) -> tuple[str, str]:
        return self.company

    def upload_business_income(self, period: str, xlsx_path: Path) -> str:
        assert xlsx_path.read_bytes() == b"fake-business-xlsx"
        if self.upload_error:
            raise self.upload_error
        self.business_uploaded.append((xlsx_path, period))
        return "사업소득 2명 업로드 완료"

    def open_other_income_screen(self, business_number: str) -> tuple[str, str]:
        return self.company

    def upload_other_income(self, period: str, xlsx_path: Path) -> str:
        assert xlsx_path.read_bytes() == b"fake-other-income-xlsx"
        if self.upload_error:
            raise self.upload_error
        self.other_income_uploaded.append((xlsx_path, period))
        return "기타소득 1명 업로드 완료"

    def close_wht_return(self, business_number: str, period: str) -> str:
        if self.close_wht_error:
            raise self.close_wht_error
        self.closed.append(("wht", period))
        return "마감 완료!"

    def close_business_income_report(self, business_number: str, period: str) -> str:
        if self.close_business_error:
            raise self.close_business_error
        self.closed.append(("business", period))
        return "마감할 데이터가 존재하지 않습니다 (건너뜀)"

    def produce_wht_efile(self, business_number: str, period: str, password: str) -> str:
        if self.produce_efile_error:
            raise self.produce_efile_error
        self.efile_produced.append((business_number, period, password))
        return "전자신고파일이 생성되었습니다"


def test_no_job_does_nothing(tmp_path: Path):
    api = FakeApi([])
    assert process_one(api, FakeUploader(), tmp_path) is False
    assert api.reports == []


def test_success_reports_message_and_deletes_file(tmp_path: Path):
    api, uploader = FakeApi([JOB]), FakeUploader()
    assert process_one(api, uploader, tmp_path) is True
    assert api.reports == [("job1", True, "3명 업로드 완료")]
    assert uploader.uploaded[0][1:] == ("2026-08", date(2026, 9, 10))
    assert list(tmp_path.iterdir()) == []


def test_missing_pay_date_is_reported_without_upload(tmp_path: Path):
    api, uploader = FakeApi([replace(JOB, pay_date=None)]), FakeUploader()
    assert process_one(api, uploader, tmp_path) is True
    assert uploader.uploaded == []
    assert api.reports[0][1] is False
    assert "지급일이 없어" in api.reports[0][2]


def test_business_input_success_reports_message_and_deletes_file(tmp_path: Path):
    """WEHAGO_BUSINESS_INPUT — 지급일 없이 귀속연월만으로 사업소득자료입력 업로드 (plan/16 §13-3-4)."""
    job = replace(JOB, kind=WEHAGO_BUSINESS_INPUT, pay_date=None)
    api, uploader = FakeApi([job]), FakeUploader()
    assert process_one(api, uploader, tmp_path) is True
    assert api.reports == [("job1", True, "사업소득 2명 업로드 완료")]
    assert uploader.business_uploaded[0][1] == "2026-08"
    assert list(tmp_path.iterdir()) == []


def test_business_input_company_mismatch_is_not_uploaded(tmp_path: Path):
    job = replace(JOB, kind=WEHAGO_BUSINESS_INPUT, pay_date=None)
    api = FakeApi([job])
    uploader = FakeUploader(company=("다른회사", "9999999999"))
    assert process_one(api, uploader, tmp_path) is True
    assert uploader.business_uploaded == []
    assert api.reports[0][1] is False
    assert "위하고 수임처가 다릅니다" in api.reports[0][2]


def test_other_income_input_success_reports_message_and_deletes_file(tmp_path: Path):
    """WEHAGO_OTHER_INPUT — 지급일 없이 귀속연월만으로 기타소득자료입력 업로드 (plan/16 §13-3-3)."""
    job = replace(JOB, kind=WEHAGO_OTHER_INPUT, pay_date=None)
    api, uploader = FakeApi([job]), FakeUploader()
    assert process_one(api, uploader, tmp_path) is True
    assert api.reports == [("job1", True, "기타소득 1명 업로드 완료")]
    assert uploader.other_income_uploaded[0][1] == "2026-08"
    assert list(tmp_path.iterdir()) == []


def test_other_income_input_company_mismatch_is_not_uploaded(tmp_path: Path):
    job = replace(JOB, kind=WEHAGO_OTHER_INPUT, pay_date=None)
    api = FakeApi([job])
    uploader = FakeUploader(company=("다른회사", "9999999999"))
    assert process_one(api, uploader, tmp_path) is True
    assert uploader.other_income_uploaded == []
    assert api.reports[0][1] is False
    assert "위하고 수임처가 다릅니다" in api.reports[0][2]


def test_monthly_production_closes_wht_business_and_produces_efile(tmp_path: Path, monkeypatch):
    """지방세 마감(close_local_tax_payment)은 법정동 입력 문제로 개발 보류 중이라
    호출하지 않는다 (2026-10-02 사용자 결정, 나중에 보완). 원천징수 전자신고 파일
    제작은 마감 다음 단계로 자동 진행된다 (2026-10-02 추가)."""
    monkeypatch.setattr("easyone_agent.runner.get_secret_optional", lambda name: None)
    job = replace(JOB, kind=MONTHLY_PRODUCTION)
    api, uploader = FakeApi([job]), FakeUploader()
    assert process_one(api, uploader, tmp_path) is True
    assert uploader.closed == [("wht", "2026-08"), ("business", "2026-08")]
    assert uploader.efile_produced == [("123-45-67890", "2026-08", "abc12345")]
    job_id, succeeded, message = api.reports[0]
    assert (job_id, succeeded) == ("job1", True)
    assert "마감·제작 완료" in message and "지방세 마감은 자동화 보류" in message
    assert api.step_progress_by_job["job1"] == {
        "wehago_income_tax": "done", "wehago_business_income": "done", "wht_efile": "done",
    }


def test_monthly_production_wht_failure_skips_business_income(tmp_path: Path):
    job = replace(JOB, kind=MONTHLY_PRODUCTION)
    uploader = FakeUploader(close_wht_error=WehagoError("원천세 마감 실패"))
    api = FakeApi([job])
    assert process_one(api, uploader, tmp_path) is True
    assert uploader.closed == []
    job_id, succeeded, message = api.reports[0]
    assert (job_id, succeeded) == ("job1", False)
    assert "원천세 마감 실패" in message
    assert api.step_progress_by_job["job1"] == {}


def test_monthly_production_efile_failure_keeps_close_progress(tmp_path: Path, monkeypatch):
    """제작(전자신고 파일)이 실패해도 그 전에 끝난 마감 단계는 step_progress에 남는다."""
    monkeypatch.setattr("easyone_agent.runner.get_secret_optional", lambda name: None)
    job = replace(JOB, kind=MONTHLY_PRODUCTION)
    uploader = FakeUploader(produce_efile_error=WehagoError("맥에서는 제작을 할 수 없습니다"))
    api = FakeApi([job])
    assert process_one(api, uploader, tmp_path) is True
    assert uploader.closed == [("wht", "2026-08"), ("business", "2026-08")]
    job_id, succeeded, message = api.reports[0]
    assert (job_id, succeeded) == ("job1", False)
    assert "맥에서는 제작을 할 수 없습니다" in message
    assert api.step_progress_by_job["job1"] == {
        "wehago_income_tax": "done", "wehago_business_income": "done",
    }



def test_unimplemented_job_kind_is_reported_without_touching_uploader(tmp_path: Path):
    job = replace(JOB, kind="CERTIFICATE_ISSUE")
    api, uploader = FakeApi([job]), FakeUploader()
    assert process_one(api, uploader, tmp_path) is True
    assert uploader.uploaded == [] and uploader.closed == []
    job_id, succeeded, message = api.reports[0]
    assert (job_id, succeeded) == ("job1", False)
    assert "미구현" in message


def test_company_mismatch_is_not_uploaded(tmp_path: Path):
    api = FakeApi([JOB])
    uploader = FakeUploader(company=("하늘푸드", "1234567890"))
    assert process_one(api, uploader, tmp_path) is True
    assert uploader.uploaded == []
    job_id, succeeded, message = api.reports[0]
    assert (job_id, succeeded) == ("job1", False)
    assert "수임처가 다릅니다" in message
    assert list(tmp_path.iterdir()) == []


def test_upload_error_is_reported_and_loop_continues(tmp_path: Path):
    api = FakeApi([JOB])
    assert process_one(api, FakeUploader(upload_error=RuntimeError("양식 오류")), tmp_path)
    assert api.reports[0][1] is False
    # 예상 못 한 오류는 기술 메시지 대신 사람이 읽을 안내 + 짧은 기술 정보
    assert "위하고에는 저장되지 않았습니다" in api.reports[0][2]
    assert "기술 정보: RuntimeError" in api.reports[0][2]


def test_login_failure_is_reported_then_raised(tmp_path: Path):
    api = FakeApi([JOB])
    with pytest.raises(LoginFailed):
        process_one(api, FakeUploader(login_error=LoginFailed("비밀번호 불일치")), tmp_path)
    assert api.reports[0][1] is False
    assert "로그인 실패" in api.reports[0][2]


def test_report_failure_does_not_crash(tmp_path: Path):
    api = FakeApi([JOB], report_error=RuntimeError("network down"))
    assert process_one(api, FakeUploader(), tmp_path) is True


def test_run_forever_stops_on_login_failure(tmp_path: Path):
    api = FakeApi([JOB, JOB])
    sleeps: list[float] = []
    run_forever(
        api,
        FakeUploader(login_error=LoginFailed("잠김")),
        tmp_path / "work",
        5,
        sleep=sleeps.append,
    )
    assert len(api.reports) == 1  # 두 번째 작업은 시도하지 않는다
    assert sleeps == []


class _Stop(Exception):
    pass


def test_run_forever_stops_for_update_when_available(tmp_path: Path):
    api = FakeApi([])
    clock = iter([0.0, 100.0])  # now() 두 번째 호출에서 interval(10) 경과로 판정

    def sleep(sec: float) -> None:
        raise AssertionError("업데이트가 있으면 sleep 전에 멈춰야 한다")

    reason = run_forever(
        api,
        FakeUploader(),
        tmp_path / "work",
        5,
        sleep=sleep,
        update_check_interval_sec=10,
        update_available=lambda: True,
        now=lambda: next(clock),
    )
    assert reason == "update_available"


def test_run_forever_ignores_update_before_interval_elapses(tmp_path: Path):
    api = FakeApi([JOB])
    sleeps: list[float] = []

    def sleep(sec: float) -> None:
        sleeps.append(sec)
        raise _Stop

    with pytest.raises(_Stop):
        run_forever(
            api,
            FakeUploader(),
            tmp_path / "work",
            5,
            sleep=sleep,
            update_check_interval_sec=10,
            update_available=lambda: True,
            now=lambda: 0.0,  # 경과 시간 0 — 아직 간격이 지나지 않았다
        )
    assert len(sleeps) == 1


def test_run_forever_disabled_update_check_never_calls_it(tmp_path: Path):
    api = FakeApi([JOB])

    def update_available() -> bool:
        raise AssertionError("update_check_interval_sec<=0 이면 호출되면 안 된다")

    def sleep(sec: float) -> None:
        raise _Stop

    with pytest.raises(_Stop):
        run_forever(
            api,
            FakeUploader(),
            tmp_path / "work",
            5,
            sleep=sleep,
            update_check_interval_sec=0,
            update_available=update_available,
        )


def test_run_forever_rests_between_jobs(tmp_path: Path):
    """작업을 끝내면 위하고 속도(5~15초)로 쉬고, 일이 없으면 폴링 간격으로 묻는다."""
    api = FakeApi([JOB])
    sleeps: list[float] = []

    def sleep(sec: float) -> None:
        sleeps.append(sec)
        if len(sleeps) == 2:
            raise _Stop

    with pytest.raises(_Stop):
        run_forever(api, FakeUploader(), tmp_path / "work", 5, sleep=sleep)
    assert 5.0 <= sleeps[0] <= 15.0
    assert sleeps[1] == 5


def test_pace_hometax_is_faster_than_wehago():
    from easyone_agent.pace import PACE

    assert PACE["hometax"].think_sec == (0.5, 1.0) and PACE["wetax"].think_sec == (0.5, 1.0)
    assert PACE["hometax"].gap_sec[1] <= 7.0 and PACE["wetax"].gap_sec[1] <= 7.0
    assert PACE["wehago"].gap_sec[0] >= 5.0  # 위하고는 사설 업체 — 신중하게


class NoDownloadApi(FakeApi):
    def download_payroll_excel(self, job_id: str) -> bytes:
        raise AssertionError("로그인 테스트는 급여파일을 받지 않는다")


def test_login_test_success_is_reported_as_failed_without_upload():
    api, uploader = NoDownloadApi([JOB]), FakeUploader()
    assert login_test_one(api, uploader) is True
    assert uploader.uploaded == []
    job_id, succeeded, message = api.reports[0]
    assert (job_id, succeeded) == ("job1", False)  # 업로드가 없었으니 전송 완료로 남기지 않는다
    assert "로그인 성공" in message


def test_login_test_failure_is_reported():
    api = NoDownloadApi([JOB])
    assert login_test_one(api, FakeUploader(login_error=LoginFailed("비밀번호 불일치"))) is False
    assert api.reports[0][1] is False
    assert "로그인 실패" in api.reports[0][2]
    assert "비밀번호 불일치" in api.reports[0][2]


def test_login_test_without_job_does_nothing():
    api = NoDownloadApi([])
    assert login_test_one(api, FakeUploader()) is None
    assert api.reports == []


def test_run_login_test_waits_for_job_then_stops():
    api = NoDownloadApi([])
    sleeps: list[float] = []

    def sleep(sec: float) -> None:
        sleeps.append(sec)
        api.jobs.append(JOB)  # 기다리는 동안 세무사가 전송을 요청했다

    assert run_login_test(api, FakeUploader(), 5, sleep=sleep) is True
    assert sleeps == [5]
    assert len(api.reports) == 1


def test_failure_message_shows_step_and_saved_state():
    from easyone_agent.runner import failure_message
    from easyone_agent.wehago import WehagoError

    class U:
        step = "사원코드 연결·저장"
        may_have_saved = True

    assert failure_message(WehagoError("위하고 사원과 맞지 않음"), U()) == "[사원코드 연결·저장] 위하고 사원과 맞지 않음"
    msg = failure_message(TimeoutError("Locator.wait_for: Timeout 30000ms exceeded"), U())
    assert msg.startswith("[사원코드 연결·저장] 위하고 화면이 예상과 달라 멈췄습니다")
    assert "저장됐을 수 있으니" in msg and "Timeout 30000ms" not in msg
