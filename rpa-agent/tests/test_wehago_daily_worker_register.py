from __future__ import annotations

from easyone_agent.wehago import _parse_daily_worker_rows

# 일용직 사원등록(SWSA0107) #Tab1_left_grid `_REALGRID_ROWS_JS` 실측 필드 (2026-09-30)
_ROW = {"age": "49", "cd_emp": "1", "fg_forg": "0", "nm_emp": "김태호", "no_social": "7707281323914"}
_EMPTY_ROW = {"age": "", "cd_emp": "", "fg_forg": "", "nm_emp": "", "no_social": ""}


def test_maps_wehago_fields_to_import_payload():
    rows = _parse_daily_worker_rows([_ROW])
    assert rows == [
        {
            "employee_code": "1",
            "name": "김태호",
            "rrn": "7707281323914",
            "income_type": "DAILY",
        }
    ]


def test_skips_empty_placeholder_row():
    assert _parse_daily_worker_rows([_ROW, _EMPTY_ROW]) == _parse_daily_worker_rows([_ROW])
