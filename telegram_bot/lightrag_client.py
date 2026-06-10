import json
import os
import re
import time

import requests

from .openai_models import openai_model_supports_temperature, resolve_openai_model
from .translation import TECHNICAL_TRANSLATION_RULES_RU, split_text_for_translation


class LightRAGClient:
    @staticmethod
    def _default_timeout_seconds() -> int:
        try:
            value = int(os.getenv("BOT_LIGHTRAG_TIMEOUT_SECONDS", "20"))
        except ValueError:
            value = 20
        return max(10, min(value, 180))

    def __init__(
        self,
        base_url: str,
        api_key: str | None = None,
        timeout_seconds: int | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = (api_key or "").strip() or None
        self.timeout_seconds = (
            timeout_seconds
            if timeout_seconds is not None
            else self._default_timeout_seconds()
        )
        self.retry_attempts = max(0, int(os.getenv("BOT_HTTP_RETRY_ATTEMPTS", "2")))
        self.retry_backoff_seconds = float(os.getenv("BOT_HTTP_RETRY_BACKOFF", "0.7"))

    def _headers(self) -> dict[str, str]:
        if not self.api_key:
            return {}
        return {"X-API-Key": self.api_key}

    @staticmethod
    def _to_int(value) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def is_weak_answer(answer: str) -> bool:
        text = (answer or "").lower().strip()
        if not text:
            return True
        weak_markers = (
            "недостаточно информации",
            "нет достаточной информации",
            "не могу ответить",
            "не могу предоставить",
            "не могу дать ответ",
            "не располагаю информацией",
            "not enough information",
            "insufficient information",
            "i don't have enough information",
            "cannot provide an answer",
            "can't provide an answer",
            "unable to answer",
            "unable to provide",
            "sorry, i cannot",
            "sorry, i can't",
        )
        if any(marker in text for marker in weak_markers):
            return True
        if len(text) < 280 and re.search(
            r"^(извините|sorry)[,.]?\s+(я\s+)?(не\s+могу|cannot|can't)",
            text,
        ):
            return True
        return False

    _is_weak_answer = is_weak_answer

    @staticmethod
    def openai_timeout_seconds() -> int:
        try:
            value = int(os.getenv("BOT_OPENAI_TIMEOUT_SECONDS", "45"))
        except ValueError:
            value = 45
        return max(15, min(value, 120))

    def _request(self, method: str, url: str, **kwargs):
        method_upper = method.upper()
        if method_upper == "GET":
            request_fn = requests.get
        elif method_upper == "POST":
            request_fn = requests.post
        else:
            raise ValueError(f"unsupported method: {method}")
        allow_retry = bool(kwargs.pop("allow_retry", True))
        attempts = self.retry_attempts + 1 if allow_retry else 1
        last_error = None
        for attempt in range(attempts):
            try:
                response = request_fn(url, **kwargs)
            except requests.RequestException as exc:
                last_error = exc
                if attempt < attempts - 1:
                    time.sleep(self.retry_backoff_seconds * (attempt + 1))
                    continue
                raise
            if response.status_code in {429, 500, 502, 503, 504} and attempt < attempts - 1:
                if response.status_code == 429:
                    retry_after = response.headers.get("Retry-After", "").strip()
                    try:
                        delay = float(retry_after)
                    except ValueError:
                        delay = self.retry_backoff_seconds * (attempt + 1)
                else:
                    delay = self.retry_backoff_seconds * (attempt + 1)
                time.sleep(max(delay, 0.0))
                continue
            return response
        if last_error:
            raise last_error
        raise requests.RequestException("request failed")

    def health(self) -> tuple[bool, str]:
        try:
            response = self._request(
                method="GET",
                url=f"{self.base_url}/health",
                headers=self._headers(),
                timeout=self.timeout_seconds,
            )
            if response.status_code == 200:
                return True, "ok"
            return False, f"health status={response.status_code}"
        except requests.RequestException as exc:
            return False, f"health error={exc}"

    def query(self, query: str, mode: str = "mix") -> tuple[bool, str]:
        try:
            response = self._request(
                method="POST",
                url=f"{self.base_url}/query",
                json={"query": query, "mode": mode},
                headers=self._headers(),
                timeout=self.timeout_seconds,
                allow_retry=True,
            )
        except requests.RequestException as exc:
            return False, f"query error={exc}"

        if not (200 <= response.status_code < 300):
            return False, f"query status={response.status_code}"

        try:
            payload = response.json()
        except ValueError:
            return False, "query invalid json"
        answer = (
            payload.get("response")
            or payload.get("answer")
            or payload.get("result")
            or ""
        )
        if not answer:
            return False, "query empty response"
        return True, str(answer).strip()

    @staticmethod
    def _openai_model_name(model: str | None = None) -> str:
        return resolve_openai_model(model)

    def query_openai_chat(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        temperature: float = 0.3,
        model: str | None = None,
    ) -> tuple[bool, str]:
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key:
            return False, "openai api key is missing"
        model_name = self._openai_model_name(model)
        api_base = os.getenv("OPENAI_API_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        payload: dict = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        if openai_model_supports_temperature(model_name):
            payload["temperature"] = temperature
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        try:
            response = self._request(
                method="POST",
                url=f"{api_base}/chat/completions",
                json=payload,
                headers=headers,
                timeout=self.openai_timeout_seconds(),
                allow_retry=True,
            )
        except requests.RequestException as exc:
            return False, f"openai error={exc}"

        if not (200 <= response.status_code < 300):
            return False, f"openai status={response.status_code}"
        try:
            body = response.json()
        except ValueError:
            return False, "openai invalid json"
        answer = (
            (body.get("choices") or [{}])[0].get("message", {}).get("content", "")
        )
        if not answer:
            return False, "openai empty response"
        return True, str(answer).strip()

    def query_openai_general(
        self,
        question: str,
        *,
        model: str | None = None,
    ) -> tuple[bool, str]:
        return self.query_openai_chat(
            (
                "Ты технический ассистент. Отвечай кратко и по делу. "
                "Если не уверен, явно скажи об этом."
            ),
            question,
            model=model,
        )

    def query_openai_json(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        temperature: float = 0.1,
        model: str | None = None,
    ) -> tuple[bool, dict | str]:
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key:
            return False, "openai api key is missing"
        model_name = self._openai_model_name(model)
        api_base = os.getenv("OPENAI_API_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        payload: dict = {
            "model": model_name,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        if openai_model_supports_temperature(model_name):
            payload["temperature"] = temperature
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        try:
            response = self._request(
                method="POST",
                url=f"{api_base}/chat/completions",
                json=payload,
                headers=headers,
                timeout=self.openai_timeout_seconds(),
                allow_retry=True,
            )
        except requests.RequestException as exc:
            return False, f"openai error={exc}"

        if not (200 <= response.status_code < 300):
            return False, f"openai status={response.status_code}"
        try:
            body = response.json()
        except ValueError:
            return False, "openai invalid json"
        content = (body.get("choices") or [{}])[0].get("message", {}).get("content", "")
        if not content:
            return False, "openai empty response"
        raw = str(content).strip()
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            match = re.search(r"\{[\s\S]*\}", raw)
            if not match:
                return False, "openai response is not valid json"
            try:
                parsed = json.loads(match.group(0))
            except json.JSONDecodeError:
                return False, "openai response is not valid json"
        if not isinstance(parsed, dict):
            return False, "openai json root must be object"
        return True, parsed

    def translate_to_russian(self, text: str) -> tuple[bool, str]:
        chunks = split_text_for_translation(text)
        if not chunks:
            return False, "translate empty text"

        translated_chunks: list[str] = []
        for chunk in chunks:
            prompt = (
                f"{TECHNICAL_TRANSLATION_RULES_RU}\n\n"
                "Фрагмент для перевода (верни только перевод):\n\n"
                f"{chunk}"
            )
            ok, answer = self.query(prompt, mode="naive")
            if not ok:
                return False, answer
            translated_chunks.append(answer)
        return True, "\n\n".join(translated_chunks).strip()

    def ask_with_fallback(
        self,
        question: str,
        primary_mode: str = "mix",
        fallback_modes: tuple[str, ...] = ("hybrid", "global"),
    ) -> tuple[bool, str, str]:
        tried_modes: list[str] = []
        weak_answer: str | None = None
        weak_mode: str | None = None
        for mode in (primary_mode, *fallback_modes):
            if mode in tried_modes:
                continue
            tried_modes.append(mode)
            ok, answer_or_error = self.query(question, mode)
            if ok and not self._is_weak_answer(answer_or_error):
                return True, answer_or_error, f"{mode} (проверено: {','.join(tried_modes)})"
            if ok:
                weak_answer = answer_or_error
                weak_mode = mode
                continue
        if weak_answer is not None and weak_mode is not None:
            return (
                True,
                weak_answer,
                f"{weak_mode} (все режимы слабые; проверено: {','.join(tried_modes)})",
            )
        return False, "all query modes failed", ",".join(tried_modes)

    def ingest_text(
        self,
        text: str,
        description: str = "",
    ) -> tuple[bool, str, str | None]:
        file_source = description.strip() or "telegram:text-ingest"
        payload = {"text": text, "file_source": file_source}
        if description:
            payload["description"] = description
        try:
            response = self._request(
                method="POST",
                url=f"{self.base_url}/documents/text",
                json=payload,
                headers=self._headers(),
                timeout=self.timeout_seconds,
                allow_retry=False,
            )
            if 200 <= response.status_code < 300:
                track_id = None
                try:
                    track_id = response.json().get("track_id")
                except ValueError:
                    track_id = None
                return True, f"accepted status={response.status_code}", track_id
            try:
                response_body = str(response.json())
            except ValueError:
                response_body = response.text[:500]
            return (
                False,
                f"ingest status={response.status_code} body={response_body}",
                None,
            )
        except requests.RequestException as exc:
            return False, f"ingest error={exc}", None

    def ingest_file(
        self,
        file_name: str,
        file_bytes: bytes,
        mime_type: str | None = None,
        description: str = "",
    ) -> tuple[bool, str, str | None]:
        files = {
            "file": (
                file_name,
                file_bytes,
                mime_type or "application/octet-stream",
            )
        }
        data = {}
        if description:
            data["description"] = description
        last_status = None
        last_body = ""
        for endpoint in ("/documents/upload", "/documents/file"):
            try:
                response = self._request(
                    method="POST",
                    url=f"{self.base_url}{endpoint}",
                    files=files,
                    data=data,
                    headers=self._headers(),
                    timeout=self.timeout_seconds,
                    allow_retry=False,
                )
            except requests.RequestException as exc:
                return False, f"ingest error={exc}", None

            if 200 <= response.status_code < 300:
                track_id = None
                try:
                    track_id = response.json().get("track_id")
                except ValueError:
                    track_id = None
                return (
                    True,
                    f"accepted status={response.status_code} endpoint={endpoint}",
                    track_id,
                )

            last_status = response.status_code
            try:
                last_body = str(response.json())
            except ValueError:
                last_body = response.text[:500]
            if response.status_code != 404:
                break

        return False, f"ingest status={last_status} body={last_body}", None

    def track_status(
        self,
        track_id: str,
    ) -> tuple[bool, str, bool, bool]:
        try:
            response = self._request(
                method="GET",
                url=f"{self.base_url}/documents/track_status/{track_id}",
                headers=self._headers(),
                timeout=self.timeout_seconds,
            )
        except requests.RequestException as exc:
            return False, f"track status error={exc}", False, False

        if not (200 <= response.status_code < 300):
            return False, f"track status={response.status_code}", False, False

        try:
            payload = response.json()
        except ValueError:
            return False, "track status invalid json", False, False

        summary = payload.get("status_summary", {}) or {}
        summary_text = ", ".join(f"{k}={v}" for k, v in sorted(summary.items()))
        if not summary_text:
            summary_text = "queued"

        documents = payload.get("documents", []) or []
        statuses = [str(doc.get("status", "")).lower() for doc in documents if doc]
        if not statuses:
            processing_count = self._to_int(summary.get("processing", 0))
            pending_count = self._to_int(summary.get("pending", 0))
            processed_count = self._to_int(summary.get("processed", 0))
            failed_count = self._to_int(summary.get("failed", 0))
            if processing_count > 0 or pending_count > 0:
                return True, summary_text, False, False
            if processed_count > 0 or failed_count > 0:
                is_success = failed_count == 0 and processed_count > 0
                return True, summary_text, True, is_success
            return True, summary_text, False, False

        terminal_statuses = {"processed", "failed"}
        is_terminal = all(status in terminal_statuses for status in statuses)
        is_success = is_terminal and all(status == "processed" for status in statuses)
        return True, summary_text, is_terminal, is_success

