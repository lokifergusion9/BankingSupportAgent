import json
import time
import uuid
from collections import defaultdict
from pathlib import Path

from pydantic import BaseModel,Field
from langchain.messages import SystemMessage,HumanMessage
from langgraph.types import Command

from bankingsupportagent.config import get_llm
from bankingsupportagent.db.seed import seed
from bankingsupportagent.graph import build_graph
from bankingsupportagent.tools.card_tools import fetch_card_status
from evals.e2e_cases import E2E_CASES


RESULTS_DIR = Path(__file__).parent / "results"
PAUSE_BETWEEN_CASES = 2      # seconds, to stay under the API rate limit
MAX_ATTEMPTS = 3


# ---------- LLM judge (only for requirements that code cannot check) ----------

class Verdict(BaseModel):
    passed: bool = Field(description="True only if the reply fully meets the requirement")
    reason: str = Field(description="One sentence explaining the decision")


JUDGE_PROMPT = """You are a strict quality reviewer for a bank's customer support assistant.
You will get a requirement and the assistant's reply. Decide whether the reply meets the
requirement. Judge only the requirement, not style. If in doubt, fail it."""


def judge(reply: str, requirement: str) -> Verdict:
    llm = get_llm().with_structured_output(Verdict)
    return llm.invoke([
        SystemMessage(JUDGE_PROMPT),
        HumanMessage(f"Requirement: {requirement}\n\nAssistant reply:\n{reply}"),
    ])



# ---------- Running one conversation ----------

def run_conversation(graph, case):
    """Send every turn of the case through the graph. Answer confirmation pauses automatically."""
    config = {"configurable": {"thread_id": f"eval-{case['id']}-{uuid.uuid4().hex[:6]}"}}
    interrupts = 0
    result = None

    for number, message in enumerate(case["turns"]):
        inputs = {"messages": message}
        if number == 0 and case.get("customer_id"):
            inputs["customer_id"] = case["customer_id"]
        result = graph.invoke(inputs, config=config)

        while "__interrupt__" in result:
            interrupts += 1
            if interrupts > 3:
                raise RuntimeError("Too many confirmation pauses")
            approved = case.get("approve", False)
            result = graph.invoke(Command(resume={"approved": approved}), config=config)

    stored = graph.get_state(config).values["messages"]
    return result, interrupts, stored


def check(case, result, interrupts, stored):
    """Return a list of failed checks (an empty list means the case passed)."""
    failures = []
    reply = result["messages"][-1].content
    reply_lower = reply.lower()

    expected_route = case.get("expected_route")
    if expected_route and result.get("route") != expected_route:
        failures.append(f"route was '{result.get('route')}', expected '{expected_route}'")

    for text in case.get("must_contain", []):
        if text.lower() not in reply_lower:
            failures.append(f"reply is missing '{text}'")

    options = case.get("must_contain_any")
    if options and not any(text.lower() in reply_lower for text in options):
        failures.append(f"reply contains none of {options}")

    for text in case.get("must_not_contain", []):
        if text.lower() in reply_lower:
            failures.append(f"reply must not contain '{text}'")

    if "card_status" in case:
        customer_id, last4, expected_status = case["card_status"]
        actual = fetch_card_status(customer_id, last4)
        if actual != expected_status:
            failures.append(f"card {last4} is '{actual}', expected '{expected_status}'")

    if "max_interrupts" in case and interrupts > case["max_interrupts"]:
        failures.append(f"{interrupts} confirmation pauses, allowed {case['max_interrupts']}")

    secret = case.get("not_stored")
    if secret and any(secret in str(m.content) for m in stored):
        failures.append("sensitive text was stored in the conversation")

    if case.get("judge"):
        verdict = judge(reply, case["judge"])
        if not verdict.passed:
            failures.append(f"judge: {verdict.reason}")

    return failures, reply


def run_case(graph, case):
    """Run one case on a fresh database, retrying the whole case if the API errors."""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            seed()
            start = time.perf_counter()
            result, interrupts, stored = run_conversation(graph, case)
            seconds = time.perf_counter() - start
            failures, reply = check(case, result, interrupts, stored)
            return failures, reply, seconds
        except Exception as error:
            if attempt == MAX_ATTEMPTS:
                return [f"error: {type(error).__name__}: {error}"], "", 0.0
            wait = 15 * attempt
            print(f"   ! {type(error).__name__}: retrying case in {wait}s")
            time.sleep(wait)


# ---------- Main ----------

def main():
    graph = build_graph()
    results = []

    for number, case in enumerate(E2E_CASES, start=1):
        failures, reply, seconds = run_case(graph, case)
        passed = not failures
        results.append({
            "id": case["id"],
            "category": case["category"],
            "passed": passed,
            "failures": failures,
            "reply": reply,
            "seconds": round(seconds, 2),
        })
        mark = "PASS" if passed else "FAIL"
        print(f"{number:>2}. {mark} [{case['category']:<10}] {case['id']:<26} {seconds:5.1f}s")
        for failure in failures:
            print(f"      - {failure}")
        time.sleep(PAUSE_BETWEEN_CASES)

    seed()   # leave the database clean for normal use

    # ---------- summary ----------
    total = len(results)
    passed_count = sum(r["passed"] for r in results)

    by_category = defaultdict(lambda: [0, 0])
    for r in results:
        by_category[r["category"]][1] += 1
        by_category[r["category"]][0] += r["passed"]

    timed = [r["seconds"] for r in results if r["seconds"] > 0]
    average = sum(timed) / len(timed) if timed else 0.0

    print(f"\nEnd-to-end: {passed_count}/{total} cases passed ({passed_count / total:.0%})")
    for category, (ok, count) in sorted(by_category.items()):
        print(f"  {category:<10} {ok}/{count}")
    print(f"Average time per conversation: {average:.1f}s")

    RESULTS_DIR.mkdir(exist_ok=True)
    output = RESULTS_DIR / "e2e_results.json"
    output.write_text(json.dumps({
        "passed": passed_count,
        "total": total,
        "pass_rate": round(passed_count / total, 3),
        "average_seconds": round(average, 2),
        "by_category": {c: {"passed": v[0], "total": v[1]} for c, v in by_category.items()},
        "cases": results,
    }, indent=2))
    print(f"\nSaved detailed results to {output}")


if __name__ == "__main__":
    main()