from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from openpyxl import Workbook

from easyone_agent.api import IMPORT_ALL, IMPORT_CLIENT, Job
from easyone_agent.import_runner import process_import
from easyone_agent.wehago import LoginFailed


class FakeApi:
    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []

    def report_import_client(self, job_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.sent.append(payload)
        return {}


class FakeSource:
    def __init__(self, companies: list[tuple[str, str]], broken: set[str] = frozenset(),
                 login_error: Exception | None = None) -> None:
        self.companies = companies
        self.broken = broken
        self.login_error = login_error
        self.exports: list[Path] = []

    def ensure_logged_in(self) -> None:
        if self.login_error:
            raise self.login_error

    def list_companies(self) -> list[tuple[str, str]]:
        return self.companies

    def read_company(self, business_number: str) -> dict[str, Any]:
        if business_number in self.broken:
            raise RuntimeError("수임처정보 화면을 열지 못함")
        name = dict((bn, n) for n, bn in self.companies).get(business_number, "서도")
        return {"business_name": name, "business_number": business_number, "representative": "엄순덕"}

    def export_employees(self, business_number: str, workdir: Path) -> Path:
        wb = Workbook()
        wb.active.append(["사원코드", "사원명", "주민(외국인)등록번호", "계좌번호"])
        wb.active.append(["1", "한지민", "600915-2000001", "110-123-456789"])
        path = workdir / f"{business_number}_사원등록.xlsx"
        wb.save(path)
        self.exports.append(path)
        return path


def test_master_import_continues_after_one_company_fails(tmp_path: Path):
    api = FakeApi()
    source = FakeSource([("서도", "224-02-38407"), ("동문", "111-22-33333")], broken={"111-22-33333"})
    job = Job("j1", None, None, None, "위하고 전체 수임처", kind=IMPORT_ALL)

    ok, message = process_import(api, source, job, tmp_path)

    assert ok and "2곳 중 1곳" in message and "1곳 실패" in message
    first, second = api.sent
    assert first["employees"][0]["name"] == "한지민" and first["total"] == 2
    assert "110-123-456789" not in str(first)  # 계좌는 보내지 않는다
    assert second["error"].startswith("RuntimeError") and "employees" not in second
    assert list(tmp_path.iterdir()) == []  # 받은 사원자료 엑셀은 지운다


def test_client_import_rejects_other_company(tmp_path: Path):
    class OtherCompany(FakeSource):
        def read_company(self, business_number: str) -> dict[str, Any]:
            return {"business_name": "딴회사", "business_number": "999-99-99999"}

    api = FakeApi()
    job = Job("j2", None, None, "224-02-38407", "위하고 수임처", kind=IMPORT_CLIENT)
    ok, _ = process_import(api, OtherCompany([]), job, tmp_path)

    assert not ok
    assert "사업자번호가 다릅니다" in api.sent[0]["error"]


def test_login_failure_stops_import(tmp_path: Path):
    job = Job("j3", None, None, "224-02-38407", "서도", kind=IMPORT_CLIENT)
    with pytest.raises(LoginFailed):
        process_import(FakeApi(), FakeSource([], login_error=LoginFailed("잠김")), job, tmp_path)
