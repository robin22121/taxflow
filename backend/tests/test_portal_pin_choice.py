"""세무사가 지정한 PIN — 형식 검증과 무작위 발급 동작."""

from __future__ import annotations

import pytest

from app.services.portal import PIN_LENGTH, InvalidPinError, generate_pin, validate_pin


def test_valid_pin_passes():
    assert validate_pin("123456") == "123456"


def test_surrounding_spaces_are_trimmed():
    assert validate_pin(" 246810 ") == "246810"


@pytest.mark.parametrize("bad", ["12345", "1234567", "abcdef", "12 456", "", "１２３４５６"])
def test_invalid_pin_rejected(bad: str):
    with pytest.raises(InvalidPinError):
        validate_pin(bad)


def test_generated_pin_is_accepted_by_validator():
    """무작위 발급과 지정 PIN이 같은 규칙을 따라야 한다."""
    for _ in range(20):
        pin = generate_pin()
        assert len(pin) == PIN_LENGTH
        assert validate_pin(pin) == pin
