from functools import lru_cache

from langchain_chroma import Chroma
from sentence_transformers import CrossEncoder

from bankingsupportagent.config import CHROMA_DIR, COLLECTION_NAME, RERANK_MODEL, get_embeddings

TOP_K = 4           # How many chunks to return per question
CANDIDATES = 12     # How many chunks the first search hands to the re-ranker


@lru_cache
def get_vector_store():
    """Open the chroma db once and reuse it later"""
    return Chroma(
        collection_name = COLLECTION_NAME,
        embedding_function=get_embeddings(),
        persist_directory=str(CHROMA_DIR),
    )


@lru_cache
def get_reranker():
    """Load the re-ranking model once and reuse it later"""
    return CrossEncoder(RERANK_MODEL)


def retrieve(query: str, k:int=TOP_K):
    """Return the K chunks that best answer the query.

    Two steps: a fast search by meaning finds CANDIDATES chunks, then a slower re-ranker reads the question
    together with each chunk and keeps the K best. The first step is good at "roughly about this topic",
    the second at "actually answers this question".
    """
    candidates = get_vector_store().similarity_search(query, k=CANDIDATES)
    scores = get_reranker().predict([(query, doc.page_content) for doc in candidates])
    best_first = sorted(zip(scores, candidates), key=lambda pair: pair[0], reverse=True)
    return [doc for _, doc in best_first[:k]]


def format_docs(docs) -> str:
    """Join chunks into one text block, even labelled with its source and page"""
    return "\n\n".join(
        f"[Source: {d.metadata['source']}, page {d.metadata['page']}]\n{d.page_content}"
        for d in docs
    )
