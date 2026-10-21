"""Refuse state-changing browser requests that come from another site (CSRF protection).

The session cookie is SameSite=Lax, which already stops most cross-site
requests. This middleware adds a second check: a POST, PUT, PATCH or DELETE
that carries an Origin (or Referer) header must come from an allowed origin.
Requests without either header (curl, server-side calls) carry no browser
cookies from another site and are let through.
"""

from collections.abc import Awaitable, Callable
from urllib.parse import urlsplit

from fastapi import Request, Response
from fastapi.responses import JSONResponse

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def _origin_of(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}"


def make_origin_check(
    allowed_origins: list[str],
) -> Callable[[Request, Callable[[Request], Awaitable[Response]]], Awaitable[Response]]:
    allowed = {origin.rstrip("/") for origin in allowed_origins}

    async def origin_check(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if request.method not in SAFE_METHODS:
            origin = request.headers.get("origin")
            if origin is None and (referer := request.headers.get("referer")):
                origin = _origin_of(referer)
            if origin is not None and origin.rstrip("/") not in allowed:
                return JSONResponse(
                    {"detail": "Request refused: it does not come from this site."},
                    status_code=403,
                )
        return await call_next(request)

    return origin_check
