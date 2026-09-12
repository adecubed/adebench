"""One run's report: JSON + markdown in the history folder, with the delta
against the previous COMPARABLE run — same setup fingerprint: adapter, door,
golden set (hashed), sections run, voice-door cut and sources, sandbox test,
repo, weights. Runs are identified by a timestamp with seconds plus a short
hash, so two runs in the same minute never collide."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path

from adebench.config import CFG

STATUSES = ("PASS", "FAIL", "ERROR", "SKIP")

# Everything that changes what a run measures. Two runs are comparable only
# if all of it is equal.
COMPARABILITY_KEYS = ("adapter", "door", "cases_hash", "sections", "voice_cut", "voice_sources",
                      "events_block", "sandbox_test", "repo", "weights", "max_card")


def cases_hash() -> str:
    """Short hash of the golden set, so that a changed question set never
    gets compared with the previous one."""
    h = hashlib.sha1()
    for name in ("questions.json", "abstention.json"):
        p = CFG.cases / name
        if p.exists():
            h.update(name.encode()); h.update(p.read_bytes())
    return h.hexdigest()[:10]


def fingerprint(config: dict) -> str:
    base = {k: config.get(k) for k in COMPARABILITY_KEYS}
    if isinstance(base.get("sections"), list):
        base["sections"] = sorted(base["sections"])
    return hashlib.sha1(json.dumps(base, sort_keys=True, default=str).encode()).hexdigest()[:10]


def total_score(sections: list[dict], weights: dict | None = None) -> tuple[float, int, int, int]:
    """(points, measured weight, weight not run, full-suite weight).
    The full suite is always the denominator of reference: running only
    'door' does not turn 25/25 into a full score. Sections that ran but had
    no evidence are 'not measured'; sections not selected are 'not run'."""
    if weights is None:
        from adebench.sections import WEIGHTS as weights
    total = sum(weights.values())
    points, measured, run = 0.0, 0, 0
    for s in sections:
        if not s.get("weight"):
            continue
        run += s["weight"]
        if s.get("score") is None:
            continue
        measured += s["weight"]
        points += s["score"] * s["weight"]
    return round(points, 1), measured, total - run, total


def counts(sections: list[dict]) -> dict:
    c = {s: 0 for s in STATUSES}
    for s in sections:
        for case in s.get("cases", []):
            st = case.get("status", "FAIL")
            c[st] = c.get(st, 0) + 1
    return c


def _comparable(run: dict, config: dict) -> bool:
    return (run.get("config") or {}).get("fingerprint") == config.get("fingerprint")


def _last_run(config: dict) -> dict | None:
    if not CFG.history.exists():
        return None
    for f in sorted(CFG.history.glob("*.json"), reverse=True):
        try:
            run = json.loads(f.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        if _comparable(run, config):
            return run
    return None


def save(sections: list[dict], config: dict) -> tuple[Path, Path, dict]:
    CFG.history.mkdir(parents=True, exist_ok=True)
    config = dict(config)
    config.setdefault("cases_hash", cases_hash())
    config["fingerprint"] = fingerprint(config)
    previous = _last_run(config)
    when = datetime.now()
    points, measured, not_run, total = total_score(sections, config.get("weights"))
    run = {
        "when": when.isoformat(timespec="seconds"),
        "total": points, "measured_weight": measured, "not_run_weight": not_run, "total_weight": total,
        "counts": counts(sections),
        "config": config,
        "sections": [{k: v for k, v in s.items() if not k.startswith("_")} for s in sections],
    }
    delta = {"total": None, "sections": {}}
    if previous:
        delta["total"] = round(points - previous.get("total", 0), 1)
        prev = {s["name"]: s for s in previous.get("sections", [])}
        for s in sections:
            p = prev.get(s["name"])
            if p and p.get("score") is not None and s.get("score") is not None:
                delta["sections"][s["name"]] = round((s["score"] - p["score"]) * s["weight"], 1)
        delta["against"] = previous.get("when")
    run["delta"] = delta
    stem = f"{when.strftime('%Y%m%d-%H%M%S')}-{config['fingerprint'][:6]}"
    pj = CFG.history / f"{stem}.json"
    pm = CFG.history / f"{stem}.md"
    n = 1
    while pj.exists():
        n += 1
        pj = CFG.history / f"{stem}-{n}.json"
        pm = CFG.history / f"{stem}-{n}.md"
    pj.write_text(json.dumps(run, ensure_ascii=False, indent=1), encoding="utf-8")
    pm.write_text(markdown(run), encoding="utf-8")
    return pj, pm, run


def _fmt_delta(v) -> str:
    if v is None:
        return ""
    return f" ({'+' if v >= 0 else ''}{v})"


def score_line(run: dict) -> str:
    measured, total = run.get("measured_weight", 100), run.get("total_weight", 100)
    not_run = run.get("not_run_weight", 0)
    not_measured = total - measured - not_run
    s = f"{run['total']} / {measured}{_fmt_delta(run['delta'].get('total'))}"
    if measured != total:
        parts = []
        if not_run:
            parts.append(f"{not_run} not run (sections not selected)")
        if not_measured:
            parts.append(f"{not_measured} not measured (no evidence)")
        s += f" — coverage {measured}/{total}: " + ", ".join(parts)
    return s


def markdown(run: dict) -> str:
    c = run.get("counts", {})
    cfg = run.get("config") or {}
    lines = [f"# adebench — {run['when']}", "",
             f"**Score: {score_line(run)}**",
             f"Cases: {c.get('PASS', 0)} PASS · {c.get('FAIL', 0)} FAIL · {c.get('ERROR', 0)} ERROR · {c.get('SKIP', 0)} SKIP",
             f"Adapter `{cfg.get('adapter')}` · door `{cfg.get('door')}` · cases `{cfg.get('cases_hash')}` "
             f"· setup `{cfg.get('fingerprint')}` · sections {', '.join(cfg.get('sections') or [])}"]
    if run["delta"].get("against"):
        lines.append(f"Delta against the comparable run of {run['delta']['against']}.")
    lines += ["", "| Section | Weight | Points | PASS/FAIL/ERROR/SKIP |", "|---|---|---|---|"]
    for s in run["sections"]:
        if not s.get("weight"):
            continue
        k = s.get("counts", {})
        statuses = f"{k.get('PASS', 0)}/{k.get('FAIL', 0)}/{k.get('ERROR', 0)}/{k.get('SKIP', 0)}"
        if s.get("score") is None:
            lines.append(f"| {s['name']} | {s['weight']} | not measured | {statuses} |")
            continue
        points = round(s["score"] * s["weight"], 1)
        d = run["delta"]["sections"].get(s["name"])
        lines.append(f"| {s['name']} | {s['weight']} | {points}{_fmt_delta(d)} | {statuses} |")
    for s in run["sections"]:
        lines += ["", f"## {s['name']}"]
        if s.get("measures"):
            lines.append("")
            for k, v in s["measures"].items():
                lines.append(f"- {k}: `{json.dumps(v, ensure_ascii=False)}`")
        if s.get("warnings"):
            lines.append("")
            for w in s["warnings"]:
                lines.append(f"- ⚠ {w}")
        not_ok = [x for x in s["cases"] if x.get("status", "FAIL") != "PASS"]
        if not_ok:
            lines += ["", "Not passed:"]
            for x in not_ok:
                lines.append(f"- {x.get('status', 'FAIL')} {x['case']}" + (f" — {x['note']}" if x.get("note") else ""))
    return "\n".join(lines) + "\n"


def print_summary(run: dict, pm: Path):
    c = run.get("counts", {})
    print(f"\nadebench — score {score_line(run)}")
    print(f"  cases: {c.get('PASS', 0)} PASS · {c.get('FAIL', 0)} FAIL · {c.get('ERROR', 0)} ERROR · {c.get('SKIP', 0)} SKIP")
    for s in run["sections"]:
        if not s.get("weight"):
            continue
        k = s.get("counts", {})
        if s.get("score") is None:
            print(f"  {s['name']:<12} {'not measured':>17}   {k.get('SKIP', 0)} SKIP")
            continue
        d = run["delta"]["sections"].get(s["name"])
        print(f"  {s['name']:<12} {round(s['score'] * s['weight'], 1):>5}/{s['weight']:<3}{_fmt_delta(d):<8} "
              f"{k.get('PASS', 0)} PASS {k.get('FAIL', 0)} FAIL {k.get('ERROR', 0)} ERROR {k.get('SKIP', 0)} SKIP")
    warnings = [(s["name"], w) for s in run["sections"] for w in s.get("warnings", [])]
    if warnings:
        print("  warnings:")
        for n, w in warnings:
            print(f"    [{n}] {w}")
    print(f"  report: {pm}")
