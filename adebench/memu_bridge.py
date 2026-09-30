"""The memU side of the adebench adapter: one process, run with memU's own
Python, that keeps a memU MemoryService open and answers JSON lines on stdin.

    <memU venv>/python -m adebench.memu_bridge   (started by adebench.memu)

It imports nothing from adebench and nothing adebench imports from it: the
harness stays dependency-free, memU stays in its own environment. Every
request is one line {"op": ..., ...}; every answer one line {"ok": ..., ...}.
Logging goes to stderr, so stdout carries answers only.

memU itself calls no LLM: `MemoryService` only embeds and stores. Its memorize
path is prepare -> an external agent carries out the job files -> commit
(docs/developer.md). This bridge runs memU's own prepare_memorize and
commit_memorize, and in between it is that external agent: a Gemini model
driven through Google's OpenAI-compatible endpoint, handed memU's own executor
prompt, with a few file tools confined to the workspace (no shell).

Everything lives under MEMU_STORE: the SQLite store, the memorize workspace
(memU's CLI fixes it at ~/.memu/developer; the library takes it as a
parameter) and a private HOME, so no `~` of memU's resolves into the user's
home. The process runs with MEMU_STORE as its working directory and the
workspace is given to memU as the RELATIVE path `workspace`, so the job files,
the executor prompt and every tool answer the model sees carry no absolute
path (and no user name). Telemetry, template refresh and docs refresh are
switched off. The only key this process uses is GOOGLE_API_KEY, read here
from the environment.

Environment: MEMU_HOME, MEMU_STORE (see adebench.memu), GOOGLE_API_KEY,
MEMU_EXECUTOR_MODEL (default gemini-3-flash-preview), MEMU_EMBED_MODEL_ADEBENCH
(default gemini-embedding-001), MEMU_EXECUTOR_MAX_STEPS (tool-call turns the
executor may take for one prepared run before it is abandoned, default 200).
"""
from __future__ import annotations

import asyncio
import copy
import json
import os
import shutil
import sys
import time
import traceback
from pathlib import Path

HOME = Path(os.environ.get("MEMU_HOME", ".")).resolve()
STORE = Path(os.environ.get("MEMU_STORE", "") or HOME / "adebench_store").resolve()
DB = STORE / "memu.sqlite3"
WS_REL = Path("workspace")           # what memU and the model see
WORKSPACE = STORE / WS_REL           # where it is
FAKE_HOME = STORE / "home"
GOOGLE_OPENAI = "https://generativelanguage.googleapis.com/v1beta/openai/"
LLM_MODEL = os.environ.get("MEMU_EXECUTOR_MODEL", "gemini-3-flash-preview")
EMBED_MODEL = os.environ.get("MEMU_EMBED_MODEL_ADEBENCH", "gemini-embedding-001")
VERIFY_COMMAND = "memu memorize verify-resources"
MAX_STEPS = int(os.environ.get("MEMU_EXECUTOR_MAX_STEPS", "200"))

LOOP = asyncio.new_event_loop()
svc = None
llm = None
# run id -> [{track, name, before: file dict | None, after: content committed}]
_runs: dict[str, list[dict]] = {}
USAGE = {"llm_calls": 0, "llm_prompt_tokens": 0, "llm_completion_tokens": 0, "llm_total_tokens": 0,
         "llm_errors": 0, "embed_calls": 0, "embed_texts": 0, "embed_chars": 0,
         "memorize_runs": 0, "memorize_sessions": 0, "memorize_s": 0.0, "noop_runs": 0,
         "discarded_runs": 0}


