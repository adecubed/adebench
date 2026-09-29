# adebench — 2026-09-29T11:07:36

**Score: 42.1 / 65 — coverage 65/100: 35 not measured (no evidence)**
Cases: 18 PASS · 10 FAIL · 0 ERROR · 5 SKIP
Adapter `adebench.jevmem:JevMemAdapter` · door `evidence` · cases `0f9a4640dc` · setup `b4aa97e819` · sections door, cards, updates, time, live_state, abstention, file_search, graph

| Section | Weight | Points | PASS/FAIL/ERROR/SKIP |
|---|---|---|---|
| door | 25 | 18.8 | 6/2/0/0 |
| cards | 15 | not measured | 0/0/0/1 |
| updates | 10 | 3.3 | 1/2/0/0 |
| time | 10 | 6.7 | 4/2/0/0 |
| live_state | 10 | 10.0 | 7/0/0/1 |
| abstention | 10 | 3.3 | 0/4/0/0 |
| file_search | 10 | not measured | 0/0/0/1 |
| graph | 10 | not measured | 0/0/0/2 |
| write_back | report-only | — | 0/2/0/0 |

## door

- door: `"evidence"`
- door_budget_chars: `null`
- pressure_chars: `0`
- questions: `8`
- validated: `8`
- mean_answer_position: `204`
- mean_door_text_chars: `943`
- min_margin_chars: `null`
- passes_within_300_chars_of_the_edge: `0`
- questions_with_forbidden_values: `1`
- stale_values_delivered: `1`
- chars_before_answer_mean: `204`
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

- links_by_type: `{"ENTITY:SHARED_ENTITY": 151, "TEMPORAL:PRECEDES": 20, "TEMPORAL:SUCCEEDS": 20, "CAUSAL:LEADS_TO": 116, "SEMANTIC:RELATED_TO": 94, "TEMPORAL:TEMPORALLY_CLOSE": 5}`
- superseded_live: `0`
- relation_updates: `0`
- probe: `true`
- probe_entity: `"zetgihdch"`
- probe_replace_ms: `2924`
- probe_reads_with_both: `28`
- probe_cleanup_ok: `true`

- ⚠ no trace of updates in live memory: the dedup has not worked yet or found no pairs

Not passed:
- FAIL a new write with a changed value replaces the old one at the door (no id given) — new value served in 2924 ms; STALE: the old value is still delivered (28 reads with both)
- FAIL restating the current value does not pile up a second copy — 6 copies delivered

## time

- share_of_memories_with_age: `0.4`
- facts_with_event_date: `"16/21"`
- days_tried: `["2026-09-10", "2026-09-09", "2026-09-08"]`
- signed_episodes: `1`
- signed_question: `"what did pc2 do?"`

Not passed:
- FAIL semantic memories carry their age (14/35) — 40%
- FAIL «what did pc2 do?» finds the episodes signed [pc2] — 3 episodes in the answer

## live_state

- live_state_age_min: `null`
- write_to_serve_ms: `3421`
- write_to_serve_p50_ms: `3792`
- write_to_serve_p95_ms: `4701`
- write_to_serve_samples: `3`
- write_to_serve_budget_s: `30`
- overwrite_to_visible_ms: `4257`
- stale_reads_after_overwrite: `0`
- repeated_writes_settle_ms: `3827`
- out_of_order_reads: `0`
- repeated_writes_timeline: `[{"t_ms": 0, "event": "first write"}, {"t_ms": 1935, "event": "second write"}, {"t_ms": 7691, "event": "poll", "first": false, "second": true}, {"t_ms": 8718, "event": "poll", "first": false, "second": true}, {"t_ms": 9747, "event": "poll", "first": false, "second": true}]`

Not passed:
- SKIP live-state key freshness — no live-state key configured (ADEBENCH_LIVE_STATE_KEY)

## abstention

- questions: `4`

Not passed:
- FAIL What is the Zarpetta module? — episodes presented as direct matches; 3 keyword facts for something that does not exist
- FAIL Who is Ottavio Brambillesco? — episodes presented as direct matches; 4 keyword facts for something that does not exist
- FAIL Which port does the Fulmicotone service use? — episodes presented as direct matches; 4 keyword facts for something that does not exist
- FAIL What does the calendar plugin Girandola do? — episodes presented as direct matches; 4 keyword facts for something that does not exist

## file_search

- ⚠ section not measured: no repo configured (--repo)

Not passed:
- SKIP file search — no repo configured (--repo)

## graph

- nodes: `21`
- edges: `406`
- by_type: `{"ENTITY:SHARED_ENTITY": 151, "TEMPORAL:PRECEDES": 20, "TEMPORAL:SUCCEEDS": 20, "CAUSAL:LEADS_TO": 116, "SEMANTIC:RELATED_TO": 94, "TEMPORAL:TEMPORALLY_CLOSE": 5}`
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
- FAIL How many tools does the mailbox connector expose? — the degraded answer reached the door after 3172 ms (before the real answer)
- FAIL When do backups run? — the degraded answer reached the door after 3201 ms (before the real answer)

## health

- bridge: `{"loaded": true, "nodes": 21, "backend": "laya", "model": "convaiinnovations/laya", "init_s": 9.4}`
- config: `"config/laya_mem.json"`

- ⚠ no entity cards and no files: those sections are SKIP; forget is done by the adapter (node, links, vector, index), Jev-Mem has no forget of its own

## doors

- evidence: `{"calls": 58, "http_errors": 0, "ms_p50": 38, "ms_p95": 3827, "mean_chars": 884}`
