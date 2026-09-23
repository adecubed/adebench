"""The Memoose adapter implements the whole adebench contract.

Checked without memoose installed: the methods are read off the class,
nothing is instantiated (so no CLI call is made), the same way
test_ade_adapter_complete.py checks the ADE adapter.
"""
from adebench import adapter, memoose


def test_memoose_adapter_honours_the_contract():
    missing = [m for m in adapter.required_methods()
               if not callable(getattr(memoose.MemooseAdapter, m, None))]
    assert missing == [], f"MemooseAdapter is missing: {missing}"


def test_memoose_adapter_reads_its_sqlite_read_only():
    """The dataset is opened read-only: adebench writes through the CLI, never
    behind Memoose's back."""
    import inspect
    src = inspect.getsource(memoose.MemooseAdapter._sql)
    assert "mode=ro" in src and "uri=True" in src