def setup_environment() -> None:
    """Run once in the bridge process (never on import: tests import this module)."""
    for k in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "JINA_API_KEY", "VOYAGE_API_KEY", "ARK_API_KEY",
              "OPENROUTER_API_KEY", "MEMU_API_KEY", "MEMU_CLOUD_API_KEY", "MEMU_DB", "MEMU_BASE_URL",
              "MEMU_EMBED_PROVIDER", "MEMU_LLM_PROVIDER", "MEMU_EMBED_MODEL", "MEMU_MEMORY_MODE"):
        os.environ.pop(k, None)
    STORE.mkdir(parents=True, exist_ok=True)
    FAKE_HOME.mkdir(parents=True, exist_ok=True)
    os.environ.update({
        "HOME": str(FAKE_HOME), "USERPROFILE": str(FAKE_HOME),       # every ~ of memU lands here
        "MEMU_CONFIG_ENV": str(FAKE_HOME / ".memu" / "config.env"),  # absent: no user config read
        "MEMU_TELEMETRY": "0", "DO_NOT_TRACK": "1", "MEMU_EVENTS_BASE_URL": "",
        "MEMU_TEMPLATE_BASE_URL": "",   # the job templates embedded in this memU build, not a server copy
        "MEMU_DOCS_BASE_URL": "",
        "MEMU_MEMORY_MODE": "local",
    })
    os.chdir(STORE)


def run(coro):
    return LOOP.run_until_complete(coro)


def _key() -> str:
    k = os.environ.get("GOOGLE_API_KEY", "")
    if not k:
        raise RuntimeError("GOOGLE_API_KEY is not set in the bridge environment")
    return k


# ── the executor: the external agent memU's memorize hands its jobs to ─────

SYSTEM = """You are the external agent that carries out a prepared memU self-evolve run.
You have no shell. Use these tools instead of `bash`:
  read_file(path)            instead of `cat <path>`
  list_dir(path)             instead of `ls <path>`
  write_file(path, content)  to create or overwrite a file
  append_line(path, line)    instead of `echo "<line>" >> <path>`
  run_command(command)       only for the memU command a job tells you to run
Paths are relative to your working directory; the memU workspace is `{workspace}`."""

TOOLS = [
    {"type": "function", "function": {"name": "read_file", "description": "Read a UTF-8 text file.",
     "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}}},
    {"type": "function", "function": {"name": "list_dir", "description": "List the entries of a directory.",
     "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}}},
    {"type": "function", "function": {"name": "write_file", "description": "Create or overwrite a text file.",
     "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
                    "required": ["path", "content"]}}},
    {"type": "function", "function": {"name": "append_line", "description": "Append one line to a text file.",
     "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "line": {"type": "string"}},
                    "required": ["path", "line"]}}},
    {"type": "function", "function": {"name": "run_command", "description": "Run a memU command named by a job.",
     "parameters": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]}}},
]


def executor_setup() -> dict:
    """What the score is measured WITH: memU plus this executor."""
    return {
        "role": "the external agent memU's memorize hands its job files to (memU itself calls no LLM)",
        "model": LLM_MODEL,
        "endpoint": "Google OpenAI-compatible chat/completions, function calling, default thinking",
        "prompt": "memU's own executor prompt (memu.cli._memorize_executor_prompt) and the job templates "
                  "embedded in this memU build, unchanged; one agent session per prepared run (<=10 sessions)",
        "system_note": SYSTEM.format(workspace=WS_REL.as_posix()),
        "tools_given": ["read_file", "list_dir", "write_file", "append_line",
                        f"run_command (only `{VERIFY_COMMAND}`)"],
        "tools_not_given": ["a shell", "network", "any path outside the workspace"],
        "max_steps_per_run": MAX_STEPS,
    }


def info_dict(memu_version: str | None, top_k: int | None, init_s: float) -> dict:
    """The bridge's self-description: names and models, no absolute path."""
    return {"ok": True, "memu_version": memu_version, "store": "<MEMU_STORE>/memu.sqlite3",
            "workspace": f"<MEMU_STORE>/{WS_REL.as_posix()}",
            "embedding": f"openai-compatible {GOOGLE_OPENAI} {EMBED_MODEL}",
            "executor": f"{LLM_MODEL} via {GOOGLE_OPENAI} chat/completions (function calling)",
            "retrieve_top_k": top_k, "init_s": init_s}


def _rel(p: Path) -> str:
    try:
        return p.resolve().relative_to(STORE).as_posix()
    except ValueError:
        return p.name


def _inside(p: str) -> Path:
    path = Path(os.path.expanduser(str(p).strip().strip('"').strip("'")))
    path = (path if path.is_absolute() else STORE / path).resolve()
    if path != WORKSPACE and WORKSPACE not in path.parents:
        raise PermissionError(f"outside the workspace: {p}")
    return path


