"""Two runs side by side: `python -m adebench.compare brain.json gbrain.json`.

Two memories are comparable on a section only when both measured it; the
table says "not measured" where one did not, and the bottom line is the
score on the sections BOTH measured, next to each run's own score. The
golden set must be the same (cases hash): otherwise the table is printed
with a warning, and no bottom line.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def load(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _sections(run: dict) -> dict[str, dict]:
    return {s["name"]: s for s in run.get("sections", []) if s.get("weight")}


def compare(a: dict, b: dict, label_a: str = "A", label_b: str = "B") -> tuple[str, dict]:
    sa, sb = _sections(a), _sections(b)
    names = [n for n in sa] + [n for n in sb if n not in sa]
    same_cases = (a.get("config") or {}).get("cases_hash") == (b.get("config") or {}).get("cases_hash")
    rows, common_w, pa, pb = [], 0, 0.0, 0.0
    for n in names:
        x, y = sa.get(n), sb.get(n)
        w = (x or y)["weight"]

        def cell(s):
            if s is None:
                return "not run"
            if s.get("score") is None:
                return "not measured"
            k = s.get("counts", {})
            return f"{round(s['score'] * w, 1)}/{w}  ({k.get('PASS', 0)}P {k.get('FAIL', 0)}F {k.get('ERROR', 0)}E {k.get('SKIP', 0)}S)"
        both = x is not None and y is not None and x.get("score") is not None and y.get("score") is not None
        if both:
            common_w += w
            pa += x["score"] * w
            pb += y["score"] * w
        rows.append((n, cell(x), cell(y), "" if both else "excluded from the common score"))
    w1, w2 = max(len(r[1]) for r in rows) + 2, max(len(r[2]) for r in rows) + 2
    lines = [f"{'section':<14}{label_a:<{w1}}{label_b:<{w2}}"]
    for n, c1, c2, note in rows:
        lines.append(f"{n:<14}{c1:<{w1}}{c2:<{w2}}{note}")
    lines.append("")
    lines.append(f"{'own score':<14}{a.get('total')}/{a.get('measured_weight'):<{w1 - 4}}{b.get('total')}/{b.get('measured_weight')}")
    summary = {"common_weight": common_w, "same_cases": same_cases,
               label_a: round(pa, 1) if common_w else None, label_b: round(pb, 1) if common_w else None}
    if not same_cases:
        lines.append("WARNING: different golden sets (cases hash): the sections are not comparable question by question")
    elif common_w:
        lines.append(f"{'common':<14}{round(pa, 1)}/{common_w:<{w1 - 4}}{round(pb, 1)}/{common_w}"
                     f"   on the {common_w} points both measured")
    ca, cb = a.get("config") or {}, b.get("config") or {}
    lines.append(f"doors: {label_a} '{ca.get('door')}' · {label_b} '{cb.get('door')}'"
                 + ("" if ca.get("pressure") == cb.get("pressure") else
                    f"   pressure differs ({ca.get('pressure')} vs {cb.get('pressure')})"))
    return "\n".join(lines), summary


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if len(argv) < 2:
        print("usage: python -m adebench.compare A.json B.json [labelA labelB]")
        return 2
    la, lb = (argv[2], argv[3]) if len(argv) >= 4 else (Path(argv[0]).stem[:12], Path(argv[1]).stem[:12])
    text, _ = compare(load(argv[0]), load(argv[1]), la, lb)
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
