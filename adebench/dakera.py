"""adebench adapter for Dakera (https://dakera.ai), a self-hosted vector
memory server, over its REST API (agent-scoped).

Dakera is a retrieval+memory engine, not a full personal-brain reader. This
adapter adds the thin reference reader adebench needs (the composed "door"
text: cards first, then dated semantic facts, then episodic, then working;
an unknown-terms/abstention path when the query names nothing known) on top
of Dakera's /v1/memory endpoints. Everything is scoped to agent_id
"adebench-eval"; no other namespace is touched. No adebench internals are
imported except CFG (pressure/door), like the gbrain adapter.

    DAKERA_API_KEY=... PYTHONPATH=/tmp/adebench python3 -m adebench \
        --adapter adebench.dakera:DakeraAdapter --cases examples/synthetic_data/cases \
        --repo examples/synthetic_data/repo --door chat --history /tmp/dakera-run --no-sandbox-test
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.request
import urllib.error
import uuid
from datetime import datetime, timezone


def _ca_date(ca) -> str:
    """A memory's real stored timestamp as YYYY-MM-DD (Dakera sets created_at
    on every write). Accepts a unix seconds value or an ISO string."""
    if ca is None:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")
    try:
        if isinstance(ca, (int, float)):
            return datetime.fromtimestamp(float(ca), tz=timezone.utc).strftime("%Y-%m-%d")
        return str(ca)[:10]
    except Exception:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

try:
    from adebench.config import CFG
except Exception:  # pragma: no cover
    class _C:  # minimal fallback
        pressure = 0
        door = "chat"
    CFG = _C()

BASE = os.environ.get("DAKERA_URL", "http://localhost:3000")
KEY = os.environ.get("DAKERA_API_KEY", "")
AID = "adebench-eval"

STOP = {"the", "what", "which", "who", "how", "does", "do", "is", "are", "for", "and", "with", "about",
        "many", "when", "where", "much", "on", "in", "of", "a", "an", "to", "owner", "owners"}

# How many hits the composed door pulls. A small top_k lets Dakera's auto-curated
# memories crowd a relevant fact out of the window, which makes the door flap
# run-to-run; a larger window delivers the relevant facts consistently.
TOPK = int(os.environ.get("DAKERA_RECALL_TOPK", "8"))


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9.]{3,}", (text or "").lower())}


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]{4,}", (text or "").lower()))


class DakeraAdapter:
    def __init__(self) -> None:
        self._traces: list[dict] = []
        self._wids: dict[tuple[str, str], str] = {}  # (session,key) -> unique wid tag
        self.cards_data: dict[str, dict] = {}
        self.facts: list[dict] = []
        self.episodes: list[dict] = []
        self._aliases: list[dict] = []
        self._corrections: list[dict] = []
        self.files: list[dict] = []
        self.vocab: set[str] = set()
        self.entities: set[str] = set()
        self._load()

    # ── HTTP ──────────────────────────────────────────────────────────────
    def _req(self, path: str, body: dict | None, method: str, timeout: float = 60):
        url = BASE + path
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method,
                                     headers={"Content-Type": "application/json",
                                              "Authorization": "Bearer " + KEY})
        t0 = time.perf_counter()
        code, out = 200, {}
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                out = json.load(r)
        except urllib.error.HTTPError as e:
            code = e.code
        except Exception:
            code = 500
        ms = (time.perf_counter() - t0) * 1000
        self._traces.append({"door": path.split("?")[0], "ms": ms,
                             "chars": len(json.dumps(out)) if out else 0, "http": code})
        return out, ms

    def _post(self, path, body, timeout=60):
        return self._req(path, body, "POST", timeout)

    def _get(self, path, timeout=60):
        return self._req(path, None, "GET", timeout)

    def _all_memories(self) -> list[dict]:
        data, _ = self._get("/v1/agents/%s/memories?limit=1000" % AID)
        if isinstance(data, dict):
            mems = data.get("memories") or data.get("items") or []
        else:
            mems = data or []
        return [m.get("memory", m) for m in mems]

    # ── load namespace into local structures ──────────────────────────────
    def _load(self) -> None:
        for mm in self._all_memories():
            tags = mm.get("tags", []) or []
            content = mm.get("content", "") or ""
            mid = mm.get("id")
            get = lambda p: next((t.split(":", 1)[1] for t in tags if t.startswith(p + ":")), None)  # noqa: E731
            if "working" in tags:
                continue
            self.vocab |= _words(content)
            if "card" in tags:
                ent = get("card")
                if ent:
                    self.cards_data[ent] = {"content": content, "date": get("date") or "", "id": mid}
                    self.entities.add(ent)
                    self.vocab.add(ent)
            elif "fact" in tags:
                self.facts.append({"key": get("fact"), "content": content,
                                   "entity": get("entity"), "date": get("date")})
            elif "episode" in tags:
                inp = content.split(" -> ")[0]
                out = content.split(" -> ", 1)[1] if " -> " in content else ""
                self.episodes.append({"created_at": get("ts") or (get("date") or ""),
                                      "day": get("date"), "repl": get("repl") or "",
                                      "input_summary": inp, "output_summary": out})
            elif "alias" in tags:
                self._aliases.append({"alias": get("alias"), "canonical": get("canonical")})
            elif "correction" in tags:
                self._corrections.append({"entity": get("correction"), "content": content})
            elif "file" in tags:
                self.files.append({"path": get("file"), "content": content})
        for a in self._aliases:
            if a.get("alias"):
                self.vocab.add(a["alias"])
        self._load_graph()

    def _load_graph(self) -> None:
        """Read the knowledge graph (GET /v1/knowledge/export). Dakera auto-
        builds shares_entity edges plus the explicit linked_by edges from
        ingest. GET /links is POST-only (405), so the export is the read path."""
        self._edge_count: dict[str, int] = {}
        self._graph_counts = {"nodes": 0, "edges": 0}
        self._fact_ids: list[str] = []
        self._live_ids: set[str] = set()
        self._graph_node_ids: set[str] = set()
        for mm in self._all_memories():
            mid = mm.get("id")
            if mid:
                self._live_ids.add(mid)
            if "fact" in (mm.get("tags", []) or []) and mid:
                self._fact_ids.append(mid)
        out, _ = self._get("/v1/knowledge/export?agent_id=%s" % AID)
        if not isinstance(out, dict):
            return
        self._graph_counts = {"nodes": out.get("node_count", 0), "edges": out.get("edge_count", 0)}
        for e in out.get("edges", []) or []:
            for k in ("from_id", "to_id"):
                nid = e.get(k)
                if nid:
                    self._edge_count[nid] = self._edge_count.get(nid, 0) + 1
                    self._graph_node_ids.add(nid)

    # ── liveness ──────────────────────────────────────────────────────────
    def health(self) -> bool:
        # true only if /health/ready actually answered 200 — a down service must
        # fail the run loudly, not silently make every section fail
        req = urllib.request.Request(BASE + "/health/ready", method="GET",
                                     headers={"Authorization": "Bearer " + KEY})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status == 200
        except Exception:
            return False

    def warm_up(self) -> float | None:
        _, ms = self._post("/v1/memory/recall", {"agent_id": AID, "query": "hello", "top_k": 1})
        return ms

    # ── doors ─────────────────────────────────────────────────────────────
    def doors(self) -> list[str]:
        return ["chat", "raw"]

    def door_cut(self, door: str) -> int | None:
        return 2400 if door == "chat" else None

    def _recall(self, query: str, k: int = TOPK) -> list[dict]:
        out, _ = self._post("/v1/memory/recall", {"agent_id": AID, "query": query, "top_k": k})
        hits = out.get("memories", []) if isinstance(out, dict) else []
        return [h.get("memory", h) for h in hits]

    def _named_cards(self, query: str) -> list[dict]:
        ql = query.lower()
        # abstention guard: if the query's real subject is an unknown proper
        # noun (capitalised, not a known entity/alias), it is asking about
        # something invented — do not attach a real card on a modifier match.
        toks = re.findall(r"[A-Za-z0-9]+", query)
        known = ({e.lower() for e in self.entities}
                 | {a["alias"].replace("_", " ").lower() for a in self._aliases if a.get("alias")}
                 | {a["alias"].lower() for a in self._aliases if a.get("alias")})
        if any(t[0].isupper() and len(t) >= 4 and t.lower() not in self.vocab and t.lower() not in known
               for t in toks[1:]):
            return []
        alias_map = {a["alias"]: a["canonical"] for a in self._aliases if a.get("alias")}
        out, seen = [], set()
        for name in list(self.entities) + list(alias_map.keys()):
            canon = alias_map.get(name, name)
            if canon not in self.cards_data or canon in seen:
                continue
            n = name.replace("_", " ")
            if len(n) >= 3 and re.search(r"(?<![a-z0-9])" + re.escape(n) + r"(?![a-z0-9])", ql):
                seen.add(canon)
                out.append({"key": "card:" + canon, "content": self.cards_data[canon]["content"]})
        return out

    def ask(self, query: str) -> dict:
        qwords = _words(query) - STOP
        cards = self._named_cards(query)
        unknown = sorted(w for w in qwords if w.isalpha() and len(w) >= 5 and w not in self.vocab)
        hits = self._recall(query, TOPK)
        semantic, episodic = [], []
        for mm in hits:
            tags = mm.get("tags", []) or []
            content = mm.get("content", "") or ""
            if "fact" in tags:
                date = next((t.split(":", 1)[1] for t in tags if t.startswith("date:")), "") or ""
                if date in ("", "none"):
                    date = _ca_date(mm.get("created_at"))  # Dakera's real stored timestamp, not a constant
                semantic.append({"source": "semantic_v2:fact", "content": "[since %s] %s" % (date, content),
                                 "_hit": len(_words(content) & qwords)})
            elif "episode" in tags:
                ts = next((t.split(":", 1)[1] for t in tags if t.startswith("ts:")),
                          next((t.split(":", 1)[1] for t in tags if t.startswith("date:")), ""))
                inp = content.split(" -> ")[0]
                episodic.append({"created_at": ts, "input_summary": inp,
                                 "output_summary": content.split(" -> ", 1)[1] if " -> " in content else "",
                                 "repl": next((t.split(":", 1)[1] for t in tags if t.startswith("repl:")), "")})
        strong = [s for s in semantic if s["_hit"] > 0]
        semantic = strong if strong else semantic
        semantic.sort(key=lambda s: -s["_hit"])
        semantic = semantic[:5]
        weak = (not cards) and bool(unknown)
        if weak:
            semantic = [{"source": "semantic_vec:near", "content": s["content"]} for s in semantic[:2]]
            episodic = [dict(e, _fallback=True) for e in episodic]
        working = self._working_hits(query)
        parts = []
        if weak:
            parts.append("UNKNOWN TERMS: " + ", ".join(unknown)
                         + "\n  No direct match in memory: say so instead of guessing.")
        if cards:
            parts.append("CARDS:\n" + "\n".join("  ▣ %s: %s" % (c["key"][5:].upper(), c["content"]) for c in cards))
        if semantic:
            head = "NEAREST (no direct match):" if weak else "SEMANTIC MEMORY:"
            parts.append(head + "\n" + "\n".join("  ✦ %s" % s["content"] for s in semantic))
        if episodic:
            head = "EPISODIC MEMORY (no direct match):" if weak else "EPISODIC MEMORY:"
            parts.append(head + "\n" + "\n".join("  [%s] %s | %s → %s"
                         % (str(e["created_at"])[:10], e["repl"], e["input_summary"], e["output_summary"])
                         for e in episodic))
        if working:
            parts.append("WORKING MEMORY:\n" + "\n".join("  %s: %s" % (w["key"], w["value"]) for w in working))
        summary = ("CONTEXT for '%s':\n\n" % query + "\n\n".join(parts)) if parts else ("No result for '%s'." % query)
        r = {"summary": summary, "semantic": semantic, "episodic": episodic, "working": working,
             "_ms": self._traces[-1]["ms"] if self._traces else 0}
        if cards:
            r["cards"] = cards
        if weak and unknown:
            r["unknown_terms"] = unknown
        return r

    def door_text(self, query: str, door: str):
        r = self.ask(query)
        from adebench.ade import competing_payload  # same simulated payload every adapter uses
        payload = competing_payload(getattr(CFG, "pressure", 0))
        text = payload + r["summary"]
        cut = self.door_cut(door)
        return (text[:cut] if cut else text), r

    # ── cards / corrections / aliases ─────────────────────────────────────
    def cards(self) -> list[dict]:
        return [{"entity": e, "content": d["content"], "date": d["date"]} for e, d in self.cards_data.items()]

    def corrections(self) -> list[dict]:
        # Dakera has no owner-correction / distiller feature, so the correction
        # cases SKIP (like gbrain); cards are stored and served verbatim.
        return []

    def aliases(self) -> list[dict]:
        return [a for a in self._aliases if a.get("alias") and a.get("canonical")]

    # ── facts ─────────────────────────────────────────────────────────────
    def update_trace(self) -> dict:
        return {}

    def event_date_share(self):
        dated = sum(1 for f in self.facts if f.get("date") and f["date"] != "none")
        return (dated, len(self.facts))

    # ── episodes / time ───────────────────────────────────────────────────
    def recent_days(self, n: int) -> list[str]:
        return sorted({str(e["created_at"])[:10] for e in self.episodes if e.get("created_at")}, reverse=True)[:n]

    def episodes_of_day(self, day: str, limit: int) -> list[dict]:
        return [e for e in self.episodes if str(e.get("created_at", "")).startswith(day)][:limit]

    def signed_episodes(self, prefix: str) -> int:
        return sum(1 for e in self.episodes if str(e.get("input_summary", "")).startswith(prefix))

    # ── working memory ────────────────────────────────────────────────────
    def _working_mems(self) -> list[dict]:
        return [mm for mm in self._all_memories() if "working" in (mm.get("tags", []) or [])]

    def _working_hits(self, query: str) -> list[dict]:
        qtok = _tokens(query)
        out = []
        for mm in self._working_mems():
            content = mm.get("content", "") or ""
            if _tokens(content) & qtok:
                tags = mm.get("tags", []) or []
                key = next((t.split(":", 1)[1] for t in tags if t.startswith("wkey:")), "")
                out.append({"key": key, "value": content})
        return out

    def working_write(self, session: str, key: str, value: str, ttl_hours: int) -> bool:
        prev = self._wids.get((session, key))
        if prev:
            self._post("/v1/memory/forget", {"agent_id": AID, "tags": [prev]})
        wid = "wid:" + uuid.uuid4().hex
        out, _ = self._post("/v1/memory/store", {
            "agent_id": AID, "content": "[%s] %s" % (key, value), "memory_type": "working", "importance": 0.5,
            "tags": ["adebench-eval", "working", "wsession:" + session, "wkey:" + key, wid]})
        m = out.get("memory", out) if isinstance(out, dict) else {}
        if m.get("id"):
            self._wids[(session, key)] = wid
            return True
        return False

    def working_read(self, session: str, key: str):
        for mm in self._working_mems():
            tags = mm.get("tags", []) or []
            if ("wkey:" + key) in tags and ("wsession:" + session) in tags:
                return mm.get("content")
        return None

    def working_clear(self, session: str) -> None:
        self._post("/v1/memory/forget", {"agent_id": AID, "tags": ["wsession:" + session]})
        self._wids = {k: v for k, v in self._wids.items() if k[0] != session}

    def working_age_minutes(self, session: str, key: str):
        return None

    # ── files / graph ─────────────────────────────────────────────────────
    def file_search(self, query: str, limit: int) -> list[str]:
        out, _ = self._post("/v1/memory/search", {"agent_id": AID, "query": query, "top_k": limit})
        hits = out.get("memories", []) if isinstance(out, dict) else []
        paths = []
        for h in hits:
            mm = h.get("memory", h)
            tags = mm.get("tags", []) or []
            p = next((t.split(":", 1)[1] for t in tags if t.startswith("file:")), None)
            if p:
                paths.append(p)
        return paths[:limit]

    def graph_edges(self, entity: str) -> int:
        cid = self.cards_data.get(entity, {}).get("id")
        return self._edge_count.get(cid, 0) if cid else 0

    def graph_orphans(self):
        # adebench's definition: fact nodes whose backing fact no longer exists
        # (dangling). A graph node id not among the live memories is dangling;
        # on a clean ingest with no deletions this is zero.
        if not self._graph_node_ids:
            return (0, 0)
        orphans = sum(1 for nid in self._graph_node_ids if nid not in self._live_ids)
        return (orphans, len(self._graph_node_ids))

    def graph_counts(self) -> dict:
        return dict(self._graph_counts)

    # ── report-only ───────────────────────────────────────────────────────
    def health_report(self):
        return {"cards": len(self.cards_data), "facts": len(self.facts), "episodes": len(self.episodes)}, []

    def measured_doors(self) -> list[str]:
        return ["/v1/memory/recall"]

    def traces(self) -> list[dict]:
        return self._traces

    def probe_doors(self, questions: list[str]) -> None:
        pass

    # ── optional: anti-leak check for the abstention section ───────────────
    def stored_mentions(self, phrase: str) -> int:
        """How many stored memories contain this phrase (Dakera full-text
        search). The abstention section uses it to warn if an invented entity
        of the golden set leaked into the memory it measures."""
        out, _ = self._post("/v1/memory/search", {"agent_id": AID, "query": phrase, "top_k": 20})
        hits = out.get("memories", []) if isinstance(out, dict) else []
        pl = phrase.lower()
        return sum(1 for h in hits if pl in (h.get("memory", h).get("content", "") or "").lower())
