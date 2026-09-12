"""The adebench sections. Each returns a dict:

    {"nome", "peso", "punteggio" (0..1 or None = not measured),
     "casi": [{"caso", "stato": PASS|FAIL|ERROR|SKIP, "ok", "nota"}],
     "misure": {...}, "avvisi": [...]}

A case is PASS or FAIL when the check ran and had evidence; ERROR when the
memory system failed to answer (an HTTP error, an exception) — it counts as
a failure, never as a pass; SKIP when this memory has no such feature or no
data for the check — it is excluded from the score and shown as missing
coverage. A section with no PASS/FAIL/ERROR case is "not measured": its
weight leaves the denominator instead of scoring 0 or 1.

Sections A-H count toward the score; 'salute' (health) and 'porte' (latency
and noise per door) are report-only. The sections know nothing about
endpoints or tables: they talk to the adapter (adebench/adattatore.py).
Case names and notes are in Italian on purpose: they are read by the person
who owns the memory.
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
from typing import Callable

from adebench.adattatore import corrente
from adebench.config import CFG

PESI = {
    "porta": 25, "schede": 15, "aggiornamento": 10, "tempo": 10,
    "stato_vivo": 10, "astensione": 10, "ricerca_file": 10, "grafo": 10,
}
STATI = ("PASS", "FAIL", "ERROR", "SKIP")


def _caso(caso: str, ok: bool | None, nota: str = "", stato: str | None = None, **extra) -> dict:
    """ok=True → PASS, ok=False → FAIL, ok=None → SKIP; stato overrides."""
    if stato is None:
        stato = "SKIP" if ok is None else ("PASS" if ok else "FAIL")
    d = {"caso": caso, "stato": stato, "ok": stato == "PASS", "nota": nota}
    d.update(extra)
    return d


def _prova(caso: str, fn: Callable[[], dict]) -> dict:
    """Run one check; any exception becomes an ERROR case, never a PASS."""
    try:
        return fn()
    except Exception as e:  # noqa: BLE001
        return _caso(caso, False, f"{type(e).__name__}: {str(e)[:160]}", stato="ERROR")


def _sez(nome: str, casi: list[dict], misure: dict | None = None,
         avvisi: list[str] | None = None, punteggio: float | None = None) -> dict:
    misurati = [c for c in casi if c["stato"] != "SKIP"]
    if punteggio is None:
        punteggio = (sum(1 for c in misurati if c["stato"] == "PASS") / len(misurati)) if misurati else None
    conteggi = {s: sum(1 for c in casi if c["stato"] == s) for s in STATI}
    avvisi = list(avvisi or [])
    if punteggio is None and not any("non misurata" in a for a in avvisi):
        avvisi.append("sezione non misurata: nessun caso con evidenza (tutti SKIP o nessun caso)")
    return {"nome": nome, "peso": PESI.get(nome, 0),
            "punteggio": None if punteggio is None else round(punteggio, 4),
            "casi": casi, "conteggi": conteggi, "misure": misure or {}, "avvisi": avvisi}


def _presente(testo: str, gruppo: list[str]) -> str | None:
    """The first alternative of the group present in the text as a whole
    token: '8766' does not match '18766', '0.2.4' does not match '10.2.4'.
    Boundaries are enforced only where the alternative starts/ends with an
    alphanumeric character, so 'C:\\Users\\simon\\ade' still matches inside a
    longer path."""
    for alt in gruppo:
        prefisso = alt.endswith("*")  # 'anonimizz*' matches anonimizza/anonimizzazione
        nucleo = alt[:-1] if prefisso else alt
        if not nucleo:
            continue
        pat = re.escape(nucleo)
        if nucleo[0].isalnum():
            pat = r"(?<![0-9A-Za-z])" + pat
        if nucleo[-1].isalnum() and not prefisso:
            pat = pat + r"(?![0-9A-Za-z])"
        if re.search(pat, testo, re.IGNORECASE):
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

    def _una(d: dict) -> dict:
        testo, r = ada.testo_della_porta(d["domanda"], CFG.porta)
        summary = r.get("summary") or ""
        if not testo.strip() and not summary.strip():
            return _caso(d["domanda"], False, "risposta vuota dalla porta", stato="ERROR",
                         validata=d.get("validata", False))
        mancanti = [g for g in d["attese"] if not _presente(testo, g)]
        trovate = [_presente(testo, g) for g in d["attese"] if _presente(testo, g)]
        pos = min((testo.lower().find(t.lower()) for t in trovate), default=-1)
        scheda_ok = True
        if d.get("entita"):
            chiavi = [str(s.get("key", "")) for s in r.get("schede", [])]
            scheda_ok = any(k.endswith(d["entita"]) for k in chiavi)
        intero_ok = not [g for g in d["attese"] if not _presente(summary, g)]
        nota = ""
        if mancanti:
            nota = "mancano " + " | ".join("/".join(g) for g in mancanti)
            if intero_ok:
                nota += " (c'erano nella risposta intera: persi da questa porta)"
        if not scheda_ok:
            nota += f" scheda {d['entita']} assente"
        lunghezze.append(len(testo))
        if pos >= 0:
            posizioni.append(pos)
        raw_semantici.extend(r.get("semantic", []))
        return _caso(d["domanda"], not mancanti and scheda_ok, nota.strip(), posizione=pos,
                     chars=len(testo), ms=round(r.get("_ms", 0)), validata=d.get("validata", False))

    for d in domande:
        casi.append(_prova(d["domanda"], lambda d=d: _una(d)))
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
        return _sez("schede", [_caso("schede per entita'", None, "questa memoria non ne ha")],
                    {}, ["sezione non misurata: nessuna scheda per entita' in questa memoria"])
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
        nome = f"alias '{a['alias']}' porta alla scheda {a['canonico']}"

        def _alias(a=a, nome=nome) -> dict:
            r = ada.chiedi(f"Cos'e' {a['alias'].replace('_', ' ')}?")
            chiavi = [str(s.get("key", "")) for s in r.get("schede", [])]
            return _caso(nome, any(k.endswith(a["canonico"]) for k in chiavi), f"schede viste: {chiavi}")
        casi.append(_prova(nome, _alias))
    misure = {"schede": len(righe), "correzioni": len(correzioni), "alias": len(alias),
              "alias_provati": min(CFG.alias_campione, len(candidati))}
    return _sez("schede", casi, misure)


# ─── C. Fact updates ─────────────────────────────────────────────────────────

def aggiornamento(con_collaudo: bool = True) -> dict:
    """The MECHANISM, exercised by a sandbox test script (CFG.collaudo) that
    prints one PASS/FAIL line per check and "N/M passati". The historical
    trace of updates goes in the measures but does not score: an update that
    happened once does not prove the mechanism works today."""
    try:
        misure = dict(corrente().traccia_aggiornamenti() or {})
    except Exception as e:  # noqa: BLE001
        misure = {"traccia_errore": f"{type(e).__name__}: {str(e)[:120]}"}
    n_sup = misure.get("superseded_vivi", 0) or 0
    n_upd = misure.get("relation_updates", 0) or 0
    quota_v2 = misure.get("quota_memoria_viva_v2")
    casi = []
    avvisi = []
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
            if not m or p.returncode not in (0, 1):
                casi.append(_caso("collaudo del meccanismo di aggiornamento", False,
                                  (p.stderr or p.stdout)[-300:], stato="ERROR"))
        except Exception as e:  # noqa: BLE001
            casi.append(_caso("collaudo del meccanismo di aggiornamento", False, str(e)[:200], stato="ERROR"))
    else:
        casi.append(_caso("meccanismo di aggiornamento (serve --collaudo)", None,
                          "senza collaudo la traccia storica non fa punteggio"))
        avvisi.append("sezione non misurata: nessun collaudo del meccanismo (--collaudo); "
                      f"traccia storica: superseded={n_sup}, updates={n_upd}")
    if n_sup == 0 and n_upd == 0 and "traccia_errore" not in misure:
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
    casi.append(_caso(f"ricordi semantici con l'eta' attaccata ({con_tag}/{len(sem)})",
                      None if quota_tag is None else quota_tag >= 0.95,
                      f"{quota_tag:.0%}" if quota_tag is not None else "nessun ricordo semantico visto"))
    d, n = _prova_valore(lambda: ada.quota_event_date(), (0, 0))
    giorni = _prova_valore(lambda: ada.giorni_recenti(3), [])
    if not giorni:
        casi.append(_caso("filtro per giorno dell'episodica", None, "nessun episodio"))
    for g in giorni:
        def _giorno(g=g) -> dict:
            eps = ada.episodi_del_giorno(g, 10)
            ok = bool(eps) and all(str(e.get("created_at", "")).startswith(g) for e in eps)
            return _caso(f"filtro per giorno {g} torna solo episodi di quel giorno", ok, f"{len(eps)} episodi")
        casi.append(_prova(f"filtro per giorno {g}", _giorno))
    n_pc2 = _prova_valore(lambda: ada.episodi_firmati("[pc2]"), 0)
    if n_pc2:
        def _pc2() -> dict:
            r = ada.chiedi("cosa ha fatto il pc2?")
            eps = r.get("episodic", [])
            return _caso("«cosa ha fatto il pc2?» pesca gli episodi firmati [pc2]",
                         any("[pc2" in str(e.get("input_summary", "")) for e in eps),
                         f"{len(eps)} episodi nella risposta")
        casi.append(_prova("episodi firmati [pc2]", _pc2))
    else:
        casi.append(_caso("episodi firmati da un'altra macchina", None, "nessuno in questa memoria"))
    misure = {"quota_ricordi_con_eta": None if quota_tag is None else round(quota_tag, 3),
              "fatti_con_event_date": f"{d}/{n}", "giorni_provati": giorni, "episodi_firmati_pc2": n_pc2}
    avvisi = []
    if n and d / n < 0.5:
        avvisi.append(f"solo {d} fatti su {n} hanno la data dell'evento: per gli altri l'eta' "
                      "che il modello sente e' la data di derivazione, non del fatto")
    return _sez("tempo", casi, misure, avvisi)


def _prova_valore(fn: Callable, default):
    try:
        return fn()
    except Exception:  # noqa: BLE001
        return default


# ─── E. Live state (working memory) ──────────────────────────────────────────

def stato_vivo() -> dict:
    ada = corrente()
    casi = []
    gettone = uuid.uuid4().hex[:10]
    valore = f"canarino adebench {gettone}: la parola d'ordine di oggi e' girasole"
    try:
        casi.append(_prova("scrittura canarino", lambda: _caso(
            "scrittura canarino in working memory", ada.working_scrivi("adebench", "adebench_canarino", valore, 1))))

        def _ritrova() -> list[dict]:
            testo, r = ada.testo_della_porta(f"parola d'ordine canarino adebench {gettone}", CFG.porta)
            wm = r.get("working", [])
            return [_caso("il canarino appena scritto si ritrova dalla porta di recupero",
                          any(gettone in str(e.get("value", "")) for e in wm)),
                    _caso(f"…e arriva nel testo della porta '{CFG.porta}'", gettone in testo)]
        try:
            casi.extend(_ritrova())
        except Exception as e:  # noqa: BLE001
            casi.append(_caso("ritrovamento del canarino", False, f"{type(e).__name__}: {str(e)[:120]}", stato="ERROR"))
    finally:
        try:
            ada.working_cancella("adebench")
        except Exception:  # noqa: BLE001
            pass
    casi.append(_prova("pulizia", lambda: _caso(
        "pulizia: sessione adebench vuota a fine corsa", not ada.working_leggi("adebench", "adebench_canarino"))))
    eta_min = _prova_valore(lambda: ada.working_eta_minuti(CFG.stato_vivo_sessione, CFG.stato_vivo_chiave), None)
    casi.append(_caso(f"{CFG.stato_vivo_chiave} aggiornata da meno di {CFG.stato_vivo_max_minuti} minuti",
                      eta_min is not None and eta_min <= CFG.stato_vivo_max_minuti,
                      f"{eta_min:.0f} min" if eta_min is not None else "chiave assente"))
    return _sez("stato_vivo", casi, {"eta_stato_vivo_min": None if eta_min is None else round(eta_min)})


# ─── F. Abstention ───────────────────────────────────────────────────────────

def astensione() -> dict:
    """Invented entities: no card, episodes marked as 'no direct match',
    semantic reduced to near-by-meaning hits only (or nothing). This checks
    what retrieval hands to the model, not the model's final sentence."""
    ada = corrente()
    domande = _carica("astensione.json")
    casi, punteggi = [], []
    for d in domande:
        def _una(d=d) -> dict:
            r = ada.chiedi(d)
            if not r.get("summary", "").strip() and not any(k in r for k in ("schede", "semantic", "episodic")):
                return _caso(d, False, "risposta vuota: nessuna evidenza di astensione", stato="ERROR")
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
            return _caso(d, p == 1.0, "; ".join(nota), frazione=p)
        casi.append(_prova(d, _una))
    misurati = [c for c in casi if c["stato"] != "SKIP"]
    # partial credit per question (each of the three checks), errors count 0
    punteggio = (sum(c.get("frazione", 0.0) for c in misurati) / len(misurati)) if misurati else None
    return _sez("astensione", casi, {"domande": len(domande)}, punteggio=punteggio)


