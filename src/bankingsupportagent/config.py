import os
from dotenv import load_dotenv
from langchain.chat_models import init_chat_model
from pathlib import Path
from langchain_huggingface import HuggingFaceEmbeddings


load_dotenv()

MODEL_NAME = os.getenv("GROQ_MODEL","groq:openai")
LLM_TIMEOUT_SECONDS = 15        # Give up on groq after this long
LLM_MAX_RETRIES = 1             # retry once on timeout, 429 and 5xx errors

def get_llm(temperature: float = 0):
    """Return the chat model used by every agent in the project"""
    if not os.getenv("GROQ_API_KEY"):
        raise ValueError("GROQ_API_KEY not found. Add it to your .env file...")
    return init_chat_model(MODEL_NAME,temperature=temperature,timeout=LLM_TIMEOUT_SECONDS,max_retries=LLM_MAX_RETRIES,)


# RAG
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DOCS_DIR = PROJECT_ROOT/"data"/"docs"
CHROMA_DIR = PROJECT_ROOT/"data"/"chroma_db"
COLLECTION_NAME = "bank_docs"
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
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