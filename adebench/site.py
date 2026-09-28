"""Build the static leaderboard site from the reference reports in examples/.

    python -m adebench.site            # writes site/index.html and site/<memory>.html

One page per memory, one table on the front page. Every number on the site
comes from a report file in the repository, named on the page, so anyone
can rerun it. Memories measure different things: the table shows the score
over the points each one could be measured on, the coverage, and the score
on the points it shares with a reference memory (gbrain, the one every
other memory has in common), never a single number pretending they are
the same test.
"""
from __future__ import annotations

import html
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "site"
DOMAIN = "adebench.dev"

# name, report folder, repository, what it is, the configuration that ran.
# The synthetic example memory (examples/synthetic.py) is not listed: it is
# the harness's own test double, with defects on purpose, not a product.
MEMORIES = [
    ("ADE Brain", "ade_synthetic_report", "https://github.com/adecubed/adebench",
     "episodes, cards, a fact layer that retires a value when a newer one contradicts it",
     "empty instance, BRAIN_LANG=en, cards and distillation with gemini-3-flash-preview, the set's repository indexed (full-text stage only)"),
    ("gbrain", "gbrain_report", "https://github.com/garrytan/gbrain",
     "entity pages, chronicle, remember/recall/forget, hybrid search",
     "gbrain 0.50, PGLite, embeddings ollama:nomic-embed-text (768), doors search, no character cut"),
    ("Dakera", "dakera_report", "https://dakera.ai",
     "REST memory with supersession edges and session-scoped recall",
     "adapter by its founder; fresh instance, pinned config in its README section"),
    ("Memoose", "memoose_report", "https://github.com/AndrewNgo-ini/memoose",
     "local knowledge graph in SQLite, triples plus lexical chunks, 26 MCP tools",
     "engine only (no model harness), fastembed vectors"),
    ("Aionforge", "aionforge_report", "https://github.com/jscott3201/aionforge-memory",
     "bi-temporal graph in Rust, hybrid recall, explicit forgetting, MCP only",
     "0.4.0 Docker image, embeddings gemini-embedding-001 (3072) behind a loopback shim"),
    ("Hindsight", "hindsight_report", "https://github.com/vectorize-io/hindsight",
     "world facts, experiences and observations; LLM extraction on retain; per-bank MCP",
     "MCP server 0.10.1, extraction gemini-3.5-flash-lite, prompt caching off, recall defaults"),
]
REFERENCE = "gbrain"
SECTIONS = ["door", "cards", "updates", "time", "live_state", "abstention", "file_search", "graph"]
# the core: the sections that need nothing but a write and a read through the
# door, so every memory can be measured on them (55 points). Cards, live state,
# file search and graph need a thing the memory may not have.
CORE = ["door", "updates", "time", "abstention"]


def load(folder: str) -> dict | None:
    p = ROOT / "examples" / folder / "reference.json"
    if not p.exists():
        return None
    d = json.loads(p.read_text(encoding="utf-8"))
    d["_file"] = f"examples/{folder}/reference.md"
    return d


def sections(d: dict) -> dict[str, dict]:
    out = {}
    for s in d.get("sections", []):
        out[s["name"]] = s
    return out


def points(sec: dict | None, weight: int) -> float | None:
    """Points of a section: score (0..1) × weight, None when not measured."""
    if not sec or sec.get("score") is None:
        return None
    return round(float(sec["score"]) * weight, 1)


def common(a: dict, b: dict) -> tuple[float, float, int]:
    """Points of a and b on the sections both measured, and that weight."""
    wa, wb, tot = 0.0, 0.0, 0
    sa, sb = sections(a), sections(b)
    for name in SECTIONS:
        w = int((sa.get(name) or {}).get("weight") or 0)
        pa, pb = points(sa.get(name), w), points(sb.get(name), w)
        if pa is None or pb is None or w == 0:
            continue
        wa += pa
        wb += pb
        tot += w
    return round(wa, 1), round(wb, 1), tot


