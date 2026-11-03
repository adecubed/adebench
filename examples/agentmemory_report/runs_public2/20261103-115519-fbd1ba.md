# adebench — 2026-11-03T11:55:19

**Score: 45.7 / 75 (+0.0) — coverage 75/100: 25 not measured (no evidence)**
Cases: 32 PASS · 29 FAIL · 0 ERROR · 4 SKIP
Adapter `adebench.agentmemory:AgentmemoryAdapter` · door `recall` · cases `a57efdf692` · setup `fbd1bad51d` · sections door, cards, updates, time, live_state, abstention, file_search, graph
Delta against the comparable run of 2026-11-03T11:54:40.

| Section | Weight | Points | PASS/FAIL/ERROR/SKIP |
|---|---|---|---|
| door | 25 | 21.9 (+0.0) | 21/3/0/0 |
| cards | 15 | not measured | 0/0/0/1 |
| updates | 10 | 6.7 (+0.0) | 2/1/0/0 |
| time | 10 | 6.7 (+0.0) | 4/2/0/0 |
| live_state | 10 | 7.1 (+0.0) | 5/2/0/1 |
| abstention | 10 | 3.3 (+0.0) | 0/12/0/0 |
| file_search | 10 | 0.0 (+0.0) | 0/9/0/0 |
| graph | 10 | not measured | 0/0/0/2 |
| write_back | report-only | — | 0/0/0/1 |

## door

- door: `"recall"`
- door_budget_chars: `null`
- pressure_chars: `0`
- questions: `24`
- validated: `24`
- mean_answer_position: `358`
- mean_door_text_chars: `6424`
- min_margin_chars: `null`
- passes_within_300_chars_of_the_edge: `0`
- questions_with_forbidden_values: `3`
- stale_values_delivered: `3`
- chars_before_answer_mean: `358`
- duplicate_chunks_total: `6`

- ⚠ 6 repeated chunks across the delivered texts: budget spent twice on the same information
- ⚠ 3 answers delivered a retired value next to the current one: the model has to guess which is true

Not passed:
- FAIL What port does the Nexus API listen on? — STALE value delivered next to the current one: 8080
- FAIL What is the current version of the Lyra Scheduler? — STALE value delivered next to the current one: 1.2
- FAIL What is the current status of Z-Drive 10? — STALE value delivered next to the current one: standby

## cards

- ⚠ section not measured: no entity cards in this memory

Not passed:
- SKIP entity cards — this memory has none

## updates

- memories: `46`
- superseded_live: `0`
- relation_updates: `0`
- probe: `true`
- probe_entity: `"zetmbgapp"`
- probe_replace_ms: `27`
- probe_reads_with_both: `0`
- probe_cleanup_ok: `true`

- ⚠ no trace of updates in live memory: the dedup has not worked yet or found no pairs

Not passed:
- FAIL restating the current value does not pile up a second copy — 3 copies delivered

## time

- share_of_memories_with_age: `0.875`
- facts_with_event_date: `"36/46"`
- days_tried: `["2026-09-30", "2026-09-29", "2026-09-28"]`
- signed_episodes: `3`
- signed_question: `"what did pc2 do?"`

Not passed:
- FAIL semantic memories carry their age (77/88) — 88%
- FAIL an imported memory reaches the door with its original date — served with no date

## live_state

- live_state_age_min: `null`
- write_to_serve_ms: `27`
- write_to_serve_p50_ms: `27`
- write_to_serve_p95_ms: `34`
- write_to_serve_samples: `3`
- write_to_serve_budget_s: `30`
- overwrite_to_visible_ms: `11`
- stale_reads_after_overwrite: `0`
- repeated_writes_settle_ms: `28`
- out_of_order_reads: `29`
- repeated_writes_timeline: `[{"t_ms": 0, "event": "first write"}, {"t_ms": 7, "event": "second write"}, {"t_ms": 58, "event": "poll", "first": true, "second": true}, {"t_ms": 1106, "event": "poll", "first": true, "second": true}, {"t_ms": 2146, "event": "poll", "first": true, "second": true}, {"t_ms": 3190, "event": "poll", "first": true, "second": true}, {"t_ms": 4265, "event": "poll", "first": true, "second": true}, {"t_ms": 5305, "event": "poll", "first": true, "second": true}, {"t_ms": 6354, "event": "poll", "first": true, "second": true}, {"t_ms": 7395, "event": "poll", "first": true, "second": true}, {"t_ms": 8420, "event": "poll", "first": true, "second": true}, {"t_ms": 9506, "event": "poll", "first": true, "second": true}, {"t_ms": 10558, "event": "poll", "first": true, "second": true}, {"t_ms": 11584, "event": "poll", "first": true, "second": true}, {"t_ms": 12630, "event": "poll", "first": true, "second": true}, {"t_ms": 13659, "event": "poll", "first": true, "second": true}, {"t_ms": 14698, "event": "poll", "first": true, "second": true}, {"t_ms": 15740, "event": "poll", "first": true, "second": true}, {"t_ms": 16788, "event": "poll", "first": true, "second": true}, {"t_ms": 17828, "event": "poll", "first": true, "second": true}, {"t_ms": 18848, "event": "poll", "first": true, "second": true}, {"t_ms": 19886, "event": "poll", "first": true, "second": true}, {"t_ms": 20926, "event": "poll", "first": true, "second": true}, {"t_ms": 21954, "event": "poll", "first": true, "second": true}, {"t_ms": 22995, "event": "poll", "first": true, "second": true}, {"t_ms": 24029, "event": "poll", "first": true, "second": true}, {"t_ms": 25059, "event": "poll", "first": true, "second": true}, {"t_ms": 26095, "event": "poll", "first": true, "second": true}, {"t_ms": 27152, "event": "poll", "first": true, "second": true}, {"t_ms": 28184, "event": "poll", "first": true, "second": true}, {"t_ms": 29212, "event": "poll", "first": true, "second": true}, {"t_ms": 30238, "event": "poll", "first": true, "second": true}]`

