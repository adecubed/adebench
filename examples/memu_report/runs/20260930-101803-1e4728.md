# adebench — 2026-09-30T10:18:03

**Score: 42.1 / 65 — coverage 65/100: 35 not measured (no evidence)**
Cases: 15 PASS · 9 FAIL · 0 ERROR · 7 SKIP
Adapter `adebench.memu:MemuAdapter` · door `retrieve` · cases `0f9a4640dc` · setup `1e4728926b` · sections door, cards, updates, time, live_state, abstention, file_search, graph

| Section | Weight | Points | PASS/FAIL/ERROR/SKIP |
|---|---|---|---|
| door | 25 | 18.8 | 6/2/0/0 |
| cards | 15 | not measured | 0/0/0/1 |
| updates | 10 | 6.7 | 2/1/0/0 |
| time | 10 | 0.0 | 0/2/0/2 |
| live_state | 10 | 10.0 | 7/0/0/1 |
| abstention | 10 | 6.7 | 0/4/0/0 |
| file_search | 10 | not measured | 0/0/0/1 |
| graph | 10 | not measured | 0/0/0/2 |
| write_back | report-only | — | 2/0/0/0 |

## door

- door: `"retrieve"`
- door_budget_chars: `null`
- pressure_chars: `0`
- questions: `8`
- validated: `8`
- mean_answer_position: `480`
- mean_door_text_chars: `3649`
- min_margin_chars: `null`
- passes_within_300_chars_of_the_edge: `0`
- questions_with_forbidden_values: `1`
- stale_values_delivered: `1`
- chars_before_answer_mean: `480`
- duplicate_chunks_total: `17`

- ⚠ 17 repeated chunks across the delivered texts: budget spent twice on the same information
- ⚠ 1 answers delivered a retired value next to the current one: the model has to guess which is true

Not passed:
- FAIL Which version of MailBridge is installed for the mailbox? — STALE value delivered next to the current one: 1.3.0
- FAIL What is the owner's phone number? — missing +39

## cards

- ⚠ section not measured: no entity cards in this memory

Not passed:
- SKIP entity cards — this memory has none

## updates

- superseded_live: `0`
- relation_updates: `0`
- recall_files: `5`
- empty_recall_files: `0`
- segments: `22`
- probe: `true`
- probe_entity: `"zetnfeaji"`
- probe_replace_ms: `283`
- probe_reads_with_both: `0`
- probe_cleanup_ok: `true`

- ⚠ no trace of updates in live memory: the dedup has not worked yet or found no pairs

Not passed:
- FAIL restating the current value does not pile up a second copy — 2 copies delivered

## time

- share_of_memories_with_age: `0.0`
- facts_with_event_date: `"0/5"`
- days_tried: `[]`
- signed_episodes: `0`
- signed_question: `"what did pc2 do?"`

- ⚠ only 0 facts out of 5 carry the event date: for the others the age the model hears is the derivation date, not the fact's

Not passed:
- FAIL semantic memories carry their age (0/40) — 0%
- SKIP episodic day filter — no episodes
- FAIL an imported memory reaches the door with its original date — imported memory not served within 30 s
- SKIP episodes signed by another machine — none in this memory

## live_state

- live_state_age_min: `null`
- write_to_serve_ms: `283`
- write_to_serve_p50_ms: `304`
- write_to_serve_p95_ms: `335`
- write_to_serve_samples: `3`
- write_to_serve_budget_s: `30`
- overwrite_to_visible_ms: `286`
- stale_reads_after_overwrite: `0`
- repeated_writes_settle_ms: `281`
- out_of_order_reads: `0`
- repeated_writes_timeline: `[{"t_ms": 0, "event": "first write"}, {"t_ms": 310, "event": "second write"}, {"t_ms": 880, "event": "poll", "first": false, "second": true}, {"t_ms": 2183, "event": "poll", "first": false, "second": true}, {"t_ms": 3492, "event": "poll", "first": false, "second": true}]`

Not passed:
- SKIP live-state key freshness — no live-state key configured (ADEBENCH_LIVE_STATE_KEY)

## abstention

- questions: `4`

Not passed:
- FAIL What is the Zarpetta module? — 5 keyword facts for something that does not exist
- FAIL Who is Ottavio Brambillesco? — 5 keyword facts for something that does not exist
- FAIL Which port does the Fulmicotone service use? — 5 keyword facts for something that does not exist
- FAIL What does the calendar plugin Girandola do? — 5 keyword facts for something that does not exist

