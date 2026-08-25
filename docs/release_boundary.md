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
- Real ADDS-Frontier task packets, oracle bytes, commitment nonces, exact disease/program
  identities, curator identities, canary tokens, detailed preflight records, semantic-review arm
  payloads, sealed mappings, reviewer responses, workflow and resolution ledgers, triage records,
  canonical unblinding/replay details, resolution receipts, independent-oracle challenge packets,
  keys, assignments, responses, comparisons, and ledgers, oracle-fragility detailed reports,
  oracle-support curation packets, oracle-transition detailed reports, coupled-augmentation matched
  records and sealed candidate/control bindings, coupled-placebo three-arm or tokenizer-placebo
  five-arm packets, role keys, evidence text, per-placebo evaluation-only tokenizer diagnostics,
  independent-family per-placebo reports, and frozen WordPiece/SentencePiece model assets,
  adjudication records, admission records, and model submissions.
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
- Real clinical outcome stress scenarios, missingness-model elicitation, hidden-dependence working
  records, replicate-level simulation records, and correction-selection deliberations.
- Real clinical outcome sensitivity protocols, log-IMOR elicitation, prediction-stratum working
  records, latent outcomes, and correction-selection deliberations.
- Real collaborator or Biohub program data, biomodel outputs, cell-state or perturbation payloads,
  reviewer assignments, manual baseline worksheets, adjudication records, pilot timings, and
  program-level pilot results.
- Real upstream cell-state or perturbation payloads, source bytes, donor or cell records,
  scientific-owner mappings, reviewer identities, and non-public handoff fixtures.
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
- ADDS-Frontier allocation protocols, empty slot registries, private-payload schemas, salted
  commitments, payload-free aggregate authoring progress, and payload-free automated preflight
  and semantic-review readiness/workflow/resolution, independent-oracle challenge, and aggregate
  oracle-fragility, oracle-support curation, oracle-transition audit, and matched coupled-
  augmentation, coupled-placebo, and tokenizer-placebo readiness summaries, including payload-free
  post-selection tokenizer diagnostics and locally pre-sealed independent-family protocols and
  aggregate results, after boundary and integrity review.
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
- Synthetic informative-evaluability and dependence-closure stress protocols and aggregate reports
  after exact-partition, analytic-truth, replay, workload, privacy, and
  no-automatic-correction review.
- Preregistered synthetic prediction-stratified binary pattern-mixture protocols and aggregate
  reports after exact stress binding, log-IMOR grid, sparse-support, recovery, identification,
  replay, privacy, and no-automatic-selection review.
- Preregistered synthetic pattern-mixture cluster-jackknife protocols and aggregate reports after
  exact stress/protocol/report binding, all-grid calibration, Monte Carlo precision,
  nominal/dependence-closed comparison, fail-closed support, privacy, and no-automatic-closure
  review.
- Reproducible dataset cards pointing to external archives.

## Current Policy

The GitHub repo should be treated as a sanitized executable control plane and protocol layer. Full episode banks, evaluator references, raw snapshots, working notes, and run outputs stay outside Git until an explicit release packaging step creates a separate audited artifact.

The scientific claim anchors are `docs/12_scd_vertical_slice.md`,
`docs/13_target_id_governance_node.md`,
`docs/33_informative_evaluability_and_dependence_stress.md`,
`docs/34_preregistered_pattern_mixture_sensitivity.md`,
`docs/35_dependence_closed_pattern_mixture_uncertainty.md`, and
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

`docs/uc_clinical_provider_validation_snapshot.json` adds two public-source ulcerative-colitis
induction contract runs under that boundary. It records one retained uncertain result and one
bounded favorable result, treatment-phase identity, and exact hashes without source bytes or jobs.

`docs/uc_phase_population_validation_snapshot.json` adds induction and maintenance analyses from
one `NCT02435992` source capture. It records distinct endpoint/safety population counts and exact
hashes while keeping `same_participants_inferred` false. The shared NCT/source counts as one trial;
no phase pooling, participant overlap, longitudinal exchangeability, comparative phase effect, or
clinical acceptability is inferred.

`docs/uc_maintenance_risk_difference_validation_snapshot.json` adds one independent primary
maintenance replication from `NCT01458574`. It preserves an explicit percentage-point scale,
candidate-first sign binding, role-wise endpoint/safety counts, exact artifact hashes, and five
screened exclusion/defer controls. It does not claim same-candidate replication, cross-trial
pooling, participant identity, safety acceptability, or a treatment recommendation. Raw source,
review, manifest, and run artifacts remain outside Git.

