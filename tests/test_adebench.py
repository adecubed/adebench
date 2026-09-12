"""Tests that need no memory service: a fake adapter drives the sections,
and the client is exercised against a local HTTP server.

Each test guards one way the score could lie:
  - an HTTP error is never an answer (health false, cases ERROR, no PASS)
  - a failed read is an ERROR, never an empty value that turns into SKIP
  - a memory without a feature is SKIP and leaves the denominator
  - running one section is not a full score
  - expected words match whole tokens ('8766' is not inside '18766')
  - two runs in the same second get two files; the delta only compares
    comparable runs (same adapter, door, golden set, sections, setup)
"""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from adebench import adapter, report, sections
from adebench.config import CFG


# ─── a fake memory ───────────────────────────────────────────────────────────

class Fake:
    """Adapter with knobs: what the door answers, whether calls fail."""

    def __init__(self, answer=None, error: Exception | None = None, cards=(), edges=0, fact_nodes=(0, 0)):
        self._answer = answer or {"summary": ""}
        self._error = error
        self._cards = list(cards)
        self._edges = edges
        self._fact_nodes = fact_nodes
        self.working: dict = {}

    def _r(self):
        if self._error:
            raise self._error
        return dict(self._answer)

    def health(self): return self._error is None
    def warm_up(self): return 1.0
    def doors(self): return ["only"]
    def door_text(self, q, door): r = self._r(); return r.get("summary", ""), r
    def ask(self, q): return self._r()
    def cards(self): return self._cards
    def corrections(self): return []
    def aliases(self): return []
    def update_trace(self): return {"superseded_live": 0, "relation_updates": 1}
    def event_date_share(self): return (0, 0)
    def recent_days(self, n): return []
    def episodes_of_day(self, d, limit): return []
    def signed_episodes(self, p): return 0
    def working_write(self, s, k, v, ttl): self.working[(s, k)] = v; return True
    def working_read(self, s, k): return self.working.get((s, k))
    def working_clear(self, s): self.working = {kk: v for kk, v in self.working.items() if kk[0] != s}
    def working_age_minutes(self, s, k): return None
    def file_search(self, q, limit): return []
    def graph_edges(self, e): return self._edges
    def graph_orphans(self): return self._fact_nodes
    def graph_counts(self): return {"nodes": 0, "edges": 0}
    def health_report(self): return {}, []
    def measured_doors(self): return []
    def traces(self): return []
    def probe_doors(self, q): pass


class BrokenRead(Fake):
    def __init__(self, broken: str, **kw):
        super().__init__(**kw)
        self._broken = broken

    def cards(self):
        if self._broken == "cards":
            raise RuntimeError("db locked")
        return super().cards()

    def recent_days(self, n):
        if self._broken == "days":
            raise RuntimeError("db locked")
        return super().recent_days(n)

    def working_age_minutes(self, s, k):
        if self._broken == "age":
            raise RuntimeError("db locked")
        return super().working_age_minutes(s, k)


@pytest.fixture
def cases(tmp_path, monkeypatch):
    (tmp_path / "questions.json").write_text(json.dumps([
        {"question": "porta?", "expected": [["8766"]], "validated": True}]), encoding="utf-8")
    (tmp_path / "abstention.json").write_text(json.dumps(["Cos'e' Zarpetta?"]), encoding="utf-8")
    monkeypatch.setattr(CFG, "cases", tmp_path)
    monkeypatch.setattr(CFG, "history", tmp_path / "history")
    monkeypatch.setattr(CFG, "door", "only")
    monkeypatch.setattr(CFG, "sandbox_test", None)
    monkeypatch.setattr(CFG, "repo", None)
    return tmp_path


def _use(ada):
    adapter.use(ada)
    return ada


# ─── the contract ────────────────────────────────────────────────────────────

def test_contract_checked_before_running():
    with pytest.raises(TypeError, match="does not implement"):
        adapter.load("builtins:object")
    assert len(adapter.required_methods()) >= 20


def test_fake_honours_the_contract():
    missing = [m for m in adapter.required_methods() if not callable(getattr(Fake(), m, None))]
    assert missing == []


# ─── errors are never passes ─────────────────────────────────────────────────

def test_service_error_is_not_abstention(cases):
    _use(Fake(error=RuntimeError("HTTP 500")))
    s = sections.abstention()
    assert s["counts"]["ERROR"] == 1 and s["counts"]["PASS"] == 0
    assert s["score"] == 0.0


