"""The TokenMizer adapter implements the whole adebench contract.

Checked without a server: the methods are read off the class, nothing is
instantiated (so no HTTP call is made), the same way
test_ade_adapter_complete.py checks the ADE adapter.
"""
from adebench import adapter, tokenmizer


def test_tokenmizer_adapter_honours_the_contract():
    missing = [m for m in adapter.required_methods()
               if not callable(getattr(tokenmizer.TokenmizerAdapter, m, None))]
    assert missing == [], f"TokenmizerAdapter is missing: {missing}"


def test_tokenmizer_writes_only_through_the_proxy():
    """The memory is built from conversations that pass through the proxy:
    write_fact is one such turn, and the live-state canary is not written at
    all (there is no working memory to hold it, nor a way to remove it)."""
    assert callable(tokenmizer.TokenmizerAdapter.write_fact)
    assert callable(tokenmizer.TokenmizerAdapter.forget_memory)
    assert tokenmizer.TokenmizerAdapter.working_write(object(), "s", "k", "v", 1) is None
