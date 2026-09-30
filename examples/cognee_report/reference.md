# adebench — 2026-09-30T10:17:53

**Score: 43.7 / 65 — coverage 65/100: 35 not measured (no evidence)**
Cases: 19 PASS · 9 FAIL · 0 ERROR · 5 SKIP
Adapter `adebench.cognee:CogneeAdapter` · door `context` · cases `0f9a4640dc` · setup `9c9c8684e6` · sections door, cards, updates, time, live_state, abstention, file_search, graph

| Section | Weight | Points | PASS/FAIL/ERROR/SKIP |
|---|---|---|---|
| door | 25 | 18.8 | 6/2/0/0 |
| cards | 15 | not measured | 0/0/0/1 |
| updates | 10 | 3.3 | 1/2/0/0 |
| time | 10 | 8.3 | 5/1/0/0 |
| live_state | 10 | 10.0 | 7/0/0/1 |
| abstention | 10 | 3.3 | 0/4/0/0 |
| file_search | 10 | not measured | 0/0/0/1 |
| graph | 10 | not measured | 0/0/0/2 |
| write_back | report-only | — | 0/2/0/0 |

## door

- door: `"context"`
- door_budget_chars: `null`
- pressure_chars: `0`
- questions: `8`
- validated: `8`
- mean_answer_position: `294`
- mean_door_text_chars: `4725`
- min_margin_chars: `null`
- passes_within_300_chars_of_the_edge: `0`
- questions_with_forbidden_values: `1`
- stale_values_delivered: `1`
- chars_before_answer_mean: `294`
- duplicate_chunks_total: `51`

- ⚠ 51 repeated chunks across the delivered texts: budget spent twice on the same information
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
- edges_by_relationship: `{"made_from": 21, "is_part_of": 21, "contains": 61, "is_a": 51, "prefers": 1, "synonym_of": 1, "is_based_in": 1, "destination_is": 1, "commutes_by": 2, "travel_mode": 1, "updated_on": 3, "replaced": 1, "replaced_on": 1, "is_synonymous_with": 1, "served_by": 1, "installed_in": 1, "synced_cache": 1, "refreshed_cache": 1, "distills": 1, "scheduled_on": 2, "scheduled_at": 2, "is_memory_service_of": 1, "departure_time": 1, "return_time": 1, "listens_on": 1, "has_memory_level": 3}`
- probe: `true`
- probe_entity: `"zetgfdlnb"`
- probe_replace_ms: `1056`
- probe_reads_with_both: `14`
- probe_cleanup_ok: `true`

- ⚠ no trace of updates in live memory: the dedup has not worked yet or found no pairs

Not passed:
- FAIL a new write with a changed value replaces the old one at the door (no id given) — new value served in 1056 ms; STALE: the old value is still delivered (14 reads with both)
- FAIL restating the current value does not pile up a second copy — 3 copies delivered

## time

- share_of_memories_with_age: `0.803`
- facts_with_event_date: `"16/21"`
- days_tried: `["2026-09-10", "2026-09-09", "2026-09-08"]`
- signed_episodes: `1`
- signed_question: `"what did pc2 do?"`

Not passed:
- FAIL semantic memories carry their age (53/66) — 80%

## live_state

- live_state_age_min: `null`
- write_to_serve_ms: `883`
- write_to_serve_p50_ms: `883`
- write_to_serve_p95_ms: `926`
- write_to_serve_samples: `3`
- write_to_serve_budget_s: `30`
- overwrite_to_visible_ms: `905`
- stale_reads_after_overwrite: `0`
- repeated_writes_settle_ms: `956`
- out_of_order_reads: `0`
- repeated_writes_timeline: `[{"t_ms": 0, "event": "first write"}, {"t_ms": 620465, "event": "second write"}, {"t_ms": 635622, "event": "poll", "first": false, "second": true}, {"t_ms": 637370, "event": "poll", "first": false, "second": true}, {"t_ms": 639225, "event": "poll", "first": false, "second": true}]`

