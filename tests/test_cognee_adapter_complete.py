"""The cognee adapter implements the whole adebench contract.

Checked without cognee: the methods are read off the class, nothing is
instantiated (so no bridge process is started).
"""
import inspect

from adebench import adapter, cognee


def test_cognee_adapter_honours_the_contract():
    missing = [m for m in adapter.required_methods()
               if not callable(getattr(cognee.CogneeAdapter, m, None))]
    assert missing == [], f"CogneeAdapter is missing: {missing}"


def test_cognee_adapter_has_the_write_probes():
    for m in ("write_fact", "forget_memory", "import_memory", "ingest_exchange", "declared_bytes"):
        assert callable(getattr(cognee.CogneeAdapter, m, None)), m


def test_the_default_door_is_the_context_in_gemini_mode_recall_in_gliner_mode():
    assert cognee.DOORS[0] == ("context" if cognee.MODE == "gemini" else "recall")


def test_passages_are_read_off_the_hybrid_context_with_their_date():
    ctx = ("The question is: `q`\nContext:\n`## Relevant passages\ndate: 2026-08-20\n"
           "MailBridge 1.4.2 replaced 1.3.0 on 2026-08-20.\n---\nAlex lives in Turin.\n\n"
           "## Relevant entities\n### alex\n- alex is a person.`")
    assert cognee.passages(ctx) == [("2026-08-20", "MailBridge 1.4.2 replaced 1.3.0 on 2026-08-20."),
                                    ("", "Alex lives in Turin.")]
    last = "Context:\n`## Relevant passages\ndate: 2021-03-14T09:30:00\nthe spare keys are in the blue box`"
    assert cognee.passages(last) == [("2021-03-14T09:30:00", "the spare keys are in the blue box")]
    assert cognee.passages("no context") == []


def test_a_hit_carries_the_date_it_was_given_and_no_storage_time_otherwise():
    dated = {"text": "Backups run on Sundays at 03:00.", "external_metadata": {"date": "2026-03-01"},
             "created_at": 1790696207786}
    assert cognee.hit_line(dated) == "[2026-03-01] Backups run on Sundays at 03:00."
    undated = {"text": "'agenda' is another name for calendar.", "external_metadata": {},
               "created_at": 1790696207786}
    assert cognee.hit_line(undated) == "'agenda' is another name for calendar."
    assert cognee.hit_line({"text": "x", "external_metadata": {}, "created_at": None}) == "x"


class _FakeBridge:
    info = {"ok": True, "cognee_version": "1.6.1", "store": r"C:\Users\someone\cognee\adebench_store_gemini",
            "llm": "gemini:gemini/gemini-3-flash-preview", "extractor": "llm",
            "embedding": "gemini:gemini/gemini-embedding-001 (768 dims)"}

    def call(self, op, **kw):
        if op == "health":
            return {"ok": True, "status": "healthy", "dataset_exists": True,
                    "components": {"file_storage": {"status": "healthy",
                                                    "details": "file:///C:/Users/someone/cognee/data ok"}}}
        if op == "usage":
            return {"ok": True, "usage": {}}
        return {"ok": True}


def test_health_report_carries_no_absolute_path_and_says_the_door_setup():
    a = cognee.CogneeAdapter()
    a._b = _FakeBridge()
    measures, warnings = a.health_report()
    text = repr(measures) + repr(warnings)
    assert "someone" not in text and "C:\\" not in text and "file:///" not in text
    assert "adebench_store_gemini" in text
    assert "setup" in measures


def test_health_needs_healthy_and_unknown_doors_raise():
    a = cognee.CogneeAdapter()

    class Degraded(_FakeBridge):
        def call(self, op, **kw):
            return {"ok": True, "status": "degraded", "dataset_exists": True}
    a._b = Degraded()
    assert a.health() is False
    a._b = _FakeBridge()
    assert a.health() is True
    try:
        a.door_text("q", "nope")
    except cognee.CogneeError:
        pass
    else:
        raise AssertionError("an unknown door must raise")


def test_no_other_cloud_key_reaches_the_bridge_and_none_on_the_command_line():
    for k in ("LLM_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY"):
        assert k in cognee._KEYS
    src = inspect.getsource(cognee._Bridge.__init__)
    argv = src.split("Popen(")[1].split("stdin=")[0]
    assert "KEY" not in argv


def test_without_the_environment_the_bridge_refuses_to_start(monkeypatch):
    monkeypatch.setattr(cognee, "HOME", "")
    monkeypatch.setattr(cognee, "PY", "")
    a = cognee.CogneeAdapter()
    assert a.health() is False
