"""Runtime configuration: which adapter talks to the memory, which door is
measured, where the cases and the history live. Everything can be set from
the command line or the environment; nothing is imported from the memory
system's own code."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

PACCHETTO = Path(__file__).resolve().parent
RADICE = PACCHETTO.parent


def _lista(valore: str) -> list[str]:
    return [v.strip() for v in valore.split(",") if v.strip()]


@dataclass
class Config:
    # The adapter: 'module:Class' implementing adebench.adattatore.Adattatore.
    adattatore: str = os.environ.get("ADEBENCH_ADATTATORE", "adebench.ade:AdattatoreADE")
    brain_url: str = os.environ.get("ADEBENCH_BRAIN_URL", "http://localhost:8766")
    # Door measured by the 'porta' section (the adapter lists the valid ones).
    porta: str = os.environ.get("ADEBENCH_PORTA", "sofia")
    # ADE voice door: the sources the voice client really asks for, the cut it
    # applies, whether it puts a "latest events" block before the answer.
    sorgenti_sofia: list[str] = field(default_factory=lambda: _lista(
        os.environ.get("ADEBENCH_SORGENTI", "working,semantic,episodic,conversations,files")))
    taglio_sofia: int = int(os.environ.get("ADEBENCH_TAGLIO", "2400"))
    blocco_eventi: bool = os.environ.get("ADEBENCH_BLOCCO_EVENTI", "1") not in ("0", "false", "no")
    # Folder with domande.json and astensione.json (the golden set).
    casi: Path = Path(os.environ.get("ADEBENCH_CASI", str(RADICE / "casi" / "esempio")))
    # Where the run reports go.
    storico: Path = Path(os.environ.get("ADEBENCH_STORICO", str(RADICE / "storico")))
    # Repository root for the file-search section. Empty = section skipped.
    repo: Path | None = Path(os.environ["ADEBENCH_REPO"]) if os.environ.get("ADEBENCH_REPO") else None
    # Optional sandbox test of the fact-update mechanism (prints "N/M passati").
    collaudo: Path | None = Path(os.environ["ADEBENCH_COLLAUDO"]) if os.environ.get("ADEBENCH_COLLAUDO") else None
    # Max length of an entity card.
    max_scheda: int = int(os.environ.get("ADEBENCH_MAX_SCHEDA", "900"))
    # Live-state freshness check: which key must be fresher than N minutes.
    stato_vivo_sessione: str = os.environ.get("ADEBENCH_STATO_VIVO_SESSIONE", "global")
    stato_vivo_chiave: str = os.environ.get("ADEBENCH_STATO_VIVO_CHIAVE", "mail_non_lette")
    stato_vivo_max_minuti: int = int(os.environ.get("ADEBENCH_STATO_VIVO_MINUTI", "30"))
    # How many alias→card and file-search cases to sample per run.
    alias_campione: int = 8
    file_campione: int = 15


CFG = Config()
