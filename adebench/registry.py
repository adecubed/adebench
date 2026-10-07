"""How to run each memory, one entry per board row, for public and private runs alike.

    adapter    module:Class for `python -m adebench --adapter`
    import     the import script (path from the repository root), None when the adapter loads the set itself
    store_env  the variable through which the memory takes its data folder; the runner points it at a
               fresh folder per build and deletes it afterwards
    env        variables the memory needs, `{store}` replaced by the store folder. Every run starts
               without the parent's ADEBENCH_*, MEM0_*... variables (DROP_ENV): set them here
    server     optional: a server started per build on the fresh store (adebench/builds.py). Its cmd
               names the real executable, never a launcher (npm, a .cmd): on Windows killing a
               launcher leaves its child running
    cleanup    other folders the memory writes the set into, deleted after a private run and scanned
    folder     examples/<folder>: where the public runs and the outcome go
    file       "reference" or "reference_gemini": the board row this entry measures
    model      a model inside: 5 public and 3 private builds, otherwise 3 and 1 (spec section 4)
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# variables of the parent shell that would change what is measured or where a memory writes
# (ADEBENCH_DOOR, ADEBENCH_PRESSURE, BRAIN_URL...): every run, public or private, starts
# without them and gets only what its entry sets
DROP_ENV = ("ADEBENCH_", "BRAIN_", "SUPERMEMORY_", "MEM0_", "COGNEE_", "MEMU_", "ENGRAM_", "AGENTMEMORY_",
            "DAKERA_", "HINDSIGHT_", "AIONFORGE_", "GBRAIN_", "MEMOOSE_", "JEVMEM_", "NEMP_", "TOKENMIZER_")

# where each memory is installed; the defaults are relative to the home folder
BENCH = os.environ.get("ADEBENCH_BENCH_DIR") or (Path.home() / "ade" / "bench_memories").as_posix()
GBRAIN = os.environ.get("ADEBENCH_GBRAIN_BIN") or (Path.home() / ".bun" / "bin" / "gbrain.exe").as_posix()
# gbrain.exe looks for bun.exe on PATH
BUN_DIR = os.environ.get("ADEBENCH_BUN_DIR") or (Path.home() / "AppData" / "Roaming" / "npm" / "node_modules"
                                                 / "bun" / "bin").as_posix()
AGENTMEMORY_CLI = f"{BENCH}/agentmemory/node_modules/@agentmemory/agentmemory/dist/cli.mjs"
# the flags of the published runs: every section, the write-back probe, no sandbox test
FULL = ["--write-back", "--no-sandbox-test"]

# agentmemory runs its own server (the CLI starts iii.exe, which starts the worker) on a fresh data
# folder; HOME points at the install's home, where the pinned iii 0.11.2 binary is
_AGENTMEMORY_SERVER = {
    "cmd": ["node", AGENTMEMORY_CLI], "cwd": "{store}",
    "env": {"AGENTMEMORY_DATA_DIR": "{store}", "AGENTMEMORY_III_CONFIG": f"{BENCH}/agentmemory/iii-config.loopback.yaml",
            "HOME": f"{BENCH}/agentmemory/home", "USERPROFILE": f"{BENCH}/agentmemory/home"},
    "health": "http://127.0.0.1:3111/agentmemory/health", "wait_s": 180}
_AGENTMEMORY_GEMINI_ENV = {"GEMINI_MODEL": "gemini-3-flash-preview", "EMBEDDING_PROVIDER": "gemini",
                           "AGENTMEMORY_AUTO_COMPRESS": "true", "GRAPH_EXTRACTION_ENABLED": "true",
                           "CONSOLIDATION_ENABLED": "true"}

REGISTRY: dict[str, dict] = {
    "synthetic": {"adapter": "examples.synthetic:SyntheticAdapter", "import": None, "store_env": None, "env": {},
                  "flags": ["--sections", "door", "updates", "time", "abstention", "--no-sandbox-test"],
                  "folder": None, "file": "reference", "model": False},
    "engram": {"adapter": "adebench.engram:EngramAdapter", "import": "examples/engram_import.py",
               "store_env": "ENGRAM_DATA_DIR", "env": {"ENGRAM_BIN": f"{BENCH}/engram/bin/engram.exe"},
               "flags": FULL, "folder": "engram_report", "file": "reference", "model": False},
    "memoose": {"adapter": "adebench.memoose:MemooseAdapter", "import": "examples/memoose_import.py",
                "store_env": "MEMOOSE_DATA_DIR", "env": {},
                "flags": ["--sandbox-test", "examples/memoose_sandbox_test.py"],
                "folder": "memoose_report", "file": "reference", "model": False},
    # gbrain keeps its brain under GBRAIN_HOME/.gbrain: a fresh home, initialised like the published run
    "gbrain": {"adapter": "adebench.gbrain:GbrainAdapter", "import": "examples/gbrain_import.py", "store_env": None,
               "env": {"GBRAIN_HOME": "{store}", "ADEBENCH_GBRAIN_BIN": GBRAIN,
                       "PATH": BUN_DIR + os.pathsep + os.environ.get("PATH", "")},
               "prepare": [[GBRAIN, "init", "--pglite", "--non-interactive",
                            "--embedding-model", "ollama:nomic-embed-text", "--embedding-dimensions", "768",
                            "--expansion-model", "ollama:llama3.2:3b", "--chat-model", "ollama:llama3.2:3b"]],
               "flags": FULL, "folder": "gbrain_report", "file": "reference", "model": False},
    "jevmem": {"adapter": "adebench.jevmem:JevMemAdapter", "import": "examples/jevmem_import.py",
               "store_env": "JEVMEM_STORE",
               "env": {"JEVMEM_HOME": f"{BENCH}/Jev-Mem", "JEVMEM_PYTHON": f"{BENCH}/Jev-Mem/.venv/Scripts/python.exe"},
               "flags": FULL, "folder": "jevmem_report", "file": "reference", "model": True},
    "agentmemory": {"adapter": "adebench.agentmemory:AgentmemoryAdapter", "import": "examples/agentmemory_import.py",
                    "store_env": None,
                    "env": {"AGENTMEMORY_URL": "http://127.0.0.1:3111", "AGENTMEMORY_SCRATCH": "{store}"},
                    "server": dict(_AGENTMEMORY_SERVER, env={**_AGENTMEMORY_SERVER["env"], "EMBEDDING_PROVIDER": "local",
                                                             "GEMINI_API_KEY": "", "GOOGLE_API_KEY": ""}),
                    "flags": FULL, "folder": "agentmemory_report", "file": "reference", "model": False},
    "agentmemory_gemini": {"adapter": "adebench.agentmemory:AgentmemoryAdapter",
                           "import": "examples/agentmemory_import.py", "store_env": None,
                           "env": {"AGENTMEMORY_URL": "http://127.0.0.1:3111", "AGENTMEMORY_SCRATCH": "{store}"},
                           "server": dict(_AGENTMEMORY_SERVER, env={**_AGENTMEMORY_SERVER["env"], **_AGENTMEMORY_GEMINI_ENV}),
                           "flags": FULL, "folder": "agentmemory_report", "file": "reference_gemini", "model": True},
    "supermemory": {"adapter": "adebench.supermemory:SupermemoryAdapter", "import": "examples/supermemory_import.py",
                    "store_env": None, "env": {"SUPERMEMORY_URL": "http://127.0.0.1:3951"},
                    "server": {"cmd": [f"{BENCH}/supermemory/bin/supermemory-server.exe"], "cwd": "{store}",
                               "env": {"SUPERMEMORY_DATA_DIR": "{store}", "PORT": "3951"},
                               "health": "http://127.0.0.1:3951/v3/health", "wait_s": 180},
                    "flags": FULL, "folder": "supermemory_report", "file": "reference", "model": True},
    "mem0": {"adapter": "adebench.mem0:Mem0Adapter", "import": "examples/mem0_import.py", "store_env": "MEM0_STORE",
             "env": {"MEM0_HOME": f"{BENCH}/mem0", "MEM0_PYTHON": f"{BENCH}/mem0/.venv/Scripts/python.exe"},
             "flags": FULL, "folder": "mem0_report", "file": "reference", "model": True},
    "cognee": {"adapter": "adebench.cognee:CogneeAdapter", "import": "examples/cognee_import.py",
               "store_env": "COGNEE_STORE",
               "env": {"COGNEE_HOME": f"{BENCH}/cognee", "COGNEE_PYTHON": f"{BENCH}/cognee/.venv/Scripts/python.exe",
                       "COGNEE_LLM": "gemini"},
               "flags": FULL, "folder": "cognee_report", "file": "reference", "model": True},
    "memu": {"adapter": "adebench.memu:MemuAdapter", "import": "examples/memu_import.py", "store_env": "MEMU_STORE",
             "env": {"MEMU_HOME": f"{BENCH}/memu", "MEMU_PYTHON": f"{BENCH}/memu/.venv/Scripts/python.exe"},
             "flags": FULL, "folder": "memu_report", "file": "reference", "model": True},
    # TokenMizer is a proxy: its server runs on the build's store with examples/tokenmizer.yaml; it
    # reads its Gemini key only as TOKENMIZER_GEMINI_API_KEY, taken from the environment
    "tokenmizer": {"adapter": "adebench.tokenmizer:TokenmizerAdapter", "import": "examples/tokenmizer_import.py",
                   "store_env": None,
                   "env": {"TOKENMIZER_URL": "http://127.0.0.1:8020",
                           "TOKENMIZER_MCP": f"{BENCH}/tokenmizer/.venv/Scripts/tokenmizer-mcp.exe",
                           "TOKENMIZER_STORAGE_DIR": "{store}/checkpoints"},
                   "prepare": [[sys.executable, "-c", "import shutil, sys; shutil.copy(sys.argv[1], 'tokenmizer.yaml')",
                                str(ROOT / "examples" / "tokenmizer.yaml")]],
                   "server": {"cmd": [f"{BENCH}/tokenmizer/.venv/Scripts/tokenmizer.exe", "serve",
                                      "--config", "{store}/tokenmizer.yaml", "--port", "8020"],
                              "cwd": "{store}", "env": {"TOKENMIZER_GEMINI_API_KEY": "{env:GEMINI_API_KEY}"},
                              "health": "http://127.0.0.1:8020/health", "wait_s": 120},
                   "flags": ["--sections", "door", "cards", "updates", "time", "abstention", "file_search", "graph",
                             "--write-back", "--no-sandbox-test"],
                   "folder": "tokenmizer_report", "file": "reference", "model": True},
}


def clean_env() -> dict:
    return {k: v for k, v in os.environ.items() if not k.startswith(DROP_ENV)}


def entry(name: str) -> dict:
    e = REGISTRY.get(name)
    if e is None:
        raise SystemExit(f"no registry entry for {name!r}")
    return e


def builds_for(name: str, private: bool) -> int:
    model = entry(name).get("model", False)
    return (3 if model else 1) if private else (5 if model else 3)
