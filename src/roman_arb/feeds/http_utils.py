from __future__ import annotations

import base64
import json
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

_RETRYABLE_HTTP = {429, 500, 502, 503, 504}


def _retry_delay(exc: Exception, attempt: int) -> float:
    if isinstance(exc, HTTPError):
        try:
            raw = exc.headers.get("Retry-After") if exc.headers else None
            if raw is not None:
                return max(0.0, min(10.0, float(raw)))
        except Exception:
            pass
    return min(4.0, 0.5 * (2**attempt))


def _read_json(req: Request, timeout: int, retries: int):
    retries = max(0, int(retries))
    for attempt in range(retries + 1):
        try:
            with urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except HTTPError as exc:
            if exc.code not in _RETRYABLE_HTTP or attempt >= retries:
                raise
            time.sleep(_retry_delay(exc, attempt))
        except URLError as exc:
            if attempt >= retries:
                raise
            time.sleep(_retry_delay(exc, attempt))
    raise RuntimeError("unreachable HTTP retry state")


def get_json(
    url: str,
    headers: dict[str, str] | None = None,
    timeout: int = 20,
    retries: int = 2,
):
    req = Request(url, headers=headers or {}, method="GET")
    return _read_json(req, timeout, retries)


def post_form_json(
    url: str,
    data: dict[str, str],
    headers: dict[str, str] | None = None,
    timeout: int = 20,
    retries: int = 2,
):
    payload = urlencode(data).encode("utf-8")
    h = {"Content-Type": "application/x-www-form-urlencoded"}
    h.update(headers or {})
    req = Request(url, data=payload, headers=h, method="POST")
    return _read_json(req, timeout, retries)


def basic_auth(client_id: str, secret: str) -> str:
    raw = f"{client_id}:{secret}".encode()
    return "Basic " + base64.b64encode(raw).decode()
