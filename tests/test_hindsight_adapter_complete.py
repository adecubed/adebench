"""The Hindsight adapter implements the whole adebench contract.

Checked without a server: the methods are read off the class, nothing is
instantiated (so no MCP session is opened), the same way
test_ade_adapter_complete.py checks the ADE adapter.
"""
from adebench import adapter, hindsight


def test_hindsight_adapter_honours_the_contract():
    missing = [m for m in adapter.required_methods()
               if not callable(getattr(hindsight.HindsightAdapter, m, None))]
    assert missing == [], f"HindsightAdapter is missing: {missing}"


def test_hindsight_adapter_has_the_write_probes():
    for m in ("write_fact", "forget_memory", "import_memory", "ingest_exchange", "declared_bytes"):
        assert callable(getattr(hindsight.HindsightAdapter, m, None)), m
