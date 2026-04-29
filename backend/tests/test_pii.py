from app.services.pii import redact_payload, redact_pii


def test_rrn_with_hyphen():
    assert redact_pii("김연호 900101-1234567 100만원") == "김연호 ******-******* 100만원"


def test_rrn_without_hyphen():
    # RRN regex catches 6+7 even without hyphen and re-formats with dash for visual marker.
    assert redact_pii("9001011234567") == "******-*******"


def test_rrn_with_space():
    assert redact_pii("900101 1234567") == "******-*******"


def test_business_number():
    # Mask preserves length (incl. dashes)
    assert redact_pii("사업자번호 111-22-33333 입니다") == "사업자번호 ************ 입니다"


def test_card_number():
    assert redact_pii("4111-1111-1111-1111") == "****-****-****-****" or redact_pii(
        "4111111111111111"
    ) == "****************"


def test_idempotent():
    once = redact_pii("김연호 900101-1234567")
    twice = redact_pii(once)
    assert once == twice


def test_no_false_positives_on_amounts():
    # 100만원 / 1,200,000 / 2026-04 should pass through
    assert redact_pii("100만원") == "100만원"
    assert redact_pii("1,200,000원") == "1,200,000원"
    assert redact_pii("2026-04-25") == "2026-04-25"
    assert redact_pii("010-1234-5678") == "010-1234-5678"  # phone is fine


def test_redact_payload_recursive():
    p = {
        "name": "김연호",
        "rrn": "900101-1234567",
        "nested": [{"id": "ok", "rrn": "880515-2345678"}],
    }
    out = redact_payload(p)
    assert out["name"] == "김연호"
    assert out["rrn"] == "******-*******"
    assert out["nested"][0]["rrn"] == "******-*******"
    assert out["nested"][0]["id"] == "ok"


def test_empty_input():
    assert redact_pii("") == ""
    assert redact_pii(None) is None  # type: ignore[arg-type]
