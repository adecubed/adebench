"""Build the static leaderboard site from the reference reports in examples/.

    python -m adebench.site            # writes site/index.html and site/<memory>.html

One page per memory, one table on the front page. Every number on the site
comes from a report file in the repository, named on the page, so anyone
can rerun it. Memories measure different things: the ranking is on the core
(the sections every memory can be measured on), the full score is over what
each one could be measured on, and the cost of an answer (characters handed
to the model) and the speed of a write are shown next to them, because two
memories with the same score can cost the model 300 characters or 20,000.
"""
from __future__ import annotations

import html
import json
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "site"
ASSETS = ROOT / "site_assets"      # og.png (social preview) and favicon.svg, made once, committed
DOMAIN = "adebench.dev"
BASE = f"https://{DOMAIN}"

# The synthetic example memory (examples/synthetic.py) is not listed: it is
# the harness's own test double, with defects on purpose, not a product.
# facts: how the memory is reached and what it needs, as the run used it.
MEMORIES = [
    {"name": "ADE Brain", "folder": "ade_synthetic_report", "repo": "https://github.com/adecubed/adebench",
     "what": "episodes, cards, a fact layer that retires a value when a newer one contradicts it",
     "cfg": "empty instance, BRAIN_LANG=en, cards and distillation with gemini-3-flash-preview, the set's repository indexed (full-text stage only)",
     "access": "REST", "model_on_write": "yes: cards and distillation (Gemini)", "key": "model provider",
     "where": "self-hosted", "license": "private", "deterministic": "yes in five builds, model-written cards included",
     "note": "the memory of adebench's author, and its code is private: nobody else can rerun this row. It runs on the same set and rules as every other memory"},
    {"name": "gbrain", "folder": "gbrain_report", "repo": "https://github.com/garrytan/gbrain",
     "what": "entity pages, chronicle, remember/recall/forget, hybrid search",
     "cfg": "gbrain 0.50, PGLite, embeddings ollama:nomic-embed-text (768), door search, no character cut",
     "access": "CLI / MCP", "model_on_write": "embeddings only", "key": "none (local Ollama)",
     "where": "local", "license": "MIT", "deterministic": "yes"},
    {"name": "Dakera", "folder": "dakera_report", "repo": "https://dakera.ai",
     "what": "REST memory with supersession edges and session-scoped recall",
     "cfg": "adapter by its founder; fresh Docker instance, pinned config in its section of docs/memories.md. Dakera returns records, not text: the adapter's reference reader composes the door (cards, dated facts, episodes, working memory, an unknown-terms path)",
     "access": "REST", "model_on_write": "embeddings only (local models)", "key": "none (auth off, local models)",
     "where": "self-hosted", "license": "engine not public", "deterministic": "yes with the pinned config"},
    {"name": "Memoose", "folder": "memoose_report", "repo": "https://github.com/AndrewNgo-ini/memoose",
     "what": "local knowledge graph in SQLite, triples plus lexical chunks, 26 MCP tools",
     "cfg": "engine only (no model harness), fastembed vectors",
     "access": "CLI / SQLite", "model_on_write": "no", "key": "none",
     "where": "local", "license": "Apache-2.0", "deterministic": "yes"},
    {"name": "Aionforge", "folder": "aionforge_report", "repo": "https://github.com/jscott3201/aionforge-memory",
     "what": "bi-temporal graph in Rust, hybrid recall, explicit forgetting, MCP only",
     "cfg": "0.4.0 Docker image, embeddings gemini-embedding-001 (3072) behind a loopback shim",
     "access": "MCP", "model_on_write": "embeddings only", "key": "embedding provider",
     "where": "self-hosted", "license": "Apache-2.0", "deterministic": "yes"},
    {"name": "Jev-Mem", "folder": "jevmem_report", "repo": "https://github.com/libingzheren/Jev-Mem",
     "what": "graph memory whose decisions are taken by a small System-One model",
     "cfg": "Laya local decisions (config/laya_mem.json), embeddings all-MiniLM-L6-v2, no answer model",
     "access": "Python library", "model_on_write": "yes: a small System-One model (Laya, local)", "key": "none (Laya)",
     "where": "local", "license": "MIT", "deterministic": "no: the same input builds different links"},
    {"name": "Hindsight", "folder": "hindsight_report", "repo": "https://github.com/vectorize-io/hindsight",
     "what": "world facts, experiences and observations; LLM extraction on retain; per-bank MCP",
     "cfg": "MCP server 0.10.1, extraction gemini-3.5-flash-lite, prompt caching off, recall defaults",
     "access": "MCP", "model_on_write": "yes: an LLM extracts every write", "key": "LLM provider",
     "where": "self-hosted", "license": "MIT", "deterministic": "no: extraction is a model call"},
    {"name": "Nemp", "folder": "nemp_report", "repo": "https://github.com/SukinShetty/Nemp-memory",
     "what": "Claude Code plugin: a JSON file in the project, and the model itself as the engine",
     "cfg": "measured inside Claude Code: every operation is one claude -p turn (sonnet), Nemp loaded with --plugin-dir",
     "access": "inside Claude Code", "model_on_write": "yes: every operation is a model turn", "key": "Claude Code",
     "where": "local file", "license": "MIT", "deterministic": "no: every operation is a model turn"},
    {"name": "engram", "folder": "engram_report", "repo": "https://github.com/Gentleman-Programming/engram",
     "what": "one Go binary with SQLite full-text search, memory for coding agents over MCP",
     "cfg": "2.2.1 Windows release, MCP stdio with the agent tool profile (19 tools), door mem_search in 'any' mode (the default 'all' finds nothing for a verbatim question), fresh store",
     "access": "MCP / CLI", "model_on_write": "no", "key": "none",
     "where": "local", "license": "MIT", "deterministic": "yes"},
    {"name": "agentmemory", "folder": "agentmemory_report", "repo": "https://github.com/rohitg00/agentmemory",
     "what": "persistent memory for coding agents: BM25 plus vectors, supersession by overlap, 54 MCP tools",
     "cfg": "npm 0.9.29 with iii 0.11.2, keyless: local all-MiniLM-L6-v2 vectors, no LLM; door = memory_recall's own text",
     "access": "MCP / REST", "model_on_write": "no (keyless)", "key": "none",
     "where": "local", "license": "Apache-2.0", "deterministic": "yes"},
    {"name": "agentmemory (Gemini)", "folder": "agentmemory_report", "file": "reference_gemini",
     "repo": "https://github.com/rohitg00/agentmemory",
     "what": "the same memory with its LLM features on: compression, graph extraction, consolidation",
     "cfg": "npm 0.9.29, gemini-3-flash-preview, gemini-embedding-001; same door and set as the keyless row",
     "access": "MCP / REST", "model_on_write": "yes: compression and graph extraction (Gemini)", "key": "LLM provider",
     "where": "local", "license": "Apache-2.0", "deterministic": "yes in five builds"},
    {"name": "supermemory", "folder": "supermemory_report", "repo": "https://github.com/supermemoryai/supermemory",
     "what": "memory and context engine: an LLM agent extracts and versions memory entries from documents",
     "cfg": "self-hosted server 0.0.8, native Gemini provider (gemini-3.1-flash-lite-preview, fixed by the binary), local bge-base-en-v1.5",
     "access": "REST", "model_on_write": "yes: an LLM agent extracts every document", "key": "LLM provider",
     "where": "self-hosted", "license": "MIT", "deterministic": "no: extraction is a model call"},
    {"name": "cognee", "folder": "cognee_report", "repo": "https://github.com/topoteretes/cognee",
     "what": "knowledge graph plus vector index built from what is added (cognify)",
     "cfg": "1.6.1, gemini-3-flash-preview and gemini-embedding-001, door = recall context (only_context), dates shown through include_external_metadata, fresh session per call",
     "access": "Python library", "model_on_write": "yes: graph extraction (Gemini)", "key": "LLM provider",
     "where": "local", "license": "Apache-2.0", "deterministic": "no: extraction is a model call"},
    {"name": "mem0", "folder": "mem0_report", "repo": "https://github.com/mem0ai/mem0",
     "what": "memory layer for agents: an LLM extracts facts from each exchange, hybrid vector and BM25 search",
     "cfg": "open-source library 2.2.1 (not the hosted platform), gemini-3-flash-preview (max_tokens 8192: the 2000 default cut Gemini's thinking and dropped extractions), gemini-embedding-001, local Qdrant",
     "access": "Python library", "model_on_write": "yes: an LLM extracts every write", "key": "LLM provider",
     "where": "local", "license": "Apache-2.0", "deterministic": "no: extraction is a model call"},
    {"name": "memU", "folder": "memu_report", "repo": "https://github.com/NevaMind-AI/memU",
     "what": "personal memory kept as wiki pages, written by an external agent on memU's own jobs",
     "cfg": "0.11.0b3 from source; memU runs no model itself, so Gemini 3 Flash plays the executor agent with memU's prompt and workspace-only file tools (the score is memU plus this executor); gemini-embedding-001",
     "access": "CLI / Python library", "model_on_write": "yes: the executor agent (Gemini)", "key": "LLM provider",
     "where": "local", "license": "Apache-2.0", "deterministic": "yes in five builds"},
]
REFERENCE = "gbrain"
SECTIONS = ["door", "cards", "updates", "time", "live_state", "abstention", "file_search", "graph"]
# the core: the sections that need nothing but a write and a read through the
# door, so every memory can be measured on them (55 points). Cards, live state,
# file search and graph need a thing the memory may not have.
CORE = ["door", "updates", "time", "abstention"]


