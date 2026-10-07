"""TokenMizer's own rate limiter answers 429 with a wait: the adapter waits and asks again,
as any client would, instead of turning a busy second into an ERROR."""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from adebench import tokenmizer


def _server(replies):
    calls = []

    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            calls.append(self.path)
            code, body = replies[min(len(calls), len(replies)) - 1]
            raw = json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, calls


def _adapter(srv):
    a = tokenmizer.TokenmizerAdapter()
    a.url = f"http://127.0.0.1:{srv.server_address[1]}"
    return a


def test_a_rate_limited_read_waits_and_retries():
    srv, calls = _server([(429, {"detail": "Rate limit exceeded. Retry after 0.2s"}), (200, {"ok": True})])
    try:
        assert _adapter(srv)._http("GET", "/api/resume/adebench") == {"ok": True}
        assert len(calls) == 2
    finally:
        srv.shutdown()


def test_a_server_that_keeps_refusing_is_still_an_error():
    srv, calls = _server([(429, {"detail": "Rate limit exceeded. Retry after 0.1s"})])
    try:
        with pytest.raises(tokenmizer.TokenmizerError, match="429"):
            _adapter(srv)._http("GET", "/api/resume/adebench")
        assert 2 <= len(calls) <= 10
    finally:
        srv.shutdown()
