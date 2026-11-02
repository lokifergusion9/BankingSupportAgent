from groq import BadRequestError
from contextlib import closing
from typing import Literal

from pydantic import BaseModel, Field
from langchain.messages import SystemMessage, HumanMessage, AIMessage

from bankingsupportagent.config import get_llm
from bankingsupportagent.state import SupportState
from bankingsupportagent.agents.router import format_history
from bankingsupportagent.tools.account_tools import get_connection


Category = Literal["fraud","account_security","complaint","human_request","other"]

PRIORITY = {
    "fraud":"high",
    "account_security":"high",
    "complaint":"medium",
    "human_request":"medium",
    "other":"low"
}

CONTACT_TIME = {
    "high": "within 2 hours",
    "medium": "within 1 working day",
    "low": "within 2 working day"
}

SAFETY_ADVICE = (
    "\n\nWhile you wait: if your card may be at risk, block it in the app (Cards > Block Card) "
    "or call our 24x7 helpline 1800-000-1234. Never share your OTP, PIN or password with anyone, "
    "including people who say they are from SecureBank."
)


class EscalationTicket(BaseModel):
    category: Category = Field(
        description="fraud: unauthorised transactions or a stolen card being used. "
        "account_security: hacked account, unknown login, changed mobile number, SIM swap. "
        "complaint: unhappy with a service, staff or charge. "
        "human_request: the customer asks for a person or manager. "
        "other: anything else."
    )
    summary: str = Field(
        description="One or two sentences for the specialist: what happened, when, and what the "
        "customer wants. No full card or account numbers, PINs, OTPs or passwords."
    )


ESCALATION_PROMPT = """You prepare hand-over tickets for SecureBank's human support specialists. Read the conversation and fill
the ticket.

Rules:
1. Choose the category that best fits the customer's main problem.
2. Write a short, factual summary that lets a specialist acts without reading the whole chat.
3. Include amounts, dates and merchant name if the customer gave them.
4. Never include full card numbers, account numbers, PINs, OTPs, or passwords in the summary. Last 4 digits are fine.
5. Do not add anything the customer did not say."""


def create_ticket(customer_id, category:str, priority:str, summary:str) -> str:
    with closing(get_connection()) as conn:
        cursor = conn.execute(
            "INSERT INTO tickets (customer_id, category, priority, summary) VALUES (?,?,?,?)",
            (customer_id,category,priority,summary),
        )
        conn.commit()
        ticket_number = cursor.lastrowid
    return f"TKT-{ticket_number:06d}"


def escalation(state:SupportState):
    # 1. LLM understand the conversation and fill in the ticket (structured output)
    conversation = format_history(state["messages"][-7:])
    llm = get_llm().with_structured_output(EscalationTicket)
    try:
        ticket = llm.invoke([SystemMessage(ESCALATION_PROMPT), HumanMessage(conversation)])
    except BadRequestError:
        # The model could not fill in the ticket. Still create one, so nothing is lost.
        ticket = EscalationTicket(
            category="human_request",
            summary="Automatic summary failed. Specialist should read the conversation.",
        )


    # 2. Code: priority, ticket number and reply
    priority = PRIORITY[ticket.category]
    reference = create_ticket(state.get("customer_id"),ticket.category,priority,ticket.summary)


    reply = (
        f"I've passed this to a SecureBank specialist. Your ticket reference is {reference}. "
        f"Someone will contact you on your registered mobile number {CONTACT_TIME[priority]}."
    )
    if ticket.category in ("fraud", "account_security"):
        reply += SAFETY_ADVICE

    return {"messages": [AIMessage(reply)]}