from __future__ import annotations

from urllib.parse import urlparse


def safe_element_url(raw: str | None) -> str | None:
    if not raw:
        return None
    parsed = urlparse(raw.strip())
    if parsed.scheme not in ("http", "https"):
        return None
    if not parsed.netloc:
        return None
    return raw.strip()


SECURITY_HEADERS = {
    "Content-Security-Policy": "default-src 'self'",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
}