## file_search

- ⚠ section not measured: no repo configured (--repo)

Not passed:
- SKIP file search — no repo configured (--repo)

## graph

- orphan_fact_nodes: `"the graph has no fact nodes: nothing to check"`

- ⚠ section not measured: no case with evidence (all SKIP or no cases)

Not passed:
- SKIP entities with a card in the graph — no entity with a card
- SKIP orphan fact nodes = 0 — the graph has no fact nodes: nothing to check

## write_back

- degraded_answer: `"I have no record of that. You asked: {question}"`
- questions_tested: `2`
- poisoned: `0`
- cleanup_ok: `true`
- wait_s: `10`

## health

- bridge: `{"memu_version": "0.11.0-beta.3", "store": "<MEMU_STORE>/memu.sqlite3", "workspace": "<MEMU_STORE>/workspace", "embedding": "openai-compatible https://generativelanguage.googleapis.com/v1beta/openai/ gemini-embedding-001", "executor": "gemini-3-flash-preview via https://generativelanguage.googleapis.com/v1beta/openai/ chat/completions (function calling)", "retrieve_top_k": 5, "init_s": 1.28}`
- memorize_runs: `[{"sessions": 1, "jobs": 3, "s": 35.3, "changed": ["memory/zetnfeaji-connector"]}, {"sessions": 1, "jobs": 3, "s": 19.6, "changed": ["memory/zetnfeaji-connector"]}, {"sessions": 1, "jobs": 3, "s": 57.7, "changed": ["memory/zetnfeaji-connector"]}, {"sessions": 1, "jobs": 3, "s": 19.6, "changed": []}, {"sessions": 1, "jobs": 3, "s": 45.4, "changed": ["memory/household-info"]}, {"sessions": 1, "jobs": 3, "s": 28.8, "changed": ["memory/mailbridge-connector"]}, {"sessions": 1, "jobs": 3, "s": 27.8, "changed": []}]`
- executor: `{"role": "the external agent memU's memorize hands its job files to (memU itself calls no LLM)", "model": "gemini-3-flash-preview", "endpoint": "Google OpenAI-compatible chat/completions, function calling, default thinking", "prompt": "memU's own executor prompt (memu.cli._memorize_executor_prompt) and the job templates embedded in this memU build, unchanged; one agent session per prepared run (<=10 sessions)", "system_note": "You are the external agent that carries out a prepared memU self-evolve run.\nYou have no shell. Use these tools instead of `bash`:\n  read_file(path)            instead of `cat <path>`\n  list_dir(path)             instead of `ls <path>`\n  write_file(path, content)  to create or overwrite a file\n  append_line(path, line)    instead of `echo \"<line>\" >> <path>`\n  run_command(command)       only for the memU command a job tells you to run\nPaths are relative to your working directory; the memU workspace is `workspace`.", "tools_given": ["read_file", "list_dir", "write_file", "append_line", "run_command (only `memu memorize verify-resources`)"], "tools_not_given": ["a shell", "network", "any path outside the workspace"], "max_steps_per_run": 200}`
- usage: `{"llm_calls": 125, "llm_prompt_tokens": 430141, "llm_completion_tokens": 4359, "llm_total_tokens": 456951, "llm_errors": 0, "embed_calls": 87, "embed_texts": 95, "embed_chars": 4206, "memorize_runs": 7, "memorize_sessions": 7, "memorize_s": 234.3, "noop_runs": 2, "discarded_runs": 0}`
- health: `{"ok": true, "files": 10, "embed_dims": 3072, "embed_ms": 284}`

- ⚠ the score is memU PLUS its external executor: memU calls no LLM, memorize hands its job files to an agent; here gemini-3-flash-preview with file tools and no shell (measures.executor)
- ⚠ no entity cards, no episodes, no graph, no files: those sections are SKIP; memU's retrieve is a vector search over page lines with no relevance floor: it always returns its top 5
- ⚠ no event dates: memorize input accepts no timestamp; memU's timestamps are write times

## doors

- retrieve: `{"calls": 71, "http_errors": 0, "ms_p50": 298, "ms_p95": 347, "mean_chars": 3939}`
- hook: `{"calls": 8, "http_errors": 0, "ms_p50": 292, "ms_p95": 310, "mean_chars": 2978}`