Not passed:
- SKIP live-state key freshness — no live-state key configured (ADEBENCH_LIVE_STATE_KEY)

## abstention

- questions: `4`

Not passed:
- FAIL What is the Zarpetta module? — episodes presented as direct matches; 9 keyword facts for something that does not exist
- FAIL Who is Ottavio Brambillesco? — episodes presented as direct matches; 8 keyword facts for something that does not exist
- FAIL Which port does the Fulmicotone service use? — episodes presented as direct matches; 8 keyword facts for something that does not exist
- FAIL What does the calendar plugin Girandola do? — episodes presented as direct matches; 9 keyword facts for something that does not exist

## file_search

- ⚠ section not measured: no repo configured (--repo)

Not passed:
- SKIP file search — no repo configured (--repo)

## graph

- nodes: `133`
- edges: `183`
- nodes_by_type: `{"TextSummary": 21, "DocumentChunk": 21, "TextDocument": 21, "Entity": 43, "EntityType": 27}`
- edges_by_relationship: `{"made_from": 21, "is_part_of": 21, "contains": 61, "is_a": 51, "prefers": 1, "synonym_of": 1, "is_based_in": 1, "destination_is": 1, "commutes_by": 2, "travel_mode": 1, "updated_on": 3, "replaced": 1, "replaced_on": 1, "is_synonymous_with": 1, "served_by": 1, "installed_in": 1, "synced_cache": 1, "refreshed_cache": 1, "distills": 1, "scheduled_on": 2, "scheduled_at": 2, "is_memory_service_of": 1, "departure_time": 1, "return_time": 1, "listens_on": 1, "has_memory_level": 3}`
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
- FAIL How many tools does the mailbox connector expose? — the degraded answer reached the door after 898 ms (before the real answer)
- FAIL When do backups run? — the degraded answer reached the door after 841 ms (before the real answer)

## health

- bridge: `{"cognee_version": "1.6.1", "mode": "gemini", "llm": "gemini:gemini/gemini-3-flash-preview", "store": "adebench_store_gemini", "dataset": "adebench", "extractor": "llm", "embedding": "gemini:gemini/gemini-embedding-001 (768 dims)", "init_s": 6.8, "vector_db": "lancedb", "graph_db": "ladybug"}`
- search_types_seen: `{"HYBRID_COMPLETION": 43}`
- setup: `{"llm": "gemini:gemini/gemini-3-flash-preview", "extractor": "llm", "embedding": "gemini:gemini/gemini-embedding-001 (768 dims)", "context_door": "cognee.recall, no query_type (cognee's routing), only_context=True, retriever_specific_config={include_external_metadata: true, external_metadata_keys: [date]} (non-default: puts each passage's date in the context), a fresh session_id per call", "answer_door": "the same call without only_context: the LLM's answer", "chunks_door": "query_type=CHUNKS, top_k=15"}`
- llm_usage_this_run: `{"aembedding:gemini-embedding-001": {"calls": 161, "prompt_tokens": 4730, "completion_tokens": 0}, "acompletion:gemini-3-flash-preview": {"calls": 25, "prompt_tokens": 10133, "completion_tokens": 48482}}`
- health: `{"status": "healthy", "components": {"relational_db": {"status": "healthy", "details": "Connection successful"}, "vector_db": {"status": "healthy", "details": "Index accessible"}, "graph_db": {"status": "healthy", "details": "Schema validated"}, "file_storage": {"status": "healthy", "details": "Storage accessible"}}}`

- ⚠ no entity cards and no files: those sections are SKIP; cognee's chunk retrieval is a vector search with no relevance floor: it always returns its top_k hits

## doors

- context: `{"calls": 43, "http_errors": 0, "ms_p50": 841, "ms_p95": 2189, "mean_chars": 4610}`
- answer: `{"calls": 8, "http_errors": 0, "ms_p50": 2916, "ms_p95": 3441, "mean_chars": 18}`
- chunks: `{"calls": 8, "http_errors": 0, "ms_p50": 413, "ms_p95": 455, "mean_chars": 993}`
