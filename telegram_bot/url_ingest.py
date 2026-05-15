import ipaddress
import os
import socket
from urllib.parse import urldefrag, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

_MAX_HEADINGS = 12
_MAX_PARAGRAPHS = 40
_MAX_OUTPUT_CHARS = 12000
_MAX_FETCH_BYTES = 1_000_000
_MAX_FOLLOW_PAGES = int(os.getenv("BOT_URL_FOLLOW_MAX_PAGES", "6"))
_MAX_LINKS_TO_QUEUE = int(os.getenv("BOT_URL_FOLLOW_MAX_LINKS", "24"))
_MAX_FOLLOW_DEPTH = int(os.getenv("BOT_URL_FOLLOW_DEPTH", "1"))


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
    default_port = 443 if parsed.scheme == "https" else 80
    try:
        infos = socket.getaddrinfo(host, parsed.port or default_port, proto=socket.IPPROTO_TCP)
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


def _same_site(url_a: str, url_b: str) -> bool:
    pa, pb = urlparse(url_a), urlparse(url_b)
    if pa.scheme not in {"http", "https"} or pb.scheme not in {"http", "https"}:
        return False
    return pa.netloc.lower() == pb.netloc.lower()


def _normalize_follow_url(base_url: str, href: str) -> str | None:
    raw = (href or "").strip()
    if not raw or raw.startswith(("#", "javascript:", "mailto:", "tel:", "data:")):
        return None
    joined = urljoin(base_url, raw)
    joined, _frag = urldefrag(joined)
    parsed = urlparse(joined)
    if parsed.scheme not in {"http", "https"}:
        return None
    if not parsed.netloc:
        return None
    return joined


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


def _extract_significant_from_html(url: str, body: str) -> tuple[bool, str]:
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
    return True, result


def _collect_same_site_links(html: str, page_url: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    seen: set[str] = set()
    out: list[str] = []
    page_norm, _ = urldefrag(page_url)
    seen.add(page_norm.rstrip("/"))

    for tag in soup.find_all("a", href=True):
        if len(out) >= _MAX_LINKS_TO_QUEUE:
            break
        candidate = _normalize_follow_url(page_url, tag["href"])
        if not candidate or not _same_site(page_url, candidate):
            continue
        key = candidate.rstrip("/")
        if key in seen:
            continue
        seen.add(key)
        out.append(candidate)
    return out


def _fetch_one(
    url: str,
    timeout_seconds: int,
) -> tuple[bool, str, str, str]:
    safe_ok, safe_reason = _is_public_url(url)
    if not safe_ok:
        return False, safe_reason, "", ""
    try:
        with requests.get(
            url,
            timeout=timeout_seconds,
            headers={"User-Agent": "LightRAG-TelegramBot/1.0"},
            stream=True,
            allow_redirects=False,
        ) as response:
            if 300 <= response.status_code < 400:
                return False, "url redirects are blocked", "", ""
            if response.status_code >= 400:
                return False, f"url fetch status={response.status_code}", "", ""

            content_type = (response.headers.get("Content-Type") or "").lower()
            if (
                "text/html" not in content_type
                and "text/plain" not in content_type
                and "application/xhtml+xml" not in content_type
            ):
                return False, f"url unsupported content-type={content_type or 'unknown'}", "", ""

            body = _read_response_text_limited(response).strip()
    except requests.RequestException as exc:
        return False, f"url fetch error={exc}", "", ""
    except ValueError as exc:
        return False, str(exc), "", ""

    return True, "", body, content_type


def fetch_significant_text_from_url(
    url: str,
    timeout_seconds: int = 20,
) -> tuple[bool, str]:
    max_pages = max(1, min(_MAX_FOLLOW_PAGES, 20))
    max_depth = max(0, min(_MAX_FOLLOW_DEPTH, 3))
    queue: list[tuple[str, int]] = [(url, 0)]
    visited: set[str] = set()
    blocks: list[str] = []
    pages_fetched = 0
    queued_keys: set[str] = set()

    while queue and pages_fetched < max_pages:
        current, depth = queue.pop(0)
        key, _frag = urldefrag(current)
        key = key.rstrip("/")
        if key in visited:
            continue
        visited.add(key)
        if key in queued_keys:
            queued_keys.discard(key)

        ok, err, body, content_type = _fetch_one(current, timeout_seconds)
        if not ok:
            if current == url:
                return False, err
            continue

        pages_fetched += 1

        if "text/plain" in content_type:
            if not body:
                if current == url:
                    return False, "url empty content"
                continue
            blocks.append(f"Source URL: {current}\n\n{body}")
            continue

        extract_ok, chunk_or_err = _extract_significant_from_html(current, body)
        if not extract_ok:
            if current == url:
                return False, chunk_or_err
            continue
        blocks.append(chunk_or_err)

        if pages_fetched >= max_pages:
            break

        if depth < max_depth:
            for link in _collect_same_site_links(body, current):
                if pages_fetched + len(queue) >= max_pages:
                    break
                lk, _ = urldefrag(link)
                lk_norm = lk.rstrip("/")
                if lk_norm in visited or lk_norm in queued_keys:
                    continue
                queued_keys.add(lk_norm)
                queue.append((link, depth + 1))

    if not blocks:
        return False, "url no significant content"

    merged = "\n\n---\n\n".join(blocks).strip()
    if not merged:
        return False, "url empty content"
    return True, merged[:_MAX_OUTPUT_CHARS]
