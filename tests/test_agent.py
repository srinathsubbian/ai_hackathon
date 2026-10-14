import json
from types import SimpleNamespace as NS

import pytest
from fastapi.testclient import TestClient

from app import main
from app.agent import RecommenderAgent, extract_budget
from app.catalog import Catalog

CSV = "data/products.csv"


def msg(content=None, tool_calls=None):
    return NS(content=content, tool_calls=tool_calls)


def call(id_, name, **args):
    return NS(id=id_, function=NS(name=name, arguments=json.dumps(args)))


class FakeLLM:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def complete(self, messages, tools=None):
        self.calls.append({"messages": list(messages), "tools": tools})
        return self.responses.pop(0)


def make_agent(responses):
    agent = RecommenderAgent(Catalog(CSV))
    agent.llm = FakeLLM(responses)
    return agent


def test_native_runs_tool_then_answers(monkeypatch):
    monkeypatch.setattr("app.config.TOOL_MODE", "native")
    agent = make_agent([
        msg(tool_calls=[call("c1", "search_products", query="winter warm", max_price=200)]),
        msg("Try the PeakShell jacket (P005)."),
    ])
    messages = [{"role": "user", "content": "warm winter jacket under $200"}]
    reply = agent.run_turn(messages)
    assert "PeakShell" in reply
    tool_msg = next(m for m in messages if m["role"] == "tool")
    assert tool_msg["tool_call_id"] == "c1" and "P005" in tool_msg["content"]
    assert agent.llm.calls[0]["tools"]  # tools were offered to the model
    assert agent.llm.calls[0]["messages"][0]["role"] == "system"


def test_native_survives_bad_tool_args(monkeypatch):
    monkeypatch.setattr("app.config.TOOL_MODE", "native")
    bad = NS(id="c1", function=NS(name="search_products", arguments="{not json"))
    agent = make_agent([msg(tool_calls=[bad]), msg("Sorry, let me rephrase.")])
    messages = [{"role": "user", "content": "hi"}]
    assert agent.run_turn(messages)
    assert "error" in next(m for m in messages if m["role"] == "tool")["content"]


def test_native_step_limit(monkeypatch):
    monkeypatch.setattr("app.config.TOOL_MODE", "native")
    monkeypatch.setattr("app.config.MAX_STEPS", 2)
    agent = make_agent([msg(tool_calls=[call(f"c{i}", "search_products", query="x")]) for i in range(5)])
    assert "couldn't finish" in agent.run_turn([{"role": "user", "content": "hi"}])


def test_rag_mode_injects_catalog_matches(monkeypatch):
    monkeypatch.setattr("app.config.TOOL_MODE", "rag")
    agent = make_agent([msg("Here are options.")])
    messages = [{"role": "user", "content": "warm winter jacket under $200"}]
    assert agent.run_turn(messages) == "Here are options."
    call_ = agent.llm.calls[0]
    assert call_["tools"] is None  # no function-calling needed
    system = call_["messages"][0]["content"]
    assert "P005" in system and "P010" not in system  # relevant item in, unrelated/over-budget out
    assert messages[-1] == {"role": "assistant", "content": "Here are options."}


@pytest.mark.parametrize("text,expected", [
    ("jacket under $200", 200.0),
    ("shoes below 1,500 please", 1500.0),
    ("anything up to ₹999", 999.0),
    ("under 100 ... actually under 80", 80.0),
    ("a nice jacket", None),
])
def test_extract_budget(text, expected):
    assert extract_budget(text) == expected


def test_chat_endpoint_keeps_session(monkeypatch):
    monkeypatch.setattr("app.config.TOOL_MODE", "native")
    main.agent.llm = FakeLLM([msg("What's your budget?"), msg("Here are some options.")])
    client = TestClient(main.app)
    r1 = client.post("/chat", json={"message": "running shoes"})
    assert r1.status_code == 200
    sid = r1.json()["session_id"]
    r2 = client.post("/chat", json={"message": "under $100", "session_id": sid})
    assert r2.json()["session_id"] == sid
    history = main.agent.llm.calls[1]["messages"]
    assert [m["role"] for m in history] == ["system", "user", "assistant", "user"]


def test_chat_without_llm_config_returns_500(monkeypatch):
    from app.llm import LLMClient
    monkeypatch.setattr("app.config.LLM_MODEL", "")
    monkeypatch.setattr("app.config.LLM_API_KEY", "")
    monkeypatch.setattr("app.config.LLM_BASE_URL", "")
    main.agent.llm = LLMClient()
    r = TestClient(main.app).post("/chat", json={"message": "hi"})
    assert r.status_code == 500
    assert r.json()["detail"] == "Server is not configured correctly."
