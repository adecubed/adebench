# Sets as data, a second public set and a private holdout

Date: 2026-09-30. Status: draft for review. Roadmap item 2 of the README.

## Why

The board ranks memories on one public set of 8 door questions and 4 abstention
questions, written by the author of the ADE Brain, which is second on the board. One
door probe is worth about 3 points and a core probe about 1.8, anyone can read the
questions, and nothing shows whether a memory's number holds on questions it has not
seen. This adds a larger public set to rank on and a private set to check against.

## Decisions taken

- A set's content is written by another model (Gemini) from a fixed specification, and
  accepted only by a mechanical validator. Nobody edits a set by hand.
- Each new set is three times the current one: 24 door questions, 12 abstention
  questions, about 60 history items.
- The board ranks on the new public set `public2`. The current set stays as `quick`,
  shown as a second column. The private set's numbers are not published: each memory's
  page shows only the outcome of the check (below).

## 1. Sets as data

A set is a folder:

```
sets/<name>/
  world.json      cards, facts, aliases, episodes (each with an id and, where it has one,
                  an event date), the set's reference date `as_of`, and the canary token
  cases/          questions.json, abstention.json (the format adebench reads today)
  repo/           the small repository for file search
  set.json        name, version, generator model and prompt hash, seed, sha256 of the
                  canonical content, validator report
```

`examples/synthetic.py` and `examples/synthetic_data/` become `sets/quick/`, with the same
content: the quick set's hash and every published number stay valid. Every import script
takes `--set <folder>` (default `sets/quick`) and reads `world.json` instead of importing
constants from `examples.synthetic`. This is a mechanical change to 15 importers, tested by
importing `quick` through the new loader into the synthetic memory and checking the
reference report does not move.

## 2. The generator

`python -m adebench.genset --name public2 --seed N --out sets/public2` sends Gemini a fixed
specification and writes the set. The specification fixes the mix, the same as today's set
scaled by three:

- door questions: 11 plain facts, 4 facts carried by an entity card, 3 questions through an
  alias (a real other name, sharing no word with the entity's name), 3 on a value that was
  replaced (the retired value listed in `forbidden`; the replacing fact states only the new
  value), 3 dated questions (the date written in the text). No never-stored questions:
  their answer is absent by construction, so every memory fails them, and not inventing is
  what the abstention section measures (decided 2026-09-30; the `quick` set keeps its one);
- abstention: 12 invented entities, each with a question;
- history: cards, dated and undated facts, aliases, episodes with times, some signed by
  another machine (`[pc2]`-style prefix);
- one canary token, a random string placed in a few history items, used only to detect
  leaks (section 5).

The generator never prints the content: it writes the set and prints the validator's
result. A set that fails validation is discarded and generated again (at most 5 attempts;
then the generator stops and reports).

## 3. The validator

Presence of text is not evidence. Every case is checked against the world at the set's
reference date `as_of`:

- **Answerable questions.** The generator returns, with each question, the ids of the
  items that answer it. For each expected token group, at least one cited item must contain
  it, be dated on or before `as_of` (or be undated), not be superseded by a later item about
  the same entity and attribute, and, if it is a fact, name its entity or one of its aliases.
  The match is the scorer's own (`sections.present`), so a set never counts on evidence the
  scorer would not find. A superseded item may be cited next to the current one, but never
  counts.
- **Retired values.** Every `forbidden` value must appear in the world only in the item it
  was retired from: not in a card, an episode or the replacing fact (decided 2026-09-30).
- **Specific answers.** An expected token is a specific value of at most 3 words, never a
  placeholder such as "null" or "unknown", which any JSON door or refusal would contain.
- **Invented entities.** Absent from every item, alias and file, under the same
  normalisation and as a whole word inside longer names; no alias of a real entity may
  normalise to one of them.
- **Leading questions.** No question contains any of its own expected tokens.
- **Structure.** The mix of section 2 is met exactly and no question has a kind outside it;
  ids are unique; every date parses; every alias points at an entity that exists and shares
  no word with its name.

The validator's report (counts per check, no content) goes into `set.json`.

## 4. The holdout check

Each memory runs on `public2` (5 builds with a model inside, 3 without) and on the
private set (3 and 1). The check compares the core score on the two sets, per 55 points.

Two sources of spread are counted:

- **builds**: the memory's own runs on each set, picked at random in each resample;
- **questions**: a different set samples different questions. Only the sections whose cases
  come from the set's questions are resampled (door and abstention, with replacement within
  each); updates and time are mostly probes the harness writes itself, the same on every
  set, and are taken from the picked run as they are.

