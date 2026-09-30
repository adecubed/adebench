# adebench — a benchmark for personal AI memory, on its own terms

**English** · [Italiano](#lang-it) · **Leaderboard: [adebench.dev](https://adebench.dev)**

`adebench` measures the memory of a personal AI assistant the way that memory is actually
used, not the way generic memory benchmarks are built. It was born for an
[ADE](https://nerine.io) Brain — the Python service that keeps the long-term memory of the
Sofia voice assistant — and talks to any other memory system through an adapter.

Public benchmarks such as LoCoMo, LongMemEval or BEAM tell you how a memory architecture
performs on *somebody else's conversations*. They are the right tool to compare
architectures. They say nothing about whether *your* assistant will get the port number
right tomorrow, whether the entity card it reads aloud still honours the corrections you
gave it last week, or whether it will admit it has never heard of something.

adebench asks exactly those questions, against the live service, in about three minutes.

## What it measures

Two words come up everywhere below. A **door** is the path a memory is reached through and
the text that comes out of it: a voice assistant's `/ask` with its sources, its "latest
events" block and its 2,400-character cut; an MCP tool call; a raw search. The same question
through two doors gives two different texts, and adebench scores the text, not the retrieval
behind it: a fact that retrieval found but the cut removed does not help the model. A
**card** is the composed summary a memory keeps about one entity (a person, a project, a
service), the thing to deliver first when the question names it; in gbrain they are entity
pages, in the ADE Brain they are built by a distiller and honour the owner's corrections.

The score is 0–100, weighted over eight sections. Each section is a list of cases derived
either from a small golden set you own or, for most sections, **from the memory's own
data** — so the benchmark grows with the memory and cannot be gamed by editing questions.

| Section | Weight | What passes |
|---|---|---|
| `door` | 25 | The expected words are inside the text **the client actually receives** through the chosen door (see *Doors*). Not the raw hits: the text. |
| `cards` | 15 | Every entity card exists, is dated, fits the limit, contains each mandatory item of the owner's corrections; every alias leads to the canonical card. Fully derived from the data. |
| `updates` | 10 | Facts get **updated**, not accumulated. With the optional `write_fact`, the harness runs the same probe on every memory: "listens on port 8000", then a new write with 9000 and no id of what it replaces, and the door must serve 9000 and never 8000 again; an unrelated fact about the same entity must survive, and restating the value must not pile up a copy. Without `write_fact`, the adapter's own sandbox test (`--sandbox-test`) scores, and the report says so. The historical trace is reported, never scored. |
| `time` | 10 | Every memory reaches the model with its age (a leading bracketed date in any language: `[since 2026-05-10]`, `[dal 2026-05-10]`), the episodic day filter returns only that day, machine-signed episodes are found by a question in the owner's language, and a memory imported with an old original date reaches the door with **that** date, not the import date (optional `import_memory`, SKIP without it). |
| `live_state` | 10 | A canary written to working memory is served through the door (polled until it appears: the **write-to-serve latency** is reported in ms, with a p50/p95 over a few canaries, and a memory that never serves one within the budget fails); the same key **overwritten** is served with the new value and never the old one (a stale read right after a write, or both values together, is a fail); **two writes in quick succession** settle on the second and never go back to the first (out-of-order visibility is a fail); the live state key is fresher than N minutes. |
| `abstention` | 10 | On invented entities: no card, episodes marked as *no direct match*, no keyword hits — the memory says it does not know. |
| `file_search` | 10 | Real function names sampled from a repository: the grep-replacement search puts the right file in the top 5. |
| `graph` | 10 | Every entity with a card has edges in the knowledge graph; no orphan fact nodes. |

Two more sections are **report-only** and never move the score: `health` (memory lifecycle:
live vs archived facts, share written through the v2 pipeline, facts at the confidence
floor, corrupted text, pending distillation, unacknowledged anomalies, and **index
coverage**: rows in each full-text index against rows in the table it is built from — the
reference Brain ran four days with 15 episodes indexed out of 2,689 while the score stayed
at 95, because the benchmark only looked at what came out of the door) and `doors` (latency
p50/p95 and characters produced per door). The third axis — how much text the memory
injects — is measured on every run, because 90 % accuracy at 500 characters and 90 % at
5,000 are not the same thing.

Every run writes a JSON and a Markdown report to the history folder, with the delta against
the previous **comparable** run, so the question becomes: *does the memory remember better
than yesterday?*

### How a point is earned

Every check ends in one of four states, and the report counts them:

| State | Meaning | Effect on the score |
|---|---|---|
| `PASS` | the check ran, had evidence, and the memory did the right thing | earns |
| `FAIL` | the check ran, had evidence, and the memory did not | does not earn |
| `ERROR` | the memory did not answer (HTTP error, exception, empty response, failed read) | does not earn — a broken service never looks like a good one |
| `SKIP` | this memory has no such feature, or there is no data to check against | leaves the score entirely |

A section with no `PASS`/`FAIL`/`ERROR` case is *not measured*: its weight leaves the
denominator, and the report says `score / measured weight` with the coverage next to it.
The reference denominator is always the full suite: running only `door` reports
`25 / 25 — coverage 25/100: 75 not run`, never a full score. A read from the memory that
blows up is an `ERROR` case, never an empty value that would turn into a `SKIP`. Absence of
evidence is never a point. Expected words match whole tokens: `8766` does not match
`18766`, `0.2.4` does not match `10.2.4`.

A delta is computed only against a run with the same setup fingerprint: adapter, door,
golden set, sections run, cut and sources of the voice door, sandbox test, repo, weights.
Anything else is another measurement, not a regression.

Two limits, stated plainly. The abstention section checks what retrieval hands to the
model on invented entities, not the sentence the assistant finally says: that would need an
LLM judge and would stop being deterministic. And the updates section scores only the
sandbox test of the mechanism; the historical trace of past updates is reported, never
scored, because an update that happened once does not prove the mechanism works today.

## Doors

A memory is reached through more than one door, and each delivers a different text for the
same question. `--door` picks the one the `door` section measures; the other seven sections
are door-independent. The ADE adapter exposes three:

| Door | Who uses it | What is measured |
|---|---|---|
| `voice` (default) | the voice assistant | `/sofia/ask` with the voice client's sources, its "latest events" block, card first, cut at 2,400 characters — what the voice model literally hears |
| `agent` | Claude, Codex, any MCP agent | the orchestrator context (`brain_get_context`) plus the top semantic hits (`brain_semantic_search`), no cut — what an agent literally gets at task start |
| `raw` | your own client | `/sofia/ask` with the memory's default sources and no cut — the upper bound of what retrieval can deliver |

No voice assistant? Run with `--door agent`.

Some memories do not answer in one call: they return a **brief** (one line per hit, an
identifier each) and let the agent fetch the detail it wants. adebench measures that as a
door of its own, `two-step`, with a fixed and declared rule (`adebench/twostep.py`): the
brief is delivered first, then the details in the order the brief lists them, each in full,
until the next one would not fit the same budget a one-call door gets; every call's latency
is summed. The gbrain adapter, the ADE adapter (the Brain's `brief` mode plus
`GET /sofia/item`) and the synthetic memory expose it; `ADEBENCH_TWO_STEP_DETAIL_CHARS` caps
each fetched detail, the policy "read the head of many items". What an agent could choose
better with judgement is exactly what this door does not measure.

On the reference memory, budget 2,400: the one-call composed door 23/25, the two-step door
17/25 with whole details and 18/25 with details capped at 300; under the census p95, 19/25
against 8/25. On gbrain the opposite, 18/25 to 20/25. The brief costs about 1,400 characters
of previews, which the one-call door spends on the entity card whole plus facts cut at 220:
under a tight budget the winner is the door that spends it on content, not the number of calls.

### Margin and pressure

The cut is fixed; what competes for the space before it is not. A tool response can be 264
bytes at the median and 700 KB on a bad day, decided by an argument the model picks at
runtime (measured by [callwitness](https://github.com/AditiChaudharyy14/callwitness) across
29 MCP servers). So a door test on a normal payload and a door test on a bad day are two
different tests, and adebench runs both:

- every passing question reports its **margin**: how many characters separate the last
  expected word from the **door's budget** (the cut the adapter declares with `door_cut`),
  not from the end of the text that happened to come back — a 10-character answer under a
  2,400 cut has 2,390 characters of room, not zero. Doors without a cut have no margin. The
  report warns when a pass has less than 300 characters of margin — one bad day away from a
  fail;
- `--pressure N` (or `ADEBENCH_PRESSURE`) places N characters of simulated competing payload
  where the client puts its own variable-size blocks, before the cut. It is part of the
  setup fingerprint, so a run under pressure is never compared with a run without;
- the door section also reports **budget spent on nothing**: the characters delivered
  before the answer, and the **repeated chunks** in the delivered text (the same line served
  twice, e.g. once by an events block and once by the episodic section). No relevance
  labels are used, so there is no "precision" score: that would be a judgement, not a
  measurement.

### Pressure levels from a callwitness census

`N` does not have to be a number you pick. `--census` reads a callwitness baseline
(schema `callwitness.baseline.v1`): either the published census,
`https://callwitness.tech/baseline/v1.json`, or a file you generated against your own
servers with `pip install -U callwitness` and `callwitness baseline --out mine.json`. Then:

- `--pressure median`, `--pressure p95` or `--pressure max` resolve to the census
  percentiles of a single tool response (bytes, taken as characters). The resolved number
  is what enters the setup fingerprint;
- `--pressure-profile` runs the door at all three levels too and reports the passes at
  each, report-only: "median day", "p95 day", "worst observed". Median and p95 are the
  stable levels; the worst observed is the worst *argument* anybody happened to pick so
  far (the same server returned 906x and 81x its declared size in two census runs), so
  the report labels it a lower bound of a bad day, never the floor of the score;
- a report-only `census` section says where this door sits in the distribution (its mean
  delivered text against the census calls) and, when the adapter implements the optional
  `declared_bytes()` (the size of its MCP `tools/list`), the **declared-vs-returned**
  ratio — the measure that reorders servers in the census.

The two origins are never treated as one: `origin: "census"` is the published document,
`origin: "local"` is your own traffic, and a document with no origin field is `census` only
when it comes from the published URL — otherwise the report labels it unknown. Locally
generated documents currently report `declared_bytes = 0` (the recorder does not keep
`tools/list` yet), so declared-vs-returned has a reference against the published census only.

### Write-back: a memory learning from its own bad answers

A failure no read-side section catches (reported by VodouAI on r/AIMemory): retrieval is
degraded, the assistant answers "no record of that", the normal write path saves the
exchange, and the next day that entry outranks the real fact, because it is newer and
matches the question almost word for word. The real fact is still in the store, so every
read-side check passes; it just stopped reaching the door.

`--write-back` tests it, opt-in and report-only. For a few golden questions that pass on a
good day, the door is first starved (pressure equal to its budget) to show the answer really
gets lost, then a fixed degraded answer (`ADEBENCH_DEGRADED_ANSWER`, default `I have no
record of that. You asked: {question}`) goes through the memory's **own** write path, and
the question is asked again with no pressure. A case fails if the degraded answer reaches
the door or the real answer is no longer delivered. It is the STALE check, except the stale
value is one the system wrote itself. No LLM runs in the harness: whatever the memory does
with the exchange, a distiller included, is the memory's business.

An adapter opts in with three optional methods: `ingest_exchange(question, answer)` (the
normal write path of one exchange), `forget_memory(id)` (what was written is always
removed; the report says whether the removal was confirmed) and, if the memory processes
writes later, `settle()`. On the synthetic memory, whose write path stores the exchange as a
fact ranked first, both probes fail: that is the example of what the section catches.

## Other memory systems: write an adapter

The sections never talk to a memory system directly. They call an **adapter** — one class
implementing the contract in [`adebench/adapter.py`](adebench/adapter.py) — and the only
file that knows endpoints, tables and column names is that class.
[`adebench/ade.py`](adebench/ade.py) is the adapter for an ADE Brain and doubles as the
worked example: about 250 lines, HTTP plus read-only SQLite.

```bash
python -m adebench --adapter mymemory.bench:MyAdapter --cases my/cases
```

The contract, in short:

| Group | Methods | If your memory lacks it |
|---|---|---|
| liveness | `health`, `warm_up` | — |
| doors | `doors`, `door_text(query, door)`, `door_cut(door)`, `ask(query)` | at least one door is required: the text a client receives; `door_cut` returns its character budget or `None` |
| entity cards | `cards`, `corrections`, `aliases` | return `[]` → section SKIP |
| fact updates | `update_trace`, `event_date_share` | return `{}` / `(0, 0)` |
| episodes and time | `recent_days`, `episodes_of_day`, `signed_episodes` | return `[]` / `0` → those cases SKIP |
| live state | `working_write/read/clear`, `working_age_minutes` | the canary needs a writable short-lived store |
| files and graph | `file_search`, `graph_edges`, `graph_orphans`, `graph_counts` | return `[]` / `0` → SKIP |
| report-only | `health_report`, `measured_doors`, `traces`, `probe_doors` | free-form; may return empty |
| optional | `declared_bytes` | bytes declared by your MCP `tools/list`; absent → declared-vs-returned not measured |

The raw answer returned by `ask` and `door_text` is a plain dict with optional keys
(`summary`, `cards`, `semantic`, `episodic`, `working`, `unknown_terms`); missing keys
simply skip the checks that need them. A method that raises becomes an `ERROR` case. The
loader verifies the class has every method before the first call, and says which are
missing.

The weights are the same for every adapter, so two memory systems benchmarked with the same
golden set are comparable section by section — as long as the door is the same kind of door
and the coverage is the same.

### Second real memory: gbrain

[`adebench/gbrain.py`](adebench/gbrain.py) is the adapter for
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
    --cases examples/synthetic_data/cases --history /tmp/gbrain-run --write-back
```

Two reports side by side, scored on the sections both measured:

```bash
python -m adebench.compare history/brain.json /tmp/gbrain-run/gbrain.json brain gbrain
```

On the synthetic golden set gbrain 0.50 scores 75.4 of the 90 points it can be measured on
(`file_search` needs a repository); the report is in
[`examples/gbrain_report/`](examples/gbrain_report/), run of 28 Sep 2026 with adebench
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

### Third real memory: Dakera

[`adebench/dakera.py`](adebench/dakera.py) is the adapter for [Dakera](https://dakera.ai), a self-hosted vector memory server for AI agents. It talks to Dakera's REST API only (no engine code imported), scoped to a single `agent_id` namespace so a run never touches other data. Dakera is a retrieval + memory engine rather than a full personal brain, so the adapter supplies the thin reference reader `door_text` needs: cards first, then dated semantic facts, then episodic, then working, with an unknown-terms path so an invented subject abstains. [`examples/dakera_import.py`](examples/dakera_import.py) loads the synthetic set the way `gbrain_import.py` does — everything **stored as written**, no step edits the golden data.

What maps and what does not:

- **cards** stored verbatim; owner corrections / a distiller: none, so the correction cases SKIP
- **fact updates** — with adebench 0.2.12's optional `write_fact`, the `updates` section runs the **harness's own id-less update probe** (the same for every memory), and Dakera **passes it 3/3**. `write_fact` is a plain store with no id of what it replaces; Dakera's engine then forms a `Supersedes` edge to the near-identical earlier fact (shared entity, ≥0.92 cosine, strictly later), and a session-scoped recall **demotes the retired value**, so the door serves the new value and never the old, an unrelated fact about the same entity survives, and restating the value adds no copy. The adapter never says which fact is superseded — Dakera does. The adapter's own `--sandbox-test` ([`examples/dakera_sandbox_test.py`](examples/dakera_sandbox_test.py), 3 checks on a throwaway namespace) still runs and is **reported as evidence, no longer scored**, now that the harness probe measures the section
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
    --cases examples/synthetic_data/cases --repo examples/synthetic_data/repo \
    --sandbox-test examples/dakera_sandbox_test.py \
    --door chat --history /tmp/dakera-run
```

On the synthetic golden set Dakera scores **96.9 / 100** on this configuration, stable across repeated runs (report in [`examples/dakera_report/`](examples/dakera_report/)); on the 90 points gbrain is also measured on it is **86.9 vs gbrain's 75.4** (gbrain run of 28 Sep). The one door miss is a golden question whose fact (the owner's phone number) isn't in the set. Genuine supersession *is* exercised — and passes — in the `updates` section through `write_fact` (above), where Dakera's engine retires the old value. The door's stale question (`mailbox_version`) is a **different, softer case**: its pass is a **door result, not supersession** — the retired value (`1.3.0`) is stored verbatim and simply wasn't returned within `top_k=8` for that question, and the entity card (which carries only `1.4.2`) is what the door delivers; a query that ranked the historical line higher would serve it next to `1.4.2`. adebench scores what the door delivers, and here it did not deliver the stale line. Note: on a *default* Dakera instance, recall-time sentence-decomposition is on, which on a fresh tiny namespace crowds recall and makes the score non-deterministic run-to-run until it settles — hence the pinned config above.

### Fourth real memory: Memoose

[`adebench/memoose.py`](adebench/memoose.py) is the adapter for
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
[`examples/memoose_sandbox_test.py`](examples/memoose_sandbox_test.py) asks the same
question through Memoose's own API instead.

```bash
pip install memoose fastembed        # fastembed: without it the vectors fall back to a hash
python examples/memoose_import.py    # the synthetic memory, into dataset 'adebench'
python -m adebench --adapter adebench.memoose:MemooseAdapter     --cases examples/synthetic_data/cases --sandbox-test examples/memoose_sandbox_test.py     --history /tmp/memoose-run
memoose -d adebench forget --all     # the dataset was a scratch one
```

On the synthetic golden set Memoose scores 68.3 of the 90 points it can be measured on
(report in [`examples/memoose_report/`](examples/memoose_report/)). What the run says, and
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

### Fifth real memory: Aionforge Memory

[`adebench/aionforge.py`](adebench/aionforge.py) is the adapter for
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
ADEBENCH_LIVE_STATE_KEY= python -m adebench --adapter adebench.aionforge:AionforgeAdapter     --cases examples/synthetic_data/cases --history /tmp/aionforge-run --write-back
```

On the synthetic golden set Aionforge scores 51.8 of the 65 points it can be measured on
(report in [`examples/aionforge_report/`](examples/aionforge_report/)); on the 65 points
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

### Sixth real memory: Hindsight

[`adebench/hindsight.py`](adebench/hindsight.py) is the adapter for
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
python -m adebench --adapter adebench.hindsight:HindsightAdapter --cases examples/synthetic_data/cases     --history /tmp/hindsight-run --write-back --sections door cards updates time abstention file_search graph
```

On the synthetic golden set Hindsight scores 36.2 of the 55 points it can be measured on
(report in [`examples/hindsight_report/`](examples/hindsight_report/)); on the 55 points
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
  ([report](examples/hindsight_report/reference_floor_0.1.md): 36.5 / 55). Hindsight's own
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

### Seventh real memory: Jev-Mem

[`adebench/jevmem.py`](adebench/jevmem.py) is the adapter for
[Jev-Mem](https://github.com/libingzheren/Jev-Mem) (paper:
[arXiv 2609.23986](https://arxiv.org/abs/2609.23986)), agentic memory whose memory
decisions (typing, relations, routing, stopping) are taken by a small System-One model
instead of an LLM, over a graph with semantic, temporal, causal and entity links.
Jev-Mem is a Python library with heavy dependencies, so adebench does not import it:
the adapter starts [`adebench/jevmem_bridge.py`](adebench/jevmem_bridge.py) with
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
    --cases examples/synthetic_data/cases --history /tmp/jevmem-run --no-sandbox-test --write-back
```

**The build is not deterministic.** The same 21 observations, loaded twice, give
different link sets (on CPU as on GPU: 95 causal links in one build, 116 in the next),
and retrieval follows the links. So the number is the mean of six runs, each on a fresh
build: **41.9 of 65**, from 39.0 to 42.9
([`examples/jevmem_report/repeats.json`](examples/jevmem_report/repeats.json); the
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

### Eighth real memory: Nemp, measured inside Claude Code

[`adebench/nemp.py`](adebench/nemp.py) is the adapter for
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
    --cases examples/synthetic_data/cases --history /tmp/nemp-run --no-sandbox-test --write-back
```

On the synthetic golden set Nemp scores **36.4 of the 65 points** it can be measured on
(report in [`examples/nemp_report/`](examples/nemp_report/); 45 model turns, $6.93 at API
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

### Six more, found by the scout

[`adebench/scout.py`](adebench/scout.py) lists AI memory repositories on GitHub that
adebench has not measured yet (`python -m adebench.scout`: topic and keyword searches,
minus forks, archived, stale and curated lists; the state is kept across runs, so each run
shows only what is new). Six of the largest were measured on 29-30 Sep 2026, each with its
own adapter, import script and offline tests, and each adapter reviewed before publishing.
A memory that needs a model to write ran with Gemini, the way its users run it, never with
a smaller local model; where extraction is a model call the reference is the median of
three fresh builds, and the spread is in the report folder (`repeats.json`).

| Memory | Core · 55 | Full | Model | Report |
|---|---|---|---|---|
| [supermemory](https://github.com/supermemoryai/supermemory) | 38.1 | 48.1 / 65 | gemini-3.1-flash-lite (fixed by its binary) | [`supermemory_report/`](examples/supermemory_report/) |
| [agentmemory](https://github.com/rohitg00/agentmemory), keyless and with Gemini | 35.5 | 42.6 / 65 | none / gemini-3-flash | [`agentmemory_report/`](examples/agentmemory_report/) |
| [engram](https://github.com/Gentleman-Programming/engram) | 35.2 | 45.2 / 65 | none | [`engram_report/`](examples/engram_report/) |
| [mem0](https://github.com/mem0ai/mem0) (open-source library) | 34.8 | 44.8 / 65 | gemini-3-flash | [`mem0_report/`](examples/mem0_report/) |
| [cognee](https://github.com/topoteretes/cognee) | 33.7 | 43.7 / 65 | gemini-3-flash | [`cognee_report/`](examples/cognee_report/) |
| [memU](https://github.com/NevaMind-AI/memU) | 32.2 | 42.1 / 65 | gemini-3-flash as its executor agent | [`memu_report/`](examples/memu_report/) |

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

### The ADE Brain on the same set

The Brain is the memory adebench was written against, and its numbers in this README are
on its owner's real memory. For the leaderboard it runs on the synthetic set like everyone
else: [`examples/ade_import.py`](examples/ade_import.py) loads the set into an EMPTY Brain
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
python -c "import asyncio; from brain.memory.indexer import index_project;     asyncio.run(index_project('examples/synthetic_data/repo', force=True))"   # GOOGLE_API_KEY unset
ADEBENCH_LIVE_STATE_KEY= python -m adebench --brain http://127.0.0.1:8766     --cases examples/synthetic_data/cases --repo examples/synthetic_data/repo     --history /tmp/brain-synthetic-run --no-sandbox-test --write-back
```

On the synthetic golden set the Brain scores 93.8 / 100 (report in
[`examples/ade_synthetic_report/`](examples/ade_synthetic_report/)). What the run says:

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

## Reproducible example, no service needed

`examples/synthetic.py` is a second adapter: a small memory that lives in the process, with
invented data and **defects put there on purpose**, so the report shows FAIL as well as PASS.
Anyone can run it in two seconds and get the same number:

```bash
python -m adebench --adapter examples.synthetic:SyntheticAdapter \
  --cases examples/synthetic_data/cases --repo examples/synthetic_data/repo \
  --sandbox-test examples/synthetic_data/sandbox_test.py --history /tmp/adebench-run
```

Expected: **90.0 / 100**, 48 PASS · 5 FAIL · 0 ERROR · 0 SKIP. The five failures are the
five defects: a question about a fact the memory never stored, a fact that delivers the
retired version next to the current one (a `STALE` fail), a card missing one mandatory item
of its correction, an invented plugin that still drags in the calendar card, and an entity
with no edges in the graph. The full report is committed as
[`examples/synthetic_report/reference.md`](examples/synthetic_report/reference.md), and a
test in CI re-runs the example on every push and fails if the total or any section score
drifts from that reference.

The synthetic memory has no voice assistant: its doors are `chat` (a composed answer cut at
1,500 characters) and `raw`. It is also the proof that the adapter contract holds for a
memory that is not an ADE Brain.

## Run it

Requires Python 3.11+ and a running memory service. No third-party dependencies.

```bash
git clone https://github.com/adecubed/adebench
cd adebench
python -m adebench --brain http://localhost:8766 --cases cases/example --repo /path/to/brain/repo
```

Options:

| Flag / env | Meaning |
|---|---|
| `--adapter` / `ADEBENCH_ADAPTER` | `module:Class` adapter (default `adebench.ade:AdeAdapter`) |
| `--brain` / `ADEBENCH_BRAIN_URL` | memory service URL (default `http://localhost:8766`) |
| `--door` / `ADEBENCH_DOOR` | door measured by the `door` section (the adapter lists them) |
| `--pressure` / `ADEBENCH_PRESSURE` | simulated competing payload before the cut: characters, or `median` / `p95` / `max` of a census (default 0) |
| `--census` / `ADEBENCH_CENSUS` | callwitness baseline, URL or file (`callwitness.baseline.v1`) |
| `--pressure-profile` / `ADEBENCH_PRESSURE_PROFILE` | run the door at the census median, p95 and max too (report-only) |
| `--cases` / `ADEBENCH_CASES` | folder with `questions.json` and `abstention.json` |
| `--history` / `ADEBENCH_HISTORY` | where reports go (default `history/`) |
| `--repo` / `ADEBENCH_REPO` | repository root for the file-search section |
| `--sandbox-test` / `ADEBENCH_SANDBOX_TEST` | sandbox test script of the fact-update mechanism (prints `N/M passed`) |
| `--sections a b` | run only some sections (the report says what was not run) |
| `--no-sandbox-test` | skip the sandbox test; recorded in the setup fingerprint, so such a run is never compared with one that ran it |
| `--write-back` / `ADEBENCH_WRITE_BACK` | opt-in, report-only: a degraded answer through the memory's own write path must not come back through the door; removed afterwards |
| `ADEBENCH_DEGRADED_ANSWER` | the degraded answer written back, `{question}` replaced by the golden question (default `I have no record of that. You asked: {question}`) |
| `ADEBENCH_WRITE_BACK_QUESTIONS` / `_S` | how many golden questions to probe (default 2) and how long to wait for the write to reach the door (default 10 s) |
| `--validation` | write a validation sheet for the golden set (see below) |
| `ADEBENCH_VOICE_SOURCES`, `ADEBENCH_VOICE_CUT`, `ADEBENCH_EVENTS_BLOCK` | the voice client's sources, cut and events block, if yours differ |
| `ADEBENCH_MAX_CARD` | max length of an entity card (default 900) |
| `ADEBENCH_SIGNED_PREFIX` / `_QUESTION` | the prefix another machine signs its episodes with (default `[pc2]`) and the question that must find them, in the owner's language (default `what did pc2 do?`) |
| `ADEBENCH_LIVE_STATE_SESSION` / `_KEY` / `_MINUTES` | which live-state key must be fresh, and how fresh; an empty `_KEY` means the memory has no such key (the case is SKIP) |

Production memory is only read (SQLite opened read-only through the path the service
reports), with three exceptions, each removed at the end of its check: canaries in working
memory (session `adebench`, TTL one hour); one imported memory dated 2021-03-14, when the
adapter has `import_memory`; and, only with `--write-back`, the degraded exchanges. Run
`--write-back` on a sandbox when the memory's write path has side effects you cannot undo.

## The golden set, and how to validate it

`cases/example/questions.json` is a minimal example (the questions are in Italian because
the reference Brain speaks Italian). Your real golden set lives outside this repository: it
contains facts about you. Each question looks like:

```json
{"question": "Su che porta risponde il Brain?",
 "expected": [["8766"]],
 "entity": "brain",
 "validated": false}
```

`expected` is a list of groups; every group must be present, any alternative inside a group
counts. Alternatives match whole tokens; end one with `*` to accept a prefix
(`"anonimizz*"` matches *anonimizza* and *anonimizzazione*). `entity` (optional) requires
that entity's card to be part of the answer. `forbidden` (optional) lists **retired values
that must not reach the model**: a text carrying both the current port and the old one
passes a keyword check while the model has to guess, and that is worse than a clean miss —
the case fails with a `STALE` note and the report counts them (the forgetting-aware idea
from Memora's FAMA metric, applied to the delivered text). Be precise about what this
certifies: it is a **ban on presence**, not a detection of contradiction. "It was 8010,
now it is 8766" fails too, even though the old value is correctly labelled as history. That
is the requirement as stated — the retired value must not reach the model at all — and it
says nothing about whether the model would have guessed right. `validated` is a human flag: the benchmark
keeps warning until every question has been checked by the person who owns the memory.
`python -m adebench --validation` writes a sheet with each question, the expectations and
the first 600 characters the door delivers, so validating is a five-minute read.

`abstention.json` lists questions about things that do not exist. An entry is a plain
question, or `{"question": ..., "entity": "Girandola Notturna"}`: with the entity named, the
section also asks the memory whether it **stores** that entity anywhere (adapter method
`stored_mentions`, optional) and warns if it does. The reference Brain once stopped
abstaining on an invented workflow because an episode *about the benchmark* had named it:
the benchmark had written its own answer into the memory it measures. The rule is simple and
the warning enforces it: the invented entities never go into the memory, not even in notes
about the benchmark.

Two rules for a good golden set: deterministic expectations (ports, versions, names, dates)
rather than paraphrases, and never fix a failing case by loosening the expectation — if the
memory does not know a fact, teach it the fact.

## Why these sections

They come from reading the reference Brain, not from a paper: the voice client cuts at
2,400 characters and puts the card first, so that is what gets measured; entity cards are
regenerated from facts and the owner's corrections, so honouring corrections is a
first-class check; the distiller marks superseded facts, so the update mechanism is a
section; every fact carries an event date and the door attaches the age, so age delivery is
a section.

The literature still shaped it. Knowledge updates, abstention and temporal reasoning are the
three abilities every serious memory evaluation asks for (LongMemEval, Memora's
forgetting-aware accuracy, HaluMem's operation-level hallucinations). Reporting accuracy
together with latency and injected context, pinning the retrieval budget, and preferring
deterministic checks to an LLM judge come from the same place.

## Tests

```bash
pip install pytest
python -m pytest -q
```

The tests need no memory service: a fake adapter drives the sections and a local HTTP
server plays a broken service. They guard the ways a score could lie — an error counted as
a pass, a failed read counted as missing data, a missing feature counted as a success, a
substring counted as a match, one section counted as a full score, two runs overwriting
each other, a delta between two different setups. They run in CI on every push.

## What should be added?

This is an early version, published to ask exactly that. Things already on the list:

- an adapter for a real memory system that is not an ADE Brain (the synthetic one proves
  the contract; a real one would prove the sections);
- a live update test (write → correct → retrieve the new value → exclude the old one)
  against the running service, once the service exposes a dedup-aware write and a delete;
- an ingestion adapter to run LongMemEval / LoCoMo against a sandboxed memory and report the
  per-category delta against a no-memory baseline (not comparable to public leaderboards).
  A first step for the ADE Brain is in [`examples/longmemeval/`](examples/longmemeval/):
  retrieval recall, three readers including a local open-weight one, and the same answers
  under two judges;
- a judge (pinned model) for open-ended questions, kept separate from the deterministic score;
- duplicate detection across live facts as a health measure;
- a multi-machine section (federation: satellites pushing signed episodes to a central Brain).

Open an issue with what you would measure about a personal assistant's memory that this
does not.

## License

MIT. See `LICENSE`.

---

<a id="lang-it"></a>
## Italiano

adebench misura la memoria di un assistente AI per come viene usata davvero. Nasce per il
Brain ADE, il servizio Python che custodisce la memoria di lungo periodo dell'assistente
vocale Sofia, e parla con qualunque altra memoria attraverso un adattatore
(`adebench/adapter.py`; `adebench/ade.py` è l'implementazione ADE e fa da esempio).

Otto sezioni a punteggio: porta (cosa riceve il client, con il taglio del client vocale),
schede e correzioni, aggiornamento dei fatti, età e tempo, stato vivo, astensione, ricerca
file, grafo. Due di solo report: salute del ciclo memoria, latenza e caratteri per porta.
Ogni controllo finisce in PASS, FAIL, ERROR o SKIP: un errore non fa mai punti, una
funzione assente esce dal denominatore, e il report dice sempre quanto della suite è stato
misurato. Report JSON e Markdown a ogni corsa, con il delta solo rispetto a corse con lo
stesso setup.

```bash
python -m adebench --brain http://localhost:8766 --cases cases/example --repo /percorso/del/repo
python -m adebench --door agent        # senza assistente vocale
python -m adebench --validation        # scheda per validare il golden set
```

Il golden set vero vive fuori dal repo. Ogni domanda ha le parole attese a gruppi (a parola
intera, `*` per un prefisso), l'entità di cui serve la scheda, e il flag `validated` che
resta falso finché un umano non l'ha controllata. Regola: un caso che fallisce non si
aggiusta allargando le attese; se la memoria non sa un fatto, glielo si insegna.

È una versione iniziale, pubblicata per chiedere cosa manca. Apri una issue.
