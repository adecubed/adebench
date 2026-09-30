# adebench — 2026-09-30T10:11:16

**Score: 48.1 / 65 (+0.0) — coverage 65/100: 35 not measured (no evidence)**
Cases: 20 PASS · 8 FAIL · 0 ERROR · 5 SKIP
Adapter `adebench.supermemory:SupermemoryAdapter` · door `memories` · cases `0f9a4640dc` · setup `e37cca2b5e` · sections door, cards, updates, time, live_state, abstention, file_search, graph
Delta against the comparable run of 2026-09-30T10:03:50.

| Section | Weight | Points | PASS/FAIL/ERROR/SKIP |
|---|---|---|---|
| door | 25 | 15.6 (+0.0) | 5/3/0/0 |
| cards | 15 | not measured | 0/0/0/1 |
| updates | 10 | 10.0 (+0.0) | 3/0/0/0 |
| time | 10 | 5.0 (+0.0) | 3/3/0/0 |
| live_state | 10 | 10.0 (+0.0) | 7/0/0/1 |
| abstention | 10 | 7.5 (+0.0) | 2/2/0/0 |
| file_search | 10 | not measured | 0/0/0/1 |
| graph | 10 | not measured | 0/0/0/2 |
| write_back | report-only | — | 2/0/0/0 |

## door

- door: `"memories"`
- door_budget_chars: `null`
- pressure_chars: `0`
- questions: `8`
- validated: `8`
- mean_answer_position: `81`
- mean_door_text_chars: `364`
- min_margin_chars: `null`
- passes_within_300_chars_of_the_edge: `0`
- questions_with_forbidden_values: `1`
- stale_values_delivered: `1`
- chars_before_answer_mean: `81`
- duplicate_chunks_total: `0`

- ⚠ 1 answers delivered a retired value next to the current one: the model has to guess which is true

Not passed:
- FAIL Which version of MailBridge is installed for the mailbox? — STALE value delivered next to the current one: 1.3.0
- FAIL Where does the owner live? — missing Turin
- FAIL What is the owner's phone number? — missing +39

## cards

- ⚠ section not measured: no entity cards in this memory

Not passed:
- SKIP entity cards — this memory has none

## updates

- memories_latest: `31`
- memories_forgotten: `null`
- superseded_live: `null`
- relation_updates: `7`
- history_versions: `7`
- static: `0`
- probe: `true`
- probe_entity: `"zetdbfjcp"`
- probe_replace_ms: `2094`
- probe_reads_with_both: `0`
- probe_cleanup_ok: `true`

## time

- share_of_memories_with_age: `0.822`
- facts_with_event_date: `"26/31"`
- days_tried: `["2026-09-10", "2026-09-09", "2026-09-08"]`
- signed_episodes: `1`
- signed_question: `"what did pc2 do?"`

Not passed:
- FAIL semantic memories carry their age (37/45) — 82%
- FAIL an imported memory reaches the door with its original date — imported memory not served within 30 s
- FAIL «what did pc2 do?» finds the episodes signed [pc2] — 0 episodes in the answer

## live_state

- live_state_age_min: `null`
- write_to_serve_ms: `2080`
- write_to_serve_p50_ms: `2080`
- write_to_serve_p95_ms: `2104`
- write_to_serve_samples: `3`
- write_to_serve_budget_s: `30`
- overwrite_to_visible_ms: `2112`
- stale_reads_after_overwrite: `0`
- repeated_writes_settle_ms: `2086`
- out_of_order_reads: `0`
- repeated_writes_timeline: `[{"t_ms": 0, "event": "first write"}, {"t_ms": 4167, "event": "second write"}, {"t_ms": 10450, "event": "poll", "first": false, "second": true}, {"t_ms": 13544, "event": "poll", "first": false, "second": true}, {"t_ms": 16630, "event": "poll", "first": false, "second": true}]`

Not passed:
- SKIP live-state key freshness — no live-state key configured (ADEBENCH_LIVE_STATE_KEY)

## abstention

- questions: `4`

Not passed:
- FAIL Which port does the Fulmicotone service use? — 3 keyword facts for something that does not exist
- FAIL What does the calendar plugin Girandola do? — episodes presented as direct matches; 6 keyword facts for something that does not exist

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

- setup: `{"server": "supermemory-server 0.0.8", "llm": "gemini-3.1-flash-lite-preview (native Gemini provider, fixed by the binary)", "embeddings": "Xenova/bge-base-en-v1.5, local, 768d (the self-hosted default)"}`
- container: `"adebench"`
- documents: `21`
- documents_by_status: `{"done": 21}`
- memories_latest: `31`
- memories_forgotten: `null`
- superseded_live: `null`
- relation_updates: `7`
- history_versions: `7`
- static: `0`
- settle_waits_s: `[2.1, 6.1, 6.1, 6.1, 6.1, 6.1, 6.1]`
- settle_wait_p50_s: `6.1`
- live_state_writes: `{"written": 6, "hard_deleted": 6, "soft_forgotten": 0, "failed": 0, "residue": 0}`
- update_trace_note: `"memories_forgotten and superseded_live are not observable: the list endpoint returns only the latest, non-forgotten entries"`

- ⚠ every write_fact/ingest_exchange/import waited for extraction before the door was asked (settle): p50 6.1 s, max 6.1 s. The serve times in the updates and write-back sections start after that wait
- ⚠ cards, files and graph edges are not exposed by the API: those sections are SKIP

## doors

- POST /v4/search: `{"calls": 52, "http_errors": 0, "ms_p50": 2103, "ms_p95": 2160, "mean_chars": 2690}`
- POST /v4/profile: `{"calls": 3, "http_errors": 0, "ms_p50": 2113, "ms_p95": 2150, "mean_chars": 12119}`