def load(folder: str, file: str = "reference") -> dict | None:
    p = ROOT / "examples" / folder / f"{file}.json"
    if not p.exists():
        return None
    d = json.loads(p.read_text(encoding="utf-8"))
    d["_file"] = f"examples/{folder}/{file}.md"
    return d


def load_repeats(folder: str, file: str = "reference") -> dict | None:
    """The memory's repeated runs (adebench.repeats), next to its reference:
    reference -> repeats.json, reference_gemini -> repeats_gemini.json. The
    older per-memory format (Jev-Mem: section points per run) is read too."""
    name = "repeats" + file[len("reference"):]
    p = ROOT / "examples" / folder / f"{name}.json"
    if not p.exists():
        return None
    r = json.loads(p.read_text(encoding="utf-8"))
    if "core" not in r:
        cores = [round(sum((x.get("sections") or {}).get(n) or 0 for n in CORE), 1) for x in r.get("runs", [])]
        if not cores:
            return None
        r["core"] = {"mean": round(sum(cores) / len(cores), 1), "min": min(cores), "max": max(cores), "weight": 55}
        r["total"] = {"mean": r.get("mean"), "min": r.get("min"), "max": r.get("max")}
    r["_file"] = f"examples/{folder}/{name}.json"
    return r


def sections(d: dict) -> dict[str, dict]:
    return {s["name"]: s for s in d.get("sections", [])}


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


