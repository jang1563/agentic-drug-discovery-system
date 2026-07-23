# Release Boundary

This repository uses a conservative boundary so that future public or collaborator-facing releases do not inherit raw data, evaluator-only material, working notes, or generated run artifacts in Git history.

## Commit by Default

- Project overview and design docs.
- Sanitized model, tool, source, verifier, and compute registries only when they do not contain raw or evaluator-only payloads.
- Builder scripts, verifier scripts, launch scripts, and schema/reward specs.
- Typed execution-core code, deterministic tests, and explicitly non-benchmark fixtures.
- Templates and empty directory markers needed to reconstruct the workspace layout.

## Keep Outside Git

- Full case banks and raw source snapshots.
- Source capture bundles, real provider review jobs, ingestion runs, and reviewer working files.
- Evaluator-only labels and locked episode data.
- Generated reward and verifier results.
- Run logs and machine-specific execution outputs.
- Real policy checkpoints and policy-run artifacts containing full state or tool ledgers.
- Real sealed boards, cached episode packets, label vaults, commitment nonces, policy submissions,
  and per-episode evaluations.
- Root-level cluster scheduler `.out` / `.err` logs.
- API keys, credentials, `.env*`, key material, and local machine caches.

## Generated but Potentially Shareable Later

These may become release assets after a separate audit:

- Public visible-packet examples.
- Synthetic mini case banks.
- Public-only source manifests.
- Payload-free source receipts and ingestion review reports after separate scientific and boundary review.
- Aggregated benchmark metrics without evaluator-only labels or raw source snapshots.
- Payload-free sealed-evaluation hashes and aggregate policy metrics after leakage review.
- Reproducible dataset cards pointing to external archives.

## Current Policy

The GitHub repo should be treated as a sanitized executable control plane and protocol layer. Full episode banks, evaluator references, raw snapshots, working notes, and run outputs stay outside Git until an explicit release packaging step creates a separate audited artifact.

The scientific claim anchors are `docs/12_scd_vertical_slice.md`,
`docs/13_target_id_governance_node.md`, and
`docs/public_evidence_summary.json`. The sealed policy-evaluation aggregate is separately anchored
by `docs/25_cutoff_safe_policy_evaluation.md` and
`docs/retrospective_policy_evaluation_snapshot.json`;
`scripts/audit/validate_vertical_slice_doc.py`
checks the vertical-slice claims, while
`scripts/audit/validate_policy_evaluation_snapshot.py` checks the sealed-evaluation aggregate and
implementation hashes.

`docs/preclinical_provider_validation_snapshot.json` is a separate contract-execution anchor. It
contains no source bytes, reviewer text, review jobs, or local paths and explicitly states that
exact replay requires excluded external artifacts.

`docs/clinical_provider_validation_snapshot.json` follows the same boundary for one exact
ClinicalTrials.gov contract run: it records registry/design/safety identities, typed aggregate
values, artifact hashes, outcomes, and limitations, but no source payload or reviewer job.

The cross-trial synthesis surface contains explicit synthetic selection examples, typed
trial-level outputs, source evidence IDs, content hashes, and a payload-free aggregate record of
one external PALOMA-2/3 execution. It does not include the real review packet, full state, source
bytes, pooled estimates, benefit-risk scores, clinical judgments, or treatment recommendations.

The portfolio and endpoint-mapping surface likewise contains only executable verifiers, strict
schemas, synthetic references, and tests. Real multi-trial source bundles, single-trial review jobs,
portfolio review files, reviewer working identities, and ontology-resolution artifacts remain
external until separate scientific and release-boundary approval.

The typed replanning surface contains policy/checkpoint code, JSON Schema, documentation, and
synthetic tests. Real senicapoc and PALOMA policy/checkpoint runs were executed externally, but
`PolicyCheckpoint` values contain the complete program state and cumulative tool ledger, so
`policy_checkpoints/` and `policy_runs/` remain outside Git until a separate payload and provenance
review approves a sanitized artifact.

