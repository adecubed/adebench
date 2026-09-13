"""Adapter for gbrain (github.com/garrytan/gbrain): the second real memory.

Everything goes through one door of gbrain's own, `gbrain call <tool>
'<json>'`, the trusted local dispatch of its MCP tools: the same operations
an agent gets over MCP, with their JSON result. No gbrain code is imported.

    bun install -g github:garrytan/gbrain#latest-stable
    gbrain init --pglite
    python -m adebench --adapter adebench.gbrain:GbrainAdapter --cases my/cases

Doors:
  search  what an agent gets from `search` (hybrid retrieval, snippets) plus
          the facts `recall` returns for the same query; no cut
          ADEBENCH_GBRAIN_CUT=N cuts it at N characters, to compare with a
          memory whose door has a budget (e.g. 2400 for a voice client)
  two-step  a brief with identifiers (named entity cards, then search hits
          with 120-char snippets), then get_page on each identifier in that
          order until ADEBENCH_TWO_STEP_BUDGET (default 2400) is full: two
          calls or more, one budget, latency summed (adebench.twostep)
  pack    `context_pack` for the entities the search found: a budget-packed
          BRIEF (one line per entity, open threads, "use get_page before
          relying on details"), i.e. the first step of a two-step door. It is
          measured as what it is: answers are rarely in it, and the report
          says "lost through this door". ADEBENCH_GBRAIN_PACK_TOKENS, default 600

What maps and what does not (SKIP is honest, not a zero):
  cards          entity pages (person / company / project); corrections and
                 aliases: none, the cards section runs without them
  fact updates   no supersede trace is read: update_trace is empty, the
                 section relies on the sandbox test you point to (or SKIPs)
  time           chronicle_day / chronicle_since: dated events
  live state     remember / recall / forget, the memory verbs, with a TTL;
                 no "live state key": that case is SKIP
  files          not mapped (gbrain indexes pages, not a repository)
  graph          get_links + get_backlinks per entity, get_health for orphans
  declared bytes `gbrain --tools-json`: what the MCP server declares
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from datetime import datetime, timedelta

from adebench.config import CFG

ENTITY_TYPES = ("person", "company", "project", "people", "companies", "projects")
DOORS = ("search", "pack", "two-step")


class GbrainError(RuntimeError):
    pass


class GbrainAdapter:
    def __init__(self) -> None:
        self.bin = os.environ.get("ADEBENCH_GBRAIN_BIN") or shutil.which("gbrain") or "gbrain"
        self.source = os.environ.get("ADEBENCH_GBRAIN_SOURCE")  # --source <id>, optional
        self.pack_tokens = int(os.environ.get("ADEBENCH_GBRAIN_PACK_TOKENS", "600"))
        # a cut on the search door, in characters (0 = none): set it to the
        # voice budget of the memory you compare with, e.g. 2400
        self.search_cut = int(os.environ.get("ADEBENCH_GBRAIN_CUT", "0"))
        # the two-step door: brief + fetches under one budget (same as a voice cut)
        self.two_step_budget = int(os.environ.get("ADEBENCH_TWO_STEP_BUDGET", "2400"))
        self._traces: list[dict] = []
        self._remembered: dict[tuple[str, str], str] = {}   # (session, key) -> fact id
        self._entities: dict[str, str] | None = None          # name -> slug, lazily from list_pages

    def _entity_slugs(self) -> dict[str, str]:
        if self._entities is None:
            self._entities = {}
            for t in ("person", "company", "project"):
                try:
                    for p in self._results(self._call("list_pages", {"type": t, "limit": 200})):
                        sl = str(p.get("slug", ""))
                        if sl:
                            self._entities[sl.rsplit("/", 1)[-1].lower()] = sl
                except GbrainError:
                    continue
        return self._entities

    def _named_cards(self, query: str) -> list[dict]:
        """The card of every known entity the question names, read with
        get_page: what gbrain's `entity` verb gives an agent that asks by
        name, and what the reference client does with its own cards."""
        ql = query.lower()
        out = []
        for name, sl in self._entity_slugs().items():
            if len(name) >= 3 and re.search(r"(?<![a-z0-9])" + re.escape(name) + r"(?![a-z0-9])", ql):
                try:
                    page = self._call("get_page", {"slug": sl})
                except GbrainError:
                    continue
                text = self._card_text(page)
                if text:
                    out.append({"key": f"card:{sl}", "content": text})
            if len(out) >= 2:
                break
        return out

    @staticmethod
    def _card_text(page) -> str:
        if not isinstance(page, dict):
            return ""
        content = str(page.get("compiled_truth") or page.get("content") or "").replace("\r\n", "\n")
        if content.startswith("# "):   # the page title is not part of the card
            content = content.split("\n", 1)[1].lstrip() if "\n" in content else ""
        # a trailing "Related: [[...]]" line is the importer's, not the card's
        lines = [ln for ln in content.split("\n") if not ln.startswith("Related: [[")]
        return "\n".join(lines).strip()

    # ── the one door to gbrain ────────────────────────────────────────────
    def _run(self, args: list[str], timeout: float = 180) -> tuple[str, float, int]:
        cmd = [self.bin] + args
        t0 = time.perf_counter()
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                               timeout=timeout, shell=os.name == "nt" and self.bin.lower().endswith((".cmd", ".bat")))
        except FileNotFoundError as e:
            raise GbrainError(f"gbrain not found ({self.bin}): {e}") from e
        except subprocess.TimeoutExpired as e:
            raise GbrainError(f"gbrain {' '.join(args[:2])}: timeout after {timeout}s") from e
        ms = (time.perf_counter() - t0) * 1000
        return r.stdout, ms, r.returncode

    def _call(self, tool: str, params: dict | None = None, timeout: float = 180):
        args = ["call"] + (["--source", self.source] if self.source else []) + [tool, json.dumps(params or {})]
        out, ms, code = self._run(args, timeout)
        text = out.strip()
        # the envelope is the last JSON value on stdout (progress lines may precede it)
        start = min((i for i in (text.find("{"), text.find("[")) if i >= 0), default=-1)
        data = None
        if start >= 0:
            try:
                data = json.loads(text[start:])
            except json.JSONDecodeError:
                data = None
        self._traces.append({"door": tool, "ms": ms, "chars": len(text), "http": 200 if code == 0 else 500})
        if code != 0:
            raise GbrainError(f"gbrain call {tool} exited {code}: {text[:200]}")
        if isinstance(data, dict) and data.get("error"):
            raise GbrainError(f"gbrain call {tool}: {data.get('error')}")
        return data

    # ── liveness ──────────────────────────────────────────────────────────
    def health(self) -> bool:
        try:
            return isinstance(self._call("get_stats", timeout=120), dict)
        except GbrainError:
            return False

    def warm_up(self) -> float | None:
        try:
            _, ms, _ = self._run(["call", "search", json.dumps({"query": "hello", "limit": 1})], timeout=300)
            return ms
        except GbrainError:
            return None

    # ── doors ─────────────────────────────────────────────────────────────
    def doors(self) -> list[str]:
        return list(DOORS)

    def door_cut(self, door: str) -> int | None:
        if door == "pack":
            return self.pack_tokens * 4
        if door == "two-step":
            return self.two_step_budget
        return self.search_cut or None

    def _two_step(self, query: str, payload: str) -> tuple[str, dict]:
        """Brief with identifiers (search with 120-char snippets, the named
        entity cards first), then get_page on each identifier in that order
        until the budget is full: adebench.twostep.compose."""
        from adebench.twostep import compose
        t0 = time.perf_counter()
        r = self.ask(query)   # the same retrieval; the brief is its identifiers
        hits = self._results(self._call("search", {"query": query, "limit": 8, "snippet_chars": 120}))
        ids = [c["key"][5:] for c in r.get("cards", [])]
        lines = [f"- {c['key'][5:]}: {c['content'][:120]}" for c in r.get("cards", [])]
        for h in hits:
            sl = str(h.get("slug", ""))
            if sl and sl not in ids:
                ids.append(sl)
                lines.append(f"- {sl}: {self._text_of(h)[:120]}")
        brief = f"BRIEF for '{query}' (fetch by identifier):\n" + "\n".join(lines)
        cache: dict[str, str] = {}

        def fetch(sl: str) -> str:
            if sl not in cache:
                try:
                    cache[sl] = self._card_text(self._call("get_page", {"slug": sl}))
                except GbrainError:
                    cache[sl] = ""
            return cache[sl]

        text, info = compose(brief, ids, fetch, self.two_step_budget, payload)
        r["_ms"] = round((time.perf_counter() - t0) * 1000)
        r["_two_step"] = info
        return text, r

    @staticmethod
    def _results(data) -> list[dict]:
        if isinstance(data, list):
            return [x for x in data if isinstance(x, dict)]
        if isinstance(data, dict):
            for k in ("results", "items", "hits", "pages"):
                if isinstance(data.get(k), list):
                    return [x for x in data[k] if isinstance(x, dict)]
        return []

    @staticmethod
    def _text_of(hit: dict) -> str:
        for k in ("chunk_text", "snippet", "content", "text", "summary"):
            if hit.get(k):
                return str(hit[k])
        return ""

    def _facts(self, data) -> list[dict]:
        if isinstance(data, dict) and isinstance(data.get("facts"), list):
            return [f for f in data["facts"] if isinstance(f, dict)]
        return self._results(data)

    def ask(self, query: str) -> dict:
        hits = self._results(self._call("search", {"query": query, "limit": 8, "snippet_chars": 0}))
        facts = []
        try:
            facts = self._facts(self._call("recall", {"query": query, "limit": 8}))
        except GbrainError:
            pass
        # gbrain tells the agent how each hit matched: `evidence`
        # (keyword_exact, high_vector_match, weak_semantic...) and
        # `create_safety` (exists / probable / unknown). When every hit is a
        # weak semantic neighbour the query names something the memory does
        # not know: that is gbrain's own signal, passed on as unknown terms,
        # and the hits are delivered as neighbours, not as an answer.
        weak = bool(hits) and all(str(h.get("evidence", "")).startswith("weak") and not h.get("keyword_hit")
                                  for h in hits)
        cards, semantic, lines = [], [], []
        named = self._named_cards(query)
        weak = weak and not named   # a question that names a known entity is not about an unknown thing
        for c in named:
            cards.append(c)
            lines.append(f"  ▣ {c['key'][5:].rsplit('/', 1)[-1].upper()}: {c['content']}")
        named_slugs = {c["key"][5:] for c in named}
        if weak:
            hits = hits[:2]   # neighbours by meaning only: two, like any vector floor would keep
        for h in hits:
            slug, title = str(h.get("slug", "")), str(h.get("title") or h.get("slug", ""))
            text = self._text_of(h)
            # the age reaches the model either way: the page's own date when
            # the frontmatter has one, otherwise gbrain's fallback (updated_at),
            # which is what the Brain does with created_at
            date = str(h.get("effective_date") or "")[:10]
            if date:
                text = f"[dal {date}] {text}"
            by_meaning = not h.get("keyword_hit")
            entry = {"source": f"{'semantic_vec' if by_meaning else 'gbrain'}:{slug}", "content": text,
                     "score": h.get("score"), "evidence": h.get("evidence"), "create_safety": h.get("create_safety")}
            semantic.append(entry)
            if slug in named_slugs:
                continue   # already delivered as a card, first
            if str(h.get("type", "")).lower() in ENTITY_TYPES and not weak:
                cards.append({"key": f"card:{slug}", "content": text})
                lines.append(f"  ▣ {title.upper()}: {text}")
            else:
                lines.append(f"  ✦ [{slug}] {text}")
        working = [{"key": str(f.get("id", "")), "value": str(f.get("fact", ""))} for f in facts if f.get("fact")]
        parts = []
        unknown: list[str] = []
        if weak:
            seen = " ".join(self._text_of(h) for h in hits).lower()
            unknown = [t for t in re.findall(r"[a-zA-Z]{5,}", query) if t.lower() not in seen][:5] or [query[:40]]
            parts.append("UNKNOWN TERMS: " + ", ".join(unknown)
                         + "\n  No exact match in memory (evidence: weak_semantic on every hit): say so instead of guessing.")
        card_lines = [ln for ln in lines if ln.startswith("  ▣")]
        hit_lines = [ln for ln in lines if not ln.startswith("  ▣")]
        if card_lines:
            parts.append("CARDS:\n" + "\n".join(card_lines))
        if hit_lines:
            parts.append(("NEAREST PAGES (no direct match):\n" if weak else "SEARCH:\n") + "\n".join(hit_lines))
        if working:
            parts.append("REMEMBERED:\n" + "\n".join(f"  {w['value']}" for w in working))
        summary = f"CONTEXT for '{query}':\n\n" + "\n\n".join(parts) if parts else f"No result for '{query}'."
        out = {"summary": summary, "semantic": semantic, "working": working, "_ms": self._traces[-1]["ms"] if self._traces else 0}
        if cards:
            out["cards"] = cards
        if unknown:
            out["unknown_terms"] = unknown
        return out

    def door_text(self, query: str, door: str) -> tuple[str, dict]:
        from adebench.ade import competing_payload   # the same simulated payload every adapter uses
        payload = competing_payload(CFG.pressure)
        if door == "two-step":
            return self._two_step(query, payload)
        r = self.ask(query)
        if door == "pack":
            slugs = [c["key"][5:] for c in r.get("cards", [])] or \
                    [s["source"][7:] for s in r.get("semantic", [])[:3]]
            if not slugs:
                return "", r
            pack = self._call("context_pack", {"entities": ",".join(slugs), "budget_tokens": self.pack_tokens})
            text = pack.get("text") if isinstance(pack, dict) else None
            if not text:
                text = json.dumps(pack, ensure_ascii=False)
            return (payload + str(text))[: self.pack_tokens * 4], r
        summary = r["summary"]
        if payload and "CARDS:" in summary:
            head, _, tail = summary.partition("\n\nSEARCH:")
            text = head + "\n\n" + payload + ("SEARCH:" + tail if tail else "")
        else:
            text = payload + summary
        return (text[: self.search_cut] if self.search_cut else text), r

    # ── entity cards ──────────────────────────────────────────────────────
    def cards(self) -> list[dict]:
        out = []
        for t in ("person", "company", "project"):
            try:
                pages = self._results(self._call("list_pages", {"type": t, "limit": 40}))
            except GbrainError:
                continue
            for p in pages:
                slug = str(p.get("slug", ""))
                if not slug:
                    continue
                try:
                    page = self._call("get_page", {"slug": slug, "include_content": True})
                except GbrainError:
                    continue
                content = self._card_text(page)
                out.append({"entity": slug.rsplit("/", 1)[-1], "content": content,
                            "date": str(page.get("updated_at") or page.get("created_at") or "")[:10]
                            if isinstance(page, dict) else ""})
        return out

    def corrections(self) -> list[dict]:
        return []

    def aliases(self) -> list[dict]:
        return []

    # ── facts ─────────────────────────────────────────────────────────────
    def update_trace(self) -> dict:
        return {}

    def event_date_share(self) -> tuple[int, int]:
        return (0, 0)

    # ── episodes ──────────────────────────────────────────────────────────
    def recent_days(self, n: int) -> list[str]:
        since = (datetime.now() - timedelta(days=60)).strftime("%Y-%m-%d")
        try:
            rows = self._results(self._call("chronicle_since", {"date": since, "limit": 300}))
        except GbrainError:
            return []
        days = sorted({str(r.get("date") or r.get("occurred_at") or r.get("created_at") or "")[:10] for r in rows}
                      - {""}, reverse=True)
        return days[:n]

    def episodes_of_day(self, day: str, limit: int) -> list[dict]:
        try:
            rows = self._results(self._call("chronicle_day", {"date": day, "limit": limit}))
        except GbrainError:
            return []
        return [{"created_at": str(r.get("date") or r.get("occurred_at") or day),
                 "repl": str(r.get("kind") or r.get("type") or "chronicle"),
                 "input_summary": str(r.get("title") or r.get("text") or r.get("summary") or ""),
                 "output_summary": ""} for r in rows][:limit]

    def signed_episodes(self, prefix: str) -> int:
        return 0

    # ── working memory: the memory verbs ──────────────────────────────────
    def working_write(self, session: str, key: str, value: str, ttl_hours: int) -> bool:
        # gbrain's remember is append-only: a key-value overwrite is "forget
        # the previous fact for this key, then remember the new one"
        old = self._remembered.get((session, key))
        if old:
            try:
                self._call("forget", {"id": old, "reason": "adebench overwrite"})
            except GbrainError:
                pass
        r = self._call("remember", {"fact": f"[{key}] {value}", "provenance": f"adebench:{session}:{key}",
                                    "ttl": f"{ttl_hours}h"})
        fid = str(r.get("id", "")) if isinstance(r, dict) else ""
        if fid:
            self._remembered[(session, key)] = fid
        return bool(fid)

    def working_read(self, session: str, key: str):
        try:
            facts = self._facts(self._call("recall", {"grep": f"[{key}]", "limit": 5}))
        except GbrainError:
            return None
        for f in facts:
            if f"[{key}]" in str(f.get("fact", "")):
                return str(f["fact"])
        return None

    def working_clear(self, session: str) -> None:
        ids = {fid for (s, _k), fid in self._remembered.items() if s == session}
        try:
            for f in self._facts(self._call("recall", {"grep": "[adebench", "limit": 50})):
                src = str(f.get("provenance") or f.get("source") or "")
                if src.startswith(f"adebench:{session}:") and f.get("id") is not None:
                    ids.add(str(f["id"]))
        except GbrainError:
            pass
        for fid in ids:
            try:
                self._call("forget", {"id": fid, "reason": "adebench cleanup"})
            except GbrainError:
                pass
        self._remembered = {k: v for k, v in self._remembered.items() if k[0] != session}

    def working_age_minutes(self, session: str, key: str) -> float | None:
        return None

    # ── files and graph ───────────────────────────────────────────────────
    def file_search(self, query: str, limit: int) -> list[str]:
        return []

    def _slug_of(self, entity: str) -> str | None:
        hits = self._results(self._call("search", {"query": entity, "limit": 3}))
        for h in hits:
            slug = str(h.get("slug", ""))
            if slug.rsplit("/", 1)[-1] == entity or slug == entity:
                return slug
        return str(hits[0].get("slug")) if hits else None

    def graph_edges(self, entity: str) -> int:
        slug = self._slug_of(entity)
        if not slug:
            return 0
        n = 0
        for tool in ("get_links", "get_backlinks"):
            try:
                n += len(self._results(self._call(tool, {"slug": slug})))
            except GbrainError:
                pass
        return n

    def graph_orphans(self) -> tuple[int, int]:
        try:
            h = self._call("get_health")
        except GbrainError:
            return (0, 0)
        if not isinstance(h, dict):
            return (0, 0)
        orphans = h.get("orphans") if isinstance(h.get("orphans"), int) else (h.get("orphans") or {}).get("count", 0)
        pages = h.get("pages") if isinstance(h.get("pages"), int) else (h.get("pages") or {}).get("total", 0)
        return (int(orphans or 0), int(pages or 0))

    def graph_counts(self) -> dict:
        try:
            s = self._call("get_stats")
        except GbrainError:
            return {}
        return s if isinstance(s, dict) else {}

    # ── report-only ───────────────────────────────────────────────────────
    def health_report(self) -> tuple[dict, list[str]]:
        try:
            h = self._call("get_health")
            return (h if isinstance(h, dict) else {}), []
        except GbrainError as e:
            return {}, [str(e)]

    def measured_doors(self) -> list[str]:
        return ["search", "context_pack", "recall"]

    def traces(self) -> list[dict]:
        return self._traces

    def probe_doors(self, questions: list[str]) -> None:
        pass

    # ── optional: what the MCP server declares ────────────────────────────
    def declared_bytes(self) -> int | None:
        try:
            out, _, code = self._run(["--tools-json"], timeout=120)
        except GbrainError:
            return None
        return len(out.encode("utf-8")) if code == 0 and out.strip() else None
