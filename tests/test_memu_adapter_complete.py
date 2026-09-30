"""The memU adapter implements the whole adebench contract.

Checked without memU: the methods are read off the class, nothing is
instantiated that would start the bridge process.
"""
import json
import re

from adebench import adapter, memu, memu_bridge


def test_memu_adapter_honours_the_contract():
    missing = [m for m in adapter.required_methods()
               if not callable(getattr(memu.MemuAdapter, m, None))]
    assert missing == [], f"MemuAdapter is missing: {missing}"


def test_memu_adapter_has_the_write_probes():
    for m in ("write_fact", "forget_memory", "import_memory", "ingest_exchange", "settle",
              "declared_bytes", "stored_mentions"):
        assert callable(getattr(memu.MemuAdapter, m, None)), m


def test_the_default_door_is_retrieve():
    assert memu.DOORS[0] == "retrieve"


def test_the_retrieve_door_is_what_memu_retrieve_prints():
    result = {"segments": [{"text": "Port: 8766", "created_at": "2026-09-29T10:00:00", "recall_file_id": "a"}],
              "files": [{"id": "a", "track": "memory", "name": "brain", "content": "- Port: 8766"}],
              "resources": []}
    d = {"result": result, "shaped": {"segments": [], "files": [{"path": "~/.memu/memory/brain.md"}]}}
    text = memu.printed(memu.door_payload(d, "retrieve"))
    assert json.loads(text) == result and text.startswith('{\n  "segments"')
    assert "~/.memu/memory/brain.md" in memu.printed(memu.door_payload(d, "hook"))


def test_no_storage_date_is_presented_as_age(monkeypatch):
    result = {"segments": [{"text": "Port: 8766", "created_at": "2026-09-29T10:00:00", "recall_file_id": "a"}],
              "files": [{"id": "a", "track": "memory", "name": "brain"}], "resources": []}
    a = memu.MemuAdapter()
    monkeypatch.setattr(a, "_retrieve", lambda q, door: {"result": result})
    r = a.ask("port?")
    assert [s["content"] for s in r["semantic"]] == ["Port: 8766"]


def _strings(x):
    if isinstance(x, dict):
        for v in x.values():
            yield from _strings(v)
    elif isinstance(x, (list, tuple)):
        for v in x:
            yield from _strings(v)
    else:
        yield str(x)


class _FakeBridge:
    def __init__(self, info):
        self.info = info

    def call(self, op, **kw):
        return {"ok": True, "executor": memu_bridge.executor_setup(), "usage": {},
                "files": 0, "embed_dims": 3}


def test_health_report_names_the_executor_and_carries_no_absolute_path():
    a = memu.MemuAdapter()
    a._b = _FakeBridge(memu_bridge.info_dict("0.11.0b3", 5, 1.0))
    measures, _ = a.health_report()
    dumped = json.dumps(measures)
    assert not re.search(r"[A-Za-z]:\\|/Users/|/home/", dumped), dumped
    assert all(str(memu_bridge.STORE) not in v for v in _strings(measures))
    assert measures["executor"]["model"] == memu_bridge.LLM_MODEL
    assert "a shell" in measures["executor"]["tools_not_given"]


class _FakeService:
    def __init__(self, files):
        self.files, self.commits = files, []

    async def list_all_recall_files(self, cursor=None):
        return {"recall_files": self.files, "next_cursor": None}

    async def commit_results(self, recall_files=None, resource=None, user=None):
        self.commits.append(recall_files)
        return {"recall_files": recall_files}


def test_forget_refuses_when_the_file_changed_after_the_run(monkeypatch):
    svc = _FakeService([{"track": "memory", "name": "zeta", "content": "port 9000, and a later edit"}])
    monkeypatch.setattr(memu_bridge, "svc", svc)
    monkeypatch.setitem(memu_bridge._runs, "r1", [{"track": "memory", "name": "zeta",
                                                   "before": {"content": "port 8000", "description": "d"},
                                                   "after": "port 9000"}])
    ans = memu_bridge.op_forget({"id": "r1"})
    assert ans["ok"] is False and "changed since" in ans["error"]
    assert svc.commits == [] and "r1" in memu_bridge._runs


def test_forget_reverts_when_nothing_changed_since(monkeypatch):
    svc = _FakeService([{"track": "memory", "name": "zeta", "content": "port 9000"}])
    monkeypatch.setattr(memu_bridge, "svc", svc)
    monkeypatch.setitem(memu_bridge._runs, "r2", [{"track": "memory", "name": "zeta",
                                                   "before": None, "after": "port 9000"}])
    ans = memu_bridge.op_forget({"id": "r2"})
    assert ans == {"ok": True, "reverted": 1}
    assert svc.commits == [[{"name": "zeta", "track": "memory", "description": "", "content": ""}]]


def test_no_other_key_reaches_the_bridge():
    for k in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "JINA_API_KEY", "VOYAGE_API_KEY", "MEMU_API_KEY"):
        assert k in memu._KEYS
    assert "GOOGLE_API_KEY" not in memu._KEYS


def test_without_the_environment_the_bridge_refuses_to_start(monkeypatch):
    monkeypatch.setattr(memu, "HOME", "")
    monkeypatch.setattr(memu, "PY", "")
    a = memu.MemuAdapter()
    assert a.health() is False
