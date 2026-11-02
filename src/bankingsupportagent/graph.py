from langgraph.graph import StateGraph,START,END
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.prebuilt import ToolNode, tools_condition

from bankingsupportagent.agents.faq import faq_agent
from bankingsupportagent.state import SupportState
from bankingsupportagent.agents.router import router_node
from bankingsupportagent.agents.account import account_agent
from bankingsupportagent.tools.account_tools import ACCOUNT_TOOLS
from bankingsupportagent.agents.cards import card_agent
from bankingsupportagent.tools.card_tools import CARD_TOOLS
from bankingsupportagent.agents.escalation import escalation
from bankingsupportagent.guardrails import guardrail_node


# Decides which node runs after the router
def pick_agent(state:SupportState) -> str:
    return state["route"]


def build_graph(checkpointer=None):
    """Build the support graph. Without a checkpointer, conversations live in memory only."""
    builder = StateGraph(SupportState)

    #Nodes
    builder.add_node("router",router_node)
    builder.add_node("faq_agent",faq_agent)
    builder.add_node("account_agent",account_agent)
    builder.add_node("account_tools", ToolNode(ACCOUNT_TOOLS))
    builder.add_node("card_agent",card_agent)
    builder.add_node("card_tools",ToolNode(CARD_TOOLS))
    builder.add_node("escalation",escalation)
    builder.add_node("guardrail", guardrail_node)

    #Edges
    builder.add_edge(START, "guardrail")
    builder.add_edge("guardrail", "router")
    builder.add_conditional_edges(
        "router",
        pick_agent,
        {
            "faq": "faq_agent",
            "account": "account_agent",
            "card": "card_agent",
            "escalate": "escalation",
        },
    )

    builder.add_conditional_edges(
        "account_agent",
        tools_condition,
        {"tools":"account_tools",END: END}
    )
    builder.add_edge("account_tools","account_agent")

    builder.add_conditional_edges(
        "card_agent",
        tools_condition,
        {"tools": "card_tools",END:END}
    )
    builder.add_edge("card_tools","card_agent")
    

    for node in ["faq_agent","escalation"]:
        builder.add_edge(node,END)

    return builder.compile(checkpointer=checkpointer or InMemorySaver())