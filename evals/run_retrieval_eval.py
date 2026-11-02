"""Measure how well the policy search finds the right chunk. No LLM and no API key needed.

hit@K : share of questions whose answer appears in the top K chunks (K = what the FAQ agent actually sees)
MRR   : mean of 1/rank of the first correct chunk (1.0 = always first), looking at the top 10
"""
import json
from pathlib import Path

from bankingsupportagent.rag.retriever import TOP_K, retrieve
from evals.retrieval_cases import RETRIEVAL_CASES

RESULTS_DIR = Path(__file__).parent / "results"
LOOK_AT = 10


def squash(text: str) -> str:
    return " ".join(text.split())


def first_correct_rank(chunks, needle: str):
    for rank, chunk in enumerate(chunks, start=1):
        if squash(needle) in squash(chunk.page_content):
            return rank
    return None


def evaluate(search=retrieve, top_k=TOP_K, cases=RETRIEVAL_CASES):
    rows = []
    for case_id, question, needle in cases:
        rank = first_correct_rank(search(question, LOOK_AT), needle)
        rows.append({"id": case_id, "question": question, "rank": rank})
    hits = sum(1 for r in rows if r["rank"] and r["rank"] <= top_k)
    mrr = sum(1 / r["rank"] for r in rows if r["rank"]) / len(rows)
    return {"hit_at_k": hits / len(rows), "top_k": top_k, "mrr": round(mrr, 3), "total": len(rows), "cases": rows}


def main():
    report = evaluate()
    for row in report["cases"]:
        mark = "ok  " if row["rank"] and row["rank"] <= report["top_k"] else "MISS"
        print(f"{mark} rank={str(row['rank']):<4} {row['id']:<20} {row['question']}")
    print(f"\nhit@{report['top_k']}: {report['hit_at_k']:.0%} ({round(report['hit_at_k'] * report['total'])}/{report['total']})   MRR: {report['mrr']}")

    RESULTS_DIR.mkdir(exist_ok=True)
    (RESULTS_DIR / "retrieval_results.json").write_text(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
