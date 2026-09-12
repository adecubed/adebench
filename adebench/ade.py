"""The adapter for an ADE Brain: HTTP on its endpoints, read-only SQLite on
its databases. This is the only file that knows the Brain's API. To bench
another memory system, write another class with the same methods (see
adebench/adattatore.py) and point --adattatore to it."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from adebench import client
from adebench.client import get, post, delete, sql, colonne
from adebench.config import CFG

PORTE = ("sofia", "agente", "grezza")


class AdattatoreADE:
    """Doors:
      sofia  — the voice client: its sources, its "latest events" block, its cut
      agente — what an MCP agent gets: orchestrator context + semantic search, no cut
      grezza — /sofia/ask with the Brain's default sources and no cut (upper bound)
    """

    def __init__(self) -> None:
        self._recenti: str | None = None

    # ── liveness ──────────────────────────────────────────────────────────
    def health(self) -> bool:
        return bool(client.health())

    def riscalda(self) -> float | None:
        return client.riscalda()

    # ── doors ─────────────────────────────────────────────────────────────
    def porte(self) -> list[str]:
        return list(PORTE)

    def _sorgenti(self, porta: str) -> list[str]:
        return CFG.sorgenti_sofia if porta == "sofia" else []

    def chiedi(self, query: str, porta: str | None = None) -> dict:
        porta = porta or CFG.porta
        r = client.ask(query, self._sorgenti(porta), include_raw=True)
        raw = r.get("raw") or {}
        out = {"summary": r.get("summary") or "", "_ms": r.get("_ms", 0)}
        for k in ("schede", "semantic", "episodic", "working", "sconosciuti"):
            if k in raw:
                out[k] = raw[k]
        return out

    def _blocco_recenti(self) -> str:
        """Replica of the LATEST EVENTS block the voice client puts before
        the answer when there is no entity card."""
        if self._recenti is not None:
            return self._recenti
        righe, per_fonte = [], {}
        eps = get("/memory/episodic/recent", limit=15)
        for e in eps if isinstance(eps, list) else []:
            if not isinstance(e, dict):
                continue
            fonte = str(e.get("repl", "?"))
            if per_fonte.get(fonte, 0) >= 3:
                continue
            per_fonte[fonte] = per_fonte.get(fonte, 0) + 1
            righe.append(f"[{str(e.get('created_at', ''))[:10]}] ({fonte}) "
                         f"{str(e.get('input_summary', ''))[:130]}")
            if len(righe) >= 8:
                break
        self._recenti = ("ULTIMI EVENTI (dal più recente; sofia_server = le tue giornate, "
                         "claude_code = lavoro al PC):\n" + "\n".join(righe) + "\n\n") if righe else ""
        return self._recenti

    def _come_sente_sofia(self, summary: str) -> str:
        eventi = self._blocco_recenti() if CFG.blocco_eventi else ""
        if "▣" in summary:
            return (summary + "\n\n" + eventi)[:CFG.taglio_sofia]
        return (eventi + summary)[:CFG.taglio_sofia]

    def testo_della_porta(self, query: str, porta: str) -> tuple[str, dict]:
        r = self.chiedi(query, porta)
        summary = r["summary"]
        if porta == "sofia":
            return self._come_sente_sofia(summary), r
        if porta == "agente":
            ctx = post("/brain/orchestrator/context", {"user_input": query, "limit_semantic": 5})
            testo = (ctx.get("context") or "") if isinstance(ctx, dict) else ""
            sem = post("/memory/semantic/search", query=query, limit=5)
            if isinstance(sem, list):
                testo += "\n" + "\n".join(str(x.get("content", "")) for x in sem if isinstance(x, dict))
            return testo, r
        return summary, r

    # ── entity cards ──────────────────────────────────────────────────────
    def schede(self) -> list[dict]:
        return [{"entita": r["key"].split(":", 1)[1], "content": r["content"] or "",
                 "data": r.get("last_reinforced") or r.get("created_at") or ""}
                for r in sql("brain_semantic.db",
                             "SELECT key, content, last_reinforced, created_at FROM semantic_memory "
                             "WHERE relation_type='scheda' AND superseded=0 ORDER BY key")]

    def correzioni(self) -> list[dict]:
        out = []
        for r in sql("brain_semantic.db", "SELECT key, content FROM semantic_memory "
                                          "WHERE relation_type='correzione' AND superseded=0 ORDER BY key"):
            # key = correzione:<entita>:<timestamp>
            parti = r["key"].split(":")
            out.append({"entita": parti[1] if len(parti) > 1 else "", "content": r["content"] or ""})
        return out

    def alias(self) -> list[dict]:
        return [{"alias": r["alias"], "canonico": r["canonico"]}
                for r in sql("brain_graph.db", "SELECT alias, canonico FROM entity_alias")]

    # ── facts ─────────────────────────────────────────────────────────────
    def traccia_aggiornamenti(self) -> dict:
        vivi = sql("brain_semantic.db", "SELECT relation_type, superseded, key FROM semantic_memory")
        n_sup = sum(1 for r in vivi if r["superseded"])
        n_upd = sum(1 for r in vivi if r["relation_type"] == "updates")
        motivi = {}
        if "motivo" in colonne("brain_semantic.db", "semantic_archive"):
            for r in sql("brain_semantic.db", "SELECT motivo, count(*) n FROM semantic_archive GROUP BY motivo"):
                motivi[str(r["motivo"])] = r["n"]

        def _v2(r):
            if r["relation_type"] in ("updates", "derives", "extends", "merged"):
                return True
            return r["relation_type"] == "fact" and not r["key"].startswith(("cross_", "folder:"))
        vive = [r for r in vivi if not r["superseded"]
                and r["relation_type"] not in ("scheda", "correzione", "antipattern")]
        quota = (sum(1 for r in vive if _v2(r)) / len(vive)) if vive else 0.0
        return {"superseded_vivi": n_sup, "relation_updates": n_upd, "archivio_per_motivo": motivi,
                "archivio_ha_colonne_v2": bool(motivi) or "motivo" in colonne("brain_semantic.db", "semantic_archive"),
                "quota_memoria_viva_v2": round(quota, 3)}

    def quota_event_date(self) -> tuple[int, int]:
        r = sql("brain_semantic.db",
                "SELECT count(*) n, sum(CASE WHEN event_date IS NOT NULL AND event_date!='' THEN 1 ELSE 0 END) d "
                "FROM semantic_memory WHERE superseded=0 AND relation_type NOT IN ('scheda','correzione','antipattern')")
        return (r[0]["d"] or 0, r[0]["n"]) if r else (0, 0)

    # ── episodes ──────────────────────────────────────────────────────────
    def giorni_recenti(self, quanti: int) -> list[str]:
        return [r["g"] for r in sql("brain_episodic.db",
                                    "SELECT DISTINCT substr(created_at,1,10) g FROM episodic_memory "
                                    "ORDER BY g DESC LIMIT ?", quanti)]

    def episodi_del_giorno(self, giorno: str, limit: int) -> list[dict]:
        eps = get("/memory/episodic/recent", limit=limit, day=giorno)
        return eps if isinstance(eps, list) else []

    def episodi_firmati(self, prefisso: str) -> int:
        r = sql("brain_episodic.db", "SELECT count(*) n FROM episodic_memory WHERE input_summary LIKE ?",
                prefisso + "%")
        return r[0]["n"] if r else 0

    # ── working memory ────────────────────────────────────────────────────
    def working_scrivi(self, sessione: str, chiave: str, valore: str, ttl_ore: int) -> bool:
        w = post("/memory/working/write", {"session_id": sessione, "key": chiave, "value": valore,
                                            "repl": "adebench", "ttl_hours": ttl_ore})
        return bool(isinstance(w, dict) and w.get("ok"))

    def working_leggi(self, sessione: str, chiave: str) -> Any:
        return get("/memory/working/read", session_id=sessione, key=chiave)

    def working_cancella(self, sessione: str) -> None:
        delete("/memory/working/clear", session_id=sessione)

    def working_eta_minuti(self, sessione: str, chiave: str) -> float | None:
        r = sql("brain_working.db", "SELECT created_at FROM working_memory WHERE session_id=? AND key=?",
                sessione, chiave)
        if not r or not r[0].get("created_at"):
            return None
        try:
            t = datetime.fromisoformat(str(r[0]["created_at"]).replace("Z", "+00:00"))
            if t.tzinfo is None:
                t = t.replace(tzinfo=timezone.utc)
            return (datetime.now(timezone.utc) - t).total_seconds() / 60
        except Exception:  # noqa: BLE001
            return None

    # ── files and graph ───────────────────────────────────────────────────
    def ricerca_file(self, query: str, limit: int) -> list[str]:
        r = post("/brain/memory/tool/search", {"query": query, "limit": limit})
        return [str(x.get("key", "")) for x in (r if isinstance(r, list) else []) if isinstance(x, dict)]

    def grafo_vicini(self, entita: str) -> int:
        g = get("/memory/graph/query", slug=entita, depth=1, limit=50)
        return len(g.get("edges", [])) if isinstance(g, dict) else 0

    def grafo_orfani(self) -> tuple[int, int]:
        fatti = {r["key"] for r in sql("brain_semantic.db", "SELECT key FROM semantic_memory")}
        nodi = [r["slug"] for r in sql("brain_graph.db", "SELECT slug FROM graph_nodes WHERE slug LIKE 'fact:%'")]
        return sum(1 for s in nodi if s[5:] not in fatti), len(nodi)

    def grafo_conteggi(self) -> dict:
        n = sql("brain_graph.db", "SELECT count(*) n FROM graph_nodes")
        a = sql("brain_graph.db", "SELECT count(*) n FROM graph_edges")
        return {"nodi": n[0]["n"] if n else 0, "archi": a[0]["n"] if a else 0}

    # ── report-only ───────────────────────────────────────────────────────
    def salute(self) -> tuple[dict, list[str]]:
        m: dict = {}
        vivi = sql("brain_semantic.db", "SELECT relation_type, key, confidence, content FROM semantic_memory WHERE superseded=0")
        m["fatti_vivi"] = len(vivi)
        arch = sql("brain_semantic.db", "SELECT count(*) n FROM semantic_archive")
        m["fatti_archiviati"] = arch[0]["n"] if arch else 0
        per_tipo: dict = {}
        prod = {"cross_": 0, "folder:": 0, "distiller/altro": 0}
        for r in vivi:
            per_tipo[r["relation_type"]] = per_tipo.get(r["relation_type"], 0) + 1
            if r["relation_type"] == "fact":
                k = "cross_" if r["key"].startswith("cross_") else "folder:" if r["key"].startswith("folder:") else "distiller/altro"
                prod[k] += 1
        m["per_relation_type"] = per_tipo
        m["fact_per_produttore"] = prod
        m["al_floor_0.3"] = sum(1 for r in vivi if (r["confidence"] or 0) <= 0.31)
        m["mojibake"] = sum(1 for r in vivi if "�" in (r["content"] or "") or "Ã" in (r["content"] or ""))
        pend = get("/memory/episodic/pending")
        m["episodi_da_distillare"] = pend.get("pending") if isinstance(pend, dict) else None
        st = get("/brain/stats")
        m["anomalie_non_riconosciute"] = st.get("unacknowledged_anomalies") if isinstance(st, dict) else None
        ep = sql("brain_episodic.db", "SELECT count(*) n FROM episodic_memory")
        m["episodi"] = ep[0]["n"] if ep else 0
        avvisi = []
        if m["mojibake"]:
            avvisi.append(f"{m['mojibake']} fatti vivi con testo corrotto (mojibake)")
        if (m["anomalie_non_riconosciute"] or 0) > 1000:
            avvisi.append(f"{m['anomalie_non_riconosciute']} anomalie dell'observer mai riconosciute")
        if prod["cross_"] > prod["distiller/altro"] * 3:
            avvisi.append("la memoria viva e' dominata dai pattern di cross-learning")
        return m, avvisi

    def porte_misurate(self) -> list[str]:
        return ["/sofia/ask", "/brain/memory/tool/search", "/brain/orchestrator/context"]

    def tracce(self) -> list[dict]:
        return client.tracce

    def sonda_porte(self, domande: list[str]) -> None:
        for q in domande:
            post("/brain/memory/tool/search", {"query": q, "limit": 5})
            post("/brain/orchestrator/context", {"user_input": q, "limit_semantic": 5})
