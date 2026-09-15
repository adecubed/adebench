# adebench — a benchmark for personal AI memory, on its own terms

**English** · [Italiano](#lang-it)

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
| `updates` | 10 | Facts get **updated**, not accumulated: a sandbox test of the dedup mechanism (`--sandbox-test`). The historical trace is reported, never scored. |
| `time` | 10 | Every memory reaches the model with its age, the episodic day filter returns only that day, machine-signed episodes are found. |
| `live_state` | 10 | A canary written to working memory is served through the door (polled until it appears: the **write-to-serve latency** is reported in ms, with a p50/p95 over a few canaries, and a memory that never serves one within the budget fails); the same key **overwritten** is served with the new value and never the old one (a stale read right after a write, or both values together, is a fail); **two writes in quick succession** settle on the second and never go back to the first (out-of-order visibility is a fail); the live state key is fresher than N minutes. |
| `abstention` | 10 | On invented entities: no card, episodes marked as *no direct match*, no keyword hits — the memory says it does not know. |
| `file_search` | 10 | Real function names sampled from a repository: the grep-replacement search puts the right file in the top 5. |
| `graph` | 10 | Every entity with a card has edges in the knowledge graph; no orphan fact nodes. |

Two more sections are **report-only** and never move the score: `health` (memory lifecycle:
live vs archived facts, share written through the v2 pipeline, facts at the confidence
floor, corrupted text, pending distillation, unacknowledged anomalies) and `doors` (latency
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
gbrain init --pglite --non-interactive --embedding-model google:gemini-embedding-001 --embedding-dimensions 768
python examples/gbrain_import.py            # the synthetic memory, page by page
ADEBENCH_LIVE_STATE_KEY= python -m adebench --adapter adebench.gbrain:GbrainAdapter \
    --cases examples/synthetic_data/cases --history /tmp/gbrain-run
```

Two reports side by side, scored on the sections both measured:

```bash
python -m adebench.compare history/brain.json /tmp/gbrain-run/gbrain.json brain gbrain
```

On the synthetic golden set gbrain scores 73.8 of the 80 points it can be measured on
(`updates` needs a sandbox test of its own, `file_search` a repository); the two failing
door questions are the dataset's deliberate defects, the same two the synthetic memory
fails. The report is in [`examples/gbrain_report/`](examples/gbrain_report/). Any embedding
provider gbrain supports works; keyless mode leaves it with keyword search only.

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
| `--validation` | write a validation sheet for the golden set (see below) |
| `ADEBENCH_VOICE_SOURCES`, `ADEBENCH_VOICE_CUT`, `ADEBENCH_EVENTS_BLOCK` | the voice client's sources, cut and events block, if yours differ |
| `ADEBENCH_MAX_CARD` | max length of an entity card (default 900) |
| `ADEBENCH_LIVE_STATE_SESSION` / `_KEY` / `_MINUTES` | which live-state key must be fresh, and how fresh; an empty `_KEY` means the memory has no such key (the case is SKIP) |

Production memory is only read (SQLite opened read-only through the path the service
reports). The only writes are a canary in working memory, session `adebench`, TTL one hour,
removed at the end of the run.

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
