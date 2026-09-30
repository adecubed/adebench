"""Every memory on the board declares its configuration, field by field."""
from __future__ import annotations

import re

from adebench import site


def test_every_memory_on_the_board_declares_its_configuration():
    missing = {}
    for m in site.MEMORIES:
        cfg = site.load_config(m["folder"], m.get("file", "reference"))
        if cfg is None:
            missing[m["name"]] = "no memory.json"
            continue
        empty = [f for f in site.CONFIG_FIELDS if not str(cfg.get(f, "")).strip()]
        if empty:
            missing[m["name"]] = empty
    assert missing == {}, missing


def test_a_configuration_carries_no_local_path_or_key():
    for m in site.MEMORIES:
        cfg = site.load_config(m["folder"], m.get("file", "reference")) or {}
        text = " ".join(str(v) for v in cfg.values())
        assert not re.search(r"[A-Za-z]:[\\/]|/Users/|/home/|/opt/|AIza[0-9A-Za-z_-]{20}", text), m["name"]
