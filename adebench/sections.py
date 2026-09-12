"""The adebench sections. Each returns a dict:

    {"name", "weight", "score" (0..1 or None = not measured),
     "cases": [{"case", "status": PASS|FAIL|ERROR|SKIP, "ok", "note"}],
     "counts": {...}, "measures": {...}, "warnings": [...]}

A case is PASS or FAIL when the check ran and had evidence; ERROR when the
memory system failed to answer (an HTTP error, an exception, an empty
response) — it counts as a failure, never as a pass; SKIP when this memory
has no such feature or no data for the check — it is excluded from the score
and shown as missing coverage. A section with no PASS/FAIL/ERROR case is
"not measured": its weight leaves the denominator instead of scoring 0 or 1.

Sections A-H count toward the score; 'health' and 'doors' (latency and noise
per door) are report-only. The sections know nothing about endpoints or
tables: they talk to the adapter (adebench/adapter.py).
"""
from __future__ import annotations

import json
import os
import random
import re
import statistics
import subprocess
import sys
import uuid
from typing import Callable

from adebench.adapter import current
from adebench.config import CFG

WEIGHTS = {
    "door": 25, "cards": 15, "updates": 10, "time": 10,
    "live_state": 10, "abstention": 10, "file_search": 10, "graph": 10,
}
STATUSES = ("PASS", "FAIL", "ERROR", "SKIP")


def _case(case: str, ok: bool | None, note: str = "", status: str | None = None, **extra) -> dict:
    """ok=True → PASS, ok=False → FAIL, ok=None → SKIP; status overrides."""
    if status is None:
        status = "SKIP" if ok is None else ("PASS" if ok else "FAIL")
    d = {"case": case, "status": status, "ok": status == "PASS", "note": note}
    d.update(extra)
    return d


def _try(case: str, fn: Callable[[], dict]) -> dict:
    """Run one check; any exception becomes an ERROR case, never a PASS."""
    try:
        return fn()
    except Exception as e:  # noqa: BLE001
        return _case(case, False, f"{type(e).__name__}: {str(e)[:160]}", status="ERROR")


def _read(name: str, fn: Callable, default, cases: list[dict]):
    """Read a value from the adapter. On failure the value is the default AND
    an ERROR case is appended: a read that blew up must never look like a
    memory that simply has no such data (that would become a SKIP)."""
    try:
        return fn()
    except Exception as e:  # noqa: BLE001
        cases.append(_case(name, False, f"{type(e).__name__}: {str(e)[:160]}", status="ERROR"))
        return default


def _section(name: str, cases: list[dict], measures: dict | None = None,
             warnings: list[str] | None = None, score: float | None = None) -> dict:
    measured = [c for c in cases if c["status"] != "SKIP"]
    if score is None:
        score = (sum(1 for c in measured if c["status"] == "PASS") / len(measured)) if measured else None
    counts = {s: sum(1 for c in cases if c["status"] == s) for s in STATUSES}
    warnings = list(warnings or [])
    if score is None and not any("not measured" in w for w in warnings):
        warnings.append("section not measured: no case with evidence (all SKIP or no cases)")
    return {"name": name, "weight": WEIGHTS.get(name, 0),
            "score": None if score is None else round(score, 4),
            "cases": cases, "counts": counts, "measures": measures or {}, "warnings": warnings}


def present(text: str, group: list[str]) -> str | None:
    """The first alternative of the group present in the text as a whole
    token: '8766' does not match '18766', '0.2.4' does not match '10.2.4'.
    Boundaries are enforced only where the alternative starts/ends with an
    alphanumeric character, so a path still matches inside a longer path.
    A trailing '*' declares a prefix: 'anonimizz*' matches 'anonimizza'."""
    for alt in group:
        prefix = alt.endswith("*")
        core = alt[:-1] if prefix else alt
        if not core:
            continue
        pat = re.escape(core)
        if core[0].isalnum():
            pat = r"(?<![0-9A-Za-z])" + pat
        if core[-1].isalnum() and not prefix:
            pat = pat + r"(?![0-9A-Za-z])"
        if re.search(pat, text, re.IGNORECASE):
            return alt
    return None


def _load(name: str):
    return json.loads((CFG.cases / name).read_text(encoding="utf-8"))


# ─── A. The door ─────────────────────────────────────────────────────────────

