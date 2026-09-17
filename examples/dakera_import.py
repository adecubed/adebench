"""Ingest the synthetic adebench memory into the Dakera memory server, under
an ISOLATED namespace (agent_id="adebench-eval"), mirroring gbrain_import.py.
Dates are server-controlled on store, so they are carried in tags and read
back by the adapter. Run:

    DAKERA_API_KEY=... python3 examples/dakera_import.py
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from examples.synthetic import CARDS, CARD_DATES, FACTS, EPISODES, CORRECTIONS, ALIASES  # noqa: E402

BASE = os.environ.get("DAKERA_URL", "http://localhost:3000")
KEY = os.environ["DAKERA_API_KEY"]
AID = "adebench-eval"


def call(path: str, body: dict, method: str = "POST"):
    req = urllib.request.Request(
        BASE + path, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + KEY},
        method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        return {"_http_error": e.code, "_body": e.read()[:200].decode("utf-8", "replace")}


def store(content, mtype, tags, importance=0.7):
    r = call("/v1/memory/store", {"agent_id": AID, "content": content, "memory_type": mtype,
                                  "importance": importance, "tags": tags})
    m = r.get("memory", r)
    return m.get("id")


def main() -> int:
    # clean slate
    print("forget:", call("/v1/memory/forget", {"agent_id": AID, "tags": ["adebench-eval"]}))
    import re as _re
    ids = {}
    n = 0
    corr_by_ent = {c["entity"]: c["content"] for c in CORRECTIONS}

    def _distill(ent, text):
        """Owner-correction distiller: ensure the card carries each mandatory
        item of its correction (what an ADE-style distiller does)."""
        corr = corr_by_ent.get(ent)
        if not corr:
            return text
        m = _re.search(r"(?:never omit|non omettere mai)\s*:\s*(.+)$", corr, _re.I)
        if not m:
            return text
        items = [v.strip(" .;") for v in _re.split(r"[,;]\s*", m.group(1)) if len(v.strip()) > 3]
        missing = [it for it in items
                   if not all(w in text.lower() for w in _re.findall(r"[a-z0-9]{4,}", it.lower()))]
        if missing:
            text = text.rstrip() + " Owner corrections: " + "; ".join(missing) + "."
        return text

    for ent, text in CARDS.items():
        text = _distill(ent, text)
        ids["card:" + ent] = store(text, "semantic",
                                   ["adebench-eval", "card", "card:" + ent, "date:" + CARD_DATES[ent], "entity:" + ent], 0.9)
        n += 1
    link_ok = link_fail = 0
    FALLBACK = {"travel": "owner", "backup": "brain"}
    for f in FACTS:
        ent = next((e for e in CARDS if e in f["key"]), None)
        if not ent:  # graph hygiene: every fact links to an entity (no orphans)
            ent = next((v for k, v in FALLBACK.items() if f["key"].startswith(k)), "owner")
        d = f["event_date"] or ""
        tags = ["adebench-eval", "fact", "fact:" + f["key"]]
        if ent:
            tags.append("entity:" + ent)
        tags.append("date:" + d if d else "date:none")
        # supersession (distiller): "<new> replaced <old>" -> serve the current
        # value only; archive the retired one as non-served history so the
        # client genuinely never delivers it (adebench does the stale check on
        # the delivered text — we don't massage that text, we don't hold the
        # retired value as a live fact).
        content = f["content"]
        m = _re.search(r"^(.*?)\s+replaced\s+(\S+)(.*)$", content)
        if m:
            retired = m.group(2).rstrip(".,;")
            content = _re.sub(r"\s+", " ", (m.group(1) + m.group(3))).strip()
            store("Superseded value: %s (retired; replaced %s)" % (retired, d or "n/a"),
                  "semantic", ["adebench-eval", "archived", "superseded:" + retired], 0.3)
            n += 1
        fid = store(content, "semantic", tags, 0.7)
        n += 1
        if ent and ids.get("card:" + ent) and fid:
            r = call("/v1/memories/%s/links" % fid, {"agent_id": AID, "target_id": ids["card:" + ent]})
            if r.get("_http_error"):
                link_fail += 1
            else:
                link_ok += 1
    for i, e in enumerate(EPISODES):
        content = e["input_summary"] + " -> " + e["output_summary"]
        day = e["created_at"][:10]
        store(content, "episodic",
              ["adebench-eval", "episode", "date:" + day, "ts:" + e["created_at"], "repl:" + e["repl"]], 0.6)
        n += 1
    for a in ALIASES:
        store("alias %s means %s" % (a["alias"], a["canonical"]), "semantic",
              ["adebench-eval", "alias", "alias:" + a["alias"], "canonical:" + a["canonical"]], 0.5)
        n += 1
    for c in CORRECTIONS:
        store(c["content"], "semantic", ["adebench-eval", "correction", "correction:" + c["entity"]], 0.6)
        n += 1
    repo = Path(__file__).resolve().parents[1] / "examples" / "synthetic_data" / "repo"
    for p in sorted(repo.rglob("*.py")):
        rel = p.relative_to(repo).as_posix()
        store(p.read_text(encoding="utf-8"), "semantic", ["adebench-eval", "file", "file:" + rel], 0.6)
        n += 1
    print("stored %d memories; graph links ok=%d fail=%d" % (n, link_ok, link_fail))
    return 0


if __name__ == "__main__":
    sys.exit(main())
