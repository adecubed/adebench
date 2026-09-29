"""The Nemp adapter implements the whole adebench contract (checked on the
class: nothing is run, no model turn is spent)."""
from adebench import adapter, nemp


def test_nemp_adapter_honours_the_contract():
    missing = [m for m in adapter.required_methods() if not callable(getattr(nemp.NempAdapter, m, None))]
    assert missing == [], f"NempAdapter is missing: {missing}"


def test_nemp_adapter_has_the_write_probes():
    for m in ("write_fact", "forget_memory", "import_memory", "ingest_exchange"):
        assert callable(getattr(nemp.NempAdapter, m, None)), m


def test_slug():
    assert nemp.slug("mail_bridge") == "mail-bridge"
    assert nemp.slug("The Brain: port!") == "the-brain-port"
