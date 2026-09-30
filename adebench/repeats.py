"""Summarise the repeated runs of one memory, and rank memories with ties.

    python -m adebench.repeats examples/mem0_report              # runs/ -> repeats.json, reference.*
    python -m adebench.repeats examples/agentmemory_report runs_gemini   # -> repeats_gemini.json, reference_gemini.*

A memory with a model inside does not give the same number twice, and on 55
core points one probe is worth about 1.8. So the board shows the mean and the
range of every run kept in the report folder, the raw reports stay in the
repository, and the reference report (the one the memory's page details) is
the median run by core, then by total; with an even number of runs, the lower
of the two middle ones.

Two memories are level when their means are closer than the wider of their
two bands, a band being a memory's own range and never less than one probe:
a memory measured once has no range, and must not look more precise than one
that was measured five times.
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

from adebench.site import core

PROBE = 1.8   # 55 core points over the core probes of the synthetic set, about one probe


def summarize(runs: list[dict]) -> dict:
    rows = []
    for d in runs:
        pts, w, _ = core(d)
        rows.append({"when": d.get("when"), "core": pts, "core_weight": w, "total": d.get("total"),
                     "measured": d.get("measured_weight")})
    cores = [r["core"] for r in rows]
    totals = [r["total"] for r in rows]
    ordered = sorted(rows, key=lambda r: (r["core"], r["total"]))
    ref = ordered[(len(ordered) - 1) // 2]
    return {"builds": len(rows), "runs": rows,
            "core": {"mean": round(sum(cores) / len(cores), 1), "min": min(cores), "max": max(cores),
                     "weight": max(r["core_weight"] for r in rows)},
            "total": {"mean": round(sum(totals) / len(totals), 1), "min": min(totals), "max": max(totals),
                      "measured": max(r["measured"] for r in rows)},
            "reference": ref["when"]}


def write(folder: Path, runs_dir: str = "runs") -> dict:
    """Read <folder>/<runs_dir>/*.json, write the repeats file and copy the median
    run as the reference report (runs -> reference.*, runs_x -> reference_x.*)."""
    folder = Path(folder)
    suffix = runs_dir[len("runs"):]            # "" or "_gemini"
    files = sorted((folder / runs_dir).glob("*.json"))
    if not files:
        raise SystemExit(f"no runs in {folder / runs_dir}")
    runs = [json.loads(f.read_text(encoding="utf-8")) for f in files]
    s = summarize(runs)
    ref = files[[d.get("when") for d in runs].index(s["reference"])]
    s["reference_file"] = f"{runs_dir}/{ref.name}"
    s["files"] = [f"{runs_dir}/{f.name}" for f in files]
    (folder / f"repeats{suffix}.json").write_text(json.dumps(s, indent=1) + "\n", encoding="utf-8")
    shutil.copyfile(ref, folder / f"reference{suffix}.json")
    if ref.with_suffix(".md").exists():
        shutil.copyfile(ref.with_suffix(".md"), folder / f"reference{suffix}.md")
    return s


def ranks(board: list[tuple[float, float]]) -> list[int]:
    """board: (mean core points, range) per memory. A memory's rank is one plus
    the number of memories clearly ahead of it: ahead by more than the wider of
    the two bands, each band at least one probe."""
    band = [max(spread, PROBE) for _, spread in board]
    rank = [1 + sum(1 for j, (mj, _) in enumerate(board) if mj - mi > max(band[i], band[j]))
            for i, (mi, _) in enumerate(board)]
    # a wide range ties a memory with more of the ones above it; it must not
    # lift it over a memory with a higher mean, so ranks never improve down the means
    best = 0
    for i in sorted(range(len(board)), key=lambda i: -board[i][0]):
        best = rank[i] = max(rank[i], best)
    return rank


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    out = write(Path(sys.argv[1]), sys.argv[2] if len(sys.argv) > 2 else "runs")
    c = out["core"]
    print(f"{out['builds']} runs · core mean {c['mean']} ({c['min']}-{c['max']}) · reference {out['reference_file']}")
