# adebench — a benchmark for an ADE Brain, on its own terms

**English** · [Italiano](#lang-it)

`adebench` measures the memory of an [ADE](https://nerine.io) Brain — the Python service that
keeps the long-term memory of the Sofia voice assistant — the way that Brain is actually
used, not the way generic memory benchmarks are built.

Public benchmarks such as LoCoMo, LongMemEval or BEAM tell you how a memory architecture
performs on *somebody else's conversations*. They are the right tool to compare
architectures. They say nothing about whether *your* assistant will get the port number
right tomorrow, whether the entity card it reads aloud still honours the corrections you
gave it last week, or whether it will admit it has never heard of something.

adebench asks exactly those questions, against the live service, in about three minutes.

## What it measures

The score is 0–100, weighted over eight sections. Each section is a list of pass/fail
cases derived either from a small golden set you own or, for most sections, **from the
Brain's own data** — so the benchmark grows with the memory and cannot be gamed by
editing questions.

| Section | Weight | What passes |
|---|---|---|
| `porta` | 25 | The expected words are inside the text **the client actually receives** through the chosen door (see *Doors* below). Not the raw hits: the text. |
| `schede` | 15 | Every entity card exists, is dated, fits the limit, contains each *"non omettere mai"* item of the owner's corrections; every alias leads to the canonical card. Fully derived from the DB. |
| `aggiornamento` | 10 | Facts get **updated**, not accumulated: historical trace of `superseded`/`updates` plus an optional sandbox test of the dedup mechanism. |
| `tempo` | 10 | Every memory reaches the model with its age (`[dal …]`), the day filter of the episodic memory returns only that day, machine-signed episodes are found. |
| `stato_vivo` | 10 | A canary written to working memory is found immediately and survives the cut; the live mail state is fresher than 30 minutes. |
| `astensione` | 10 | On invented entities: no card, episodes marked as *no direct match*, no keyword hits — the Brain says it does not know. |
| `ricerca_file` | 10 | Real function names sampled from a repository: the grep-replacement search puts the right file in the top 5. |
| `grafo` | 10 | Every entity with a card has edges in the knowledge graph; no orphan fact nodes. |

Two more sections are **report-only** and never move the score: `salute` (health of the
memory lifecycle: live vs archived facts, share written through the v2 pipeline, facts at
the confidence floor, corrupted text, pending distillation, unacknowledged anomalies) and
`porte` (latency p50/p95 and characters produced per door: voice, agent search, orchestrator
context). The third axis — how much text the memory injects — is measured on every run,
because 90 % accuracy at 500 characters and 90 % at 5,000 are not the same thing.

Every run writes a JSON and a Markdown report to the history folder, with the delta against
the previous run, so the question becomes: *does the Brain remember better than yesterday?*

## Doors

A Brain is reached through more than one door, and each delivers a different text for the
same question. `--porta` picks the one the `porta` section measures; the other seven
sections are door-independent.

| Door | Who uses it | What is measured |
|---|---|---|
| `sofia` (default) | the voice assistant | `/sofia/ask` with the voice client's sources, its "latest events" block, card first, cut at 2,400 characters — what the voice model literally hears |
| `agente` | Claude, Codex, any MCP agent | the orchestrator context (`brain_get_context`) plus the top semantic hits (`brain_semantic_search`), no cut — what an agent literally gets at task start |
| `grezza` | your own client | `/sofia/ask` with the Brain's default sources and no cut — the upper bound of what retrieval can deliver |

No voice assistant? Run with `--porta agente`. Reports are only compared with previous runs
through the same door, because a delta between two doors would compare two different things.

## Other memory systems: write an adapter

The sections never talk to a memory system directly. They call an **adapter** — one class
implementing the contract in [`adebench/adattatore.py`](adebench/adattatore.py) — and the
only file that knows endpoints, tables and column names is that class.
[`adebench/ade.py`](adebench/ade.py) is the adapter for an ADE Brain and doubles as the
worked example: about 250 lines, HTTP plus read-only SQLite.

```bash
python -m adebench --adattatore mymemory.bench:MyAdapter --casi my/cases
```

The contract, in short:

| Group | Methods | If your memory lacks it |
|---|---|---|
| liveness | `health`, `riscalda` | — |
| doors | `porte`, `testo_della_porta(query, porta)`, `chiedi(query)` | at least one door is required: the text a client receives |
| entity cards | `schede`, `correzioni`, `alias` | return `[]` → section skipped, scored 0 |
| fact updates | `traccia_aggiornamenti`, `quota_event_date` | return `{}` / `(0, 0)` → trace-only score |
| episodes and time | `giorni_recenti`, `episodi_del_giorno`, `episodi_firmati` | return `[]` / `0` → those cases skipped |
| live state | `working_scrivi/leggi/cancella`, `working_eta_minuti` | the canary needs a writable short-lived store |
| files and graph | `ricerca_file`, `grafo_vicini`, `grafo_orfani`, `grafo_conteggi` | return `[]` / `0` → section skipped or scored 0 |
| report-only | `salute`, `porte_misurate`, `tracce`, `sonda_porte` | free-form; may return empty |

The raw answer returned by `chiedi` and `testo_della_porta` is a plain dict with optional
keys (`summary`, `schede`, `semantic`, `episodic`, `working`, `sconosciuti`); missing keys
simply skip the checks that need them. The loader verifies the class has every method
before the first call, and says which are missing.

The weights are the same for every adapter, so two memory systems benchmarked with the same
golden set are comparable section by section — as long as the door is the same kind of door.

## Run it

Requires Python 3.11+ and a running Brain. No third-party dependencies.

```bash
git clone https://github.com/adecubed/adebench
cd adebench
python -m adebench --brain http://localhost:8766 --casi casi/esempio --repo /path/to/brain/repo
```

Options:

| Flag / env | Meaning |
|---|---|
| `--adattatore` / `ADEBENCH_ADATTATORE` | `module:Class` adapter (default `adebench.ade:AdattatoreADE`) |
| `--brain` / `ADEBENCH_BRAIN_URL` | memory service URL (default `http://localhost:8766`) |
| `--porta` / `ADEBENCH_PORTA` | door measured by the `porta` section: `sofia`, `agente`, `grezza` |
| `ADEBENCH_BLOCCO_EVENTI` | set to `0` if your voice client has no "latest events" block |
| `--casi` / `ADEBENCH_CASI` | folder with `domande.json` and `astensione.json` |
| `--storico` / `ADEBENCH_STORICO` | where reports go (default `storico/`) |
| `--repo` / `ADEBENCH_REPO` | repository root for the file-search section |
| `--collaudo` / `ADEBENCH_COLLAUDO` | optional sandbox test script of the fact-update mechanism (prints `N/M passati`) |
| `--sezioni a b` | run only some sections |
| `--validazione` | write a validation sheet for the golden set (see below) |
| `ADEBENCH_SORGENTI`, `ADEBENCH_TAGLIO` | the voice client's sources and cut, if yours differ |

Production memory is only read (SQLite opened read-only through the path the Brain reports).
The only writes are a canary in working memory, session `adebench`, TTL one hour, removed at
the end of the run.

## The golden set, and how to validate it

`casi/esempio/domande.json` is a minimal example. Your real golden set lives outside this
repository (it contains facts about you). Each question looks like:

```json
{"domanda": "Su che porta risponde il Brain?",
 "attese": [["8766"]],
 "entita": "brain",
 "validata": false}
```

`attese` is a list of groups; every group must be present, any alternative inside a group
counts. `entita` (optional) requires that entity's card to be part of the answer.
`validata` is a human flag: the benchmark keeps warning until every question has been
checked by the person who owns the Brain. `python -m adebench --validazione` writes a sheet
with each question, the expectations and the first 600 characters the voice model would
hear, so validating is a five-minute read.

Two rules for a good golden set: deterministic expectations (ports, versions, names, dates)
rather than paraphrases, and never fix a failing case by loosening the expectation — if the
Brain does not know a fact, teach it the fact.

## Why these sections

They come from reading the Brain, not from a paper: the voice client cuts at 2,400
characters and puts the card first, so that is what gets measured; entity cards are
regenerated from facts and the owner's corrections, so honouring corrections is a first-class
check; the distiller marks superseded facts, so the update trace is a section; every fact
carries an `event_date` and the door attaches `[dal …]`, so age delivery is a section.

The literature still shaped it. Knowledge updates, abstention and temporal reasoning are the
three abilities every serious memory evaluation asks for (LongMemEval, Memora's
forgetting-aware accuracy, HaluMem's operation-level hallucinations). Reporting accuracy
together with latency and injected context, pinning the retrieval budget, and preferring
deterministic checks to an LLM judge come from the same place.

## What should be added?

This is the first version, and it is published to ask exactly that. Things already on the list:

- a second adapter for a memory system that is not an ADE Brain, to prove the contract holds;
- an ingestion adapter to run LongMemEval / LoCoMo against a sandboxed Brain and report the
  per-category delta against a no-memory baseline (not comparable to public leaderboards);
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

adebench misura la memoria di un Brain ADE — il servizio Python che custodisce la memoria di
lungo periodo dell'assistente vocale Sofia — per come quel Brain viene usato davvero.
I benchmark pubblici (LoCoMo, LongMemEval, BEAM) confrontano architetture su conversazioni
di altri; adebench chiede se *il tuo* assistente domani dirà la porta giusta, se la scheda
che legge a voce rispetta ancora le correzioni che gli hai dato, se ammette di non sapere.

Otto sezioni a punteggio (la porta, schede e correzioni, aggiornamento dei fatti, età e
tempo, stato vivo, astensione, ricerca file, grafo) più due di solo report (salute del ciclo
memoria, latenza e rumore per porta). La porta si sceglie con `--porta`: `sofia` misura il
testo che il modello vocale sente dopo il taglio a 2.400 caratteri, `agente` quello che un
agente MCP riceve a inizio task, `grezza` il limite superiore del recupero senza taglio.
Chi non ha Sofia usa `--porta agente`.
Report JSON e Markdown a ogni corsa, con il delta rispetto alla precedente.

```bash
python -m adebench --brain http://localhost:8766 --casi casi/esempio --repo /percorso/del/repo
python -m adebench --validazione   # scheda per validare il golden set
```

Il golden set vero vive fuori dal repo. Ogni domanda ha le parole attese a gruppi, l'entità
di cui serve la scheda, e il flag `validata` che resta falso finché un umano non l'ha
controllata. Regola: un caso che fallisce non si aggiusta allargando le attese; se il Brain
non sa un fatto, glielo si insegna.

È la prima versione: è pubblicata per chiedere cosa manca. Apri una issue.
