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
    def door_cut(self, door): return 2400
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
    monkeypatch.setattr(CFG, "write_to_serve_max_s", 0)  # no polling in tests unless asked
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


# ─── mandatory items of a correction ────────────────────────────────────────

def test_mandatory_items_stop_at_the_end_of_the_sentence():
    text = ("Nella scheda di X non omettere mai: la porta 8766, il modello Nova; il sito su Render. "
            "NON dire che X cerca investitori: non e' mai partita.")
    assert sections._mandatory_items(text) == ["la porta 8766", "il modello Nova", "il sito su Render"]
    assert sections._mandatory_items("never omit: a.b version 1.4.2, twelve tools") == ["a.b version 1.4.2", "twelve tools"]
    assert sections._mandatory_items("no marker here") == []


def test_mandatory_item_tolerates_inflection():
    card = "Il progetto e' presente nel MCP Registry ed e' montato come server core."
    assert sections._item_present("presenza nel MCP Registry", card)
    assert sections._item_present("montata come server core", card)
    assert not sections._item_present("nerine.io espone una porta MCP pubblica", card)
    assert not sections._item_present("versione 1.4.2 su PyPI", "versione 1.3.0 su PyPI")


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


# ─── write-to-serve latency ─────────────────────────────────────────────────

def test_write_to_serve_latency_is_measured(cases, monkeypatch):
    class Slow(Fake):
        """Serves a just-written value only from the second ask (async index)."""
        def __init__(self):
            super().__init__(answer={"summary": "x"})
            self.asks = 0
        def door_text(self, q, door):
            self.asks += 1
            if self.asks >= 2 and self.working:
                vs = list(self.working.values())
                return "\n".join(vs), {"summary": "\n".join(vs), "working": [{"key": k[1], "value": v} for k, v in self.working.items()]}
            return "nothing yet", {"summary": "nothing yet", "working": []}
    _use(Slow())
    monkeypatch.setattr(CFG, "write_to_serve_max_s", 5)
    monkeypatch.setattr(CFG, "write_to_serve_samples", 3)
    monkeypatch.setattr(sections.time, "sleep", lambda s: None)
    s = sections.live_state()
    served = next(c for c in s["cases"] if c["case"].startswith("the canary just written"))
    assert served["status"] == "PASS" and "write-to-serve" in served["note"]
    assert s["measures"]["write_to_serve_ms"] is not None
    assert s["measures"]["write_to_serve_samples"] == 3
    assert s["measures"]["write_to_serve_p50_ms"] is not None and s["measures"]["write_to_serve_p95_ms"] is not None
    over = next(c for c in s["cases"] if c["case"].startswith("after overwriting"))
    assert over["status"] == "PASS" and s["measures"]["stale_reads_after_overwrite"] == 0


def test_out_of_order_visibility_is_a_fail(cases, monkeypatch):
    class Reordering(Fake):
        """Serves writes with a lag, so the FIRST of two quick writes shows up
        after the second was already visible (an async index that applies
        writes out of order)."""
        def __init__(self):
            super().__init__(answer={"summary": "x"})
            self.log: list[str] = []
            self.asks = 0
        def working_write(self, s, k, v, ttl):
            self.log.append(v)
            return super().working_write(s, k, v, ttl)
        def door_text(self, q, door):
            seq = [v for v in self.log if "sequenza" in v]
            if len(seq) == 2:
                self.asks += 1   # polls of the repeated-writes test only
                # poll 1: only the second; poll 2: both (the first lands late); then the second only
                vals = [seq[1]] if self.asks == 1 else ([seq[1], seq[0]] if self.asks == 2 else [seq[1]])
            else:
                vals = list(self.working.values())
            return "\n".join(vals), {"summary": "\n".join(vals), "working": [{"key": "k", "value": v} for v in vals]}
    _use(Reordering())
    monkeypatch.setattr(CFG, "write_to_serve_max_s", 5)
    monkeypatch.setattr(CFG, "write_to_serve_samples", 1)
    monkeypatch.setattr(sections.time, "sleep", lambda s: None)
    s = sections.live_state()
    rep = next(c for c in s["cases"] if c["case"].startswith("two writes in quick succession"))
    assert rep["status"] == "FAIL" and "after the second was already visible" in rep["note"]
    assert s["measures"]["out_of_order_reads"] >= 1
    tl = rep["timeline"]   # a failed case carries the timeline: both writes, then every poll
    assert [e["event"] for e in tl[:2]] == ["first write", "second write"]
    assert any(e["event"] == "poll" and e["first"] and e["second"] for e in tl)


