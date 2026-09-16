"""A golden set saved by a Windows editor often starts with a UTF-8 BOM.
That is not a reason to lose a whole section: 2026-09-16 the abstention
section scored 0 because PowerShell had written the file with a BOM."""
from adebench import sections
from adebench.config import CFG


def test_golden_set_with_bom_is_read(tmp_path, monkeypatch):
    monkeypatch.setattr(CFG, "cases", tmp_path)
    (tmp_path / "abstention.json").write_bytes(b"\xef\xbb\xbf[\"Cos'e' Zarpetta?\"]")
    assert sections._load("abstention.json") == ["Cos'e' Zarpetta?"]
