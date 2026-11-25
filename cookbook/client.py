"""POST /v1/systemone. The key stays in the environment or a mode-600 file."""

from __future__ import annotations

import json
import os
import re
import ssl
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

DEFAULT_BASE_URL = "https://api.typesafe.ai"
DEFAULT_MODEL = "jev-1.13.0"
_SECRET = re.compile(r"apikey_[A-Za-z0-9_-]+")


class DecisionError(RuntimeError):
    def __init__(self, status_code: int, body: str) -> None:
        self.status_code = status_code
        self.body = body
        super().__init__(f"decision API {status_code}: {body}")


def redact(text: str, key: str = "") -> str:
    cleaned = _SECRET.sub("apikey_[redacted]", text)
    if key:
        cleaned = cleaned.replace(key, "[redacted]")
    return cleaned


def load_api_key() -> str:
    for name in ("TYPESAFE_API_KEY", "JEV_API_KEY"):
        env = os.getenv(name, "").strip()
        if env:
            return env
    override = os.getenv("TYPESAFE_KEY_FILE", "").strip()
    paths = [Path(override)] if override else [
        Path.home() / ".config" / "typesafe" / "api_key",
        Path.home() / ".typesafe" / "api_key",
    ]
    for path in paths:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        for line in text.splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                return stripped
    return ""


def _ssl_context() -> ssl.SSLContext:
    """Python.org builds on macOS do not ship the system CA bundle."""
    for path in ("/etc/ssl/cert.pem", "/private/etc/ssl/cert.pem"):
        if os.path.isfile(path):
            return ssl.create_default_context(cafile=path)
    try:
        import certifi
    except ImportError:
        return ssl.create_default_context()
    return ssl.create_default_context(cafile=certifi.where())


def _needs_auth(base_url: str) -> bool:
    host = base_url.lower()
    return "127.0.0.1" not in host and "localhost" not in host


def system_one(
    state: Any,
    questions: dict[str, Any],
    *,
    model: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
    timeout: float = 30.0,
    retries: int = 2,
) -> dict[str, Any]:
    """One decision call. Returns the JSON body plus elapsed_ms."""
    key = (api_key if api_key is not None else load_api_key()).strip()
    root = (base_url or os.getenv("DECISION_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
    if _needs_auth(root) and not key:
        raise DecisionError(
            401,
            "No API key. Set TYPESAFE_API_KEY, or write ~/.config/typesafe/api_key (mode 600).",
        )
    payload = {
        "state": state,
        "model": (model or os.getenv("TYPESAFE_MODEL") or DEFAULT_MODEL).strip() or DEFAULT_MODEL,
        "questions": questions,
    }
    encoded = json.dumps(payload).encode("utf-8")
    if _SECRET.search(encoded.decode("utf-8")):
        raise DecisionError(400, "Refusing to send a state that looks like an API key.")

    headers = {"Content-Type": "application/json"}
    if key and _needs_auth(root):
        headers["Authorization"] = f"Bearer {key}"

    last: DecisionError | None = None
    for attempt in range(retries + 1):
        request = urllib.request.Request(
            f"{root}/v1/systemone",
            data=encoded,
            headers=headers,
            method="POST",
        )
        started = time.perf_counter()
        try:
            with urllib.request.urlopen(request, timeout=timeout, context=_ssl_context()) as response:
                raw = response.read().decode("utf-8")
                status = response.status
        except urllib.error.HTTPError as exc:
            detail = redact(exc.read().decode("utf-8", "replace")[:400], key)
            last = DecisionError(exc.code, detail or exc.reason)
            if exc.code in {429, 500, 502, 503, 529} and attempt < retries:
                time.sleep(0.4 * (2**attempt))
                continue
            raise last from None
        except urllib.error.URLError as exc:
            raise DecisionError(502, redact(str(exc.reason), key)[:200]) from None
        elapsed_ms = (time.perf_counter() - started) * 1000
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise DecisionError(status, "response was not JSON") from exc
        if not isinstance(data.get("answers"), dict):
            raise DecisionError(status, "response missing answers")
        data["elapsed_ms"] = round(elapsed_ms, 1)
        return data
    raise last or DecisionError(429, "rate limited")
