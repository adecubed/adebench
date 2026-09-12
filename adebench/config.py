"""Runtime configuration: which adapter talks to the memory, which door is
measured, where the cases and the history live. Everything can be set from
the command line or the environment; nothing is imported from the memory
system's own code."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

PACKAGE = Path(__file__).resolve().parent
ROOT = PACKAGE.parent


def _list(value: str) -> list[str]:
    return [v.strip() for v in value.split(",") if v.strip()]


@dataclass
class Config:
    # The adapter: 'module:Class' implementing adebench.adapter.Adapter.
    adapter: str = os.environ.get("ADEBENCH_ADAPTER", "adebench.ade:AdeAdapter")
    brain_url: str = os.environ.get("ADEBENCH_BRAIN_URL", "http://localhost:8766")
    # Door measured by the 'door' section (the adapter lists the valid ones).
    door: str = os.environ.get("ADEBENCH_DOOR", "voice")
    # ADE voice door: the sources the voice client really asks for, the cut it
    # applies, whether it puts a "latest events" block before the answer.
    voice_sources: list[str] = field(default_factory=lambda: _list(
        os.environ.get("ADEBENCH_VOICE_SOURCES", "working,semantic,episodic,conversations,files")))
    voice_cut: int = int(os.environ.get("ADEBENCH_VOICE_CUT", "2400"))
    events_block: bool = os.environ.get("ADEBENCH_EVENTS_BLOCK", "1") not in ("0", "false", "no")
    # Folder with questions.json and abstention.json (the golden set).
    cases: Path = Path(os.environ.get("ADEBENCH_CASES", str(ROOT / "cases" / "example")))
    # Where the run reports go.
    history: Path = Path(os.environ.get("ADEBENCH_HISTORY", str(ROOT / "history")))
    # Repository root for the file-search section. Empty = section skipped.
    repo: Path | None = Path(os.environ["ADEBENCH_REPO"]) if os.environ.get("ADEBENCH_REPO") else None
    # Optional sandbox test of the fact-update mechanism (prints "N/M passed" or "N/M passati").
    sandbox_test: Path | None = Path(os.environ["ADEBENCH_SANDBOX_TEST"]) if os.environ.get("ADEBENCH_SANDBOX_TEST") else None
    # Max length of an entity card.
    max_card: int = int(os.environ.get("ADEBENCH_MAX_CARD", "900"))
    # Live-state freshness check: which key must be fresher than N minutes.
    live_state_session: str = os.environ.get("ADEBENCH_LIVE_STATE_SESSION", "global")
    live_state_key: str = os.environ.get("ADEBENCH_LIVE_STATE_KEY", "mail_non_lette")
    live_state_max_minutes: int = int(os.environ.get("ADEBENCH_LIVE_STATE_MINUTES", "30"))
    # How many alias→card and file-search cases to sample per run.
    alias_sample: int = 8
    file_sample: int = 15


CFG = Config()
