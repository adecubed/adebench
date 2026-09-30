# adebench — 2026-09-30T09:58:30

**Score: 42.6 / 65 — coverage 65/100: 35 not measured (no evidence)**
Cases: 17 PASS · 11 FAIL · 0 ERROR · 5 SKIP
Adapter `adebench.agentmemory:AgentmemoryAdapter` · door `recall` · cases `0f9a4640dc` · setup `34483ae0a3` · sections door, cards, updates, time, live_state, abstention, file_search, graph

| Section | Weight | Points | PASS/FAIL/ERROR/SKIP |
|---|---|---|---|
| door | 25 | 18.8 | 6/2/0/0 |
| cards | 15 | not measured | 0/0/0/1 |
| updates | 10 | 6.7 | 2/1/0/0 |
| time | 10 | 6.7 | 4/2/0/0 |
| live_state | 10 | 7.1 | 5/2/0/1 |
| abstention | 10 | 3.3 | 0/4/0/0 |
| file_search | 10 | not measured | 0/0/0/1 |
| graph | 10 | not measured | 0/0/0/2 |
| write_back | report-only | — | 0/0/0/1 |

## door

- door: `"recall"`
- door_budget_chars: `null`
- pressure_chars: `0`
- questions: `8`
- validated: `8`
- mean_answer_position: `271`
- mean_door_text_chars: `6426`
- min_margin_chars: `null`
- passes_within_300_chars_of_the_edge: `0`
- questions_with_forbidden_values: `1`
- stale_values_delivered: `1`
- chars_before_answer_mean: `271`
- duplicate_chunks_total: `5`

- ⚠ 5 repeated chunks across the delivered texts: budget spent twice on the same information
- ⚠ 1 answers delivered a retired value next to the current one: the model has to guess which is true

Not passed:
- FAIL Which version of MailBridge is installed for the mailbox? — STALE value delivered next to the current one: 1.3.0
- FAIL What is the owner's phone number? — missing +39

## cards

- ⚠ section not measured: no entity cards in this memory

Not passed:
- SKIP entity cards — this memory has none

## updates

- memories: `17`
- superseded_live: `0`
- relation_updates: `0`
- probe: `true`
- probe_entity: `"zetedcgic"`
- probe_replace_ms: `33`
- probe_reads_with_both: `0`
- probe_cleanup_ok: `true`

- ⚠ no trace of updates in live memory: the dedup has not worked yet or found no pairs

Not passed:
- FAIL restating the current value does not pile up a second copy — 3 copies delivered

## time

- share_of_memories_with_age: `0.75`
- facts_with_event_date: `"12/17"`
- days_tried: `["2026-09-10", "2026-09-09", "2026-09-08"]`
- signed_episodes: `1`
- signed_question: `"what did pc2 do?"`

Not passed:
- FAIL semantic memories carry their age (39/52) — 75%
- FAIL an imported memory reaches the door with its original date — served with no date

## live_state

- live_state_age_min: `null`
- write_to_serve_ms: `15`
- write_to_serve_p50_ms: `15`
- write_to_serve_p95_ms: `27`
- write_to_serve_samples: `3`
- write_to_serve_budget_s: `30`
- overwrite_to_visible_ms: `41`
- stale_reads_after_overwrite: `0`
- repeated_writes_settle_ms: `55`
- out_of_order_reads: `29`
- repeated_writes_timeline: `[{"t_ms": 0, "event": "first write"}, {"t_ms": 11, "event": "second write"}, {"t_ms": 75, "event": "poll", "first": true, "second": true}, {"t_ms": 1127, "event": "poll", "first": true, "second": true}, {"t_ms": 2136, "event": "poll", "first": true, "second": true}, {"t_ms": 3161, "event": "poll", "first": true, "second": true}, {"t_ms": 4197, "event": "poll", "first": true, "second": true}, {"t_ms": 5255, "event": "poll", "first": true, "second": true}, {"t_ms": 6288, "event": "poll", "first": true, "second": true}, {"t_ms": 7321, "event": "poll", "first": true, "second": true}, {"t_ms": 8359, "event": "poll", "first": true, "second": true}, {"t_ms": 9397, "event": "poll", "first": true, "second": true}, {"t_ms": 10423, "event": "poll", "first": true, "second": true}, {"t_ms": 11449, "event": "poll", "first": true, "second": true}, {"t_ms": 12487, "event": "poll", "first": true, "second": true}, {"t_ms": 13496, "event": "poll", "first": true, "second": true}, {"t_ms": 14519, "event": "poll", "first": true, "second": true}, {"t_ms": 15548, "event": "poll", "first": true, "second": true}, {"t_ms": 16614, "event": "poll", "first": true, "second": true}, {"t_ms": 17682, "event": "poll", "first": true, "second": true}, {"t_ms": 18708, "event": "poll", "first": true, "second": true}, {"t_ms": 19765, "event": "poll", "first": true, "second": true}, {"t_ms": 20811, "event": "poll", "first": true, "second": true}, {"t_ms": 21893, "event": "poll", "first": true, "second": true}, {"t_ms": 22942, "event": "poll", "first": true, "second": true}, {"t_ms": 23969, "event": "poll", "first": true, "second": true}, {"t_ms": 25053, "event": "poll", "first": true, "second": true}, {"t_ms": 26094, "event": "poll", "first": true, "second": true}, {"t_ms": 27164, "event": "poll", "first": true, "second": true}, {"t_ms": 28176, "event": "poll", "first": true, "second": true}, {"t_ms": 29233, "event": "poll", "first": true, "second": true}, {"t_ms": 30297, "event": "poll", "first": true, "second": true}]`

Not passed:
- FAIL after overwriting the canary the door serves the new value, never the old one — overwrite-to-visible 41 ms · STALE: old and new value delivered together
- FAIL two writes in quick succession: the door settles on the second, never back on the first — second write visible in 55 ms · 29 read(s) served the first write after the second was already visible
- SKIP live-state key freshness — no live-state key configured (ADEBENCH_LIVE_STATE_KEY)

## abstention

- questions: `4`

Not passed:
- FAIL What is the Zarpetta module? — episodes presented as direct matches; 7 keyword facts for something that does not exist
- FAIL Who is Ottavio Brambillesco? — episodes presented as direct matches; 6 keyword facts for something that does not exist
- FAIL Which port does the Fulmicotone service use? — episodes presented as direct matches; 7 keyword facts for something that does not exist
- FAIL What does the calendar plugin Girandola do? — episodes presented as direct matches; 7 keyword facts for something that does not exist

## file_search

- ⚠ section not measured: no repo configured (--repo)

Not passed:
- SKIP file search — no repo configured (--repo)

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
- alerts: `["cpu_critical_184%"]`
- notes: `["memory_heap_tight_85%_rss170mb"]`
- llm_provider: `"noop"`
- embedding_provider: `"embeddings"`
- flags_enabled: `[]`
- memories: `17`
- memories_latest: `17`

- ⚠ /health answered HTTP 503 status critical: ['cpu_critical_184%'] (its monitor averages CPU over 30 s)
- ⚠ no entity cards, file search or graph (extraction needs an LLM): those sections are SKIP
- ⚠ keyless mode: an assistant reply is dropped by the model-free compression, so episodes keep only the user's prompt

## doors

- memory_recall: `{"calls": 56, "http_errors": 0, "ms_p50": 29, "ms_p95": 69, "mean_chars": 6992}`
- memory_smart_search: `{"calls": 8, "http_errors": 0, "ms_p50": 22, "ms_p95": 31, "mean_chars": 2972}`
