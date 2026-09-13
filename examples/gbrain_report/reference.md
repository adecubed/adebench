# adebench — 2026-09-13T11:54:41

**Score: 73.8 / 80 (+7.6) — coverage 80/100: 20 not measured (no evidence)**
Cases: 32 PASS · 2 FAIL · 0 ERROR · 5 SKIP
Adapter `adebench.gbrain:GbrainAdapter` · door `search` · cases `0f9a4640dc` · setup `2f332b8dff` · sections door, cards, updates, time, live_state, abstention, file_search, graph
Delta against the comparable run of 2026-09-13T11:51:23.

| Section | Weight | Points | PASS/FAIL/ERROR/SKIP |
|---|---|---|---|
| door | 25 | 18.8 (+0.0) | 6/2/0/0 |
| cards | 15 | 15.0 (+0.0) | 8/0/0/0 |
| updates | 10 | not measured | 0/0/0/1 |
| time | 10 | 10.0 (+2.5) | 4/0/0/1 |
| live_state | 10 | 10.0 (+1.7) | 6/0/0/1 |
| abstention | 10 | 10.0 (+3.3) | 4/0/0/0 |
| file_search | 10 | not measured | 0/0/0/1 |
| graph | 10 | 10.0 (+0.0) | 4/0/0/1 |

## door

- door: `"search"`
- door_budget_chars: `null`
- pressure_chars: `0`
- questions: `8`
- validated: `8`
- mean_answer_position: `194`
- mean_door_text_chars: `1218`
- min_margin_chars: `null`
- passes_within_300_chars_of_the_edge: `0`
- questions_with_forbidden_values: `1`
- stale_values_delivered: `1`
- chars_before_answer_mean: `194`
- duplicate_chunks_total: `0`

- ⚠ 1 answers delivered a retired value next to the current one: the model has to guess which is true

Not passed:
- FAIL Which version of MailBridge is installed for the mailbox? — STALE value delivered next to the current one: 1.3.0
- FAIL What is the owner's phone number? — missing +39

## cards

- cards: `4`
- corrections: `0`
- aliases: `0`
- aliases_tried: `0`

## updates

- ⚠ section not measured: no sandbox test of the mechanism (--sandbox-test); historical trace: superseded=0, updates=0
- ⚠ no trace of updates in live memory: the dedup has not worked yet or found no pairs

Not passed:
- SKIP update mechanism (needs --sandbox-test) — without the sandbox test the historical trace does not score

## time

- share_of_memories_with_age: `1.0`
- facts_with_event_date: `"0/0"`
- days_tried: `["2026-09-10", "2026-09-09", "2026-09-08"]`
- signed_episodes_pc2: `0`

Not passed:
- SKIP episodes signed by another machine — none in this memory

## live_state

- live_state_age_min: `null`
- write_to_serve_ms: `3495`
- write_to_serve_p50_ms: `3346`
- write_to_serve_p95_ms: `3495`
- write_to_serve_samples: `3`
- write_to_serve_budget_s: `30`
- overwrite_to_visible_ms: `3202`
- stale_reads_after_overwrite: `0`

Not passed:
- SKIP live-state key freshness — no live-state key configured (ADEBENCH_LIVE_STATE_KEY)

## abstention

- questions: `4`

## file_search

- ⚠ section not measured: no repo configured (--repo)

Not passed:
- SKIP file search — no repo configured (--repo)

## graph

- page_count: `18`
- chunk_count: `20`
- embedded_count: `20`
- link_count: `8`
- tag_count: `0`
- timeline_entry_count: `4`
- pages_by_type: `{"atom": 10, "note": 4, "project": 3, "person": 1}`
- orphan_fact_nodes: `"the graph has no fact nodes: nothing to check"`

Not passed:
- SKIP orphan fact nodes = 0 — the graph has no fact nodes: nothing to check

## health

- page_count: `18`
- linkable_page_count: `8`
- embed_coverage: `1`
- stale_pages: `18`
- orphan_pages: `4`
- missing_embeddings: `0`
- brain_score: `68`
- dead_links: `0`
- entity_page_count: `1`
- link_coverage: `null`
- timeline_coverage: `null`
- most_connected: `[{"slug": "people/owner", "link_count": 3}]`
- embed_coverage_score: `35`
- link_density_score: `11`
- timeline_coverage_score: `4`
- no_orphans_score: `8`
- no_dead_links_score: `10`
- migrations: `{"pending": ["0.11.0", "0.12.0", "0.12.2", "0.13.0", "0.13.1", "0.14.0", "0.16.0", "0.18.0", "0.18.1", "0.21.0", "0.22.4", "0.28.0", "0.29.1", "0.31.0", "0.32.2", "0.43.0", "0.46.3"], "partial": [], "wedged": [], "skipped_future": 0}`

## doors

- search: `{"calls": 20, "http_errors": 0, "ms_p50": 1603, "ms_p95": 1753, "mean_chars": 4856}`
- recall: `{"calls": 18, "http_errors": 0, "ms_p50": 1621, "ms_p95": 1839, "mean_chars": 2831}`

## census

- origin: `"local"`
- generated_at: `"2026-09-13T00:00:00Z"`
- calls: `20`
- servers_called: `3`
- tool_response_bytes: `{"median": 512, "p95": 140000, "max": 140000}`
- this_door_mean_chars: `4856`
- this_door_rank_in_census: `0.75`
- declared_vs_returned: `{"declared_bytes": 155687, "returned_mean_chars": 4856, "returned_over_declared": 0.03}`

- ⚠ this census document carries no declared sizes (declared_bytes = 0: the local recorder does not keep tools/list yet), so declared-vs-returned has no reference
- ⚠ this door delivers 4856 characters on average: larger than 75% of the 20 tool responses in the census