def test_stale_read_after_overwrite_is_a_fail(cases, monkeypatch):
    class Sticky(Fake):
        """Serves the first value ever written to a key, forever (a cache
        that never invalidates): the overwrite is invisible."""
        def __init__(self):
            super().__init__(answer={"summary": "x"})
            self.first: dict = {}
        def working_write(self, s, k, v, ttl):
            self.first.setdefault((s, k), v)
            return super().working_write(s, k, v, ttl)
        def door_text(self, q, door):
            vs = list(self.first.values())
            return "\n".join(vs), {"summary": "\n".join(vs), "working": [{"key": k[1], "value": v} for k, v in self.first.items()]}
    _use(Sticky())
    monkeypatch.setattr(CFG, "write_to_serve_max_s", 0)
    monkeypatch.setattr(CFG, "write_to_serve_samples", 1)
    monkeypatch.setattr(sections.time, "sleep", lambda s: None)
    s = sections.live_state()
    over = next(c for c in s["cases"] if c["case"].startswith("after overwriting"))
    assert over["status"] == "FAIL" and "stale read" in over["note"]
    assert s["measures"]["stale_reads_after_overwrite"] >= 1


def test_canary_never_served_is_a_fail_with_the_budget_in_the_note(cases, monkeypatch):
    _use(Fake(answer={"summary": "nothing", "working": []}))
    monkeypatch.setattr(CFG, "write_to_serve_max_s", 0)
    s = sections.live_state()
    served = next(c for c in s["cases"] if c["case"].startswith("the canary just written"))
    assert served["status"] == "FAIL" and "not served within" in served["note"]


# ─── stale values delivered next to the current one ────────────────────────

def test_stale_value_beside_the_current_one_is_a_fail(cases):
    (cases / "questions.json").write_text(json.dumps([
        {"question": "porta?", "expected": [["8766"]], "forbidden": [["8010"]], "validated": True}]), encoding="utf-8")
    _use(Fake(answer={"summary": "La porta era 8010, ora e' 8766."}))
    s = sections.door()
    c = s["cases"][0]
    assert c["status"] == "FAIL" and c["stale"] and "STALE" in c["note"]
    assert s["measures"]["stale_values_delivered"] == 1
    _use(Fake(answer={"summary": "La porta e' 8766."}))
    assert sections.door()["cases"][0]["status"] == "PASS"


# ─── duplicate chunks: budget spent twice ───────────────────────────────────

def test_duplicate_chunks_counts_repeated_lines():
    a = "  ✦ Il Brain ascolta sulla porta 8766 e parte prima dei client."
    b = "  · il  brain ascolta sulla porta 8766 e parte prima dei client."  # same after normalising
    text = "\n".join([a, "  ✦ un'altra riga abbastanza lunga da contare come pezzo di testo", b, "corta"])
    assert sections.duplicate_chunks(text) == 1
    assert sections.duplicate_chunks("una sola riga lunga abbastanza da essere contata una volta") == 0


def test_door_reports_duplicates(cases):
    line = "La porta 8766 e' quella del Brain, e questa riga si ripete identica due volte."
    _use(Fake(answer={"summary": line + "\n" + line}))
    s = sections.door()
    assert s["cases"][0]["duplicates"] == 1 and s["measures"]["duplicate_chunks_total"] == 1


# ─── margin and pressure ────────────────────────────────────────────────────

def test_door_margin_is_measured_against_the_budget_not_the_text(cases):
    # 100 x + " porta 8766" → the answer ends at char 111; the door cuts at 2400,
    # so the room left is 2400 - 111, whatever the length of the text that came back
    _use(Fake(answer={"summary": "x" * 100 + " porta 8766 " + "y" * 50}))
    s = sections.door()
    c = s["cases"][0]
    assert c["status"] == "PASS" and c["margin"] == 2400 - 111
    assert s["measures"]["min_margin_chars"] == 2400 - 111
    assert s["measures"]["passes_within_300_chars_of_the_edge"] == 0


def test_short_answer_has_plenty_of_margin(cases):
    _use(Fake(answer={"summary": "porta 8766"}))
    c = sections.door()["cases"][0]
    assert c["margin"] == 2400 - 10  # the reviewer's case: 10 chars, budget 2400 → 2390 of room


def test_door_without_a_cut_has_no_margin(cases):
    class NoCut(Fake):
        def door_cut(self, door): return None
    _use(NoCut(answer={"summary": "porta 8766"}))
    s = sections.door()
    assert s["cases"][0]["margin"] is None and s["measures"]["min_margin_chars"] is None


def test_pressure_is_part_of_the_setup_fingerprint():
    base = {"adapter": "x:A", "door": "voice", "cases_hash": "h", "sections": ["door"], "pressure": 0}
    assert report.fingerprint(base) != report.fingerprint({**base, "pressure": 1200})


