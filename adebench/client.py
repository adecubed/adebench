"""Low-level access used by the ADE adapter: HTTP with a stopwatch, and
read-only SQLite on the Brain's databases. Nothing here is called by the
sections; another adapter may ignore this module entirely."""
from __future__ import annotations

import json
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from adebench.config import CFG

# Every call leaves a trace (endpoint, ms, chars, http): latency and noise
# per door come from here, without instrumenting the sections.
traces: list[dict] = []


class ServiceDown(RuntimeError):
    """The memory service did not answer (connection refused, timeout)."""


class ErrorResponse(RuntimeError):
    """The memory service answered with an HTTP error. Raised, never returned:
    an error body must not be mistaken for an answer (a 500 on /sofia/ask
    used to score as perfect abstention)."""

    def __init__(self, path: str, code: int, body: str):
        super().__init__(f"HTTP {code} on {path}: {body[:120]}")
        self.path, self.code, self.body = path, code, body


def _req(method: str, path: str, body: dict | None = None, params: dict | None = None,
         timeout: float = 60) -> tuple[Any, float]:
    url = CFG.brain_url + path
    if params:
        url += "?" + urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json; charset=utf-8"})
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
    except urllib.error.HTTPError as e:
        try:
            raw = e.read()
        except OSError:  # body unreadable (socket closed early): still an error response
            raw = b""
        ms = (time.perf_counter() - t0) * 1000
        traces.append({"door": path, "ms": ms, "chars": len(raw), "http": e.code})
        raise ErrorResponse(path, e.code, raw[:300].decode("utf-8", "ignore")) from e
    except Exception as e:  # noqa: BLE001
        raise ServiceDown(f"{method} {path}: {e}") from e
    ms = (time.perf_counter() - t0) * 1000
    traces.append({"door": path, "ms": ms, "chars": len(raw), "http": 200})
    try:
        return json.loads(raw.decode("utf-8")), ms
    except Exception:  # noqa: BLE001
        return raw.decode("utf-8", "ignore"), ms


def get(path: str, **params) -> Any:
    return _req("GET", path, params=params)[0]


def post(path: str, body: dict | None = None, **params) -> Any:
    return _req("POST", path, body=body, params=params)[0]


def delete(path: str, **params) -> Any:
    return _req("DELETE", path, params=params)[0]


def ask(query: str, sources: list[str], include_raw: bool = True) -> dict:
    """POST /sofia/ask — the Brain's retrieval door (despite the name it
    serves any client). Empty sources = the Brain's defaults."""
    body = {"query": query, "sources": sources, "include_raw": include_raw}
    r, ms = _req("POST", "/sofia/ask", body=body, timeout=90)
    if not isinstance(r, dict):
        r = {"ok": False, "summary": str(r)}
    r["_ms"] = ms
    # noise is measured on the TEXT sent to the client, not on the JSON
    # (which, with include_raw, also carries the raw hits)
    if traces:
        traces[-1]["chars"] = len(r.get("summary") or "")
    return r


def warm_up() -> float | None:
    """The first /sofia/ask after boot loads the embedder and the vector
    store and can take more than 90 s: paid here, outside the measures."""
    try:
        _, ms = _req("POST", "/sofia/ask", body={"query": "ciao", "sources": ["semantic"]}, timeout=300)
    except (ServiceDown, ErrorResponse):
        return None
    traces.pop()
    return ms


def health() -> dict:
    """The health payload, or {} when the service is down OR answers with an
    error status. Only a 200 with a dict counts as alive."""
    try:
        r = get("/brain/health")
        return r if isinstance(r, dict) else {}
    except (ServiceDown, ErrorResponse):
        return {}


def debug() -> dict:
    try:
        r = get("/sofia/ask/debug")
    except ErrorResponse:
        return {}
    return r if isinstance(r, dict) else {}


# ─── Read-only access to the databases ──────────────────────────────────────

_db_dir: Path | None = None


def db_dir() -> Path:
    global _db_dir
    if _db_dir is None:
        d = debug().get("DB_DIR")
        if not d:
            raise ServiceDown("DB_DIR unknown: /sofia/ask/debug does not answer")
        _db_dir = Path(d)
    return _db_dir


def sql(db: str, query: str, *args) -> list[dict]:
    """READ-ONLY query (URI mode=ro) on one of the Brain's databases."""
    p = db_dir() / db
    if not p.exists():
        return []
    uri = "file:" + p.as_posix() + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute(query, args).fetchall()]
    finally:
        conn.close()


def columns(db: str, table: str) -> set[str]:
    return {r["name"] for r in sql(db, f"PRAGMA table_info({table})")}
