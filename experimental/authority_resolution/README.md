# GovKM / ADEBench authority-resolution fixture generator v0.2.0

**Scope:** Public, purely synthetic fixture-generation candidate for ADEBench's proposed experimental non-Core authority-resolution track. **Not** an ADEBench scorer, model-memory adapter, or completed benchmark. No scored tests, upstream submission, private holdout, or external communication.

## Quick start (non-scored fixture self-validation)

```sh
python -m unittest discover -s tests -v
python generate_authority_cases.py --seed 20261022 --count 2 --set public --output-dir examples/public_seed_20261022
```

`--count N` generates N variants **per** six-pattern family (6N total). The seed is a nonnegative integer <2^63. The output directory must not exist; no overwrite. Holdout export is explicitly rejected. Python's PRNG stream should be replayed using the Python runtime version recorded in metadata.

## v0.2 protocol corrections

- `cases.json` includes `source_inventory_text`, which is **only the input record collection** offered for indexing. It must never be counted as delivered-to-model evidence. The only scoring boundary accepted by Simone is ADEBench's independently captured `delivered_text_after_cut`. This implementation does not create, simulate or evaluate that field. `expected_outcomes.json` is a separated private-to-evaluator oracle; never provide it to a model or retrieval system.
- Authorized supersession AR-01 requires source E1, superseding E2, and source grant G1 as **required** evidence rather than assuming supersession alone suffices. Revocation AR-04 likewise requires E1, E2 and G1.
- AR-06 recognizes two different outcomes: `NO_AUTHORITY_IF_COVERAGE_PROVEN` only where grant-register coverage (SOURCE-REGISTRY) is independently supported in model-delivered evidence; otherwise `AUTHORITY_UNRESOLVED`. `source_coverage` is a fictional source assertion, **not proof that the memory delivered it**. External score thresholds and semantic paraphrase matching remain ADEBench decisions.
- All scenarios preserve distinct `valid_at` (effective authority) versus `recorded_at` (ingestion/source chronology). AR-05 historical as-of t2 must not be superseded retroactively by t3. Exact boundary conditions remain subject to ADEBench's scoring contract.
- Three separate evaluator dimensions are declared: operative value, authority outcome and source event delivery. This generator DOES NOT implement any evaluator, cutoff algorithm, or score.

## Files and provenance

`cases.json` public fictional events and coverage assumptions; `expected_outcomes.json` candidate oracle (never feed to memory); `metadata.json` seed/version/runtime; `sha256_manifest.json` SHA-256 for output files and generator/test source; `tests/test_generator.py` local non-scored consistency checks. Source and tests are included in manifest rather than embedding self-referential hashes into source.

**Packaging boundary:** No partner records, GovKM doctrine, internal scoring methods, or proprietary AIL logic may be contributed. ADEBench controls its own scoring and experimental leaderboard; attribution of GovKM as fixture author and licensing under actual repo license must be verified at the separate upstream approval gate. ADEBench, not GovKM, retains any private holdout seeds.

**Protocol note:** `source_coverage` currently declares a fictional complete registry as a source assertion. It does not prove actual retrieved or delivered coverage. This deliberately prevents false-positive claims that "no grant found" means "no authority." An independent evaluator must define a falsifiable model-visible coverage proof before scoring NO_AUTHORITY. Do not infer a passing result from this metadata.
