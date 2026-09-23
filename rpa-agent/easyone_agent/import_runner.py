"""위하고 → 이지원천 가져오기 작업 처리 (plan/16 §12).

수임처마다: 위하고 수임처정보 기본사항 읽기 → 사원등록 [사원자료 엑셀변환] 받기 →
필요한 항목만 뽑아 서버로 보내기 → 받은 파일 삭제. 한 수임처가 실패해도 다음 수임처로 넘어간다.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Protocol

from easyone_agent.api import IMPORT_ALL, EasyoneApi, Job
from easyone_agent.company import normalize_business_number
from easyone_agent.logmask import mask_text
from easyone_agent.wehago import LoginFailed
from easyone_agent.wehago_employees import parse_employee_export

logger = logging.getLogger(__name__)


class WehagoImportSource(Protocol):
    """위하고 화면 조작 (wehago.py). 테스트에서는 가짜로 바꾼다."""

    def ensure_logged_in(self) -> None: ...

    def list_companies(self) -> list[tuple[str, str]]:
        """담당 수임처 전체 (상호, 사업자번호)."""
        ...

    def read_company(self, business_number: str) -> dict[str, Any]:
        """수임처정보 기본사항 — business_name·business_number·representative·… ."""
        ...

    def export_employees(self, business_number: str, workdir: Path) -> Path:
        """사원등록 [사원자료 엑셀변환] 파일 경로. 호출자가 지운다."""
        ...


def process_import(api: EasyoneApi, source: WehagoImportSource, job: Job, workdir: Path) -> tuple[bool, str]:
    """가져오기 작업 한 건. (성공 여부, 결과 메시지)를 돌려준다. LoginFailed 는 그대로 올린다."""
    source.ensure_logged_in()
    if job.kind == IMPORT_ALL:
        targets = source.list_companies()
        if not targets:
            return False, "위하고 담당 수임처 목록이 비어 있습니다"
        total: int | None = len(targets)
    else:
        targets = [(job.business_name, job.business_number or "")]
        total = None

    succeeded = failed = 0
    for name, business_number in targets:
        ok = _import_one(api, source, job, name, business_number, total, workdir)
        succeeded += ok
        failed += not ok

    if job.kind == IMPORT_ALL:
        message = f"위하고 수임처 {len(targets)}곳 중 {succeeded}곳 가져옴" + (f", {failed}곳 실패" if failed else "")
        return succeeded > 0, message
    return succeeded == 1, "가져오기 완료" if succeeded else "가져오기 실패 — 결과에서 사유를 확인하세요"


def _import_one(
    api: EasyoneApi,
    source: WehagoImportSource,
    job: Job,
    name: str,
    business_number: str,
    total: int | None,
    workdir: Path,
) -> bool:
    base: dict[str, Any] = {"business_number": business_number, "business_name": name or business_number}
    if total:
        base["total"] = total
    export: Path | None = None
    try:
        basics = source.read_company(business_number)
        if normalize_business_number(basics["business_number"]) != normalize_business_number(business_number):
            raise RuntimeError(f"위하고 수임처 사업자번호가 다릅니다: {basics['business_number']}")
        export = source.export_employees(business_number, workdir)
        payload = {**base, **basics, "employees": parse_employee_export(export)}
    except LoginFailed:
        raise
    except Exception as e:
        logger.exception("가져오기 실패 %s", mask_text(business_number))
        _send(api, job.id, {**base, "error": mask_text(f"{type(e).__name__}: {e}")[:500]})
        return False
    finally:
        # 사원자료 엑셀에는 주민번호·계좌가 있다 — PC에 남기지 않는다.
        if export is not None:
            export.unlink(missing_ok=True)
    return _send(api, job.id, payload)


def _send(api: EasyoneApi, job_id: str, payload: dict[str, Any]) -> bool:
    try:
        api.report_import_client(job_id, payload)
    except Exception:
        logger.exception("가져오기 결과 전송 실패")
        return False
    return "error" not in payload