# ─── G. File search ──────────────────────────────────────────────────────────

def ricerca_file() -> dict:
    """Real functions sampled from the repo: the grep-replacement search
    must put the right file in the top 5."""
    if not CFG.repo:
        return _sez("ricerca_file", [_caso("ricerca file", None, "nessun repo configurato (--repo)")],
                    {}, ["sezione non misurata: nessun repo configurato (--repo)"])
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
        def _una(nome=nome, rel=rel) -> dict:
            chiavi = [k.replace("\\", "/") for k in ada.ricerca_file(nome, 5)]
            ok = any(k.endswith(rel) for k in chiavi)
            return _caso(f"{nome} → {rel}", ok, "" if ok else f"top5: {[k[-45:] for k in chiavi]}")
        casi.append(_prova(f"{nome} → {rel}", _una))
    if not casi:
        casi.append(_caso("ricerca file", None, "nessuna funzione campionabile nel repo"))
    return _sez("ricerca_file", casi, {"funzioni_indicizzabili": len(funzioni), "provate": len(campione)})


# ─── H. Graph ────────────────────────────────────────────────────────────────

def grafo() -> dict:
    ada = corrente()
    entita = [s["entita"] for s in _prova_valore(lambda: ada.schede(), [])]
    casi = []
    if not entita:
        casi.append(_caso("entita' con scheda nel grafo", None, "nessuna entita' con scheda"))
    for ent in entita:
        casi.append(_prova(f"{ent}: archi nel grafo", lambda ent=ent: (
            lambda n: _caso(f"{ent}: archi nel grafo", n > 0, f"{n} archi"))(ada.grafo_vicini(ent))))

    def _orfani() -> dict:
        orfani, totali = ada.grafo_orfani()
        if totali == 0:
            return _caso("nodi fatto orfani = 0", None, "il grafo non ha nodi fatto: niente da verificare")
        return _caso("nodi fatto orfani = 0", orfani == 0, f"{orfani} orfani su {totali}")
    casi.append(_prova("nodi fatto orfani", _orfani))
    misure = dict(_prova_valore(lambda: ada.grafo_conteggi(), {}))
    orf = next((c for c in casi if c["caso"].startswith("nodi fatto orfani")), None)
    misure["fact_orfani"] = orf["nota"] if orf else None
    return _sez("grafo", casi, misure)


