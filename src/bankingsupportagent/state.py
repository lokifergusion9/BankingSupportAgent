from typing import Annotated
from typing_extensions import TypedDict
from langgraph.graph.message import add_messages

class SupportState(TypedDict):
    messages: Annotated[list,add_messages]
    route: str
    route_reason: str
    customer_id: str