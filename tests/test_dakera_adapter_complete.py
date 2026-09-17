"""The Dakera adapter implements the whole adebench contract.

Checked without a running server: the methods are read off the class, nothing
is instantiated (so no HTTP call is made), the same way
test_ade_adapter_complete.py checks the ADE adapter.
"""
from adebench import adapter, dakera


def test_dakera_adapter_honours_the_contract():
    missing = [m for m in adapter.required_methods()
               if not callable(getattr(dakera.DakeraAdapter, m, None))]
    assert missing == [], f"DakeraAdapter is missing: {missing}"
