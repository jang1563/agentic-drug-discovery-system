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
- Real held-out curator identities, affiliation records, attestations, evidence snapshots, votes,
  rationales, adjudications, curation manifests, and per-episode curation results.
- Real clinical decision policies, action catalogs, evidence tensors, and compiled decision
  packages.
- Real clinical cohort manifests, accepted-state bindings, package diagnostics, and cohort reports.
- Real clinical prediction submissions, clinical outcome manifests, unit-level endpoint/safety
  labels, source-level outcome assessments, curator materials, and per-unit evaluation results.
- Real clinical outcome dependence manifests, unit-to-cluster assignments, cluster-level results,
  and unit-level uncertainty contributions.
- Real clinical outcome design scenarios, pilot parameter elicitation, replicate-level simulation
  records, and non-public gate-selection deliberations.
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
- Preregistered held-out protocols and payload-free stage-stratified aggregate reports after
  curator-privacy, label-leakage, and small-stratum review.
- Compiler-generated synthetic clinical evidence decision packages after schema and provenance
  review.
- Compiler-generated synthetic clinical cohort manifests and reports after schema, state-binding,
  provenance-overlap, and interpretation-boundary review.
- Preregistered synthetic clinical outcome protocols, package-bound prediction submissions,
  evaluator-style synthetic outcome manifests, and aggregate reports after cutoff, provenance,
  privacy, metric, and interpretation-boundary review.
- Preregistered synthetic uncertainty protocols, evaluator-style synthetic dependence manifests,
  and aggregate cluster-robust reports after dependence, small-cluster, privacy, and interpretation
  review.
- Synthetic prospective clustered-board design protocols and aggregate reports after parameter,
  workload, replay, Monte Carlo precision, privacy, and no-automatic-selection review.
- Reproducible dataset cards pointing to external archives.

## Current Policy

The GitHub repo should be treated as a sanitized executable control plane and protocol layer. Full episode banks, evaluator references, raw snapshots, working notes, and run outputs stay outside Git until an explicit release packaging step creates a separate audited artifact.

The scientific claim anchors are `docs/12_scd_vertical_slice.md`,
`docs/13_target_id_governance_node.md`, and
`docs/public_evidence_summary.json`. The sealed policy-evaluation aggregate is separately anchored
by `docs/25_cutoff_safe_policy_evaluation.md` and
`docs/retrospective_policy_evaluation_snapshot.json`;
the next-board protocol is defined by `docs/26_independent_heldout_evaluation.md`.
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

The held-out evaluation layer ships typed preregistration, opaque roster commitment, curation
validation, stage-stratified Wilson metrics, strict schemas/readers, and synthetic protocol/report
examples. A real curation manifest would expose episode-level votes and working governance
records, so it remains evaluator-only together with identity/affiliation source documents and
label evidence. No real independently curated held-out result is currently public or claimed.

The clinical evidence decision layer ships implementation, strict schema/readers, documentation,
tests, and one compiler-generated synthetic package. A real policy or action catalog can expose
program thresholds, priorities, costs, source identities, and planned operations; a real tensor or
package can retain trial-level evidence lineage. Those artifacts remain outside Git and Hugging
Face until a separate scientific, privacy, and release-boundary review approves them.

The clinical cohort diagnostics layer ships implementation, strict manifest/report/summary
schemas, deterministic readers and replay, documentation, tests, and one compiler-generated
synthetic matched-policy report. Real manifests can disclose selected programs and policy
comparisons; accepted-state hashes, package diagnostics, source/trial overlap, action frequencies,
and costs can expose program strategy and evidence lineage. Real cohort artifacts remain outside
Git and Hugging Face until separate scientific, privacy, governance, and release-boundary review.
The public synthetic report contains no outcomes and cannot support calibration or clinical
performance claims.

The preregistered clinical outcome layer ships implementation, strict protocol/submission/
manifest/report/summary schemas, deterministic replay, documentation, tests, and synthetic
artifacts. A real submission can expose program forecasts and policy behavior; a real outcome
manifest can expose selected programs, endpoint and safety labels, source lineage, assessment
timing, and evaluator governance. Real submissions, manifests, curator materials, and unit-level
scores remain outside Git and Hugging Face. Only separately reviewed aggregate reports may be
released. The checked-in one-unit result verifies contract execution and cannot establish
calibration, discrimination, clinical utility, efficacy, safety, or policy superiority.

The dependence-aware clinical outcome uncertainty layer ships implementation, a public frozen
protocol, strict dependence-manifest/report/summary schemas and readers, deterministic replay,
documentation, tests, and synthetic artifacts. Real dependence manifests can reveal selected
program relationships, shared evidence lineages, and unit-to-cluster assignments; cluster-level
results and unit-level metric contributions can permit reconstruction attacks. They remain
evaluator-only. Public reports contain only aggregate diagnostics and CR1 intervals, fail closed
for insufficient or dominant clusters, or cluster uncertainty that rounds to zero at the reporting
precision, and do not claim validated coverage or policy superiority. The checked-in one-cluster
example intentionally emits no interval.

The prospective clustered-board design layer ships implementation, strict protocol/report/summary
schemas, bounded deterministic replay, documentation, tests, and aggregate synthetic examples.
Real scenario ranges can reveal expected program counts, attrition, prevalence, dependence, and
internal acceptance criteria; replicate records and gate deliberations can expose unreleased study
plans. They remain outside Git and Hugging Face. Public examples contain fixed synthetic
parameters and aggregate Monte Carlo results only, and no candidate gate is selected automatically.

The clinical evidence closed-loop layer ships implementation, strict schema/readers, documentation,
tests, and one compiler-generated synthetic transition. Real closed-loop policies, execution
batches, provider requests/outcomes, compact receipts, reviewer refresh records, before/after
tensors, and transition packages can expose program strategy, source lineage, trial-level changes,
costs, and planned operations. They remain outside Git and Hugging Face until separate scientific,
privacy, security, and release-boundary review approves them.

`adds-pinned-ingestion` enforces the raw-data boundary operationally: source bundles are immutable,
contain exact bytes plus a receipt, and are refused inside any Git worktree. Compiled manifests and
review reports contain no raw bundle path and still require explicit human review before promotion.
The CDC MMWR, NCBI PubMed treatment-gap, ChEMBL functional-activity, NCBI PubMed disease-model, and
ClinicalTrials.gov endpoint/safety trial-design provider paths ship only their verifiers, schemas,
synthetic examples, tests, and payload-free validation documentation. Real article/API bundles,
reviewer-selected excerpts/jobs, external run artifacts, and any real compiled manifest remain
external until separate scientific and release-boundary approval.

## GitHub and Hugging Face Split

- The approved 0.3.0.dev2 release is public on GitHub and Hugging Face.
- The GitHub release contains the full sanitized code surface:
  adapters, chains, verifiers, the typed `agentic_drug_discovery/` core,
  governance docs, automation, tests, and `benchmark/`.
- The public Hugging Face Dataset package is a commit-pinned subset:
  documentation, the typed execution core, the dependency-free pinned-evidence and
  local clinical-synthesis adapters and bindings, the clinical evidence tensor and bounded-VOI
  compiler, clinical cohort diagnostics and synthetic matched-policy report, the bounded clinical
  closed-loop compiler and synthetic transition, dependence-aware clinical outcome uncertainty
  protocols and aggregate synthetic reports, tests, schemas, aggregate evidence, audit code,
  and the `benchmark/` scorer.
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
