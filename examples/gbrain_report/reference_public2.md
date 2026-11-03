# adebench — 2026-11-03T11:00:20

**Score: 78.1 / 100 (+0.0)**
Cases: 68 PASS · 16 FAIL · 0 ERROR · 3 SKIP
Adapter `adebench.gbrain:GbrainAdapter` · door `search` · cases `a57efdf692` · setup `1f23c43a4d` · sections door, cards, updates, time, live_state, abstention, file_search, graph
Delta against the comparable run of 2026-11-03T10:53:58.

| Section | Weight | Points | PASS/FAIL/ERROR/SKIP |
|---|---|---|---|
| door | 25 | 19.8 (+0.0) | 19/5/0/0 |
| cards | 15 | 15.0 (+0.0) | 16/0/0/0 |
| updates | 10 | 3.3 (+0.0) | 1/2/0/0 |
| time | 10 | 10.0 (+0.0) | 5/0/0/1 |
| live_state | 10 | 10.0 (+0.0) | 7/0/0/1 |
| abstention | 10 | 10.0 (+0.0) | 12/0/0/0 |
| file_search | 10 | 0.0 (+0.0) | 0/9/0/0 |
| graph | 10 | 10.0 (+0.0) | 8/0/0/1 |
| write_back | report-only | — | 0/2/0/0 |

## door

- door: `"search"`
- door_budget_chars: `null`
- pressure_chars: `0`
- questions: `24`
- validated: `24`
- mean_answer_position: `293`
- mean_door_text_chars: `1254`
- min_margin_chars: `null`
- passes_within_300_chars_of_the_edge: `0`
- questions_with_forbidden_values: `3`
- stale_values_delivered: `2`
- chars_before_answer_mean: `293`
- duplicate_chunks_total: `0`

- ⚠ 2 answers delivered a retired value next to the current one: the model has to guess which is true

Not passed:
- FAIL Where is the documentation for Nexus API kept? — card nexus_api absent
- FAIL What is the lead researcher's name for Project Iota? — card project_iota absent
- FAIL What port does the Nexus API listen on? — STALE value delivered next to the current one: 8080
- FAIL What is the current version of the Lyra Scheduler? — card lyra_scheduler absent
- FAIL What is the current status of Z-Drive 10? — STALE value delivered next to the current one: standby

## cards

- cards: `8`
- corrections: `0`
- aliases: `0`
- aliases_tried: `0`

## updates

- probe: `true`
- probe_entity: `"zetdkjjia"`
- probe_replace_ms: `2387`
- probe_reads_with_both: `9`
- probe_cleanup_ok: `true`

- ⚠ no trace of updates in live memory: the dedup has not worked yet or found no pairs

Not passed:
- FAIL a new write with a changed value replaces the old one at the door (no id given) — new value served in 2387 ms; STALE: the old value is still delivered (9 reads with both)
- FAIL restating the current value does not pile up a second copy — 2 copies delivered

## time

- share_of_memories_with_age: `1.0`
- facts_with_event_date: `"0/0"`
- days_tried: `["2026-09-30", "2026-09-29", "2026-09-28"]`
- signed_episodes: `0`
- signed_question: `"what did pc2 do?"`

Not passed:
- SKIP episodes signed by another machine — none in this memory

## live_state

- live_state_age_min: `null`
- write_to_serve_ms: `2440`
- write_to_serve_p50_ms: `2470`
- write_to_serve_p95_ms: `2531`
- write_to_serve_samples: `3`
- write_to_serve_budget_s: `30`
- overwrite_to_visible_ms: `2533`
- stale_reads_after_overwrite: `0`
- repeated_writes_settle_ms: `2524`
- out_of_order_reads: `0`
- repeated_writes_timeline: `[{"t_ms": 0, "event": "first write"}, {"t_ms": 2227, "event": "second write"}, {"t_ms": 7185, "event": "poll", "first": false, "second": true}, {"t_ms": 10869, "event": "poll", "first": false, "second": true}, {"t_ms": 14401, "event": "poll", "first": false, "second": true}]`

Not passed:
- SKIP live-state key freshness — no live-state key configured (ADEBENCH_LIVE_STATE_KEY)

## abstention

- questions: `12`

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

- page_count: `52`
- chunk_count: `53`
- embedded_count: `53`
- link_count: `32`
- tag_count: `0`
- timeline_entry_count: `11`
- pages_by_type: `{"atom": 32, "note": 12, "project": 8}`
- orphan_fact_nodes: `"the graph has no fact nodes: nothing to check"`

Not passed:
- SKIP orphan fact nodes = 0 — the graph has no fact nodes: nothing to check

## write_back

- degraded_answer: `"I have no record of that. You asked: {question}"`
- questions_tested: `2`
- poisoned: `2`
- cleanup_ok: `true`
- wait_s: `10`

- ⚠ 2 of 2 degraded answers written back reached the door or pushed the real answer out: the memory learns from its own bad answers

Not passed:
- FAIL In which rack is Titan Node 4 mounted? — the degraded answer reached the door after 2338 ms
- FAIL What is the current version of the Nexus API? — the degraded answer reached the door after 2530 ms

## health

- page_count: `52`
- linkable_page_count: `20`
- embed_coverage: `1`
- stale_pages: `52`
- orphan_pages: `12`
- missing_embeddings: `0`
- brain_score: `71`
- dead_links: `0`
- entity_page_count: `0`
- link_coverage: `null`
- timeline_coverage: `null`
- most_connected: `[]`
- embed_coverage_score: `35`
- link_density_score: `15`
- timeline_coverage_score: `5`
- no_orphans_score: `6`
- no_dead_links_score: `10`
- migrations: `{"pending": ["0.11.0", "0.12.0", "0.12.2", "0.13.0", "0.13.1", "0.14.0", "0.16.0", "0.18.0", "0.18.1", "0.21.0", "0.22.4", "0.28.0", "0.29.1", "0.31.0", "0.32.2", "0.43.0", "0.46.3"], "partial": [], "wedged": [], "skipped_future": 0}`

## doors

- search: `{"calls": 69, "http_errors": 0, "ms_p50": 1276, "ms_p95": 1405, "mean_chars": 5088}`
- recall: `{"calls": 64, "http_errors": 0, "ms_p50": 1269, "ms_p95": 1393, "mean_chars": 3123}`
