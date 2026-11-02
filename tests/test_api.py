import json
from types import SimpleNamespace

import groq
import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from langchain.messages import AIMessage, AIMessageChunk, HumanMessage

from bankingsupportagent import api, auth
from bankingsupportagent.agents.escalation import create_ticket
from bankingsupportagent.api import app
from bankingsupportagent.db.seed import DEMO_PASSWORDS
from bankingsupportagent.ratelimit import RateLimiter


class FakeGraph:
    """Stands in for the LangGraph graph, so API tests never call the LLM."""

    def __init__(self):
        self.waiting = False
        self.calls = []
        self.tokens = ["Hello ", "from the fake graph"]     # what stream() "writes"
        self.stream_error = None
        self.pause_after_stream = False
        self.saved = []                                    # the saved conversation get_state() returns

    def invoke(self, graph_input, config):
        self.calls.append((graph_input, config))
        if self.waiting:
            return {"__interrupt__": [SimpleNamespace(value={"message": "Block card ending 4821?"})], "route": "card"}
        return {"messages": [AIMessage("Hello from the fake graph")], "route": "faq"}

    def stream(self, graph_input, config, stream_mode):
        self.calls.append((graph_input, config))
        yield AIMessageChunk(content="routing noise"), {"langgraph_node": "router"}     # must never reach the customer
        for token in self.tokens:
            yield AIMessageChunk(content=token), {"langgraph_node": "faq_agent"}
        if self.stream_error:
            raise self.stream_error
        if self.pause_after_stream:
            self.waiting = True

    def get_state(self, config):
        interrupts = (SimpleNamespace(value={"message": "Block card ending 4821?"}),) if self.waiting else ()
        messages = self.saved or [AIMessage("".join(self.tokens))]
        return SimpleNamespace(interrupts=interrupts, values={"messages": messages, "route": "faq"})


@pytest.fixture
def graph():
    return FakeGraph()