def measures(d: dict) -> dict:
    """The numbers next to the score: what an answer costs, how fast a write
    is seen, what the write-back probe found."""
    secs = sections(d)
    dm = (secs.get("door") or {}).get("measures") or {}
    lm = (secs.get("live_state") or {}).get("measures") or {}
    um = (secs.get("updates") or {}).get("measures") or {}
    wm = (secs.get("write_back") or {}).get("measures") or {}
    return {"chars": dm.get("mean_door_text_chars"), "position": dm.get("chars_before_answer_mean"),
            "stale": dm.get("stale_values_delivered"), "write_ms": lm.get("write_to_serve_ms"),
            "write_p95": lm.get("write_to_serve_p95_ms"), "replace_ms": um.get("probe_replace_ms"),
            "poisoned": wm.get("poisoned"), "wb_tested": wm.get("questions_tested"),
            "wb_errors": sum(1 for c in (secs.get("write_back") or {}).get("cases", []) if c.get("status") == "ERROR")}


def fmt_ms(ms) -> str:
    if ms is None:
        return "—"
    ms = float(ms)
    return f"{ms:.0f} ms" if ms < 1000 else f"{ms / 1000:.1f} s"


def fmt_chars(n) -> str:
    return "—" if n is None else f"{int(n):,}"


