"""The ADE adapter implements the whole contract.

2026-09-16: a module-level function was pasted inside the class body and
silently pushed two methods out of it; the loader refused the adapter at
the next real run. The unit tests drive a fake adapter, so nothing noticed."""
from adebench import adapter, ade


def test_ade_adapter_implements_every_required_method():
    missing = [m for m in adapter.required_methods() if not callable(getattr(ade.AdeAdapter, m, None))]
    assert missing == []
