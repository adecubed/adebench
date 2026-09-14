"""The two-step door: a brief with stable identifiers, then fetches, under
ONE budget.

Some memories do not hand over an answer in one call. They return a brief
(one line per hit, an identifier each) and let the agent fetch the detail
it wants. That is a door too, and it is measured like the others: the text
the agent has after the two steps, cut at the same budget as a one-call
door, with the latency of every call summed.

The rule is fixed and declared, so two memories are compared on the same
policy: the brief is delivered first, then the competing payload (if any),
then the details in the order the brief lists them, until the next one
would not fit. No detail is fetched that cannot fit: a client with a
budget does not pay for what it cannot read. What the agent could choose
better with judgement is exactly what this door does not measure.

`detail_chars` caps every fetched detail: the client policy "read the head
of many items" instead of "read few items whole". Both are two-step doors;
which one wins under a given budget is a finding about the budget, so the
cap is part of the setup and reported.
"""
from __future__ import annotations

from typing import Callable


def compose(brief: str, ids: list[str], fetch: Callable[[str], str], budget: int,
            payload: str = "", detail_chars: int = 0) -> tuple[str, dict]:
    """(text, info): the delivered text and what it cost in calls."""
    parts = [brief.rstrip()]
    used = len(parts[0]) + len(payload)
    fetched, skipped = [], []
    for i in ids:
        if used >= budget:
            skipped.append(i)
            continue
        detail = (fetch(i) or "").strip()
        if detail_chars and len(detail) > detail_chars:
            detail = detail[:detail_chars].rstrip() + " […]"
        block = f"\n\n[{i}]\n{detail}"
        if used + len(block) > budget:
            skipped.append(i)
            continue   # a later, shorter detail may still fit
        parts.append(block)
        fetched.append(i)
        used += len(block)
    text = parts[0] + ("\n\n" + payload if payload else "") + "".join(parts[1:])
    return text[:budget], {"brief_chars": len(parts[0]), "fetched": fetched, "skipped": skipped,
                           "calls": 1 + len(fetched) + len(skipped), "detail_chars": detail_chars or None}
