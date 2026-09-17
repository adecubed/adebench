"""Ingest the synthetic adebench memory into a Dakera server, under an
ISOLATED namespace (agent_id="adebench-eval"), mirroring gbrain_import.py.

The synthetic set is loaded AS WRITTEN — no step edits the data:
- facts are stored verbatim (the deliberate "replaced" stale fact included);
- cards are stored verbatim (no owner-correction distillation);
- a fact is linked to an entity only when its key names that entity, exactly
  as gbrain_import.py does; everything else is left to Dakera's own graph.

Dakera stores a real timestamp for every memory, so undated facts carry no
date tag and the adapter shows Dakera's stored time as their age.

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
from examples.synthetic import CARDS, CARD_DATES, FACTS, EPISODES, ALIASES  # noqa: E402

BASE = os.environ.get("DAKERA_URL", "http://localhost:3000")
KEY = os.environ["DAKERA_API_KEY"]
AID = "adebench-eval"


def call(path: str, body: dict):
    req = urllib.request.Request(
        BASE + path, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + KEY},
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        return {"_http_error": e.code, "_body": e.read()[:200].decode("utf-8", "replace")}


def store(content, mtype, tags, importance=0.7):
    r = call("/v1/memory/store", {"agent_id": AID, "content": content, "memory_type": mtype,
                                  "importance": importance, "tags": tags})
    return r.get("memory", r).get("id")


def main() -> int:
    print("forget:", call("/v1/memory/forget", {"agent_id": AID, "tags": ["adebench-eval"]}))
    ids = {}
    n = 0
    # cards — stored verbatim (no distillation)
    for ent, text in CARDS.items():
        ids["card:" + ent] = store(text, "semantic",
                                   ["adebench-eval", "card", "card:" + ent, "date:" + CARD_DATES[ent], "entity:" + ent], 0.9)
        n += 1
    # facts — stored verbatim; linked to an entity only when the key names one
    link_ok = link_fail = 0
    for f in FACTS:
        ent = next((e for e in CARDS if e in f["key"]), None)
        d = f["event_date"] or ""
        tags = ["adebench-eval", "fact", "fact:" + f["key"]]
        if ent:
            tags.append("entity:" + ent)
        tags.append("date:" + d if d else "date:none")
        fid = store(f["content"], "semantic", tags, 0.7)
        n += 1
        if ent and ids.get("card:" + ent) and fid:
            r = call("/v1/memories/%s/links" % fid, {"agent_id": AID, "target_id": ids["card:" + ent]})
            link_fail += 1 if r.get("_http_error") else 0
            link_ok += 0 if r.get("_http_error") else 1
    # episodes (dates carried in tags; store controls created_at)
    for i, e in enumerate(EPISODES):
        content = e["input_summary"] + " -> " + e["output_summary"]
        day = e["created_at"][:10]
        store(content, "episodic",
              ["adebench-eval", "episode", "date:" + day, "ts:" + e["created_at"], "repl:" + e["repl"]], 0.6)
        n += 1
    # aliases (alternate names — part of the synthetic set)
    for a in ALIASES:
        store("alias %s means %s" % (a["alias"], a["canonical"]), "semantic",
              ["adebench-eval", "alias", "alias:" + a["alias"], "canonical:" + a["canonical"]], 0.5)
        n += 1
    # repo files for the file-search section
    repo = Path(__file__).resolve().parents[1] / "examples" / "synthetic_data" / "repo"
    for p in sorted(repo.rglob("*.py")):
        store(p.read_text(encoding="utf-8"), "semantic",
              ["adebench-eval", "file", "file:" + p.relative_to(repo).as_posix()], 0.6)
        n += 1
    print("stored %d memories; entity links ok=%d fail=%d" % (n, link_ok, link_fail))
    return 0



if __name__ == "__main__":
    sys.exit(main())
