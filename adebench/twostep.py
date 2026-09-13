"""The two-step door: a brief with stable identifiers, then fetches, under
ONE budget.

Some memories do not hand over an answer in one call. They return a brief
(one line per hit, an identifier each) and let the agent fetch the detail
it wants. That is a door too, and it is measured like the others: the text
the agent has after the two steps, cut at the same budget as a one-call
door, with the latency of every call summed.

The rule is fixed and declared, so two memories are compared on the same
policy: the brief is delivered first, then the competing payload (if any),
then the details in the order the brief lists them, each in full, until the
next one would not fit. No detail is fetched that cannot fit: a client with
a budget does not pay for what it cannot read. What the agent could choose
better with judgement is exactly what this door does not measure.
"""
from __future__ import annotations

from typing import Callable


def compose(brief: str, ids: list[str], fetch: Callable[[str], str], budget: int,
            payload: str = "") -> tuple[str, dict]:
    """(text, info): the delivered text and what it cost in calls."""
    parts = [brief.rstrip()]
    used = len(parts[0]) + len(payload)
    fetched, skipped = [], []
    for i in ids:
        if used >= budget:
            skipped.append(i)
            continue
        detail = fetch(i) or ""
        block = f"\n\n[{i}]\n{detail.strip()}"
        if used + len(block) > budget:
            skipped.append(i)
            continue   # a later, shorter detail may still fit
        parts.append(block)
        fetched.append(i)
        used += len(block)
    text = parts[0] + ("\n\n" + payload if payload else "") + "".join(parts[1:])
    return text[:budget], {"brief_chars": len(parts[0]), "fetched": fetched, "skipped": skipped,
                           "calls": 1 + len(fetched) + len(skipped)}
