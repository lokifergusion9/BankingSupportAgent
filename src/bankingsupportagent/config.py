import os
from dotenv import load_dotenv
from langchain.chat_models import init_chat_model
from pathlib import Path
from langchain_huggingface import HuggingFaceEmbeddings


load_dotenv()

MODEL_NAME = os.getenv("GROQ_MODEL","groq:openai/gpt-oss-20b")
LLM_TIMEOUT_SECONDS = 30        # Give up on one groq attempt after this long
LLM_MAX_RETRIES = 3             # retry on timeout, 429 and 5xx errors (waits longer each time)
# gpt-oss models think before answering. "low" cuts tokens and time a lot, which matters on the free
# tier's tokens-per-minute limit. Set GROQ_REASONING_EFFORT to medium/high, or empty to turn it off.
REASONING_EFFORT = os.getenv("GROQ_REASONING_EFFORT", "low")

def get_llm(temperature: float = 0):
    """Return the chat model used by every agent in the project"""
    if not os.getenv("GROQ_API_KEY"):
        raise ValueError("GROQ_API_KEY not found. Add it to your .env file...")
    extra = {"reasoning_effort": REASONING_EFFORT} if REASONING_EFFORT and "gpt-oss" in MODEL_NAME else {}
    return init_chat_model(MODEL_NAME,temperature=temperature,timeout=LLM_TIMEOUT_SECONDS,max_retries=LLM_MAX_RETRIES,**extra)


# RAG
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DOCS_DIR = PROJECT_ROOT/"data"/"docs"
CHROMA_DIR = PROJECT_ROOT/"data"/"chroma_db"
COLLECTION_NAME = "bank_docs"
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
RERANK_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"      # re-orders the search results by how well they answer
DB_PATH = PROJECT_ROOT/"data"/"bank.db"
CHECKPOINT_DB_PATH = PROJECT_ROOT/"data"/"checkpoints.db"     # saved conversations, survives restarts

def get_embeddings():
    """Return the embedding model used for both indexing and searching"""
    return HuggingFaceEmbeddings(model_name = EMBEDDING_MODEL)


# Login credentials (JWT, RS256)
KEYS_DIR = PROJECT_ROOT / "keys"
JWT_PRIVATE_KEY_PATH = KEYS_DIR / "private.pem"
JWT_PUBLIC_KEY_PATH = KEYS_DIR / "public.pem"
JWT_ALGORITHM = "RS256"
ACCESS_TOKEN_MINUTES = 30

# Abuse limits (per server process)
LOGIN_MAX_FAILURES = 5              # wrong passwords allowed per customer ID and client address...
LOGIN_WINDOW_SECONDS = 15 * 60      # ...within this time, then login is locked until it passes
CHAT_MAX_PER_MINUTE = 20            # messages per customer, also protects the LLM's tokens-per-minute limit