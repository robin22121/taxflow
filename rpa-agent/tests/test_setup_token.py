from easyone_agent.__main__ import _extract_agent_token


def test_plain_token():
    assert _extract_agent_token("rpa_AbC-12_x") == "rpa_AbC-12_x"


def test_whole_settings_command_is_accepted():
    # 2026-09-27: 설정 화면 안내 명령을 통째로 붙여 넣어 claim 이 401 이 난 적이 있다
    pasted = "EASYONE_AGENT_TOKEN=rpa_AbC-12_x uv run python -m certificate_agent easyone --server https://x"
    assert _extract_agent_token(pasted) == "rpa_AbC-12_x"


def test_no_token():
    assert _extract_agent_token("EASYONE_AGENT_TOKEN=") is None
