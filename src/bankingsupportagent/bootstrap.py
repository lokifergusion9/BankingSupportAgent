import logging

from bankingsupportagent.config import CHROMA_DIR, DB_PATH, JWT_PRIVATE_KEY_PATH, JWT_PUBLIC_KEY_PATH

logger = logging.getLogger("securebank.bootstrap")


def ensure_ready() -> list[str]:
    """Create whatever a fresh machine is missing: login keys, demo database, policy index.

    Existing files are never touched, so this is safe to call on every start.
    Returns what it created.
    """
    created = []

    if not (JWT_PRIVATE_KEY_PATH.exists() and JWT_PUBLIC_KEY_PATH.exists()):
        from bankingsupportagent.keys import generate_keys
        generate_keys()
        created.append("login keys")

    if not DB_PATH.exists():
        from bankingsupportagent.db.seed import seed
        seed()
        created.append("demo database")

    if not (CHROMA_DIR.exists() and any(CHROMA_DIR.iterdir())):
        from bankingsupportagent.rag.ingest import build_vector_store
        build_vector_store()
        created.append("policy index")

    for item in created:
        logger.info("First start: created %s", item)
    return created