def core(d: dict) -> tuple[float, int, list[str]]:
    """Points and weight on the core sections, and the core sections not measured."""
    secs = sections(d)
    pts, w, missing = 0.0, 0, []
    for name in CORE:
        sec = secs.get(name)
        p = points(sec, int((sec or {}).get("weight") or 0))
        if p is None:
            missing.append(name)
            continue
        pts += p
        w += int(sec["weight"])
    return round(pts, 1), w, missing


def own_data() -> list[dict]:
    """Runs on a memory's own data: examples/own_data/*.json, totals only."""
    out = []
    for p in sorted((ROOT / "examples" / "own_data").glob("*.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        d["_file"] = f"examples/own_data/{p.name}"
        out.append(d)
    return out


def own_rows(own: list[dict]) -> str:
    rows = []
    for o in own:
        share = 100 * float(o["total"]) / float(o["measured_weight"])
        probes = sum(int(v) for v in (o.get("counts") or {}).values())
        rows.append(
            f"<tr><td><b>{esc(o.get('memory'))}</b><br><span class=\"muted hide-sm\">{esc(o.get('what', ''))}</span></td>"
            f"<td class=\"n\"><span class=\"big\">{share:.0f}%</span><br><span class=\"muted\">{esc(o['total'])} / {esc(o['measured_weight'])}</span></td>"
            f"<td class=\"n\">{probes}<br><span class=\"muted\">set {esc(o.get('cases_hash', ''))}</span></td>"
            f"<td class=\"n\">{esc(str(o.get('when', ''))[:10])}<br><span class=\"muted\">adebench {esc(o.get('adebench', ''))}</span></td></tr>")
    return "".join(rows)


def esc(s) -> str:
    return html.escape(str(s))


CSS = """
:root{--bg:#0f1115;--fg:#e8e8e8;--muted:#9aa0a6;--line:#2a2e36;--accent:#6ee7c8;--warn:#f9d84a}
@media (prefers-color-scheme: light){:root{--bg:#fbfbfb;--fg:#15171b;--muted:#5d6470;--line:#e2e5ea;--accent:#0f766e;--warn:#9a6b00}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.5 system-ui,Segoe UI,Roboto,sans-serif}
main{max-width:1040px;margin:0 auto;padding:32px 16px 64px}h1{font-size:2rem;margin:0 0 4px}h2{margin-top:2.2rem}
.sub{color:var(--muted);margin:0 0 24px}table{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums}
th,td{padding:10px 8px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}th{color:var(--muted);font-weight:600;font-size:.85rem}
td.n,th.n{text-align:right;white-space:nowrap}.big{font-size:1.25rem;font-weight:700}.muted{color:var(--muted)}
a{color:var(--accent)}code{background:var(--line);padding:1px 5px;border-radius:4px;font-size:.9em}
.skip{color:var(--muted)}.fail{color:var(--warn)}.note{border-left:3px solid var(--line);padding:8px 14px;color:var(--muted);margin:16px 0}
@media (max-width:640px){table{font-size:.9rem}th,td{padding:8px 4px}.hide-sm{display:none}}
"""


def page(title: str, body: str, description: str) -> str:
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)}</title><meta name="description" content="{esc(description)}"><style>{CSS}</style></head>
<body><main>{body}
<p class="muted" style="margin-top:48px">adebench is MIT. Every number here comes from a report file in
<a href="https://github.com/adecubed/adebench">adecubed/adebench</a>; the adapters and the golden set are in the same repository.
Built {datetime.now(timezone.utc).strftime('%Y-%m-%d')}.</p></main></body></html>"""


def build() -> None:
    OUT.mkdir(exist_ok=True)
    loaded = [(n, f, repo, what, cfg, load(f)) for n, f, repo, what, cfg in MEMORIES]
    ref = next((d for n, f, repo, what, cfg, d in loaded if n == REFERENCE and d), None)

    rows = []
    for name, folder, repo, what, cfg, d in loaded:
        if not d:
            continue
        total = d.get("total")
        measured = d.get("measured_weight")
        cov = d.get("total_weight") or 100
        cm = common(d, ref) if ref and name != REFERENCE else None
        rows.append((name, folder, repo, what, cfg, d, total, measured, cov, cm, core(d)))
    # order: the core, the same 55 points for everyone; a SKIP elsewhere costs nothing
    rows.sort(key=lambda r: -(r[10][0] / r[10][1] if r[10][1] else 0))

    trs = []
    for name, folder, repo, what, cfg, d, total, measured, cov, cm, (cpts, cw, cmiss) in rows:
        share = f"{100 * float(total) / float(measured):.0f}%" if measured else "—"
        core_share = f"{100 * cpts / cw:.0f}%" if cw else "—"
        core_note = f"{cpts} / {cw}" + (f" (no {', '.join(cmiss)})" if cmiss else "")
        common_txt = (f"{cm[0]} vs {cm[1]} on {cm[2]}" if cm else ("reference" if name == REFERENCE else "—"))
        trs.append(f"""<tr><td><a href="{esc(folder)}.html"><b>{esc(name)}</b></a><br><span class="muted hide-sm">{esc(what)}</span></td>