def own_data() -> list[dict]:
    """Runs on a memory's own data: examples/own_data/*.json, totals only."""
    out = []
    for p in sorted((ROOT / "examples" / "own_data").glob("*.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        d["_file"] = f"examples/own_data/{p.name}"
        out.append(d)
    return out


def esc(s) -> str:
    return html.escape(str(s))


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


# Visits: GoatCounter (no cookies, so no consent banner). Off unless the site's
# code is set: GOATCOUNTER=adecubed in the Pages workflow counts at
# https://adecubed.goatcounter.com. Outbound clicks are counted by name.
GOATCOUNTER = os.environ.get("GOATCOUNTER", "").strip()

FONTS = ("https://fonts.googleapis.com/css2?family=Jersey+10&family=IBM+Plex+Mono:wght@400;500;600&display=swap")

CSS = """
:root{--bg:#000;--fg:#f2f2f2;--muted:#8a8a8a;--rule:#f2f2f2;--soft:#2b2b2b;--hot:#ff4f00;--warn:#ffb000;
--display:'Jersey 10',Impact,'Arial Narrow',sans-serif;--mono:'IBM Plex Mono',ui-monospace,Consolas,monospace}
*{box-sizing:border-box}html{background:var(--bg)}
body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.55 var(--mono)}
main{max-width:1280px;margin:0 auto;padding:18px 24px 40px}
a{color:inherit;text-decoration:none}a:hover{color:var(--hot)}
.bar{display:flex;justify-content:space-between;gap:16px;font-size:12px;letter-spacing:.04em;text-transform:uppercase;
border-bottom:1px solid var(--rule);padding-bottom:6px}
.type{display:inline-block;white-space:nowrap}
.type span{display:inline-block;max-width:1.2em;overflow:hidden;vertical-align:top;
animation:key 1ms steps(1) backwards;animation-delay:calc(var(--i) * 130ms + 300ms)}
.type:after{content:"";display:inline-block;width:.42em;height:.7em;margin-left:.08em;background:var(--hot);
vertical-align:.02em;animation:blink 1s steps(1) infinite}
@keyframes key{from,to{max-width:0}}@keyframes blink{50%{opacity:0}}
@media (prefers-reduced-motion:reduce){.type span{animation:none}.type:after{animation:none}}
.sr{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}
.hero{font-weight:400;font-family:var(--display);color:var(--hot);font-size:clamp(88px,19vw,300px);line-height:.82;margin:14px 0 6px;letter-spacing:.01em}
.lede{max-width:760px;font-size:15px;margin:0 0 28px}
.label{font-size:12px;letter-spacing:.06em;text-transform:uppercase;border-bottom:1px solid var(--rule);padding-bottom:6px;margin:36px 0 0}
.board{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums}
.board th{font:500 11px/1.4 var(--mono);text-transform:uppercase;letter-spacing:.05em;color:var(--muted);text-align:left;
padding:10px 8px 8px;border-bottom:1px solid var(--soft);vertical-align:bottom}
.board td{padding:12px 8px;border-bottom:1px solid var(--soft);vertical-align:top}
.board .n{text-align:right;white-space:nowrap}
.board .rank{font-family:var(--display);font-size:clamp(22px,2.6vw,30px);line-height:1;color:var(--muted);text-align:left;padding-right:2px}
.name{font-family:var(--display);font-size:clamp(30px,4vw,46px);line-height:.95;text-transform:uppercase;white-space:nowrap}
.name:before{content:"\\2731";font-size:.55em;vertical-align:.35em;margin-right:.18em}
.what{color:var(--muted);font-size:12px;margin-top:4px;max-width:420px}
.score{font-family:var(--display);font-size:clamp(34px,4.4vw,54px);line-height:.9;color:var(--hot)}
.score.plain{color:var(--fg)}
.sm{color:var(--muted);font-size:12px}
.cols{display:grid;grid-template-columns:repeat(4,1fr);gap:0 28px;margin-top:44px;border-top:1px solid var(--rule)}
.cols h3{font-family:var(--display);font-weight:400;font-size:34px;line-height:1;text-transform:uppercase;margin:10px 0 8px;
padding-bottom:8px;border-bottom:1px solid var(--rule)}
.cols p{font-size:12.5px;margin:0 0 10px}
code{font-family:var(--mono);background:var(--soft);padding:1px 5px}
.note{font-size:12.5px;color:var(--muted);max-width:900px;margin:14px 0 0}
.note b{color:var(--fg);font-weight:500}
.facts{display:grid;grid-template-columns:repeat(4,1fr);gap:0 28px;border-top:1px solid var(--rule);margin-top:20px}
.facts div{padding:10px 0;border-bottom:1px solid var(--soft)}
.facts dt{font-size:11px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted)}
.facts dd{margin:2px 0 0}
.pageh{font-weight:400;font-family:var(--display);color:var(--hot);font-size:clamp(64px,12vw,170px);line-height:.85;text-transform:uppercase;margin:14px 0 6px}
.fail{color:var(--hot)}.skip{color:var(--muted)}
.wrap{overflow-x:auto}
@media (max-width:860px){.cols,.facts{grid-template-columns:1fr 1fr}.hide-md{display:none}}
@media (max-width:560px){main{padding:14px 16px 32px}.cols,.facts{grid-template-columns:1fr}.hide-sm{display:none}
.board td,.board th{padding:10px 4px}.name{white-space:normal}}
"""


def page(title: str, body: str, description: str, path: str = "/", ld: list[dict] | None = None,
         index: bool = True) -> str:
    url = BASE + path
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)}</title><meta name="description" content="{esc(description)}">
<link rel="canonical" href="{url}">{'' if index else '<meta name="robots" content="noindex">'}
<meta name="theme-color" content="#000000"><link rel="icon" href="/favicon.svg" type="image/svg+xml">
<meta property="og:type" content="website"><meta property="og:site_name" content="adebench">
<meta property="og:title" content="{esc(title)}"><meta property="og:description" content="{esc(description)}">
<meta property="og:url" content="{url}"><meta property="og:image" content="{BASE}/og.png">
<meta property="og:image:width" content="1200"><meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image"><meta name="twitter:title" content="{esc(title)}">
<meta name="twitter:description" content="{esc(description)}"><meta name="twitter:image" content="{BASE}/og.png">
{''.join(jsonld(x) for x in (ld or []))}
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="{FONTS}" rel="stylesheet"><style>{CSS}</style></head>
<body><main>
<div class="bar"><a href="/">&copy;{datetime.now(timezone.utc).year} adebench &middot; adecubed</a><span>built {datetime.now(timezone.utc).strftime('%Y-%m-%d')} from the reports in the repo</span></div>
{body}
</main>{analytics()}</body></html>"""


def analytics() -> str:
    if not GOATCOUNTER:
        return ""
    return (f'<script data-goatcounter="https://{GOATCOUNTER}.goatcounter.com/count" '
            'async src="//gc.zgo.at/count.js"></script>')


def click(name: str) -> str:
    """GoatCounter counts a click on a link carrying this attribute as an event."""
    return f' data-goatcounter-click="{esc(name)}"' if GOATCOUNTER else ""


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def jsonld(obj: dict) -> str:
    return '<script type="application/ld+json">' + json.dumps(obj, separators=(",", ":")).replace("</", "<\\/") + "</script>"


def pct(a, b) -> str:
    return f"{100 * float(a) / float(b):.0f}%" if b else "—"


def build() -> None:
    OUT.mkdir(exist_ok=True)
    for old in OUT.glob("*_report.html"):   # the pre-0.2.16 flat pages
        old.unlink()
    from adebench.repeats import ranks   # repeats reads site.core: imported here, not at the top
    loaded = [dict(m, d=load(m["folder"], m.get("file", "reference")),
                   rep=load_repeats(m["folder"], m.get("file", "reference"))) for m in MEMORIES]
    ref = next((m["d"] for m in loaded if m["name"] == REFERENCE and m["d"]), None)
    rows = []
    for m in loaded:
        d, rep = m["d"], m["rep"]
        if not d:
            continue
        m["total"], m["measured"], m["cov"] = d.get("total"), d.get("measured_weight"), d.get("total_weight") or 100
        m["cm"] = common(d, ref) if ref and m["name"] != REFERENCE else None
        m["core"] = core(d)
        m["m"] = measures(d)
        cpts, cw, _ = m["core"]
        if rep:   # the board shows the mean of the runs, and their range
            m["runs"], m["core_mean"] = rep["builds"], rep["core"]["mean"]
            m["core_lo"], m["core_hi"] = rep["core"]["min"], rep["core"]["max"]
            m["total_mean"] = rep["total"]["mean"] if rep["total"].get("mean") is not None else m["total"]
            m["total_lo"], m["total_hi"] = rep["total"].get("min"), rep["total"].get("max")
        else:
            m["runs"], m["core_mean"], m["core_lo"], m["core_hi"] = 1, cpts, cpts, cpts
            m["total_mean"], m["total_lo"], m["total_hi"] = m["total"], m["total"], m["total"]
        rows.append(m)
    # order: the core, the same 55 points for everyone; a SKIP elsewhere costs nothing
    on55 = lambda r: r["core_mean"] * 55 / r["core"][1] if r["core"][1] else 0  # noqa: E731
    rows.sort(key=lambda r: -on55(r))
    for r, rank in zip(rows, ranks([(on55(r), r["core_hi"] - r["core_lo"]) for r in rows])):
        r["rank"] = rank
    rows.sort(key=lambda r: (r["rank"], -on55(r)))   # a wide range can tie a memory with ones above its mean
    tied = {r["rank"] for r in rows if sum(1 for x in rows if x["rank"] == r["rank"]) > 1}

    def spread(lo, hi, n) -> str:
        return f"{n} run" if n == 1 else (f"{lo}–{hi} · {n} runs" if lo != hi else f"same in {n} runs")

    trs = []
    for r in rows:
        cpts, cw, cmiss = r["core"]
        mm = r["m"]
        core_note = f"{r['core_mean']} / {cw} · {spread(r['core_lo'], r['core_hi'], r['runs'])}" + (f" · no {', '.join(cmiss)}" if cmiss else "")
        full_note = f"{r['total_mean']} / {r['measured']}" + (f" · {r['total_lo']}–{r['total_hi']}" if r["runs"] > 1 and r["total_lo"] != r["total_hi"] else "")
        rank = f"{r['rank']}{'=' if r['rank'] in tied else ''}"
        trs.append(f"""<tr><td class="n rank">{rank}</td><td><a href="/{slug(r['name'])}/"><div class="name">{esc(r['name'])}</div></a><div class="what hide-sm">{esc(r['what'])}</div>{f'<div class="sm">{esc(r["note"])}</div>' if r.get("note") else ""}</td>
