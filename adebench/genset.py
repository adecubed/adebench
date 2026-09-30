"""Generate a golden set with a model, validate it, write it (spec section 2).

    python -m adebench.genset --name public2 --seed 11 --out sets/public2

The model gets a fixed specification (the mix in validate_set.MIX_PUBLIC),
returns world, questions, abstention and repo as one JSON document, and the
set is written only if every validator rule passes; otherwise it is thrown
away and asked again, at most five times. Nothing of the content is printed:
only the attempt count and, per failed attempt, how many problems each rule
found. The key is GOOGLE_API_KEY, read here.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
import shutil
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from adebench import sets, validate_set

SPEC = """You write a synthetic history for testing an AI assistant's memory, and questions about it.
Return ONE JSON object, nothing else, with keys "world", "questions", "abstention", "repo".
world: {{"name": "{name}", "as_of": "<YYYY-MM-DD>", "cards": [...], "corrections": [...], "aliases": [...],
  "facts": [...], "episodes": [...]}}
- cards: {cards} entities (people, services, projects, devices), each {{"id": "card:<entity>", "entity": "<snake_case>",
  "text": "<3-4 sentences>", "date": "<YYYY-MM-DD>"}}. A card states each value as it is at as_of and never
  mentions a value that a fact replaced.
- facts: at least {facts}, each {{"id", "entity", "attribute", "text", "date": "<YYYY-MM-DD> or null", "supersedes": "<id> or null"}}.
  Every fact's text names its entity (its name or one of its aliases): "Titan Node 4 is mounted in rack C12", never
  "The hardware is mounted in rack C12". At least 4 facts are undated. Exactly {replaced} pairs where a later fact
  replaces an earlier value of the same entity and attribute: the later fact states ONLY the new value ("The Nexus API
  listens on port 8443") and has "supersedes" set to the earlier fact's id; the old value appears in the earlier fact
  and nowhere else.
- corrections: {corrections}, each {{"entity", "content": "In the <entity> card never omit: <item>, <item>"}}.
- aliases: {aliases}, each {{"alias": "<snake_case other name>", "canonical": "<entity>"}}: a real other name that shares
  no word with the entity's name (a nickname, a codename, a former name), never the same words reordered.
- episodes: {episodes}, each {{"id", "created_at": "<YYYY-MM-DDTHH:MM:SS>", "repl": "chat", "input", "output"}};
  exactly 3 of them with input starting "[pc2] " and repl "pc2:chat".
- Every date on or before as_of. Invented, varied, specific values: ports, versions, names, times, counts. Seed: {seed}.
questions: exactly these kinds and counts, no other kind: {door}. Each {{"question", "expected": [["<token>", "<alt>"]],
  "forbidden": [["<retired value>"]] (only for kind replaced), "entity": "<entity or omit>", "validated": true,
  "kind", "evidence": ["<ids of the items that answer it>"]}}.
  - "expected" is a list of groups: every group must be answered; the strings inside one group are alternative
    spellings of the SAME value ("6", "six"). Most questions have one group.
  - fact: answered by a fact. card: answered by a card, "entity" set. alias: names the entity only through an alias.
  - replaced: asks the current value; "forbidden" is the old one; evidence is the replacing fact.
  - dated: asks when something happened; the expected token is a YYYY-MM-DD date written in the text of the cited
    item ("On 2026-06-20 the scheduler was upgraded to 1.3").
  - Expected tokens are short exact strings of at most 3 words, copied exactly as they appear in the evidence text
    (a number, a name, a version), never words of the question and never placeholders like "null" or "unknown".
abstention: exactly {abstention} objects {{"question", "entity"}} about invented things that appear nowhere in the
  world, alias or repo, not even inside an identifier. "entity" is ONE invented proper name: a single made-up word of
  5 to 10 letters that is not a word of any language and not the name of anything real; the question may add a common
  noun ("What does the <Name> module do?"). 3 of the questions also name a real entity next to the invented one.
repo: {{"<file>.py": "<python source>"}}, 3 files, at least 12 functions in all, about the world's services.
"""


def prompt(name: str, seed: int, mix: dict) -> str:
    door = ", ".join(f"{n} {k}" for k, n in mix["door"].items())
    return SPEC.format(name=name, seed=seed, door=door, abstention=mix.get("abstention", 12),
                       cards=mix.get("cards", 8), facts=mix.get("facts", 30), aliases=mix.get("aliases", 6),
                       corrections=mix.get("corrections", 3), episodes=mix.get("episodes", 12),
                       replaced=mix["door"].get("replaced", 3))


def parse(text: str) -> dict:
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    try:
        d = json.loads(t)
    except json.JSONDecodeError as e:
        raise ValueError(f"not JSON: {e.msg}") from None
    if not isinstance(d, dict) or not all(k in d for k in ("world", "questions", "abstention", "repo")):
        raise ValueError("missing keys")
    return d


def gemini(model: str) -> Callable[[str], str]:
    key = os.environ.get("GOOGLE_API_KEY") or ""
    if not key:
        raise SystemExit("GOOGLE_API_KEY is not set")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

    def ask(p: str) -> str:
        body = json.dumps({"contents": [{"parts": [{"text": p}]}],
                           "generationConfig": {"responseMimeType": "application/json", "temperature": 1.0}}).encode()
        req = urllib.request.Request(url, body, {"Content-Type": "application/json", "x-goog-api-key": key})
        with urllib.request.urlopen(req, timeout=600) as r:
            out = json.loads(r.read())
        return out["candidates"][0]["content"]["parts"][0]["text"]
    return ask


def _write(out: Path, d: dict) -> None:
    (out / "cases").mkdir(parents=True)
    (out / "repo").mkdir()
    dump = lambda x: json.dumps(x, indent=1, ensure_ascii=False) + "\n"  # noqa: E731
    (out / "world.json").write_text(dump(d["world"]), encoding="utf-8")
    (out / "cases" / "questions.json").write_text(dump(d["questions"]), encoding="utf-8")
    (out / "cases" / "abstention.json").write_text(dump(d["abstention"]), encoding="utf-8")
    for fname, src in d["repo"].items():
        (out / "repo" / Path(fname).name).write_text(src, encoding="utf-8")


def generate(out: Path, name: str, seed: int, ask: Callable[[str], str], mix: dict = validate_set.MIX_PUBLIC,
             attempts: int = 5, say: Callable[[str], None] = print, model: str = "", canary: bool = False) -> dict:
    out = Path(out)
    if out.exists():
        raise SystemExit(f"{out} exists: a set is never overwritten")
    p = prompt(name, seed, mix)
    for n in range(1, attempts + 1):
        try:
            d = parse(ask(p))
            problems = validate_set.check(d["world"], d["questions"], d["abstention"], d["repo"], mix)
        except (ValueError, KeyError, TypeError, AttributeError) as e:
            say(f"attempt {n}: rejected ({type(e).__name__})")
            continue
        if any(problems.values()):
            say(f"attempt {n}: rejected, " + ", ".join(f"{r} {len(v)}" for r, v in problems.items() if v))
            continue
        if canary:
            token = "cnry" + secrets.token_hex(6)
            d["world"]["canary"] = token
            for f in d["world"]["facts"][:3]:
                f["text"] = f"{f['text']} (ref {token})"
        _write(out, d)
        meta = {"name": name, "version": "1", "written_by": f"{model or 'model'} via adebench.genset",
                "prompt_sha256": hashlib.sha256(p.encode()).hexdigest(), "seed": seed, "attempts": n,
                "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "validator": {r: 0 for r in validate_set.RULES}, "sha256": sets.sha256(out)}
        (out / "set.json").write_text(json.dumps(meta, indent=1) + "\n", encoding="utf-8")
        say(f"attempt {n}: accepted; {len(d['questions'])} questions, {len(d['abstention'])} abstention; "
            f"sha256 {meta['sha256'][:12]}")
        return meta
    if out.exists():
        shutil.rmtree(out)
    raise SystemExit(f"no valid set in {attempts} attempts")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="adebench.genset")
    ap.add_argument("--name", required=True)
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--model", default="gemini-3-flash-preview")
    ap.add_argument("--canary", action="store_true", help="plant a leak-detection token (holdout sets)")
    a = ap.parse_args(argv)
    generate(Path(a.out), a.name, a.seed, gemini(a.model), model=a.model, canary=a.canary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
