# adebench — 2026-11-03T16:12:15

**Score: 47.2 / 75 — coverage 75/100: 25 not measured (no evidence)**
Cases: 33 PASS · 28 FAIL · 0 ERROR · 4 SKIP
Adapter `adebench.jevmem:JevMemAdapter` · door `evidence` · cases `a57efdf692` · setup `455b1b0328` · sections door, cards, updates, time, live_state, abstention, file_search, graph

| Section | Weight | Points | PASS/FAIL/ERROR/SKIP |
|---|---|---|---|
| door | 25 | 21.9 | 21/3/0/0 |
| cards | 15 | not measured | 0/0/0/1 |
| updates | 10 | 3.3 | 1/2/0/0 |
| time | 10 | 6.7 | 4/2/0/0 |
| live_state | 10 | 10.0 | 7/0/0/1 |
| abstention | 10 | 5.3 | 0/12/0/0 |
| file_search | 10 | 0.0 | 0/9/0/0 |
| graph | 10 | not measured | 0/0/0/2 |
| write_back | report-only | — | 0/2/0/0 |

## door

- door: `"evidence"`
- door_budget_chars: `null`
- pressure_chars: `0`
- questions: `24`
- validated: `24`
- mean_answer_position: `181`
- mean_door_text_chars: `1118`
- min_margin_chars: `null`
- passes_within_300_chars_of_the_edge: `0`
- questions_with_forbidden_values: `3`
- stale_values_delivered: `3`
- chars_before_answer_mean: `181`
- duplicate_chunks_total: `0`

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

- links_by_type: `{"SEMANTIC:RELATED_TO": 236, "CAUSAL:LEADS_TO": 184, "TEMPORAL:PRECEDES": 57, "TEMPORAL:SUCCEEDS": 57, "TEMPORAL:TEMPORALLY_CLOSE": 41, "ENTITY:SHARED_ENTITY": 403}`
- superseded_live: `0`
- relation_updates: `0`
- probe: `true`
- probe_entity: `"zethhckeh"`
- probe_replace_ms: `4211`
- probe_reads_with_both: `26`
- probe_cleanup_ok: `true`

- ⚠ no trace of updates in live memory: the dedup has not worked yet or found no pairs

Not passed:
- FAIL a new write with a changed value replaces the old one at the door (no id given) — new value served in 4211 ms; STALE: the old value is still delivered (26 reads with both)
- FAIL restating the current value does not pile up a second copy — 6 copies delivered

## time

- share_of_memories_with_age: `0.441`
- facts_with_event_date: `"48/58"`
- days_tried: `["2026-09-30", "2026-09-29", "2026-09-28"]`
- signed_episodes: `3`
- signed_question: `"what did pc2 do?"`

Not passed:
- FAIL semantic memories carry their age (49/111) — 44%
- FAIL «what did pc2 do?» finds the episodes signed [pc2] — 0 episodes in the answer

## live_state

- live_state_age_min: `null`
- write_to_serve_ms: `7661`
- write_to_serve_p50_ms: `6887`
- write_to_serve_p95_ms: `7661`
- write_to_serve_samples: `3`
- write_to_serve_budget_s: `30`
- overwrite_to_visible_ms: `5412`
- stale_reads_after_overwrite: `0`
- repeated_writes_settle_ms: `4893`
- out_of_order_reads: `0`
- repeated_writes_timeline: `[{"t_ms": 0, "event": "first write"}, {"t_ms": 2131, "event": "second write"}, {"t_ms": 9157, "event": "poll", "first": false, "second": true}, {"t_ms": 10178, "event": "poll", "first": false, "second": true}, {"t_ms": 11221, "event": "poll", "first": false, "second": true}]`

Not passed:
- SKIP live-state key freshness — no live-state key configured (ADEBENCH_LIVE_STATE_KEY)

## abstention

- questions: `12`
- leaked_entities: `0`

Not passed:
- FAIL What is the primary function of the Zoltaris module? — 5 keyword facts for something that does not exist
- FAIL Does Vornak interface with the Nexus API? — 5 keyword facts for something that does not exist
- FAIL How many Glimmox units are installed in Sector G? — 5 keyword facts for something that does not exist
- FAIL Is Brakit compatible with Lyra Scheduler? — 5 keyword facts for something that does not exist
- FAIL Who designed the Krelin processor? — episodes presented as direct matches; 4 keyword facts for something that does not exist
- FAIL When was the Duxo firmware last updated? — 5 keyword facts for something that does not exist
- FAIL Does Jalvor require access to Orion DB? — episodes presented as direct matches; 4 keyword facts for something that does not exist
- FAIL What is the encryption level of Moxie? — 5 keyword facts for something that does not exist
- FAIL Is the Plynth sensor calibrated? — 5 keyword facts for something that does not exist
- FAIL Where is the Quarx server located? — episodes presented as direct matches; 3 keyword facts for something that does not exist
- FAIL What protocol does Riften use? — episodes presented as direct matches; 4 keyword facts for something that does not exist
- FAIL Is Skalo active in the West Wing? — episodes presented as direct matches; 4 keyword facts for something that does not exist

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

- nodes: `58`
- edges: `978`
- by_type: `{"SEMANTIC:RELATED_TO": 236, "CAUSAL:LEADS_TO": 184, "TEMPORAL:PRECEDES": 57, "TEMPORAL:SUCCEEDS": 57, "TEMPORAL:TEMPORALLY_CLOSE": 41, "ENTITY:SHARED_ENTITY": 403}`
- orphan_fact_nodes: `"the graph has no fact nodes: nothing to check"`

- ⚠ section not measured: no case with evidence (all SKIP or no cases)

Not passed:
- SKIP entities with a card in the graph — no entity with a card
- SKIP orphan fact nodes = 0 — the graph has no fact nodes: nothing to check

## write_back

- degraded_answer: `"I have no record of that. You asked: {question}"`
- questions_tested: `2`
- poisoned: `2`
- cleanup_ok: `true`
- wait_s: `10`

- ⚠ 2 of 2 degraded answers written back reached the door or pushed the real answer out: the memory learns from its own bad answers

Not passed:
- FAIL In which rack is Titan Node 4 mounted? — the degraded answer reached the door after 6659 ms
- FAIL What is the current version of the Nexus API? — the degraded answer reached the door after 3725 ms

## health

- bridge: `{"loaded": true, "nodes": 58, "backend": "laya", "model": "convaiinnovations/laya", "init_s": 11.2}`
- config: `"config/laya_mem.json"`

- ⚠ no entity cards and no files: those sections are SKIP; forget is done by the adapter (node, links, vector, index), Jev-Mem has no forget of its own

## doors

- evidence: `{"calls": 80, "http_errors": 0, "ms_p50": 4210, "ms_p95": 7876, "mean_chars": 1130}`
