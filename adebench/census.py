"""A callwitness baseline (schema callwitness.baseline.v1): the measured
distribution of what MCP servers return at runtime, per call and per server.

adebench reads it for two things:

- pressure levels that are measured instead of picked: `--pressure median`,
  `p95` or `max` resolve to the census percentiles of a single tool
  response (bytes, taken as characters); `--pressure-profile` runs the
  door at all three and reports the passes at each;
- the report-only 'census' section: where this memory's door sits in that
  distribution, and — when the document carries declared sizes — the
  declared-vs-returned ratio, the measure that reorders servers.

Two origins exist and are never treated as one: `census` is the published
document (https://callwitness.tech/baseline/v1.json, 29 servers, one
machine); `local` is a file the user generated with `callwitness baseline`
against their own servers. A document without an origin field is `census`
only when it comes from the published URL; anything else is `unknown` and
the report says so.

Depend on this document, not on the raw census JSONL: within v1 fields may
be added but names, units (bytes, milliseconds) and meanings will not change.
"""
from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

SCHEMA = "callwitness.baseline.v1"
PUBLISHED_URL = "https://callwitness.tech/baseline/v1.json"
LEVELS = ("median", "p95", "max")


@dataclass
class Census:
    spec: str
    origin: str                      # census | local | unknown
    origin_declared: bool            # False when inferred from the source URL
    generated_at: str
    calls: list[int]                 # returned bytes, one per successful call
    servers_called: int
    servers_started: int
    declared: list[dict] = field(default_factory=list)   # {server, declared_bytes, ratio_max}
    caveat: str = ""

    @property
    def n(self) -> int:
        return len(self.calls)

    @property
    def declared_known(self) -> bool:
        """A locally generated document reports declared_bytes = 0: the
        recorder does not keep tools/list yet. Then the ratio is not known,
        and adebench must not compute one against a guessed denominator."""
        return any(d.get("declared_bytes") for d in self.declared)

    def percentile(self, q: float) -> int:
        v = sorted(self.calls)
        return v[min(len(v) - 1, int(q * len(v)))] if v else 0

    def levels(self) -> dict[str, int]:
        return {"median": self.percentile(0.5), "p95": self.percentile(0.95), "max": max(self.calls, default=0)}

    def rank(self, size: int) -> float | None:
        """Share of census calls smaller than `size` (0..1)."""
        if not self.calls:
            return None
        return round(sum(1 for c in self.calls if c < size) / len(self.calls), 2)

    def label(self) -> str:
        s = self.origin
        if not self.origin_declared:
            s += " (no origin field in the document; inferred from its source)"
        return s


def _read(spec: str) -> dict:
    if spec.startswith(("http://", "https://")):
        with urllib.request.urlopen(spec, timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))
    return json.loads(Path(spec).read_text(encoding="utf-8"))


def load(spec: str) -> Census:
    doc = _read(spec)
    return parse(doc, spec)


def parse(doc: dict, spec: str = "") -> Census:
    schema = str(doc.get("schema", ""))
    if not schema.startswith(SCHEMA):
        raise ValueError(f"not a {SCHEMA} document (schema: {schema or 'missing'})")
    origin = doc.get("origin")
    declared_origin = origin is not None
    if origin is None:
        origin = "census" if spec == PUBLISHED_URL else "unknown"
    calls = [int(x) for x in doc.get("returned_bytes_all") or []]
    if not calls:  # older shape: rebuild the per-call list from the servers
        for s in doc.get("servers") or []:
            calls += [int(c.get("returned_bytes", 0)) for c in s.get("calls") or []]
    sample = doc.get("sample") or {}
    declared = []
    for s in doc.get("servers") or []:
        ratio = (s.get("returned_over_declared") or {}).get("max")
        declared.append({"server": s.get("server"), "declared_bytes": int(s.get("declared_bytes") or 0),
                         "ratio_max": ratio, "calls": int((s.get("returned_bytes") or {}).get("n") or 0)})
    return Census(spec=spec, origin=str(origin), origin_declared=declared_origin,
                  generated_at=str(doc.get("generated_at", "")), calls=calls,
                  servers_called=int(sample.get("servers_called") or 0),
                  servers_started=int(sample.get("servers_started") or 0),
                  declared=declared, caveat=str(doc.get("caveat", "")))


def resolve_pressure(value: str, census: Census | None) -> int:
    """'1200' → 1200; 'median' | 'p95' | 'max' → the census level."""
    v = value.strip().lower()
    if v.lstrip("-").isdigit():
        return int(v)
    if v not in LEVELS:
        raise ValueError(f"pressure must be a number or one of {', '.join(LEVELS)}: {value!r}")
    if census is None:
        raise ValueError(f"--pressure {v} needs --census (a callwitness baseline URL or file)")
    return census.levels()[v]