`docs/ra_acr20_risk_difference_validation_snapshot.json` adds a second real immune-inflammatory
disease through `NCT00383188`. It preserves a candidate-first ACR20 percentage-point interval that
crosses null, commits the evidence on `HOLD`, records endpoint/safety denominator mismatch, and
keeps four screened exclusions or deferrals. It does not claim efficacy replication, safety
acceptability, or a treatment recommendation.

`docs/ra_olokizumab_additive_tensor_validation_snapshot.json` adds the first real source-disjoint
additive tensor under the same release boundary. It retains two olokizumab Week-12 ACR20 risk
differences on their proportion source scale, normalizes only decision precision to percentage
points, preserves distinct methotrexate- and TNF-inhibitor-inadequate-response contexts, and records
a safety-triggered `HOLD`. It does not contain source bytes, review jobs, full states, or the real
decision package and does not claim population exchangeability, pooling, comparative safety,
clinical acceptability, or treatment choice.

`docs/ra_olokizumab_population_transport_report.json` adds a reviewed descriptive
population-stratification diagnostic. It binds the exact synthesis, trial, endpoint, ITT
population, registry source, and official-title field before retaining methotrexate- and
TNF-inhibitor-inadequate-response strata side by side. It performs no pooling or cross-stratum
contrast and emits no transport estimate because the target population, within-stratum
replication, individual-level covariates, preregistered transport model, and risk-of-bias
assessment are absent. Project-internal approval is not independent scientific review.

`docs/ra_olokizumab_mtx_ir_replication_spec.json` and
`docs/ra_olokizumab_mtx_ir_replication_report.json` add the follow-on same-stratum execution. Two
source-disjoint MTX-inadequate-response phase 3 trials now support one reviewed stratum, removing
the distinct-strata and no-within-stratum-replication blockers. The provider retains the exact
month-precision source date and its conservative period-end normalization. Source bytes, real
jobs, manifests, full states, and the decision package remain excluded. Five transport blockers,
non-pooling, a workflow `HOLD`, and all prohibited-inference flags remain explicit.

`docs/ra_olokizumab_mtx_ir_risk_of_bias_spec.json` and
`docs/ra_olokizumab_mtx_ir_risk_of_bias_report.json` add a project-internal outcome-specific
follow-on. Exact public registry fields and registry-labeled protocol/SAP PDF hashes, pages,
sections, excerpts, and dates are retained without shipping source bytes. Source-specific arm and
endpoint identity plus PDF page/date/text checks fail closed. ITT analysis denominators are not
presented as proof of complete observed outcomes, and a standalone final pre-unblinding SAP is not
claimed. This resolves only `risk_of_bias_not_assessed`; four transport blockers and all no-pooling,
no-transport, no-treatment, and no-independent-review boundaries remain explicit. This is not an
official Cochrane RoB 2 assessment.

The cross-trial synthesis surface contains explicit synthetic selection examples, typed
trial-level outputs, source evidence IDs, content hashes, and payload-free aggregate records of
external PALOMA-2/3 and olokizumab executions. It does not include the real review packets, full
states, source bytes, pooled estimates, benefit-risk scores, clinical judgments, or treatment
recommendations.

The ulcerative-colitis M6, endpoint-mapping, synthesis, and evidence-tensor conformance surface
remains fully synthetic. Separate UC and RA surfaces use real public ClinicalTrials.gov snapshots
to validate exact ingestion, direction-aware gating, phase identity, retained uncertainty, and one
RA source-disjoint additive tensor plus one same-stratum MTX-IR replication. They do not extend
real-source validation upstream to M6,
establish population transportability or independent scientific review, or constitute a second
end-to-end therapeutic result.

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

The multi-endpoint benefit-risk portfolio layer ships implementation, strict specification/report
schemas and readers, documentation, and synthetic strict/overlap tests. A real portfolio can expose
selected endpoint domains, exact trial and source reuse, safety numerators and denominators, and
program-state fingerprints. Real specifications, reports, source states, and endpoint-review
materials remain outside Git and Hugging Face until separate scientific, privacy, governance, and
release-boundary review. The synthetic controls establish accounting behavior only.

