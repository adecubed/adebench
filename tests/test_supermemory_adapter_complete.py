"""The supermemory adapter implements the whole adebench contract.

Checked without a server: the methods are read off the class, and the rest
runs on canned API payloads through a fake `_req` (no HTTP), the same way
test_aionforge_adapter_complete.py checks the Aionforge adapter.
"""
from datetime import datetime, timezone

from adebench import adapter, supermemory
from adebench.config import LOCAL_TZ

A = supermemory.SupermemoryAdapter


def _utc(*args) -> str:
    return datetime(*args, tzinfo=LOCAL_TZ).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def test_supermemory_adapter_honours_the_contract():
    missing = [m for m in adapter.required_methods() if not callable(getattr(A, m, None))]
    assert missing == [], f"SupermemoryAdapter is missing: {missing}"


def test_supermemory_adapter_has_the_write_probes():
    for m in ("write_fact", "forget_memory", "import_memory", "ingest_exchange", "settle", "declared_bytes",
              "stored_mentions"):
        assert callable(getattr(A, m, None)), m


def test_dates_come_from_the_memory_never_from_the_write_time():
    # an extracted event date wins
    assert A._when({"metadata": {"temporalContext": {"eventDate": ["2026-08-20"]}},
                    "updatedAt": "2026-09-29T15:42:13Z"}) == "2026-08-20"
    # else the source document's documentDate
    assert A._when({"metadata": {}, "updatedAt": "2026-09-29T15:42:13Z",
                    "documents": [{"metadata": {"temporalContext": {"documentDate": "2021-03-14"}}}]}) == "2021-03-14"
    # nothing dated: no date, not updatedAt
    assert A._when({"metadata": None, "updatedAt": "2026-09-29T15:42:13Z"}) == ""


def test_naive_times_are_local_and_converted_to_utc():
    assert supermemory._iso("2026-09-10T09:12:00") == _utc(2026, 9, 10, 9, 12)
    assert supermemory._iso("2021-03-14") == _utc(2021, 3, 14, 12, 0)      # a date alone: local noon
    assert supermemory._iso("2021-03-14").startswith("2021-03-14")          # ... which keeps the day
    # a zone given is kept
    assert supermemory._iso("2026-09-10T09:12:00+02:00") == "2026-09-10T09:12:00+02:00"
    assert supermemory._iso("2026-09-10T09:12:00Z") == "2026-09-10T09:12:00Z"


def test_episode_documents_split_into_request_and_result():
    assert A._split("user: [pc2] Sync the calendar cache\nassistant: Cache refreshed") == \
        ("[pc2] Sync the calendar cache", "Cache refreshed")


class _Fake(A):
    """The adapter with `_req` answered from a table: (method, path) -> a
    dict, an HTTP status to raise, or a list of those served in turn."""

    def __init__(self, routes: dict) -> None:
        super().__init__()
        self.routes, self.calls = routes, []

    def _req(self, method, path, body=None, timeout=120, ok_codes=(200, 201, 204)):
        self.calls.append((method, path, body))
        r = self.routes.get((method, path))
        if isinstance(r, list):
            r = r.pop(0) if len(r) > 1 else r[0]
        if isinstance(r, int):
            raise supermemory.SupermemoryError(f"{method} {path}: HTTP {r}: nope")
        return r if r is not None else {}


EMPTY_LISTS = {("POST", "/v3/documents/list"): {"memories": [], "pagination": {"totalPages": 1}},
               ("POST", "/v4/memories/list"): {"memoryEntries": [], "pagination": {"totalPages": 1}}}

SEARCH = {"results": [
    {"id": "m1", "memory": "MailBridge 1.4.2 replaced version 1.3.0 on 2026-08-20.", "version": 1,
     "similarity": 0.84, "updatedAt": "2026-09-29T15:42:13Z",
     "metadata": {"temporalContext": {"eventDate": ["2026-08-20"]}}},
    {"id": "m2", "memory": "User synced the calendar cache on pc2.", "similarity": 0.5,
     "updatedAt": "2026-09-29T15:42:13Z", "metadata": {},
     "documents": [{"id": "d2", "metadata": {"kind": "episode", "temporalContext": {"documentDate": "2026-09-08"}}}]},
    {"id": "m3", "memory": "Undated fact.", "updatedAt": "2026-09-29T15:42:13Z", "metadata": None},
]}


