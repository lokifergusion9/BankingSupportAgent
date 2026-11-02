from groq import BadRequestError
from typing import Literal
from pydantic import BaseModel, Field
from langchain.messages import SystemMessage, HumanMessage, AIMessage
from bankingsupportagent.config import get_llm
from bankingsupportagent.state import SupportState

HISTORY_MESSAGES = 6

class RouteDecision(BaseModel):
    route: Literal["faq","account","card","escalate"] = Field(
        description="which team should handle the customer's message"
    )
    reason: str = Field(description="One short sentence explaining why this route was chosen")


ROUTER_PROMPT = """You are the routing assistant for SecureBank customer support.
Read the customer's message and choose exactly one route:

-faq: general questions about bank products, fees, interest rates, documents, branch timings or policies. No personal account
data is needed.
-account: questions about the customer's own account, such as balance, recent transactions or statements
-card: debit/credit card issues, such as a lost or stolen card, blocking a card, card limits, or a charge the customer does
not recognize
-escalate: anything that needs a human, such as suspected fraud, a hacked account, complaints, legal issues, or when the customer
asks for a human.

If a message fits more than one route, choose the more serious one (escalate>card>account>faq).

Use the recent conversation to understand short follow-ups such as "yes, do it".
Disputes about a transaction the customer does not recognise go to card; use
escalate only for suspected fraud, a hacked account, complaints or a request for a human."""


def format_history(messages) -> str:
    """Turn recent messages into plain text. Tool calls and tool results are skipped."""
    lines = []
    for m in messages:
        if isinstance(m, HumanMessage):
            lines.append(f"Customer: {m.content}")
        elif isinstance(m, AIMessage) and m.content:
            lines.append(f"Assistant: {m.content}")
    return "\n".join(lines)




def route_query(query: str, history: str = "") -> RouteDecision:
    llm = get_llm()
    router = llm.with_structured_output(RouteDecision)
    if history:
        text = f"Recent conversation:\n{history}\n\nLatest customer message:\n{query}"
    else:
        text = query
    return router.invoke([SystemMessage(ROUTER_PROMPT), HumanMessage(text)])


def router_node(state: SupportState):
    messages = state["messages"]
    history = format_history(messages[-(HISTORY_MESSAGES + 1):-1])
    try:
        decision = route_query(messages[-1].content, history)
        return {"route": decision.route, "route_reason": decision.reason}
    except BadRequestError:
        # The model refused or failed to fill in the RouteDecision (e.g. on an attack message).
        # Never crash: hand the conversation to a human instead.
        return {
            "route": "escalate",
            "route_reason": "Router could not classify the message; sent to a human to be safe.",
        }


# def router_node(state: SupportState):
#     messages = state["messages"]
#     history = format_history(messages[-(HISTORY_MESSAGES + 1):-1])
#     decision = route_query(messages[-1].content, history)
#     return {"route": decision.route, "route_reason": decision.reason}