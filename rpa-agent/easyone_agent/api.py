"""이지원천 서버 API 클라이언트 — 서버로 나가는 HTTPS만 쓴다 (backend/app/api/rpa.py)."""

from __future__ import annotations

from dataclasses import dataclass

import httpx


@dataclass(frozen=True, slots=True)
class Job:
    id: str
    client_id: str
    period: str  # "YYYY-MM"
    business_number: str
    business_name: str


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
