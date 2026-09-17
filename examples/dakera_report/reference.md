# adebench — 2026-09-17T15:25:09

**Score: 84.9 / 90 — coverage 90/100: 10 not measured (no evidence)**
Cases: 49 PASS · 2 FAIL · 0 ERROR · 2 SKIP
Adapter `adebench.dakera:DakeraAdapter` · door `chat` · cases `0f9a4640dc` · setup `7a536028fa` · sections door, cards, updates, time, live_state, abstention, file_search, graph

| Section | Weight | Points | PASS/FAIL/ERROR/SKIP |
|---|---|---|---|
| door | 25 | 21.9 | 7/1/0/0 |
| cards | 15 | 15.0 | 16/0/0/0 |
| updates | 10 | not measured | 0/0/0/1 |
| time | 10 | 8.0 | 4/1/0/0 |
| live_state | 10 | 10.0 | 7/0/0/1 |
| abstention | 10 | 10.0 | 4/0/0/0 |
| file_search | 10 | 10.0 | 6/0/0/0 |
| graph | 10 | 10.0 | 5/0/0/0 |

## door

- door: `"chat"`
- door_budget_chars: `2400`
- pressure_chars: `0`
- questions: `8`
- validated: `8`
- mean_answer_position: `162`
- mean_door_text_chars: `299`
- min_margin_chars: `2164`
- passes_within_300_chars_of_the_edge: `0`
- questions_with_forbidden_values: `1`
- stale_values_delivered: `0`
- chars_before_answer_mean: `162`
- duplicate_chunks_total: `0`

Not passed:
- FAIL What is the owner's phone number? — missing +39

## cards

- cards: `4`
- corrections: `2`
- aliases: `3`
- aliases_tried: `3`

## updates

- ⚠ section not measured: no sandbox test of the mechanism (--sandbox-test); historical trace: superseded=0, updates=0
- ⚠ no trace of updates in live memory: the dedup has not worked yet or found no pairs

Not passed:
- SKIP update mechanism (needs --sandbox-test) — without the sandbox test the historical trace does not score

## time

- share_of_memories_with_age: `1.0`
- facts_with_event_date: `"8/10"`
- days_tried: `["2026-09-10", "2026-09-09", "2026-09-08"]`
- signed_episodes_pc2: `1`

Not passed:
- FAIL «cosa ha fatto il pc2?» finds the episodes signed [pc2] — 0 episodes in the answer

## live_state

- live_state_age_min: `null`
- write_to_serve_ms: `1268`
- write_to_serve_p50_ms: `47`
- write_to_serve_p95_ms: `1268`
- write_to_serve_samples: `3`
- write_to_serve_budget_s: `30`
- overwrite_to_visible_ms: `1200`
- stale_reads_after_overwrite: `0`
- repeated_writes_settle_ms: `27`
- out_of_order_reads: `0`
- repeated_writes_timeline: `[{"t_ms": 0, "event": "first write"}, {"t_ms": 35, "event": "second write"}, {"t_ms": 99, "event": "poll", "first": false, "second": true}, {"t_ms": 1127, "event": "poll", "first": false, "second": true}, {"t_ms": 2156, "event": "poll", "first": false, "second": true}]`

Not passed:
- SKIP live-state key freshness — no live-state key configured (ADEBENCH_LIVE_STATE_KEY)

## abstention

- questions: `4`

## file_search

- indexable_functions: `6`
- tried: `6`

## graph

- nodes: `20`
- edges: `40`
- orphan_fact_nodes: `"0 orphans out of 10"`

## health

- cards: `4`
- facts: `10`
- episodes: `4`

## doors

- /v1/memory/recall: `{"calls": 24, "http_errors": 0, "ms_p50": 1124, "ms_p95": 1377, "mean_chars": 3786}`