def test_answer_renders_the_results_in_order_with_their_dates():
    a = _Fake({("POST", "/v4/search"): SEARCH})
    text, r = a.door_text("Which version of MailBridge?", "memories")
    assert text.splitlines() == ["[2026-08-20] MailBridge 1.4.2 replaced version 1.3.0 on 2026-08-20.",
                                 "[2026-09-08] User synced the calendar cache on pc2.",
                                 "Undated fact."]
    assert "2026-09-29" not in text                    # never the write time
    assert [e["created_at"] for e in r["episodic"]] == ["2026-09-08"]
    assert r["unknown_terms"] == []
    assert "searchMode" not in a.calls[0][2]           # the default door sends the API default


def test_answer_with_nothing_found_is_an_abstention():
    a = _Fake({("POST", "/v4/search"): {"results": [], "total": 0}})
    text, r = a.door_text("What does the Zarpetta module do?", "memories")
    assert text == "" and r["semantic"] == []
    assert "Zarpetta" in r["unknown_terms"]


def test_profile_door_puts_the_profile_before_the_results():
    a = _Fake({("POST", "/v4/profile"): {"profile": {"static": ["Alex is a designer."], "dynamic": []},
                                         "searchResults": SEARCH}})
    text, _ = a.door_text("Who is the owner?", "profile")
    assert text.splitlines()[0] == "Alex is a designer."


def test_404_is_a_removal_only_after_our_own_delete():
    a = _Fake({("DELETE", "/v3/documents/d1"): [{}, 404], ("DELETE", "/v3/documents/nope"): 404})
    assert a.forget_memory("d1") is True               # deleted now
    assert a.forget_memory("d1") is True               # 404, but we deleted it
    assert a.forget_memory("nope") is False            # 404 for an id never seen: a failed cleanup


def test_wait_done_tells_deleted_from_missing():
    a = _Fake({("GET", "/v3/documents/gone"): 404, ("GET", "/v3/documents/never"): 404,
               ("GET", "/v3/documents/ok"): {"status": "done", "dreamingStatus": "done"}})
    a._deleted.add("gone")
    assert a.wait_done(["gone", "never", "ok"], max_s=0) == {"gone": "deleted", "never": "missing", "ok": "done"}


def test_settle_warns_when_documents_are_still_pending():
    a = _Fake({("GET", "/v3/documents/slow"): {"status": "extracting", "dreamingStatus": None}, **EMPTY_LISTS})
    a.settle_max_s = 0
    a._pending = ["slow"]
    a.settle()
    measures, warnings = a.health_report()
    assert measures["settles_timed_out"] == 1
    assert any("still not processed" in w for w in warnings)
    assert measures["setup"]["llm"].startswith("gemini-3.1-flash-lite-preview")
    assert measures["memories_forgotten"] is None and measures["superseded_live"] is None
    assert "url" not in measures


def test_live_state_overwrite_hard_deletes_the_backing_document():
    a = _Fake({("POST", "/v4/memories"): [{"documentId": "doc1", "memories": [{"id": "mem1"}]},
                                          {"documentId": "doc2", "memories": [{"id": "mem2"}]}],
               ("DELETE", "/v3/documents/doc1"): {}, ("DELETE", "/v3/documents/doc2"): {}, **EMPTY_LISTS})
    assert a.working_write("s", "k", "one", 1)
    assert a.working_write("s", "k", "two", 1)          # overwrite: doc1 goes
    a.working_clear("s")                                 # clear: doc2 goes
    assert [p for m, p, _ in a.calls if m == "DELETE"] == ["/v3/documents/doc1", "/v3/documents/doc2"]
    measures, _ = a.health_report()
    assert measures["live_state_writes"]["residue"] == 0


def test_live_state_without_a_document_falls_back_to_forget_and_counts_residue():
    a = _Fake({("POST", "/v4/memories"): [{"memories": [{"id": "mem1"}]}, {"memories": [{"id": "mem2"}]}],
               ("DELETE", "/v4/memories"): {"id": "mem1", "forgotten": True}, **EMPTY_LISTS})
    a.working_write("s", "k", "one", 1)
    a.working_write("s", "k", "two", 1)
    measures, warnings = a.health_report()
    assert measures["live_state_writes"]["soft_forgotten"] == 1
    assert measures["live_state_writes"]["residue"] == 1
    assert any("live state left 1" in w for w in warnings)
