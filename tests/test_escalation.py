import httpx
import pytest
from groq import APIConnectionError, APIError
from langchain.messages import HumanMessage

from bankingsupportagent.agents import escalation as escalation_module
from bankingsupportagent.agents.escalation import escalation, list_tickets


class FailingLLM:
    def __init__(self, error):
        self.error = error

    def with_structured_output(self, schema):
        return self

    def invoke(self, messages):
        raise self.error


def state():
    return {"messages": [HumanMessage("Someone hacked my account")], "customer_id": "C1001"}


def test_ticket_is_still_created_when_the_model_refuses_while_streaming(monkeypatch):
    refusal = APIError("Tool choice is required, but model did not call a tool",
                       request=httpx.Request("POST", "https://api.groq.com"), body=None)
    monkeypatch.setattr(escalation_module, "get_llm", lambda: FailingLLM(refusal))

    reply = escalation(state())["messages"][0].content

    assert "TKT-000001" in reply
    assert [t["reference"] for t in list_tickets("C1001")] == ["TKT-000001"]


def test_outage_does_not_create_a_ticket(monkeypatch):
    outage = APIConnectionError(request=httpx.Request("POST", "https://api.groq.com"))
    monkeypatch.setattr(escalation_module, "get_llm", lambda: FailingLLM(outage))

    with pytest.raises(APIConnectionError):
        escalation(state())

    assert list_tickets("C1001") == []