# ─── Report-only: health and doors ───────────────────────────────────────────

def salute() -> dict:
    try:
        m, avvisi = corrente().salute()
    except Exception as e:  # noqa: BLE001
        m, avvisi = {}, [f"salute non disponibile: {type(e).__name__}: {str(e)[:120]}"]
    return {"nome": "salute", "peso": 0, "punteggio": None, "casi": [], "misure": m, "avvisi": avvisi}


def porte() -> dict:
    """Latency and noise per door. The retrieval door was already called by
    the sections; the adapter probes the other doors on the golden questions."""
    ada = corrente()
    domande = _carica("domande.json")
    try:
        ada.sonda_porte([d["domanda"] for d in domande[:10]])
    except Exception:  # noqa: BLE001
        pass
    misurate = set(ada.porte_misurate())
    per_porta: dict = {}
    for t in ada.tracce():
        p = t["porta"]
        if p not in misurate:
            continue
        per_porta.setdefault(p, {"ms": [], "chars": [], "errori": 0})
        per_porta[p]["ms"].append(t["ms"])
        per_porta[p]["chars"].append(t["chars"])
        if t.get("http", 200) != 200:
            per_porta[p]["errori"] += 1

    def _p(v, q):
        if not v:
            return None
        v = sorted(v)
        return round(v[min(len(v) - 1, int(q * len(v)))])
    m = {}
    for p, v in per_porta.items():
        m[p] = {"chiamate": len(v["ms"]), "errori_http": v["errori"], "ms_p50": _p(v["ms"], 0.5),
                "ms_p95": _p(v["ms"], 0.95), "chars_medi": round(statistics.mean(v["chars"])) if v["chars"] else None}
    avvisi = []
    if CFG.porta == "sofia":
        ask = m.get("/sofia/ask", {})
        if ask.get("chars_medi") and ask["chars_medi"] > CFG.taglio_sofia * 1.5:
            avvisi.append(f"la porta di recupero produce in media {ask['chars_medi']} caratteri: piu' di una "
                          f"volta e mezza quello che il modello vocale puo' sentire ({CFG.taglio_sofia})")
    return {"nome": "porte", "peso": 0, "punteggio": None, "casi": [], "misure": m, "avvisi": avvisi}
