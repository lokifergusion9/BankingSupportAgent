import json
import logging
import time
import uuid
from contextlib import asynccontextmanager, closing
from pathlib import Path
from typing import Literal

import groq
import jwt
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.security import HTTPBearer
from langchain.messages import AIMessage, AIMessageChunk, HumanMessage
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command
from pydantic import BaseModel, Field

from bankingsupportagent.agents.escalation import list_tickets
from bankingsupportagent.auth import authenticate, create_access_token, decode_access_token
from bankingsupportagent.bootstrap import ensure_ready
from bankingsupportagent.config import (
    CHAT_MAX_PER_MINUTE, CHECKPOINT_DB_PATH, LOGIN_MAX_FAILURES, LOGIN_WINDOW_SECONDS,
)
from bankingsupportagent.graph import build_graph
from bankingsupportagent.guardrails import normalize_reply
from bankingsupportagent.ratelimit import RateLimiter
from bankingsupportagent.rag.retriever import get_reranker, get_vector_store
from bankingsupportagent.tools.account_tools import get_connection

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("securebank.api")
STATIC_DIR = Path(__file__).parent / "static"

login_failures = RateLimiter(LOGIN_MAX_FAILURES, LOGIN_WINDOW_SECONDS)
chat_requests = RateLimiter(CHAT_MAX_PER_MINUTE, 60)


# ---------- 1. Startup: build the graph and load the models once ----------

@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_ready()          # a fresh machine gets its keys, demo database and policy index automatically
    CHECKPOINT_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    # Conversations are saved to disk, so a restart does not wipe them
    with SqliteSaver.from_conn_string(str(CHECKPOINT_DB_PATH)) as checkpointer:
        app.state.graph = build_graph(checkpointer)
        get_vector_store()
        get_reranker()
        yield


app = FastAPI(title="SecureBank Support API", lifespan=lifespan)

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'",
}


@app.middleware("http")
async def add_headers_and_log(request: Request, call_next):
    """Log every request (never its body, which can hold personal data) and add safety headers."""
    request_id = uuid.uuid4().hex[:8]
    started = time.perf_counter()
    response = await call_next(request)
    milliseconds = (time.perf_counter() - started) * 1000
    logger.info("%s %s -> %s in %.0f ms [%s]", request.method, request.url.path, response.status_code, milliseconds, request_id)
    response.headers["X-Request-ID"] = request_id
    for name, value in SECURITY_HEADERS.items():
        response.headers[name] = value
    return response


# ---------- 2. Errors: turn failures into the right status code ----------

LLM_UNAVAILABLE = "The assistant is temporarily unavailable. Please try again."
SERVER_ERROR = "Something went wrong on our side. Please try again."


@app.exception_handler(groq.APIError)
async def llm_failed(request, exc):
    logger.error("LLM call failed on %s: %r", request.url.path, exc)
    return JSONResponse(status_code=503, content={"detail": LLM_UNAVAILABLE})


@app.exception_handler(Exception)
async def unexpected_error(request, exc):
    logger.exception("Unexpected error on %s", request.url.path)
    return JSONResponse(status_code=500, content={"detail": SERVER_ERROR})


# ---------- 3. Login guard: who is calling? ----------

bearer = HTTPBearer()   # reads "Authorization: Bearer <token>"; no header -> 401


def get_current_customer(credentials=Depends(bearer)) -> str:
    """Verify the token and return the customer ID inside it."""
    try:
        return decode_access_token(credentials.credentials)
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid or expired token. Please log in again.")


def check_chat_rate(customer_id: str = Depends(get_current_customer)) -> str:
    """Same as get_current_customer, but also stops one customer from flooding the assistant."""
    wait = chat_requests.retry_after(customer_id)
    if wait:
        raise HTTPException(status_code=429, detail="You are sending messages too fast. Please wait a moment.",
                            headers={"Retry-After": str(wait)})
    chat_requests.record(customer_id)
    return customer_id


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


def response_from_saved_state(config: dict) -> ChatResponse:
    """Same as to_response, for after a streamed run, when only the saved conversation is at hand."""
    state = app.state.graph.get_state(config)
    route = state.values.get("route")
    if state.interrupts:
        return ChatResponse(status="needs_confirmation", reply=state.interrupts[0].value["message"], route=route)
    return ChatResponse(status="ok", reply=normalize_reply(state.values["messages"][-1].content), route=route)


# The agents that write the answer. The router and the ticket step also use the LLM, but their output is not for the customer.
ANSWER_NODES = {"faq_agent", "account_agent", "card_agent"}
NO_ANSWER = "NO_ANSWER"     # the FAQ agent's "I don't know" marker; it is replaced by a polite fallback


def sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def stream_reply(graph_input, config: dict):
    """Server-sent events: many `token` events while the answer is written, then one `done` (or `error`).

    `done` carries the final reply, which is the one to keep: it may differ from the streamed text
    (for example the FAQ fallback, or a confirmation question).
    """
    held = ""           # start of the answer, kept back while it could still turn out to be NO_ANSWER
    started = False
    try:
        for chunk, metadata in app.state.graph.stream(graph_input, config, stream_mode="messages"):
            if metadata.get("langgraph_node") not in ANSWER_NODES:
                continue
            if not isinstance(chunk, AIMessageChunk) or not isinstance(chunk.content, str) or not chunk.content:
                continue
            text = normalize_reply(chunk.content)
            if started:
                yield sse("token", {"text": text})
                continue
            held += text
            if NO_ANSWER.startswith(held.strip()):
                continue
            started = True
            yield sse("token", {"text": held})
        yield sse("done", response_from_saved_state(config).model_dump())
    except groq.APIError as error:
        logger.error("LLM call failed while streaming: %r", error)
        yield sse("error", {"detail": LLM_UNAVAILABLE})
    except Exception:
        logger.exception("Unexpected error while streaming")
        yield sse("error", {"detail": SERVER_ERROR})


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
def login(body: LoginRequest, request: Request):
    # Locking per customer ID *and* client address: someone guessing passwords cannot lock the real customer out
    key = (request.client.host if request.client else "unknown", body.customer_id)
    wait = login_failures.retry_after(key)
    if wait:
        raise HTTPException(status_code=429, detail="Too many failed attempts. Please try again later.",
                            headers={"Retry-After": str(wait)})
    if not authenticate(body.customer_id, body.password):
        login_failures.record(key)
        raise HTTPException(status_code=401, detail="Incorrect customer ID or password.")
    login_failures.reset(key)
    return TokenResponse(access_token=create_access_token(body.customer_id))


def start_turn(body: ChatRequest, customer_id: str):
    """Shared by /chat and /chat/stream: the graph input and config for a new customer message."""
    config = config_for(customer_id, body.thread_id)
    if is_waiting_for_confirmation(config):
        raise HTTPException(status_code=409, detail="Please answer the pending confirmation first.")
    # customer_id comes from the verified token, never from the request body
    return {"messages": [HumanMessage(body.message)], "customer_id": customer_id}, config


@app.post("/chat", response_model=ChatResponse)
def chat(body: ChatRequest, customer_id: str = Depends(check_chat_rate)):
    graph_input, config = start_turn(body, customer_id)
    result = app.state.graph.invoke(graph_input, config=config)
    return to_response(result)


@app.post("/chat/stream")
def chat_stream(body: ChatRequest, customer_id: str = Depends(check_chat_rate)):
    """Like /chat, but the answer arrives word by word as server-sent events."""
    graph_input, config = start_turn(body, customer_id)
    return StreamingResponse(stream_reply(graph_input, config), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/approve", response_model=ChatResponse)
def approve(body: ApproveRequest, customer_id: str = Depends(get_current_customer)):
    config = config_for(customer_id, body.thread_id)
    if not is_waiting_for_confirmation(config):
        raise HTTPException(status_code=409, detail="There is nothing to approve in this conversation.")

    # The dict in resume= becomes the return value of interrupt() inside block_card
    result = app.state.graph.invoke(Command(resume={"approved": body.approved}), config=config)
    return to_response(result)


@app.get("/history")
def history(thread_id: str = Query(min_length=1, max_length=100), customer_id: str = Depends(get_current_customer)):
    """The saved conversation, so a refreshed page can pick up where it left off."""
    state = app.state.graph.get_state(config_for(customer_id, thread_id))
    saved = state.values.get("messages", []) if state.values else []
    messages = [
        {"role": "user" if isinstance(m, HumanMessage) else "assistant", "content": normalize_reply(m.content)}
        for m in saved
        if isinstance(m, (HumanMessage, AIMessage)) and isinstance(m.content, str) and m.content
    ]
    pending = state.interrupts[0].value["message"] if state.interrupts else None
    return {"messages": messages, "pending_confirmation": pending}


@app.get("/tickets")
def tickets(customer_id: str = Depends(get_current_customer)):
    """The logged-in customer's own support tickets."""
    return {"tickets": list_tickets(customer_id)}


@app.get("/", include_in_schema=False)
def chat_page():
    return FileResponse(STATIC_DIR / "index.html")
