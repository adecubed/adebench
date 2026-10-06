"""Search for the private set's canary anywhere it must not be (spec section 5).

The canary is a random token the generator writes into a few facts of the
private set. If it turns up outside the private folder (a repository, a
memory's default data or cache folder, a session transcript, the temp
folder), the private set has leaked.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

HOME = Path.home()
# the adebench repo; ~/ade or ADEBENCH_ADE_DIR (the orchestrator repo, the live Brain's data and
# bench_memories with every memory's install); the memories' default homes; Ollama's logs;
# the session transcripts; the temp folder
DEFAULT_ROOTS = [Path(__file__).resolve().parents[1], Path(os.environ.get("ADEBENCH_ADE_DIR") or Path.home() / "ade"),
                 *(HOME / d for d in (".mem0", ".cognee", ".engram", ".agentmemory", ".memu", ".gbrain", ".memoose")),
                 HOME / ".ollama" / "logs", HOME / ".claude" / "projects", Path(tempfile.gettempdir())]
WEIGHTS = {".safetensors", ".bin", ".onnx", ".gguf", ".pt"}
# trees that hold installed code, never data a memory wrote about the set; a Python virtual
# environment of any name (it has a pyvenv.cfg) too: they were 95% of the files under
# ~/ade and made a cold scan take most of an hour
PRUNE = {".git", "node_modules", "__pycache__", ".pytest_cache", "site-packages"}


def _installed(path: str) -> bool:
    return os.path.exists(os.path.join(path, "pyvenv.cfg"))


def _reparse(path: str) -> bool:
    """A symlink or an NTFS junction: not followed (os.walk follows junctions before 3.12)."""
    try:
        st = os.lstat(path)
    except OSError:
        return True
    return os.path.islink(path) or bool(getattr(st, "st_file_attributes", 0) & 0x400)


def scan(token: str, roots: list[Path], exclude: list[Path], max_bytes: int = 20_000_000) -> list[Path]:
    needle = token.encode()
    skip = [Path(e).resolve() for e in exclude]
    hits = []
    for root in roots:
        root = Path(root)
        if not root.exists():
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            here = Path(dirpath).resolve()
            if any(here == s or s in here.parents for s in skip):
                dirnames[:] = []
                continue
            dirnames[:] = [d for d in dirnames if d not in PRUNE and not _reparse(os.path.join(dirpath, d))
                           and not _installed(os.path.join(dirpath, d))]
            for f in filenames:
                p = Path(dirpath) / f
                try:
                    if p.suffix in WEIGHTS or p.stat().st_size > max_bytes:
                        continue
                    if needle in p.read_bytes():
                        hits.append(p)
                except OSError:
                    continue
    return sorted(hits)
