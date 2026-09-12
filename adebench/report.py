"""One run's report: JSON + markdown in the history folder, with the delta
against the previous COMPARABLE run — same adapter, same door, same golden
set (hash of the case files). Runs are identified by a timestamp with
seconds plus a short hash, so two runs in the same minute never collide."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path

from adebench.config import CFG

STATI = ("PASS", "FAIL", "ERROR", "SKIP")


def hash_casi() -> str:
    """Short hash of the golden set, so that a changed question set never
    gets compared with the previous one."""
    h = hashlib.sha1()
    for nome in ("domande.json", "astensione.json"):
        p = CFG.casi / nome
        if p.exists():
            h.update(nome.encode()); h.update(p.read_bytes())
    return h.hexdigest()[:10]


def punteggio_totale(sezioni: list[dict]) -> tuple[float, int, int]:
    """(points, measured weight, total weight). Sections not measured leave
    the denominator: the score is 'points out of measured weight'."""
    punti, misurato, totale = 0.0, 0, 0
    for s in sezioni:
        if not s.get("peso"):
            continue
        totale += s["peso"]
        if s.get("punteggio") is None:
            continue
        misurato += s["peso"]
        punti += s["punteggio"] * s["peso"]
    return round(punti, 1), misurato, totale


def conteggi(sezioni: list[dict]) -> dict:
    c = {s: 0 for s in STATI}
    for s in sezioni:
        for caso in s.get("casi", []):
            c[caso.get("stato", "FAIL")] = c.get(caso.get("stato", "FAIL"), 0) + 1
    return c


def _comparabile(corsa: dict, config: dict) -> bool:
    c = corsa.get("config") or {}
    return all(c.get(k) == config.get(k) for k in ("adattatore", "porta", "hash_casi"))


def _ultima_corsa(config: dict) -> dict | None:
    if not CFG.storico.exists():
        return None
    for f in sorted(CFG.storico.glob("*.json"), reverse=True):
        try:
            corsa = json.loads(f.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        if _comparabile(corsa, config):
            return corsa
    return None


def salva(sezioni: list[dict], config: dict) -> tuple[Path, Path, dict]:
    CFG.storico.mkdir(parents=True, exist_ok=True)
    config = dict(config)
    config.setdefault("hash_casi", hash_casi())
    prima = _ultima_corsa(config)
    quando = datetime.now()
    punti, misurato, totale = punteggio_totale(sezioni)
    corsa = {
        "quando": quando.isoformat(timespec="seconds"),
        "totale": punti, "peso_misurato": misurato, "peso_totale": totale,
        "conteggi": conteggi(sezioni),
        "config": config,
        "sezioni": [{k: v for k, v in s.items() if not k.startswith("_")} for s in sezioni],
    }
    delta = {"totale": None, "sezioni": {}}
    if prima:
        delta["totale"] = round(punti - prima.get("totale", 0), 1)
        prima_sez = {s["nome"]: s for s in prima.get("sezioni", [])}
        for s in sezioni:
            p = prima_sez.get(s["nome"])
            if p and p.get("punteggio") is not None and s.get("punteggio") is not None:
                delta["sezioni"][s["nome"]] = round((s["punteggio"] - p["punteggio"]) * s["peso"], 1)
        delta["rispetto_a"] = prima.get("quando")
    corsa["delta"] = delta
    impronta = hashlib.sha1(json.dumps(config, sort_keys=True, default=str).encode()).hexdigest()[:6]
    stem = f"{quando.strftime('%Y%m%d-%H%M%S')}-{impronta}"
    pj = CFG.storico / f"{stem}.json"
    pm = CFG.storico / f"{stem}.md"
    n = 1
    while pj.exists():
        n += 1
        pj = CFG.storico / f"{stem}-{n}.json"
        pm = CFG.storico / f"{stem}-{n}.md"
    pj.write_text(json.dumps(corsa, ensure_ascii=False, indent=1), encoding="utf-8")
    pm.write_text(markdown(corsa), encoding="utf-8")
    return pj, pm, corsa


def _fmt_delta(v) -> str:
    if v is None:
        return ""
    return f" ({'+' if v >= 0 else ''}{v})"


def _riga_score(corsa: dict) -> str:
    mis, tot = corsa.get("peso_misurato", 100), corsa.get("peso_totale", 100)
    s = f"{corsa['totale']} / {mis}{_fmt_delta(corsa['delta'].get('totale'))}"
    if mis != tot:
        s += f" — coverage {mis}/{tot}: {tot - mis} points not measured"
    return s


def markdown(corsa: dict) -> str:
    c = corsa.get("conteggi", {})
    righe = [f"# adebench — {corsa['quando']}", "",
             f"**Score: {_riga_score(corsa)}**",
             f"Cases: {c.get('PASS', 0)} PASS · {c.get('FAIL', 0)} FAIL · {c.get('ERROR', 0)} ERROR · {c.get('SKIP', 0)} SKIP"]
    cfg = corsa.get("config") or {}
    righe.append(f"Adapter `{cfg.get('adattatore')}` · door `{cfg.get('porta')}` · cases `{cfg.get('hash_casi')}`")
    if corsa["delta"].get("rispetto_a"):
        righe.append(f"Delta against the comparable run of {corsa['delta']['rispetto_a']}.")
    righe += ["", "| Section | Weight | Points | PASS/FAIL/ERROR/SKIP |", "|---|---|---|---|"]
    for s in corsa["sezioni"]:
        if not s.get("peso"):
            continue
        k = s.get("conteggi", {})
        stati = f"{k.get('PASS', 0)}/{k.get('FAIL', 0)}/{k.get('ERROR', 0)}/{k.get('SKIP', 0)}"
        if s.get("punteggio") is None:
            righe.append(f"| {s['nome']} | {s['peso']} | not measured | {stati} |")
            continue
        punti = round(s["punteggio"] * s["peso"], 1)
        d = corsa["delta"]["sezioni"].get(s["nome"])
        righe.append(f"| {s['nome']} | {s['peso']} | {punti}{_fmt_delta(d)} | {stati} |")
    for s in corsa["sezioni"]:
        righe += ["", f"## {s['nome']}"]
        if s.get("misure"):
            righe.append("")
            for k, v in s["misure"].items():
                righe.append(f"- {k}: `{json.dumps(v, ensure_ascii=False)}`")
        if s.get("avvisi"):
            righe.append("")
            for a in s["avvisi"]:
                righe.append(f"- ⚠ {a}")
        non_ok = [x for x in s["casi"] if x.get("stato", "FAIL") != "PASS"]
        if non_ok:
            righe += ["", "Not passed:"]
            for x in non_ok:
                righe.append(f"- {x.get('stato', 'FAIL')} {x['caso']}" + (f" — {x['nota']}" if x.get("nota") else ""))
    return "\n".join(righe) + "\n"


def stampa(corsa: dict, pm: Path):
    c = corsa.get("conteggi", {})
    print(f"\nadebench — score {_riga_score(corsa)}")
    print(f"  cases: {c.get('PASS', 0)} PASS · {c.get('FAIL', 0)} FAIL · {c.get('ERROR', 0)} ERROR · {c.get('SKIP', 0)} SKIP")
    for s in corsa["sezioni"]:
        if not s.get("peso"):
            continue
        k = s.get("conteggi", {})
        if s.get("punteggio") is None:
            print(f"  {s['nome']:<14} {'not measured':>17}   {k.get('SKIP', 0)} SKIP")
            continue
        d = corsa["delta"]["sezioni"].get(s["nome"])
        print(f"  {s['nome']:<14} {round(s['punteggio'] * s['peso'], 1):>5}/{s['peso']:<3}{_fmt_delta(d):<8} "
              f"{k.get('PASS', 0)} PASS {k.get('FAIL', 0)} FAIL {k.get('ERROR', 0)} ERROR {k.get('SKIP', 0)} SKIP")
    avvisi = [(s["nome"], a) for s in corsa["sezioni"] for a in s.get("avvisi", [])]
    if avvisi:
        print("  warnings:")
        for n, a in avvisi:
            print(f"    [{n}] {a}")
    print(f"  report: {pm}")
