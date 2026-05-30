from __future__ import annotations

import logging
import os
from dataclasses import dataclass

import requests

logger = logging.getLogger(__name__)

DEFAULT_OPENAI_MODEL = "o4-mini"
OMODEL_SET_PREFIX = "omodel:set:"

# Статический каталог reasoning-моделей (цены USD за 1M tokens, OpenAI pricing).
# Обновлять вручную при смене тарифов; /v1/models не отдаёт pricing.
_REASONING_CATALOG: tuple[tuple[str, int, float, float], ...] = (
    ("gpt-5.5", 10, 5.0, 30.0),
    ("gpt-5.5-pro", 20, 30.0, 180.0),
    ("gpt-5.4", 30, 2.5, 15.0),
    ("gpt-5.4-mini", 40, 0.75, 4.5),
    ("o4-mini", 50, 1.1, 4.4),
    ("o3", 60, 2.0, 8.0),
    ("o3-mini", 70, 1.1, 4.4),
)

_catalog_by_id: dict[str, "OpenAIModelInfo"] = {}
_available_models: tuple["OpenAIModelInfo", ...] = ()
_last_refresh_note: str = "not loaded"


@dataclass(frozen=True)
class OpenAIModelInfo:
    model_id: str
    priority: int
    input_usd_per_1m: float
    output_usd_per_1m: float

    def price_label(self) -> str:
        def fmt(value: float) -> str:
            if value >= 10:
                return f"${value:g}"
            if value >= 1:
                return f"${value:.1f}"
            return f"${value:.2f}".rstrip("0").rstrip(".")

        return f"{fmt(self.input_usd_per_1m)}/{fmt(self.output_usd_per_1m)}"

    def button_label(self, *, selected: bool = False) -> str:
        mark = "✅ " if selected else ""
        short = self.model_id.replace("gpt-", "g").replace("-mini", "-m")
        return f"{mark}{short} {self.price_label()}"


def _build_catalog() -> dict[str, OpenAIModelInfo]:
    result: dict[str, OpenAIModelInfo] = {}
    for model_id, priority, inp, out in _REASONING_CATALOG:
        result[model_id] = OpenAIModelInfo(
            model_id=model_id,
            priority=priority,
            input_usd_per_1m=inp,
            output_usd_per_1m=out,
        )
    return result


def _catalog_entries() -> dict[str, OpenAIModelInfo]:
    global _catalog_by_id
    if not _catalog_by_id:
        _catalog_by_id = _build_catalog()
    return _catalog_by_id


def default_openai_model() -> str:
    raw = os.getenv("BOT_OPENAI_MODEL", DEFAULT_OPENAI_MODEL).strip()
    return raw or DEFAULT_OPENAI_MODEL


def _api_matches_catalog(api_id: str, catalog_id: str) -> bool:
    aid = (api_id or "").strip().lower()
    cid = catalog_id.strip().lower()
    if not aid or not cid:
        return False
    return aid == cid or aid.startswith(f"{cid}-")


def _best_catalog_match(api_id: str, catalog: dict[str, OpenAIModelInfo]) -> OpenAIModelInfo | None:
    aid = (api_id or "").strip().lower()
    if not aid:
        return None
    best: OpenAIModelInfo | None = None
    best_len = -1
    for info in catalog.values():
        cid = info.model_id.lower()
        if aid == cid or aid.startswith(f"{cid}-"):
            if len(cid) > best_len:
                best = info
                best_len = len(cid)
    return best


def _fetch_remote_model_ids() -> set[str] | None:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        return None
    api_base = os.getenv("OPENAI_API_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    headers = {"Authorization": f"Bearer {api_key}"}
    try:
        response = requests.get(
            f"{api_base}/models",
            headers=headers,
            timeout=20,
        )
    except requests.RequestException as exc:
        logger.warning("OpenAI models list failed: %s", exc)
        return None
    if not (200 <= response.status_code < 300):
        logger.warning("OpenAI models list status=%s", response.status_code)
        return None
    try:
        payload = response.json()
    except ValueError:
        logger.warning("OpenAI models list invalid json")
        return None
    ids: set[str] = set()
    for item in payload.get("data") or []:
        if isinstance(item, dict) and item.get("id"):
            ids.add(str(item["id"]).strip().lower())
    return ids


def _filter_catalog_by_remote(
    catalog: dict[str, OpenAIModelInfo],
    remote_ids: set[str] | None,
) -> list[OpenAIModelInfo]:
    if remote_ids is None:
        return sorted(catalog.values(), key=lambda m: m.priority)[:5]
    matched_by_id: dict[str, OpenAIModelInfo] = {}
    for rid in remote_ids:
        info = _best_catalog_match(rid, catalog)
        if info is not None:
            matched_by_id[info.model_id] = info
    matched = sorted(matched_by_id.values(), key=lambda m: m.priority)
    if matched:
        return matched[:5]
    default_id = default_openai_model()
    if default_id in catalog:
        return [catalog[default_id]]
    return [next(iter(catalog.values()))]


def refresh_openai_models_catalog() -> tuple["OpenAIModelInfo", ...]:
    global _available_models, _last_refresh_note
    catalog = _catalog_entries()
    remote_ids = _fetch_remote_model_ids()
    models = _filter_catalog_by_remote(catalog, remote_ids)
    _available_models = tuple(models)
    if remote_ids is None:
        _last_refresh_note = "static catalog (no OPENAI_API_KEY or API error)"
    else:
        _last_refresh_note = f"API ok, {len(remote_ids)} models, showing {len(models)}"
    logger.info(
        "OpenAI Q&A models: %s (%s)",
        ", ".join(m.model_id for m in models),
        _last_refresh_note,
    )
    return _available_models


def get_available_openai_models() -> tuple[OpenAIModelInfo, ...]:
    if not _available_models:
        return refresh_openai_models_catalog()
    return _available_models


def get_openai_models_refresh_note() -> str:
    return _last_refresh_note


def is_allowed_openai_model(model_id: str) -> bool:
    mid = (model_id or "").strip().lower()
    if not mid:
        return False
    return any(m.model_id == mid for m in get_available_openai_models())


def openai_model_supports_temperature(model_id: str) -> bool:
    mid = (model_id or "").strip().lower()
    if not mid:
        return True
    if mid.startswith("o") and mid[1:2] in {"", "-", "1", "3", "4"}:
        return False
    if mid.startswith("gpt-5"):
        return False
    return True


def resolve_openai_model(override: str | None = None) -> str:
    candidate = (override or "").strip().lower()
    if candidate and is_allowed_openai_model(candidate):
        return candidate
    default = default_openai_model()
    if is_allowed_openai_model(default):
        return default
    available = get_available_openai_models()
    if available:
        return available[0].model_id
    return DEFAULT_OPENAI_MODEL
