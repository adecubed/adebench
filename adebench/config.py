"""Runtime configuration: which adapter talks to the memory, which door is
measured, where the cases and the history live. Everything can be set from
the command line or the environment; nothing is imported from the memory
system's own code."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

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
    # Simulated competing payload, in characters, placed where the client
    # puts its own variable-size blocks (events, long tool responses) before
    # the cut. 0 = a normal day. Part of the setup fingerprint.
    pressure: int = int(os.environ.get("ADEBENCH_PRESSURE", "0"))
    # A callwitness baseline (URL or file, schema callwitness.baseline.v1):
    # measured pressure levels (median / p95 / max of a tool response) and
    # the report-only 'census' section. None = no census.
    census: str | None = os.environ.get("ADEBENCH_CENSUS") or None
    # Run the door at every census level and report the passes at each.
    pressure_profile: bool = os.environ.get("ADEBENCH_PRESSURE_PROFILE", "") not in ("", "0", "false", "no")
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
    live_state_key: str = os.environ.get("ADEBENCH_LIVE_STATE_KEY", "mail_non_lette")  # empty = no such key (SKIP)
    live_state_max_minutes: int = int(os.environ.get("ADEBENCH_LIVE_STATE_MINUTES", "30"))
    # Signed episodes: a memory shared by several machines signs the episodes
    # of the others with a prefix. The probe asks about that machine in the
    # owner's language (the default is English; set the question in yours).
    signed_prefix: str = os.environ.get("ADEBENCH_SIGNED_PREFIX", "[pc2]")
    signed_question: str = os.environ.get("ADEBENCH_SIGNED_QUESTION", "what did pc2 do?")
    # Write-back probe (opt-in, --write-back): a degraded answer goes through
    # the memory's own write path and must not come back through the door.
    # {question} is replaced by the golden question: a real degraded answer
    # names its subject, which is what makes it retrievable next time.
    write_back: bool = os.environ.get("ADEBENCH_WRITE_BACK", "0").lower() in ("1", "true", "yes")
    degraded_answer: str = os.environ.get("ADEBENCH_DEGRADED_ANSWER",
                                          "I have no record of that. You asked: {question}")
    write_back_questions: int = int(os.environ.get("ADEBENCH_WRITE_BACK_QUESTIONS", "2"))
    write_back_wait_s: int = int(os.environ.get("ADEBENCH_WRITE_BACK_S", "10"))
    # Write-to-serve latency: how long the canary may take to become
    # retrievable after the write (polled every second). A memory with
    # asynchronous indexing pays here; the number is reported either way.
    write_to_serve_max_s: int = int(os.environ.get("ADEBENCH_WRITE_TO_SERVE_S", "30"))
    # How many canaries are written and timed: one number is a sample, a
    # p50/p95 needs a few. Each one costs the write-to-serve latency.
    write_to_serve_samples: int = int(os.environ.get("ADEBENCH_WRITE_TO_SERVE_SAMPLES", "3"))
    # How many alias→card and file-search cases to sample per run.
    alias_sample: int = 8
    file_sample: int = 15


CFG = Config()


# The day a memory lives in. A personal memory keeps its owner's day, not
# UTC: the reference Brain answers "episodes of the 15th" with an episode
# stamped 22:01Z on the 14th, because in Rome that is one past midnight.
# Explicit so a test can pin it (ADEBENCH_TZ, an IANA name); default: the
# timezone of the machine running the benchmark, which is the Brain's.
LOCAL_TZ = ZoneInfo(os.environ["ADEBENCH_TZ"]) if os.environ.get("ADEBENCH_TZ") else datetime.now().astimezone().tzinfo


def local_day(stamp: str) -> str:
    """'YYYY-MM-DD' of an ISO timestamp in LOCAL_TZ. A stamp without offset
    is taken as it is: nothing to convert."""
    try:
        dt = datetime.fromisoformat(str(stamp))
    except ValueError:
        return str(stamp)[:10]
    if dt.tzinfo is None:
        return dt.strftime("%Y-%m-%d")
    return dt.astimezone(LOCAL_TZ).strftime("%Y-%m-%d")
