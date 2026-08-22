from __future__ import annotations
import base64
import json
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def get_json(url: str, headers: dict[str, str] | None = None, timeout: int = 20):
    req = Request(url, headers=headers or {}, method="GET")
    with urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def post_form_json(url: str, data: dict[str, str], headers: dict[str, str] | None = None, timeout: int = 20):
    payload = urlencode(data).encode("utf-8")
    h = {"Content-Type": "application/x-www-form-urlencoded"}
    h.update(headers or {})
    req = Request(url, data=payload, headers=h, method="POST")
    with urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def basic_auth(client_id: str, secret: str) -> str:
    raw = f"{client_id}:{secret}".encode()
    return "Basic " + base64.b64encode(raw).decode()