def _tool(name: str, args: dict, ws) -> str:
    from memu.hosts.bridging.resources import verify_resource_log
    try:
        if name == "read_file":
            return _inside(args["path"]).read_text(encoding="utf-8")[:60000]
        if name == "list_dir":
            p = _inside(args["path"])
            if not p.exists():
                return "(does not exist)"
            items = sorted(x.name + ("/" if x.is_dir() else "") for x in p.iterdir())
            return "\n".join(items) or "(empty)"
        if name == "write_file":
            p = _inside(args["path"])
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(str(args.get("content", "")), encoding="utf-8")
            return f"wrote {len(str(args.get('content', '')))} characters to {_rel(p)}"
        if name == "append_line":
            p = _inside(args["path"])
            with p.open("a", encoding="utf-8") as fh:
                fh.write(str(args.get("line", "")).rstrip("\n") + "\n")
            return "appended"
        if name == "run_command":
            cmd = " ".join(str(args.get("command", "")).split())
            if cmd == VERIFY_COMMAND:
                kept = verify_resource_log(ws.resource_log, ws.resources)
                return f"kept {kept} resource(s); wrote {_rel(ws.resources)}"
            return f"not available: only `{VERIFY_COMMAND}` can be run"
        return f"unknown tool {name}"
    except Exception as e:  # noqa: BLE001
        return f"error: {type(e).__name__}: {str(e).replace(str(STORE), '<MEMU_STORE>')}"


def _chat(messages: list[dict]):
    delay = 5
    for attempt in range(6):
        try:
            r = llm.chat.completions.create(model=LLM_MODEL, messages=messages, tools=TOOLS)
            USAGE["llm_calls"] += 1
            u = r.usage
            if u is not None:
                USAGE["llm_prompt_tokens"] += u.prompt_tokens or 0
                USAGE["llm_completion_tokens"] += u.completion_tokens or 0
                USAGE["llm_total_tokens"] += u.total_tokens or 0
            return r
        except Exception as e:  # noqa: BLE001
            USAGE["llm_errors"] += 1
            print(f"executor call failed ({attempt + 1}): {type(e).__name__}: {str(e)[:200]}", file=sys.stderr)
            if attempt == 5:
                raise
            time.sleep(delay)
            delay = min(delay * 2, 60)


def _execute(prompt: str, ws) -> dict:
    messages = [{"role": "system", "content": SYSTEM.format(workspace=WS_REL.as_posix())},
                {"role": "user", "content": prompt}]
    tools_used: dict[str, int] = {}
    for step in range(MAX_STEPS):
        r = _chat(messages)
        m = r.choices[0].message
        messages.append(m.model_dump(exclude_none=True))   # keeps Gemini's thought signatures
        if not m.tool_calls:
            return {"steps": step + 1, "final": (m.content or "")[:400], "tools": tools_used}
        for tc in m.tool_calls:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            tools_used[tc.function.name] = tools_used.get(tc.function.name, 0) + 1
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": _tool(tc.function.name, args, ws)})
    raise RuntimeError(f"executor did not finish in {MAX_STEPS} steps")


# ── the store ──────────────────────────────────────────────────────────────

def _count_embeddings(client) -> None:
    inner = client.embed

    async def embed(inputs):
        USAGE["embed_calls"] += (len(inputs) + client.batch_size - 1) // client.batch_size
        USAGE["embed_texts"] += len(inputs)
        USAGE["embed_chars"] += sum(len(t) for t in inputs)
        return await inner(inputs)
    client.embed = embed