Not passed:
- FAIL after overwriting the canary the door serves the new value, never the old one — overwrite-to-visible 11 ms · STALE: old and new value delivered together
- FAIL two writes in quick succession: the door settles on the second, never back on the first — second write visible in 28 ms · 29 read(s) served the first write after the second was already visible
- SKIP live-state key freshness — no live-state key configured (ADEBENCH_LIVE_STATE_KEY)

## abstention

- questions: `12`
- leaked_entities: `0`

Not passed:
- FAIL What is the primary function of the Zoltaris module? — episodes presented as direct matches; 3 keyword facts for something that does not exist
- FAIL Does Vornak interface with the Nexus API? — episodes presented as direct matches; 5 keyword facts for something that does not exist
- FAIL How many Glimmox units are installed in Sector G? — episodes presented as direct matches; 6 keyword facts for something that does not exist
- FAIL Is Brakit compatible with Lyra Scheduler? — episodes presented as direct matches; 7 keyword facts for something that does not exist
- FAIL Who designed the Krelin processor? — episodes presented as direct matches; 4 keyword facts for something that does not exist
- FAIL When was the Duxo firmware last updated? — episodes presented as direct matches; 5 keyword facts for something that does not exist
- FAIL Does Jalvor require access to Orion DB? — episodes presented as direct matches; 6 keyword facts for something that does not exist
- FAIL What is the encryption level of Moxie? — episodes presented as direct matches; 3 keyword facts for something that does not exist
- FAIL Is the Plynth sensor calibrated? — episodes presented as direct matches; 3 keyword facts for something that does not exist
- FAIL Where is the Quarx server located? — episodes presented as direct matches; 3 keyword facts for something that does not exist
- FAIL What protocol does Riften use? — episodes presented as direct matches; 3 keyword facts for something that does not exist
- FAIL Is Skalo active in the West Wing? — episodes presented as direct matches; 3 keyword facts for something that does not exist

## file_search

- indexable_functions: `9`
- tried: `9`

Not passed:
- FAIL check_protocol → nexus_utils.py — top5: []
- FAIL schedule_backup → db_monitor.py — top5: []
- FAIL verify_engine → db_monitor.py — top5: []
- FAIL set_orchestration_port → scheduler_core.py — top5: []
- FAIL check_drive_status → db_monitor.py — top5: []
- FAIL get_api_version → nexus_utils.py — top5: []
- FAIL run_rust_task → scheduler_core.py — top5: []
- FAIL log_response → nexus_utils.py — top5: []
- FAIL get_current_v → scheduler_core.py — top5: []

## graph

- nodes: `0`
- edges: `0`
- orphan_fact_nodes: `"the graph has no fact nodes: nothing to check"`

- ⚠ section not measured: no case with evidence (all SKIP or no cases)

Not passed:
- SKIP entities with a card in the graph — no entity with a card
- SKIP orphan fact nodes = 0 — the graph has no fact nodes: nothing to check

## write_back

- degraded_answer: `"I have no record of that. You asked: {question}"`
- questions_tested: `0`
- poisoned: `0`
- cleanup_ok: `null`
- wait_s: `10`

Not passed:
- SKIP the degraded answer does not come back through the door — no write path in this adapter (ingest_exchange / forget_memory)

## health

- status: `"critical"`
- http: `503`
- version: `"0.9.29"`
- alerts: `["cpu_critical_330%"]`
- notes: `["memory_heap_tight_95%_rss188mb"]`
- llm_provider: `"llm"`
- embedding_provider: `"embeddings"`
- flags_enabled: `["CONSOLIDATION_ENABLED"]`
- memories: `46`
- memories_latest: `46`
- graph: `{"nodes": 0, "edges": 0}`

- ⚠ /health answered HTTP 503 status critical: ['cpu_critical_330%'] (its monitor averages CPU over 30 s)
- ⚠ no entity cards and no file search: those sections are SKIP; the graph is extracted from episodes only: no entity card to check edges on, the orphan count is reported, not scored
- ⚠ the transcript import compresses without a model whatever the provider: the assistant's reply is dropped, episodes keep only the user's prompt

## doors

- memory_recall: `{"calls": 80, "http_errors": 0, "ms_p50": 27, "ms_p95": 51, "mean_chars": 7013}`
- memory_smart_search: `{"calls": 10, "http_errors": 0, "ms_p50": 13, "ms_p95": 37, "mean_chars": 2890}`
