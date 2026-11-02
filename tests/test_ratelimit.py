from bankingsupportagent import ratelimit
from bankingsupportagent.ratelimit import RateLimiter


def test_allows_up_to_the_limit_then_blocks(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(ratelimit.time, "monotonic", lambda: now[0])
    limiter = RateLimiter(limit=2, window=60)

    assert limiter.retry_after("a") == 0
    limiter.record("a")
    limiter.record("a")

    assert limiter.retry_after("a") > 0
    assert limiter.retry_after("b") == 0        # other keys are independent


def test_allows_again_after_the_window(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(ratelimit.time, "monotonic", lambda: now[0])
    limiter = RateLimiter(limit=1, window=60)
    limiter.record("a")
    assert limiter.retry_after("a") == 60

    now[0] += 61

    assert limiter.retry_after("a") == 0


def test_reset(monkeypatch):
    limiter = RateLimiter(limit=1, window=60)
    limiter.record("a")
    limiter.record("b")

    limiter.reset("a")
    assert limiter.retry_after("a") == 0
    assert limiter.retry_after("b") > 0

    limiter.reset()
    assert limiter.retry_after("b") == 0
