"""통합 다운로드 ZIP의 거래처 폴더명 규칙 테스트."""

from app.api.filings import _unique_folder


def test_strips_path_separators():
    used: set[str] = set()

    assert _unique_folder("하늘/식품", used) == "하늘식품"
    assert _unique_folder("a\\b:c*d?e", used) == "abcde"


def test_duplicate_names_get_suffix():
    used: set[str] = set()

    assert _unique_folder("동문건설", used) == "동문건설"
    assert _unique_folder("동문건설", used) == "동문건설_2"
    assert _unique_folder("동문건설", used) == "동문건설_3"


def test_blank_name_falls_back():
    used: set[str] = set()

    assert _unique_folder("", used) == "거래처"
    assert _unique_folder("   ", used) == "거래처_2"


def test_name_is_truncated():
    used: set[str] = set()

    assert len(_unique_folder("가" * 200, used)) == 60
