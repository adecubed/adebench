"""Sandbox test of Memoose's update mechanism, on a throwaway dataset.

The harness's own update probe cannot run here: it hands a memory a plain
sentence (`write_fact`), and Memoose learns facts as triples a model has
extracted, so the engine alone has nothing to do with the sentence. This
script asks the same question through Memoose's own API instead: does a new
assertion retire the old value, with nobody saying which one it replaces?

    python -m adebench --adapter adebench.memoose:MemooseAdapter \
        --cases my/cases --sandbox-test examples/memoose_sandbox_test.py

Nothing here touches the benchmark's dataset: it writes into
`adebench-sandbox`, under a temporary MEMOOSE_DATA_DIR, and deletes it.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile

BIN = os.environ.get("ADEBENCH_MEMOOSE_BIN") or shutil.which("memoose") or "memoose"
DATASET = "adebench-sandbox"
ENTITY = "zetaprobe"


def run(data_dir: str, args: list[str], stdin: str | None = None) -> dict:
    env = {**os.environ, "MEMOOSE_DATA_DIR": data_dir, "PYTHONIOENCODING": "utf-8"}
    p = subprocess.run([BIN, "--json", "-d", DATASET] + args, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=300, input=stdin, env=env)
    if p.returncode != 0:
        raise RuntimeError(f"memoose {' '.join(args[:2])}: {(p.stderr or p.stdout)[:200]}")
    return json.loads(p.stdout) if p.stdout.strip() else {}


def remember(data_dir: str, target: str, text: str) -> dict:
    """One assertion, the way an agent makes it: a fact, with no id of what it
    replaces and no mention of the older value."""
    return run(data_dir, ["tool", "remember", "--stdin"], json.dumps({
        "entities": [{"name": ENTITY, "type": "System", "description": ""},
                     {"name": target, "type": "Concept", "description": ""}],
        "relations": [{"source": ENTITY, "name": "listens_on", "target": target,
                       "description": text}],
        "summary": text, "source_text": text}))


def live_targets(data_dir: str) -> list[str]:
    r = run(data_dir, ["recall", f"{ENTITY} listens on port", "-m", "facts", "-n", "10"])
    return [f["target"] for f in r.get("facts", []) if not f.get("superseded")]


def served_text(data_dir: str) -> str:
    r = run(data_dir, ["recall", f"what port does {ENTITY} listen on", "-n", "10"])
    parts = [f"{f['source']} {f['relation']} {f['target']}" for f in r.get("facts", [])]
    parts += [str(c.get("summary") or "") for c in r.get("chunks", [])]
    return " | ".join(parts)


def main() -> int:
    checks: list[tuple[str, bool, str]] = []
    data_dir = tempfile.mkdtemp(prefix="memoose-sandbox-")
    try:
        # 1 ── the default: two values for one relation, both alive
        remember(data_dir, "port_8000", f"The {ENTITY} connector listens on port 8000.")
        remember(data_dir, "port_9000", f"The {ENTITY} connector listens on port 9000.")
        live = live_targets(data_dir)
        checks.append(("a new value retires the old one on its own",
                       live == ["port_9000"],
                       f"live targets: {live or 'none'}"))

        # 2 ── the relation declared functional: Memoose's own supersession
        run(data_dir, ["tool", "declare_functional_relations", "--stdin"],
            json.dumps({"names": ["listens_on"]}))
        remember(data_dir, "port_9100", f"The {ENTITY} connector listens on port 9100.")
        live = live_targets(data_dir)
        checks.append(("with the relation declared functional, the newest value is the only live one",
                       live == ["port_9100"], f"live targets: {live or 'none'}"))

        # 3 ── what the door serves after the retirement
        text = served_text(data_dir)
        checks.append(("the retired values never reach the door again",
                       "8000" not in text and "9000" not in text,
                       "the answer still carries " + ", ".join(
                           v for v in ("8000", "9000") if v in text) if ("8000" in text or "9000" in text)
                       else "only the current value"))

        # 4 ── restating the current value must not pile up a copy
        remember(data_dir, "port_9100", f"The {ENTITY} connector listens on port 9100.")
        live = live_targets(data_dir)
        checks.append(("restating the current value leaves one fact, not two",
                       live.count("port_9100") == 1, f"live targets: {live or 'none'}"))
    finally:
        shutil.rmtree(data_dir, ignore_errors=True)

    for name, ok, note in checks:
        print(f"{'PASS' if ok else 'FAIL'} {name}" + (f"  —  {note}" if note else ""))
    passed = sum(1 for _, ok, _ in checks if ok)
    print(f"\n{passed}/{len(checks)} passed")
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    sys.exit(main())
