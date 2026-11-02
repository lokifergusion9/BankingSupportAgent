from langchain.messages import SystemMessage, AIMessage

from bankingsupportagent.config import get_llm
from bankingsupportagent.state import SupportState
from bankingsupportagent.tools.account_tools import ACCOUNT_TOOLS

ACCOUNT_PROMPT = """You are SecureBank's account assistant. You help the logged-in customers with their own account balance
and recent transactions.

Rules:
1. Always use the tool to get the account data. Never guess or invent balances, amounts, dates or transactions.
2. You can only access the logged-in customer's own account. If the customer asks about another account politely refuse.
3. If a tool says the customer is not verified, ask them to log in. Do not try again.
4. Show amount exactly as the tool returns them. Never show full account number.
5. If the customer doesn't recognize a transaction, tell them they can report it as a dispute, and that our card team can help wth it.
6. Keep answers short. Use a short list for transactions.
"""


def account_agent(state:SupportState):
    llm = get_llm().bind_tools(ACCOUNT_TOOLS)
    response = llm.invoke([SystemMessage(ACCOUNT_PROMPT), *state["messages"]])
    return {"messages": [AIMessage(content=response.content, tool_calls=response.tool_calls)]}