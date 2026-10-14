from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["products"] == 30


def test_index_served():
    r = client.get("/")
    assert r.status_code == 200
    assert "Shopping Assistant" in r.text


def test_empty_message_rejected():
    assert client.post("/chat", json={"message": ""}).status_code == 422


def test_too_long_message_rejected():
    assert client.post("/chat", json={"message": "x" * 1001}).status_code == 422
