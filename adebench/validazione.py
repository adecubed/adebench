"""Validation sheet for the golden set: for every question, the expected
words and what the memory really answered (the text the chosen door
delivers), so whoever validates can judge at a glance whether question and
expectations are right.

    python -m adebench --validazione     → <casi>/validazione.md

How to validate: read validazione.md and fix domande.json:
  - wrong or incomplete expectations → change them;
  - question about a fact the memory never knew → drop it, or teach the
    fact (that is a memory defect, not a test defect);
  - question and expectations right → "validata": true.
The benchmark warns as long as one question is not validated.
"""
from __future__ import annotations

import json
from pathlib import Path

from adebench.adattatore import corrente
from adebench.config import CFG


def _presente(testo: str, gruppo: list[str]) -> bool:
    t = testo.lower()
    return any(a.lower() in t for a in gruppo)


def scrivi_scheda() -> Path:
    ada = corrente()
    domande = json.loads((CFG.casi / "domande.json").read_text(encoding="utf-8"))
    righe = ["# Validazione del golden set", "",
             "Per ogni domanda: le parole attese (gruppi in OR, tutti i gruppi devono esserci), "
             f"l'esito, e i primi 600 caratteri di quello che arriva dalla porta '{CFG.porta}'. "
             "Correggi `domande.json` e metti `\"validata\": true` quando la domanda e' giusta.", ""]
    for i, d in enumerate(domande, 1):
        testo, _ = ada.testo_della_porta(d["domanda"], CFG.porta)
        mancanti = [g for g in d["attese"] if not _presente(testo, g)]
        esito = "OK" if not mancanti else "MANCA " + " | ".join("/".join(g) for g in mancanti)
        stato = "validata" if d.get("validata") else "DA VALIDARE"
        righe += [f"## {i}. {d['domanda']}", "",
                  f"- attese: {' — '.join('/'.join(g) for g in d['attese'])}"
                  + (f" · scheda: {d['entita']}" if d.get("entita") else ""),
                  f"- esito: **{esito}** · {stato}", "",
                  "```", testo[:600].strip(), "```", ""]
    out = CFG.casi / "validazione.md"
    out.write_text("\n".join(righe), encoding="utf-8")
    return out