The same-trial multi-endpoint stress layer ships a deterministic compiler, strict report schema and
reader, documentation, and identity-closed synthetic matched/heterogeneous/relabeling controls. A
real report can expose endpoint-pair population identities, population hashes, treatment phase,
endpoint and safety windows, shared safety units, and source overlap. Real pairwise reports, source
states, endpoint/population review declarations, and estimand or safety-window adjudications remain
outside Git and Hugging Face until separate scientific, privacy, governance, and release-boundary
review. Structural matching is never released as a clinical comparability claim.

The provenance-bound endpoint review-candidate layer ships an exhaustive design-scoped compiler,
strict spec/packet schemas and readers, documentation, and identity-closed synthetic omission,
exclusion, heterogeneity, and tamper controls. A real packet can expose endpoint and population
text, exact trial/design identities, safety aggregates, source locators and hashes, phase/window
diagnostics, and the complete candidate relationship graph. Real specs, packets, source states,
reviewer assignments, semantic endpoint-family decisions, and endpoint-safety adjudications remain
outside Git and Hugging Face until separate scientific, privacy, governance, and release-boundary
review. Public implementation fixes approval, ontology, estimand, comparability, safety,
benefit-risk, and treatment-choice claims to false.

The ClinicalTrials.gov registry-record inventory ships a study-scoped compiler, strict spec/packet
schemas and readers, CLI and isolated-wheel coverage, documentation, and synthetic
secondary/unmatched/ambiguous outcome plus serious/other event controls. A real packet can expose
NCT/version identities, endpoint titles and windows, safety terms and aggregate counts, source
pointers and hashes, and exact lexical candidate relationships. Raw bundles and real specs,
inventories, reviewer decisions, endpoint mappings, safety adjudications, and downstream promoted
states remain outside Git and Hugging Face until separate scientific, privacy, governance, and
release-boundary review. Public implementation performs no endpoint selection, equivalence,
comparability, causal safety inference, synthesis, or treatment choice.

The cross-trial harmonization candidate layer ships an exact-inventory-bound compiler, strict
spec/packet schemas and readers, a repeated-inventory CLI, documentation, and synthetic
full-Cartesian, zero-result, module-presence, ambiguity, missingness, safety-window, source-reuse,
bound, replay, and tamper controls. A real packet can expose trial and source identities, endpoint
titles and result structure, protocol-link candidates, safety record identities, and reviewer
workload. Real inventory sets, candidate packets, reviewer assignments, endpoint-family or
estimand decisions, safety-window adjudications, and comparability decisions remain outside Git and
Hugging Face until separate scientific, privacy, governance, and release-boundary review. Public
implementation performs no semantic approval, pooling, benefit-risk synthesis, regulatory
inference, or treatment choice.

The harmonization-difficulty layer ships a payload-free aggregate compiler, strict spec/report
schemas and readers, CLI, documentation, synthetic adversarial tests, and one exact public-source
olokizumab MTX-IR aggregate. That report retains NCT IDs, source and inventory hashes, counts,
review routes, signatures, and fixed nonclaims. Raw snapshots, source bundles, real inventory
packets, the pair-level candidate graph, endpoint titles, pair IDs, safety terms, reviewer
assignments, and semantic decisions remain outside Git and Hugging Face. Aggregate blocker counts
describe review workload only; they do not establish endpoint equivalence, model accuracy,
comparability, efficacy, safety, benefit-risk, or treatment choice.

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

The informative-evaluability and dependence-closure stress layer ships bounded implementation,
strict protocol/report/summary schemas, deterministic replay, documentation, tests, and aggregate
synthetic examples. Real missingness-model elicitation, hidden-dependence working records,
replicate records, and correction-selection deliberations remain outside Git and Hugging Face.
Public examples compare declared population and evaluable estimands and do not select a correction
automatically.

The prediction-stratified binary pattern-mixture layer ships a stress-bound protocol, aggregate
report and summary schemas, strict readers, deterministic replay, tests, and a synthetic recovery
study. Real log-IMOR ranges require outcome-blind clinical elicitation. Real prediction-stratum
working records and latent outcomes remain outside Git and Hugging Face. Point sensitivity
envelopes are neither sampling intervals nor confidence sets, and synthetic target passage does
not validate a real board or missingness range.

The pattern-mixture sampling-uncertainty layer ships an exact stress/protocol/report-bound
protocol, aggregate report and summary schemas, strict readers, deterministic replay, tests, and a
synthetic cluster-jackknife calibration study. Real dependence manifests, log-IMOR elicitation,
cluster influence working records, and replicate-level intervals remain outside Git and Hugging
Face. Public output contains no unit or cluster roster, never discovers dependence automatically,
and keeps fixed-assumption sampling intervals separate from identification uncertainty.

