import sys
import json
import time
from collections import defaultdict
from pathlib import Path

from bankingsupportagent.agents.router import route_query
from evals.router_cases import ROUTER_CASES

RESULTS_DIR = Path(__file__).parent / "results"


def call_with_retry(fn, *args, retries=3):
    """Retry a few times on errors such as rate limits, waiting longer each time."""
    for attempt in range(1, retries + 1):
        try:
            return fn(*args)
        except Exception as error:
            if attempt == retries:
                raise
            wait = 10 * attempt
            print(f"   ! {type(error).__name__}: retrying in {wait}s")
            time.sleep(wait)


def main():
    use_history = "--no-history" not in sys.argv
    results = []

    for number, case in enumerate(ROUTER_CASES, start=1):
        history = case.get("history", "") if use_history else ""

        start = time.perf_counter()
        decision = call_with_retry(route_query, case["query"], history)
        seconds = time.perf_counter() - start

        correct = decision.route in case["expected"]
        results.append({
            "query": case["query"],
            "expected": case["expected"],
            "predicted": decision.route,
            "reason": decision.reason,
            "correct": correct,
            "seconds": round(seconds, 2),
        })
        mark = "OK  " if correct else "FAIL"
        print(f"{number:>2}. {mark} {decision.route:<9} | {case['query'][:70]}")

    # ---------- summary ----------
    total = len(results)
    passed = sum(r["correct"] for r in results)

    by_route = defaultdict(lambda: [0, 0])          # route -> [passed, total]
    for r in results:
        main_route = r["expected"][0]
        by_route[main_route][1] += 1
        by_route[main_route][0] += r["correct"]

    average_seconds = sum(r["seconds"] for r in results) / total

    print(f"\nHistory: {'ON' if use_history else 'OFF'}")
    print(f"Routing accuracy: {passed}/{total} = {passed / total:.0%}")
    for route, (ok, count) in sorted(by_route.items()):
        print(f"  {route:<9} {ok}/{count}")
    print(f"Average router latency: {average_seconds:.2f}s")

    failures = [r for r in results if not r["correct"]]
    if failures:
        print("\nFailures:")
        for r in failures:
            print(f"  - '{r['query']}'\n    expected {r['expected']}, got '{r['predicted']}': {r['reason']}")

    RESULTS_DIR.mkdir(exist_ok=True)
    file_name = "router_results.json" if use_history else "router_results_no_history.json"
    output = RESULTS_DIR / file_name
    output.write_text(json.dumps({
        "history": use_history,
        "accuracy": round(passed / total, 3),
        "passed": passed,
        "total": total,
        "average_seconds": round(average_seconds, 2),
        "cases": results,
    }, indent=2))
    print(f"\nSaved detailed results to {output}")


if __name__ == "__main__":
    main()