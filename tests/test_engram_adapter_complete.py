"""The Engram adapter implements the whole adebench contract.

Checked without a server: the methods are read off the class, nothing is
instantiated (so no `engram mcp` is started), the same way
test_aionforge_adapter_complete.py checks the Aionforge adapter.
"""
from adebench import adapter, engram


def test_engram_adapter_honours_the_contract():
    missing = [m for m in adapter.required_methods()
               if not callable(getattr(engram.EngramAdapter, m, None))]
    assert missing == [], f"EngramAdapter is missing: {missing}"


def test_engram_adapter_has_the_write_probes():
    # no settle(): Engram writes synchronously, there is nothing pending to wait for
    for m in ("write_fact", "forget_memory", "import_memory", "ingest_exchange", "declared_bytes",
              "stored_mentions"):
        assert callable(getattr(engram.EngramAdapter, m, None)), m


def test_engram_dates_are_stored_as_engram_stores_them():
    assert engram._utc("2021-03-14T09:30:00") == "2021-03-14 09:30:00"
    assert engram._utc("2026-09-01") == "2026-09-01 12:00:00"
    assert engram._utc("2026-09-10T09:12:00+02:00") == "2026-09-10 07:12:00"


# A mem_search `result` as Engram v2.2.1 printed it (match_mode any, recorded
# on the synthetic store): a hit with pending-conflict lines, a truncated
# preview, and a plain one.
RECORDED_RESULT = (
    "Found 3 memories:\n\n"
    "[1] #32 (manual) \u2014 I have no record of that. You asked: When do backups run?\n"
    "    I have no record of that. You asked: When do backups run?\n"
    "    2026-09-29 17:44:23 | project: adebench | scope: project\n"
    "    conflict: contested by #obs-c3b3b2c436f0486b (pending)\n"
    "    conflict: contested by #obs-491102ca6e384537 (pending)\n\n"
    "[2] #1 (manual) \u2014 brain\n"
    "    The Brain is the memory service of the assistant. It listens on port 8766, keeps three memory "
    "levels (working, episodic and semantic), and is distilled by the Nova model every night. Updated "
    "2026-09-01. And a tail long enough to be cut by Engram at three hundred characters, so it carries "
    "the mark [preview]\n"
    "    2026-09-01 14:00:00 | project: adebench | scope: project\n\n"
    "[3] #16 (manual) \u2014 [pc2] Sync the calendar cache\n"
    "    Cache refreshed\n"
    "    2026-09-08 10:30:00 | project: adebench | scope: project\n\n"
    "---\nResults above are previews (300 chars). To read the full content of a specific memory, "
    "call mem_get_observation(id: <ID>).\n"
)


def test_engram_search_output_is_parsed_offline():
    hits = engram.parse_search(RECORDED_RESULT)
    assert sorted(hits) == [1, 16, 32]
    assert hits[32]["preview"] == "I have no record of that. You asked: When do backups run?"
    assert hits[32]["shown_at"] == "2026-09-29 17:44:23"
    assert hits[1]["title"] == "brain"
    assert hits[1]["preview"].startswith("The Brain is the memory service") and not hits[1]["preview"].endswith("[preview]")
    assert hits[16] == {"title": "[pc2] Sync the calendar cache", "preview": "Cache refreshed",
                        "shown_at": "2026-09-08 10:30:00"}
    assert engram.parse_search("No memories found for: \"x\"") == {}


def test_engram_days_are_read_in_adebench_local_tz(monkeypatch):
    from zoneinfo import ZoneInfo
    from adebench import config
    monkeypatch.setattr(config, "LOCAL_TZ", ZoneInfo("Europe/Rome"))
    assert engram._day("2026-09-10 22:30:00") == "2026-09-11"   # 00:30 in Rome
    monkeypatch.setattr(config, "LOCAL_TZ", ZoneInfo("America/New_York"))
    assert engram._day("2026-09-10 02:30:00") == "2026-09-09"