@pytest.fixture
def client(graph, tmp_path, monkeypatch):
    """A client with throwaway JWT keys and a fake graph. The lifespan is not run (no `with`)."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    (tmp_path / "private.pem").write_bytes(key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    (tmp_path / "public.pem").write_bytes(key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
    monkeypatch.setattr(auth, "JWT_PRIVATE_KEY_PATH", tmp_path / "private.pem")
    monkeypatch.setattr(auth, "JWT_PUBLIC_KEY_PATH", tmp_path / "public.pem")
    auth.private_key.cache_clear()
    auth.public_key.cache_clear()

    api.login_failures.reset()
    api.chat_requests.reset()
    monkeypatch.setattr(app.state, "graph", graph, raising=False)
    return TestClient(app)


def login(client, customer_id="C1001"):
    response = client.post("/login", json={"customer_id": customer_id, "password": DEMO_PASSWORDS[customer_id]})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def parse_events(text: str) -> list[tuple[str, dict]]:
    """Turn a server-sent-events body into [(event, data), ...]."""
    events = []
    for block in text.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines())
        events.append((lines["event"], json.loads(lines["data"])))
    return events


# ---------- Basics ----------

def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_security_headers_and_request_id(client):
    response = client.get("/health")

    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert "default-src 'self'" in response.headers["Content-Security-Policy"]
    assert len(response.headers["X-Request-ID"]) == 8


def test_login_wrong_password(client):
    response = client.post("/login", json={"customer_id": "C1001", "password": "wrong"})
    assert response.status_code == 401


def test_login_unknown_customer(client):
    response = client.post("/login", json={"customer_id": "C9999", "password": "whatever"})
    assert response.status_code == 401


def test_login_locks_after_repeated_failures(client):
    for _ in range(5):
        assert client.post("/login", json={"customer_id": "C1001", "password": "wrong"}).status_code == 401

    # Locked now, even for the right password
    locked = client.post("/login", json={"customer_id": "C1001", "password": DEMO_PASSWORDS["C1001"]})
    assert locked.status_code == 429
    assert int(locked.headers["Retry-After"]) > 0

    # Another customer is not affected
    assert client.post("/login", json={"customer_id": "C1002", "password": DEMO_PASSWORDS["C1002"]}).status_code == 200


def test_successful_login_clears_failures(client):
    for _ in range(4):
        client.post("/login", json={"customer_id": "C1001", "password": "wrong"})
    login(client)
    for _ in range(4):
        assert client.post("/login", json={"customer_id": "C1001", "password": "wrong"}).status_code == 401


# ---------- /chat ----------

def test_chat_needs_a_token(client):
    response = client.post("/chat", json={"thread_id": "t1", "message": "hi"})
    assert response.status_code in (401, 403)


def test_chat_rejects_bad_token(client):
    response = client.post("/chat", json={"thread_id": "t1", "message": "hi"}, headers={"Authorization": "Bearer nonsense"})
    assert response.status_code == 401


def test_chat_uses_customer_from_token(client, graph):
    response = client.post("/chat", json={"thread_id": "t1", "message": "hi"}, headers=login(client, "C1002"))

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "reply": "Hello from the fake graph", "route": "faq"}
    graph_input, config = graph.calls[0]
    assert graph_input["customer_id"] == "C1002"
    assert config["configurable"]["thread_id"] == "C1002:t1"      # threads are private per customer


def test_chat_asks_for_confirmation(client, graph):
    graph.invoke = lambda graph_input, config: {
        "__interrupt__": [SimpleNamespace(value={"message": "Block card ending 4821?"})],
        "route": "card",
    }
    response = client.post("/chat", json={"thread_id": "t1", "message": "block my card"}, headers=login(client))

    assert response.json() == {"status": "needs_confirmation", "reply": "Block card ending 4821?", "route": "card"}


def test_chat_cleans_lookalike_characters(client, graph):
    graph.invoke = lambda graph_input, config: {"messages": [AIMessage("DSP‑000011")], "route": "card"}
    response = client.post("/chat", json={"thread_id": "t1", "message": "dispute"}, headers=login(client))

    assert response.json()["reply"] == "DSP-000011"


def test_chat_blocked_while_confirmation_pending(client, graph):
    graph.waiting = True
    response = client.post("/chat", json={"thread_id": "t1", "message": "hi"}, headers=login(client))

    assert response.status_code == 409


def test_chat_is_rate_limited(client, monkeypatch):
    monkeypatch.setattr(api, "chat_requests", RateLimiter(2, 60))
    headers = login(client)
    body = {"thread_id": "t1", "message": "hi"}

    assert client.post("/chat", json=body, headers=headers).status_code == 200
    assert client.post("/chat", json=body, headers=headers).status_code == 200
    third = client.post("/chat", json=body, headers=headers)

    assert third.status_code == 429
    assert int(third.headers["Retry-After"]) > 0


def test_message_length_limit(client):
    response = client.post("/chat", json={"thread_id": "t1", "message": "x" * 2001}, headers=login(client))

    assert response.status_code == 422


def test_llm_failure_becomes_503(client, graph):
    request = httpx.Request("POST", "https://api.groq.com")
    graph.invoke = lambda graph_input, config: (_ for _ in ()).throw(groq.APIConnectionError(request=request))

    response = client.post("/chat", json={"thread_id": "t1", "message": "hi"}, headers=login(client))

    assert response.status_code == 503
    assert "temporarily unavailable" in response.json()["detail"]


# ---------- /chat/stream ----------

def test_stream_sends_tokens_then_done(client, graph):
    response = client.post("/chat/stream", json={"thread_id": "t1", "message": "hi"}, headers=login(client))

    assert response.headers["content-type"].startswith("text/event-stream")
    events = parse_events(response.text)
    assert [name for name, _ in events] == ["token", "token", "done"]
    assert "".join(data["text"] for name, data in events if name == "token") == "Hello from the fake graph"
    assert events[-1][1] == {"status": "ok", "reply": "Hello from the fake graph", "route": "faq"}


def test_stream_holds_back_the_no_answer_marker(client, graph):
    graph.tokens = ["NO", "_ANSWER"]
    graph.saved = [AIMessage("I'm sorry, I don't have that information.")]

    response = client.post("/chat/stream", json={"thread_id": "t1", "message": "hi"}, headers=login(client))

    events = parse_events(response.text)
    assert [name for name, _ in events] == ["done"]       # the marker was never shown
    assert events[0][1]["reply"] == "I'm sorry, I don't have that information."


def test_stream_does_not_hold_back_normal_text(client, graph):
    graph.tokens = ["No", " problem, ", "here is the answer"]

    events = parse_events(client.post("/chat/stream", json={"thread_id": "t1", "message": "hi"}, headers=login(client)).text)

    streamed = "".join(data["text"] for name, data in events if name == "token")
    assert streamed == "No problem, here is the answer"


def test_stream_reports_confirmation(client, graph):
    graph.tokens = []
    graph.pause_after_stream = True         # the run ends paused at interrupt(), waiting for Yes/No

    events = parse_events(client.post("/chat/stream", json={"thread_id": "t1", "message": "block"}, headers=login(client)).text)

    assert events == [("done", {"status": "needs_confirmation", "reply": "Block card ending 4821?", "route": "faq"})]


def test_stream_reports_llm_failure_as_an_event(client, graph):
    graph.stream_error = groq.APIConnectionError(request=httpx.Request("POST", "https://api.groq.com"))

    events = parse_events(client.post("/chat/stream", json={"thread_id": "t1", "message": "hi"}, headers=login(client)).text)

    assert events[-1][0] == "error"
    assert "temporarily unavailable" in events[-1][1]["detail"]


def test_stream_needs_a_token(client):
    assert client.post("/chat/stream", json={"thread_id": "t1", "message": "hi"}).status_code in (401, 403)


# ---------- /approve ----------

def test_approve_with_nothing_pending(client):
    response = client.post("/approve", json={"thread_id": "t1", "approved": True}, headers=login(client))

    assert response.status_code == 409


def test_approve_resumes_the_graph(client, graph):
    graph.waiting = True
    graph.invoke = lambda command, config: {"messages": [AIMessage("Card blocked.")], "route": "card"}
    response = client.post("/approve", json={"thread_id": "t1", "approved": True}, headers=login(client))

    assert response.status_code == 200
    assert response.json()["reply"] == "Card blocked."


# ---------- /history and /tickets ----------

def test_history_returns_only_visible_messages(client, graph):
    graph.saved = [
        HumanMessage("What is my balance?"),
        AIMessage("", tool_calls=[{"name": "get_balance", "args": {}, "id": "1"}]),     # internal step, hidden
        AIMessage("Your balance is Rs. 85,420.50"),
    ]
    data = client.get("/history", params={"thread_id": "t1"}, headers=login(client)).json()

    assert data["messages"] == [
        {"role": "user", "content": "What is my balance?"},
        {"role": "assistant", "content": "Your balance is Rs. 85,420.50"},
    ]
    assert data["pending_confirmation"] is None


def test_history_shows_pending_confirmation(client, graph):
    graph.waiting = True

    data = client.get("/history", params={"thread_id": "t1"}, headers=login(client)).json()

    assert data["pending_confirmation"] == "Block card ending 4821?"


def test_history_needs_a_token(client):
    assert client.get("/history", params={"thread_id": "t1"}).status_code in (401, 403)


def test_tickets_shows_only_own_tickets(client):
    create_ticket("C1001", "fraud", "high", "Unknown debit")
    create_ticket("C1002", "complaint", "medium", "Slow service")

    tickets = client.get("/tickets", headers=login(client, "C1001")).json()["tickets"]

    assert [(t["reference"], t["category"]) for t in tickets] == [("TKT-000001", "fraud")]
