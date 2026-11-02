from types import SimpleNamespace

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from langchain.messages import AIMessage

from bankingsupportagent import auth
from bankingsupportagent.api import app
from bankingsupportagent.db.seed import DEMO_PASSWORDS


class FakeGraph:
    """Stands in for the LangGraph graph, so API tests never call the LLM."""

    def __init__(self):
        self.waiting = False
        self.calls = []

    def invoke(self, graph_input, config):
        self.calls.append((graph_input, config))
        if self.waiting:
            return {"__interrupt__": [SimpleNamespace(value={"message": "Block card ending 4821?"})], "route": "card"}
        return {"messages": [AIMessage("Hello from the fake graph")], "route": "faq"}

    def get_state(self, config):
        return SimpleNamespace(interrupts=("pending",) if self.waiting else ())


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

    monkeypatch.setattr(app.state, "graph", graph, raising=False)
    return TestClient(app)


def login(client, customer_id="C1001"):
    response = client.post("/login", json={"customer_id": customer_id, "password": DEMO_PASSWORDS[customer_id]})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_login_wrong_password(client):
    response = client.post("/login", json={"customer_id": "C1001", "password": "wrong"})
    assert response.status_code == 401


def test_login_unknown_customer(client):
    response = client.post("/login", json={"customer_id": "C9999", "password": "whatever"})
    assert response.status_code == 401


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
    graph.waiting = False
    graph.invoke = lambda graph_input, config: {
        "__interrupt__": [SimpleNamespace(value={"message": "Block card ending 4821?"})],
        "route": "card",
    }
    response = client.post("/chat", json={"thread_id": "t1", "message": "block my card"}, headers=login(client))

    assert response.json() == {"status": "needs_confirmation", "reply": "Block card ending 4821?", "route": "card"}


def test_chat_blocked_while_confirmation_pending(client, graph):
    graph.waiting = True
    response = client.post("/chat", json={"thread_id": "t1", "message": "hi"}, headers=login(client))

    assert response.status_code == 409


def test_approve_with_nothing_pending(client):
    response = client.post("/approve", json={"thread_id": "t1", "approved": True}, headers=login(client))

    assert response.status_code == 409


def test_approve_resumes_the_graph(client, graph):
    graph.waiting = True
    graph.invoke = lambda command, config: {"messages": [AIMessage("Card blocked.")], "route": "card"}
    response = client.post("/approve", json={"thread_id": "t1", "approved": True}, headers=login(client))

    assert response.status_code == 200
    assert response.json()["reply"] == "Card blocked."


def test_message_length_limit(client):
    response = client.post("/chat", json={"thread_id": "t1", "message": "x" * 2001}, headers=login(client))

    assert response.status_code == 422