<td class="n"><span class="big">{core_share}</span><br><span class="muted">{esc(core_note)}</span></td>
<td class="n"><span class="big">{share}</span><br><span class="muted">{esc(total)} / {esc(measured)}</span></td>
<td class="n">{esc(measured)} / {esc(cov)}</td><td class="n">{esc(common_txt)}</td></tr>""")

    own = own_data()
    body = f"""<h1>adebench</h1>
<p class="sub">A benchmark for agent memory that scores the text the memory actually delivers to the model, on one golden set, with no LLM judge.</p>
<table><thead><tr><th>Memory</th><th class="n">Core (55)</th><th class="n">Full</th><th class="n">Measured of 100</th><th class="n">Common points vs {esc(REFERENCE)}</th></tr></thead>
<tbody>{''.join(trs)}</tbody></table>
<div class="note">Same synthetic golden set for every memory (eight door questions, four invented entities, the same
update, live-state and write-back probes). <b>Core</b> is the part every memory can be measured on, because it needs
nothing but a write and a read through the door: door (25), updates (10), time (10), abstention (10). The ranking is on
it. <b>Full</b> adds what a memory has behind the door (cards, live state, file search, graph): a memory that does not
have a thing is not scored on it, and <i>measured</i> says how much of the 100 was. The last column scores two
memories only on the sections both measured.</div>
<h2>On their own data</h2>
<p>The golden set above is small on purpose, so that it runs anywhere. The bench was built for something else: a memory
measured on <i>its owner's</i> data, with probes written on the facts it really holds, rerun after every change. That
number is not comparable across memories, since every owner has different data, and it is the one that tells an owner
whether a change helped. Totals only: the probes and the reports are the owner's facts.</p>
<table><thead><tr><th>Memory</th><th class="n">Score</th><th class="n">Probes</th><th class="n">Run</th></tr></thead><tbody>
{own_rows(own)}
</tbody></table>
<div class="note">Run it on your own memory: write your probes (<code>cases/questions.json</code>, <code>cases/abstention.json</code>,
the README says how to validate them), point the harness at your memory, and send the totals with a pull request. The
harness prints the set's hash, so a number is always tied to the probes that produced it.</div>
<h2>What it measures</h2>
<p>Eight sections, weights in brackets: door (25) — the expected words are in the text the client receives, and a retired value next to the current one is a failure;
cards (15); updates (10) — a new write with no id must replace the old value at the door; time (10); live state (10) — write-to-serve latency and overwrite consistency;
abstention (10) — invented entities; file search (10); graph (10). Report-only: write-back (a degraded answer written through the memory's own path must not come back), census pressure, doors.
The <a href="https://github.com/adecubed/adebench#what-it-measures">README</a> has the rules.</p>
<h2>Run it yourself</h2>
<p><code>pip install</code> nothing: the harness has no dependencies. Every adapter and importer is in the repository, and each memory's page names the exact configuration that produced its numbers.
To add a memory, write an adapter against <code>adebench/adapter.py</code> and open a pull request; results are reviewed with the author before they appear here.</p>"""
    (OUT / "index.html").write_text(page("adebench — agent memory, measured at the door", body,
                                         "Leaderboard of agent memory systems on the adebench golden set"), encoding="utf-8")

    for name, folder, repo, what, cfg, d, total, measured, cov, cm, (cpts, cw, cmiss) in rows:
        secs = sections(d)
        srows = []
        for s in SECTIONS:
            sec = secs.get(s)
            w = int((sec or {}).get("weight") or 0)
            p = points(sec, w)
            if sec is None:
                srows.append(f"<tr><td>{s}</td><td class='n skip'>not run</td><td></td></tr>")
                continue
            counts = sec.get("counts") or {}
            fails = [c for c in sec.get("cases", []) if c.get("status") in ("FAIL", "ERROR")]
            notes = "<br>".join(f"<span class='fail'>{esc(c.get('status'))}</span> {esc(c.get('case'))}"
                                + (f" — <span class='muted'>{esc(c.get('note'))}</span>" if c.get("note") else "")
                                for c in fails[:6])
            if p is None:
                srows.append(f"<tr><td>{s}</td><td class='n skip'>not measured</td><td class='muted'>{esc((sec.get('warnings') or [''])[0])}</td></tr>")
            else:
                srows.append(f"<tr><td>{s}</td><td class='n'><b>{p}</b> / {w}<br><span class='muted'>{esc(counts.get('PASS', 0))} pass · {esc(counts.get('FAIL', 0))} fail</span></td><td>{notes}</td></tr>")
        wb = secs.get("write_back")
        wb_txt = ""
        if wb:
            c = wb.get("counts") or {}
            wb_txt = f"<p>Write-back (report-only): {esc(c.get('PASS', 0))} of {esc((c.get('PASS', 0) or 0) + (c.get('FAIL', 0) or 0))} probes clean.</p>"
        body = f"""<p><a href="index.html">← leaderboard</a></p><h1>{esc(name)}</h1>
<p class="sub">{esc(what)} — <a href="{esc(repo)}">{esc(repo)}</a></p>
<p><span class="big">{(100 * cpts / cw) if cw else 0:.0f}%</span> <span class="muted">core, {cpts} / {cw}{(' (no ' + ', '.join(cmiss) + ')') if cmiss else ''}</span>
· <span class="big">{(100 * float(total) / float(measured)):.0f}%</span> <span class="muted">full, {esc(total)} / {esc(measured)} · {esc(measured)} of {esc(cov)} points measured</span>
{('· common with ' + esc(REFERENCE) + f': {cm[0]} vs {cm[1]} on {cm[2]}') if cm else ''}</p>
<p><b>Configuration:</b> {esc(cfg)}. <b>Run:</b> {esc(str(d.get('when', ''))[:10])}, door <code>{esc(d.get('config', {}).get('door', ''))}</code>, fingerprint <code>{esc(str(d.get('config', {}).get('fingerprint', ''))[:12])}</code>.
<b>Report:</b> <a href="https://github.com/adecubed/adebench/blob/main/{esc(d['_file'])}">{esc(d['_file'])}</a></p>
<table><thead><tr><th>Section</th><th class="n">Points</th><th>Not passed</th></tr></thead><tbody>{''.join(srows)}</tbody></table>
{wb_txt}"""
        (OUT / f"{folder}.html").write_text(page(f"{name} — adebench", body, f"{name} on the adebench golden set"), encoding="utf-8")

    (OUT / "CNAME").write_text(DOMAIN + "\n", encoding="utf-8")
    (OUT / ".nojekyll").write_text("", encoding="utf-8")
    print(f"site: {len(rows)} memories -> {OUT}")


if __name__ == "__main__":
    build()
