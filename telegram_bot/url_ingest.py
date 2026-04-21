import ipaddress
import socket
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

_MAX_HEADINGS = 12
_MAX_PARAGRAPHS = 40
_MAX_OUTPUT_CHARS = 12000
_MAX_FETCH_BYTES = 1_000_000


def is_http_url(text: str) -> bool:
    value = (text or "").strip()
    if not value:
        return False
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"}:
        return False
    return bool(parsed.netloc)


def _is_public_ip(ip_text: str) -> bool:
    ip = ipaddress.ip_address(ip_text)
    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def _is_public_url(url: str) -> tuple[bool, str]:
    parsed = urlparse(url)
    host = parsed.hostname
    if not host:
        return False, "url invalid host"
    if host.lower() in {"localhost"}:
        return False, "url host is blocked"
    try:
        infos = socket.getaddrinfo(host, parsed.port or 443, proto=socket.IPPROTO_TCP)
    except OSError:
        return False, "url host resolve failed"
    if not infos:
        return False, "url host resolve failed"
    for info in infos:
        ip_text = info[4][0]
        try:
            if not _is_public_ip(ip_text):
                return False, "url host is blocked"
        except ValueError:
            return False, "url host resolve invalid"
    return True, "ok"


def _read_response_text_limited(response: requests.Response) -> str:
    chunks: list[bytes] = []
    total = 0
    for chunk in response.iter_content(chunk_size=8192):
        if not chunk:
            continue
        total += len(chunk)
        if total > _MAX_FETCH_BYTES:
            raise ValueError("url content too large")
        chunks.append(chunk)
    encoding = response.encoding or "utf-8"
    return b"".join(chunks).decode(encoding, errors="replace")


def fetch_significant_text_from_url(
    url: str,
    timeout_seconds: int = 20,
) -> tuple[bool, str]:
    safe_ok, safe_reason = _is_public_url(url)
    if not safe_ok:
        return False, safe_reason
    try:
        with requests.get(
            url,
            timeout=timeout_seconds,
            headers={"User-Agent": "LightRAG-TelegramBot/1.0"},
            stream=True,
            allow_redirects=False,
        ) as response:
            if 300 <= response.status_code < 400:
                return False, "url redirects are blocked"
            if response.status_code >= 400:
                return False, f"url fetch status={response.status_code}"

            content_type = (response.headers.get("Content-Type") or "").lower()
            if (
                "text/html" not in content_type
                and "text/plain" not in content_type
                and "application/xhtml+xml" not in content_type
            ):
                return False, f"url unsupported content-type={content_type or 'unknown'}"

            body = _read_response_text_limited(response).strip()
    except requests.RequestException as exc:
        return False, f"url fetch error={exc}"
    except ValueError as exc:
        return False, str(exc)

    if "text/plain" in content_type:
        if not body:
            return False, "url empty content"
        return True, body[:_MAX_OUTPUT_CHARS]

    soup = BeautifulSoup(body, "html.parser")
    for tag in soup(["script", "style", "noscript", "header", "footer", "nav", "form"]):
        tag.decompose()

    title = ""
    if soup.title and soup.title.string:
        title = soup.title.string.strip()

    headings: list[str] = []
    for tag_name in ("h1", "h2", "h3"):
        for tag in soup.find_all(tag_name):
            text = tag.get_text(" ", strip=True)
            if text and len(text) > 3:
                headings.append(text)
                if len(headings) >= _MAX_HEADINGS:
                    break
        if len(headings) >= _MAX_HEADINGS:
            break

    paragraphs: list[str] = []
    for tag in soup.find_all("p"):
        text = tag.get_text(" ", strip=True)
        if text and len(text) >= 40:
            paragraphs.append(text)
            if len(paragraphs) >= _MAX_PARAGRAPHS:
                break

    parts: list[str] = [f"Source URL: {url}"]
    if title:
        parts.append(f"Title: {title}")
    if headings:
        parts.append("Headings:\n- " + "\n- ".join(headings))
    if paragraphs:
        parts.append("Main content:\n" + "\n\n".join(paragraphs))
    if not headings and not paragraphs:
        return False, "url no significant content"

    result = "\n\n".join(parts).strip()
    if not result:
        return False, "url empty content"
    return True, result[:_MAX_OUTPUT_CHARS]

