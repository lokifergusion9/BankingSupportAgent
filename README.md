# SecureBank Support Agent

A multi-agent banking support assistant. A customer logs in, chats in a browser, and the system routes each
message to the right specialist agent. Built with LangGraph, Groq (LLM), Chroma + sentence-transformers (RAG),
and FastAPI.

## How it works

```
message -> guardrail -> router -> faq       (answers from the bank's policy PDFs via RAG)
                               -> account   (balance, recent transactions)
                               -> card      (freeze/block a card, asks Yes/No first)
                               -> escalate  (creates a ticket for a human)
```

- **Guardrail** masks card/account numbers and secrets (OTP, PIN, CVV, password) before any LLM sees them.
- **Router** picks one route per message, using recent history for short follow-ups ("yes, do it").
- **Login**: bcrypt password check, then an RS256 JWT. The customer ID always comes from the token, never from
  the request body, and each customer's conversation threads are private.
- **Card blocking** pauses the graph with `interrupt()` and resumes via `/approve`.
- **Conversations** are saved in `data/checkpoints.db`, so they survive a server restart.

## Setup (Windows, PowerShell)

Needs [uv](https://docs.astral.sh/uv/). Python 3.11 is installed by uv automatically.

```powershell
uv sync                                      # create .venv and install dependencies
uv run python scripts/generate_keys.py       # JWT key pair -> keys/
uv run python -m bankingsupportagent.db.seed # mock bank database -> data/bank.db
uv run python -m bankingsupportagent.rag.ingest  # index the policy PDFs -> data/chroma_db
```

Create a `.env` file in the project root:

```
GROQ_API_KEY=your-groq-key
GROQ_MODEL=groq:<model-name>
```

Get a key at https://console.groq.com. `GROQ_MODEL` is `groq:` followed by any Groq chat model that supports
tool calling and structured output.

## Run

```powershell
uv run bankingsupportagent
```

Open http://localhost:8000 and log in with a demo account:

| Customer | Password |
|----------|----------|
| `C1001` (Rahul Sharma) | `rahul-demo-123` |
| `C1002` (Priya Iyer)   | `priya-demo-123` |

These are mock customers for demo only. Interactive API docs are at http://localhost:8000/docs.

### Docker

```powershell
docker compose up --build
```

Run the three setup scripts above once first (or inside the container) so `data/` and `keys/` exist. They are
mounted into the container.

## API

| Endpoint | What it does |
|----------|--------------|
| `POST /login` | `customer_id` + `password` -> bearer token (30 min) |
| `POST /chat` | `thread_id` + `message` -> reply, or `needs_confirmation` |
| `POST /approve` | `thread_id` + `approved` -> answers a pending confirmation |
| `GET /health` | server and database check |

## Tests and evals

```powershell
uv run pytest                              # unit + API tests, no LLM or API key needed
uv run python -m evals.run_router_eval     # router accuracy (calls Groq)
uv run python -m evals.run_e2e_eval        # full-graph cases (calls Groq)
```

Results are written to `evals/results/`. The `notebooks/` folder walks through how each part was built.

## Project layout

```
src/bankingsupportagent/
  api.py          FastAPI app and endpoints
  auth.py         bcrypt + JWT
  graph.py        LangGraph wiring
  guardrails.py   masking of sensitive text
  agents/         router, faq, account, cards, escalation
  tools/          functions the agents can call
  rag/            PDF ingestion and retrieval
  db/seed.py      mock bank data
  static/         chat page
data/docs/        policy PDFs used for RAG
```

`.env`, `keys/`, `*.db` and `data/chroma_db/` are git-ignored: recreate them on a new machine with the setup steps.
