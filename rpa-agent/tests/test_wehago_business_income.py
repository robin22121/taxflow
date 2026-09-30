from __future__ import annotations

from datetime import date

from easyone_agent.wehago import _parse_business_income_rows

# 사업소득자등록(SWBU0101) #Leftgird `_REALGRID_ROWS_JS` 실측 필드 (2026-09-30)
_ROW = {
    "cd_buemp": "0000000001",
    "nm_krname": "김태호",
    "yn_for": "0",
    "no_social": "7707281323914",
    "cd_income": "940909",
    "mn_ctrl": "기타인적용역자",
    "da_retire": "",
}
_EMPTY_ROW = {k: "" for k in _ROW} | {"dummyForSort": "1"}


def test_maps_wehago_fields_to_import_payload():
    rows = _parse_business_income_rows([_ROW])
    assert rows == [
        {
            "employee_code": "0000000001",
            "name": "김태호",
            "rrn": "7707281323914",
            "resigned_at": None,
            "income_type": "BUSINESS",
            "business_type_code": "940909",
        }
    ]


def test_skips_empty_placeholder_row():
    assert _parse_business_income_rows([_ROW, _EMPTY_ROW]) == _parse_business_income_rows([_ROW])


def test_parses_resigned_at():
    resigned = _ROW | {"cd_buemp": "0000000002", "nm_krname": "김아인", "da_retire": "2026-09-30"}
    rows = _parse_business_income_rows([resigned])
    assert rows[0]["resigned_at"] == date(2026, 9, 30)


def test_ignores_malformed_resigned_at():
    bad = _ROW | {"da_retire": "이상한 값"}
    rows = _parse_business_income_rows([bad])
    assert rows[0]["resigned_at"] is None
