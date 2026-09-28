# adebench — 2026-09-28T14:48:04

**Score: 93.8 / 100 (+0.9)**
Cases: 48 PASS · 2 FAIL · 0 ERROR · 1 SKIP
Adapter `adebench.ade:AdeAdapter` · door `voice` · cases `0f9a4640dc` · setup `2942d1d84b` · sections door, cards, updates, time, live_state, abstention, file_search, graph
Delta against the comparable run of 2026-09-28T14:22:53.

| Section | Weight | Points | PASS/FAIL/ERROR/SKIP |
|---|---|---|---|
| door | 25 | 18.8 (+0.0) | 6/2/0/0 |
| cards | 15 | 15.0 (+0.0) | 11/0/0/0 |
| updates | 10 | 10.0 (+0.0) | 3/0/0/0 |
| time | 10 | 10.0 (+0.0) | 6/0/0/0 |
| live_state | 10 | 10.0 (+0.0) | 7/0/0/1 |
| abstention | 10 | 10.0 (+0.8) | 4/0/0/0 |
| file_search | 10 | 10.0 (+0.0) | 6/0/0/0 |
| graph | 10 | 10.0 (+0.0) | 5/0/0/0 |
| write_back | report-only | — | 2/0/0/0 |

## door

- door: `"voice"`
- door_budget_chars: `2400`
- pressure_chars: `0`
- questions: `8`
- validated: `8`
- mean_answer_position: `392`
- mean_door_text_chars: `1272`
- min_margin_chars: `1572`
- passes_within_300_chars_of_the_edge: `0`
- questions_with_forbidden_values: `1`
- stale_values_delivered: `1`
- chars_before_answer_mean: `392`
- duplicate_chunks_total: `0`

- ⚠ 1 answers delivered a retired value next to the current one: the model has to guess which is true

Not passed:
- FAIL Which version of MailBridge is installed for the mailbox? — STALE value delivered next to the current one: 1.3.0
- FAIL What is the owner's phone number? — missing +39

## cards

- cards: `4`
- corrections: `0`
- aliases: `3`
- aliases_tried: `3`

## updates

- superseded_live: `0`
- relation_updates: `0`
- archive_by_reason: `{}`
- archive_has_v2_columns: `false`
- v2_share: `1.0`
- probe: `true`
- probe_entity: `"zetijafcg"`
- probe_replace_ms: `124`
- probe_reads_with_both: `0`
- probe_cleanup_ok: `true`

- ⚠ no trace of updates in live memory: the dedup has not worked yet or found no pairs

## time

- share_of_memories_with_age: `1.0`
- facts_with_event_date: `"12/14"`
- days_tried: `["2026-09-10", "2026-09-09", "2026-09-08"]`
- signed_episodes: `1`
- signed_question: `"what did pc2 do?"`

## live_state

- live_state_age_min: `null`
- write_to_serve_ms: `101`
- write_to_serve_p50_ms: `95`
- write_to_serve_p95_ms: `101`
- write_to_serve_samples: `3`
- write_to_serve_budget_s: `30`
- overwrite_to_visible_ms: `72`
- stale_reads_after_overwrite: `0`
- repeated_writes_settle_ms: `66`
- out_of_order_reads: `0`
- repeated_writes_timeline: `[{"t_ms": 0, "event": "first write"}, {"t_ms": 4, "event": "second write"}, {"t_ms": 74, "event": "poll", "first": false, "second": true}, {"t_ms": 1185, "event": "poll", "first": false, "second": true}, {"t_ms": 2297, "event": "poll", "first": false, "second": true}]`

Not passed:
- SKIP live-state key freshness — no live-state key configured (ADEBENCH_LIVE_STATE_KEY)

## abstention

- questions: `4`

## file_search

- indexable_functions: `6`
- tried: `6`

## graph

- nodes: `15`
- edges: `11`
- orphan_fact_nodes: `"0 orphans out of 11"`

## write_back

- degraded_answer: `"I have no record of that. You asked: {question}"`
- questions_tested: `2`
- poisoned: `0`
- cleanup_ok: `true`
- wait_s: `10`

## health

- index_coverage: `{"episodic_memory_fts": {"stored": 4, "indexed": 4}, "episodic_archive_fts": {"stored": 0, "indexed": 0}, "semantic_fts": {"stored": 18, "indexed": 18}}`
- live_facts: `18`
- archived_facts: `3`
- by_relation_type: `{"fact": 14, "scheda": 4}`
- facts_by_producer: `{"cross_": 0, "folder:": 0, "distiller/other": 14}`
- at_floor_0.3: `0`
- mojibake: `0`
- episodes_to_distill: `4`
- unacknowledged_anomalies: `5`
- episodes: `4`

## doors

- /sofia/ask: `{"calls": 56, "http_errors": 0, "ms_p50": 104, "ms_p95": 156, "mean_chars": 723}`
- /brain/memory/tool/search: `{"calls": 14, "http_errors": 0, "ms_p50": 2, "ms_p95": 10, "mean_chars": 218}`
- /brain/orchestrator/context: `{"calls": 8, "http_errors": 0, "ms_p50": 96, "ms_p95": 114, "mean_chars": 1071}`
