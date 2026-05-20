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


_METRIC_LABELS_RU: dict[str, str] = {
    "qa_total": "вопросов получено",
    "qa_success_total": "ответов успешно",
    "qa_failed_total": "ошибок Q&A",
    "qa_web_judge_total": "проверок «нужен веб»",
    "qa_web_search_triggered_total": "запусков веб-поиска",
    "qa_web_synthesis_success_total": "синтезов с вебом",
    "ingest_text_total": "ingest текста (всего)",
    "ingest_text_success_total": "ingest текста (успех)",
    "ingest_text_failed_total": "ingest текста (ошибка)",
    "ingest_file_total": "ingest файлов (всего)",
    "ingest_file_success_total": "ingest файлов (успех)",
    "ingest_file_failed_total": "ingest файлов (ошибка)",
    "track_success_total": "треков ingest (успех)",
    "track_failed_total": "треков ingest (ошибка)",
    "track_timeout_total": "треков ingest (таймаут)",
    "rate_limited_total": "срабатываний rate-limit",
    "unhandled_errors_total": "необработанных ошибок",
}


def format_metrics(snapshot: dict[str, int]) -> str:
    return format_metrics_ru(snapshot)


def format_metrics_ru(snapshot: dict[str, int]) -> str:
    lines: list[str] = []
    for key in _METRIC_LABELS_RU:
        value = int(snapshot.get(key, 0))
        lines.append(f"• {_METRIC_LABELS_RU[key]}: {value}")
    extra_keys = sorted(k for k in snapshot if k not in _METRIC_LABELS_RU)
    for key in extra_keys:
        lines.append(f"• {key}: {snapshot[key]}")
    if not lines:
        return "• (пока нет событий — задай вопрос или добавь в БЗ)"
    return "\n".join(lines)

