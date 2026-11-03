"""Does a memory's core score drop on the private set? (spec section 4)

Each resample picks one public run and one private run at random (the spread
of builds) and resamples, with replacement, the cases of the sections that
come from the set's questions, door and abstention (the spread of questions);
updates and time are mostly probes the harness writes itself, the same on
every set, and are kept as the run has them. The 90 % interval of private
minus public, per 55 core points, decides: "lower" by X when it lies wholly
below 0 and its midpoint is below -delta, otherwise "no drop detected" with
Y, the interval's half-width. The check is one-sided: a set of this size can
show a drop, not that two scores are equal within a few points.

Two sets from the same generator still differ in difficulty: their questions come from one
invented world each, so they are not independent draws, and a memory nobody tuned (gbrain on
holdout-v1) dropped 8 points. So the difference is taken against the set's own shift, the
median gap of the other memories measured on both sets (at least MIN_OTHERS): a drop every
memory shares is the set; a memory tuned to the public questions drops beyond it.
"""
from __future__ import annotations

import random

WEIGHTS = {"door": 25, "updates": 10, "time": 10, "abstention": 10}
MIN_OTHERS = 4
SET_SECTIONS = {"door", "abstention"}


def core_cases(run: dict) -> dict[str, list[float]]:
    out = {}
    for s in run.get("sections", []):
        if s.get("name") in WEIGHTS:
            # a case's credit as the board counts it: its partial credit (fraction, abstention)
            # when it has one, otherwise PASS
            bits = [float(c["fraction"]) if c.get("fraction") is not None else float(c.get("status") == "PASS")
                    for c in s.get("cases", []) if c.get("status") != "SKIP"]
            if bits:
                out[s["name"]] = bits
    return out


def core55(cases: dict[str, list[float]]) -> float:
    w = sum(WEIGHTS[k] for k in cases)
    if not w:
        return 0.0
    pts = sum(WEIGHTS[k] * sum(v) / len(v) for k, v in cases.items())
    return round(pts * 55 / w, 4)


def _resample(cases: dict[str, list[float]], rng: random.Random) -> dict[str, list[float]]:
    return {k: ([rng.choice(v) for _ in v] if k in SET_SECTIONS else v) for k, v in cases.items()}


def _shared(public: list[dict], private: list[dict]) -> tuple[list[dict], list[dict]]:
    pub = [core_cases(r) for r in public]
    priv = [core_cases(r) for r in private]
    if any("door" not in c for c in pub + priv):
        raise ValueError("a run has no door cases: it did not measure the memory")
    # both sides on the same sections: a section every run measured
    shared = set.intersection(*(set(c) for c in pub + priv))
    return ([{k: v for k, v in c.items() if k in shared} for c in pub],
            [{k: v for k, v in c.items() if k in shared} for c in priv])


def gap(public: list[dict], private: list[dict]) -> float:
    """Mean private core minus mean public core, per 55, on the sections both sides share."""
    pub, priv = _shared(public, private)
    return round(sum(map(core55, priv)) / len(priv) - sum(map(core55, pub)) / len(pub), 4)


def set_shift(other_gaps: list[float]) -> float:
    """How much harder the private set is for everyone: the median gap of the other memories."""
    if len(other_gaps) < MIN_OTHERS:
        raise ValueError(f"the set's shift needs {MIN_OTHERS} other memories measured on both sets, "
                         f"there are {len(other_gaps)}")
    g = sorted(other_gaps)
    m = len(g) // 2
    return g[m] if len(g) % 2 else (g[m - 1] + g[m]) / 2


def compare(public: list[dict], private: list[dict], delta: float = 3.0, n: int = 2000, seed: int = 0,
            shift: float = 0.0) -> dict:
    rng = random.Random(seed)
    pub, priv = _shared(public, private)
    diffs = sorted(core55(_resample(rng.choice(priv), rng)) - core55(_resample(rng.choice(pub), rng)) - shift
                   for _ in range(n))
    lo, hi = diffs[int(0.05 * n)], diffs[int(0.95 * n) - 1]
    mid = round((lo + hi) / 2, 1)
    lower = hi < 0 and mid < -delta
    return {"outcome": "lower" if lower else "no_drop", "x": mid if lower else None,
            "y": round((hi - lo) / 2, 1), "delta": delta, "shift": round(shift, 1),
            "public_builds": len(public), "private_builds": len(private)}
