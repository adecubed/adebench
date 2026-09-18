# adebench — 2026-09-18T10:21:17

**Score: 90.0 / 100**
Cases: 51 PASS · 5 FAIL · 0 ERROR · 0 SKIP
Adapter `examples.synthetic:SyntheticAdapter` · door `chat` · cases `0f9a4640dc` · setup `9c559b7b5f` · sections door, cards, updates, time, live_state, abstention, file_search, graph

| Section | Weight | Points | PASS/FAIL/ERROR/SKIP |
|---|---|---|---|
| door | 25 | 18.8 | 6/2/0/0 |
| cards | 15 | 14.1 | 15/1/0/0 |
| updates | 10 | 10.0 | 3/0/0/0 |
| time | 10 | 10.0 | 6/0/0/0 |
| live_state | 10 | 10.0 | 8/0/0/0 |
| abstention | 10 | 9.2 | 3/1/0/0 |
| file_search | 10 | 10.0 | 6/0/0/0 |
| graph | 10 | 8.0 | 4/1/0/0 |
| write_back | report-only | — | 0/2/0/0 |

## door

- door: `"chat"`
- door_budget_chars: `1500`
- pressure_chars: `0`
- questions: `8`
- validated: `8`
- mean_answer_position: `174`
- mean_door_text_chars: `357`
- min_margin_chars: `1264`
- passes_within_300_chars_of_the_edge: `0`
- questions_with_forbidden_values: `1`
- stale_values_delivered: `1`
- chars_before_answer_mean: `174`
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
- probe: `true`
- probe_entity: `"zetkeobib"`
- probe_replace_ms: `0`
- probe_reads_with_both: `0`
- probe_cleanup_ok: `true`
- sandbox_test: `"4/4"`

## time

- share_of_memories_with_age: `1.0`
- facts_with_event_date: `"7/9"`
- days_tried: `["2026-09-10", "2026-09-09", "2026-09-08"]`
- signed_episodes: `1`
- signed_question: `"what did pc2 do?"`

## live_state

- live_state_age_min: `7`
- write_to_serve_ms: `1`
- write_to_serve_p50_ms: `0`
- write_to_serve_p95_ms: `1`
- write_to_serve_samples: `3`
- write_to_serve_budget_s: `30`
- overwrite_to_visible_ms: `0`
- stale_reads_after_overwrite: `0`
- repeated_writes_settle_ms: `0`
- out_of_order_reads: `0`
- repeated_writes_timeline: `[{"t_ms": 0, "event": "first write"}, {"t_ms": 0, "event": "second write"}, {"t_ms": 0, "event": "poll", "first": false, "second": true}, {"t_ms": 1002, "event": "poll", "first": false, "second": true}, {"t_ms": 2004, "event": "poll", "first": false, "second": true}]`

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

## write_back

- degraded_answer: `"I have no record of that. You asked: {question}"`
- questions_tested: `2`
- poisoned: `2`
- cleanup_ok: `true`
- wait_s: `10`

- ⚠ 2 of 2 degraded answers written back reached the door or pushed the real answer out: the memory learns from its own bad answers

Not passed:
- FAIL How many tools does the mailbox connector expose? — the degraded answer reached the door after 2 ms; the starved door did lose the answer
- FAIL When do backups run? — the degraded answer reached the door after 1 ms (before the real answer); the starved door did lose the answer

## health

- live_facts: `9`
- cards: `4`
- episodes: `4`

## doors

- /ask: `{"calls": 37, "http_errors": 0, "ms_p50": 1, "ms_p95": 1, "mean_chars": 293}`

## census

- origin: `"local"`
- generated_at: `"2026-09-13T00:00:00Z"`
- calls: `20`
- servers_called: `3`
- tool_response_bytes: `{"median": 512, "p95": 140000, "max": 140000}`
- this_door_mean_chars: `293`
- this_door_rank_in_census: `0.4`
- declared_vs_returned: `{"declared_bytes": 2200, "returned_mean_chars": 293, "returned_over_declared": 0.13}`

- ⚠ this census document carries no declared sizes (declared_bytes = 0: the local recorder does not keep tools/list yet), so declared-vs-returned has no reference
- ⚠ this door delivers 293 characters on average: larger than 40% of the 20 tool responses in the census

## pressure_profile

- levels_bytes: `{"median": 512, "p95": 140000, "max": 140000}`
- origin: `"local"`
- worst_observed_is_a_lower_bound: `true`
- median: `{"pressure_chars": 512, "PASS": 6, "FAIL": 2, "ERROR": 0, "min_margin_chars": 750}`
- p95: `{"pressure_chars": 140000, "PASS": 0, "FAIL": 8, "ERROR": 0, "min_margin_chars": null}`
- max: `{"pressure_chars": 140000, "PASS": 0, "FAIL": 8, "ERROR": 0, "min_margin_chars": null}`

- ⚠ the worst observed tool response (140000 bytes) alone exceeds this door's budget (1500): on that day the memory has no room at all
- ⚠ 'max' is the worst response observed so far, a lower bound of a bad day that moves with every census; median and p95 are the levels to compare across runs
- ⚠ 6 answers that pass on a median day are lost on a p95 day
