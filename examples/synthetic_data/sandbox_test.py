"""Sandbox test of the synthetic memory's update mechanism.

The benchmark scores the 'updates' section only through a script like this
one: it exercises the mechanism on a throwaway copy and prints one PASS or
FAIL line per check plus "N/M passed". Here the "mechanism" is a tiny
in-memory store with the same rule as the reference Brain: a new fact that
shares most of its words with an old one supersedes it.
"""
from __future__ import annotations

import re
import sys


def words(t: str) -> set[str]:
    return set(re.findall(r"[a-z0-9.]{3,}", t.lower()))


class Store:
    def __init__(self):
        self.facts: dict[str, dict] = {}

    def write(self, key: str, content: str) -> str | None:
        new = words(content)
        for k, f in self.facts.items():
            if f["superseded"]:
                continue
            old = words(f["content"])
            short = min(len(old), len(new))
            if short and len(old & new) / short >= 0.6 and min(len(old), len(new)) / max(len(old), len(new)) >= 0.5:
                f["superseded"] = True
                self.facts[key] = {"content": content, "superseded": False, "supersedes": k}
                return k
        self.facts[key] = {"content": content, "superseded": False, "supersedes": None}
        return None

    def live(self) -> list[str]:
        return [f["content"] for f in self.facts.values() if not f["superseded"]]


def main() -> int:
    results = []

    def check(name: str, ok: bool):
        results.append(ok)
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")

    s = Store()
    s.write("port_v1", "The Brain listens on port 8010 and starts before the clients.")
    old = s.write("port_v2", "The Brain listens on port 8766 and starts before the clients.")
    check("a fact that changes one word supersedes the old one", old == "port_v1")
    check("the old value is gone from the live facts", not any("8010" in c for c in s.live()))
    check("the new value is live", any("8766" in c for c in s.live()))
    s.write("long", "The calendar is read every fifteen minutes from the work account and cached for one hour.")
    frag = s.write("short", "calendar read every fifteen minutes")
    check("a short fragment does not supersede a rich fact", frag is None)
    n_ok = sum(results)
    print(f"{n_ok}/{len(results)} passed")
    return 0 if n_ok == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
