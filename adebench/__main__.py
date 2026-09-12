"""python -m adebench — run the memory benchmark and save the report."""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from adebench import adapter, report, sections
from adebench.config import CFG

ORDER = ["door", "cards", "updates", "time", "live_state", "abstention", "file_search", "graph"]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="adebench", description="Benchmark of a personal AI memory, on its own terms.")
    ap.add_argument("--adapter", help=f"'module:Class' adapter (default {CFG.adapter})")
    ap.add_argument("--brain", help=f"memory service URL (default {CFG.brain_url})")
    ap.add_argument("--door", help="door measured by the 'door' section (the adapter lists them)")
    ap.add_argument("--cases", help="folder with questions.json and abstention.json")
    ap.add_argument("--history", help="folder for the run reports")
    ap.add_argument("--repo", help="repository root for the file-search section")
    ap.add_argument("--sandbox-test", help="sandbox test script of the fact-update mechanism")
    ap.add_argument("--sections", nargs="*", choices=ORDER, help="only these sections")
    ap.add_argument("--no-sandbox-test", action="store_true", help="skip the sandbox test (faster)")
    ap.add_argument("--no-report", action="store_true", help="do not save to the history folder")
    ap.add_argument("--validation", action="store_true",
                    help="write validation.md next to the cases, with the memory's real answers")
    args = ap.parse_args(argv)
    if args.adapter:
        CFG.adapter = args.adapter
    if args.brain:
        CFG.brain_url = args.brain.rstrip("/")
    if args.door:
        CFG.door = args.door
    if args.cases:
        CFG.cases = Path(args.cases)
    if args.history:
        CFG.history = Path(args.history)
    if args.repo:
        CFG.repo = Path(args.repo)
    if args.sandbox_test:
        CFG.sandbox_test = Path(args.sandbox_test)

    try:
        ada = adapter.load(CFG.adapter)
    except Exception as e:  # noqa: BLE001
        print(f"adapter {CFG.adapter}: {e}")
        return 2
    adapter.use(ada)
    doors = ada.doors()
    if CFG.door not in doors:
        if args.door:
            print(f"door '{CFG.door}' unknown to this adapter; available: {', '.join(doors)}")
            return 2
        CFG.door = doors[0]
    if not ada.health():
        print(f"memory service off, unreachable or answering with errors at {CFG.brain_url}")
        return 2
    if args.validation:
        from adebench.validation import write_sheet
        ada.warm_up()
        print(f"validation sheet: {write_sheet()}")
        return 0

    chosen = args.sections or ORDER
    print(f"adebench — adapter {CFG.adapter} on {CFG.brain_url} — door: {CFG.door} — sections: {', '.join(chosen)}")
    ms = ada.warm_up()
    print(f"  warm-up: {'%.0f ms' % ms if ms else 'failed'}")

    results: list[dict] = []
    semantic_seen: list[dict] = []
    t_start = time.perf_counter()
    for name in ORDER:
        if name not in chosen:
            continue
        t0 = time.perf_counter()
        print(f"  {name}…", end="", flush=True)
        try:
            if name == "door":
                s = sections.door()
                semantic_seen = s.pop("_semantic", [])
            elif name == "updates":
                s = sections.updates(with_sandbox=not args.no_sandbox_test)
            elif name == "time":
                s = sections.time_section(semantic_seen)
            else:
                s = getattr(sections, name)()
        except Exception as e:  # noqa: BLE001
            # a section that blows up is an ERROR with zero points, not a skip
            s = sections._section(name, [sections._case(f"section {name}", False,
                                                        f"{type(e).__name__}: {str(e)[:160]}", status="ERROR")])
        k = s.get("counts", {})
        print(f" {k.get('PASS', 0)} PASS {k.get('FAIL', 0)} FAIL {k.get('ERROR', 0)} ERROR {k.get('SKIP', 0)} SKIP "
              f"({time.perf_counter() - t0:.0f}s)")
        results.append(s)

    print("  health…", end="", flush=True)
    results.append(sections.health())
    print(" ok")
    print("  doors…", end="", flush=True)
    results.append(sections.doors())
    print(" ok")

    # the sandbox test as it was EFFECTIVELY used: a path that --no-sandbox-test
    # switched off must not look like the same setup as a run that ran it
    sandbox_enabled = bool(CFG.sandbox_test) and not args.no_sandbox_test
    config = {"adapter": CFG.adapter, "brain_url": CFG.brain_url, "door": CFG.door,
              "cases_hash": report.cases_hash(),
              "voice_sources": CFG.voice_sources, "voice_cut": CFG.voice_cut,
              "events_block": CFG.events_block, "weights": sections.WEIGHTS, "max_card": CFG.max_card,
              # posix form: the same setup must fingerprint the same on Windows and Linux
              "cases": CFG.cases.as_posix(),
              "repo": CFG.repo.as_posix() if CFG.repo else None,
              "sandbox_test": CFG.sandbox_test.as_posix() if sandbox_enabled else None,
              "sandbox_enabled": sandbox_enabled,
              "sections": chosen, "duration_s": round(time.perf_counter() - t_start)}
    config["fingerprint"] = report.fingerprint(config)
    if args.no_report:
        points, measured, not_run, total = report.total_score(results)
        run = {"when": "-", "total": points, "measured_weight": measured, "not_run_weight": not_run,
               "total_weight": total, "counts": report.counts(results), "config": config, "sections": results,
               "delta": {"total": None, "sections": {}}}
        report.print_summary(run, Path("-"))
        return 0
    pj, pm, run = report.save(results, config)
    report.print_summary(run, pm)
    return 0


if __name__ == "__main__":
    sys.exit(main())
