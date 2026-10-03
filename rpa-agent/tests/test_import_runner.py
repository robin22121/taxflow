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

    def list_business_income_earners(self, business_number: str) -> list[dict[str, Any]]:
        return []

    def list_other_income_earners(self, business_number: str) -> list[dict[str, Any]]:
        return []

    def list_daily_workers(self, business_number: str) -> list[dict[str, Any]]:
        return []


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


def test_import_merges_business_other_daily_earners(tmp_path: Path):
    """§13-3-4 — 사업/기타/일용소득자 명단도 사원등록(근로) 엑셀과 합쳐서 보낸다."""

    class WithOtherIncomeTypes(FakeSource):
        def list_business_income_earners(self, business_number: str) -> list[dict[str, Any]]:
            return [{"employee_code": "1", "name": "김태호", "rrn": "7707281323914",
                     "income_type": "BUSINESS", "business_type_code": "940909"}]

        def list_other_income_earners(self, business_number: str) -> list[dict[str, Any]]:
            return [{"employee_code": "3", "name": "김아인", "rrn": "8105121323917", "income_type": "OTHER"}]

        def list_daily_workers(self, business_number: str) -> list[dict[str, Any]]:
            return [{"employee_code": "1", "name": "김연호", "rrn": None, "income_type": "DAILY"}]

    api = FakeApi()
    job = Job("j4", None, None, "224-02-38407", "서도", kind=IMPORT_CLIENT)
    ok, _ = process_import(api, WithOtherIncomeTypes([]), job, tmp_path)

    assert ok
    employees = api.sent[0]["employees"]
    assert len(employees) == 4  # 근로 1 + 사업 1 + 기타 1 + 일용 1
    by_type = {e.get("income_type"): e for e in employees if e.get("income_type")}
    assert by_type["BUSINESS"]["name"] == "김태호"
    assert by_type["OTHER"]["name"] == "김아인"
    assert by_type["DAILY"]["name"] == "김연호"


class _TypedSource(FakeSource):
    """유형별로 한 명씩 돌려주고, 어떤 화면을 열었는지 기록한다."""

    def __init__(self) -> None:
        super().__init__([])
        self.opened: list[str] = []

    def export_employees(self, business_number: str, workdir: Path) -> Path:
        self.opened.append("WAGE")
        return super().export_employees(business_number, workdir)

    def list_business_income_earners(self, business_number: str) -> list[dict[str, Any]]:
        self.opened.append("BUSINESS")
        return [{"employee_code": "1", "name": "김태호", "income_type": "BUSINESS"}]

    def list_other_income_earners(self, business_number: str) -> list[dict[str, Any]]:
        self.opened.append("OTHER")
        return [{"employee_code": "3", "name": "김아인", "income_type": "OTHER"}]

    def list_daily_workers(self, business_number: str) -> list[dict[str, Any]]:
        self.opened.append("DAILY")
        return [{"employee_code": "1", "name": "김연호", "income_type": "DAILY"}]


def test_import_reads_only_selected_employee_types(tmp_path: Path):
    """선택한 소득유형(근로·일용)만 가져온다 — 고르지 않은 화면은 열지도 않는다."""
    api, source = FakeApi(), _TypedSource()
    job = Job("j5", None, None, "224-02-38407", "서도", kind=IMPORT_CLIENT,
              import_options={"employee_income_types": ["WAGE", "DAILY"]})

    ok, _ = process_import(api, source, job, tmp_path)

    assert ok
    assert source.opened == ["WAGE", "DAILY"]
    assert {e["name"] for e in api.sent[0]["employees"]} == {"한지민", "김연호"}


def test_import_without_employees_sends_company_only(tmp_path: Path):
    """사원정보를 고르지 않으면(빈 목록) 수임처 기본사항만 보내고 사원 화면은 열지 않는다."""
    api, source = FakeApi(), _TypedSource()
    job = Job("j6", None, None, "224-02-38407", "서도", kind=IMPORT_CLIENT,
              import_options={"employee_income_types": []})

    ok, _ = process_import(api, source, job, tmp_path)

    assert ok
    assert source.opened == []
    assert api.sent[0]["employees"] == []
    assert list(tmp_path.iterdir()) == []


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
