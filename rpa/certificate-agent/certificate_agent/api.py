"""서버 HTTP 클라이언트."""

from __future__ import annotations

from typing import Any

import httpx


class ServerClient:
    def __init__(self, base_url: str, token: str, timeout: float = 30.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.client = httpx.Client(
            base_url=self.base_url,
            headers={"X-Agent-Token": token},
            timeout=timeout,
        )

    def claim_next(self) -> dict[str, Any] | None:
        r = self.client.get("/api/agent/jobs/next")
        r.raise_for_status()
        if r.status_code == 204 or not r.text or r.text == "null":
            return None
        return r.json()

    def submit_result(
        self,
        job_id: str,
        *,
        file_bytes: bytes,
        filename: str,
        mime: str,
        success: bool,
        message: str = "",
    ) -> dict[str, Any]:
        files = {"file": (filename, file_bytes, mime)}
        data = {"success": str(success).lower(), "message": message}
        r = self.client.post(f"/api/agent/jobs/{job_id}/result", files=files, data=data)
        r.raise_for_status()
        return r.json()

    def close(self) -> None:
        self.client.close()
