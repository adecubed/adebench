# GovKM experimental authority-resolution contribution

GovKM is fixture author. The synthetic contribution is offered under this repository's MIT license; see ../../LICENSE. The original v0.2 source, example files and manifests are preserved byte for byte. README.md and CONTRIBUTION_NOTES.md describe the original candidate preparation status; this submission note records the subsequent authorized proposal.

This directory is a proposed experimental location outside Core, subject to maintainer review under issue #2. It adds no scorer, adapter, package dependency, CI configuration or leaderboard change. ADEBench retains scoring, metrics, experimental leaderboard and private holdout custody.

Only source_inventory_text is offered as unscored source input. expected_outcomes.json is a public-example evaluation oracle and must never enter memory/model input. Only independently captured delivered_text_after_cut can support future ADEBench scores. No private holdout was generated or included.

Validation: Python 3.12.14, 17/17 offline generator tests passed. Public seed 20261022, count 2 per family gives 12 cases. Cases and expected outcomes reproduce approved sample bytes. Original metadata records Python 3.13.5; current-runtime replay changes python_version and its manifest hash only. No scored benchmark or native AI-memory/model experiment was run.

Maintainer review remains needed for directory/schema, public-oracle placement, delivered coverage proof for no-authority cases, temporal boundaries and matching/cut rules. No claim of adoption before merge.
