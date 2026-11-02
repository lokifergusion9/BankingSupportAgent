import logging
from contextlib import asynccontextmanager, closing
from pathlib import Path
from typing import Literal

import groq
import jwt
from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.security import HTTPBearer
from langchain.messages import HumanMessage
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command
from pydantic import BaseModel, Field

from bankingsupportagent.auth import authenticate, create_access_token, decode_access_token
from bankingsupportagent.config import CHECKPOINT_DB_PATH
from bankingsupportagent.graph import build_graph
from bankingsupportagent.guardrails import normalize_reply
from bankingsupportagent.rag.retriever import get_vector_store
from bankingsupportagent.tools.account_tools import get_connection

logger = logging.getLogger("securebank.api")
STATIC_DIR = Path(__file__).parent / "static"


# ---------- 1. Startup: build the graph and load the embedding model once ----------

@asynccontextmanager
async def lifespan(app: FastAPI):
    CHECKPOINT_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    # Conversations are saved to disk, so a restart does not wipe them
    with SqliteSaver.from_conn_string(str(CHECKPOINT_DB_PATH)) as checkpointer:
        app.state.graph = build_graph(checkpointer)
        get_vector_store()
        yield


app = FastAPI(title="SecureBank Support API", lifespan=lifespan)


# ---------- 2. Errors: turn failures into the right status code ----------

@app.exception_handler(groq.APIError)
async def llm_failed(request, exc):
    logger.error("LLM call failed on %s: %r", request.url.path, exc)
    return JSONResponse(status_code=503, content={"detail": "The assistant is temporarily unavailable. Please try again."})


@app.exception_handler(Exception)
async def unexpected_error(request, exc):
    logger.exception("Unexpected error on %s", request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Something went wrong on our side. Please try again."})


# ---------- 3. Login guard: who is calling? ----------

bearer = HTTPBearer()   # reads "Authorization: Bearer <token>"; no header -> 401


def get_current_customer(credentials=Depends(bearer)) -> str:
    """Verify the token and return the customer ID inside it."""
    try:
        return decode_access_token(credentials.credentials)
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid or expired token. Please log in again.")


# ---------- 4. Request and response shapes ----------

class LoginRequest(BaseModel):
    customer_id: str = Field(min_length=1, max_length=20)
    password: str = Field(min_length=1, max_length=64)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class ChatRequest(BaseModel):
    thread_id: str = Field(min_length=1, max_length=100)
    message: str = Field(min_length=1, max_length=2000)


class ApproveRequest(BaseModel):
    thread_id: str = Field(min_length=1, max_length=100)
    approved: bool


class ChatResponse(BaseModel):
    status: Literal["ok", "needs_confirmation"]
    reply: str
    route: str | None = None


# ---------- 5. Helpers: talk to the graph ----------

def config_for(customer_id: str, thread_id: str) -> dict:
    """Each customer gets their own threads: Rahul's 'abc' is 'C1001:abc'."""
    return {"configurable": {"thread_id": f"{customer_id}:{thread_id}"}}


def is_waiting_for_confirmation(config: dict) -> bool:
    """True if this conversation is paused at interrupt(), waiting for Yes/No."""
    return bool(app.state.graph.get_state(config).interrupts)


def to_response(result: dict) -> ChatResponse:
    """Turn the graph's result into the reply the app shows."""
    if "__interrupt__" in result:
        question = result["__interrupt__"][0].value["message"]
        return ChatResponse(status="needs_confirmation", reply=question, route=result.get("route"))
    return ChatResponse(status="ok", reply=normalize_reply(result["messages"][-1].content), route=result.get("route"))


# ---------- 6. Endpoints ----------

@app.get("/health")
def health():
    """Is the server up and can it reach the bank database?"""
    try:
        with closing(get_connection()) as conn:
            conn.execute("SELECT 1 FROM customers LIMIT 1")
    except Exception:
        return JSONResponse(status_code=503, content={"status": "database unavailable"})
    return {"status": "ok"}


@app.post("/login", response_model=TokenResponse)
def login(body: LoginRequest):
    if not authenticate(body.customer_id, body.password):
        raise HTTPException(status_code=401, detail="Incorrect customer ID or password.")
    return TokenResponse(access_token=create_access_token(body.customer_id))


@app.post("/chat", response_model=ChatResponse)
def chat(body: ChatRequest, customer_id: str = Depends(get_current_customer)):
    config = config_for(customer_id, body.thread_id)
    if is_waiting_for_confirmation(config):
        raise HTTPException(status_code=409, detail="Please answer the pending confirmation first.")

    # customer_id comes from the verified token, never from the request body
    graph_input = {"messages": [HumanMessage(body.message)], "customer_id": customer_id}
    result = app.state.graph.invoke(graph_input, config=config)
    return to_response(result)


@app.post("/approve", response_model=ChatResponse)
def approve(body: ApproveRequest, customer_id: str = Depends(get_current_customer)):
    config = config_for(customer_id, body.thread_id)
    if not is_waiting_for_confirmation(config):
        raise HTTPException(status_code=409, detail="There is nothing to approve in this conversation.")

    # The dict in resume= becomes the return value of interrupt() inside block_card
    result = app.state.graph.invoke(Command(resume={"approved": body.approved}), config=config)
    return to_response(result)


@app.get("/", include_in_schema=False)
def chat_page():
    return FileResponse(STATIC_DIR / "index.html")