def door() -> dict:
    """What the client really receives through the configured door. A
    question passes when every group of expected words is in that text —
    not in the raw hits."""
    ada = current()
    questions = _load("questions.json")
    cases, positions, lengths, semantic_seen = [], [], [], []

    def _one(q: dict) -> dict:
        text, r = ada.door_text(q["question"], CFG.door)
        summary = r.get("summary") or ""
        if not text.strip() and not summary.strip():
            return _case(q["question"], False, "empty answer from the door", status="ERROR",
                         validated=q.get("validated", False))
        missing = [g for g in q["expected"] if not present(text, g)]
        found = [present(text, g) for g in q["expected"] if present(text, g)]
        pos = min((text.lower().find(t.lower()) for t in found), default=-1)
        card_ok = True
        if q.get("entity"):
            keys = [str(c.get("key", "")) for c in r.get("cards", [])]
            card_ok = any(k.endswith(q["entity"]) for k in keys)
        whole_ok = not [g for g in q["expected"] if not present(summary, g)]
        note = ""
        if missing:
            note = "missing " + " | ".join("/".join(g) for g in missing)
            if whole_ok:
                note += " (present in the uncut answer: lost through this door)"
        if not card_ok:
            note += f" card {q['entity']} absent"
        lengths.append(len(text))
        if pos >= 0:
            positions.append(pos)
        semantic_seen.extend(r.get("semantic", []))
        return _case(q["question"], not missing and card_ok, note.strip(), position=pos,
                     chars=len(text), ms=round(r.get("_ms", 0)), validated=q.get("validated", False))

    for q in questions:
        cases.append(_try(q["question"], lambda q=q: _one(q)))
    measures = {
        "door": CFG.door,
        "questions": len(questions),
        "validated": sum(1 for q in questions if q.get("validated")),
        "mean_answer_position": round(statistics.mean(positions)) if positions else None,
        "mean_door_text_chars": round(statistics.mean(lengths)) if lengths else None,
    }
    warnings = []
    if measures["validated"] < len(questions):
        warnings.append(f"{len(questions) - measures['validated']} golden-set questions not yet "
                        "validated ('validated' field in questions.json; see --validation)")
    sec = _section("door", cases, measures, warnings)
    sec["_semantic"] = semantic_seen
    return sec


# ─── B. Entity cards, corrections, aliases ───────────────────────────────────

def _mandatory_items(text: str) -> list[str]:
    """'Nella scheda di X non omettere mai: a, b; c' -> ['a', 'b', 'c'].
    The marker is the owner's Italian idiom; 'never omit:' is accepted too."""
    m = re.search(r"(?:non omettere mai|never omit)\s*:\s*(.+)$", text, re.IGNORECASE | re.DOTALL)
    if not m:
        return []
    return [v.strip(" .;") for v in re.split(r"[,;]\s*", m.group(1)) if len(v.strip()) > 3]


def _item_present(item: str, card: str) -> bool:
    words = [w for w in re.findall(r"[\w./@-]{4,}", item.lower())]
    if not words:
        return True
    inside = sum(1 for w in words if w in card.lower())
    return inside / len(words) >= 0.6


def cards() -> dict:
    """All derived from the data: every card exists, is dated, fits the
    limit and contains the mandatory items of its corrections; every alias
    leads to the canonical card."""
    ada = current()
    rows = ada.cards()
    if not rows:
        return _section("cards", [_case("entity cards", None, "this memory has none")],
                        {}, ["section not measured: no entity cards in this memory"])
    corrections = ada.corrections()
    cases = []
    for c in rows:
        ent, text = c["entity"], c["content"]
        cases.append(_case(f"card {ent} exists and is dated", bool(text) and bool(c.get("date"))))
        cases.append(_case(f"card {ent} within {CFG.max_card} characters", len(text) <= CFG.max_card,
                           f"{len(text)} characters"))
        for corr in corrections:
            if corr["entity"] != ent:
                continue
            for item in _mandatory_items(corr["content"]):
                cases.append(_case(f"card {ent} contains «{item[:60]}»", _item_present(item, text)))
    aliases = ada.aliases()
    with_card = {c["entity"] for c in rows}
    random.seed(11)
    candidates = [a for a in aliases if a["canonical"] in with_card and a["alias"] != a["canonical"]]
    for a in random.sample(candidates, min(CFG.alias_sample, len(candidates))):
        name = f"alias '{a['alias']}' leads to card {a['canonical']}"

        def _alias(a=a, name=name) -> dict:
            r = ada.ask(f"Cos'e' {a['alias'].replace('_', ' ')}?")
            keys = [str(c.get("key", "")) for c in r.get("cards", [])]
            return _case(name, any(k.endswith(a["canonical"]) for k in keys), f"cards seen: {keys}")
        cases.append(_try(name, _alias))
    measures = {"cards": len(rows), "corrections": len(corrections), "aliases": len(aliases),
                "aliases_tried": min(CFG.alias_sample, len(candidates))}
    return _section("cards", cases, measures)


