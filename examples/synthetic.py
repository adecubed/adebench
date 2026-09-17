"""A synthetic memory, in process, no service: the second adapter and the
reproducible example.

    python -m adebench --adapter examples.synthetic:SyntheticAdapter \
        --cases examples/synthetic_data/cases --repo examples/synthetic_data/repo \
        --sandbox-test examples/synthetic_data/sandbox_test.py --history /tmp/run

Everything is invented and deterministic. The memory is imperfect ON
PURPOSE, so the report shows FAIL and SKIP as well as PASS:
  - the 'mailbox_version' fact carries the retired 1.3.0 next to 1.4.2, so
    the door delivers both and the question fails as STALE
  - the 'calendar' card lacks one mandatory item of its correction
  - the 'mailbox' entity has no edges in the graph
  - one abstention question contains the word 'calendar', so the memory
    hands over the calendar card for an invented thing
  - one golden question asks a fact the memory never stored
  - 'travel' facts have no event date

It also shows what the contract needs from a memory that has no voice
assistant: two doors, 'chat' (a plain composed answer) and 'raw'.
"""
from __future__ import annotations

import re
from pathlib import Path

from adebench.config import CFG

# ─── the data ────────────────────────────────────────────────────────────────

CARDS = {
    "brain": ("The Brain is the memory service of the assistant. It listens on port 8766, "
              "keeps three memory levels (working, episodic and semantic), and is distilled by "
              "the Nova model every night. Updated 2026-09-01."),
    "mailbox": ("The mailbox is served by the MailBridge connector, version 1.4.2, installed in "
                "its own virtual environment. It exposes 12 tools. Updated 2026-08-20."),
    "calendar": ("The calendar comes from the owner's work account and is read every 15 minutes. "
                 "Events are cached for one hour. Updated 2026-08-30."),
    "owner": ("The owner is Alex, a product designer based in Turin who commutes by train and "
              "prefers morning meetings. Updated 2026-09-05."),
}
CARD_DATES = {"brain": "2026-09-01", "mailbox": "2026-08-20", "calendar": "2026-08-30", "owner": "2026-09-05"}
CORRECTIONS = [
    {"entity": "brain", "content": "In the brain card never omit: port 8766, the Nova model, the three memory levels"},
    # 'shared with the team' is NOT in the calendar card: a deliberate FAIL
    {"entity": "calendar", "content": "In the calendar card never omit: read every 15 minutes, shared with the team"},
]
ALIASES = [
    {"alias": "the_brain", "canonical": "brain"},
    {"alias": "mail_bridge", "canonical": "mailbox"},
    {"alias": "agenda", "canonical": "calendar"},
]
FACTS = [
    {"key": "brain_port", "content": "The Brain listens on port 8766.", "event_date": "2026-05-10"},
    {"key": "brain_model", "content": "Distillation uses the Nova model.", "event_date": "2026-06-01"},
    {"key": "mailbox_version", "content": "MailBridge 1.4.2 replaced 1.3.0 on 2026-08-20.", "event_date": "2026-08-20"},
    {"key": "mailbox_tools", "content": "MailBridge exposes 12 tools to the assistant.", "event_date": "2026-08-20"},
    {"key": "calendar_refresh", "content": "The calendar is read every 15 minutes.", "event_date": "2026-07-02"},
    {"key": "owner_city", "content": "Alex lives in Turin.", "event_date": "2026-04-15"},
    {"key": "owner_meetings", "content": "Alex prefers morning meetings.", "event_date": "2026-05-20"},
    {"key": "travel_train", "content": "The owner commutes by train.", "event_date": None},
    {"key": "travel_bike", "content": "In summer the owner sometimes commutes by bike.", "event_date": None},
    {"key": "backup_policy", "content": "Backups run on Sundays at 03:00.", "event_date": "2026-03-01"},
]
EPISODES = [
    {"created_at": "2026-09-10T09:12:00", "repl": "chat", "input_summary": "Install MailBridge 1.4.2 in its own venv",
     "output_summary": "Installed MailBridge 1.4.2; 12 tools registered"},
    {"created_at": "2026-09-10T18:40:00", "repl": "chat", "input_summary": "Set backup schedule",
     "output_summary": "Backups on Sundays at 03:00"},
    {"created_at": "2026-09-09T11:00:00", "repl": "chat", "input_summary": "Plan the Turin trip by train",
     "output_summary": "Train at 07:15, back at 19:30"},
    {"created_at": "2026-09-08T08:30:00", "repl": "pc2:chat", "input_summary": "[pc2] Sync the calendar cache",
     "output_summary": "Cache refreshed"},
]
GRAPH_EDGES = {"brain": 3, "calendar": 2, "owner": 4, "mailbox": 0}  # mailbox: deliberate FAIL
FACT_NODES = (0, 10)


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9.]{3,}", text.lower())}


