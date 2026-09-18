"""폴링 루프 — 잡 pick → 실행 → 결과 업로드."""

from __future__ import annotations

import time
import traceback

from certificate_agent.api import ServerClient
from certificate_agent.config import AgentConfig
from certificate_agent.issue_flow import MODE, execute

POLL_INTERVAL_SEC = 5.0


def run_loop(cfg: AgentConfig) -> None:
    client = ServerClient(cfg.server_url, cfg.agent_token)
    print(f"[+] agent started. mode={MODE} server={cfg.server_url}")
    try:
        while True:
            try:
                job = client.claim_next()
            except Exception as exc:  # noqa: BLE001
                print(f"[!] claim failed: {exc}")
                time.sleep(POLL_INTERVAL_SEC)
                continue

            if not job:
                time.sleep(POLL_INTERVAL_SEC)
                continue

            print(f"[+] job claimed: {job['id']} cert_type={job['cert_type']}")
            try:
                file_bytes, filename, mime, msg = execute(job, cfg)
                print(f"[+] execute done: {msg}")
                res = client.submit_result(
                    job["id"],
                    file_bytes=file_bytes,
                    filename=filename,
                    mime=mime,
                    success=True,
                    message=msg,
                )
                print(f"[+] uploaded: {res}")
            except Exception as exc:  # noqa: BLE001
                tb = traceback.format_exc()
                print(f"[!] execute failed: {exc}\n{tb}")
                try:
                    client.submit_result(
                        job["id"],
                        file_bytes=b"",
                        filename="fail.txt",
                        mime="text/plain",
                        success=False,
                        message=f"{type(exc).__name__}: {exc}",
                    )
                except Exception as exc2:  # noqa: BLE001
                    print(f"[!] failure report also failed: {exc2}")
    finally:
        client.close()
