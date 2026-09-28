# adebench — 2026-09-28T10:48:53

**Score: 51.8 / 65 (+2.6) — coverage 65/100: 35 not measured (no evidence)**
Cases: 21 PASS · 6 FAIL · 0 ERROR · 6 SKIP
Adapter `adebench.aionforge:AionforgeAdapter` · door `search` · cases `0f9a4640dc` · setup `82c81062fb` · sections door, cards, updates, time, live_state, abstention, file_search, graph
Delta against the comparable run of 2026-09-28T10:47:29.

| Section | Weight | Points | PASS/FAIL/ERROR/SKIP |
|---|---|---|---|
| door | 25 | 18.8 (+0.0) | 6/2/0/0 |
| cards | 15 | not measured | 0/0/0/1 |
| updates | 10 | 6.7 (+0.0) | 2/1/0/0 |
| time | 10 | 8.0 (+0.0) | 4/1/0/1 |
| live_state | 10 | 10.0 (+2.5) | 7/0/0/1 |
| abstention | 10 | 8.3 (+0.0) | 2/2/0/0 |
| file_search | 10 | not measured | 0/0/0/1 |
| graph | 10 | not measured | 0/0/0/2 |
| write_back | report-only | — | 0/2/0/0 |

## door

- door: `"search"`
- door_budget_chars: `null`
- pressure_chars: `0`
- questions: `8`
- validated: `8`
- mean_answer_position: `140`
- mean_door_text_chars: `419`
- min_margin_chars: `null`
- passes_within_300_chars_of_the_edge: `0`
- questions_with_forbidden_values: `1`
- stale_values_delivered: `1`
- chars_before_answer_mean: `140`
- duplicate_chunks_total: `0`

- ⚠ 1 answers delivered a retired value next to the current one: the model has to guess which is true

Not passed:
- FAIL Which version of MailBridge is installed for the mailbox? — STALE value delivered next to the current one: 1.3.0
- FAIL What is the owner's phone number? — missing +39

## cards

- ⚠ section not measured: no entity cards in this memory

Not passed:
- SKIP entity cards — this memory has none

## updates

- census: `[{"kinds": {"bad_patterns": 0, "entities": 0, "episodes": 0, "facts": 0, "notes": 0, "skills": 0}, "namespace": "global", "total": 0, "work_statuses": {"blocked": 0, "done": 0, "dropped": 0, "in_progress": 0, "todo": 0}}, {"kinds": {"bad_patterns": 0, "entities": 4, "episodes": 25, "facts": 2, "notes": 0, "skills": 0}, "namespace": "agent:0b6f3f7e-5d5c-4e1a-9d3e-00000adeb001", "total": 31, "work_statuses": {"blocked": 0, "done": 0, "dropped": 0, "in_progress": 0, "todo": 0}}]`
- superseded_live: `0`
- probe: `true`
- probe_entity: `"zetdmhhjo"`
- probe_replace_ms: `427`
- probe_reads_with_both: `23`
- probe_cleanup_ok: `true`

- ⚠ no trace of updates in live memory: the dedup has not worked yet or found no pairs

Not passed:
- FAIL a new write with a changed value replaces the old one at the door (no id given) — new value served in 427 ms; STALE: the old value is still delivered (23 reads with both)

## time

- share_of_memories_with_age: `0.891`
- facts_with_event_date: `"25/25"`
- days_tried: `["2026-09-28", "2026-09-10", "2026-09-09"]`
- signed_episodes: `0`
- signed_question: `"what did pc2 do?"`

Not passed:
- FAIL semantic memories carry their age (41/46) — 89%
- SKIP episodes signed by another machine — none in this memory

## live_state

- live_state_age_min: `null`
- write_to_serve_ms: `483`
- write_to_serve_p50_ms: `452`
- write_to_serve_p95_ms: `483`
- write_to_serve_samples: `3`
- write_to_serve_budget_s: `30`
- overwrite_to_visible_ms: `455`
- stale_reads_after_overwrite: `0`
- repeated_writes_settle_ms: `427`
- out_of_order_reads: `0`
- repeated_writes_timeline: `[{"t_ms": 0, "event": "first write"}, {"t_ms": 466, "event": "second write"}, {"t_ms": 1388, "event": "poll", "first": false, "second": true}, {"t_ms": 2740, "event": "poll", "first": false, "second": true}, {"t_ms": 4085, "event": "poll", "first": false, "second": true}]`

Not passed:
- SKIP live-state key freshness — no live-state key configured (ADEBENCH_LIVE_STATE_KEY)

## abstention

- questions: `4`

Not passed:
- FAIL Which port does the Fulmicotone service use? — 1 keyword facts for something that does not exist
- FAIL What does the calendar plugin Girandola do? — 4 keyword facts for something that does not exist

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
- poisoned: `2`
- cleanup_ok: `true`
- wait_s: `10`

- ⚠ 2 of 2 degraded answers written back reached the door or pushed the real answer out: the memory learns from its own bad answers

Not passed:
- FAIL How many tools does the mailbox connector expose? — the degraded answer reached the door after 420 ms (before the real answer)
- FAIL When do backups run? — the degraded answer reached the door after 443 ms (before the real answer)

## health

- status: `{"auth": {"enabled": false, "issuers": []}, "build": {"build_status": "clean", "built_at": "2026-07-10T23:42:34-04:00", "sha": "de7fb2350925"}, "counts": {"kinds": {"bad_patterns": 0, "entities": 4, "episodes": 25, "facts": 2, "notes": 0, "skills": 0}, "memories": 31, "work_items": 0, "work_statuses": {"blocked": 0, "done": 0, "dropped": 0, "in_progress": 0, "todo": 0}}, "recall_wrapper": "recalled-memory-context", "resources": ["aionforge://manifest/tools.json", "aionforge://guide/mcp-surface", "aionforge://policy/tool-approval"], "sampling": false, "schema": "aionforge.server_status.v1", "surface": {"mutating_tools": ["capture", "batch_capture", "message_send", "message_ack", "consolidate", "forget", "unforget", "pin", "unpin", "work_create", "work_advance", "work_link"], "prompts": 1, "read_like_tools": ["server_status", "search", "read_memory", "session_manifest", "message_poll", "message_wait", "memory_census", "consolidation_status", "audit_history", "work_tree", "work_query"], "resources": 10, "tools": 23}, "telemetry": {"memory_traffic": {"bytes_in_total": 4000, "bytes_out_total": 1093237, "estimated_tokens_in_total": 1000, "estimated_tokens_out_total": 273309, "token_estimate_divisor": 4, "token_estimate_kind": "coarse_bytes_divisor"}}, "transports": ["stdio", "streamable_http"], "version": "0.4.0"}`
- consolidation: `{"failed": 0, "generation": 393, "oldest_pending_age_s": 0, "pending": 0, "schema": "aionforge.consolidation_status.v1", "state": "idle"}`

- ⚠ cards, files and graph edges are not exposed by the MCP surface: those sections are SKIP

## doors

- search: `{"calls": 52, "http_errors": 0, "ms_p50": 364, "ms_p95": 398, "mean_chars": 2052}`
