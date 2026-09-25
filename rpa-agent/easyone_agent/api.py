"""이지원천 서버 API 클라이언트 — 서버로 나가는 HTTPS만 쓴다 (backend/app/api/rpa.py)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

import httpx

# 위하고 → 이지원천 가져오기 (plan/16 §12)
IMPORT_ALL = "WEHAGO_MASTER_IMPORT_ALL"
IMPORT_CLIENT = "WEHAGO_CLIENT_IMPORT"


@dataclass(frozen=True, slots=True)
class Job:
    id: str
    client_id: str | None  # 가져오기는 비어 있을 수 있다
    period: str | None  # "YYYY-MM" — 가져오기는 None
    business_number: str | None  # 전체 가져오기만 None
    business_name: str
    kind: str = "WEHAGO_PAYROLL_INPUT"
    pay_date: date | None = None  # 위하고 급여자료입력 지급일 — 서버가 아직 안 보내면 None


class EasyoneApi:
    def __init__(
        self,
        base_url: str,
        agent_token: str,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._http = httpx.Client(
            base_url=base_url.rstrip("/"),
            headers={"X-Agent-Token": agent_token},
            timeout=30.0,
            transport=transport,
        )

    def claim(self) -> Job | None:
        r = self._http.post("/api/v1/rpa/agent/claim")
        r.raise_for_status()
        data = r.json()["job"]
        if data is None:
            return None
        return Job(
            id=data["id"],
            client_id=data["client_id"],
            period=data["period"],
            business_number=data["business_number"],
            business_name=data["business_name"],
            kind=data["kind"],
            pay_date=date.fromisoformat(data["pay_date"]) if data.get("pay_date") else None,
        )

    def download_payroll_excel(self, job_id: str) -> bytes:
        r = self._http.get(f"/api/v1/rpa/agent/jobs/{job_id}/payroll-excel")
        if r.status_code == 409:
            raise RuntimeError(f"서버가 급여파일 제공을 거부했습니다: {r.json().get('detail')}")
        r.raise_for_status()
        return r.content

    def report(self, job_id: str, succeeded: bool, message: str) -> None:
        r = self._http.post(
            f"/api/v1/rpa/agent/jobs/{job_id}/result",
            json={"status": "SUCCEEDED" if succeeded else "FAILED", "message": message},
        )
        r.raise_for_status()

    def report_import_client(self, job_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        """가져오기 — 수임처 1건 결과. 서버가 바로 반영하고, 전체 가져오기의 생존 신호도 된다."""
        r = self._http.post(f"/api/v1/rpa/agent/imports/{job_id}/client-result", json=payload)
        if r.status_code == 409:
            raise RuntimeError(f"서버가 가져오기 결과를 거부했습니다: {r.json().get('detail')}")
        r.raise_for_status()
        return r.json()
