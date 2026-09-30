"""The mem0 adapter implements the whole adebench contract.

Checked without mem0: the methods are read off the class, nothing is
instantiated that would start the bridge process.
"""
from adebench import adapter, mem0


def test_mem0_adapter_honours_the_contract():
    missing = [m for m in adapter.required_methods()
               if not callable(getattr(mem0.Mem0Adapter, m, None))]
    assert missing == [], f"Mem0Adapter is missing: {missing}"


def test_mem0_adapter_has_the_write_probes():
    for m in ("write_fact", "forget_memory", "import_memory", "ingest_exchange", "settle",
              "declared_bytes", "stored_mentions"):
        assert callable(getattr(mem0.Mem0Adapter, m, None)), m


def test_the_default_door_is_search():
    assert mem0.DOORS[0] == "search"


def test_a_hit_is_its_text_and_the_metadata_mem0_returned():
    dated = {"memory": "Backups run on Sundays at 03:00.", "metadata": {"date": "2026-03-01", "kind": "fact"},
             "created_at": "2026-09-29T16:44:43.689463+00:00"}
    assert mem0.hit_line(dated) == ('Backups run on Sundays at 03:00. '
                                    'metadata={"date": "2026-03-01", "kind": "fact"}')


def test_an_undated_hit_carries_no_date_not_even_the_write_time():
    undated = {"memory": "'agenda' is another name for calendar.", "metadata": {},
               "created_at": "2026-09-29T16:44:43.689463+00:00"}
    assert mem0.hit_line(undated) == "'agenda' is another name for calendar."
    assert "2026-09-29" not in mem0.hit_line({"memory": "x", "metadata": {"kind": "alias"},
                                               "created_at": "2026-09-29T16:44:43+00:00"})
    assert mem0.hit_line({"memory": "x", "metadata": None, "created_at": None}) == "x"


def test_signed_episodes_are_counted_on_the_saved_messages_not_the_rewording():
    saved = [{"role": "user", "content": "[pc2] Sync the calendar cache"},
             {"role": "assistant", "content": "Cache refreshed"},
             {"role": "user", "content": "Plan the Turin trip by train"},
             {"role": "assistant", "content": "[pc2] is not a user message"}]
    assert mem0.count_signed(saved, "[pc2]") == 1
    assert mem0.count_signed([], "[pc2]") == 0


def test_signed_episodes_asks_the_bridge_for_the_messages(monkeypatch):
    a = mem0.Mem0Adapter()
    seen = []

    def fake(op, **kw):
        seen.append(op)
        return {"ok": True, "messages": [{"role": "user", "content": "[pc2] Sync the calendar cache"}]}
    monkeypatch.setattr(a, "_call", fake)
    assert a.signed_episodes("[pc2]") == 1 and seen == ["messages"]


def test_the_day_filter_sees_episodes_only(monkeypatch):
    a = mem0.Mem0Adapter()
    rows = [{"memory": "a card", "metadata": {"date": "2026-09-05", "kind": "card"}},
            {"memory": "an episode", "metadata": {"date": "2026-09-09T11:00:00", "kind": "episode"}}]
    monkeypatch.setattr(a, "rows", lambda: rows)
    assert a.recent_days(5) == ["2026-09-09"]
    assert a.episodes_of_day("2026-09-05", 5) == []
    assert [e["input_summary"] for e in a.episodes_of_day("2026-09-09", 5)] == ["an episode"]
    monkeypatch.setattr(a, "rows", lambda: rows[:1])
    assert a.recent_days(5) == []


def test_the_import_empties_only_a_mem0_store(tmp_path):
    from examples.mem0_import import is_mem0_store
    assert is_mem0_store(tmp_path / "missing")
    assert is_mem0_store(tmp_path)
    (tmp_path / "history.db").write_text("")
    (tmp_path / "qdrant").mkdir()
    assert is_mem0_store(tmp_path)
    (tmp_path / "notes.txt").write_text("mine")
    assert not is_mem0_store(tmp_path)


def test_no_other_cloud_key_reaches_the_bridge():
    for k in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY", "MEM0_API_KEY"):
        assert k in mem0._KEYS
    # the Gemini key is the one mem0 is configured with: passed through, read by the bridge
    assert "GOOGLE_API_KEY" not in mem0._KEYS


def test_a_write_that_stored_nothing_has_a_receipt_forget_accepts(monkeypatch):
    a = mem0.Mem0Adapter()
    monkeypatch.setattr(a, "add", lambda *args, **kw: [])
    ids = a.write_fact("The x connector listens on port 9000.")
    assert len(ids) == 1 and ids[0].startswith(mem0.NOOP)
    assert a.forget_memory(ids[0]) is True


def test_without_the_environment_the_bridge_refuses_to_start(monkeypatch):
    monkeypatch.setattr(mem0, "HOME", "")
    monkeypatch.setattr(mem0, "PY", "")
    a = mem0.Mem0Adapter()
    assert a.health() is False
