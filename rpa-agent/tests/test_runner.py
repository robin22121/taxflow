from __future__ import annotations

from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest

from easyone_agent.api import Job
from easyone_agent.runner import login_test_one, process_one, run_forever, run_login_test
from easyone_agent.wehago import LoginFailed

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
        self.report_error = report_error

    def claim(self) -> Job | None:
        return self.jobs.pop(0) if self.jobs else None

    def download_payroll_excel(self, job_id: str) -> bytes:
        return b"fake-xlsx"

    def report(self, job_id: str, succeeded: bool, message: str) -> None:
        if self.report_error:
            raise self.report_error
        self.reports.append((job_id, succeeded, message))


class FakeUploader:
    def __init__(
        self,
        company: tuple[str, str] = ("주식회사 하늘식품", "1234567890"),
        login_error: Exception | None = None,
        upload_error: Exception | None = None,
    ) -> None:
        self.company = company
        self.login_error = login_error
        self.upload_error = upload_error
        self.uploaded: list[tuple[Path, str, date]] = []

    def ensure_logged_in(self) -> None:
        if self.login_error:
            raise self.login_error

    def open_company(self, business_number: str) -> tuple[str, str]:
        return self.company

    def upload_payroll(self, xlsx_path: Path, period: str, pay_date: date) -> str:
        assert xlsx_path.read_bytes() == b"fake-xlsx"
        if self.upload_error:
            raise self.upload_error
        self.uploaded.append((xlsx_path, period, pay_date))
        return "3명 업로드 완료"


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
    assert "양식 오류" in api.reports[0][2]


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
