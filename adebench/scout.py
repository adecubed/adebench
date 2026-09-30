"""Find AI memory systems on GitHub that adebench has not measured yet.

    python -m adebench.scout            # writes scout/candidates.json and scout/new.md

Step 1 of the loop find -> prepare -> measure -> approve (docs/specs/
2026-09-29-scout-design.md). It only lists: nothing is installed or run.
A fixed set of topic and keyword searches, minus forks, archived and
stale repos, curated lists, and repos that are not about memory for
AI agents. The state is kept across runs, so new.md holds only what
appeared since the last one. GITHUB_TOKEN is optional: without it the
searches are paced to stay under GitHub's 10 per minute.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode

API = "https://api.github.com"
HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "scout"

QUERIES = [
    "topic:agent-memory", "topic:ai-memory", "topic:llm-memory", "topic:memory-mcp",
    "topic:mcp-memory", "topic:long-term-memory", "topic:agentic-memory",
    "topic:memory-layer", "topic:memory-system",
    '"agent memory" in:name,description', '"llm memory" in:name,description',
    '"memory layer" in:name,description', '"mcp memory" in:name,description',
    '"long-term memory" in:description', '"persistent memory" in:description',
]

CURATED = re.compile(r"awesome|curated list|reading list|\bpapers\b|\bsurvey\b", re.I)
MEMORY = re.compile(r"memor|\bmem\b|remember", re.I)
FOR_AI = re.compile(r"\b(agents?|agentic|llms?|ai|mcp|claude|gpt|rag|assistants?|chatbots?)\b", re.I)

INTERFACES = [  # order is the order of the guess
    ("mcp", re.compile(r"\bmcp\b|modelcontextprotocol", re.I)),
    ("pip", re.compile(r"\bpip3? install\b|\buv add\b|\bpypi\b", re.I)),
    ("npm", re.compile(r"\bnpm (i|install)\b|\bnpx\b|\bbun add\b|\bpnpm add\b", re.I)),
    ("rest", re.compile(r"\bcurl\b[^\n]*https?://|\bREST\b|\bopenapi\b|/v1/")),
    ("docker", re.compile(r"\bdocker\b", re.I)),
    ("plugin", re.compile(r"/plugin install|\.?claude-plugin|claude code plugin", re.I)),
]

GITHUB_URL = re.compile(r"github\.com/([\w.-]+)/([\w.-]+)")


class RateLimited(Exception):
    pass


def fetch_github(url: str, accept: str) -> tuple[int, dict, str]:
    """GET with the optional GITHUB_TOKEN; returns (status, lower-case headers, body)."""
    headers = {"Accept": accept, "User-Agent": "adebench-scout", "X-GitHub-Api-Version": "2022-11-28"}
    if os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {os.environ['GITHUB_TOKEN']}"
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, {k.lower(): v for k, v in r.headers.items()}, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, {k.lower(): v for k, v in e.headers.items()}, e.read().decode("utf-8", "replace")


def _get(fetch, url, accept, sleep):
    """One request; waits out a short rate limit once, raises RateLimited on a long one."""
    for attempt in (0, 1):
        status, headers, body = fetch(url, accept)
        limited = status == 429 or (status == 403 and (headers.get("x-ratelimit-remaining") == "0"
                                                       or "retry-after" in headers))
        if not limited:
            return status, body
        if "retry-after" in headers:
            wait = int(headers["retry-after"])
        else:
            wait = int(headers.get("x-ratelimit-reset", "0")) - int(time.time())
        if attempt or wait > 70:
            raise RateLimited(f"GitHub rate limit, reset in {max(wait, 0)} s")
        sleep(max(wait, 0) + 1)
    raise AssertionError("unreachable")


def search(fetch, queries, *, min_stars, days, today, sleep, pause=0.0, pages=3) -> tuple[dict, str | None]:
    """Run the queries; returns ({full_name: item}, reason it stopped early or None)."""
    since = (today - timedelta(days=days)).isoformat()
    found: dict[str, dict] = {}
    first = True
    for q in queries:
        full = f"{q} fork:false archived:false stars:>={min_stars} pushed:>={since}"
        for page in range(1, pages + 1):
            if not first and pause:
                sleep(pause)
            first = False
            url = f"{API}/search/repositories?" + urlencode(
                {"q": full, "sort": "stars", "order": "desc", "per_page": 100, "page": page})
            try:
                status, body = _get(fetch, url, "application/vnd.github+json", sleep)
            except RateLimited as e:
                return found, str(e)
            if status != 200:
                return found, f"search failed ({status}) on {q!r}: {body[:200]}"
            items = json.loads(body).get("items", [])
            for it in items:
                found.setdefault(it["full_name"], it)
            if len(items) < 100:
                break
    return found, None


def keep(item: dict, *, min_stars: int, cutoff: date) -> bool:
    if item.get("fork") or item.get("archived") or not item.get("language"):
        return False
    if item.get("stargazers_count", 0) < min_stars:
        return False
    if datetime.fromisoformat(item["pushed_at"].replace("Z", "+00:00")).date() < cutoff:
        return False
    own = f"{item['full_name']} {item.get('description') or ''}"
    text = f"{own} {' '.join(item.get('topics') or [])}"
    if CURATED.search(text):
        return False
    # memory must be in the repo's own words: a database tagged agent-memory is not one
    return bool(MEMORY.search(own.replace("-", " ").replace("_", " "))
                and FOR_AI.search(text.replace("-", " ").replace("_", " ")))


def guess_interface(readme: str) -> list[str]:
    return [name for name, rx in INTERFACES if rx.search(readme)]


def known_repos(adapters_dir: Path, known_file: Path) -> set[str]:
    """owner/repo (lower case) of the memories adebench already has an adapter for, plus known.txt."""
    known: set[str] = set()
    if adapters_dir.is_dir():
        for py in adapters_dir.glob("*.py"):
            head = "\n".join(py.read_text(encoding="utf-8", errors="replace").splitlines()[:20])
            for owner, name in GITHUB_URL.findall(head):
                name = name.rstrip(".").removesuffix(".git")
                known.add(f"{owner}/{name}".lower())
    if known_file.is_file():
        for line in known_file.read_text(encoding="utf-8").splitlines():
            line = line.split("#", 1)[0].strip()
            if line:
                known.add(line.lower())
    known.discard("adecubed/adebench")
    return known


def _record(item: dict) -> dict:
    return {"full_name": item["full_name"], "url": item["html_url"], "stars": item["stargazers_count"],
            "pushed": item["pushed_at"][:10], "license": (item.get("license") or {}).get("spdx_id"),
            "language": item.get("language"), "description": item.get("description") or "",
            "topics": item.get("topics") or []}


def _new_md(new: list[dict], today: date, stopped: str | None) -> str:
    lines = [f"# New memory repos, {today.isoformat()}", ""]
    if stopped:
        lines += [f"> Stopped early: {stopped}. The list is partial.", ""]
    if not new:
        return "\n".join(lines + ["Nothing new since the last run.", ""])
    lines += [f"{len(new)} new.", "", "| repo | stars | last push | language | license | interface | description |",
              "|---|---:|---|---|---|---|---|"]
    for r in new:
        iface = ", ".join(r["interface"]) if r.get("interface") else ("?" if r.get("interface") is None else "-")
        desc = r["description"].replace("|", "\\|").replace("\n", " ")[:160]
        lines.append(f"| [{r['full_name']}]({r['url']}) | {r['stars']} | {r['pushed']} | {r['language']} | "
                     f"{r['license'] or '-'} | {iface} | {desc} |")
    return "\n".join(lines + [""])


def run(out: Path = OUT, fetch=fetch_github, *, today: date | None = None, sleep=time.sleep,
        queries=None, min_stars: int = 10, days: int = 90, readme_max: int | None = None,
        pause: float | None = None, adapters_dir: Path = HERE) -> dict:
    today = today or datetime.now(timezone.utc).date()
    token = bool(os.environ.get("GITHUB_TOKEN"))
    if pause is None:
        pause = 2.0 if token else 7.0
    if readme_max is None:
        readme_max = 300 if token else 40
    out.mkdir(parents=True, exist_ok=True)
    state_file = out / "candidates.json"
    state = json.loads(state_file.read_text(encoding="utf-8")) if state_file.is_file() else {"repos": {}}
    repos: dict[str, dict] = state["repos"]
    known = known_repos(adapters_dir, out / "known.txt")

    found, stopped = search(fetch, queries or QUERIES, min_stars=min_stars, days=days, today=today,
                            sleep=sleep, pause=pause)
    cutoff = today - timedelta(days=days)
    new_names = []
    for name, item in found.items():
        if not keep(item, min_stars=min_stars, cutoff=cutoff):
            continue
        rec = _record(item)
        old = repos.get(name)
        rec["first_seen"] = old["first_seen"] if old else today.isoformat()
        rec["last_seen"] = today.isoformat()
        rec["interface"] = old.get("interface") if old else None
        if name.lower() in known:
            rec["status"] = "known"
        elif old:
            rec["status"] = "seen"
        else:
            rec["status"] = "new"
            new_names.append(name)
        repos[name] = rec

    # READMEs: first sightings first, then older ones never read (cap reached last time)
    todo = [n for n in new_names] + [n for n, r in repos.items()
                                     if r["status"] == "seen" and r.get("interface") is None]
    for name in todo[:readme_max]:
        try:
            status, body = _get(fetch, f"{API}/repos/{name}/readme", "application/vnd.github.raw", sleep)
        except RateLimited as e:
            stopped = stopped or f"{e} (while reading READMEs)"
            break
        repos[name]["interface"] = guess_interface(body) if status == 200 else []

    state = {"updated": today.isoformat(), "repos": dict(sorted(repos.items(), key=lambda kv: kv[0].lower()))}
    state_file.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    new = sorted((repos[n] for n in new_names), key=lambda r: -r["stars"])
    (out / "new.md").write_text(_new_md(new, today, stopped), encoding="utf-8")
    return {"found": len(found), "kept": sum(1 for r in repos.values() if r["last_seen"] == today.isoformat()),
            "new": [r["full_name"] for r in new], "stopped": stopped}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="adebench.scout", description="List AI memory repos on GitHub not measured yet.")
    ap.add_argument("--out", default=str(OUT), help="state folder (candidates.json, new.md, known.txt)")
    ap.add_argument("--min-stars", type=int, default=10)
    ap.add_argument("--days", type=int, default=90, help="drop repos with no push in this many days")
    ap.add_argument("--readme-max", type=int, help="READMEs read per run (default 40, 300 with GITHUB_TOKEN)")
    args = ap.parse_args(argv)
    s = run(Path(args.out), min_stars=args.min_stars, days=args.days, readme_max=args.readme_max)
    print(f"{s['found']} found, {s['kept']} kept, {len(s['new'])} new -> {Path(args.out) / 'new.md'}")
    if s["stopped"]:
        print(f"stopped early: {s['stopped']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
