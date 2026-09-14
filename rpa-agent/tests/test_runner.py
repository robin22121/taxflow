from __future__ import annotations

from pathlib import Path

import pytest

from easyone_agent.api import Job
from easyone_agent.runner import process_one, run_forever
from easyone_agent.wehago import LoginFailed

JOB = Job(
    id="job1",
    client_id="c1",
    period="2026-08",
    business_number="123-45-67890",
    business_name="(주)하늘식품",
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
        self.uploaded: list[tuple[Path, str]] = []

    def ensure_logged_in(self) -> None:
        if self.login_error:
            raise self.login_error

    def open_company(self, business_number: str) -> tuple[str, str]:
        return self.company

    def upload_payroll(self, xlsx_path: Path, period: str) -> str:
        assert xlsx_path.read_bytes() == b"fake-xlsx"
        if self.upload_error:
            raise self.upload_error
        self.uploaded.append((xlsx_path, period))
        return "3명 업로드 완료"


def test_no_job_does_nothing(tmp_path: Path):
    api = FakeApi([])
    assert process_one(api, FakeUploader(), tmp_path) is False
    assert api.reports == []


def test_success_reports_message_and_deletes_file(tmp_path: Path):
    api, uploader = FakeApi([JOB]), FakeUploader()
    assert process_one(api, uploader, tmp_path) is True
    assert api.reports == [("job1", True, "3명 업로드 완료")]
    assert uploader.uploaded[0][1] == "2026-08"
    assert list(tmp_path.iterdir()) == []


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