STOP = {"the", "what", "which", "who", "how", "does", "is", "are", "for", "and", "with", "about",
        "many", "when", "where", "much", "cos", "che", "qual", "quale"}


class SyntheticAdapter:
    """In-process memory implementing the adebench contract."""

    def __init__(self) -> None:
        self.working: dict[tuple[str, str], str] = {}
        self._traces: list[dict] = []
        self._known = set()
        for t in list(CARDS.values()) + [f["content"] for f in FACTS] + \
                [e["input_summary"] + " " + e["output_summary"] for e in EPISODES]:
            self._known |= _words(t)
        self._known |= set(CARDS) | {a["alias"] for a in ALIASES}

    # ── liveness ──
    def health(self) -> bool:
        return True

    def warm_up(self) -> float | None:
        return 0.1

    # ── doors ──
    def doors(self) -> list[str]:
        return ["chat", "raw", "two-step"]

    def _retrieve(self, query: str) -> dict:
        q = _words(query) - STOP
        unknown = sorted(w for w in q if w not in self._known and w.isalpha() and len(w) >= 5)
        cards = []
        for ent in CARDS:
            names = {ent} | {a["alias"] for a in ALIASES if a["canonical"] == ent}
            if any(n in q or n.replace("_", " ") in query.lower() for n in names):
                cards.append({"key": f"card:{ent}", "content": CARDS[ent]})
        semantic = []
        for f in FACTS:
            hit = len(_words(f["content"]) & q)
            if hit:
                age = f"[since {f['event_date']}] " if f["event_date"] else "[since 2026-09-01] "
                semantic.append({"source": "semantic_v2:fact", "content": age + f["content"], "_hit": hit})
        semantic.sort(key=lambda s: -s["_hit"])
        semantic = semantic[:5]
        episodic = []
        for e in EPISODES:
            if _words(e["input_summary"] + " " + e["output_summary"]) & q:
                episodic.append(dict(e))
        if unknown:
            # the specific word is unknown: keyword hits are noise
            semantic = []
            episodic = [dict(e, _fallback=True) for e in episodic]
        working = [{"key": k, "value": v} for (s, k), v in self.working.items()
                   if _words(v) & q]
        parts = []
        if unknown:
            parts.append("UNKNOWN TERMS: " + ", ".join(unknown) + "\n  No memory about them: say so instead of guessing.")
        if cards:
            parts.append("CARDS:\n" + "\n".join(f"  ▣ {c['key'][5:].upper()}: {c['content']}" for c in cards))
        if semantic:
            parts.append("SEMANTIC MEMORY:\n" + "\n".join(f"  ✦ {s['content']}" for s in semantic))
        if episodic:
            head = "EPISODIC MEMORY (no direct match):" if unknown else "EPISODIC MEMORY:"
            parts.append(head + "\n" + "\n".join(f"  [{e['created_at'][:10]}] {e['repl']} | {e['input_summary']} → {e['output_summary']}"
                                                  for e in episodic))
        if working:
            parts.append("WORKING MEMORY:\n" + "\n".join(f"  {w['key']}: {w['value']}" for w in working))
        summary = f"CONTEXT for '{query}':\n\n" + "\n\n".join(parts) if parts else f"No result for '{query}'."
        out = {"summary": summary, "_ms": 1.0, "semantic": semantic, "episodic": episodic, "working": working}
        if cards:
            out["cards"] = cards
        if unknown:
            out["unknown_terms"] = unknown
        self._traces.append({"door": "/ask", "ms": 1.0, "chars": len(summary), "http": 200})
        return out

    def ask(self, query: str) -> dict:
        return self._retrieve(query)

    def door_cut(self, door: str) -> int | None:
        return 1500 if door in ("chat", "two-step") else None

    def door_text(self, query: str, door: str) -> tuple[str, dict]:
        r = self._retrieve(query)
        if door == "two-step":
            # brief: one line per hit with its identifier; fetch: the full text
            from adebench.ade import competing_payload
            from adebench.twostep import compose
            ids = [c["key"] for c in r.get("cards", [])] + [s["source"] for s in r.get("semantic", [])]
            texts = {c["key"]: c["content"] for c in r.get("cards", [])}
            texts.update({s["source"]: s["content"] for s in r.get("semantic", [])})
            brief = f"BRIEF for '{query}':\n" + "\n".join(f"- {i}: {texts[i][:60]}" for i in ids)
            text, info = compose(brief, ids, lambda i: texts.get(i, ""), 1500, competing_payload(CFG.pressure))
            r["_two_step"] = info
            return text, r
        if door == "chat":
            from adebench.ade import competing_payload
            return (competing_payload(CFG.pressure) + r["summary"])[:1500], r  # the chat client cuts at 1,500
        return r["summary"], r

    # ── cards ──
    def cards(self) -> list[dict]:
        return [{"entity": e, "content": t, "date": CARD_DATES[e]} for e, t in CARDS.items()]

    def corrections(self) -> list[dict]:
        return list(CORRECTIONS)

    def aliases(self) -> list[dict]:
        return list(ALIASES)

    # ── facts ──
    def update_trace(self) -> dict:
        return {"superseded_live": 1, "relation_updates": 1, "archive_by_reason": {"supersede": 1}, "v2_share": 1.0}

    def event_date_share(self) -> tuple[int, int]:
        return sum(1 for f in FACTS if f["event_date"]), len(FACTS)

    # ── episodes ──
    def recent_days(self, n: int) -> list[str]:
        return sorted({e["created_at"][:10] for e in EPISODES}, reverse=True)[:n]

    def episodes_of_day(self, day: str, limit: int) -> list[dict]:
        return [e for e in EPISODES if e["created_at"].startswith(day)][:limit]

    def signed_episodes(self, prefix: str) -> int:
        return sum(1 for e in EPISODES if e["input_summary"].startswith(prefix))

    # ── working memory ──
    def working_write(self, session: str, key: str, value: str, ttl_hours: int) -> bool:
        self.working[(session, key)] = value
        return True

    def working_read(self, session: str, key: str):
        return self.working.get((session, key))

    def working_clear(self, session: str) -> None:
        self.working = {k: v for k, v in self.working.items() if k[0] != session}

    def working_age_minutes(self, session: str, key: str) -> float | None:
        return 7.0  # the live state was refreshed seven minutes ago

    # ── files and graph ──
    def file_search(self, query: str, limit: int) -> list[str]:
        if not CFG.repo:
            return []
        hits = []
        for p in sorted(Path(CFG.repo).rglob("*.py")):
            if query in p.read_text(encoding="utf-8", errors="ignore"):
                hits.append(p.as_posix())
        return hits[:limit]

    def graph_edges(self, entity: str) -> int:
        return GRAPH_EDGES.get(entity, 0)

    def graph_orphans(self) -> tuple[int, int]:
        return FACT_NODES

    def graph_counts(self) -> dict:
        return {"nodes": 14, "edges": sum(GRAPH_EDGES.values())}

    # ── report-only ──
    def health_report(self) -> tuple[dict, list[str]]:
        return {"live_facts": len(FACTS), "cards": len(CARDS), "episodes": len(EPISODES)}, []

    def measured_doors(self) -> list[str]:
        return ["/ask"]

    def traces(self) -> list[dict]:
        return self._traces

    def probe_doors(self, questions: list[str]) -> None:
        pass

    # ── optional: what this memory's MCP server declares in tools/list ──
    def declared_bytes(self) -> int | None:
        return 2200
