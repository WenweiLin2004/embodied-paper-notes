"""Small HTTP boundary: bounded downloads, retries, and polite arXiv pacing."""
from __future__ import annotations

import ipaddress
import threading
import time
from urllib.parse import urlparse

import httpx

MAX_DOWNLOAD_BYTES = 30 * 1024 * 1024
_ARXIV_LOCK = threading.Lock()
_ARXIV_LAST_REQUEST = 0.0


class SourceError(RuntimeError):
    """A source could not be fetched or did not match the requested paper."""


def validate_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"https", "http"} or not parsed.hostname:
        raise SourceError("Only HTTP(S) paper URLs are supported.")
    if parsed.username or parsed.password:
        raise SourceError("URLs containing credentials are not supported.")
    host = parsed.hostname.lower().rstrip(".")
    if host == "localhost" or host.endswith((".localhost", ".local")):
        raise SourceError("Use a public scholarly URL, not a local address.")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address is not None and not address.is_global:
        raise SourceError("Private and loopback addresses are not paper sources.")
    return url


def _pace(url: str) -> None:
    global _ARXIV_LAST_REQUEST
    if urlparse(url).hostname not in {"arxiv.org", "export.arxiv.org", "www.arxiv.org"}:
        return
    with _ARXIV_LOCK:
        wait = 3.0 - (time.monotonic() - _ARXIV_LAST_REQUEST)
        if wait > 0:
            time.sleep(wait)
        _ARXIV_LAST_REQUEST = time.monotonic()


def get(url: str, *, params: dict | None = None) -> httpx.Response:
    """Fetch a public URL with a 30 MB cap; never turn provider failures into []."""
    validate_url(url)
    for attempt in range(3):
        _pace(url)
        try:
            with httpx.Client(timeout=httpx.Timeout(25.0, connect=10.0),
                              headers={"User-Agent": "embodied-paper-notes/0.1 (personal research)"}) as client:
                # Follow redirects ourselves so each redirect target is validated.
                current, query = url, params
                for _ in range(6):
                    with client.stream("GET", current, params=query) as response:
                        if response.is_redirect:
                            target = str(response.url.join(response.headers["location"]))
                            current, query = validate_url(target), None
                            continue
                        response.raise_for_status()
                        body = bytearray()
                        for data in response.iter_bytes():
                            body.extend(data)
                            if len(body) > MAX_DOWNLOAD_BYTES:
                                raise SourceError("Paper download exceeds the 30 MB limit.")
                        headers = dict(response.headers)
                        # iter_bytes already decoded the body; do not decode it twice.
                        for name in ("content-encoding", "transfer-encoding", "content-length"):
                            headers.pop(name, None)
                        return httpx.Response(response.status_code, headers=headers,
                                              content=bytes(body), request=response.request)
                raise SourceError("Too many redirects from paper source.")
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code not in {429, 500, 502, 503, 504} or attempt == 2:
                raise SourceError(f"Source returned HTTP {exc.response.status_code}: {url}") from exc
            retry_after = exc.response.headers.get("Retry-After", "")
            delay = min(float(retry_after), 15.0) if retry_after.isdigit() else 2 ** (attempt + 1)
        except httpx.TransportError as exc:
            if attempt == 2:
                raise SourceError(f"Source request failed: {url}: {type(exc).__name__}") from exc
            delay = 2 ** (attempt + 1)
        time.sleep(delay)
    raise SourceError(f"Unable to fetch {url}")