def test_synthetic_chat_door_loses_answers_under_pressure(monkeypatch):
    from examples.synthetic import SyntheticAdapter
    ada = SyntheticAdapter()
    monkeypatch.setattr(CFG, "pressure", 0)
    text0, _ = ada.door_text("When do backups run?", "chat")
    monkeypatch.setattr(CFG, "pressure", 1450)
    text1, _ = ada.door_text("When do backups run?", "chat")
    assert "03:00" in text0 and "03:00" not in text1  # the same answer falls off the cut on a bad day


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


# ─── the reproducible example gives the committed reference score ──────────

def test_synthetic_example_matches_reference(tmp_path, monkeypatch):
    """examples/synthetic_report/reference.json is what anyone gets by running
    the synthetic memory: same total, same PASS/FAIL/ERROR/SKIP counts."""
    from pathlib import Path
    from adebench.__main__ import main
    root = Path(__file__).resolve().parents[1]
    reference = json.loads((root / "examples" / "synthetic_report" / "reference.json").read_text(encoding="utf-8"))
    monkeypatch.setattr(adapter, "_current", None)
    monkeypatch.chdir(root)
    assert main(["--adapter", "examples.synthetic:SyntheticAdapter",
                 "--cases", "examples/synthetic_data/cases", "--repo", "examples/synthetic_data/repo",
                 "--sandbox-test", "examples/synthetic_data/sandbox_test.py",
                 "--census", "examples/synthetic_data/census.json", "--pressure-profile",
                 "--history", str(tmp_path)]) == 0
    run = json.loads(next(tmp_path.glob("*.json")).read_text(encoding="utf-8"))
    assert run["total"] == reference["total"]
    assert run["counts"] == reference["counts"]
    assert [(s["name"], s["score"]) for s in run["sections"]] == \
           [(s["name"], s["score"]) for s in reference["sections"]]


# ─── the HTTP client never returns an error body as an answer ───────────────

class _Server500(BaseHTTPRequestHandler):
    def _answer(self):
        # drain the request body first: answering before the client has
        # finished sending makes Windows abort the connection (WinError 10053)
        n = int(self.headers.get("Content-Length") or 0)
        if n:
            self.rfile.read(n)
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


# ─── callwitness census: measured pressure levels ───────────────────────────

from pathlib import Path  # noqa: E402
from adebench import census as cw  # noqa: E402


def _census_doc(**over):
    d = {"schema": "callwitness.baseline.v1", "generated_at": "2026-09-13T04:03:45Z",
         "sample": {"servers_started": 4, "servers_called": 3, "calls": 10},
         "returned_bytes_all": [88, 100, 200, 264, 300, 900, 2000, 9000, 25039, 701216],
         "servers": [{"server": "a", "declared_bytes": 1000, "returned_bytes": {"n": 5},
                      "returned_over_declared": {"p50": 0.3, "max": 2.5}},
                     {"server": "b", "declared_bytes": 500, "returned_bytes": {"n": 5},
                      "returned_over_declared": {"p50": 1.0, "max": 905.96}}]}
    d.update(over)
    return d


def test_census_levels_are_the_percentiles_of_a_tool_response():
    c = cw.parse(_census_doc(), spec=cw.PUBLISHED_URL)
    assert c.levels() == {"median": 900, "p95": 701216, "max": 701216} or c.levels()["median"] in (300, 900)
    assert c.n == 10 and c.servers_called == 3 and c.declared_known


def test_census_origin_is_read_or_inferred_never_assumed():
    assert cw.parse(_census_doc(), spec=cw.PUBLISHED_URL).origin == "census"
    assert cw.parse(_census_doc(), spec=cw.PUBLISHED_URL).origin_declared is False
    assert cw.parse(_census_doc(), spec="/tmp/mine.json").origin == "unknown"
    assert cw.parse(_census_doc(origin="local"), spec="/tmp/mine.json").origin == "local"
    assert cw.parse(_census_doc(origin="local"), spec=cw.PUBLISHED_URL).origin == "local"  # the field wins


def test_census_rejects_other_schemas():
    with pytest.raises(ValueError):
        cw.parse({"schema": "something.else.v1"})


def test_pressure_names_resolve_against_the_census_only():
    c = cw.parse(_census_doc(), spec=cw.PUBLISHED_URL)
    assert cw.resolve_pressure("1200", None) == 1200
    assert cw.resolve_pressure("max", c) == 701216
    assert cw.resolve_pressure("median", c) == c.levels()["median"]
    with pytest.raises(ValueError):
        cw.resolve_pressure("p95", None)
    with pytest.raises(ValueError):
        cw.resolve_pressure("worst", c)


def test_local_census_without_declared_sizes_has_no_ratio_reference(cases):
    doc = _census_doc(origin="local", servers=[{"server": "tool_1", "declared_bytes": 0, "returned_bytes": {"n": 5}}])
    c = cw.parse(doc, spec="mine.json")
    assert not c.declared_known
    adapter.use(Fake(answer={"summary": "x"}))
    s = sections.census_section(c)
    assert s["weight"] == 0 and s["measures"]["declared_vs_returned"] is None
    assert any("declared_bytes = 0" in w for w in s["warnings"])
    assert "census_returned_over_declared_top" not in s["measures"]


