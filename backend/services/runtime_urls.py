"""
Runtime URL helpers for resolving public backend URLs.
"""

from urllib.parse import urlsplit

from fastapi import Request

from config import settings


_LOCAL_HOSTNAMES = {"localhost", "127.0.0.1", "0.0.0.0", "::1"}


def _is_local_url(url: str) -> bool:
    parsed = urlsplit(url)
    hostname = (parsed.hostname or "").lower()
    return hostname in _LOCAL_HOSTNAMES


def _origin_from_request(request: Request) -> str:
    scheme = request.headers.get("x-forwarded-proto") or request.url.scheme
    host = (
        request.headers.get("x-forwarded-host")
        or request.headers.get("host")
        or request.url.netloc
    )
    if not host:
        return ""
    return f"{scheme}://{host}".rstrip("/")


def resolve_backend_url(request: Request | None = None) -> str:
    """
    Resolve the public backend base URL.

    Priority:
    1. Explicit BACKEND_URL env when it is public
    2. Request origin headers (for routes with request context)
    3. Local fallback only in development
    """
    configured_url = settings.BACKEND_URL.strip().rstrip("/")
    environment = settings.ENVIRONMENT.lower()

    if configured_url and not _is_local_url(configured_url):
        return configured_url

    if request is not None:
        request_origin = _origin_from_request(request)
        if request_origin:
            return request_origin

    if environment == "development" and configured_url:
        return configured_url

    raise RuntimeError(
        "BACKEND_URL must point to a public URL in production"
    )