from easyone_agent.company import company_matches


def test_legal_form_and_dashes_are_ignored():
    assert company_matches("(주)하늘식품", "123-45-67890", "주식회사 하늘식품", "1234567890")
    assert company_matches("㈜ 동문건설", "1234567890", "동문건설(주)", "123-45-67890")


def test_different_number_or_name_does_not_match():
    assert not company_matches("하늘식품", "1234567890", "하늘식품", "1234567891")
    assert not company_matches("하늘식품", "1234567890", "하늘푸드", "1234567890")


def test_blank_expected_values_never_match():
    assert not company_matches("하늘식품", "", "하늘식품", "")
    assert not company_matches("", "1234567890", "", "1234567890")
