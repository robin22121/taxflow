from __future__ import annotations

from easyone_agent.wehago import _parse_other_income_rows

# 기타(이자/배당)소득자등록(SWET0101) #Leftgrid `_REALGRID_ROWS_JS` 실측 필드 (2026-09-30)
_ROW = {
    "cd_etemp": "0000000003",
    "cd_income": "69",
    "nm_income": "분리과세기타소득",
    "nm_krname": "김태호",
    "nm_linecolor": None,
    "no_biz": "",
    "no_social": "7707281323914",
    "ty_income": "1",
    "yn_corp": "1",
    "yn_for": "0",
    "yn_resident": "0",
}
_EMPTY_ROW = {
    "cd_etemp": "0000000001",  # 다음 코드가 미리 채워져 있어도 이름이 비면 걸러진다
    "cd_income": "",
    "nm_income": "",
    "nm_krname": "",
    "nm_linecolor": "",
    "no_biz": "",
    "no_social": "",
    "ty_income": "",
    "yn_corp": "",
    "yn_for": "",
    "yn_resident": "",
}


def test_maps_wehago_fields_to_import_payload():
    rows = _parse_other_income_rows([_ROW])
    assert rows == [
        {
            "employee_code": "0000000003",
            "name": "김태호",
            "rrn": "7707281323914",
            "income_type": "OTHER",
        }
    ]


def test_skips_row_with_prefilled_code_but_no_name():
    assert _parse_other_income_rows([_ROW, _EMPTY_ROW]) == _parse_other_income_rows([_ROW])