def test_declared_vs_returned_needs_the_optional_method(cases):
    c = cw.parse(_census_doc(), spec=cw.PUBLISHED_URL)

    class WithDeclared(Fake):
        def measured_doors(self): return ["/ask"]
        def traces(self): return [{"door": "/ask", "ms": 1, "chars": 3000, "http": 200}]
        def declared_bytes(self): return 1500
    adapter.use(WithDeclared(answer={"summary": "x"}))
    s = sections.census_section(c)
    assert s["measures"]["declared_vs_returned"]["returned_over_declared"] == 2.0
    assert s["measures"]["this_door_rank_in_census"] == 0.7  # 7 of 10 census calls are smaller
    assert s["measures"]["census_returned_over_declared_top"][0]["server"] == "b"


def test_pressure_profile_reports_passes_per_level_and_restores_pressure(cases, monkeypatch):
    from examples.synthetic import SyntheticAdapter
    c = cw.parse(_census_doc(returned_bytes_all=[100, 200, 300, 1450, 1450, 1450, 1450, 1450, 1450, 5000]),
                 spec=cw.PUBLISHED_URL)
    monkeypatch.setattr(CFG, "door", "chat")
    monkeypatch.setattr(CFG, "pressure", 0)
    root = Path(__file__).resolve().parents[1]
    monkeypatch.setattr(CFG, "cases", root / "examples" / "synthetic_data" / "cases")
    adapter.use(SyntheticAdapter())
    s = sections.pressure_profile(c)
    assert CFG.pressure == 0
    assert s["measures"]["median"]["pressure_chars"] == 1450
    assert s["measures"]["median"]["PASS"] < sections.door()["counts"]["PASS"]  # pressure costs answers
    assert s["measures"]["max"]["PASS"] == 0  # 5,000 bytes alone exceed the 1,500 chat cut
    assert any("exceeds this door's budget" in w for w in s["warnings"])


def test_cli_pressure_level_needs_a_census(cases, monkeypatch):
    from adebench.__main__ import main
    monkeypatch.setattr(adapter, "_current", None)
    monkeypatch.setattr(CFG, "census", None)  # a previous CLI run in this process may have set one
    monkeypatch.setattr(CFG, "pressure_profile", False)
    assert main(["--adapter", "tests.test_adebench:Fake", "--cases", str(cases), "--no-report",
                 "--sections", "door", "--pressure", "p95"]) == 2


def test_no_live_state_key_is_skip_not_fail(cases, monkeypatch):
    _use(Fake(answer={"summary": "x", "working": []}))
    monkeypatch.setattr(CFG, "write_to_serve_max_s", 0)
    monkeypatch.setattr(CFG, "live_state_key", "")
    s = sections.live_state()
    fresh = next(c for c in s["cases"] if "freshness" in c["case"])
    assert fresh["status"] == "SKIP"


# ─── the gbrain adapter honours the contract (no gbrain needed) ─────────────

def test_gbrain_adapter_honours_the_contract(monkeypatch):
    monkeypatch.setenv("ADEBENCH_GBRAIN_BIN", "gbrain-not-installed-anywhere")
    g = adapter.load("adebench.gbrain:GbrainAdapter")
    assert not [m for m in adapter.required_methods() if not callable(getattr(g, m, None))]
    assert g.health() is False          # a missing binary is "not alive", never an exception
    assert g.doors() == ["search", "pack"] and g.door_cut("pack") == 2400 and g.door_cut("search") is None
    assert g.declared_bytes() is None


# ─── two runs side by side ──────────────────────────────────────────────────

def test_compare_scores_only_the_sections_both_measured():
    from adebench.compare import compare
    def run(door, sections, cases_hash="h"):
        return {"total": sum(s * w for _, s, w in sections if s is not None), "measured_weight": sum(w for _, s, w in sections if s is not None),
                "config": {"door": door, "cases_hash": cases_hash, "pressure": 0},
                "sections": [{"name": n, "weight": w, "score": s, "counts": {"PASS": 1}} for n, s, w in sections]}
    a = run("voice", [("door", 0.8, 25), ("updates", 1.0, 10), ("graph", 0.5, 10)])
    b = run("pack", [("door", 0.6, 25), ("updates", None, 10), ("graph", 1.0, 10)])
    text, s = compare(a, b, "brain", "gbrain")
    assert s["common_weight"] == 35 and s["brain"] == 25.0 and s["gbrain"] == 25.0
    assert "not measured" in text and "excluded from the common score" in text
    _, s2 = compare(a, run("pack", [("door", 0.6, 25)], cases_hash="other"), "a", "b")
    assert s2["same_cases"] is False