# ─── C. Fact updates ─────────────────────────────────────────────────────────

def updates(with_sandbox: bool = True) -> dict:
    """The MECHANISM, exercised by a sandbox test script (CFG.sandbox_test)
    that prints one PASS/FAIL line per check and "N/M passed" (or the
    Italian "N/M passati"). The historical trace of updates goes in the
    measures but does not score: an update that happened once does not prove
    the mechanism works today."""
    try:
        measures = dict(current().update_trace() or {})
    except Exception as e:  # noqa: BLE001
        measures = {"trace_error": f"{type(e).__name__}: {str(e)[:120]}"}
    n_sup = measures.get("superseded_live", 0) or 0
    n_upd = measures.get("relation_updates", 0) or 0
    v2 = measures.get("v2_share")
    cases, warnings = [], []
    if with_sandbox and CFG.sandbox_test:
        try:
            p = subprocess.run([sys.executable, str(CFG.sandbox_test)], cwd=str(CFG.sandbox_test.parent.parent),
                               capture_output=True, text=True, encoding="utf-8", errors="replace",
                               timeout=600, env={**os.environ, "PYTHONIOENCODING": "utf-8"})
            m = re.search(r"(\d+)/(\d+) (?:passed|passati)", p.stdout)
            for line in p.stdout.splitlines():
                line = re.sub(r"\x1b\[[0-9;]*m", "", line)
                if line.strip().startswith(("PASS", "FAIL")):
                    cases.append(_case("sandbox: " + line.strip()[4:].strip().split("  —")[0],
                                       line.strip().startswith("PASS")))
            measures["sandbox_test"] = f"{m.group(1)}/{m.group(2)}" if m else "no result"
            if not m or p.returncode not in (0, 1):
                cases.append(_case("sandbox test of the update mechanism", False,
                                   (p.stderr or p.stdout)[-300:], status="ERROR"))
        except Exception as e:  # noqa: BLE001
            cases.append(_case("sandbox test of the update mechanism", False, str(e)[:200], status="ERROR"))
    else:
        cases.append(_case("update mechanism (needs --sandbox-test)", None,
                           "without the sandbox test the historical trace does not score"))
        warnings.append("section not measured: no sandbox test of the mechanism (--sandbox-test); "
                        f"historical trace: superseded={n_sup}, updates={n_upd}")
    if n_sup == 0 and n_upd == 0 and "trace_error" not in measures:
        warnings.append("no trace of updates in live memory: the dedup has not worked yet or found no pairs")
    if v2 is not None and v2 < 0.5:
        warnings.append(f"only {v2:.0%} of live memory went through the v2 pipeline")
    return _section("updates", cases, measures, warnings)


# ─── D. Age and time ─────────────────────────────────────────────────────────

def time_section(semantic_seen: list[dict] | None = None) -> dict:
    ada = current()
    cases = []
    sem = semantic_seen or []
    tagged = sum(1 for s in sem if str(s.get("content", "")).startswith("[dal "))
    tag_share = (tagged / len(sem)) if sem else None
    cases.append(_case(f"semantic memories carry their age ({tagged}/{len(sem)})",
                       None if tag_share is None else tag_share >= 0.95,
                       f"{tag_share:.0%}" if tag_share is not None else "no semantic memory seen"))
    d, n = _read("reading the share of dated facts", lambda: ada.event_date_share(), (0, 0), cases)
    days = _read("reading the recent days of the episodic memory", lambda: ada.recent_days(3), None, cases)
    if days is None:      # the read failed: already an ERROR case
        days = []
    elif not days:        # the read worked and there is nothing: SKIP
        cases.append(_case("episodic day filter", None, "no episodes"))
    for day in days:
        def _day(day=day) -> dict:
            eps = ada.episodes_of_day(day, 10)
            ok = bool(eps) and all(str(e.get("created_at", "")).startswith(day) for e in eps)
            return _case(f"day filter {day} returns only that day's episodes", ok, f"{len(eps)} episodes")
        cases.append(_try(f"day filter {day}", _day))
    n_signed = _read("reading the signed episodes", lambda: ada.signed_episodes("[pc2]"), None, cases)
    if n_signed:
        def _signed() -> dict:
            r = ada.ask("cosa ha fatto il pc2?")
            eps = r.get("episodic", [])
            return _case("«cosa ha fatto il pc2?» finds the episodes signed [pc2]",
                         any("[pc2" in str(e.get("input_summary", "")) for e in eps),
                         f"{len(eps)} episodes in the answer")
        cases.append(_try("signed episodes [pc2]", _signed))
    elif n_signed == 0:
        cases.append(_case("episodes signed by another machine", None, "none in this memory"))
    measures = {"share_of_memories_with_age": None if tag_share is None else round(tag_share, 3),
                "facts_with_event_date": f"{d}/{n}", "days_tried": days, "signed_episodes_pc2": n_signed}
    warnings = []
    if n and d / n < 0.5:
        warnings.append(f"only {d} facts out of {n} carry the event date: for the others the age "
                        "the model hears is the derivation date, not the fact's")
    return _section("time", cases, measures, warnings)


