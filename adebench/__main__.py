"""python -m adebench — run the memory benchmark and save the report."""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from adebench import adattatore, report, sezioni
from adebench.config import CFG

ORDINE = ["porta", "schede", "aggiornamento", "tempo", "stato_vivo",
          "astensione", "ricerca_file", "grafo"]


def main() -> int:
    ap = argparse.ArgumentParser(prog="adebench", description="Benchmark of a personal AI memory, on its own terms.")
    ap.add_argument("--adattatore", help=f"'module:Class' adapter (default {CFG.adattatore})")
    ap.add_argument("--brain", help=f"memory service URL (default {CFG.brain_url})")
    ap.add_argument("--porta", help="door measured by the 'porta' section (the adapter lists them)")
    ap.add_argument("--casi", help="folder with domande.json and astensione.json")
    ap.add_argument("--storico", help="folder for the run reports")
    ap.add_argument("--repo", help="repository root for the file-search section")
    ap.add_argument("--collaudo", help="sandbox test script of the fact-update mechanism")
    ap.add_argument("--sezioni", nargs="*", choices=ORDINE, help="only these sections")
    ap.add_argument("--senza-collaudo", action="store_true", help="skip the sandbox test (faster)")
    ap.add_argument("--senza-report", action="store_true", help="do not save to the history folder")
    ap.add_argument("--validazione", action="store_true",
                    help="write validazione.md next to the cases, with the memory's real answers")
    args = ap.parse_args()
    if args.adattatore:
        CFG.adattatore = args.adattatore
    if args.brain:
        CFG.brain_url = args.brain.rstrip("/")
    if args.porta:
        CFG.porta = args.porta
    if args.casi:
        CFG.casi = Path(args.casi)
    if args.storico:
        CFG.storico = Path(args.storico)
    if args.repo:
        CFG.repo = Path(args.repo)
    if args.collaudo:
        CFG.collaudo = Path(args.collaudo)

    try:
        ada = adattatore.carica(CFG.adattatore)
    except Exception as e:  # noqa: BLE001
        print(f"adapter {CFG.adattatore}: {e}")
        return 2
    adattatore.imposta(ada)
    porte = ada.porte()
    if CFG.porta not in porte:
        if args.porta:
            print(f"door '{CFG.porta}' unknown to this adapter; available: {', '.join(porte)}")
            return 2
        CFG.porta = porte[0]
    if not ada.health():
        print(f"memory service off or unreachable at {CFG.brain_url}")
        return 2
    if args.validazione:
        from adebench.validazione import scrivi_scheda
        ada.riscalda()
        print(f"validation sheet: {scrivi_scheda()}")
        return 0

    scelte = args.sezioni or ORDINE
    print(f"adebench — adapter {CFG.adattatore} on {CFG.brain_url} — door: {CFG.porta} — sections: {', '.join(scelte)}")
    ms = ada.riscalda()
    print(f"  warm-up: {'%.0f ms' % ms if ms else 'failed'}")

    esiti: list[dict] = []
    semantici: list[dict] = []
    t_inizio = time.perf_counter()
    for nome in ORDINE:
        if nome not in scelte:
            continue
        t0 = time.perf_counter()
        print(f"  {nome}…", end="", flush=True)
        try:
            if nome == "porta":
                s = sezioni.porta()
                semantici = s.pop("_semantici", [])
            elif nome == "aggiornamento":
                s = sezioni.aggiornamento(con_collaudo=not args.senza_collaudo)
            elif nome == "tempo":
                s = sezioni.tempo(semantici)
            else:
                s = getattr(sezioni, nome)()
        except Exception as e:  # noqa: BLE001
            s = {"nome": nome, "peso": sezioni.PESI.get(nome, 0), "punteggio": 0.0, "casi": [],
                 "misure": {}, "avvisi": [f"section failed: {type(e).__name__}: {e}"]}
        ok = sum(1 for c in s["casi"] if c["ok"])
        print(f" {ok}/{len(s['casi'])} ({time.perf_counter() - t0:.0f}s)")
        esiti.append(s)

    print("  salute…", end="", flush=True)
    esiti.append(sezioni.salute())
    print(" ok")
    print("  porte…", end="", flush=True)
    esiti.append(sezioni.porte())
    print(" ok")

    config = {"adattatore": CFG.adattatore, "brain_url": CFG.brain_url, "porta": CFG.porta,
              "sorgenti_sofia": CFG.sorgenti_sofia, "taglio_sofia": CFG.taglio_sofia,
              "blocco_eventi": CFG.blocco_eventi, "pesi": sezioni.PESI, "casi": str(CFG.casi),
              "repo": str(CFG.repo) if CFG.repo else None, "collaudo": str(CFG.collaudo) if CFG.collaudo else None,
              "sezioni": scelte, "durata_s": round(time.perf_counter() - t_inizio)}
    if args.senza_report:
        corsa = {"quando": "-", "totale": report.punteggio_totale(esiti), "sezioni": esiti,
                 "delta": {"totale": None, "sezioni": {}}}
        report.stampa(corsa, Path("-"))
        return 0
    pj, pm, corsa = report.salva(esiti, config)
    report.stampa(corsa, pm)
    return 0


if __name__ == "__main__":
    sys.exit(main())
