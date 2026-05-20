from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlparse

import requests

_ALLOWED_PROVIDERS = frozenset({"tavily", "ddgs"})
_DEFAULT_PROVIDER = "tavily"
_TAVILY_API_URL = "https://api.tavily.com/search"


@dataclass(frozen=True)
class WebSearchResult:
    title: str
    url: str
    snippet: str
    query: str = ""


class WebSearchProvider(Protocol):
    def search_one(self, query: str, max_results: int) -> tuple[bool, list[WebSearchResult], str]:
        ...


def is_web_search_enabled() -> bool:
    return os.getenv("BOT_ENABLE_WEB_SEARCH", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def web_search_provider_name() -> str:
    raw = os.getenv("BOT_WEB_SEARCH_PROVIDER", _DEFAULT_PROVIDER).strip().lower()
    return raw if raw in _ALLOWED_PROVIDERS else _DEFAULT_PROVIDER


def _max_queries() -> int:
    try:
        value = int(os.getenv("BOT_WEB_SEARCH_MAX_QUERIES", "3"))
    except ValueError:
        value = 3
    return max(1, min(value, 5))


def _max_results_per_query() -> int:
    try:
        value = int(os.getenv("BOT_WEB_SEARCH_MAX_RESULTS", "5"))
    except ValueError:
        value = 5
    return max(1, min(value, 10))


def _total_results_cap() -> int:
    try:
        value = int(os.getenv("BOT_WEB_SEARCH_MAX_TOTAL_RESULTS", "8"))
    except ValueError:
        value = 8
    return max(1, min(value, 20))


def _http_timeout_seconds() -> int:
    try:
        value = int(os.getenv("BOT_WEB_SEARCH_TIMEOUT_SECONDS", "25"))
    except ValueError:
        value = 25
    return max(5, min(value, 120))


def _normalize_url(url: str) -> str:
    parsed = urlparse((url or "").strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    path = parsed.path.rstrip("/") or ""
    return f"{parsed.scheme}://{parsed.netloc.lower()}{path}"


def _clip(text: str, limit: int = 1200) -> str:
    value = (text or "").strip()
    if len(value) <= limit:
        return value
    return value[: limit - 3].rstrip() + "..."


def merge_results(
    batches: list[list[WebSearchResult]],
    *,
    max_total: int,
) -> list[WebSearchResult]:
    merged: list[WebSearchResult] = []
    seen: set[str] = set()
    for batch in batches:
        for item in batch:
            key = _normalize_url(item.url)
            if not key or key in seen:
                continue
            seen.add(key)
            merged.append(item)
            if len(merged) >= max_total:
                return merged
    return merged


class TavilyWebSearchProvider:
    def __init__(self, api_key: str, timeout_seconds: int) -> None:
        self._api_key = api_key.strip()
        self._timeout_seconds = timeout_seconds

    def search_one(self, query: str, max_results: int) -> tuple[bool, list[WebSearchResult], str]:
        q = (query or "").strip()
        if not q:
            return False, [], "empty query"
        if not self._api_key:
            return False, [], "tavily api key is missing"

        payload = {
            "api_key": self._api_key,
            "query": q,
            "max_results": max_results,
            "search_depth": os.getenv("BOT_TAVILY_SEARCH_DEPTH", "basic").strip() or "basic",
            "include_answer": False,
            "include_raw_content": False,
        }
        try:
            response = requests.post(
                _TAVILY_API_URL,
                json=payload,
                timeout=self._timeout_seconds,
            )
        except requests.RequestException as exc:
            return False, [], f"tavily error={exc}"

        if not (200 <= response.status_code < 300):
            return False, [], f"tavily status={response.status_code}"

        try:
            body = response.json()
        except ValueError:
            return False, [], "tavily invalid json"

        rows = body.get("results") or []
        results: list[WebSearchResult] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            url = str(row.get("url") or "").strip()
            if not _normalize_url(url):
                continue
            title = _clip(str(row.get("title") or url), 300)
            snippet = _clip(str(row.get("content") or row.get("snippet") or ""), 1200)
            results.append(WebSearchResult(title=title, url=url, snippet=snippet, query=q))
            if len(results) >= max_results:
                break
        return True, results, ""


class DdgsWebSearchProvider:
    def __init__(self, timeout_seconds: int) -> None:
        self._timeout_seconds = timeout_seconds

    def search_one(self, query: str, max_results: int) -> tuple[bool, list[WebSearchResult], str]:
        q = (query or "").strip()
        if not q:
            return False, [], "empty query"
        try:
            from ddgs import DDGS
            from ddgs.exceptions import DDGSException
        except ImportError:
            return False, [], "ddgs package is not installed"

        try:
            with DDGS(timeout=self._timeout_seconds) as client:
                rows = list(client.text(q, max_results=max_results))
        except DDGSException as exc:
            return False, [], f"ddgs error={exc}"
        except Exception as exc:
            return False, [], f"ddgs error={exc}"

        results: list[WebSearchResult] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            url = str(row.get("href") or row.get("url") or "").strip()
            if not _normalize_url(url):
                continue
            title = _clip(str(row.get("title") or url), 300)
            snippet = _clip(str(row.get("body") or row.get("snippet") or ""), 1200)
            results.append(WebSearchResult(title=title, url=url, snippet=snippet, query=q))
        return True, results, ""


def build_web_search_provider(
    provider_name: str | None = None,
) -> tuple[WebSearchProvider | None, str]:
    name = (provider_name or web_search_provider_name()).strip().lower()
    timeout = _http_timeout_seconds()
    if name == "ddgs":
        return DdgsWebSearchProvider(timeout), ""
    if name == "tavily":
        api_key = os.getenv("TAVILY_API_KEY", "").strip()
        if not api_key:
            return None, "tavily api key is missing"
        return TavilyWebSearchProvider(api_key, timeout), ""
    return None, f"unsupported web search provider: {name}"


def search_web(
    queries: list[str],
    *,
    provider: WebSearchProvider | None = None,
    provider_name: str | None = None,
) -> tuple[bool, list[WebSearchResult], str]:
    if not is_web_search_enabled():
        return False, [], "web search disabled"

    cleaned = []
    seen_q: set[str] = set()
    for raw in queries:
        q = (raw or "").strip()
        if not q:
            continue
        key = q.lower()
        if key in seen_q:
            continue
        seen_q.add(key)
        cleaned.append(q)
        if len(cleaned) >= _max_queries():
            break

    if not cleaned:
        return False, [], "no search queries"

    active_provider = provider
    if active_provider is None:
        active_provider, provider_error = build_web_search_provider(provider_name)
        if active_provider is None:
            return False, [], provider_error

    per_query = _max_results_per_query()
    max_total = _total_results_cap()
    batches: list[list[WebSearchResult]] = []
    errors: list[str] = []

    for q in cleaned:
        ok, rows, err = active_provider.search_one(q, per_query)
        if ok and rows:
            batches.append(rows)
        elif err:
            errors.append(f"{q}: {err}")

    merged = merge_results(batches, max_total=max_total)
    if merged:
        return True, merged, ""

    if errors:
        return False, [], "; ".join(errors)
    return False, [], "web search returned no results"
