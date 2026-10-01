from __future__ import annotations

from easyone_agent.wehago import district_search_term


def test_city_gu_dong():
    assert district_search_term("서울특별시 종로구 청운동 12-3") == "종로 청운"


def test_county_eup_ri():
    assert district_search_term("강원도 횡성군 횡성읍 읍상리 45") == "횡성 읍상"


def test_county_myeon_ri():
    assert district_search_term("경상남도 거제시 사등면 사곡리 1") == "사등 사곡"


def test_extra_level_before_city_still_uses_last_two():
    # 드물게 더 긴 사슬(시 다음에 군 등)이 와도 끝에서 두 단계만 본다
    assert district_search_term("경기도 OO시 OO군 OO읍 OO리") == "OO OO"


def test_fewer_than_two_admin_tokens_returns_none():
    assert district_search_term("서울특별시") is None


def test_empty_or_none_returns_none():
    assert district_search_term("") is None
    assert district_search_term(None) is None
