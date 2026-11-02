import re
from functools import lru_cache

from langchain_chroma import Chroma
from langchain_core.documents import Document
from rank_bm25 import BM25Okapi

from bankingsupportagent.config import CHROMA_DIR, COLLECTION_NAME, get_embeddings

TOP_K = 4           # How many chunks to return per question
CANDIDATES = 15     # How many chunks each search (meaning, keywords) contributes before merging
RRF_K = 60          # Standard constant for Reciprocal Rank Fusion

@lru_cache
def get_vector_store():
    """Open the chroma db once and reuse it later"""
    return Chroma(
        collection_name = COLLECTION_NAME,
        embedding_function=get_embeddings(),
        persist_directory=str(CHROMA_DIR),
    )


def tokenize(text: str) -> list[str]:
    return re.findall(r"\w+", text.lower())


@lru_cache
def get_keyword_index():
    """Build the keyword (BM25) index once from the chunks stored in Chroma."""
    stored = get_vector_store().get()
    docs = [Document(page_content=text, metadata=meta) for text, meta in zip(stored["documents"], stored["metadatas"])]
    return BM25Okapi([tokenize(d.page_content) for d in docs]), docs


def keyword_search(query: str, k: int) -> list[Document]:
    bm25, docs = get_keyword_index()
    scores = bm25.get_scores(tokenize(query))
    best = sorted(range(len(docs)), key=lambda i: scores[i], reverse=True)[:k]
    return [docs[i] for i in best if scores[i] > 0]


def chunk_id(doc: Document) -> tuple:
    return (doc.metadata["source"], doc.metadata["page"], doc.page_content)


def retrieve(query: str, k: int = TOP_K):
    """Return the K best chunks, combining search by meaning (Chroma) with search by exact words (BM25).

    Meaning search misses chunks that use different wording than the question, keyword search misses
    paraphrases. Reciprocal Rank Fusion rewards chunks that either search ranks highly.
    """
    by_meaning = get_vector_store().similarity_search(query, k=CANDIDATES)
    by_keywords = keyword_search(query, CANDIDATES)

    scores, chosen = {}, {}
    for ranking in (by_meaning, by_keywords):
        for rank, doc in enumerate(ranking, start=1):
            key = chunk_id(doc)
            chosen[key] = doc
            scores[key] = scores.get(key, 0) + 1 / (RRF_K + rank)
    best = sorted(scores, key=scores.get, reverse=True)[:k]
    return [chosen[key] for key in best]


def format_docs(docs) -> str:
    """Join chunks into one text block, even labelled with its source and page"""
    return "\n\n".join(
        f"[Source: {d.metadata['source']}, page {d.metadata['page']}]\n{d.page_content}"
        for d in docs
    )
