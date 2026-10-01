# adebench — what a memory hands to the model

**Leaderboard: [adebench.dev](https://adebench.dev)**

`adebench` measures the text an AI memory delivers to the model when it is asked a
question: whether the right fact is in it, updated, dated, without a retired value next to
it, and without an invented answer when there is nothing to find. It scores that text, not
the retrieval behind it: a fact that retrieval found and the client's cut removed does not
help the model.

It has two uses, and they are kept apart:

1. **A public comparison of memories** ([adebench.dev](https://adebench.dev)). Every memory
   is loaded with the same synthetic history ([`examples/synthetic_data/`](examples/synthetic_data/))
   through its own write path, then asked the same golden set through the door an agent
   uses. The ranking is on the **Core**, 55 points every memory can be measured on.
2. **A regression check on one memory**, with its owner's own golden set, after every
   change: *does it remember better than yesterday?* That is what adebench was first
   written for (an [ADE](https://nerine.io) Brain, the memory of the Sofia voice assistant),
   and those runs are never compared across memories.

Public benchmarks such as LoCoMo or LongMemEval measure how an architecture performs on
long conversations with a judge reading the answer. adebench is narrower and deterministic:
no LLM judges anything, every check is a token match on the delivered text, and a run takes
minutes. It does not (yet) cover multi-hop reasoning, contradictions beyond a retired value,
or memories at scale; see *What will be added*.

## The leaderboard

| Section | Points | In the Core | What passes |
|---|---|---|---|
| `door` | 25 | yes | the expected words are in the text the client receives, and no retired value is |
| `updates` | 10 | yes | a new value replaces the old one without being told which; an unrelated fact survives; restating adds no copy |
| `time` | 10 | yes | memories reach the model with their own date, not the write time; a day filter; an old memory imported keeps its date |
| `abstention` | 10 | yes | on invented entities the door says it does not know instead of handing over neighbours |
| `live_state` | 10 | no | a short-lived value written now is served, overwritten cleanly, and never goes back |
| `cards` | 15 | no | entity cards exist, are dated, honour the owner's corrections |
| `file_search` | 10 | no | a repository search puts the right file in the top 5 |
| `graph` | 10 | no | entities with a card have edges; no orphan facts |

**Core** is door + updates + time + abstention: a write and a read through the door, which
every memory has. It is the ranking. **Full** is the score over every section the memory
could be measured on; sections a memory does not have are SKIP and leave the denominator, so
Full is shown next to the Core but two Fulls with different coverage are not the same
measure.

**Sets.** A set is a folder in [`sets/`](sets/): the history a memory is loaded with
(`world.json`), the questions (`cases/`), a small repository (`repo/`) and its sha256
(`set.json`); every import script takes `--set <folder>`. `quick` is the original set (8 door
and 4 abstention questions, sha256 `680445ab…`), and every number below is on it.
`public2` (24 and 12, sha256 `4b5363ce…`) was written by gemini-3-flash-preview from the fixed
specification in [`adebench/genset.py`](adebench/genset.py) and accepted by the checks in
[`adebench/validate_set.py`](adebench/validate_set.py): every answer backed by an item valid at
the set's date, retired values only where they were retired, invented entities absent
everywhere. The board moves to `public2` once every memory has run on it.
A third set, `holdout-v1`, is private: written the same way and with the same checks, it lives
outside this repository, which keeps only its version and sha256 (`3cd42b9f…`, in
[`sets/holdout.json`](sets/holdout.json)). Only [`adebench/holdout.py`](adebench/holdout.py)
reads it, and it prints nothing from it but scores. For each memory the site publishes a single
outcome: its core score on the private set is either *lower by X* than on `public2`, or *no drop
detected (±Y)*. After every private run the set's canary token is searched for outside the
private folder, and a hit fails the run.

The board on 30 Sep 2026, adebench 0.2.17 (the live one is on the site, with one page per
memory, its configuration, its runs and its report). Scores are the mean of the runs kept
in each memory's report folder; two memories closer than the wider of their ranges, never
less than one probe (1.8 points), share a rank, and no memory ranks above one with a higher
mean ([`adebench/repeats.py`](adebench/repeats.py)):

| # | Memory | Core · 55 (mean) | Range | Runs | Full (mean) | Model on write |
|---|---|---|---|---|---|---|
| 1 | [Dakera](https://dakera.ai) | 51.9 | — | 1 | 96.9 / 100 | embeddings only (local models) |
| 2 | [ADE Brain](https://github.com/adecubed/adebench) | 48.8 | same | 5 | 93.8 / 100 | yes |
| 3= | [Aionforge](https://github.com/jscott3201/aionforge-memory) | 41.8 | — | 1 | 51.8 / 65 | embeddings only |
| 3= | [supermemory](https://github.com/supermemoryai/supermemory) | 40.5 | 38.1–43.0 | 5 | 50.5 / 65 | yes |
| 3= | [gbrain](https://github.com/garrytan/gbrain) | 40.4 | same | 3 | 75.4 / 90 | embeddings only |
| 5 | [Hindsight](https://github.com/vectorize-io/hindsight) | 36.3 | — | 1 | 36.2 / 55 | yes |
| 6= | [agentmemory](https://github.com/rohitg00/agentmemory) | 35.5 | same | 3 | 42.6 / 65 | no (keyless) |
| 6= | [agentmemory (Gemini)](https://github.com/rohitg00/agentmemory) | 35.5 | same | 5 | 42.6 / 65 | yes |
| 6= | [engram](https://github.com/Gentleman-Programming/engram) | 35.2 | same | 3 | 45.2 / 65 | no |
| 6= | [Memoose](https://github.com/AndrewNgo-ini/memoose) | 34.6 | same | 3 | 68.3 / 90 | no |
| 7= | [cognee](https://github.com/topoteretes/cognee) | 34.4 | 33.7–35.4 | 5 | 44.4 / 65 | yes |
| 7= | [mem0](https://github.com/mem0ai/mem0) | 34.2 | 30.4–35.5 | 5 | 44.2 / 65 | yes |
| 12= | [memU](https://github.com/NevaMind-AI/memU) | 32.2 | same | 5 | 42.1 / 65 | yes |
| 12= | [Nemp](https://github.com/SukinShetty/Nemp-memory) | 32.1 | — | 1 | 36.4 / 65 | yes |
| 12= | [Jev-Mem](https://github.com/libingzheren/Jev-Mem) | 31.9 | 28.9–33.0 | 6 | 41.9 / 65 | yes |

What the numbers can and cannot tell you, stated plainly:

- **One probe is about 1.8 Core points, and some memories move by several.** Memories with
  a model inside ran five fresh builds, deterministic ones three; supermemory spans 38.1 to
  43.0 on the Core and mem0 30.4 to 35.5, while the ADE Brain, memU and agentmemory gave the
  same number every time. Every raw report is in the repository. Dakera, Aionforge and
  Hindsight are still one run each (they need a Docker host), and so is Nemp (about $7 a run).
- **One public set, written by the author of the ADE Brain**, which is second on the board.
  Anyone can read the questions, so a memory can be tuned to them without meaning to. A
  private holdout set with the same structure, run before a memory goes on the board, and a
  second public set are planned.
- **Each memory runs as its users run it.** A memory that needs a model to write runs with
  a real provider (Gemini), never a smaller local model; the version, mode and every
  setting that is not the memory's default are on its page.
- **The door is the text the client literally receives** from the memory's tool; a write
  or storage time never counts as a memory's age; no local paths in a published report.
  Adapters written before 0.2.17 are being brought to these rules (Aionforge re-renders its
  door and dates by capture time).

Every memory's adapter, import script, reference report and notes from the run are in the
repository; the notes are collected in [`docs/memories.md`](docs/memories.md).

To add a memory, write an adapter (below), load the synthetic set, run it, and open a pull
request with the report. To find candidates, [topicscout](https://github.com/adecubed/topicscout)
lists AI memory repositories on GitHub that have no adapter yet:
`topicscout run ai-memory --out scout --known-from "adebench/*.py"`.

## What it measures

Two words come up everywhere below. A **door** is the path a memory is reached through and
the text that comes out of it: an MCP tool call, a REST search, a voice assistant's `/ask`
with its 2,400-character cut. The same question through two doors gives two different
texts, and adebench scores the text. A **card** is the composed summary a memory keeps about
one entity (a person, a project, a service), the thing to deliver first when the question
names it; few memories have them, which is why cards are outside the Core.

On the leaderboard every case comes from the synthetic golden set. On your own memory the
door, updates and abstention cases come from your golden set, while cards, time, graph and
file search are derived **from the memory's own data** (every card it holds, every alias,
the days it has episodes for), so those sections grow with the memory. The full score is
0-100 over eight sections, the same weights for every memory:

| Section | Weight | What passes |
|---|---|---|
| `door` | 25 | The expected words are inside the text **the client actually receives** through the chosen door (see *Doors*). Not the raw hits: the text. |
| `cards` | 15 | Every entity card exists, is dated, fits the limit, contains each mandatory item of the owner's corrections; every alias leads to the canonical card. Fully derived from the data. |
| `updates` | 10 | Facts get **updated**, not accumulated. With the optional `write_fact`, the harness runs the same probe on every memory: "listens on port 8000", then a new write with 9000 and no id of what it replaces, and the door must serve 9000 and never 8000 again; an unrelated fact about the same entity must survive, and restating the value must not pile up a copy. Without `write_fact`, the adapter's own sandbox test (`--sandbox-test`) scores, and the report says so. The historical trace is reported, never scored. |
| `time` | 10 | Every memory reaches the model with its age (a leading bracketed date in any language: `[since 2026-05-10]`, `[2026-05-10]`), the episodic day filter returns only that day, machine-signed episodes are found by a question in the owner's language, and a memory imported with an old original date reaches the door with **that** date, not the import date (optional `import_memory`, SKIP without it). |
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
LLM judge and would stop being deterministic. And the updates section scores the harness's own probe when the adapter can write a fact
(`write_fact`), otherwise the adapter's sandbox test; the historical trace of past updates
is reported, never scored, because an update that happened once does not prove the
mechanism works today.

## Doors

A memory is reached through more than one door, and each delivers a different text for the
same question. Each adapter lists its doors and `--door` picks the one the sections read
through; the leaderboard uses the door an agent gets from the memory's own tool. The ADE
adapter, for instance, exposes three:

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

The sections never talk to a memory directly. They call an **adapter**, one class
implementing the contract in [`adebench/adapter.py`](adebench/adapter.py); the only file
that knows endpoints, tools and tables is that class. Fifteen exist today, from REST and
MCP servers to Python libraries behind a bridge process (`jevmem.py`, `cognee.py`,
`mem0.py`) and a plugin measured inside Claude Code (`nemp.py`); the smallest are good
models to copy.

```bash
python -m adebench --adapter mymemory.bench:MyAdapter --cases sets/quick/cases
```

**What the Core needs.** For a memory to be on the board:

| Section | Methods it calls | Without them |
|---|---|---|
| all | `health`, `warm_up`, `doors`, `door_text(query, door)`, `door_cut(door)`, `ask(query)` | required: the door is the text a client receives; `door_cut` returns its budget or `None` |
| updates | `write_fact`, `forget_memory`, `settle` | the adapter's own `--sandbox-test` scores instead, and the report says so |
| time | `recent_days`, `episodes_of_day`, `event_date_share`, `signed_episodes`; `import_memory` | those cases SKIP |
| abstention | `ask`; `stored_mentions` | the leak check does not run |

**The rest is optional**: `cards`, `corrections`, `aliases` (return `[]`), the working
memory `working_write/read/clear/age_minutes` (live state), `file_search`, `graph_edges`,
`graph_orphans`, `graph_counts`, `update_trace`, the report-only `health_report`,
`measured_doors`, `traces`, `probe_doors`, and `ingest_exchange` (write-back) and
`declared_bytes`. The loader still asks for every name in the Protocol, so an adapter
without cards returns empty values for them; splitting the contract so these become truly
optional is on the list. A method that raises becomes an `ERROR` case, never a missing
value.

Four rules for an adapter whose numbers go on the board: `door_text` returns what the
memory's tool returns, not a re-rendering; a date is shown only when the memory holds the
memory's own date, never the write time; nothing is rewritten on the way in (the import
sends the synthetic set as it is); and everything that is not the memory's default is
stated in the docstring and in `health_report`.

The raw answer returned by `ask` and `door_text` is a plain dict with optional keys
(`summary`, `cards`, `semantic`, `episodic`, `working`, `unknown_terms`); missing keys
simply skip the checks that need them.

## Reproducible example, no service needed

`examples/synthetic.py` is a second adapter: a small memory that lives in the process, with
invented data and **defects put there on purpose**, so the report shows FAIL as well as PASS.
Anyone can run it in two seconds and get the same number:

```bash
python -m adebench --adapter examples.synthetic:SyntheticAdapter \
  --cases sets/quick/cases --repo sets/quick/repo \
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

Requires Python 3.11+. No third-party dependencies in adebench itself; each memory has its
own install, described in its adapter's docstring.

A memory on the synthetic set, the way the board is made (first load the set into an empty
store with the memory's import script, e.g. `examples/mem0_import.py`):

```bash
git clone https://github.com/adecubed/adebench
cd adebench
ADEBENCH_LIVE_STATE_KEY= python -m adebench --adapter adebench.mem0:Mem0Adapter \
    --cases sets/quick/cases --history /tmp/run --no-sandbox-test --write-back
```

Your own memory, with your own golden set (an ADE Brain here, the default adapter):

```bash
python -m adebench --brain http://localhost:8766 --cases my/cases --repo /path/to/brain/repo
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

## Your own memory: the golden set, and how to validate it

`cases/example/questions.json` is a minimal example for an ADE Brain. Your real golden set
lives outside this repository: it contains facts about you. Questions can be in any
language, the one your memory is used in. Each question looks like:

```json
{"question": "Which port does the Brain listen on?",
 "expected": [["8766"]],
 "entity": "brain",
 "validated": false}
```

`expected` is a list of groups; every group must be present, any alternative inside a group
counts. Alternatives match whole tokens; end one with `*` to accept a prefix
(`"anonymi*"` matches *anonymise* and *anonymisation*). `entity` (optional) requires
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

## What will be added

In order, from a review of 30 Sep 2026 that this README now answers:

- **Repeated runs for the last three**: Dakera, Aionforge and Hindsight, which need a Docker
  host (every other memory already has three or five runs on the board).
- **Configuration as data** on every memory's page: version, mode, top-k or limit, the
  model inside, the door's call.
- **A private holdout set** with the same structure, run before a memory goes on the board
  (a memory that scores 90 on the public set and 70 on the private one was tuned to the
  set), and **a second public set** with another hash, to see whether the order holds.
- **The adapter contract split** into the Core minimum and optional groups, and
  `sections.py` (one 64 KB file) split by section.
- **0.2.18 harness fixes**, each re-run on every memory it touches: the imported-date check
  looks too close to the canary and reports "not served" when a memory rewrote the text;
  duplicate and copy counts read a JSON door as one line or count one record's fields as
  copies.
- **New abilities**, not more of the same: multi-hop questions, contradictions beyond a
  retired value, preferences versus instructions.
- **Scale**: the same history at 10k, 100k and 1M tokens, because what changes a memory's
  answer is how much it holds, not how many questions it is asked.
- A LongMemEval / LoCoMo ingestion adapter reporting the per-category delta against a
  no-memory baseline (a first step for the ADE Brain is in
  [`examples/longmemeval/`](examples/longmemeval/)), and a pinned-model judge for
  open-ended questions, kept apart from the deterministic score.

Open an issue with what you would measure that this does not.

## License

MIT. See `LICENSE`.
