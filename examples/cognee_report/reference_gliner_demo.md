# adebench — 2026-09-29T17:48:11

**Score: 48.8 / 65 — coverage 65/100: 35 not measured (no evidence)**
Cases: 21 PASS · 7 FAIL · 0 ERROR · 5 SKIP
Adapter `adebench.cognee:CogneeAdapter` · door `recall` · cases `0f9a4640dc` · setup `3ca4c3224b` · sections door, cards, updates, time, live_state, abstention, file_search, graph

| Section | Weight | Points | PASS/FAIL/ERROR/SKIP |
|---|---|---|---|
| door | 25 | 18.8 | 6/2/0/0 |
| cards | 15 | not measured | 0/0/0/1 |
| updates | 10 | 6.7 | 2/1/0/0 |
| time | 10 | 10.0 | 6/0/0/0 |
| live_state | 10 | 10.0 | 7/0/0/1 |
| abstention | 10 | 3.3 | 0/4/0/0 |
| file_search | 10 | not measured | 0/0/0/1 |
| graph | 10 | not measured | 0/0/0/2 |
| write_back | report-only | — | 0/2/0/0 |

## door

- door: `"recall"`
- door_budget_chars: `null`
- pressure_chars: `0`
- questions: `8`
- validated: `8`
- mean_answer_position: `86`
- mean_door_text_chars: `1332`
- min_margin_chars: `null`
- passes_within_300_chars_of_the_edge: `0`
- questions_with_forbidden_values: `1`
- stale_values_delivered: `1`
- chars_before_answer_mean: `86`
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

- superseded_live: `0`
- relation_updates: `0`
- edges_by_relationship: `{"made_from": 21, "is_part_of": 21, "contains": 42, "is_a": 33, "located_in": 3, "owns": 1, "uses": 3, "born_in": 1, "headquartered_in": 1}`
- probe: `true`
- probe_entity: `"zetnklkeh"`
- probe_replace_ms: `481`
- probe_reads_with_both: `25`
- probe_cleanup_ok: `true`

- ⚠ no trace of updates in live memory: the dedup has not worked yet or found no pairs

Not passed:
- FAIL a new write with a changed value replaces the old one at the door (no id given) — new value served in 481 ms; STALE: the old value is still delivered (25 reads with both)

## time

- share_of_memories_with_age: `1.0`
- facts_with_event_date: `"16/21"`
- days_tried: `["2026-09-10", "2026-09-09", "2026-09-08"]`
- signed_episodes: `1`
- signed_question: `"what did pc2 do?"`

## live_state

- live_state_age_min: `null`
- write_to_serve_ms: `188`
- write_to_serve_p50_ms: `295`
- write_to_serve_p95_ms: `331`
- write_to_serve_samples: `3`
- write_to_serve_budget_s: `30`
- overwrite_to_visible_ms: `378`
- stale_reads_after_overwrite: `0`
- repeated_writes_settle_ms: `338`
- out_of_order_reads: `0`
- repeated_writes_timeline: `[{"t_ms": 0, "event": "first write"}, {"t_ms": 3867, "event": "second write"}, {"t_ms": 9754, "event": "poll", "first": false, "second": true}, {"t_ms": 11026, "event": "poll", "first": false, "second": true}, {"t_ms": 12315, "event": "poll", "first": false, "second": true}]`

Not passed:
- SKIP live-state key freshness — no live-state key configured (ADEBENCH_LIVE_STATE_KEY)

## abstention

- questions: `4`

Not passed:
- FAIL What is the Zarpetta module? — episodes presented as direct matches; 11 keyword facts for something that does not exist
- FAIL Who is Ottavio Brambillesco? — episodes presented as direct matches; 12 keyword facts for something that does not exist
- FAIL Which port does the Fulmicotone service use? — episodes presented as direct matches; 11 keyword facts for something that does not exist
- FAIL What does the calendar plugin Girandola do? — episodes presented as direct matches; 11 keyword facts for something that does not exist

## file_search

- ⚠ section not measured: no repo configured (--repo)

Not passed:
- SKIP file search — no repo configured (--repo)

## graph

- nodes: `106`
- edges: `126`
- nodes_by_type: `{"TextSummary": 21, "DocumentChunk": 21, "TextDocument": 21, "Entity": 30, "EntityType": 13}`
- edges_by_relationship: `{"made_from": 21, "is_part_of": 21, "contains": 42, "is_a": 33, "located_in": 3, "owns": 1, "uses": 3, "born_in": 1, "headquartered_in": 1}`
- entities_without_edges: `0`
- data_items: `21`
- orphan_fact_nodes: `"0 orphans out of 21 (not scored: with no entity edges to check, one count does not measure the graph)"`

- ⚠ section not measured: no case with evidence (all SKIP or no cases)

Not passed:
- SKIP entities with a card in the graph — no entity with a card
- SKIP orphan fact nodes = 0 — 0 orphans out of 21 (not scored: with no entity edges to check, one count does not measure the graph)

## write_back

- degraded_answer: `"I have no record of that. You asked: {question}"`
- questions_tested: `2`
- poisoned: `2`
- cleanup_ok: `true`
- wait_s: `10`

- ⚠ 2 of 2 degraded answers written back reached the door or pushed the real answer out: the memory learns from its own bad answers

Not passed:
- FAIL How many tools does the mailbox connector expose? — the degraded answer reached the door after 421 ms
- FAIL When do backups run? — the degraded answer reached the door after 317 ms (before the real answer)

## health

- bridge: `{"cognee_version": "1.6.1", "store": "adebench_store", "dataset": "adebench", "extractor": "gliner_demo", "embedding": "fastembed:BAAI/bge-small-en-v1.5 (384 dims)", "init_s": 7.5, "vector_db": "lancedb", "graph_db": "ladybug"}`
- top_k: `15`
- search_types_seen: `{"CHUNKS": 810}`
- health: `{"status": "healthy", "components": {"relational_db": {"status": "healthy", "details": "Connection successful"}, "vector_db": {"status": "healthy", "details": "Index accessible"}, "graph_db": {"status": "healthy", "details": "Schema validated"}, "file_storage": {"status": "healthy", "details": "Storage accessible"}}}`

- ⚠ no entity cards and no files: those sections are SKIP; cognee's keyless recall is a vector search over chunks with no relevance floor: it always returns top_k hits

## doors

- recall: `{"calls": 54, "http_errors": 0, "ms_p50": 272, "ms_p95": 429, "mean_chars": 1085}`
- graph_context: `{"calls": 8, "http_errors": 0, "ms_p50": 457, "ms_p95": 510, "mean_chars": 5230}`
