<div align="center">

# SecureBank Support Agent

**A multi-agent AI assistant for banking customer support.**
It answers policy questions from the bank's own documents, shows a customer their balance and
transactions, freezes or blocks cards with a confirmation step, and hands serious cases to a human.

![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)
![LangGraph](https://img.shields.io/badge/LangGraph-multi--agent-1C3C3C)
![Groq](https://img.shields.io/badge/LLM-Groq-F55036)
![Evals](https://img.shields.io/badge/end--to--end%20evals-28%2F28-brightgreen)
![Retrieval](https://img.shields.io/badge/policy%20search-94%25%20hit%404-brightgreen)

Built by **Lokesh**

<img src="docs/screenshots/02-faq.png" alt="The assistant answering a policy question with its source" width="760">

</div>

---

## Highlights

- **Five specialists, one chat.** A router sends each message to an FAQ, account, card or escalation agent.
- **Answers grounded in the bank's documents.** Policy questions use retrieval over six PDFs, a re-ranker, and
  cite the file and page.
- **Safe by design.** Card numbers, PAN and OTPs are masked before any AI model sees them, a customer can only
  reach their own data, and blocking a card always needs an explicit "Yes".
- **Measured, not guessed.** Three evals (search quality, routing, whole conversations) and 70+ tests back every
  claim in this README.
- **Pleasant to use.** Answers stream in word by word, a page refresh keeps the conversation, and customers can
  list their own support tickets.

## See it work

<table>
<tr>
<td width="50%"><b>1. Log in</b><br>Token-based login with lockout after repeated wrong passwords.<br><br><img src="docs/screenshots/01-login.png" alt="Login screen"></td>
<td width="50%"><b>2. Account questions</b><br>Balance and transactions come from the database through tools, never from the model's memory.<br><br><img src="docs/screenshots/03-account.png" alt="Balance and last three transactions"></td>
</tr>
<tr>
<td width="50%"><b>3. Confirm before anything irreversible</b><br>Blocking a card pauses the conversation until the customer answers Yes or No.<br><br><img src="docs/screenshots/04-card-confirmation.png" alt="Card block confirmation with Yes and No buttons"></td>
<td width="50%"><b>4. Hand-over to a human</b><br>Fraud and hacked-account reports create a high-priority ticket and give safety advice.<br><br><img src="docs/screenshots/05-escalation.png" alt="Escalation reply with a ticket number"></td>
</tr>
<tr>
<td width="50%"><b>5. Track your tickets</b><br>Customers see only their own tickets.<br><br><img src="docs/screenshots/06-tickets.png" alt="List of the customer's support tickets"></td>
<td width="50%"><b>6. Attacks go nowhere</b><br>A prompt-injection attempt leaks no data and is passed to a specialist.<br><br><img src="docs/screenshots/07-security.png" alt="Prompt injection attempt handed to a specialist"></td>
</tr>
</table>

<sub>All data is mock data. The screenshots were taken with `groq:openai/gpt-oss-120b`; the default model is `gpt-oss-20b`.</sub>

## How it works

```mermaid
flowchart LR
    U([Customer]) --> G["Guardrail<br/>masks card no., PAN, OTP, PIN"]
    G --> R{"Router"}
    R -->|faq| F["FAQ agent<br/>search + re-rank policy PDFs"]
    R -->|account| A["Account agent<br/>balance, transactions"]
    R -->|card| C["Card agent<br/>freeze, block, dispute"]
    R -->|escalate| E["Escalation<br/>creates a ticket"]
    C -. "asks Yes / No first" .-> U
```

1. The **guardrail** hides sensitive numbers before the message reaches any model or is saved.
2. The **router** picks one route, using recent messages for short follow-ups such as "yes, do it".
3. Each **agent** has its own prompt and only the tools it needs. Money and card actions happen in plain code
   behind those tools; the model decides *what* to call, not *how* data is read or changed.
4. **Card blocking** uses LangGraph's `interrupt()`: the graph pauses, the page shows Yes / No, and `/approve`
   resumes it.
5. **Conversations** are saved to `data/checkpoints.db`, so they survive restarts and page refreshes.

### How the policy search works

The FAQ agent can only be as good as the text it is shown, so the search was built and measured step by step
on 35 customer-style questions (`evals/retrieval_cases.py`):

| Search setup | Answer in top 4 chunks | MRR |
|--------------|-----------------------:|----:|
| Search by meaning only (starting point) | 86% | 0.78 |
| + keyword search (BM25) | 86% | 0.78 |
| Bigger embedding model (bge-small) + keyword search | 86% | 0.72 |
| + a re-ranker | 89% | 0.80 |
| **+ section labels on every chunk, with the re-ranker (used)** | **94%** | **0.83** |

Keyword search and a bigger embedding model did not help on this corpus, so they are not in the code. What
did: a cross-encoder that re-reads the top 12 candidates and keeps the 4 that best answer the question, and a
label on every chunk with its document and section title (a table row alone does not say what it belongs to).
MRR is the average of 1 / (position of the first correct chunk), so 1.0 would mean it is always first.

## Quick start (Windows, PowerShell)

You need [uv](https://docs.astral.sh/uv/) (it installs Python 3.11 for you) and a free
[Groq API key](https://console.groq.com).

```powershell
uv sync                         # install everything into .venv
copy .env.example .env          # then open .env and paste your GROQ_API_KEY
uv run bankingsupportagent      # start the app
```

Open http://localhost:8000 and log in with a demo customer:

| Customer | Password |
|----------|----------|
| `C1001` (Rahul Sharma) | `rahul-demo-123` |
| `C1002` (Priya Iyer)   | `priya-demo-123` |

The first start creates what a fresh machine is missing (login keys, demo database, policy index) and
downloads two small models, so it takes a minute or two. Later starts take seconds.
Interactive API docs are at http://localhost:8000/docs.

Things to try: *"What is the minimum balance for a savings account?"*, *"Show my last 3 transactions"*,
*"My card ending 4821 was stolen, block it now"*, *"Someone hacked my account"*.

## Configuration

Settings live in `.env` (see [.env.example](.env.example)).

| Variable | Default | Meaning |
|----------|---------|---------|
| `GROQ_API_KEY` | required | your Groq key |
| `GROQ_MODEL` | `groq:openai/gpt-oss-20b` | `groq:` + a Groq model with tool calling and structured output, e.g. `groq:openai/gpt-oss-120b` |
| `GROQ_REASONING_EFFORT` | `low` | gpt-oss only. `low` is fastest and uses the fewest tokens; empty = model default |

Abuse limits (login attempts, messages per minute) are constants in
[config.py](src/bankingsupportagent/config.py).

## API

| Endpoint | What it does |
|----------|--------------|
| `POST /login` | `customer_id` + `password` returns a bearer token (30 min). Locks for 15 min after 5 wrong passwords. |
| `POST /chat` | `thread_id` + `message` returns `{status, reply, route}` |
| `POST /chat/stream` | the same, as server-sent events: many `token` events, then one `done` (the final result) or `error` |
| `POST /approve` | `thread_id` + `approved` answers a pending Yes / No confirmation |
| `GET /history?thread_id=` | the saved conversation and any pending confirmation |
| `GET /tickets` | the logged-in customer's support tickets |
| `GET /health` | server and database check |

`status` is `ok` or `needs_confirmation`. Chat is limited to 20 messages per minute per customer (HTTP 429).

## Security

| Risk | What the project does |
|------|-----------------------|
| Sensitive data reaching the AI or storage | Card and account numbers, PAN, OTP, PIN, CVV and passwords are masked first |
| One customer reading another's data | The customer ID comes from the signed token only; tools filter on it; threads are namespaced per customer |
| Password guessing | bcrypt hashes, lockout per customer and client address, RS256-signed tokens that expire |
| Flooding and cost | 20 messages per minute per customer |
| Prompt injection and prompt leaks | Each agent only has the tools and data of the logged-in customer, so a "jailbreak" has nothing extra to reach. Checked by the `security_*` evals: injection, fake "system" messages, prompt-leak requests, cross-customer access |
| Browser attacks | CSP, `X-Frame-Options`, `nosniff` on every response; replies are escaped before display |
| Leaking through logs | Requests are logged with status and timing, never with message text |

## Tests and evals

```powershell
uv run pytest                                  # 70+ unit and API tests; no API key or model download needed
uv run python -m evals.run_retrieval_eval      # does the policy search find the right chunk? (no API key)
uv run python -m evals.run_router_eval         # routing accuracy (calls Groq)
uv run python -m evals.run_e2e_eval            # whole conversations through the full graph (calls Groq)
```

| Eval | Result |
|------|--------|
| Policy search, 35 questions | 94% have the answer in the top 4 chunks (MRR 0.83) |
| Routing, 31 messages | 31/31 |
| End to end, 28 conversations: FAQ 10, account 3, card 4, escalation 2, security 9 | 28/28 |

Results are saved in `evals/results/`. Unit tests use fakes for the LLM and the search, so they run in about
40 seconds with no network. A GitHub Actions workflow that runs them on every push is included
(`.github/workflows/ci.yml`).

## Docker

```powershell
copy .env.example .env          # add your key
docker compose up --build
```

`data/` and `keys/` are mounted from the host and filled on the first start. The two small AI models are
downloaded while the image is built (about 3 GB in total), so the first start takes well under a minute and
does not need Hugging Face. Tested on a fresh machine setup: login, chat, streaming, card confirmation and
restart persistence all work inside the container.

## Project layout

```
src/bankingsupportagent/
  api.py            FastAPI app: endpoints, streaming, rate limits, logging
  graph.py          LangGraph wiring
  agents/           router, faq, account, cards, escalation
  tools/            what the agents can call (balance, transactions, cards, policy search)
  guardrails.py     masking of sensitive text, cleanup of replies
  rag/              ingest.py (PDFs to labelled chunks), retriever.py (search + re-rank)
  auth.py           bcrypt and JWT            ratelimit.py   in-memory rate limiter
  bootstrap.py      first-start setup         db/seed.py     mock bank data
  llm_errors.py     tells a model refusal from an outage
  static/           the chat page
data/docs/          the six policy PDFs used for RAG
evals/              retrieval, router and end-to-end evals
tests/              pytest suite
notebooks/          step-by-step notes on how each part was built
```

## Updating dependencies

`pyproject.toml` and `uv.lock` are the source of truth. `requirements.txt` (used by Docker and CI) is generated
from them without PyTorch, which the Dockerfile installs separately as a CPU-only build:

```powershell
uv lock
uv export --no-dev --no-hashes --no-emit-project -o requirements.txt `
  --no-emit-package torch --no-emit-package triton --no-emit-package cuda-bindings `
  --no-emit-package cuda-pathfinder --no-emit-package cuda-toolkit   # plus one --no-emit-package per nvidia-* line
```

## Known limitations and next steps

- **Free-tier LLM limits.** On Groq's free tier `gpt-oss-20b` allows about 8,000 tokens per minute and 200,000
  per day. Normal chatting is fine, but running all the evals several times in one day can use up the daily
  budget; the app then answers "temporarily unavailable" (HTTP 503) until it resets. Switching `GROQ_MODEL` to
  `groq:openai/gpt-oss-120b` uses a separate budget.
- **Rate limits and lockouts are kept in memory**: they reset on restart and are per process. Several server
  processes would need a shared store such as Redis.
- **Mock data and fixed demo passwords** in SQLite: fine for a demo, not for real customers.
- **No screen for the specialists** who would work on the tickets. Customers can list their tickets, nothing more.
- **Next steps:** a fallback model for when one is rate-limited, a specialist dashboard, and a Redis-backed
  rate limiter.

---

<div align="center">

Built by **Lokesh**

</div>
