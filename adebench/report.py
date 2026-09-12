"""One run's report: JSON + markdown in the history folder, with the delta
against the previous run."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from adebench.config import CFG


def punteggio_totale(sezioni: list[dict]) -> float:
    tot = 0.0
    for s in sezioni:
        if s.get("punteggio") is None or not s.get("peso"):
            continue
        tot += s["punteggio"] * s["peso"]
    return round(tot, 1)


def _ultima_corsa() -> dict | None:
    """The latest previous run THROUGH THE SAME DOOR: a delta between the
    voice door and the agent door would compare two different things."""
    if not CFG.storico.exists():
        return None
    for f in sorted(CFG.storico.glob("*.json"), reverse=True):
        try:
            corsa = json.loads(f.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        if (corsa.get("config") or {}).get("porta", "sofia") == CFG.porta:
            return corsa
    return None


def salva(sezioni: list[dict], config: dict) -> tuple[Path, Path, dict]:
    CFG.storico.mkdir(parents=True, exist_ok=True)
    prima = _ultima_corsa()
    quando = datetime.now()
    totale = punteggio_totale(sezioni)
    corsa = {
        "quando": quando.isoformat(timespec="seconds"),
        "totale": totale,
        "config": config,
        "sezioni": [{k: v for k, v in s.items() if not k.startswith("_")} for s in sezioni],
    }
    delta = {"totale": None, "sezioni": {}}
    if prima:
        delta["totale"] = round(totale - prima.get("totale", 0), 1)
        prima_sez = {s["nome"]: s for s in prima.get("sezioni", [])}
        for s in sezioni:
            p = prima_sez.get(s["nome"])
            if p and p.get("punteggio") is not None and s.get("punteggio") is not None:
                delta["sezioni"][s["nome"]] = round((s["punteggio"] - p["punteggio"]) * s["peso"], 1)
        delta["rispetto_a"] = prima.get("quando")
    corsa["delta"] = delta
    stem = quando.strftime("%Y%m%d-%H%M")
    pj = CFG.storico / f"{stem}.json"
    pm = CFG.storico / f"{stem}.md"
    pj.write_text(json.dumps(corsa, ensure_ascii=False, indent=1), encoding="utf-8")
    pm.write_text(markdown(corsa), encoding="utf-8")
    return pj, pm, corsa


def _fmt_delta(v) -> str:
    if v is None:
        return ""
    return f" ({'+' if v >= 0 else ''}{v})"


def markdown(corsa: dict) -> str:
    righe = [f"# adebench — {corsa['quando']}", "",
             f"**Score: {corsa['totale']} / 100**{_fmt_delta(corsa['delta'].get('totale'))}"]
    if corsa["delta"].get("rispetto_a"):
        righe.append(f"Delta against the run of {corsa['delta']['rispetto_a']}.")
    righe += ["", "| Section | Weight | Points | Cases ok |", "|---|---|---|---|"]
    for s in corsa["sezioni"]:
        if s.get("punteggio") is None:
            continue
        ok = sum(1 for c in s["casi"] if c["ok"])
        punti = round(s["punteggio"] * s["peso"], 1)
        d = corsa["delta"]["sezioni"].get(s["nome"])
        righe.append(f"| {s['nome']} | {s['peso']} | {punti}{_fmt_delta(d)} | {ok}/{len(s['casi'])} |")
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
        falliti = [c for c in s["casi"] if not c["ok"]]
        if falliti:
            righe += ["", "Failed:"]
            for c in falliti:
                righe.append(f"- ✗ {c['caso']}" + (f" — {c['nota']}" if c.get("nota") else ""))
    return "\n".join(righe) + "\n"


def stampa(corsa: dict, pm: Path):
    print(f"\nadebench — score {corsa['totale']}/100{_fmt_delta(corsa['delta'].get('totale'))}")
    for s in corsa["sezioni"]:
        if s.get("punteggio") is None:
            continue
        ok = sum(1 for c in s["casi"] if c["ok"])
        d = corsa["delta"]["sezioni"].get(s["nome"])
        print(f"  {s['nome']:<14} {round(s['punteggio'] * s['peso'], 1):>5}/{s['peso']:<3}{_fmt_delta(d):<8} {ok}/{len(s['casi'])} cases")
    avvisi = [(s["nome"], a) for s in corsa["sezioni"] for a in s.get("avvisi", [])]
    if avvisi:
        print("  warnings:")
        for n, a in avvisi:
            print(f"    [{n}] {a}")
    print(f"  report: {pm}")
