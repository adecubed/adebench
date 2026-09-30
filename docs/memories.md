# Memories measured: notes from each run

What each run on the synthetic set found, memory by memory, with the commands to reproduce
it. The numbers here are the ones of each memory's own run and version of adebench; the
current board is on [adebench.dev](https://adebench.dev) and in the
[README](../README.md#the-leaderboard).

## Second real memory: gbrain

[`adebench/gbrain.py`](../adebench/gbrain.py) is the adapter for
[gbrain](https://github.com/garrytan/gbrain). Everything goes through `gbrain call <tool>
'<json>'`, the local dispatch of its MCP tools, so the adapter sees what an agent sees: no
gbrain code is imported. Two doors: `search` (hybrid retrieval plus the facts `recall`
returns, no cut) and `pack` (`context_pack`, budget-packed). Entity pages are the cards, the
memory verbs `remember` / `recall` / `forget` are the working memory, the chronicle gives the
dated episodes, links and backlinks the graph, and `gbrain --tools-json` the declared bytes.
Corrections, aliases, a live-state key and a repository do not exist there: those cases are
SKIP, and the report says so. gbrain's own match evidence (`evidence`, `create_safety`) is
passed on: when every hit is a weak semantic neighbour, the door delivers two neighbours and
flags the unknown terms, which is what the abstention section looks for.

To run the same golden set on both memories:

```bash
bun install -g github:garrytan/gbrain#latest-stable
gbrain init --pglite --non-interactive --path ~/.gbrain/adebench-synthetic \
    --embedding-model ollama:nomic-embed-text --embedding-dimensions 768
python examples/gbrain_import.py            # the synthetic memory, page by page
ADEBENCH_LIVE_STATE_KEY= python -m adebench --adapter adebench.gbrain:GbrainAdapter \
    --cases sets/quick/cases --history /tmp/gbrain-run --write-back
```

Two reports side by side, scored on the sections both measured:

```bash
python -m adebench.compare history/brain.json /tmp/gbrain-run/gbrain.json brain gbrain
```

On the synthetic golden set gbrain 0.50 scores 75.4 of the 90 points it can be measured on
(`file_search` needs a repository); the report is in
[`examples/gbrain_report/`](../examples/gbrain_report/), run of 28 Sep 2026 with adebench
0.2.15, PGLite, embeddings `ollama:nomic-embed-text`. Any embedding provider gbrain supports
works; keyless mode leaves it with keyword search only. What the run says:

- **door 18.8 / 25.** The two misses are the dataset's deliberate defects, the same two
  every memory fails.
- **updates 3.3 / 10.** A `remember` with a changed value does not retire the earlier one:
  the new value is served after 2.3 s, but the old one stays next to it (10 reads with
  both), and restating the current value leaves two copies. The run of 13 Sep (73.8 / 80)
  predates this probe.
- **abstention 8.3 / 10.** "What does the calendar plugin Girandola do?" gets the calendar
  page and eight keyword facts.
- **write-back 2 of 2 poisoned.** A degraded exchange written back through `remember`
  comes straight back through the door, once ahead of the real answer.

## Third real memory: Dakera

[`adebench/dakera.py`](../adebench/dakera.py) is the adapter for [Dakera](https://dakera.ai), a self-hosted vector memory server for AI agents. It talks to Dakera's REST API only (no engine code imported), scoped to a single `agent_id` namespace so a run never touches other data. Dakera is a retrieval + memory engine rather than a full personal brain, so the adapter supplies the thin reference reader `door_text` needs: cards first, then dated semantic facts, then episodic, then working, with an unknown-terms path so an invented subject abstains. [`examples/dakera_import.py`](../examples/dakera_import.py) loads the synthetic set the way `gbrain_import.py` does — everything **stored as written**, no step edits the golden data.

What maps and what does not:

- **cards** stored verbatim; owner corrections / a distiller: none, so the correction cases SKIP
- **fact updates** — with adebench 0.2.12's optional `write_fact`, the `updates` section runs the **harness's own id-less update probe** (the same for every memory), and Dakera **passes it 3/3**. `write_fact` is a plain store with no id of what it replaces; Dakera's engine then forms a `Supersedes` edge to the near-identical earlier fact (shared entity, ≥0.92 cosine, strictly later), and a session-scoped recall **demotes the retired value**, so the door serves the new value and never the old, an unrelated fact about the same entity survives, and restating the value adds no copy. The adapter never says which fact is superseded — Dakera does. The adapter's own `--sandbox-test` ([`examples/dakera_sandbox_test.py`](../examples/dakera_sandbox_test.py), 3 checks on a throwaway namespace) still runs and is **reported as evidence, no longer scored**, now that the harness probe measures the section
- **time** facts carry Dakera's stored timestamp as their age; episodes are dated
- **live state** store / recall / forget over a working-memory tag with a TTL; no scheduled live-state key, so that case is SKIP
- **files** the repo files are stored and matched through Dakera's full-text search
- **graph** entity edges and orphans read from Dakera's own knowledge graph (`GET /v1/knowledge/export`)

Run it against a **fresh, isolated Dakera instance** — a benchmark should not share a live index. This adapter changes nothing in adebench's harness; the only knobs are Dakera-server env on your side:

```bash
# fresh, isolated Dakera for the benchmark (in-memory, no persistence, no shared index).
# The CE31 / DECOMP knobs pin Dakera's recall-time sentence-decomposition so a small golden
# set isn't crowded by auto-generated sub-memories — this makes recall deterministic.
docker run -d --name dakera-eval -p 127.0.0.1:3001:3001 \
  -e DAKERA_PORT=3001 -e DAKERA_TIERED=1 -e DAKERA_STORAGE=memory -e DAKERA_AUTH_ENABLED=false \
  -e DAKERA_CE31_MAX_SENTENCES=0 -e DAKERA_BATCH_SENTENCE_DECOMP=0 \
  -v <dakera-models>:/app/models:ro  ghcr.io/dakera-ai/dakera:<version>

export DAKERA_URL=http://localhost:3001 DAKERA_API_KEY=          # auth disabled above
python examples/dakera_import.py                                # load the synthetic set
ADEBENCH_LIVE_STATE_KEY= python -m adebench --adapter adebench.dakera:DakeraAdapter \
    --cases sets/quick/cases --repo sets/quick/repo \
    --sandbox-test examples/dakera_sandbox_test.py \
    --door chat --history /tmp/dakera-run
```

On the synthetic golden set Dakera scores **96.9 / 100** on this configuration, stable across repeated runs (report in [`examples/dakera_report/`](../examples/dakera_report/)); on the 90 points gbrain is also measured on it is **86.9 vs gbrain's 75.4** (gbrain run of 28 Sep). The one door miss is a golden question whose fact (the owner's phone number) isn't in the set. Genuine supersession *is* exercised — and passes — in the `updates` section through `write_fact` (above), where Dakera's engine retires the old value. The door's stale question (`mailbox_version`) is a **different, softer case**: its pass is a **door result, not supersession** — the retired value (`1.3.0`) is stored verbatim and simply wasn't returned within `top_k=8` for that question, and the entity card (which carries only `1.4.2`) is what the door delivers; a query that ranked the historical line higher would serve it next to `1.4.2`. adebench scores what the door delivers, and here it did not deliver the stale line. Note: on a *default* Dakera instance, recall-time sentence-decomposition is on, which on a fresh tiny namespace crowds recall and makes the score non-deterministic run-to-run until it settles — hence the pinned config above.

## Fourth real memory: Memoose

[`adebench/memoose.py`](../adebench/memoose.py) is the adapter for
[Memoose](https://github.com/AndrewNgo-ini/memoose), a local knowledge graph in SQLite.
Everything goes through its own CLI, `memoose --json ...`, the same surface its 26 MCP tools
expose; the report-only measures read the dataset read-only. Two doors: `recall` (entities,
facts as triples, and the lexical chunks, in the mode Memoose routes the query to) and
`facts` (the graph alone). Entity descriptions are the cards, a session's standing context
is the live state, session turns are the episodes, and the graph section measures what
Memoose is built around. Corrections, aliases and a repository do not exist there: SKIP.

Memoose is two halves, and only one of them is measured here: a deterministic engine, and a
harness of skills that a model runs on top of it. It is the model that reads a sentence,
decides it means `zetaprobe --listens_on--> port_9000`, and calls supersede. No model runs
inside adebench, so what is scored is the engine on its own, and the skills' judgment is out
of the picture. For the same reason there is no `write_fact`: the harness's update probe
hands a memory a plain sentence, and the engine alone has nothing to do with one.
[`examples/memoose_sandbox_test.py`](../examples/memoose_sandbox_test.py) asks the same
question through Memoose's own API instead.

```bash
pip install memoose fastembed        # fastembed: without it the vectors fall back to a hash
python examples/memoose_import.py    # the synthetic memory, into dataset 'adebench'
python -m adebench --adapter adebench.memoose:MemooseAdapter     --cases sets/quick/cases --sandbox-test examples/memoose_sandbox_test.py     --history /tmp/memoose-run
memoose -d adebench forget --all     # the dataset was a scratch one
```

On the synthetic golden set Memoose scores 68.3 of the 90 points it can be measured on
(report in [`examples/memoose_report/`](../examples/memoose_report/)). What the run says, and
it is about the engine, not about the project:

- **updates 2 of 4 in the sandbox test.** A second value for a relation does not retire the
  first: Memoose keeps both and flags the subject as a hotspot for a model to judge. Declare
  the relation functional (`declare_functional_relations`) and the newest assertion retires
  the older ones by itself, with nobody saying which. But the retired sentence stays in the
  lexical chunks, and `recall` keeps serving it: after 8000 was retired by 9000 the door
  still carried both.
- **door 18.8 / 25.** The same stale value reaches the door next to the current one, the
  golden set's deliberate defect.
- **abstention 5.8 / 10.** `recall` returns its nearest neighbours whatever is asked, with no
  threshold, so an invented entity comes back with a full page of real facts. The memory
  never says it does not know.
- **time 5 / 10.** Facts carry `valid_from`, chunks carry no date at all, and a session turn
  is stamped with the moment it is written: an episode cannot be given the day it happened.
- **live_state 8.8 / 10**, **cards 15 / 15**, **graph 10 / 10**.

Cleanup is partial by design: Memoose deletes entities, relations and sessions, but not a
stored chunk. Run it against a dataset of its own, as above, and drop the dataset at the end.

## Fifth real memory: Aionforge Memory

[`adebench/aionforge.py`](../adebench/aionforge.py) is the adapter for
[Aionforge Memory](https://github.com/jscott3201/aionforge-memory), a bi-temporal graph
memory in Rust with an MCP server, 0.4.0. Everything goes through that MCP surface over
Streamable HTTP, the door an agent has: `capture` writes an event with its own time,
`search` returns a bounded bundle of snippets fused from lexical, vector, graph, recency
and trust signals, `forget` and `unforget` are explicit, `consolidate` derives facts and
entities from the episodes without a model, and `session_manifest` lists a session's
captures. Cards, files and graph edges are not exposed as such: those sections are SKIP.
Embeddings were Google's `gemini-embedding-001` (3,072 dimensions) through the
OpenAI-compatible endpoint, behind a loopback shim that adds the `index` field Aionforge's
decoder requires and Google omits; the maintainer's daily configuration is
`gemini-embedding-2` on OpenRouter, the same family. Forgetting is off by default and was
enabled with the floors lowered, so the benchmark can remove what it writes.

```bash
docker run -d --network host -v aionforge:/data -v ./config.toml:/config.toml:ro     -e AIONFORGE_EMBEDDER_API_KEY=... ghcr.io/jscott3201/aionforge-memory:0.4.0     --config /config.toml serve http --listen 127.0.0.1:3918
python examples/aionforge_import.py            # the synthetic memory, capture by capture
ADEBENCH_LIVE_STATE_KEY= python -m adebench --adapter adebench.aionforge:AionforgeAdapter     --cases sets/quick/cases --history /tmp/aionforge-run --write-back
```

On the synthetic golden set Aionforge scores 51.8 of the 65 points it can be measured on
(report in [`examples/aionforge_report/`](../examples/aionforge_report/)); on the 65 points
gbrain is also measured on, 51.8 vs gbrain's 50.4 (gbrain run of 28 Sep). What the run says:

- **door 18.8 / 25.** Six of eight; the two misses are the golden set's deliberate defects,
  and one of them is the STALE case: `MailBridge 1.4.2 replaced 1.3.0` and the older
  capture are both served, the model has to guess.
- **updates 6.7 / 10.** A new capture with 9000 does not retire the one with 8000 on its
  own: `capture` takes a `supersedes` id, the client naming what it replaces; without it
  both stay live and the door serves both (23 reads with both values).
- **live_state 10 / 10.** A capture is served by the next search: write-to-serve 452 ms
  p50, 483 ms p95, an overwrite visible in 455 ms, no out-of-order reads.
- **abstention 8.3 / 10.** `search` returns nothing for a query with no match ("hits: 0 of
  35 considered"), which the adapter passes on as unknown terms; two invented entities
  still pull one to four neighbouring facts. The deployment default has no relevance floor
  (`min_relevance` 0); the adapter runs the default.
- **time 8 / 10.** Captures carry `captured_at`, and an imported memory reaches the door
  with its original date; the aliases were captured without a date, hence 89% of memories
  with an age.
- **write-back 2 of 2 poisoned.** A degraded answer written through `capture` reaches the
  door in 448 ms and ranks above the real fact: recency is a signal, and the store has no
  rule against storing an absence of information.

One harness change came with this run (0.2.14): when a memory has no entity cards at all,
the door no longer fails a question for the missing card of the entity it names; it is
judged on the text it delivers. Memories with cards are unchanged.

## Sixth real memory: Hindsight

[`adebench/hindsight.py`](../adebench/hindsight.py) is the adapter for
[Hindsight](https://github.com/vectorize-io/hindsight) (Vectorize), agent memory with world
facts, experiences and observations, MCP server 0.10.1. Everything goes through the MCP
tools of one bank: `sync_retain` writes (an LLM extracts facts, entities and relations,
with the event's own time), `recall` is the door (the fused, reranked results, in its
order), `delete_document` removes what a write produced, `list_memories` feeds the report.
`reflect` is left out: it answers, and the benchmark measures what reaches the model.
Cards, files and graph edges are not exposed as such: SKIP. The live-state section is not
run: `retain` runs an extractor, and an arbitrary string is not a fact it keeps.

The extraction model is part of the configuration and the report says which one ran:
`gemini-3.5-flash-lite`, prompt caching off. `gemini-3.5-flash`, the model the docs name,
answered 503 for the whole day of the run; a question to the maintainers on the
representative configuration ([discussion #4840](https://github.com/vectorize-io/hindsight/discussions/4840))
was still unanswered. Recall ran with the deployment defaults (`budget` mid, no
`min_scores`).

```bash
docker run -d -p 127.0.0.1:8888:8888 -e HINDSIGHT_API_LLM_PROVIDER=gemini     -e HINDSIGHT_API_LLM_API_KEY=... -e HINDSIGHT_API_LLM_MODEL=gemini-3.5-flash-lite     -e HINDSIGHT_API_LLM_PROMPT_CACHE_ENABLED=false     -v hindsight-data:/home/hindsight/.pg0 ghcr.io/vectorize-io/hindsight:latest
python examples/hindsight_import.py           # the synthetic memory, retain by retain
python -m adebench --adapter adebench.hindsight:HindsightAdapter --cases sets/quick/cases     --history /tmp/hindsight-run --write-back --sections door cards updates time abstention file_search graph
```

On the synthetic golden set Hindsight scores 36.2 of the 55 points it can be measured on
(report in [`examples/hindsight_report/`](../examples/hindsight_report/)); on the 55 points
gbrain is also measured on, 36.3 vs gbrain's 40.4 (gbrain run of 28 Sep). What the run says:

- **door 18.8 / 25.** Six of eight; the two misses are the golden set's deliberate defects,
  and one of them is the STALE case: `MailBridge 1.4.2 replaced 1.3.0` and the older
  memory are both served.
- **abstention 6.7 / 10, and a knob.** `recall` scores every result: 1.0 and more when the
  reranker agrees, 1e-5 to 1e-2 when it does not, and on a question with no match it
  returns the whole bank at 1e-5, 28 memories for "the Zarpetta module". Delivered as the
  deployment does, that is 0 of 4 abstentions. With `ADEBENCH_HINDSIGHT_MIN_SCORE=0.1`
  the adapter drops what the reranker rejected: abstention 4 of 4, but the door loses
  "Where does the owner live?", whose facts say Alex and scored 0.006
  ([report](../examples/hindsight_report/reference_floor_0.1.md): 36.5 / 55). Hindsight's own
  `min_scores` is the server-side version of the same floor; the headline number is the
  default.
- **updates 3.3 / 10.** A new retain with 9000 does not retire the one with 8000 (both
  served, 20 reads with both), and restating a value leaves three copies. Replacement
  arrives in 561 ms.
- **time 7.5 / 10.** Memories carry `mentioned_at`; the imported canary dated 2021-03-14
  did not reach the door as stored: the extractor rewrites what it keeps.
- **write-back 0 of 2 poisoned.** The degraded exchange ("I have no record of that") is
  kept as nothing: the extractor found no fact in it. The best result of the six memories
  on this probe, for the opposite reason of the Brain's rule.

## Seventh real memory: Jev-Mem

[`adebench/jevmem.py`](../adebench/jevmem.py) is the adapter for
[Jev-Mem](https://github.com/libingzheren/Jev-Mem) (paper:
[arXiv 2609.23986](https://arxiv.org/abs/2609.23986)), agentic memory whose memory
decisions (typing, relations, routing, stopping) are taken by a small System-One model
instead of an LLM, over a graph with semantic, temporal, causal and entity links.
Jev-Mem is a Python library with heavy dependencies, so adebench does not import it:
the adapter starts [`adebench/jevmem_bridge.py`](../adebench/jevmem_bridge.py) with
Jev-Mem's own Python and talks to it in JSON lines. Writes go through the explicit
write path (`MemoryBuilder.build`), the door is what `QueryEngine.query` returns: the
ranked evidence block the answer model would read, each item with its date. No answer
model runs. Jev-Mem has no forget: the adapter removes the node, its links, its vector
and its keyword-index entries. No entity cards and no files: those sections are SKIP.

The configuration is the local one, with no API key: decisions by
[Laya](https://huggingface.co/convaiinnovations/laya) (`config/laya_mem.json`, on an
RTX 4050), embeddings `all-MiniLM-L6-v2`. The default profile calls TypeSafe's Jev API
instead.

```bash
git clone https://github.com/libingzheren/Jev-Mem && cd Jev-Mem
python3.11 -m venv .venv && .venv/bin/pip install -e '.[laya]'
export JEVMEM_HOME=$PWD JEVMEM_PYTHON=$PWD/.venv/bin/python
python examples/jevmem_import.py      # from the adebench checkout: a fresh store
ADEBENCH_LIVE_STATE_KEY= python -m adebench --adapter adebench.jevmem:JevMemAdapter \
    --cases sets/quick/cases --history /tmp/jevmem-run --no-sandbox-test --write-back
```

**The build is not deterministic.** The same 21 observations, loaded twice, give
different link sets (on CPU as on GPU: 95 causal links in one build, 116 in the next),
and retrieval follows the links. So the number is the mean of six runs, each on a fresh
build: **41.9 of 65**, from 39.0 to 42.9
([`examples/jevmem_report/repeats.json`](../examples/jevmem_report/repeats.json); the
reference report is a median run, 42.1). Door, updates, time and live state were the
same in five builds of six; abstention moves by 0.8, and one build lost the "Nova"
fact at the door. What the runs say:

- **door 18.8 / 25.** The two misses are the dataset's deliberate defects.
- **updates 3.3 / 10.** "Port 9000" after "port 8000" does not retire 8000: both are
  served (28 reads with both), and restating the value leaves six copies. The write
  path judges contradiction and obsolescence, but no such link was made on this set.
- **time 6.7 / 10.** Every dated item reaches the door with its date, and the imported
  canary keeps 2021-03-14. Items written without a date stay undated (14 of 35 served
  items carried one), and "what did pc2 do?" does not find the episodes signed [pc2].
- **live state 10 / 10.** A write is served in 3.4 s, an overwrite in 4.3 s.
- **abstention 3.3 / 10.** The query engine always returns its top items: for "the
  Zarpetta module" three to four facts and the latest episodes, ranked as matches.
- **write-back 2 of 2 poisoned.** A degraded exchange written back comes through the
  door ahead of the real answer.

adebench 0.2.16 came out of this run: Jev-Mem writes dates out ("[10 May 2026]"), and
the time checks recognised only ISO dates. A date written out now counts as a date.

## Eighth real memory: Nemp, measured inside Claude Code

[`adebench/nemp.py`](../adebench/nemp.py) is the adapter for
[Nemp](https://github.com/SukinShetty/Nemp-memory), a Claude Code plugin. Nemp has no
code: its memory is a JSON file in the project (`.nemp/memories.json`) and every command
is a markdown file of instructions the model follows with its own tools. So the only
honest door is the harness itself. Every operation is one `claude -p "/nemp:<command> ..."`
in a scratch git project, with Nemp loaded for that call only (`--plugin-dir`), no user
settings, no MCP servers, model `sonnet`. The adapter reads the stream-json transcript:
the **context** door is everything the model received from its tools while running
`/nemp:context <question>`, the **shown** door is what the command printed. The store is
read directly only for report measures. It is the first memory measured inside an agent
harness rather than through an API.

```bash
git clone https://github.com/SukinShetty/Nemp-memory
export NEMP_PLUGIN=$PWD/Nemp-memory NEMP_PROJECT=/tmp/nemp-project
python examples/nemp_import.py        # 21 /nemp:save, one model turn each
ADEBENCH_LIVE_STATE_KEY= python -m adebench --adapter adebench.nemp:NempAdapter \
    --cases sets/quick/cases --history /tmp/nemp-run --no-sandbox-test --write-back
```

On the synthetic golden set Nemp scores **36.4 of the 65 points** it can be measured on
(report in [`examples/nemp_report/`](../examples/nemp_report/); 45 model turns, $6.93 at API
prices, about 50 minutes). Two runs gave the same door, updates, time and abstention.
What the run says:

- **door 18.8 / 25.** The two misses are the dataset's deliberate defects. But
  `/nemp:context` has the model `cat` and `Read` the whole `memories.json` before
  matching: the model receives the entire store on every lookup, 20,000 to 30,000
  characters with 21 memories, growing with the store. The matching happens in the
  model's head.
- **updates 3.3 / 10.** A key is the only id: a new value under a new key does not
  retire the old one (8000 and 9000 both served), and the contradiction check only
  warns, within a key family.
- **time 2.5 / 10.** A memory carries its write time, not the time of the fact; the
  imported canary dated 2021-03-14 reaches the door with no date.
- **live state 4.3 / 10.** Every read and every write is a model turn of 25 to 50 s, so
  a value just written reaches the door after 65 to 106 s, against a budget of 30.
- **abstention 7.5 / 10.** For three of four invented entities the command shows one to four nearby
  memories, and the whole store is in context anyway.
- **write-back: it depends on the turn.** `/nemp:save` compresses the value. In one run
  the degraded exchange was saved as "assistant answered no record on file" and then
  served with the rest of the store; in the reference run the model declined to save it.

adebench 0.2.16 also came out of this run. A value found by a read that started before
the live-state budget and ended after it counted as in budget: with reads of a few ms
nobody noticed, with 25-second reads 44 s passed as "within 30". And the write-back probe
now recognises the degraded answer by its core, "no record" (`ADEBENCH_DEGRADED_MARKER`),
because a memory that rewrites what it stores keeps the meaning and loses the sentence.

## Six more, found by the scout

[`adebench/scout.py`](../adebench/scout.py) lists AI memory repositories on GitHub that
adebench has not measured yet (`python -m adebench.scout`: topic and keyword searches,
minus forks, archived, stale and curated lists; the state is kept across runs, so each run
shows only what is new). Six of the largest were measured on 29-30 Sep 2026, each with its
own adapter, import script and offline tests, and each adapter reviewed before publishing.
A memory that needs a model to write ran with Gemini, the way its users run it, never with
a smaller local model; where extraction is a model call the reference is the median of
three fresh builds, and the spread is in the report folder (`repeats.json`).

| Memory | Core · 55 (mean) | Full (mean) | Model | Report |
|---|---|---|---|---|
| [supermemory](https://github.com/supermemoryai/supermemory) | 40.5 (38.1–43.0, 5 runs) | 50.5 / 65 | gemini-3.1-flash-lite-preview (fixed by its binary) | [`supermemory_report/`](../examples/supermemory_report/) |
| [agentmemory](https://github.com/rohitg00/agentmemory), keyless and with Gemini | 35.5 (same in 3 runs) | 42.6 / 65 | none / gemini-3-flash | [`agentmemory_report/`](../examples/agentmemory_report/) |
| [engram](https://github.com/Gentleman-Programming/engram) | 35.2 (same in 3 runs) | 45.2 / 65 | none | [`engram_report/`](../examples/engram_report/) |
| [mem0](https://github.com/mem0ai/mem0) (open-source library) | 34.2 (30.4–35.5, 5 runs) | 44.2 / 65 | gemini-3-flash | [`mem0_report/`](../examples/mem0_report/) |
| [cognee](https://github.com/topoteretes/cognee) | 34.4 (33.7–35.4, 5 runs) | 44.4 / 65 | gemini-3-flash | [`cognee_report/`](../examples/cognee_report/) |
| [memU](https://github.com/NevaMind-AI/memU) | 32.2 (same in 5 runs) | 42.1 / 65 | gemini-3-flash as its executor agent | [`memu_report/`](../examples/memu_report/) |

What they have in common: none abstains (supermemory, with a relevance threshold, comes
closest at 7.5 / 10), and only agentmemory and supermemory retire an old value on their
own. Each adapter's docstring says what maps, what is SKIP and every choice that is not the
memory's default.

The review of these six set four rules for every adapter from 0.2.17 on: the door is the
text the client literally receives from the tool, not a re-rendering; a write or storage
time never counts as a memory's age; no local paths in a published report; and the graph
section is not scored on the orphan count alone when the memory has no entity cards (one
structural count does not measure a graph). The harness also forgets write-back probes
newest first and does not stop at the first failure. Adapters measured before 0.2.17
(Aionforge re-renders its door and dates by capture time) will be brought to the same rules
and re-run.

## The ADE Brain on the same set

The Brain is the memory adebench was written against, and its numbers in this README are
on its owner's real memory. For the leaderboard it runs on the synthetic set like everyone
else: [`examples/ade_import.py`](../examples/ade_import.py) loads the set into an EMPTY Brain
through its own paths (facts and card texts via `POST /memory/semantic/learn`, with the
event date and the entity each fact is about; aliases; episodes at their own time), then
asks the Brain to write each entity's card from what it holds, with its model. Nothing is
stored as given. The instance is the evaluation one (Ubuntu, `BRAIN_LANG=en`, cards and
distillation with `gemini-3-flash-preview`, decay off). The set's example repository is
indexed by the Brain's own indexer, full-text stage only (no folder summaries: those need
the model and are not part of the set). There is no mailbox on the instance, so the
mailbox live-state key is not measured (one SKIP inside live state).

```bash
BRAIN_URL=http://127.0.0.1:8766 python examples/ade_import.py
python -c "import asyncio; from brain.memory.indexer import index_project;     asyncio.run(index_project('sets/quick/repo', force=True))"   # GOOGLE_API_KEY unset
ADEBENCH_LIVE_STATE_KEY= python -m adebench --brain http://127.0.0.1:8766     --cases sets/quick/cases --repo sets/quick/repo     --history /tmp/brain-synthetic-run --no-sandbox-test --write-back
```

On the synthetic golden set the Brain scores 93.8 / 100 (report in
[`examples/ade_synthetic_report/`](../examples/ade_synthetic_report/)). What the run says:

- **door 18.8 / 25.** Six of eight, the same two misses as every other memory: the golden
  set's STALE fact and the phone number nobody stored.
- **cards 15 / 15, graph 10 / 10, updates 10 / 10, time 10 / 10, live state 10 / 10,
  file search 10 / 10.** Replacement visible in 93 ms, write to serve 106 ms. The graph
  needed a change: a fact
  loaded as text carried no entities, so the graph stayed empty (0 / 10 on the first run);
  `learn` now takes the fact's entities, as the distiller extracts them from an episode.
- **abstention 10 / 10, after a change.** "What does the calendar plugin Girandola do?"
  got the calendar card next to the unknown-terms line (9.2 / 10): the card is the nearest
  thing, not an answer. With an unknown proper noun in the question the door now keeps
  the card back; the facts by meaning and the unknown-terms line stay.
- **write-back 0 of 2 poisoned.** The degraded exchange stays in the chat log and does not
  come back through the door.
- Three things the run found in the Brain itself and that are fixed: the card above, a
  memory that had never pruned could not forget (`no such table: semantic_archive` on the
  first delete), and the card model was fixed in the source instead of the environment.
  Each change was re-measured on the owner's own set too, the way the bench is meant to
  be used.