<td class="n"><div class="score">{pct(r['core_mean'], cw)}</div><div class="sm">{esc(core_note)}</div></td>
<td class="n"><div class="score plain">{pct(r['total_mean'], r['measured'])}</div><div class="sm">{esc(full_note)}</div></td>
<td class="n hide-sm">{fmt_chars(mm['chars'])}</td>
<td class="n hide-sm">{fmt_ms(mm['write_ms'])}</td>
<td class="hide-md">{esc(r['access'])}</td></tr>""")

    own = own_data()
    own_trs = []
    for o in own:
        probes = sum(int(v) for v in (o.get("counts") or {}).values())
        own_trs.append(f"""<tr><td><div class="name">{esc(o.get('memory'))}</div><div class="what hide-sm">{esc(o.get('what', ''))}</div></td>
<td class="n"><div class="score">{pct(o['total'], o['measured_weight'])}</div><div class="sm">{esc(o['total'])} / {esc(o['measured_weight'])}</div></td>
<td class="n">{probes}<div class="sm">set {esc(o.get('cases_hash', ''))}</div></td>
<td class="n hide-sm">{esc(str(o.get('when', ''))[:10])}<div class="sm">adebench {esc(o.get('adebench', ''))}</div></td></tr>""")

    typed = "".join(f'<span style="--i:{i}">{c}</span>' for i, c in enumerate("ADEBENCH"))
    body = f"""<h1 class="hero"><span class="type" aria-hidden="true">{typed}</span><span class="sr">ADEBENCH — agent memory benchmark and leaderboard</span></h1>