def op_init(req: dict) -> dict:
    global svc, llm
    t0 = time.perf_counter()
    if req.get("fresh"):
        for p in (DB, WORKSPACE):
            if p.is_dir():
                shutil.rmtree(p)
            elif p.exists():
                p.unlink()
        _runs.clear()
    import importlib.metadata as md
    from memu.app import MemoryService
    from openai import OpenAI
    svc = MemoryService(
        database_config={"metadata_store": {"provider": "sqlite", "dsn": f"sqlite:///{DB.as_posix()}"}},
        # memU's "openai" provider (the OpenAI SDK client) pointed at Google's
        # OpenAI-compatible endpoint: MEMU_EMBED_PROVIDER=openai + MEMU_BASE_URL
        embedding_profiles={"default": {"provider": "openai", "client_backend": "sdk",
                                        "base_url": GOOGLE_OPENAI, "api_key": _key(),
                                        "embed_model": EMBED_MODEL}},
    )
    _count_embeddings(svc._get_embedding_client("embedding"))
    llm = OpenAI(api_key=_key(), base_url=GOOGLE_OPENAI, max_retries=0, timeout=180)
    WORKSPACE.mkdir(parents=True, exist_ok=True)
    return info_dict(md.version("memu-cli"), svc.progressive_retrieve_config.file.top_k,
                     round(time.perf_counter() - t0, 2))


async def _all_files() -> list[dict]:
    out, cursor = [], None
    while True:
        page = await svc.list_all_recall_files(cursor=cursor)
        out.extend(page["recall_files"])
        cursor = page.get("next_cursor")
        if not cursor:
            return out


def op_health(req: dict) -> dict:
    """The store answers a listing and the embedding provider answers a real
    embedding: both are what a retrieve needs."""
    files = run(_all_files())
    t0 = time.perf_counter()
    vecs, _ = run(svc._get_embedding_client("embedding").embed(["health check"]))
    return {"ok": True, "files": len(files), "embed_dims": len(vecs[0]) if vecs else 0,
            "embed_ms": round((time.perf_counter() - t0) * 1000)}


def op_files(req: dict) -> dict:
    return {"ok": True, "files": run(_all_files())}


def op_segments(req: dict) -> dict:
    db = svc._get_database()
    n = 0
    for f in run(_all_files()):
        n += len(db.recall_file_segment_repo.list_segments_for_file(f["id"]))
    return {"ok": True, "segments": n}


def _hook_shape(result: dict) -> dict:
    """What a host adapter's `memu-<host> retrieve` prints: memU's own
    _shape_for_agent (files lose their content for the path of their mirror,
    written under this process's HOME). The private HOME is written back as
    `~`, which is what the path is for a real user."""
    from memu.hosts.retrieval import _shape_for_agent
    shaped = _shape_for_agent(copy.deepcopy(result))
    for f in shaped.get("files", []):
        if f.get("path"):
            p = Path(f["path"])
            try:
                f["path"] = "~/" + p.relative_to(FAKE_HOME).as_posix()
            except ValueError:
                pass
    return shaped


def op_retrieve(req: dict) -> dict:
    """door 'retrieve': progressive_retrieve as `memu retrieve` prints it;
    door 'hook': the host adapter's shaped form."""
    t0 = time.perf_counter()
    res = run(svc.progressive_retrieve(req["q"]))
    ms = (time.perf_counter() - t0) * 1000
    out = {"ok": True, "result": res, "ms": ms}
    if req.get("door") == "hook":
        out["shaped"] = _hook_shape(res)
    return out


def op_put(req: dict) -> dict:
    """One recall file written straight through commit_results (what `memu
    commit` does): no agent, no LLM. Used for live state."""
    res = run(svc.commit_results(recall_files=[{"name": req["name"], "track": req.get("track", "memory"),
                                                "description": req.get("description", ""),
                                                "content": req.get("content", "")}]))
    return {"ok": True, "files": [f.get("name") for f in res.get("recall_files", [])]}


def _discard(ws) -> None:
    """memU v1 has no abort command: an unfinished or uncommitted run is
    cleared by hand so the next prepare can start."""
    USAGE["discarded_runs"] += 1
    for p in list(ws.jobs.glob("*.txt")) + list(ws.input.glob("*.jsonl")):
        p.unlink(missing_ok=True)
    for p in (ws.resource_log, ws.resources, ws.active_run):
        p.unlink(missing_ok=True)


