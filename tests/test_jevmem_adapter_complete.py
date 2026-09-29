"""The Jev-Mem adapter implements the whole adebench contract.

Checked without Jev-Mem: the methods are read off the class, nothing is
instantiated (so no bridge process is started).
"""
from adebench import adapter, jevmem


def test_jevmem_adapter_honours_the_contract():
    missing = [m for m in adapter.required_methods()
               if not callable(getattr(jevmem.JevMemAdapter, m, None))]
    assert missing == [], f"JevMemAdapter is missing: {missing}"


def test_jevmem_adapter_has_the_write_probes():
    for m in ("write_fact", "forget_memory", "import_memory", "ingest_exchange"):
        assert callable(getattr(jevmem.JevMemAdapter, m, None)), m


def test_evidence_items_are_parsed():
    lines = ["1. **MOST RELEVANT** [10 May 2026] The Brain listens on port 8000.",
             "2. *Highly Relevant* [01 September 2026] The Brain now listens on port 9000.",
             "   Original: The Brain now listens on port 9000."]
    got = [jevmem._ITEM.match(x) for x in lines]
    assert got[0].group(1) == "10 May 2026" and got[0].group(2).startswith("The Brain listens")
    assert got[1].group(2).endswith("9000.")
    assert got[2] is None