<p class="lede">A benchmark for agent memory. It scores the text a memory actually delivers to the model, on one golden set, with no LLM judge.</p>
<div class="label">Leaderboard &middot; synthetic golden set</div>
<div class="wrap"><table class="board"><thead><tr><th class="n">#</th><th>Memory</th><th class="n">Core &middot; 55</th><th class="n">Full</th>
<th class="n hide-sm">Chars per answer</th><th class="n hide-sm">Write &rarr; visible</th><th class="hide-md">Reached through</th></tr></thead>
<tbody>{''.join(trs)}</tbody></table></div>
<p class="note"><b>Core</b> is what every memory can be measured on, a write and a read through the door: door 25, updates 10,
time 10, abstention 10. The ranking is on it. <b>Full</b> adds what a memory has behind the door (cards, live state, file
search, graph), over the points it could be measured on. <b>Chars per answer</b> is what the model receives for one question:
the same score at 300 characters and at 20,000 is not the same memory. <b>Write &rarr; visible</b> is how long a value just
written takes to reach the door. Scores are the <b>mean</b> of the runs kept for each memory, with their range;
two memories closer than the wider of their ranges (never less than one probe, 1.8 points) share a rank, marked =, and
no memory ranks above one with a higher mean.</p>
<div class="label">On their own data</div>
<div class="wrap"><table class="board"><thead><tr><th>Memory</th><th class="n">Score</th><th class="n">Probes</th><th class="n hide-sm">Run</th></tr></thead>
<tbody>{''.join(own_trs)}</tbody></table></div>
<p class="note">The golden set is small on purpose, so it runs anywhere. The bench was built for something else: a memory measured on
<b>its owner's</b> data, with probes written on the facts it really holds, rerun after every change. Not comparable across
memories, and the number that tells an owner whether a change helped. Totals only: the probes are the owner's facts.</p>
<div class="cols">
<div><h3>Method</h3><p>Eight sections: door, cards, updates, time, live state, abstention, file search, graph. A point is
earned when the expected words are in the text the model receives; a retired value next to the current one is a failure.</p>
<p><a href="https://github.com/adecubed/adebench#what-it-measures">Rules in the README &rarr;</a></p></div>
<div><h3>Run it</h3><p>No dependencies. Every adapter and importer is in the repository, and each memory's page names the
configuration that produced its numbers.</p><p><code>python -m adebench --help</code></p></div>
<div><h3>Your memory</h3><p>Write your probes, point the harness at your memory, send the totals with a pull request. The
set's hash ties a number to the probes that produced it.</p></div>
<div><h3>GitHub</h3><p>adebench is MIT. Adapters, golden set, reports: <a href="https://github.com/adecubed/adebench"{click("out-github-adebench")}>adecubed/adebench</a>.
Each memory's author is told when its results go up; if we ran it wrong, we fix it and rerun.</p></div>
</div>"""
    names = ", ".join(r["name"] for r in rows)
    desc = (f"Open benchmark for AI agent memory: {len(rows)} memory systems ({names}) scored on the text they "
            "actually deliver to the model. Same golden set, no LLM judge.")
    ld = [{"@context": "https://schema.org", "@type": "WebSite", "name": "adebench", "url": BASE + "/",
           "description": desc},
          {"@context": "https://schema.org", "@type": "SoftwareSourceCode", "name": "adebench",
           "codeRepository": "https://github.com/adecubed/adebench", "license": "https://opensource.org/licenses/MIT",
           "programmingLanguage": "Python", "description": "A benchmark for agent memory that scores the text a memory delivers to the model."},
          {"@context": "https://schema.org", "@type": "ItemList", "name": "adebench leaderboard (core score)",
           "itemListElement": [{"@type": "ListItem", "position": i + 1, "name": r["name"], "url": f"{BASE}/{slug(r['name'])}/"}
                               for i, r in enumerate(rows)]}]
    (OUT / "index.html").write_text(page("adebench — agent memory benchmark and leaderboard", body, desc, "/", ld),
                                    encoding="utf-8")

    for r in rows:
        d, mm = r["d"], r["m"]
        cpts, cw, cmiss = r["core"]
        secs = sections(d)
        srows = []
        for s in SECTIONS:
            sec = secs.get(s)
            w = int((sec or {}).get("weight") or 0)
            p = points(sec, w)
            if sec is None:
                srows.append(f"<tr><td class='name' style='font-size:26px'>{s.replace('_', ' ')}</td><td class='n skip'>not run</td><td></td></tr>")
                continue
            counts = sec.get("counts") or {}
            fails = [c for c in sec.get("cases", []) if c.get("status") in ("FAIL", "ERROR")]
            notes = "<br>".join(f"<span class='fail'>{esc(c.get('status'))}</span> {esc(c.get('case'))}"
                                + (f" <span class='sm'>— {esc(c.get('note'))}</span>" if c.get("note") else "")
                                for c in fails[:6])
            label = f"<td><div class='name' style='font-size:26px'>{s.replace('_', ' ')}</div></td>"
            if p is None:
                srows.append(f"<tr>{label}<td class='n skip'>not measured</td><td class='sm'>{esc((sec.get('warnings') or [''])[0])}</td></tr>")
            else:
                srows.append(f"<tr>{label}<td class='n'><div class='score' style='font-size:34px'>{p}</div><div class='sm'>of {w} · {esc(counts.get('PASS', 0))} pass · {esc(counts.get('FAIL', 0))} fail</div></td><td>{notes}</td></tr>")
        if mm["wb_tested"] is None:
            wb = "not run"
        elif mm["wb_errors"]:
            wb = f"not measured: {mm['wb_errors']} of {mm['wb_tested']} degraded answers were not stored by the write path"
        else:
            wb = f"{mm['poisoned']} of {mm['wb_tested']} degraded answers came back"
        cm = r["cm"]
        rep = r["rep"]
        runs_fact = (f"{r['runs']} · core {r['core_lo']}–{r['core_hi']} · the details below are the median run"
                     if r["runs"] > 1 else "1 · no range measured yet")
        facts = [("Core", f"{pct(r['core_mean'], cw)} · {r['core_mean']} / {cw}" + (" (mean)" if r["runs"] > 1 else "")
                  + (f" · no {', '.join(cmiss)}" if cmiss else "")),
                 ("Full", f"{pct(r['total_mean'], r['measured'])} · {r['total_mean']} / {r['measured']} · {r['measured']} of {r['cov']} measured"),
                 ("Runs", runs_fact),
                 ("Common with " + REFERENCE, f"{cm[0]} vs {cm[1]} on {cm[2]}" if cm else "reference"),
                 ("Chars per answer", f"{fmt_chars(mm['chars'])} · answer after {fmt_chars(mm['position'])}"),
                 ("Write → visible", fmt_ms(mm["write_ms"]) + (f" · p95 {fmt_ms(mm['write_p95'])}" if mm["write_p95"] else "")),
                 ("Write-back", wb),
                 ("Reached through", r["access"]), ("Model on write", r["model_on_write"]),
                 ("Key needed", r["key"]), ("Where it runs", r["where"]), ("License", r["license"]),
                 ("Deterministic", r["deterministic"])]
        facts_html = "".join(f"<div><dt>{esc(k)}</dt><dd>{esc(v)}</dd></div>" for k, v in facts)
        body = f"""<p style="margin:10px 0 0"><a href="/">&larr; leaderboard</a></p>