# ─── E. Live state (working memory) ──────────────────────────────────────────

def live_state() -> dict:
    ada = current()
    cases = []
    token = uuid.uuid4().hex[:10]
    value = f"canarino adebench {token}: la parola d'ordine di oggi e' girasole"
    try:
        cases.append(_try("canary write", lambda: _case(
            "canary written to working memory", ada.working_write("adebench", "adebench_canary", value, 1))))

        def _find() -> list[dict]:
            text, r = ada.door_text(f"parola d'ordine canarino adebench {token}", CFG.door)
            wm = r.get("working", [])
            return [_case("the canary just written is found through the retrieval door",
                          any(token in str(e.get("value", "")) for e in wm)),
                    _case(f"…and reaches the text of door '{CFG.door}'", token in text)]
        try:
            cases.extend(_find())
        except Exception as e:  # noqa: BLE001
            cases.append(_case("canary retrieval", False, f"{type(e).__name__}: {str(e)[:120]}", status="ERROR"))
    finally:
        try:
            ada.working_clear("adebench")
        except Exception:  # noqa: BLE001
            pass
    cases.append(_try("cleanup", lambda: _case(
        "cleanup: adebench session empty at the end of the run", not ada.working_read("adebench", "adebench_canary"))))
    before = len(cases)
    age = _read("reading the live-state age", lambda: ada.working_age_minutes(CFG.live_state_session, CFG.live_state_key), None, cases)
    if len(cases) == before:  # the read succeeded: an absent key is a FAIL, not an error
        cases.append(_case(f"{CFG.live_state_key} refreshed less than {CFG.live_state_max_minutes} minutes ago",
                           age is not None and age <= CFG.live_state_max_minutes,
                           f"{age:.0f} min" if age is not None else "key absent"))
    return _section("live_state", cases, {"live_state_age_min": None if age is None else round(age)})


# ─── F. Abstention ───────────────────────────────────────────────────────────

def abstention() -> dict:
    """Invented entities: no card, episodes marked as 'no direct match',
    semantic reduced to near-by-meaning hits only (or nothing). This checks
    what retrieval hands to the model, not the model's final sentence."""
    ada = current()
    questions = _load("abstention.json")
    cases = []
    for q in questions:
        def _one(q=q) -> dict:
            r = ada.ask(q)
            if not r.get("summary", "").strip() and not any(k in r for k in ("cards", "semantic", "episodic")):
                return _case(q, False, "empty answer: no evidence of abstention", status="ERROR")
            ok_card = not r.get("cards")
            eps = r.get("episodic", [])
            ok_eps = (not eps) or all(e.get("_fallback") for e in eps)
            sem = r.get("semantic", [])
            ok_sem = len(sem) <= 2 and all(str(s.get("source", "")).startswith("semantic_vec") for s in sem)
            fraction = (ok_card + ok_eps + ok_sem) / 3
            note = []
            if not ok_card:
                note.append("produced an entity card")
            if not ok_eps:
                note.append("episodes presented as direct matches")
            if not ok_sem:
                note.append(f"{len(sem)} keyword facts for something that does not exist")
            if r.get("unknown_terms"):
                note.append(f"flagged unknown: {r['unknown_terms']}")
            return _case(q, fraction == 1.0, "; ".join(note), fraction=fraction)
        cases.append(_try(q, _one))
    measured = [c for c in cases if c["status"] != "SKIP"]
    # partial credit per question (each of the three checks); errors count 0
    score = (sum(c.get("fraction", 0.0) for c in measured) / len(measured)) if measured else None
    return _section("abstention", cases, {"questions": len(questions)}, score=score)


# ─── G. File search ──────────────────────────────────────────────────────────

