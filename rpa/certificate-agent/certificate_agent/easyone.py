"""이지원천 본 백엔드 연동 루프 — 증명원 발급 메뉴 (plan/17 §4-9).

`/api/v1/certificates/agent/*` 를 폴링한다.
- 발급 요청 → 로그인해 둔 Chrome 에 부착해 증명원별 발급 → 지정 폴더에 원본 저장 → 서버 사본 업로드
- [폴더 열어 확인] 요청 → 이 PC 에서 탐색기(Finder)로 저장 폴더를 연다

지금은 개발 경로(CDP 부착)만 쓴다. 자동 로그인 경로는 execute_phase1 을 같은 자리에 넣으면 된다.
"""

from __future__ import annotations

import platform
import re
import subprocess
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

from certificate_agent.issue_flow import execute_attached

POLL_INTERVAL_SEC = 5.0
PREFIX = "/api/v1/certificates/agent"


class EasyoneClient:
    def __init__(self, base_url: str, token: str) -> None:
        self.client = httpx.Client(
            base_url=base_url.rstrip("/"), headers={"X-Agent-Token": token}, timeout=60.0
        )

    def _post(self, path: str, **kw: Any) -> Any:
        r = self.client.post(PREFIX + path, **kw)
        r.raise_for_status()
        return r.json()

    def claim(self) -> dict[str, Any]:
        return self._post("/claim")

    def upload(self, issue_id: str, path: Path) -> Any:
        with path.open("rb") as f:
            return self._post(
                f"/issues/{issue_id}/file",
                files={"file": (path.name, f, "application/pdf" if path.suffix == ".pdf" else "image/png")},
                data={"local_path": str(path)},
            )

    def fail(self, issue_id: str, reason: str) -> Any:
        return self._post(f"/issues/{issue_id}/fail", json={"reason": reason[:2000]})

    def finish(self, job_id: str, ok: bool, message: str) -> Any:
        return self._post(f"/jobs/{job_id}/finish", json={"status": "SUCCEEDED" if ok else "FAILED", "message": message[:2000]})

    def folder_requests(self) -> list[dict[str, Any]]:
        r = self.client.get(PREFIX + "/folder-requests")
        r.raise_for_status()
        return r.json()

    def folder_opened(self, issue_id: str, local_path: Path | None = None) -> Any:
        body = {"local_path": str(local_path)} if local_path else None
        return self._post(f"/issues/{issue_id}/folder-opened", json=body)

    def download(self, issue_id: str) -> bytes:
        r = self.client.get(f"{PREFIX}/issues/{issue_id}/file")
        r.raise_for_status()
        return r.content

    def close(self) -> None:
        self.client.close()


def _safe(name: str) -> str:
    """Windows 파일명 금지문자 제거."""
    return re.sub(r'[\\/:*?"<>|]+', "_", name).strip() or "무제"


def save_path(save_dir: Path, business_name: str, title: str, filename: str) -> Path:
    """{지정폴더}/{거래처}/{YYYYMMDD_HHMMSS}_{증명원}.pdf"""
    ext = Path(filename).suffix or ".pdf"
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return save_dir / _safe(business_name) / f"{stamp}_{_safe(title)}{ext}"


def open_in_file_manager(path: Path) -> None:
    """저장 파일을 선택한 상태로 탐색기(Finder)를 연다."""
    system = platform.system()
    if system == "Windows":
        subprocess.Popen(["explorer", "/select,", str(path)])
    elif system == "Darwin":
        subprocess.Popen(["open", "-R", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path.parent)])


def short_reason(exc: Exception) -> str:
    """이지원천 화면에 보일 실패 사유 — 덤프 경로·URL 은 빼고(에이전트 로그에만) 조치 안내를 붙인다."""
    msg = str(exc)
    msg = re.sub(r"\s*\|?\s*dump=\S+", "", msg)
    msg = re.sub(r"\s*url=\S+(\s+title='[^']*')?", "", msg)
    msg = re.sub(r"^(RuntimeError: )+", "", msg).strip()
    if "신청 화면 진입 실패" in msg:
        msg += " — 홈택스 로그인이 풀렸는지 확인하세요"
    return msg[:300]


def _handle_folder_requests(client: EasyoneClient, save_dir: Path) -> None:
    opened: set[str] = set()
    for issue in client.folder_requests():
        saved: Path | None = None
        if issue.get("local_path"):
            path = Path(issue["local_path"])
            if not path.exists():
                # 다른 PC 에서 발급된 건 — 이 PC 에는 원본이 없다. 요청은 그대로 둔다.
                continue
        elif issue.get("has_file"):
            # 서버가 만든 증명서(직원용) — 서버 사본을 지정 폴더로 내려받아 원본으로 둔다
            path = save_path(save_dir, issue["business_name"], issue["title"], issue.get("file_name") or ".pdf")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(client.download(issue["id"]))
            saved = path
        else:
            continue
        if str(path.parent) not in opened:  # 같은 요청의 여러 증명원은 창 하나로
            open_in_file_manager(path)
            opened.add(str(path.parent))
            print(f"[+] 폴더 열기: {path.parent}")
        client.folder_opened(issue["id"], saved)


def _run_job(client: EasyoneClient, claimed: dict[str, Any], cdp_url: str, save_dir: Path) -> None:
    job = claimed["job"]
    issues = claimed["issues"]
    print(f"[+] 발급 요청 {job['id']} — {job['business_name']} × {[i['title'] for i in issues]}")
    failures: list[str] = []
    for issue in issues:
        try:
            data, filename, _mime, msg = execute_attached(
                {
                    "cert_type": issue["cert_type"],
                    "business_number": issue.get("business_number") or "",
                    "options": issue.get("options") or {},
                },
                cdp_url,
            )
            path = save_path(save_dir, issue["business_name"], issue["title"], filename)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            client.upload(issue["id"], path)
            print(f"[+] {issue['title']} 발급 → {path} ({msg})")
        except Exception as exc:  # noqa: BLE001
            reason = short_reason(exc)
            print(f"[!] {issue['title']} 실패: {exc}\n{traceback.format_exc()}")
            failures.append(f"{issue['title']}: {reason}")
            try:
                client.fail(issue["id"], reason)
            except Exception as exc2:  # noqa: BLE001
                print(f"[!] 실패 회신도 실패: {exc2}")
    message = "; ".join(failures) if failures else f"{len(issues)}건 발급 완료"
    client.finish(job["id"], not failures, message)


def run_easyone_loop(server_url: str, token: str, cdp_url: str, save_dir: Path) -> None:
    client = EasyoneClient(server_url, token)
    print(f"[+] 이지원천 증명발급 에이전트 시작. server={server_url} 저장폴더={save_dir}")
    try:
        while True:
            try:
                _handle_folder_requests(client, save_dir)
                claimed = client.claim()
            except Exception as exc:  # noqa: BLE001
                print(f"[!] 서버 통신 실패: {exc}")
                time.sleep(POLL_INTERVAL_SEC)
                continue
            if claimed.get("job"):
                _run_job(client, claimed, cdp_url, save_dir)
            else:
                time.sleep(POLL_INTERVAL_SEC)
    finally:
        client.close()
