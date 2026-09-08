"""검토 화면에서 신규 입사자를 주민번호와 함께 등록하는 경로."""

import pytest

from app.services.crypto import decrypt_rrn, normalize_rrn, rrn_last4


def test_normalize_rrn_accepts_hyphen_and_plain():
    assert normalize_rrn("900101-1234567") == "9001011234567"
    assert normalize_rrn("9001011234567") == "9001011234567"
    # 2020.10 이후 발급분처럼 검증부호가 성립하지 않는 번호도 통과해야 한다.
    assert normalize_rrn("240101-3000000") == "2401013000000"


@pytest.mark.parametrize(
    "bad",
    [
        "90010112345",       # 자릿수 부족
        "90010112345678",    # 자릿수 초과
        "900101-9234567",    # 성별코드 범위 밖
        "901301-1234567",    # 13월
        "900132-1234567",    # 32일
        "abcdef-1234567",    # 숫자 아님
    ],
)
def test_normalize_rrn_rejects_bad_input(bad):
    with pytest.raises(ValueError):
        normalize_rrn(bad)


def test_rrn_last4_is_actual_last_four():
    assert rrn_last4("900101-1234567") == "4567"
    assert rrn_last4("9001011234567") == "4567"


def test_encrypt_roundtrip():
    from app.services.crypto import encrypt_rrn

    blob = encrypt_rrn("9001011234567")
    assert blob != b"9001011234567"
    assert decrypt_rrn(blob) == "9001011234567"