def test_error_in_the_door_is_error_not_silent_fail(cases):
    _use(Fake(error=RuntimeError("HTTP 500")))
    assert [c["status"] for c in sections.door()["cases"]] == ["ERROR"]


def test_empty_answer_is_not_abstention(cases):
    _use(Fake(answer={"summary": ""}))
    assert sections.abstention()["counts"]["ERROR"] == 1


def test_real_abstention_passes(cases):
    _use(Fake(answer={"summary": "Nessun risultato", "episodic": [{"_fallback": True}]}))
    s = sections.abstention()
    assert s["counts"]["PASS"] == 1 and s["score"] == 1.0


# ─── a failed read is an ERROR, never an empty value ────────────────────────

def test_graph_with_broken_cards_read_is_not_ten(cases):
    _use(BrokenRead("cards", fact_nodes=(0, 10)))
    s = sections.graph()
    assert s["counts"]["ERROR"] == 1 and s["counts"]["PASS"] == 1
    assert s["score"] == 0.5  # the orphan check passed, the cards read blew up


def test_time_with_broken_episodic_is_not_ten(cases):
    _use(BrokenRead("days"))
    s = sections.time_section([{"content": "[dal 2026-09-01] fatto"}])
    assert s["counts"]["ERROR"] == 1 and s["score"] < 1.0


def test_live_state_with_broken_age_read_is_error(cases):
    _use(BrokenRead("age", answer={"summary": "x"}))
    assert sections.live_state()["counts"]["ERROR"] == 1


# ─── missing features are SKIP, out of the denominator ───────────────────────

def test_empty_graph_earns_nothing(cases):
    _use(Fake(cards=[], edges=0, fact_nodes=(0, 0)))
    s = sections.graph()
    assert s["score"] is None
    assert s["counts"]["SKIP"] == 2 and s["counts"]["PASS"] == 0


def test_graph_with_data_is_measured(cases):
    _use(Fake(cards=[{"entity": "brain", "content": "x", "date": "2026"}], edges=3, fact_nodes=(0, 10)))
    s = sections.graph()
    assert s["score"] == 1.0 and s["counts"]["PASS"] == 2


def test_no_cards_is_skip(cases):
    _use(Fake(cards=[]))
    assert sections.cards()["score"] is None


def test_updates_without_sandbox_earn_nothing(cases):
    _use(Fake())
    s = sections.updates(with_sandbox=False)
    assert s["score"] is None
    assert s["measures"]["relation_updates"] == 1  # the trace is reported, not scored


def test_total_excludes_unmeasured_and_counts_not_run():
    weights = {"a": 25, "b": 15, "c": 60}
    secs = [{"name": "a", "weight": 25, "score": 1.0, "cases": []},
            {"name": "b", "weight": 15, "score": None, "cases": []},
            {"name": "health", "weight": 0, "score": None, "cases": []}]
    assert report.total_score(secs, weights) == (25.0, 25, 60, 100)


def test_running_one_section_is_not_a_full_score():
    secs = [{"name": "door", "weight": 25, "score": 1.0, "cases": []}]
    points, measured, not_run, total = report.total_score(secs)
    assert (points, measured, not_run, total) == (25.0, 25, 75, 100)
    line = report.score_line({"total": points, "measured_weight": measured, "not_run_weight": not_run,
                              "total_weight": total, "delta": {}})
    assert "75 not run" in line


# ─── whole-token matching ───────────────────────────────────────────────────

@pytest.mark.parametrize("text,expected,found", [
    ("gira sulla porta 8766", "8766", True),
    ("gira sulla porta 18766", "8766", False),
    ("gira sulla porta 87660", "8766", False),
    ("versione 0.2.4 installata", "0.2.4", True),
    ("versione 10.2.4 installata", "0.2.4", False),
    ("salvato in C:\\Users\\simon\\ade\\report.docx", "C:\\Users\\simon\\ade", True),
    ("Model Context Protocol (MCP)", "MCP", True),
    ("usa la MCPHost", "MCP", False),
    ("il masker anonimizza i dati", "anonimizz*", True),
    ("il masker anonimizza i dati", "anonimizz", False),
    ("disanonimizzato", "anonimizz*", False),
])
def test_whole_token_expectations(text, expected, found):
    assert (sections.present(text, [expected]) is not None) == found


def test_door_with_right_and_wrong_expectation(cases):
    _use(Fake(answer={"summary": "Il Brain risponde sulla porta 8766."}))
    assert sections.door()["score"] == 1.0
    _use(Fake(answer={"summary": "Il Brain risponde sulla porta 18766."}))
    assert sections.door()["score"] == 0.0


