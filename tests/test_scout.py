"""scout: GitHub search for memory systems, with fake HTTP (no network)."""
from __future__ import annotations

import json
from datetime import date
from urllib.parse import parse_qs, urlparse

from adebench import scout

TODAY = date(2026, 9, 29)


def repo(name, stars=50, pushed="2026-09-20T10:00:00Z", fork=False, archived=False,
         language="Python", description="Long-term memory for agents", topics=("agent-memory",)):
    return {"full_name": name, "html_url": f"https://github.com/{name}", "stargazers_count": stars,
            "pushed_at": pushed, "fork": fork, "archived": archived, "language": language,
            "description": description, "license": {"spdx_id": "MIT"}, "topics": list(topics)}


class FakeGitHub:
    """Every search query returns the same items; READMEs from a dict."""

    def __init__(self, items, readmes=None, limited_after=None):
        self.items, self.readmes = items, readmes or {}
        self.limited_after = limited_after
        self.searches, self.readme_calls = [], []

    def __call__(self, url, accept):
        path = urlparse(url).path
        if path == "/search/repositories":
            if self.limited_after is not None and len(self.searches) >= self.limited_after:
                return 403, {"x-ratelimit-remaining": "0", "x-ratelimit-reset": "9999999999"}, "{}"
            self.searches.append(parse_qs(urlparse(url).query)["q"][0])
            return 200, {}, json.dumps({"items": self.items})
        if path.endswith("/readme"):
            name = path[len("/repos/"):-len("/readme")]
            self.readme_calls.append(name)
            if name in self.readmes:
                return 200, {}, self.readmes[name]
            return 404, {}, ""
        raise AssertionError(url)


def run(tmp_path, gh, **kw):
    kw.setdefault("adapters_dir", tmp_path / "no_adapters")
    return scout.run(tmp_path / "scout", gh, today=TODAY, sleep=lambda s: None, **kw)


def load(tmp_path):
    return json.loads((tmp_path / "scout" / "candidates.json").read_text(encoding="utf-8"))["repos"]


def test_queries_carry_the_filters():
    gh = FakeGitHub([])
    scout.search(gh, ["topic:agent-memory"], min_stars=10, days=90, today=TODAY, sleep=lambda s: None)
    q = gh.searches[0]
    assert "topic:agent-memory" in q and "fork:false" in q and "archived:false" in q
    assert "stars:>=10" in q and "pushed:>=2026-07-01" in q


def test_drops_forks_archived_stale_small_lists(tmp_path):
    items = [repo("a/good"), repo("a/fork", fork=True), repo("a/old", archived=True),
             repo("a/stale", pushed="2026-01-01T00:00:00Z"), repo("a/tiny", stars=3),
             repo("a/nolang", language=None), repo("a/awesome-agent-memory"),
             repo("a/papers", description="A curated list of memory papers"),
             repo("a/db", description="Git for data, for agents", topics=("agent-memory", "database")),
             repo("a/claude-mem", description="Persistent context across sessions for every agent")]
    run(tmp_path, FakeGitHub(items))
    assert set(load(tmp_path)) == {"a/good", "a/claude-mem"}


def test_interface_guess_from_readme():
    g = scout.guess_interface
    assert g("Add it to Claude: an MCP server (modelcontextprotocol)") == ["mcp"]
    assert g("pip install foo\n\ncurl http://localhost:8080/v1/memories") == ["pip", "rest"]
    assert g("npm install -g bar; docker compose up") == ["npm", "docker"]
    assert g("A Claude Code plugin: /plugin install x") == ["plugin"]
    assert g("") == []


def test_known_from_adapters_and_file(tmp_path):
    ad = tmp_path / "adapters"
    ad.mkdir()
    (ad / "x.py").write_text('"""Adapter for X (https://github.com/Owner/X-Mem)."""\n', encoding="utf-8")
    out = tmp_path / "scout"
    out.mkdir()
    (out / "known.txt").write_text("# rejected\nother/thing\n", encoding="utf-8")
    known = scout.known_repos(ad, out / "known.txt")
    assert known == {"owner/x-mem", "other/thing"}
    run(tmp_path, FakeGitHub([repo("owner/X-Mem"), repo("other/thing"), repo("new/one")]), adapters_dir=ad)
    repos = load(tmp_path)
    assert repos["owner/X-Mem"]["status"] == "known" and repos["new/one"]["status"] == "new"
    md = (out / "new.md").read_text(encoding="utf-8")
    assert "new/one" in md and "owner/X-Mem" not in md


def test_state_across_runs(tmp_path):
    gh = FakeGitHub([repo("a/one", stars=20)], readmes={"a/one": "pip install one"})
    first = run(tmp_path, gh)
    assert first["new"] == ["a/one"] and gh.readme_calls == ["a/one"]
    gh.items = [repo("a/one", stars=25), repo("b/two", stars=90)]
    second = run(tmp_path, gh)
    assert second["new"] == ["b/two"]
    assert gh.readme_calls == ["a/one", "b/two"]  # README only for first sightings
    repos = load(tmp_path)
    assert repos["a/one"]["status"] == "seen" and repos["a/one"]["stars"] == 25
    assert repos["a/one"]["first_seen"] == "2026-09-29" and repos["a/one"]["interface"] == ["pip"]


def test_new_md_most_stars_first(tmp_path):
    run(tmp_path, FakeGitHub([repo("a/small", stars=11), repo("a/big", stars=900)]))
    md = (tmp_path / "scout" / "new.md").read_text(encoding="utf-8")
    assert md.index("a/big") < md.index("a/small")


def test_readme_cap(tmp_path):
    items = [repo(f"a/r{i}") for i in range(5)]
    gh = FakeGitHub(items)
    run(tmp_path, gh, readme_max=2)
    assert len(gh.readme_calls) == 2


def test_rate_limit_saves_what_was_found(tmp_path):
    gh = FakeGitHub([repo("a/one")], limited_after=1)
    summary = run(tmp_path, gh, queries=["topic:a", "topic:b", "topic:c"])
    assert summary["stopped"] and "rate limit" in summary["stopped"]
    assert set(load(tmp_path)) == {"a/one"}
