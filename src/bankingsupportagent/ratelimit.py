import math
import time
from collections import defaultdict, deque
from threading import Lock


class RateLimiter:
    """Allow at most `limit` recorded events per `window` seconds for each key.

    Kept in memory, so it works for one server process. With several processes use a shared store (Redis).
    """

    def __init__(self, limit: int, window: float):
        self.limit = limit
        self.window = window
        self._events = defaultdict(deque)
        self._lock = Lock()

    def _recent(self, key) -> deque:
        events = self._events[key]
        cutoff = time.monotonic() - self.window
        while events and events[0] <= cutoff:
            events.popleft()
        return events

    def retry_after(self, key) -> int:
        """0 if `key` may go ahead, otherwise how many seconds it must wait."""
        with self._lock:
            events = self._recent(key)
            if len(events) < self.limit:
                return 0
            return math.ceil(events[0] + self.window - time.monotonic())

    def record(self, key) -> None:
        with self._lock:
            self._recent(key).append(time.monotonic())

    def reset(self, key=None) -> None:
        """Forget one key, or everything when no key is given."""
        with self._lock:
            if key is None:
                self._events.clear()
            else:
                self._events.pop(key, None)