The sealed-evaluation surface ships implementation, JSON Schemas, synthetic development tests,
aggregate real-board metrics, payload-free hashes, and limitations. The real role-neutral board
still contains full `ProgramState` values and cached sanitized tool packets; its external label
vault contains arm, gold decision, failure cause, metadata, and commitment nonce. Those artifacts,
all policy submissions, and per-episode scores remain outside Git.

`adds-pinned-ingestion` enforces the raw-data boundary operationally: source bundles are immutable,
contain exact bytes plus a receipt, and are refused inside any Git worktree. Compiled manifests and
review reports contain no raw bundle path and still require explicit human review before promotion.
The CDC MMWR, NCBI PubMed treatment-gap, ChEMBL functional-activity, NCBI PubMed disease-model, and
ClinicalTrials.gov endpoint/safety trial-design provider paths ship only their verifiers, schemas,
synthetic examples, tests, and payload-free validation documentation. Real article/API bundles,
reviewer-selected excerpts/jobs, external run artifacts, and any real compiled manifest remain
external until separate scientific and release-boundary approval.

## GitHub and Hugging Face Split

- The 0.3.0.dev0 GitHub candidate contains the full sanitized code surface:
  adapters, chains, verifiers, the typed `agentic_drug_discovery/` core,
  governance docs, automation, tests, and `benchmark/`.
- Its candidate Hugging Face Dataset package is a commit-pinned subset:
  documentation, the typed execution core, the dependency-free pinned-evidence and
  local clinical-synthesis adapters and bindings, tests, schemas, aggregate evidence, audit code, and the
  `benchmark/` scorer.
- `benchmark/` scores the separately hosted
  `jang1563/clinical-trial-decision-benchmark` dataset. Its data rows and
  Croissant metadata do not belong in the Agentic Drug Discovery System mirror.
- `scripts/audit/build_hf_release_package.py` reads bytes from an explicit Git
  commit, not from the working tree. Local uncommitted work therefore cannot be
  mislabeled with the source commit, but it also cannot be validated as the new
  Hugging Face candidate until it is committed.

## Public-Readiness Gate

Before merging or uploading a change to either public surface, the tracked candidate must satisfy all of the following:

- `python3 scripts/audit/github_release_file_audit.py` passes on tracked and unignored candidate files.
- `python3 scripts/audit/validate_hf_release_package.py` passes before any Hugging Face upload.
- `python3 scripts/audit/build_hf_release_package.py --output /tmp/agentic-hf-release-package --force` can reproduce the Hugging Face package locally.
- `python3 scripts/audit/validate_hf_release_package.py --package /tmp/agentic-hf-release-package` confirms the exact file set, source tree, sizes, and hashes.
- `python3 -m unittest discover -s tests -v` passes for the executable control plane.
- `python3 -m ruff check agentic_drug_discovery tests adapters/boltz_adapter.py adapters/chembl_adapter.py adapters/opentargets_adapter.py adapters/execution_registry.py adapters/pinned_evidence_adapter.py adapters/clinical_synthesis_adapter.py scripts/audit` passes for executable, adapter-binding, and release-audit Python code.
- `python3 -m pytest -q benchmark/tests` passes after installing the local benchmark package.
- `python3 -m build --wheel . --outdir /tmp/agentic-core-dist` builds the execution-core package.
- `python3 scripts/audit/smoke_test_core_wheel.py --wheel-dir /tmp/agentic-core-dist` installs that wheel outside the source tree and validates the console trajectory.
- `git diff --check` reports no whitespace errors.
- Public Python files compile with `python3 -m compileall agentic_drug_discovery adapters chains benchmark/src scripts/audit tests`.
- `docs/public_release_readiness_plan.md`, `release_manifest.json`, `codemeta.json`, `.zenodo.json`, and `huggingface/release_manifest.json` match the intended release scope.
- License, citation metadata, contributor guidance, pull request boundary checks, issue templates, and security reporting instructions are present.
