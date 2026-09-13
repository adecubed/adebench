# adebench — 2026-09-13T10:19:42

**Score: 90.0 / 100**
Cases: 50 PASS · 5 FAIL · 0 ERROR · 0 SKIP
Adapter `examples.synthetic:SyntheticAdapter` · door `chat` · cases `0f9a4640dc` · setup `ff086bb57c` · sections door, cards, updates, time, live_state, abstention, file_search, graph

| Section | Weight | Points | PASS/FAIL/ERROR/SKIP |
|---|---|---|---|
| door | 25 | 18.8 | 6/2/0/0 |
| cards | 15 | 14.1 | 15/1/0/0 |
| updates | 10 | 10.0 | 4/0/0/0 |
| time | 10 | 10.0 | 5/0/0/0 |
| live_state | 10 | 10.0 | 7/0/0/0 |
| abstention | 10 | 9.2 | 3/1/0/0 |
| file_search | 10 | 10.0 | 6/0/0/0 |
| graph | 10 | 8.0 | 4/1/0/0 |

## door

- door: `"chat"`
- door_budget_chars: `1500`
- pressure_chars: `0`
- questions: `8`
- validated: `8`
- mean_answer_position: `212`
- mean_door_text_chars: `357`
- min_margin_chars: `1187`
- passes_within_300_chars_of_the_edge: `0`
- questions_with_forbidden_values: `1`
- stale_values_delivered: `1`
- chars_before_answer_mean: `212`
- duplicate_chunks_total: `0`

- ⚠ 1 answers delivered a retired value next to the current one: the model has to guess which is true

Not passed:
- FAIL Which version of MailBridge is installed for the mailbox? — STALE value delivered next to the current one: 1.3.0
- FAIL What is the owner's phone number? — missing +39

## cards

- cards: `4`
- corrections: `2`
- aliases: `3`
- aliases_tried: `3`

Not passed:
- FAIL card calendar contains «shared with the team»

## updates

- superseded_live: `1`
- relation_updates: `1`
- archive_by_reason: `{"supersede": 1}`
- v2_share: `1.0`
- sandbox_test: `"4/4"`

## time

- share_of_memories_with_age: `1.0`
- facts_with_event_date: `"8/10"`
- days_tried: `["2026-09-10", "2026-09-09", "2026-09-08"]`
- signed_episodes_pc2: `1`

## live_state

- live_state_age_min: `7`
- write_to_serve_ms: `0`
- write_to_serve_p50_ms: `0`
- write_to_serve_p95_ms: `0`
- write_to_serve_samples: `3`
- write_to_serve_budget_s: `30`
- overwrite_to_visible_ms: `0`
- stale_reads_after_overwrite: `0`

## abstention

- questions: `4`

Not passed:
- FAIL What does the calendar plugin Girandola do? — produced an entity card; flagged unknown: ['girandola', 'plugin']

## file_search

- indexable_functions: `6`
- tried: `6`

## graph

- nodes: `14`
- edges: `9`
- orphan_fact_nodes: `"0 orphans out of 10"`

Not passed:
- FAIL mailbox: edges in the graph — 0 edges

## health

- live_facts: `10`
- cards: `4`
- episodes: `4`

## doors

- /ask: `{"calls": 20, "http_errors": 0, "ms_p50": 1, "ms_p95": 1, "mean_chars": 299}`

## census

- origin: `"local"`
- generated_at: `"2026-09-13T00:00:00Z"`
- calls: `20`
- servers_called: `3`
- tool_response_bytes: `{"median": 512, "p95": 140000, "max": 140000}`
- this_door_mean_chars: `299`
- this_door_rank_in_census: `0.4`
- declared_vs_returned: `{"declared_bytes": 2200, "returned_mean_chars": 299, "returned_over_declared": 0.14}`

- ⚠ this census document carries no declared sizes (declared_bytes = 0: the local recorder does not keep tools/list yet), so declared-vs-returned has no reference
- ⚠ this door delivers 299 characters on average: larger than 40% of the 20 tool responses in the census

## pressure_profile

- levels_bytes: `{"median": 512, "p95": 140000, "max": 140000}`
- origin: `"local"`
- median: `{"pressure_chars": 512, "PASS": 6, "FAIL": 2, "ERROR": 0, "min_margin_chars": 673}`
- p95: `{"pressure_chars": 140000, "PASS": 0, "FAIL": 8, "ERROR": 0, "min_margin_chars": null}`
- max: `{"pressure_chars": 140000, "PASS": 0, "FAIL": 8, "ERROR": 0, "min_margin_chars": null}`

- ⚠ the worst observed tool response (140000 bytes) alone exceeds this door's budget (1500): on that day the memory has no room at all
- ⚠ 6 answers that pass on a median day are lost on a p95 day