The difference `private − public2` gets a 90 % interval from 2,000 such resamples.

The check is **one-sided** (decided 2026-09-30). With 24 door and 12 abstention questions a
set cannot show that two scores are *equal* within a few points: a simulation of a memory
that behaves identically on both sets gives an interval of about ±5.8 core points for a
typical memory and ±4.6 for a strong one, so an equivalence rule would almost always say
"inconclusive". It can show a *drop*, which is what the private set is for: a memory tuned to
the public questions typically loses ten points or more. With a minimum effect
**δ = 3 core points**:

| Outcome | When |
|---|---|
| **lower by X** | the whole interval lies below 0 and its midpoint is below −δ; X is the midpoint |
| **no drop detected (±Y)** | anything else; Y is the interval's half-width, so the reader sees how fine the check was |

Only the outcome, X or Y, δ, the number of builds on each side and the set's version and hash
are published, in `examples/<memory>_report/holdout.json`. The runs themselves stay in the
private folder.

## 5. Keeping the private set private

A rule in the assistant's memory says no session opens the private set. That is not enough
on its own, so:

- **Where it lives.** `~/adebench_holdout/`, outside every repository (not
  under `~/ade`, which is itself the orchestrator's repository), and a copy on
  the evaluation server for memories that need Docker. Never in `adebench_locale` or the
  orchestrator, which Brain development reads. The runner refuses a folder inside a
  repository. Private runs are kept per set version, so a `holdout-v2` never mixes with v1.
- **Frozen before any run.** After validation the set is saved as `holdout-v1` with the
  sha256 of its canonical content. Every run checks the hash and refuses on a mismatch. A
  new private set is `holdout-v2`, never an overwrite; Gemini's seed is recorded but not
  relied on to reproduce it.
- **An isolated runner.** `python -m adebench.holdout run --memory <name>` loads the set
  from the private folder into a fresh store, runs the benchmark with its history in the
  private folder, prints only aggregates, and deletes the memory's store at the end.
  Adapters get the store path from the runner, so no store lands in a default location. The
  run starts without the parent shell's benchmark and memory variables (`ADEBENCH_*`,
  `BRAIN_*`...): only its registry entry sets them, and a server memory must name its URL
  there, so a private set can never be loaded into a live memory by default.
- **Logs, caches, artifacts.** Each registry entry declares where its memory writes text
  outside the store (bridge logs, caches, a server's own data and log) in `cleanup`; the
  runner deletes those after the run and scans them like the rest.
- **A leak check.** After every private run (once per run, not per build) the runner
  searches for the canary token in the adebench repository, `~/ade` (the
  orchestrator, the live Brain's data, every memory's install), the memories' default data
  folders, Ollama's logs, the session transcripts and the temp folder, skipping installed
  code (`node_modules`, `__pycache__`, `.git`), model weights and links. A hit fails the run
  and names the file. About 30 s with a warm disk cache, several minutes cold.
- **Who runs it.** Agents that run the holdout are told to run the command and report its
  printed aggregates, never to open the folder. The generation prompt and the model's
  answers are written straight to the private folder.
- **What cannot be hidden.** The memories' own model providers (Gemini) see the content
  during the run, as they see every set. The check protects against the people and
  sessions that develop the memories, not against the providers.

## 6. The site

- Ranking on `public2` (mean, range, ties as today). A `quick` column next to it.
- Each memory page: both sets' numbers, and the holdout outcome with δ and the set's
  version and hash.
- Memories not yet run on `public2` (Dakera, Aionforge, Hindsight until a Docker host is
  free; Nemp unless its author runs it) are listed below the ranked ones with their `quick`
  number and a note, not mixed into the ranking.

## 7. Cost and order

About $30-40 of Gemini for all runs, mostly mem0, memU, cognee and supermemory on sets three
times larger; cents for generating the two sets. Order of work:

1. sets as data and the 15 importers, `quick` unchanged (checked by its hash and the
   synthetic reference);
2. generator and validator, with offline tests on hand-made small worlds that break each
   rule;
3. `public2` generated, validated, committed;
4. holdout generated and frozen, runner and leak check;
5. runs, then the site.

## Tests

- The validator rejects a world for each rule of section 3 (one hand-made case per rule).
- `quick` through the new loader gives the same synthetic reference, section by section.
- The holdout comparison gives each outcome on constructed run and case data.
- The runner refuses a set whose hash does not match, and fails on a planted canary.
