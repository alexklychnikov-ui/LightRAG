import time
from collections import defaultdict, deque
from dataclasses import dataclass


@dataclass
class RateLimitDecision:
    allowed: bool
    retry_after_seconds: int


class InMemoryRateLimiter:
    def __init__(self, max_events: int, window_seconds: int) -> None:
        self.max_events = max(1, int(max_events))
        self.window_seconds = max(1, int(window_seconds))
        self._events: dict[int, deque[float]] = defaultdict(deque)

    def check(self, key: int) -> RateLimitDecision:
        now = time.time()
        queue = self._events[key]
        cutoff = now - self.window_seconds
        while queue and queue[0] < cutoff:
            queue.popleft()
        if len(queue) >= self.max_events:
            retry_after = max(1, int(self.window_seconds - (now - queue[0])))
            return RateLimitDecision(allowed=False, retry_after_seconds=retry_after)
        queue.append(now)
        return RateLimitDecision(allowed=True, retry_after_seconds=0)


class BotRuntimeMetrics:
    def __init__(self) -> None:
        self._counters: dict[str, int] = defaultdict(int)

    def inc(self, key: str, value: int = 1) -> None:
        self._counters[key] += int(value)

    def snapshot(self) -> dict[str, int]:
        return dict(self._counters)


def format_metrics(snapshot: dict[str, int]) -> str:
    if not snapshot:
        return "нет данных"
    keys = sorted(snapshot.keys())
    return ", ".join(f"{key}={snapshot[key]}" for key in keys)