def op_memorize(req: dict) -> dict:
    """sessions: [[{role, content}, ...], ...] -> memU's memorize, 10 sessions
    per prepared run (memU's limit), each run carried out by the executor and
    committed. Returns one run id per prepared run, for forget."""
    from memu.app.memorize.input import MemorizeInput
    from memu.app.memorize.lifecycle import MemorizeWorkspace, commit_memorize, prepare_memorize
    from memu.cli import _memorize_executor_prompt
    ws = MemorizeWorkspace(WS_REL)
    sessions = req["sessions"]
    out = []
    for i in range(0, len(sessions), 10):
        batch = [MemorizeInput.model_validate({"schema_version": "1.0", "items": [
            {"type": "message", "role": m["role"], "content": m["content"]} for m in s]}) for s in sessions[i:i + 10]]
        before = {(f["track"], f["name"]): f for f in run(_all_files())}
        t0 = time.perf_counter()
        prepared = run(prepare_memorize(batch, ws, svc, verify_command=VERIFY_COMMAND))
        try:
            ex = _execute(_memorize_executor_prompt(prepared), ws)
            res = run(commit_memorize(ws, svc))
        except Exception:
            if ws.active_run.exists():
                _discard(ws)
            raise
        secs = time.perf_counter() - t0
        committed = res.get("recall_files", [])
        rid = f"memorize-{time.time_ns()}"
        _runs[rid] = [{"track": f["track"], "name": f["name"], "before": before.get((f["track"], f["name"])),
                       "after": f.get("content") or ""} for f in committed]
        USAGE["memorize_runs"] += 1
        USAGE["memorize_sessions"] += len(batch)
        USAGE["memorize_s"] += secs
        USAGE["noop_runs"] += not committed
        out.append({"id": rid, "sessions": len(batch), "jobs": len(prepared.jobs), "s": round(secs, 1),
                    "changed": [f"{f['track']}/{f['name']}" for f in committed], "executor": ex})
    return {"ok": True, "runs": out}


def op_forget(req: dict) -> dict:
    """Undo one memorize run: every file it changed goes back to what it held
    before (a file it created is emptied: memU commit cannot delete a file).
    Refused, with nothing written, when any of those files changed after the
    run committed: restoring the old snapshot would also undo the later write."""
    rid = req["id"]
    if rid not in _runs:
        return {"ok": False, "error": f"unknown run {rid}"}
    now = {(f["track"], f["name"]): f for f in run(_all_files())}
    moved = [f"{f['track']}/{f['name']}" for f in _runs[rid]
             if ((now.get((f["track"], f["name"])) or {}).get("content") or "") != f["after"]]
    if moved:
        return {"ok": False, "error": f"changed since run {rid}: {', '.join(moved)}; not reverted"}
    files = [{"name": f["name"], "track": f["track"],
              "description": (f["before"] or {}).get("description") or "",
              "content": (f["before"] or {}).get("content") or ""} for f in _runs[rid]]
    if files:
        run(svc.commit_results(recall_files=files))
    _runs.pop(rid)
    return {"ok": True, "reverted": len(files)}


def op_usage(req: dict) -> dict:
    return {"ok": True, "usage": dict(USAGE, memorize_s=round(USAGE["memorize_s"], 1))}


def op_executor(req: dict) -> dict:
    return {"ok": True, "executor": executor_setup()}


OPS = {"init": op_init, "health": op_health, "files": op_files, "segments": op_segments, "retrieve": op_retrieve,
       "put": op_put, "memorize": op_memorize, "forget": op_forget, "usage": op_usage, "executor": op_executor,
       "ping": lambda r: {"ok": True}}


def main() -> None:
    setup_environment()
    out = sys.stdout
    sys.stdout = sys.stderr   # memU and its libraries log; keep the answer channel clean
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
            op = OPS[req["op"]]
            if svc is None and req["op"] not in ("init", "ping", "executor"):
                ans = {"ok": False, "error": "not initialised"}
            else:
                ans = op(req)
        except Exception as e:  # noqa: BLE001
            traceback.print_exc(file=sys.stderr)
            ans = {"ok": False, "error": f"{type(e).__name__}: {e}"[:500]}
        out.write(json.dumps(ans, default=str) + "\n")
        out.flush()


if __name__ == "__main__":
    main()
