"""The adebench sections. Each returns a dict:

    {"nome", "peso", "punteggio" (0..1), "casi": [{"caso", "ok", "nota"}],
     "misure": {...}, "avvisi": [...]}

Sections A-H count toward the score; 'salute' (health) and 'porte' (latency
and noise per door) are report-only: monitoring, not memory quality.

The sections know nothing about endpoints or tables: they talk to the
adapter (adebench/adattatore.py). Case names and notes are in Italian on
purpose: they are read by the person who owns the memory.
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

from adebench.adattatore import corrente
from adebench.config import CFG

PESI = {
    "porta": 25, "schede": 15, "aggiornamento": 10, "tempo": 10,
    "stato_vivo": 10, "astensione": 10, "ricerca_file": 10, "grafo": 10,
}


def _sez(nome: str, casi: list[dict], misure: dict | None = None,
         avvisi: list[str] | None = None, punteggio: float | None = None) -> dict:
    if punteggio is None:
        punteggio = (sum(1 for c in casi if c["ok"]) / len(casi)) if casi else 0.0
    return {"nome": nome, "peso": PESI.get(nome, 0), "punteggio": round(punteggio, 4),
            "casi": casi, "misure": misure or {}, "avvisi": avvisi or []}


def _caso(caso: str, ok: bool, nota: str = "", **extra) -> dict:
    d = {"caso": caso, "ok": bool(ok), "nota": nota}
    d.update(extra)
    return d


def _presente(testo: str, gruppo: list[str]) -> str | None:
    """The first alternative of the group present in the text (case-insensitive)."""
    t = testo.lower()
    for alt in gruppo:
        if alt.lower() in t:
            return alt
    return None


def _carica(nome: str):
    return json.loads((CFG.casi / nome).read_text(encoding="utf-8"))


# ─── A. The door ─────────────────────────────────────────────────────────────

def porta() -> dict:
    """What the client really receives through the configured door. A
    question passes when every group of expected words is in that text —
    not in the raw hits."""
    ada = corrente()
    domande = _carica("domande.json")
    casi, posizioni, lunghezze, raw_semantici = [], [], [], []
    for d in domande:
        testo, r = ada.testo_della_porta(d["domanda"], CFG.porta)
        summary = r.get("summary") or ""
        mancanti = [g for g in d["attese"] if not _presente(testo, g)]
        trovate = [_presente(testo, g) for g in d["attese"] if _presente(testo, g)]
        pos = min((testo.lower().find(t.lower()) for t in trovate), default=-1)
        scheda_ok = True
        if d.get("entita"):
            chiavi = [str(s.get("key", "")) for s in r.get("schede", [])]
            scheda_ok = any(k.endswith(d["entita"]) for k in chiavi)
        intero_ok = not [g for g in d["attese"] if not _presente(summary, g)]
        ok = not mancanti and scheda_ok
        nota = ""
        if mancanti:
            nota = "mancano " + " | ".join("/".join(g) for g in mancanti)
            if intero_ok:
                nota += " (c'erano nella risposta intera: persi da questa porta)"
        if not scheda_ok:
            nota += f" scheda {d['entita']} assente"
        casi.append(_caso(d["domanda"], ok, nota.strip(), posizione=pos,
                          chars=len(testo), ms=round(r.get("_ms", 0)),
                          validata=d.get("validata", False)))
        lunghezze.append(len(testo))
        if pos >= 0:
            posizioni.append(pos)
        raw_semantici.extend(r.get("semantic", []))
    misure = {
        "porta": CFG.porta,
        "domande": len(domande),
        "validate": sum(1 for d in domande if d.get("validata")),
        "posizione_media_risposta": round(statistics.mean(posizioni)) if posizioni else None,
        "chars_medi_testo_porta": round(statistics.mean(lunghezze)) if lunghezze else None,
    }
    avvisi = []
    if misure["validate"] < len(domande):
        avvisi.append(f"{len(domande) - misure['validate']} domande del golden set non ancora "
                      "validate (campo 'validata' in domande.json; vedi --validazione)")
    sez = _sez("porta", casi, misure, avvisi)
    sez["_semantici"] = raw_semantici
    return sez


# ─── B. Entity cards, corrections, aliases ───────────────────────────────────

def _voci_non_omettere(testo: str) -> list[str]:
    """'Nella scheda di X non omettere mai: a, b; c' -> ['a', 'b', 'c']."""
    m = re.search(r"non omettere mai\s*:\s*(.+)$", testo, re.IGNORECASE | re.DOTALL)
    if not m:
        return []
    return [v.strip(" .;") for v in re.split(r"[,;]\s*", m.group(1)) if len(v.strip()) > 3]


def _voce_presente(voce: str, scheda: str) -> bool:
    parole = [w for w in re.findall(r"[\w./@-]{4,}", voce.lower())]
    if not parole:
        return True
    dentro = sum(1 for w in parole if w in scheda.lower())
    return dentro / len(parole) >= 0.6


def schede() -> dict:
    """All derived from the data: every card exists, is dated, fits the
    limit and contains the 'non omettere mai' items of its corrections;
    every alias leads to the canonical card."""
    ada = corrente()
    righe = ada.schede()
    if not righe:
        return _sez("schede", [], {}, ["questa memoria non ha schede per entita': sezione saltata"], punteggio=0.0)
    correzioni = ada.correzioni()
    casi = []
    for s in righe:
        ent, testo = s["entita"], s["content"]
        casi.append(_caso(f"scheda {ent} esiste ed e' datata", bool(testo) and bool(s.get("data"))))
        casi.append(_caso(f"scheda {ent} entro {CFG.max_scheda} caratteri", len(testo) <= CFG.max_scheda,
                          f"{len(testo)} caratteri"))
        for c in correzioni:
            if c["entita"] != ent:
                continue
            for voce in _voci_non_omettere(c["content"]):
                casi.append(_caso(f"scheda {ent} contiene «{voce[:60]}»", _voce_presente(voce, testo)))
    alias = ada.alias()
    con_scheda = {s["entita"] for s in righe}
    random.seed(11)
    candidati = [a for a in alias if a["canonico"] in con_scheda and a["alias"] != a["canonico"]]
    for a in random.sample(candidati, min(CFG.alias_campione, len(candidati))):
        r = ada.chiedi(f"Cos'e' {a['alias'].replace('_', ' ')}?")
        chiavi = [str(s.get("key", "")) for s in r.get("schede", [])]
        casi.append(_caso(f"alias '{a['alias']}' porta alla scheda {a['canonico']}",
                          any(k.endswith(a["canonico"]) for k in chiavi), f"schede viste: {chiavi}"))
    misure = {"schede": len(righe), "correzioni": len(correzioni), "alias": len(alias),
              "alias_provati": min(CFG.alias_campione, len(candidati))}
    return _sez("schede", casi, misure)


# ─── C. Fact updates ─────────────────────────────────────────────────────────

def aggiornamento(con_collaudo: bool = True) -> dict:
    """Two layers: the HISTORICAL TRACE of updates (from the adapter) and the
    MECHANISM, exercised by an optional sandbox test script (CFG.collaudo)
    that prints "N/M passati"."""
    misure = corrente().traccia_aggiornamenti() or {}
    n_sup = misure.get("superseded_vivi", 0)
    n_upd = misure.get("relation_updates", 0)
    quota_v2 = misure.get("quota_memoria_viva_v2")
    casi = []
    if con_collaudo and CFG.collaudo:
        try:
            p = subprocess.run([sys.executable, str(CFG.collaudo)], cwd=str(CFG.collaudo.parent.parent),
                               capture_output=True, text=True, encoding="utf-8", errors="replace",
                               timeout=600, env={**os.environ, "PYTHONIOENCODING": "utf-8"})
            m = re.search(r"(\d+)/(\d+) passati", p.stdout)
            for riga in p.stdout.splitlines():
                riga = re.sub(r"\x1b\[[0-9;]*m", "", riga)
                if riga.strip().startswith(("PASS", "FAIL")):
                    casi.append(_caso("collaudo: " + riga.strip()[4:].strip().split("  —")[0],
                                      riga.strip().startswith("PASS")))
            misure["collaudo"] = f"{m.group(1)}/{m.group(2)}" if m else "nessun esito"
            if not m:
                misure["collaudo_errore"] = (p.stderr or p.stdout)[-400:]
        except Exception as e:  # noqa: BLE001
            casi.append(_caso("collaudo dedup in sandbox", False, str(e)[:200]))
    else:
        casi.append(_caso("traccia storica di aggiornamenti (superseded o updates > 0)", n_sup + n_upd > 0))
    avvisi = []
    if n_sup == 0 and n_upd == 0:
        avvisi.append("nessuna traccia di aggiornamento nella memoria viva: il dedup non ha ancora "
                      "lavorato o non ha trovato coppie")
    if quota_v2 is not None and quota_v2 < 0.5:
        avvisi.append(f"solo il {quota_v2:.0%} della memoria viva e' passata dalla pipeline v2")
    return _sez("aggiornamento", casi, misure, avvisi)


# ─── D. Age and time ─────────────────────────────────────────────────────────

def tempo(semantici_visti: list[dict] | None = None) -> dict:
    ada = corrente()
    casi = []
    sem = semantici_visti or []
    con_tag = sum(1 for s in sem if str(s.get("content", "")).startswith("[dal "))
    quota_tag = (con_tag / len(sem)) if sem else None
    if sem:
        casi.append(_caso(f"ricordi semantici con l'eta' attaccata ({con_tag}/{len(sem)})",
                          quota_tag >= 0.95, f"{quota_tag:.0%}"))
    d, n = ada.quota_event_date()
    giorni = ada.giorni_recenti(3)
    for g in giorni:
        eps = ada.episodi_del_giorno(g, 10)
        ok = bool(eps) and all(str(e.get("created_at", "")).startswith(g) for e in eps)
        casi.append(_caso(f"filtro per giorno {g} torna solo episodi di quel giorno", ok, f"{len(eps)} episodi"))
    n_pc2 = ada.episodi_firmati("[pc2]")
    if n_pc2:
        r = ada.chiedi("cosa ha fatto il pc2?")
        eps = r.get("episodic", [])
        casi.append(_caso("«cosa ha fatto il pc2?» pesca gli episodi firmati [pc2]",
                          any("[pc2" in str(e.get("input_summary", "")) for e in eps),
                          f"{len(eps)} episodi nella risposta"))
    misure = {"quota_ricordi_con_eta": None if quota_tag is None else round(quota_tag, 3),
              "fatti_con_event_date": f"{d}/{n}", "giorni_provati": giorni, "episodi_firmati_pc2": n_pc2}
    avvisi = []
    if n and d / n < 0.5:
        avvisi.append(f"solo {d} fatti su {n} hanno la data dell'evento: per gli altri l'eta' "
                      "che il modello sente e' la data di derivazione, non del fatto")
    return _sez("tempo", casi, misure, avvisi)


# ─── E. Live state (working memory) ──────────────────────────────────────────

def stato_vivo() -> dict:
    ada = corrente()
    casi = []
    gettone = uuid.uuid4().hex[:10]
    valore = f"canarino adebench {gettone}: la parola d'ordine di oggi e' girasole"
    try:
        casi.append(_caso("scrittura canarino in working memory",
                          ada.working_scrivi("adebench", "adebench_canarino", valore, 1)))
        testo, r = ada.testo_della_porta(f"parola d'ordine canarino adebench {gettone}", CFG.porta)
        wm = r.get("working", [])
        casi.append(_caso("il canarino appena scritto si ritrova dalla porta di recupero",
                          any(gettone in str(e.get("value", "")) for e in wm)))
        casi.append(_caso(f"…e arriva nel testo della porta '{CFG.porta}'", gettone in testo))
    finally:
        ada.working_cancella("adebench")
    casi.append(_caso("pulizia: sessione adebench vuota a fine corsa",
                      not ada.working_leggi("adebench", "adebench_canarino")))
    eta_min = ada.working_eta_minuti(CFG.stato_vivo_sessione, CFG.stato_vivo_chiave)
    casi.append(_caso(f"{CFG.stato_vivo_chiave} aggiornata da meno di {CFG.stato_vivo_max_minuti} minuti",
                      eta_min is not None and eta_min <= CFG.stato_vivo_max_minuti,
                      f"{eta_min:.0f} min" if eta_min is not None else "chiave assente"))
    return _sez("stato_vivo", casi, {"eta_stato_vivo_min": None if eta_min is None else round(eta_min)})


# ─── F. Abstention ───────────────────────────────────────────────────────────

def astensione() -> dict:
    """Invented entities: no card, episodes marked as 'no direct match',
    semantic reduced to near-by-meaning hits only (or nothing)."""
    ada = corrente()
    domande = _carica("astensione.json")
    casi, punteggi = [], []
    for d in domande:
        r = ada.chiedi(d)
        ok_scheda = not r.get("schede")
        eps = r.get("episodic", [])
        ok_epis = (not eps) or all(e.get("_fallback") for e in eps)
        sem = r.get("semantic", [])
        ok_sem = len(sem) <= 2 and all(str(s.get("source", "")).startswith("semantic_vec") for s in sem)
        p = (ok_scheda + ok_epis + ok_sem) / 3
        punteggi.append(p)
        nota = []
        if not ok_scheda:
            nota.append("ha tirato fuori una scheda")
        if not ok_epis:
            nota.append("episodi presentati come match diretti")
        if not ok_sem:
            nota.append(f"{len(sem)} fatti testuali per una cosa inesistente")
        if r.get("sconosciuti"):
            nota.append(f"segnalati sconosciuti: {r['sconosciuti']}")
        casi.append(_caso(d, p == 1.0, "; ".join(nota)))
    return _sez("astensione", casi, {"domande": len(domande)},
                punteggio=statistics.mean(punteggi) if punteggi else 0.0)


# ─── G. File search ──────────────────────────────────────────────────────────

def ricerca_file() -> dict:
    """Real functions sampled from the repo: the grep-replacement search
    must put the right file in the top 5."""
    if not CFG.repo:
        return _sez("ricerca_file", [], {}, ["nessun repo configurato (--repo): sezione saltata"], punteggio=0.0)
    ada = corrente()
    funzioni = []
    for p in sorted(CFG.repo.rglob("*.py")):
        parti = {x.lower() for x in p.parts}
        if parti & {"bcks", "backups", "__pycache__", "venv", ".venv", "venvs", "node_modules", "site-packages"}:
            continue
        if ".bak" in p.name or ".bck" in p.name:
            continue
        try:
            testo = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:  # noqa: BLE001
            continue
        for m in re.finditer(r"^def ([a-z][a-z0-9_]{11,})\(", testo, re.M):
            funzioni.append((m.group(1), p.relative_to(CFG.repo).as_posix()))
    random.seed(23)
    campione = random.sample(funzioni, min(CFG.file_campione, len(funzioni)))
    casi = []
    for nome, rel in campione:
        chiavi = [k.replace("\\", "/") for k in ada.ricerca_file(nome, 5)]
        ok = any(k.endswith(rel) for k in chiavi)
        casi.append(_caso(f"{nome} → {rel}", ok, "" if ok else f"top5: {[k[-45:] for k in chiavi]}"))
    return _sez("ricerca_file", casi, {"funzioni_indicizzabili": len(funzioni), "provate": len(campione)})


# ─── H. Graph ────────────────────────────────────────────────────────────────

def grafo() -> dict:
    ada = corrente()
    entita = [s["entita"] for s in ada.schede()]
    casi = []
    for ent in entita:
        n = ada.grafo_vicini(ent)
        casi.append(_caso(f"{ent}: archi nel grafo", n > 0, f"{n} archi"))
    orfani, totali = ada.grafo_orfani()
    casi.append(_caso("nodi fatto orfani = 0", orfani == 0, f"{orfani} orfani su {totali}"))
    misure = dict(ada.grafo_conteggi())
    misure["fact_orfani"] = orfani
    if not casi:
        return _sez("grafo", [], misure, ["nessuna entita' con scheda: sezione saltata"], punteggio=0.0)
    return _sez("grafo", casi, misure)


# ─── Report-only: health and doors ───────────────────────────────────────────

def salute() -> dict:
    m, avvisi = corrente().salute()
    return {"nome": "salute", "peso": 0, "punteggio": None, "casi": [], "misure": m, "avvisi": avvisi}


def porte() -> dict:
    """Latency and noise per door. The retrieval door was already called by
    the sections; the adapter probes the other doors on the golden questions."""
    ada = corrente()
    domande = _carica("domande.json")
    ada.sonda_porte([d["domanda"] for d in domande[:10]])
    misurate = set(ada.porte_misurate())
    per_porta: dict = {}
    for t in ada.tracce():
        p = t["porta"]
        if p not in misurate:
            continue
        per_porta.setdefault(p, {"ms": [], "chars": []})
        per_porta[p]["ms"].append(t["ms"])
        per_porta[p]["chars"].append(t["chars"])

    def _p(v, q):
        if not v:
            return None
        v = sorted(v)
        return round(v[min(len(v) - 1, int(q * len(v)))])
    m = {}
    for p, v in per_porta.items():
        m[p] = {"chiamate": len(v["ms"]), "ms_p50": _p(v["ms"], 0.5), "ms_p95": _p(v["ms"], 0.95),
                "chars_medi": round(statistics.mean(v["chars"])) if v["chars"] else None}
    avvisi = []
    if CFG.porta == "sofia":
        ask = m.get("/sofia/ask", {})
        if ask.get("chars_medi") and ask["chars_medi"] > CFG.taglio_sofia * 1.5:
            avvisi.append(f"la porta di recupero produce in media {ask['chars_medi']} caratteri: piu' di una "
                          f"volta e mezza quello che il modello vocale puo' sentire ({CFG.taglio_sofia})")
    return {"nome": "porte", "peso": 0, "punteggio": None, "casi": [], "misure": m, "avvisi": avvisi}
