# adebench — 2026-09-28T12:16:45

**Score: 36.2 / 55 (-0.3) — coverage 55/100: 10 not run (sections not selected), 35 not measured (no evidence)**
Cases: 10 PASS · 9 FAIL · 0 ERROR · 5 SKIP
Adapter `adebench.hindsight:HindsightAdapter` · door `recall` · cases `0f9a4640dc` · setup `48e790e78d` · sections door, cards, updates, time, abstention, file_search, graph
Delta against the comparable run of 2026-09-28T12:12:40.

| Section | Weight | Points | PASS/FAIL/ERROR/SKIP |
|---|---|---|---|
| door | 25 | 18.8 (+3.1) | 6/2/0/0 |
| cards | 15 | not measured | 0/0/0/1 |
| updates | 10 | 3.3 (+0.0) | 1/2/0/0 |
| time | 10 | 7.5 (+0.0) | 3/1/0/1 |
| abstention | 10 | 6.7 (-3.3) | 0/4/0/0 |
| file_search | 10 | not measured | 0/0/0/1 |
| graph | 10 | not measured | 0/0/0/2 |
| write_back | report-only | — | 2/0/0/0 |

## door

- door: `"recall"`
- door_budget_chars: `null`
- pressure_chars: `0`
- questions: `8`
- validated: `8`
- mean_answer_position: `114`
- mean_door_text_chars: `3225`
- min_margin_chars: `null`
- passes_within_300_chars_of_the_edge: `0`
- questions_with_forbidden_values: `1`
- stale_values_delivered: `1`
- chars_before_answer_mean: `114`
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

- memories_by_type: `{"world": 19, "observation": 7, "experience": 2}`
- superseded_live: `0`
- relation_updates: `0`
- probe: `true`
- probe_entity: `"zetfjcnpn"`
- probe_replace_ms: `561`
- probe_reads_with_both: `20`
- probe_cleanup_ok: `true`

- ⚠ no trace of updates in live memory: the dedup has not worked yet or found no pairs

Not passed:
- FAIL a new write with a changed value replaces the old one at the door (no id given) — new value served in 561 ms; STALE: the old value is still delivered (20 reads with both)
- FAIL restating the current value does not pile up a second copy — 3 copies delivered

## time

- share_of_memories_with_age: `1.0`
- facts_with_event_date: `"28/28"`
- days_tried: `["2026-09-10", "2026-09-08"]`
- signed_episodes: `0`
- signed_question: `"what did pc2 do?"`

Not passed:
- FAIL an imported memory reaches the door with its original date — imported memory not served within 30 s
- SKIP episodes signed by another machine — none in this memory

## abstention

- questions: `4`

Not passed:
- FAIL What is the Zarpetta module? — 28 keyword facts for something that does not exist
- FAIL Who is Ottavio Brambillesco? — 28 keyword facts for something that does not exist
- FAIL Which port does the Fulmicotone service use? — 28 keyword facts for something that does not exist
- FAIL What does the calendar plugin Girandola do? — 28 keyword facts for something that does not exist

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

- bank: `{"bank_id": "adebench", "name": "adebench", "disposition": {"skepticism": 3, "literalism": 3, "empathy": 3}, "mission": ""}`
- memories_by_type: `{"world": 19, "observation": 7, "experience": 2}`

- ⚠ cards, files and graph edges are not exposed by the bank's MCP surface: those sections are SKIP

## doors

- recall: `{"calls": 75, "http_errors": 0, "ms_p50": 577, "ms_p95": 688, "mean_chars": 16476}`