The unequal-cluster influence layer ships four bound synthetic scenarios, strict
protocol/report/summary schemas, a deterministic artifact builder, exact replay tests, and aggregate
method-grid-metric results. It compares normal and `t_(G-1)` delete-one intervals, unequal
delete-`m_j` pseudovalue intervals, and an experimental one-step Webb multiplier. It neither
selects a universal method nor claims a regression wild-cluster bootstrap. Dominant-cluster stress
results remain non-operational even when a calibration cell passes. Real influence records,
dependence rosters, cluster-level outputs, and method-selection deliberations remain excluded.

The informative-cluster-size layer ships five fixed synthetic prevalence profiles, strict
protocol/report/summary schemas, a deterministic artifact builder, exact replay tests, and
aggregate estimand and influence comparisons. It distinguishes unit-weighted from
cluster-balanced functionals and explicitly conditions calibration on the fixed public blocks.
It neither chooses an estimand nor claims cluster-superpopulation inference. Real size-outcome
profiles, block rosters, replicate or block records, influence traces, and estimand-selection
deliberations remain outside Git and Hugging Face.

The cluster-superpopulation layer ships uniform empirical-template resampling over the same five
synthetic profiles, strict protocol/report/summary schemas, exact conditional-reference binding,
deterministic substreams and replay, aggregate realized-design and tie-aware influence diagnostics,
tests, and documentation. It preserves both known truths exactly and isolates one declared
sampling-frame variance contrast. It does not claim that the template support represents an
external clinical population, filter inferential results by realized eligibility, select an
estimand or interval method, or override dominance hard stops. Real sampling frames, cluster
covariates, transport models, cluster or replicate records, and design-selection deliberations
remain outside Git and Hugging Face.

The Biohub-context readiness surface ships an independent public-source alignment review, a strict
machine profile, artifact hashes, a maturity ledger, a ten-slide claim sequence, and a proposed
90-day pilot contract. It does not contain Biohub data or model outputs, assert affiliation or
endorsement, or report an executed pilot. Real collaborator program rosters, payloads, reviewer
materials, authorization records, timings, adjudications, and program-level results remain outside
Git and Hugging Face pending a separate joint scientific, privacy, governance, and release review.

The generic upstream translational-handoff surface ships a strict schema and reader, one fully
synthetic two-source fixture, a second synthetic ulcerative-colitis conformance fixture,
contextual-only compilation, documentation, and adversarial tests.
Real source bytes, cell- or donor-level records, scientific-owner mappings, reviewer identities,
and non-public fixtures remain outside Git and Hugging Face. A valid handoff proves contract
consistency, not source truth, mechanism, efficacy, safety, clinical readiness, or transportability.

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
ClinicalTrials.gov inventory and endpoint/safety trial-design provider paths ship only their
verifiers, schemas, synthetic examples, tests, and payload-free validation documentation. Real article/API bundles,
reviewer-selected excerpts/jobs, real inventory/candidate packets, and any real compiled manifest
remain external until separate scientific and release-boundary approval. The sole bounded
harmonization exception is the explicitly reviewed payload-free aggregate described above; its raw
and pair-level inputs remain external.

## GitHub and Hugging Face Split

- The approved 0.3.0.dev2 release remains public on GitHub and Hugging Face.
- The 0.3.0.dev3 candidate is not approved, merged, or uploaded.
- The GitHub release contains the full sanitized code surface:
  adapters, chains, verifiers, the typed `agentic_drug_discovery/` core,
  governance docs, automation, tests, and `benchmark/`.
- The public Hugging Face Dataset package is a commit-pinned subset:
  documentation, the typed execution core, the dependency-free pinned-evidence and
  local clinical-synthesis adapters and bindings, the clinical evidence tensor and bounded-VOI
  compiler, clinical cohort diagnostics and synthetic matched-policy report, the bounded clinical
  closed-loop compiler and synthetic transition, dependence-aware clinical outcome uncertainty
  protocols, informative-evaluability stress analysis, prediction-stratified pattern-mixture
  sensitivity and dependence-closed cluster-jackknife calibration, aggregate synthetic reports,
  tests, schemas, aggregate evidence, audit code, and
  the `benchmark/` scorer.
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