# ─── history: no collisions, only comparable deltas ─────────────────────────

def _run():
    return [{"name": "door", "weight": 25, "score": 1.0, "cases": [], "counts": {}, "measures": {}, "warnings": []}]


def test_two_runs_in_the_same_second_do_not_overwrite(cases):
    cfg = {"adapter": "x:A", "door": "only", "cases_hash": "h", "sections": ["door"]}
    pj1, _, _ = report.save(_run(), cfg)
    pj2, _, _ = report.save(_run(), cfg)
    assert pj1 != pj2 and pj1.exists() and pj2.exists()


def test_delta_only_between_comparable_runs(cases):
    base = {"adapter": "x:A", "door": "only", "cases_hash": "h", "sections": ["door"]}
    report.save(_run(), base)
    _, _, r2 = report.save(_run(), {**base, "adapter": "y:B"})
    assert r2["delta"]["total"] is None  # different adapter: nothing to compare with
    _, _, r3 = report.save(_run(), {**base, "cases_hash": "other"})
    assert r3["delta"]["total"] is None  # different golden set
    _, _, r4 = report.save(_run(), base)
    assert r4["delta"]["total"] == 0.0  # comparable: delta computed


def test_delta_ignores_runs_with_another_setup(cases):
    base = {"adapter": "x:A", "door": "only", "cases_hash": "h", "sections": ["door", "graph"],
            "voice_cut": 2400, "sandbox_test": None, "repo": None}
    report.save(_run(), base)
    _, _, r2 = report.save(_run(), {**base, "sections": ["door"]})
    assert r2["delta"]["total"] is None  # fewer sections is another setup, not a regression
    _, _, r3 = report.save(_run(), {**base, "voice_cut": 1200})
    assert r3["delta"]["total"] is None  # another cut is another setup
    _, _, r4 = report.save(_run(), {**base, "sections": ["graph", "door"]})
    assert r4["delta"]["total"] == 0.0  # same sections in another order: comparable


def test_cli_no_sandbox_test_is_another_setup(cases, tmp_path, monkeypatch):
    """Same --sandbox-test path, once run and once switched off with
    --no-sandbox-test: 10/10 then 'not measured' must not become a -10 delta."""
    from adebench.__main__ import main
    script = tmp_path / "fake_sandbox.py"
    script.write_text("print('  PASS  something works')\nprint('1/1 passed')\n", encoding="utf-8")
    monkeypatch.setattr(adapter, "_current", None)
    common = ["--adapter", "tests.test_adebench:Fake", "--cases", str(cases),
              "--history", str(cases / "history"), "--sections", "updates", "--sandbox-test", str(script)]
    assert main(common) == 0
    assert main(common + ["--no-sandbox-test"]) == 0
    runs = [json.loads(p.read_text(encoding="utf-8")) for p in (cases / "history").glob("*.json")]
    assert len(runs) == 2
    # pick by the flag, not by file order: in the same second the file names
    # sort by fingerprint hash, not by time
    first = next(r for r in runs if r["config"]["sandbox_enabled"])
    second = next(r for r in runs if not r["config"]["sandbox_enabled"])
    assert first["total"] == 10.0 and first["config"]["sandbox_enabled"] is True
    assert second["measured_weight"] == 0 and second["config"]["sandbox_enabled"] is False
    assert second["config"]["fingerprint"] != first["config"]["fingerprint"]
    assert second["delta"]["total"] is None  # another setup: no delta, no fake regression


# ─── the HTTP client never returns an error body as an answer ───────────────

class _Server500(BaseHTTPRequestHandler):
    def _answer(self):
        self.send_response(500)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"detail": "boom"}')

    do_GET = _answer
    do_POST = _answer

    def log_message(self, *a):  # silence
        pass


@pytest.fixture
def server_500(monkeypatch):
    srv = HTTPServer(("127.0.0.1", 0), _Server500)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    monkeypatch.setattr(CFG, "brain_url", f"http://127.0.0.1:{srv.server_port}")
    yield srv
    srv.shutdown()


def test_http_500_is_not_alive(server_500):
    from adebench import client
    assert client.health() == {}


def test_http_500_raises_instead_of_answering(server_500):
    from adebench import client
    with pytest.raises(client.ErrorResponse):
        client.ask("ciao", [])


def test_ade_adapter_health_false_on_500(server_500):
    from adebench.ade import AdeAdapter
    assert AdeAdapter().health() is False
