"""Put the synthetic memory (examples/synthetic.py) into a gbrain, page by
page, so that the same golden set runs on both:

    gbrain init --pglite                       # once, an empty brain
    python examples/gbrain_import.py           # writes the pages via put_page
    python -m adebench --adapter adebench.gbrain:GbrainAdapter \
        --cases examples/synthetic_data/cases --history /tmp/gbrain-run

Cards become entity pages (person / company / project) with frontmatter;
facts become dated atom pages; episodes become dated note pages. Nothing
is invented here that the synthetic memory does not already hold.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from adebench.gbrain import GbrainAdapter  # noqa: E402
from examples.synthetic import CARDS, CARD_DATES, EPISODES, FACTS  # noqa: E402

TYPES = {"brain": "project", "mailbox": "project", "calendar": "project", "owner": "person"}
TITLES = {"brain": "Brain", "mailbox": "Mailbox (MailBridge)", "calendar": "Calendar", "owner": "Alex"}


def page(slug: str, title: str, ptype: str, body: str, date: str | None = None, links: list[str] = ()) -> str:
    fm = [f"title: {json.dumps(title)}", f"type: {ptype}"]  # quoted: titles may hold ':' or '[
    if date:
        fm.append(f"date: {date}")
    links_md = ("\n\nRelated: " + ", ".join(f"[[{s}]]" for s in links)) if links else ""
    return "---\n" + "\n".join(fm) + "\n---\n\n# " + title + "\n\n" + body + links_md + "\n"


def main() -> int:
    g = GbrainAdapter()
    if not g.health():
        print("gbrain does not answer: install it and run `gbrain init --pglite` first")
        return 2
    n = 0
    entity_slugs = {e: f"{TYPES[e]}s/{e}" if TYPES[e] != "person" else f"people/{e}" for e in CARDS}
    for ent, text in CARDS.items():
        others = [s for e, s in entity_slugs.items() if e != ent and e in text.lower()]
        g._call("put_page", {"slug": entity_slugs[ent], "content": page(
            entity_slugs[ent], TITLES[ent], TYPES[ent], text, CARD_DATES[ent], others)})
        n += 1
    for f in FACTS:
        ent = next((e for e in CARDS if e in f["key"]), None)
        links = [entity_slugs[ent]] if ent else []
        g._call("put_page", {"slug": f"atoms/{f['key']}", "content": page(
            f["key"], f["key"].replace("_", " "), "atom", f["content"], f["event_date"], links)})
        n += 1
    for i, e in enumerate(EPISODES):
        g._call("put_page", {"slug": f"note/episode-{i}", "content": page(
            f"episode-{i}", e["input_summary"], "note",
            f"{e['input_summary']}\n\nResult: {e['output_summary']}\n\nSource: {e['repl']}", e["created_at"][:10])})
        n += 1
        # the same episode as a dated timeline entry on the entity it concerns,
        # so that gbrain's chronicle (the 'time' section) sees it
        ent = next((x for x in CARDS if x in (e["input_summary"] + e["output_summary"]).lower()), "owner")
        g._call("add_timeline_entry", {"slug": entity_slugs[ent], "date": e["created_at"][:10],
                                       "summary": e["input_summary"], "detail": e["output_summary"],
                                       "source": e["repl"]})
    print(f"{n} pages written to gbrain")
    return 0


if __name__ == "__main__":
    sys.exit(main())
