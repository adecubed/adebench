"""Check a generated set against its own world (spec section 3).

Presence of text is not evidence: an answer counts only if an item the
question cites contains it, is dated on or before the set's as_of (or is
undated), and has not been superseded. Everything else that must be absent
is checked after normalising case, accents and punctuation.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date

from adebench.sections import present   # the scorer's own match: evidence must be found the way answers are

# no never_stored questions in generated sets: their answer is absent by construction, so every
# memory fails them; not inventing is what the abstention section measures (decided 30 Sep 2026)
MIX_PUBLIC = {"door": {"fact": 11, "card": 4, "alias": 3, "replaced": 3, "dated": 3},
              "abstention": 12, "cards": 8, "facts": 30, "aliases": 6, "corrections": 3, "episodes": 12}
RULES = ("answerable", "retired", "never_stored", "invented", "leading", "structure")
# an expected token must be a specific value: a generic word turns up in any JSON door or
# refusal ("null", "none") and would pass the question by accident; a long phrase fails any
# memory that paraphrases
GENERIC = {"null", "none", "n/a", "na", "unknown", "no", "yes", "true", "false", "nil", ""}
MAX_TOKEN_WORDS = 3
# words too common to identify an entity by themselves ("titan_node_4" is named by "titan")
NAME_NOISE = {"the", "project", "service", "system", "node", "server", "team", "device", "api", "app", "tool"}


def norm(text: str) -> str:
    t = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode().lower()
    words = (w.strip(".") for w in re.sub(r"[^a-z0-9+.]+", " ", t).split())   # "9100." is the token 9100
    return " " + " ".join(w for w in words if w) + " "


def has_token(token: str, text: str) -> bool:
    return norm(token).strip() != "" and norm(token) in norm(text)


def _items(world: dict) -> dict[str, dict]:
    out = {}
    for c in world.get("cards", []):
        out[c["id"]] = {"text": c["text"], "date": c.get("date"), "entity": c["entity"], "attribute": "card"}
    for f in world.get("facts", []):
        out[f["id"]] = {"text": f["text"], "date": f.get("date"), "entity": f["entity"], "attribute": f["attribute"],
                        "supersedes": f.get("supersedes")}
    for e in world.get("episodes", []):
        out[e["id"]] = {"text": f"{e['input']} {e['output']}", "date": e["created_at"][:10], "entity": None,
                        "attribute": "episode"}
    return out


def _superseded(world: dict) -> set[str]:
    facts = world.get("facts", [])
    gone = {f["supersedes"] for f in facts if f.get("supersedes")}
    for f in facts:
        for g in facts:
            if (g is not f and g["entity"] == f["entity"] and g["attribute"] == f["attribute"]
                    and f.get("date") and g.get("date") and g["date"] > f["date"] and g["date"] <= world["as_of"]):
                gone.add(f["id"])
    return gone


def _name_words(name: str) -> list[str]:
    words = norm(name.replace("_", " ")).split()
    return [w for w in words if w not in NAME_NOISE and len(w) >= 3] or words


def _names_entity(it: dict, world: dict) -> bool:
    """A fact must say what it is about: its entity's name or one of its aliases.
    "The primary IP address for the node is 10.0.0.45" answers nothing on its own."""
    if it["attribute"] in ("card", "episode") or not it["entity"]:
        return True
    names = [it["entity"]] + [a["alias"] for a in world.get("aliases", []) if a["canonical"] == it["entity"]]
    return any(any(has_token(w, it["text"]) for w in _name_words(n)) for n in names)


def _valid_date(d) -> bool:
    try:
        date.fromisoformat(str(d)[:10])
        return True
    except ValueError:
        return False


def check(world: dict, questions: list[dict], abstention: list, repo: dict[str, str], mix: dict | None) -> dict:
    p = {r: [] for r in RULES}
    items, gone, as_of = _items(world), _superseded(world), world["as_of"]
    alias_text = " ".join(f"{a['alias'].replace('_', ' ')} {a['canonical']}" for a in world.get("aliases", []))
    everything = " ".join(i["text"] for i in items.values()) + " " + alias_text + " " + " ".join(repo.values())

    for q in questions:
        alts = [a for g in q.get("expected", []) for a in g]
        for a in alts:
            if norm(a).strip() in GENERIC or len(norm(a).split()) > MAX_TOKEN_WORDS:
                p["structure"].append(f"expected {a!r} is not a specific short value")
        if any(has_token(a, q["question"]) for a in alts):
            p["leading"].append(q["question"])
        if q.get("kind") == "never_stored":
            if any(has_token(a, everything) for a in alts):
                p["never_stored"].append(q["question"])
            continue
        for group in q.get("expected", []):
            ok = False
            for eid in q.get("evidence", []):
                it = items.get(eid)
                if it is None or eid in gone or (it["date"] and it["date"][:10] > as_of):
                    continue
                if not _names_entity(it, world):
                    continue
                # the answer must be in the text, a date too: some memories are given no dates
                if present(it["text"], group):
                    ok = True
            if not ok:
                p["answerable"].append(f"{q['question']} -> {group}")
        for group in q.get("forbidden", []):
            for eid, it in items.items():
                if not any(has_token(a, it["text"]) for a in group) or eid in gone:
                    continue
                # a retired value lives only in the item it was retired from: a card, an episode or
                # the replacing fact that still names it hands the old value to the model
                p["retired"].append(f"{q['question']} -> {eid}")

    real = {norm(c["entity"]) for c in world.get("cards", [])}
    for a in abstention:
        ent = a["entity"] if isinstance(a, dict) else None
        if not ent:
            p["structure"].append(f"abstention without entity: {a}")
            continue
        words = [w for w in norm(ent).split() if len(w) >= 5] or norm(ent).split()
        if any(has_token(w, everything) for w in words) or any(norm(al["alias"].replace("_", " ")) == norm(ent)
                                                               for al in world.get("aliases", [])):
            p["invented"].append(ent)
        if norm(ent) in real:
            p["invented"].append(f"{ent} is a real entity")

    ids = [c["id"] for c in world.get("cards", [])] + [f["id"] for f in world.get("facts", [])] \
        + [e["id"] for e in world.get("episodes", [])]
    if len(ids) != len(set(ids)):
        p["structure"].append("duplicate ids")
    for it in items.values():
        if it["date"] and not _valid_date(it["date"]):
            p["structure"].append(f"bad date {it['date']}")
    entities = {c["entity"] for c in world.get("cards", [])} | {f["entity"] for f in world.get("facts", [])}
    for al in world.get("aliases", []):
        if al["canonical"] not in entities:
            p["structure"].append(f"alias {al['alias']} -> unknown {al['canonical']}")
        elif set(_name_words(al["alias"])) & set(_name_words(al["canonical"])):
            p["structure"].append(f"alias {al['alias']} reuses the words of {al['canonical']}")
    if mix:
        kinds: dict = {}
        for q in questions:
            kinds[q.get("kind")] = kinds.get(q.get("kind"), 0) + 1
        for k, n in mix.get("door", {}).items():
            if kinds.get(k, 0) != n:
                p["structure"].append(f"{k}: {kinds.get(k, 0)} questions, want {n}")
        for k in set(kinds) - set(mix.get("door", {})):
            p["structure"].append(f"{kinds[k]} questions of kind {k!r}, not in the mix")
        if "abstention" in mix and len(abstention) != mix["abstention"]:
            p["structure"].append(f"abstention: {len(abstention)}, want {mix['abstention']}")
        for key in ("cards", "aliases", "corrections", "episodes"):
            if key in mix and len(world.get(key, [])) != mix[key]:
                p["structure"].append(f"{key}: {len(world.get(key, []))}, want {mix[key]}")
        if "facts" in mix and len(world.get("facts", [])) < mix["facts"]:
            p["structure"].append(f"facts: {len(world.get('facts', []))}, want at least {mix['facts']}")
    return p