<h1 class="pageh">{esc(r['name'])}</h1>
<p class="lede">{esc(r['what'])}. <a href="{esc(r['repo'])}" style="color:var(--hot)"{click("out-repo-" + slug(r['name']))}>{esc(r['repo'])}</a></p>
{f'<p class="note"><b>Note:</b> {esc(r["note"])}</p>' if r.get("note") else ""}
<dl class="facts">{facts_html}</dl>
<p class="note"><b>Configuration:</b> {esc(r['cfg'])}. <b>Run</b> {esc(str(d.get('when', ''))[:10])}, door <code>{esc(d.get('config', {}).get('door', ''))}</code>,
fingerprint <code>{esc(str(d.get('config', {}).get('fingerprint', ''))[:12])}</code>. <b>Report:</b>
<a href="https://github.com/adecubed/adebench/blob/main/{esc(d['_file'])}" style="color:var(--hot)"{click("out-report-" + slug(r['name']))}>{esc(d['_file'])}</a>{f' · <b>All runs:</b> <a href="https://github.com/adecubed/adebench/blob/main/{esc(rep["_file"])}" style="color:var(--hot)">{esc(rep["_file"])}</a>' if rep else ""}</p>
<div class="label">Sections</div>
<div class="wrap"><table class="board"><tbody>{''.join(srows)}</tbody></table></div>"""
        sl = slug(r["name"])
        desc = (f"{r['name']} on adebench: {pct(r['core_mean'], cw)} on the core, {pct(r['total_mean'], r['measured'])} full "
                f"({r['total_mean']}/{r['measured']}), {fmt_chars(mm['chars'])} characters per answer. {r['what']}.")
        ld = [{"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
                  {"@type": "ListItem", "position": 1, "name": "adebench", "item": BASE + "/"},
                  {"@type": "ListItem", "position": 2, "name": r["name"], "item": f"{BASE}/{sl}/"}]}]
        (OUT / sl).mkdir(exist_ok=True)
        (OUT / sl / "index.html").write_text(page(f"{r['name']} on adebench — agent memory benchmark results", body, desc,
                                                  f"/{sl}/", ld), encoding="utf-8")

    for f in ("og.png", "favicon.svg"):
        if (ASSETS / f).exists():
            shutil.copyfile(ASSETS / f, OUT / f)
    day = lambda d: str(d.get("when", ""))[:10]  # noqa: E731
    latest = max((day(r["d"]) for r in rows), default="")
    urls = [(BASE + "/", latest)] + [(f"{BASE}/{slug(r['name'])}/", day(r["d"])) for r in rows]
    (OUT / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "".join(f"<url><loc>{u}</loc><lastmod>{m}</lastmod></url>\n" for u, m in urls) + "</urlset>\n", encoding="utf-8")
    (OUT / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {BASE}/sitemap.xml\n", encoding="utf-8")
    (OUT / "404.html").write_text(page("Not found — adebench", '<h1 class="hero">404</h1><p class="lede">No such page. '
                                       '<a href="/" style="color:var(--hot)">Back to the leaderboard</a>.</p>',
                                       "Page not found", "/404.html", index=False), encoding="utf-8")
    (OUT / "CNAME").write_text(DOMAIN + "\n", encoding="utf-8")
    (OUT / ".nojekyll").write_text("", encoding="utf-8")
    print(f"site: {len(rows)} memories -> {OUT}")


if __name__ == "__main__":
    build()
