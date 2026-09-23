"""The Mitosis Cortex adapter implements the whole adebench contract.

Checked without a server: the methods are read off the class, nothing is
instantiated (so no HTTP call is made), the same way
test_ade_adapter_complete.py checks the ADE adapter.
"""
from adebench import adapter, mitosis


def test_mitosis_adapter_honours_the_contract():
    missing = [m for m in adapter.required_methods()
               if not callable(getattr(mitosis.MitosisAdapter, m, None))]
    assert missing == [], f"MitosisAdapter is missing: {missing}"


def test_mitosis_adapter_writes_nothing_while_it_cannot_remove_it():
    """Cortex declares no delete tool, so the adapter offers no write path:
    no write_fact, no ingest_exchange, no import_memory, and a canary write
    that returns None (the live_state case SKIPs instead of failing)."""
    for method in ("write_fact", "ingest_exchange", "import_memory", "forget_memory"):
        assert not hasattr(mitosis.MitosisAdapter, method), method
    assert mitosis.MitosisAdapter.working_write(object(), "s", "k", "v", 1) is None


def test_the_sse_envelope_is_read_like_the_json_one():
    payload = '{"jsonrpc":"2.0","id":1,"result":{"content":[{"type":"text","text":"hi"}]}}'
    assert mitosis.MitosisAdapter._envelope(payload)["result"]["content"][0]["text"] == "hi"
    stream = f"event: message\ndata: {payload}\n\n"
    assert mitosis.MitosisAdapter._envelope(stream)["result"]["content"][0]["text"] == "hi"
