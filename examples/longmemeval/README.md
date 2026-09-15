# LongMemEval-S on the ADE Brain: retrieval, readers, judges

adebench measures a memory on its owner's questions. This page is the other half: the same
memory architecture on **somebody else's conversations**, the public
[LongMemEval-S](https://github.com/xiaowu0162/LongMemEval) set (500 questions, ~50 sessions
each). It answers three questions in order: does the memory find the right sessions, does a
model answer correctly from what it found, and how much of that number belongs to the model
that reads and to the model that judges.

The retrieval code imports the Brain itself and is not in this repository. What is here is
everything after retrieval: the five sessions the Brain chose for every question
(`top5.jsonl`), the reader and judge scripts, every answer and every verdict. Anyone with the
dataset can re-run the readers and the judges on exactly the memory we measured.

## 1. Retrieval — does the memory find the sessions?

A sandboxed Brain, one empty episodic memory per question, one episode per exchange (500
characters per side), the episodic door, **no LLM anywhere**. Metric: strict session recall
@5, every evidence session inside the top five. 470 questions (the 30 abstention questions
have no evidence session).

| Brain retrieval | strict@5 |
|---|---|
| keyword search, Italian stopwords only | 64.5% (303/470) |
| + English stopwords | 75.1% (353/470) |
| BM25 (SQLite FTS5) | 82.6% (388/470) |
| BM25 + episode vectors, rank fusion, threshold 0.30 | **88.7% (417/470)** |

The same questions translated into Italian, sessions left in English: 83.4% with vectors,
37.2% with BM25 alone. Across languages, retrieval is almost entirely the vectors.

## 2. End to end — does a model answer from it?

The Brain's top five sessions go to a reader with the official LongMemEval prompt; the
official judge prompts decide. All 500 questions, judge GPT-4o (`gpt-4o-2024-08-06`):

| Reader | Correct | Correct when retrieval was complete |
|---|---|---|
| gemini-3-flash-preview | 79.8% (399/500) | 86.6% (361/417) |
| gpt-6-astra | 88.4% (442/500) | 96.6% (403/417) |

With a strong reader the ceiling is retrieval: 53 questions miss at least one evidence
session, and there the reader has little to work with.

## 3. The open-weight reader, and what the judge does to the number

**The question.** If the hosted models are unavailable — refused, repriced, or gone — does
the memory stay useful? The kill criterion was written before the run and is committed as
[`KILL_CRITERION.md`](KILL_CRITERION.md): at least 80/100 the thesis holds, 70–79 open
weight is a fallback, below 70 the thesis is dead on this hardware, with no re-run to rescue
it.

**The setup.** A stratified 100 of the 500 (same share per question type, fixed order by id
hash), the Brain's same five sessions, and a reader running locally: `gpt-oss:20b` through
Ollama on a laptop RTX 4050 (6 GB) with 40 GB of RAM, 76% of the model on CPU, context 32k,
temperature 0. Nothing leaves the machine while it reads. Median **48.4 s** per answer, p90
194 s, 3.5 hours for the 100.

**One judge for everyone.** Changing the reader's conditions is not enough; the judge has
to be the same for every reader, so all three were judged again by `gpt-5.1-2025-11-13`
(reasoning off) on the same 100 answers:

| Reader (same memory, same 100) | Judge GPT-4o | Judge GPT-5.1 |
|---|---|---|
| gemini-3-flash-preview | 83 | 85 |
| gpt-6-astra | 89 | 85 |
| gpt-oss:20b, local | — | **67** |

By question type, judge GPT-5.1 (gpt-oss / Gemini / Astra): knowledge update 14 / 14 / 13 of 15,
single-session 24 / 24 / 24 of 24, abstention 3 / 4 / 2 of 6, preference 1 / 2 / 3 of 6,
**multi-session 12 / 20 / 21 of 24, temporal reasoning 14 / 21 / 22 of 25**. With retrieval
complete (90 questions) gpt-oss answers 64, the hosted readers 82 each.

The judge is a configuration like the reader. The same answers that put one hosted reader
6 points ahead under GPT-4o tie under GPT-5.1. A number without its judge is not a result.

**Verdict: 67/100, below 70 — the kill criterion fired.** On this hardware the thesis is dead,
as written before the run.

What the number is made of matters more than the number. Where the answer sits in one place
the local reader keeps up with the hosted ones on the same memory: knowledge updates,
single-session facts. It falls behind where it has to reason across sessions: multi-session and
temporal questions account for the whole gap. Five of those misses are **empty answers** — the
model's reasoning filled the 32k context, for about twenty minutes each, before it wrote a
word. They are counted as wrong and as reader failures (five, one short of the criterion's
separate limit).

What this does not show: the same model with its full context on a server GPU. That is a
different experiment, with its own criterion written first — not a re-run of this one to
rescue the number.

## Reproduce

```bash
# dataset: longmemeval_s_cleaned.json from huggingface.co/datasets/xiaowu0162/longmemeval-cleaned
ollama pull gpt-oss:20b
LME_READER=ollama:gpt-oss:20b LME_SUBSET=100 LME_JUDGE=0 python longmemeval_reader.py longmemeval_s.json
LME_SUBSET=100 LME_JUDGE_MODEL=gpt-5.1-2025-11-13 OPENAI_API_KEY=... python longmemeval_rejudge.py longmemeval_s.json
```

Files: `top5.jsonl` (the Brain's retrieval per question), `qa_log_*.jsonl` (each reader's
answers), `judge_*_log.jsonl` (each verdict), `result_*.json` (the summaries above).

## What this does not show

LongMemEval measures a memory on invented chat histories. It says nothing about whether a
personal assistant gets its owner's port number right tomorrow — that is what adebench's own
sections are for. And 100 questions leave the small types thin: 6 abstention and 6
preference questions move a reader by several points on their own.