def file_search() -> dict:
    """Real functions sampled from the repo: the grep-replacement search
    must put the right file in the top 5."""
    if not CFG.repo:
        return _section("file_search", [_case("file search", None, "no repo configured (--repo)")],
                        {}, ["section not measured: no repo configured (--repo)"])
    ada = current()
    functions = []
    for p in sorted(CFG.repo.rglob("*.py")):
        parts = {x.lower() for x in p.parts}
        if parts & {"bcks", "backups", "__pycache__", "venv", ".venv", "venvs", "node_modules", "site-packages"}:
            continue
        if ".bak" in p.name or ".bck" in p.name:
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:  # noqa: BLE001
            continue
        for m in re.finditer(r"^def ([a-z][a-z0-9_]{11,})\(", text, re.M):
            functions.append((m.group(1), p.relative_to(CFG.repo).as_posix()))
    random.seed(23)
    sample = random.sample(functions, min(CFG.file_sample, len(functions)))
    cases = []
    for name, rel in sample:
        def _one(name=name, rel=rel) -> dict:
            keys = [k.replace("\\", "/") for k in ada.file_search(name, 5)]
            ok = any(k.endswith(rel) for k in keys)
            return _case(f"{name} → {rel}", ok, "" if ok else f"top5: {[k[-45:] for k in keys]}")
        cases.append(_try(f"{name} → {rel}", _one))
    if not cases:
        cases.append(_case("file search", None, "no function to sample in the repo"))
    return _section("file_search", cases, {"indexable_functions": len(functions), "tried": len(sample)})


# ─── H. Graph ────────────────────────────────────────────────────────────────

def graph() -> dict:
    ada = current()
    cases = []
    read_cards = _read("reading the entity cards", lambda: ada.cards(), None, cases)
    entities = [c["entity"] for c in (read_cards or [])]
    if read_cards is not None and not entities:
        cases.append(_case("entities with a card in the graph", None, "no entity with a card"))
    for ent in entities:
        cases.append(_try(f"{ent}: edges in the graph", lambda ent=ent: (
            lambda n: _case(f"{ent}: edges in the graph", n > 0, f"{n} edges"))(ada.graph_edges(ent))))

    def _orphans() -> dict:
        orphans, total = ada.graph_orphans()
        if total == 0:
            return _case("orphan fact nodes = 0", None, "the graph has no fact nodes: nothing to check")
        return _case("orphan fact nodes = 0", orphans == 0, f"{orphans} orphans out of {total}")
    cases.append(_try("orphan fact nodes", _orphans))
    measures = dict(_read("reading the graph counts", lambda: ada.graph_counts(), {}, cases) or {})
    orf = next((c for c in cases if c["case"].startswith("orphan fact nodes")), None)
    measures["orphan_fact_nodes"] = orf["note"] if orf else None
    return _section("graph", cases, measures)


# ─── Report-only: health and doors ───────────────────────────────────────────

def health() -> dict:
    try:
        m, warnings = current().health_report()
    except Exception as e:  # noqa: BLE001
        m, warnings = {}, [f"health not available: {type(e).__name__}: {str(e)[:120]}"]
    return {"name": "health", "weight": 0, "score": None, "cases": [], "counts": {}, "measures": m, "warnings": warnings}


def doors() -> dict:
    """Latency and noise per door. The retrieval door was already called by
    the sections; the adapter probes the other doors on the golden questions."""
    ada = current()
    questions = _load("questions.json")
    try:
        ada.probe_doors([q["question"] for q in questions[:10]])
    except Exception:  # noqa: BLE001
        pass
    measured = set(ada.measured_doors())
    per_door: dict = {}
    for t in ada.traces():
        p = t["door"]
        if p not in measured:
            continue
        per_door.setdefault(p, {"ms": [], "chars": [], "errors": 0})
        per_door[p]["ms"].append(t["ms"])
        per_door[p]["chars"].append(t["chars"])
        if t.get("http", 200) != 200:
            per_door[p]["errors"] += 1

    def _p(v, q):
        if not v:
            return None
        v = sorted(v)
        return round(v[min(len(v) - 1, int(q * len(v)))])
    m = {}
    for p, v in per_door.items():
        m[p] = {"calls": len(v["ms"]), "http_errors": v["errors"], "ms_p50": _p(v["ms"], 0.5),
                "ms_p95": _p(v["ms"], 0.95), "mean_chars": round(statistics.mean(v["chars"])) if v["chars"] else None}
    warnings = []
    if CFG.door == "voice":
        ask = m.get("/sofia/ask", {})
        if ask.get("mean_chars") and ask["mean_chars"] > CFG.voice_cut * 1.5:
            warnings.append(f"the retrieval door produces {ask['mean_chars']} characters on average: more than "
                            f"one and a half times what the voice model can hear ({CFG.voice_cut})")
    return {"name": "doors", "weight": 0, "score": None, "cases": [], "counts": {}, "measures": m, "warnings": warnings}
