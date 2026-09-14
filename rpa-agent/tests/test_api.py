import httpx

from easyone_agent.api import EasyoneApi, Job


def test_claim_sends_token_and_parses_job():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/rpa/agent/claim"
        assert request.headers["X-Agent-Token"] == "rpa_test"
        return httpx.Response(
            200,
            json={
                "job": {
                    "id": "j1",
                    "client_id": "c1",
                    "period": "2026-08",
                    "business_number": "1234567890",
                    "business_name": "하늘식품",
                    "status": "RUNNING",
                }
            },
        )

    api = EasyoneApi("https://api.test/", "rpa_test", transport=httpx.MockTransport(handler))
    assert api.claim() == Job("j1", "c1", "2026-08", "1234567890", "하늘식품")


def test_claim_returns_none_when_idle():
    api = EasyoneApi(
        "https://api.test",
        "rpa_test",
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"job": None})),
    )
    assert api.claim() is None
