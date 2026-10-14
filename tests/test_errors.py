import httpx
import openai
from fastapi.testclient import TestClient

from app import main
from app.llm import normalize_base_url


def test_normalize_base_url():
    assert normalize_base_url("https://x.com/v1/chat/completions") == "https://x.com/v1"
    assert normalize_base_url("https://x.com/v1/") == "https://x.com/v1"
    assert normalize_base_url("") is None


class Boom:
    def complete(self, messages, tools=None):
        raise openai.APIConnectionError(request=httpx.Request("POST", "http://gw/v1/chat/completions"))


def test_502_generic_then_debug(monkeypatch):
    main.agent.llm = Boom()
    client = TestClient(main.app)
    r = client.post("/chat", json={"message": "hi"})
    assert r.status_code == 502 and "unavailable" in r.json()["detail"]
    monkeypatch.setattr("app.config.DEBUG_ERRORS", True)
    r = client.post("/chat", json={"message": "hi"})
    assert r.status_code == 502 and "APIConnectionError" in r.json()["detail"]
