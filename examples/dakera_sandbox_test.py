"""Sandbox test of Dakera's fact-update mechanism, for adebench's `updates`
section (`--sandbox-test`). It exercises Dakera's real API on a throwaway
namespace — nothing here touches the golden set — and prints one PASS/FAIL
line per check plus an "N/M passed" summary, which adebench parses.

    DAKERA_API_KEY=... python examples/dakera_sandbox_test.py

Checks:
  1. supersede-by-update: store a fact, PUT /v1/memory/update/{id} to the new
     value, and confirm recall serves the new value and never the retired one;
  2. dedup detection: store two identical facts and confirm
     /v1/knowledge/deduplicate finds the duplicate;
  3. importance update: POST /v1/memory/importance changes a memory's weight.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
import urllib.error

BASE = os.environ.get("DAKERA_URL", "http://localhost:3000")
KEY = os.environ.get("DAKERA_API_KEY", "")
NS = "adebench-sandbox"
TAG = "adebench-sandbox"


def _req(path, body=None, method="POST"):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method,
                                 headers={"Content-Type": "application/json",
                                          "Authorization": "Bearer " + KEY})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r), r.status
    except urllib.error.HTTPError as e:
        try:
            return json.load(e), e.code
        except Exception:
            return {}, e.code
    except Exception:
        return {}, 0


def store(content):
    d, _ = _req("/v1/memory/store", {"agent_id": NS, "content": content,
                                     "memory_type": "semantic", "importance": 0.7, "tags": [TAG]})
    return d.get("memory", d).get("id")


def recall(query):
    d, _ = _req("/v1/memory/recall", {"agent_id": NS, "query": query, "top_k": 5})
    return " ".join((m.get("memory", m).get("content", "")) for m in d.get("memories", []))


def cleanup():
    _req("/v1/memory/forget", {"agent_id": NS, "tags": [TAG]})


def main() -> int:
    cleanup()
    results = []

    # 1. supersede-by-update
    try:
        mid = store("The Zeta connector listens on port 8000.")
        _req("/v1/memory/update/%s?agent_id=%s" % (mid, NS), {"content": "The Zeta connector listens on port 9000."}, method="PUT")
        time.sleep(1)
        txt = recall("Zeta connector port")
        ok = ("9000" in txt) and ("8000" not in txt)
        results.append((ok, "supersede-by-update: the updated value is served, the retired one is not (%s)"
                        % ("9000 served, 8000 gone" if ok else "text=" + txt[:80])))
    except Exception as e:  # noqa: BLE001
        results.append((False, "supersede-by-update raised: %s" % e))

    # 2. dedup detection
    try:
        store("Backups run every Sunday at 03:00.")
        store("Backups run every Sunday at 03:00.")
        time.sleep(1)
        d, _ = _req("/v1/knowledge/deduplicate", {"agent_id": NS, "threshold": 0.9, "dry_run": True})
        found = int(d.get("duplicates_found", 0) or 0)
        ok = found >= 1
        results.append((ok, "dedup detects the duplicate fact (duplicates_found=%d)" % found))
    except Exception as e:  # noqa: BLE001
        results.append((False, "dedup raised: %s" % e))

    # 3. importance update
    try:
        mid = store("The owner prefers morning meetings.")
        d, code = _req("/v1/memory/importance", {"agent_id": NS, "memory_id": mid, "importance": 0.95})
        ok = code in (200, 201)
        results.append((ok, "importance update accepted (HTTP %s)" % code))
    except Exception as e:  # noqa: BLE001
        results.append((False, "importance update raised: %s" % e))

    cleanup()
    passed = sum(1 for ok, _ in results if ok)
    for ok, msg in results:
        print(("PASS " if ok else "FAIL ") + msg)
    print("%d/%d passed" % (passed, len(results)))
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
