"""Validation sheet for the golden set: for every question, the expected
words and what the memory really answered (the text the chosen door
delivers), so whoever validates can judge at a glance whether question and
expectations are right.

    python -m adebench --validation     → <cases>/validation.md

How to validate: read validation.md and fix questions.json:
  - wrong or incomplete expectations → change them;
  - question about a fact the memory never knew → drop it, or teach the
    fact (that is a memory defect, not a test defect);
  - question and expectations right → "validated": true.
The benchmark warns as long as one question is not validated.
"""
from __future__ import annotations

import json
from pathlib import Path

from adebench.adapter import current
from adebench.config import CFG
from adebench.sections import present


def write_sheet() -> Path:
    ada = current()
    questions = json.loads((CFG.cases / "questions.json").read_text(encoding="utf-8"))
    lines = ["# Golden set validation", "",
             "For each question: the expected words (groups in OR, every group must be present), "
             f"the outcome, and the first 600 characters delivered by door '{CFG.door}'. "
             "Fix `questions.json` and set `\"validated\": true` when the question is right.", ""]
    for i, q in enumerate(questions, 1):
        text, _ = ada.door_text(q["question"], CFG.door)
        missing = [g for g in q["expected"] if not present(text, g)]
        outcome = "OK" if not missing else "MISSING " + " | ".join("/".join(g) for g in missing)
        state = "validated" if q.get("validated") else "TO VALIDATE"
        lines += [f"## {i}. {q['question']}", "",
                  f"- expected: {' — '.join('/'.join(g) for g in q['expected'])}"
                  + (f" · card: {q['entity']}" if q.get("entity") else ""),
                  f"- outcome: **{outcome}** · {state}", "",
                  "```", text[:600].strip(), "```", ""]
    out = CFG.cases / "validation.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    return out
