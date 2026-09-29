# adebench — 2026-09-29T12:52:47

**Score: 36.4 / 65 (-5.7) — coverage 65/100: 35 not measured (no evidence)**
Cases: 12 PASS · 14 FAIL · 0 ERROR · 5 SKIP
Adapter `adebench.nemp:NempAdapter` · door `context` · cases `0f9a4640dc` · setup `b2e3bde38a` · sections door, cards, updates, time, live_state, abstention, file_search, graph
Delta against the comparable run of 2026-09-29T12:17:07.

| Section | Weight | Points | PASS/FAIL/ERROR/SKIP |
|---|---|---|---|
| door | 25 | 18.8 (+0.0) | 6/2/0/0 |
| cards | 15 | not measured | 0/0/0/1 |
| updates | 10 | 3.3 (+0.0) | 1/2/0/0 |
| time | 10 | 2.5 (+0.0) | 1/3/0/0 |
| live_state | 10 | 4.3 (-5.7) | 3/4/0/1 |
| abstention | 10 | 7.5 (+0.0) | 1/3/0/0 |
| file_search | 10 | not measured | 0/0/0/1 |
| graph | 10 | not measured | 0/0/0/2 |
| write_back | report-only | — | 0/0/2/0 |

## door

- door: `"context"`
- door_budget_chars: `null`
- pressure_chars: `0`
- questions: `8`
- validated: `8`
- mean_answer_position: `1471`
- mean_door_text_chars: `29530`
- min_margin_chars: `null`
- passes_within_300_chars_of_the_edge: `0`
- questions_with_forbidden_values: `1`
- stale_values_delivered: `1`
- chars_before_answer_mean: `1471`
- duplicate_chunks_total: `78`

- ⚠ 78 repeated chunks across the delivered texts: budget spent twice on the same information
- ⚠ 1 answers delivered a retired value next to the current one: the model has to guess which is true

Not passed:
- FAIL Which version of MailBridge is installed for the mailbox? — STALE value delivered next to the current one: 1.3.0
- FAIL What is the owner's phone number? — missing +39

## cards

- ⚠ section not measured: no entity cards in this memory

Not passed:
- SKIP entity cards — this memory has none

## updates

- memories: `21`
- updated_in_place: `0`
- superseded_live: `0`
- relation_updates: `0`
- probe: `true`
- probe_entity: `"zetjnbdbj"`
- probe_replace_ms: `13145`
- probe_reads_with_both: `18`
- probe_cleanup_ok: `true`

- ⚠ no trace of updates in live memory: the dedup has not worked yet or found no pairs

Not passed:
- FAIL a new write with a changed value replaces the old one at the door (no id given) — new value served in 13145 ms; STALE: the old value is still delivered (18 reads with both)
- FAIL restating the current value does not pile up a second copy — 3 copies delivered

## time

- share_of_memories_with_age: `0.0`
- facts_with_event_date: `"0/21"`
- days_tried: `["2026-09-29"]`
- signed_episodes: `1`
- signed_question: `"what did pc2 do?"`

- ⚠ only 0 facts out of 21 carry the event date: for the others the age the model hears is the derivation date, not the fact's

Not passed:
- FAIL semantic memories carry their age (0/35) — 0%
- FAIL an imported memory reaches the door with its original date — served with no date
- FAIL «what did pc2 do?» finds the episodes signed [pc2] — 0 episodes in the answer

## live_state

- live_state_age_min: `null`
- write_to_serve_ms: `70470`
- write_to_serve_p50_ms: `70470`
- write_to_serve_p95_ms: `71304`
- write_to_serve_samples: `3`
- write_to_serve_budget_s: `30`
- overwrite_to_visible_ms: `65479`
- stale_reads_after_overwrite: `0`
- repeated_writes_settle_ms: `105744`
- out_of_order_reads: `0`
- repeated_writes_timeline: `[{"t_ms": 0, "event": "first write"}, {"t_ms": 40338, "event": "second write"}, {"t_ms": 186818, "event": "poll", "first": false, "second": true}]`

Not passed:
- FAIL the canary just written is served through the retrieval door — write-to-serve 70470 ms (over the 30 s budget)
- FAIL 3 canaries served within the budget — p50 70470 ms · p95 71304 ms · 2 not served within 30 s
- FAIL after overwriting the canary the door serves the new value, never the old one — overwrite-to-visible 65479 ms (over the 30 s budget)
- FAIL two writes in quick succession: the door settles on the second, never back on the first — second write visible in 105744 ms (over the 30 s budget)
- SKIP live-state key freshness — no live-state key configured (ADEBENCH_LIVE_STATE_KEY)

## abstention

- questions: `4`

Not passed:
- FAIL Who is Ottavio Brambillesco? — 1 keyword facts for something that does not exist
- FAIL Which port does the Fulmicotone service use? — 4 keyword facts for something that does not exist
- FAIL What does the calendar plugin Girandola do? — 2 keyword facts for something that does not exist

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
- cleanup_ok: `null`
- wait_s: `10`

Not passed:
- ERROR How many tools does the mailbox connector expose? — ingest_exchange returned no id
- ERROR When do backups run? — ingest_exchange returned no id

## health

- model: `"sonnet"`
- calls: `45`
- cost_usd: `6.93`
- memories: `21`
- store_bytes: `21305`

- ⚠ every operation is a model turn: the result depends on the model that follows Nemp's instructions
- ⚠ the context door is the whole store (cat + Read of memories.json on every lookup)

## doors
