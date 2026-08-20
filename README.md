# Agentic Drug Discovery System

**CTDBench v0.2, an audited sickle cell disease vertical slice, and an
evidence-governed end-to-end research scaffold**

[![release-audit](https://github.com/jang1563/agentic-drug-discovery-system/actions/workflows/release-audit.yml/badge.svg?branch=main)](https://github.com/jang1563/agentic-drug-discovery-system/actions/workflows/release-audit.yml)
[![GitHub release](https://img.shields.io/github/v/release/jang1563/agentic-drug-discovery-system)](https://github.com/jang1563/agentic-drug-discovery-system/releases/latest)
[![Hugging Face dataset](https://img.shields.io/badge/Hugging%20Face-Dataset-FFD21E?logo=huggingface&logoColor=000)](https://huggingface.co/datasets/jang1563/agentic-drug-discovery-system)

Version 0.2.0 provides two concrete public artifacts: `ctdbench`, a reproducible
runner and scorer for the public
[clinical trial decision benchmark](https://huggingface.co/datasets/jang1563/clinical-trial-decision-benchmark),
and an audited, retrospective vertical slice spanning the end-to-end workflow
for sickle cell disease (SCD). Callable evidence adapters, verifier contracts,
and release checks make these artifacts inspectable and reproducible within
their stated scope.

The repository name reflects the longer-term research direction. The proposed
eight-stage, long-horizon agentic drug discovery system remains a research
scaffold rather than a completed public platform. The public 0.3.0.dev2 baseline
established the evidence-governed execution, evaluation, clinical-planning,
closed-loop, and bounded ClinicalTrials.gov harmonization backbone. The
0.3.0.dev3 candidate extends that baseline with outcome-free cohort diagnostics,
preregistered package-bound forecasts, paired policy evaluation, dependence-aware
uncertainty and design simulation, informative-evaluability stress analysis,
prediction-stratified binary log-IMOR sensitivity, dependence-closed jackknife
calibration, and unequal-cluster influence calibration comparing normal,
`t_(G-1)`, delete-`m_j`, and an experimental Webb multiplier. It now also separates
unit-weighted from cluster-balanced functionals under informative cluster size,
with aggregate influence diagnostics and fixed-profile conditional calibration. This candidate is
not approved, merged, or uploaded. No real independently curated clinical outcome
result is claimed.
Seven of eight planned atlases still do not have standalone public data, and
the demonstrated continuous multi-stage program currently covers one
disease/target slice.

## At a Glance

| Field | Value |
| --- | --- |
| Purpose | Build a verification-oriented, auditable decision environment for drug-discovery agents. |
| Release status | 0.3.0.dev2 remains public on GitHub and Hugging Face. 0.3.0.dev3 is an unapproved, unmerged, and not-uploaded update candidate. 0.2.0 remains the latest tagged stable release. |
| Core control frame | Verify, defer, stop, or flag rather than silently advancing uncertain claims. |
| Not included | Raw source snapshots/bundles, real provider review jobs and ingestion runs, real sealed or held-out boards, curator identities/attestations/votes/adjudications, real clinical decision policies/action catalogs/evidence tensors/packages, real clinical prediction submissions/outcome or dependence manifests/unit labels, real design/stress/sensitivity scenario elicitation or working records, unit-to-cluster assignments, cluster-level or unit-level scores, cached episode packets, label vaults, commitment nonces, policy submissions, per-episode evaluations, hidden labels, locked episodes, generated trajectories, run logs, credentials, local paths, or model weights. |
| License | Apache-2.0. |

## Biohub-Context Research Readiness

An independent public-source review positions this project as a **translational evidence
governance layer** downstream of cell measurement, perturbation, and biomodel research. It does
not claim a Biohub affiliation, a virtual-cell model, autonomous therapeutic design, or real-world
clinical calibration. The review includes a concrete 90-day immune-perturbation handoff pilot,
five preregistered acceptance gates, a ten-slide presentation sequence, and machine-checked
evidence hashes:

- Human-readable review: `docs/39_biohub_translational_evidence_bridge.md`
- Machine profile: `docs/biohub_research_readiness.json`
- Strict schema: `rl_env/specs/biohub_research_readiness.schema.json`
- Implemented generic M6 handoff: `docs/40_upstream_translational_handoff.md`
- Synthetic immune-disease breadth check: `docs/41_ulcerative_colitis_conformance_slice.md`
- Public-source UC provider validation: `docs/42_uc_provider_validation.md`
- Phase-bound UC population alignment: `docs/43_uc_phase_population_alignment.md`

```bash
adds-research-readiness validate \
  --profile docs/biohub_research_readiness.json

adds-translational-handoff compile \
  --request-id synthetic-demo-request
```

## Quick Start

Install the core and test dependencies, then run the deterministic fixture and the public clinical
package reader:

```bash
python -m pip install -e ".[test]"
adds-bounded-agent-demo | python -m json.tool
adds-clinical-evidence summarize \
  --package rl_env/specs/clinical_evidence_decision_package.example.json
adds-clinical-evidence validate \
  --package rl_env/specs/clinical_evidence_decision_package.example.json
adds-clinical-evidence summarize-cohort \
  --report rl_env/specs/clinical_evidence_cohort_report.example.json
adds-clinical-evidence summarize-outcomes \
  --report rl_env/specs/clinical_outcome_evaluation_report.example.json
adds-clinical-evidence summarize-uncertainty \
  --report rl_env/specs/clinical_outcome_uncertainty_report.example.json
adds-clinical-evidence summarize-uncertainty-design \
  --report rl_env/specs/clinical_outcome_design_simulation_report.example.json
adds-clinical-evidence summarize-uncertainty-stress \
  --report rl_env/specs/clinical_outcome_stress_simulation_report.example.json
adds-clinical-evidence summarize-pattern-mixture \
  --report rl_env/specs/clinical_outcome_pattern_mixture_report.example.json
adds-clinical-evidence summarize-pattern-mixture-uncertainty \
  --report rl_env/specs/clinical_outcome_pattern_mixture_uncertainty_report.example.json
adds-clinical-evidence summarize-informative-cluster-size \
  --report rl_env/specs/clinical_outcome_informative_cluster_size_report.example.json
adds-clinical-evidence summarize-cluster-superpopulation \
  --report rl_env/specs/clinical_outcome_cluster_superpopulation_report.example.json
adds-clinical-evidence summarize-pattern-mixture-influence \
  --report rl_env/specs/clinical_outcome_pattern_mixture_influence_report.example.json
python -m pytest -q
```

Compile a new package from a serialized `ProgramState` that already contains an accepted-packet
clinical synthesis:

```bash
adds-clinical-evidence compile \
  --state accepted-program-state.json \
  --config clinical-decision-config.json \
  --output clinical-decision-package.json
adds-clinical-evidence validate \
  --package clinical-decision-package.json \
  --state accepted-program-state.json
```

The compiler rejects duplicate JSON keys, non-finite numbers, uncommitted mapping or synthesis
records, replay mismatches, and accidental output replacement. The public config schema and
synthetic example are under `rl_env/specs/clinical_evidence_decision_config.*`.

Compile diagnostics over an exact multi-package roster, optionally binding one accepted state per
program for committed-ledger replay:

```bash
adds-clinical-evidence cohort \
  --manifest clinical-cohort-manifest.json \
  --package policy-a-package.json \
  --package policy-b-package.json \
  --state accepted-program-state.json \
  --output clinical-cohort-report.json
```

This report separates packages, programs, and exact evidence units; compares policies only on
shared evidence units; and reports cross-unit source-hash/trial-id reuse. It contains no outcome
labels or performance metrics and cannot establish policy calibration.

Evaluate separately registered package-bound probabilities only after an independently curated
outcome manifest is frozen:

```bash
adds-clinical-evidence evaluate-outcomes \
  --protocol clinical-outcome-protocol.json \
  --cohort-report clinical-cohort-report.json \
  --submission policy-a-predictions.json \
  --submission policy-b-predictions.json \
  --outcomes evaluator-only-outcomes.json \
  --output aggregate-clinical-outcome-report.json
```

This path requires post-deadline endpoint and safety sources, preserves indeterminate attrition,
and reports aggregate Brier, calibration, threshold, Wilson, and matched-policy metrics. Package
workflow decisions are never treated as clinical outcome labels.

Estimate dependence-aware uncertainty only after the public uncertainty protocol and private
dependence assignments have been frozen:

```bash
adds-clinical-evidence evaluate-uncertainty \
  --uncertainty-protocol clinical-uncertainty-protocol.json \
  --dependence-manifest evaluator-only-dependence.json \
  --outcome-protocol clinical-outcome-protocol.json \
  --cohort-report clinical-cohort-report.json \
  --submission policy-a-predictions.json \
  --submission policy-b-predictions.json \
  --outcomes evaluator-only-outcomes.json \
  --outcome-report aggregate-clinical-outcome-report.json \
  --output aggregate-clinical-uncertainty-report.json
```

The evaluator checks exact unit coverage and prevents known shared program, baseline trial/source,
or outcome trial/source links from being split across clusters. Public output contains only
aggregate CR1 diagnostics and intervals; unit assignments and cluster-level results remain private.

Before selecting the cluster floor and dominance limit for a real board, run the prospective
design contract over fixed stage-by-endpoint scenarios:

```bash
adds-clinical-evidence simulate-uncertainty-design \
  --protocol rl_env/specs/clinical_outcome_design_simulation_protocol.example.json \
  --output prospective-clinical-design-report.json
adds-clinical-evidence validate-uncertainty-design \
  --report prospective-clinical-design-report.json \
  --protocol rl_env/specs/clinical_outcome_design_simulation_protocol.example.json
```

The seeded beta-binomial simulator calls the production CR1 estimator, compares an explicitly
diagnostic IID reference, retains Monte Carlo Wilson bounds for coverage and interval yield, and
publishes no replicate- or unit-level records. Candidate gates are screened against declared
targets but are never selected automatically.

Stress the two assumptions separately before treating a candidate gate as transportable:

```bash
adds-clinical-evidence simulate-uncertainty-stress \
  --protocol rl_env/specs/clinical_outcome_stress_simulation_protocol.example.json \
  --output prospective-clinical-stress-report.json
adds-clinical-evidence validate-uncertainty-stress \
  --report prospective-clinical-stress-report.json \
  --protocol rl_env/specs/clinical_outcome_stress_simulation_protocol.example.json
```

This seeded extension compares the same aggregate estimates against population and evaluable
truths under nominal and exact synthetic dependence-closed cluster assignments. It distinguishes
selection-driven estimand drift from cluster-membership-driven interval miscalibration; it does
not infer hidden links or automatically correct missing outcomes.

Evaluate a preregistered pattern-mixture grid against those same deterministic streams:

```bash
adds-clinical-evidence analyze-pattern-mixture \
  --protocol rl_env/specs/clinical_outcome_pattern_mixture_protocol.example.json \
  --stress-protocol rl_env/specs/clinical_outcome_stress_simulation_protocol.example.json \
  --output clinical-outcome-pattern-mixture-report.json
adds-clinical-evidence validate-pattern-mixture \
  --report clinical-outcome-pattern-mixture-report.json \
  --protocol rl_env/specs/clinical_outcome_pattern_mixture_protocol.example.json \
  --stress-protocol rl_env/specs/clinical_outcome_stress_simulation_protocol.example.json
```

The prediction-stratified binary log-IMOR analysis uses only observable total/evaluable/favorable
counts for operational grid estimates. Synthetic truth is retained only for aggregate recovery
diagnostics. Point-envelope inclusion is descriptive, not confidence coverage; no missingness
range is learned or selected from hidden outcomes.

Add sampling uncertainty at every fixed grid assumption while comparing nominal and declared
dependence-closed resampling units:

```bash
adds-clinical-evidence analyze-pattern-mixture-uncertainty \
  --protocol rl_env/specs/clinical_outcome_pattern_mixture_uncertainty_protocol.example.json \
  --pattern-mixture-protocol rl_env/specs/clinical_outcome_pattern_mixture_protocol.example.json \
  --stress-protocol rl_env/specs/clinical_outcome_stress_simulation_protocol.example.json \
  --output clinical-outcome-pattern-mixture-uncertainty-report.json
```

The public synthetic report reproduces the prior point curve exactly, retains Monte Carlo bounds
for continuous bias and width summaries, and shows hidden-linkage undercoverage under nominal
clustering with recovery after dependence closure. It never infers the closure or combines the
sampling interval with the identifying-assumption grid into one confidence set.

Compare small- and unequal-cluster interval constructions on the dedicated public study:

```bash
adds-clinical-evidence calibrate-pattern-mixture-influence \
  --protocol rl_env/specs/clinical_outcome_pattern_mixture_influence_protocol.example.json \
  --pattern-mixture-protocol rl_env/specs/clinical_outcome_pattern_mixture_influence_pattern_protocol.example.json \
  --stress-protocol rl_env/specs/clinical_outcome_pattern_mixture_influence_stress_protocol.example.json \
  --output clinical-outcome-pattern-mixture-influence-report.json
```

The 500-replicate study preserves all production-eligibility gates, supports `t_(G-1)` as the
minimum small-cluster upgrade, and retains delete-`m_j` as an unequal-size influence sensitivity.
The one-step Webb multiplier remains experimental because its all-cell coverage target fails in
both balanced scenarios. See `docs/36_unequal_cluster_influence_calibration.md` for formulas,
results, and claim boundaries.

Compare unit-weighted and cluster-balanced targets when outcome prevalence is associated with
cluster size:

```bash
adds-clinical-evidence analyze-informative-cluster-size \
  --protocol rl_env/specs/clinical_outcome_informative_cluster_size_protocol.example.json \
  --stress-protocol rl_env/specs/clinical_outcome_informative_cluster_size_stress_protocol.example.json \
  --output clinical-outcome-informative-cluster-size-report.json
```

The public study shows that the two known truths coincide under null size-outcome association and
take opposite benefit-risk directions under positive and negative informative-size profiles. All
methods remain nearly unbiased for their declared target, while fixed-profile heterogeneity makes
conventional jackknife intervals overconservative. Delete-`m_j` reduces some influence
concentration but does not change the unit-weighted estimand. See
`docs/37_informative_cluster_size_estimands.md` for the sampling-frame interpretation and results.

Separate fixed-profile conditional variation from cluster-superpopulation variation while
preserving the same known truths:

```bash
adds-clinical-evidence analyze-cluster-superpopulation \
  --protocol rl_env/specs/clinical_outcome_cluster_superpopulation_protocol.example.json \
  --stress-protocol rl_env/specs/clinical_outcome_informative_cluster_size_stress_protocol.example.json \
  --fixed-profile-protocol rl_env/specs/clinical_outcome_informative_cluster_size_protocol.example.json \
  --fixed-profile-report rl_env/specs/clinical_outcome_informative_cluster_size_report.example.json \
  --output clinical-outcome-cluster-superpopulation-report.json
```

Uniform empirical-template resampling restores SE calibration in all `320` fixed-profile failure
cells, moving the aggregate SE pass count from `280/600` to `600/600`. Full calibration reaches
`520/600`: the dominant informative scenario still exposes unit-weighted finite-cluster bias and
undercoverage, so calibrated SE scaling is not treated as operational eligibility. See
`docs/38_cluster_superpopulation_sampling.md` for the sampling model, estimands, results, and
transport boundary.

## Core Question

Can a long-horizon discovery process be represented as an agentic environment where:

- intermediate states are explicit and queryable,
- tools and SFMs generate structured evidence,
- deterministic verifiers enforce hard constraints,
- soft verifiers score uncertainty, evidence quality, and scientific plausibility,
- success and failure trajectories become training/evaluation data,
- reward design can support RL or RLVR-style optimization?

## Current State (honest scope)

The public 0.2.0 release provides a **retrospective clinical and regulatory
decision benchmark with source-derived labels (generated without human
curation), plus one audited end-to-end vertical slice**. The public 0.3.0.dev2
baseline adds a typed execution, evaluation, clinical-evidence planning,
reviewer-governed closed-loop, and bounded registry-harmonization backbone
around those artifacts. The 0.3.0.dev3 candidate adds the clinical outcome,
dependence, pattern-mixture, and influence-calibration research described below;
it has not been merged or uploaded. It is not yet the complete autonomous eight-stage
system or full trajectory atlas described in the roadmap. Honest status:

- **Executable bounded agent loop:** `agentic_drug_discovery/` provides typed evidence, claims,
  targets, candidates, accepted-packet/action/decision/verifier ledgers, program state, decision packets,
  stage gates, budget accounting, chronology checks, evidence-polarity validation, contradiction
  handling, and fail-closed transitions. A bounded planner validates contracts, state/version,
  stage, duplicate requests, step limits, and the complete required-call budget before spending.
  The stage runner rejects missing or post-cutoff promotion context before invocation, executes
  typed calls, applies operation-specific semantic mappers, proposes a packet, and records both
  rejected attempts and accepted recovery packets for exact replay. A typed program coordinator
  chains stage plans over one cumulative execution ledger, verifies state continuity, stops on
  defer/hold/pivot/kill or blocked execution, and exposes an exact accepted-packet replay bundle.
  A typed policy layer can map an exact paused/blocked observation to predeclared replacement
  steps, enforce per-rule and global replan limits, and resume only from a SHA-256-bound checkpoint
  containing the complete state, execution ledger, plan queue, and append-only replan history.
- **Evaluation contract:** matched success/failure episode types require an exact disease, stage,
  modality, population, endpoint-family, target/mechanism, and decision-time match. Evidence is
  cutoff-bounded, evaluator-only keys are rejected from visible state, and failure arms require
  explicit failure causes. A second layer emits role-neutral sealed boards with embedded,
  hash-verified cached tool packets; salted external label commitments; fingerprint-bound policy
  submissions; and exact, arm-specific, both-correct, unsafe-advance, and descriptive confidence
  metrics. One external 4-pair/8-episode retrospective contract evaluation is summarized publicly;
  the full board and labels are not released, and this is not a scientific performance result. A
  third layer now preregisters cohort, label, curator-roster, outcome-window, stage-minimum, and
  metric commitments; validates independent strict-majority or adjudicated curation; and emits
  exact-count stage strata with Wilson intervals, action coverage, and selective risk. That layer
  currently has synthetic contract coverage only.
- **Pinned composite evidence gates:** disease-context advance now requires independently sourced,
  SHA-256-pinned disease-burden and treatment-gap events linked to one supported unmet-need claim.
  Preclinical advance likewise requires independent candidate-target functional and disease-model
  effect events with typed endpoints, candidate-name continuity, and disjoint upstream publication
  lineages. Multi-source outcomes require each evidence draft to select its source explicitly; a
  tool payload hash is no longer mislabeled as an external source-content hash.
- **Pinned public-source ingestion:** `adds-pinned-ingestion` captures exact HTTPS or reviewed local
  source bytes into immutable bundles outside Git, records byte size and SHA-256 in a payload-free
  receipt, and compiles reviewer-authored summaries into the existing pinned manifest plus a
  machine-readable review report. Compilation rechecks source bytes, chronology, schema, raw-field,
  summary-size, finite-number, local-path, and exact-content-reuse boundaries. Reusing the same
  bytes under different source ids cannot satisfy independence. Reports always require human
  review; the compiler does not infer scientific meaning from source text.
- **CDC MMWR provider contract:** `extract-cdc-mmwr` verifies a reviewer-selected disease-burden or
  treatment-gap value against a captured CDC MMWR article's receipt, DOI-bound version, canonical
  URL, citation metadata, section, excerpt, numeric value, unit, geography, and reference period.
  It emits a generic payload-free ingestion job with an excerpt hash, then leaves scientific and
  release approval to the existing review gates. Only synthetic provider fixtures are in the repo;
  the verified real CDC snapshot and reviewer job remain external.
- **NCBI PubMed treatment-gap contract:** `extract-ncbi-pubmed` verifies one reviewer-selected
  treatment-gap statement against captured PubMed EFetch XML. Direct PMID, PMCID, DOI, title, and
  electronic-publication identity must agree; METHODS/RESULTS excerpts, comparator, value, unit,
  population, geography, period, and treatment anchors must each resolve unambiguously. The
  sanitized job retains hashes rather than abstract text. A real PMID 32147964 extraction passes
  externally, while combination with the broader 2018 CDC burden correctly defers on population
  and evidence-context mismatch.
- **ChEMBL functional-activity contract:** `extract-chembl-activity` verifies one release-bound
  status/activity/assay/document/molecule/target bundle. Linked identifiers, release identity,
  standardized point estimate, source assay classification, direct single-protein assignment,
  molecule aliases, target component, and publication lineage must agree before a typed functional
  record is emitted. Assay text is removed and replaced by hashes.
- **NCBI PubMed disease-model contract:** `extract-ncbi-pubmed-disease-model` verifies a typed
  in-vivo result against one exact EFetch record, including article identity, candidate and model
  anchors, dose, route, frequency, duration, endpoint, variation, and p-value. A matched external
  ChEMBL 37/PubMed check advances with independent lineages and defers when only a shared upstream
  publication lineage is introduced; public fixtures remain synthetic.
- **Cross-stage target identity continuity:** Open Targets target nomination now creates an
  evidence-backed `TargetRecord` with Ensembl, gene-symbol, disease, and organism identity. A
  stronger ChEMBL composite operation verifies the target profile, molecule, and mechanism before
  adding ChEMBL target and optional UniProt bindings. Namespace rebinding, collisions, broken
  candidate links, and target-profile symbol mismatches fail closed. Candidate, lead, and
  preclinical advances must preserve the same target record.
- **Discovery-context identity continuity:** disease context creates an evidence-backed
  `DiseaseRecord` that every advance must preserve. Pinned preclinical promotion creates typed
  `AssayRecord` and `ModelSystemRecord` updates linked to the accepted disease, target, candidate,
  organism, and source-pinned evidence. Removal, rebinding, namespace collision, unknown-candidate
  evidence, and cross-context links fail closed; preclinical advance requires both records in the
  current packet.
- **Clinical intervention and design identity continuity:** Legacy `ctgov/search_trials` results
  remain contextual and cannot advance the default clinical gate. The source-pinned
  `clinical_trial_design` path binds one exact ClinicalTrials.gov receipt to canonical
  `InterventionRecord`, `TrialRecord`, and atomic `TrialDesignRecord` updates containing typed
  candidate/comparator arms, population, posted endpoint, and serious-adverse-event identities.
  Receipt, NCT, registry version, condition, aliases, protocol/result/adverse-event groups,
  denominators, endpoint analysis, and safety affected/at-risk counts must all agree. Arm-role
  rebinding, endpoint/safety-support removal, partial design projection, namespace collisions, and
  source mismatch fail closed. EMA can extend the accepted intervention only after a source asset
  or INN match.
- **Multi-trial portfolio and endpoint mapping:** A portfolio extractor verifies the complete set of
  independently reviewed single-trial jobs and external ClinicalTrials.gov bundles before emitting
  one payload-free ingestion job. Job, receipt, NCT, design, endpoint, safety, candidate,
  intervention, and disease identities must agree, and trial source hashes must be pairwise
  disjoint. A separate local operation binds reviewer, review time, endpoint family, ontology
  identity, and the exact ordered trial selections into an append-only
  `ClinicalEndpointMappingRecord`. It performs no endpoint-name inference or ontology-authority
  lookup; mapping removal, rebound, and direct-commit bypass fail closed.
- **Cross-trial endpoint/safety harmonization:** A local deterministic synthesis operation accepts
  only selections that exactly match a committed approved endpoint mapping. It recompiles supported
  hazard, odds, or risk ratios under fixed favorable-direction contracts,
  confidence intervals, source arm measurements, and serious-adverse-event affected/at-risk counts
  from at least two source-disjoint committed trial designs. Trial-level values and source hashes
  remain intact; automatic endpoint-name mapping, cross-trial pooling, benefit-risk scoring,
  population comparability, and clinical acceptability inference are prohibited by typed records
  and a replay-time continuity verifier.
- **Clinical evidence tensor and bounded VOI planning:** A committed synthesis can be recompiled
  into exact per-trial endpoint/safety cells, ten policy-relative evidence dimensions, and
  provenance-linked gap records. A preregistered action catalog supplies gap-resolution
  probability, decision relevance, and maximum cost; deterministic marginal VOI ranking selects a
  bounded evidence-acquisition batch against the live budget ledger. Integrity fingerprints bind
  synthesis, policy, tensor, catalog, and plan, and strict replay rejects tampering. `ADVANCE`
  means only that evidence-workflow criteria are satisfied; clinical acceptability, terminal
  decisions, pooling, and calibrated economic VOI claims remain prohibited.
- **Provenance-preserving clinical evidence closed loop:** Selected bounded-VOI actions compile
  into exact state-bound calls for the existing fail-closed runner. Compact receipts bind request,
  contract, payload hash, source hash, cost, accepted packet, action, and promoted evidence;
  bounded reviewer-only verifier runs append a refreshed endpoint mapping and synthesis. The
  after decision package removes attempted action ids from its residual catalog and can mark a gap
  resolved only when a successful targeted receipt promotes evidence whose exact source hash enters
  the after tensor. The transition remains
  evidence-workflow-only and cannot issue a provider, terminal, treatment, or acceptability
  decision.
- **Clinical cohort diagnostics and matched policy sensitivity:** An integrity-bound manifest
  fixes an exact package roster and can bind accepted `ProgramState` hashes for full committed-
  ledger replay. Reports distinguish packages, programs, and synthesis-bound evidence units;
  retain exact decision/gap/action denominators; compare policy pairs only on shared evidence;
  and expose cross-unit source-hash and trial-id reuse. The layer includes no outcomes and makes no
  correctness, clinical utility, safety, superiority, or calibration claim.
- **Preregistered clinical outcome evaluation:** A public protocol binds an exact outcome-free
  cohort report, prediction deadline, endpoint/safety harmonization and outcome definitions,
  curator-roster commitment, fixed calibration bins, threshold, confidence level, and minimum
  evaluable units. Frozen policy submissions bind favorable composite benefit-risk probabilities
  to exact package and evidence-unit hashes. Evaluator-only manifests require post-deadline source
  provenance and blinded independent endpoint/safety assessment; public reports retain only
  attrition, Brier/calibration/threshold metrics, Wilson intervals, paired policy comparisons,
  overlap counts, and limitations. The checked-in result is a one-unit synthetic contract test,
  not calibration or clinical-performance evidence.
- **Dependence-aware clinical outcome uncertainty:** A second public preregistration binds the exact
  outcome protocol, cohort report, private dependence-manifest commitment, cluster construction
  policy, confidence level, dominance threshold, and minimum cluster count before submissions. The
  evaluator verifies known-overlap closure and emits aggregate CR1 intervals for favorable rate,
  Brier score, calibration-in-the-large, and threshold accuracy overall and by fixed
  stage-by-endpoint strata, plus an overall paired Brier-difference interval. Intervals fail closed
  for insufficient clusters, dominant clusters, or cluster uncertainty that rounds to zero at the
  reporting precision. The later
  evaluator fully replays and fingerprints the base outcome report. The one-cluster public example
  intentionally emits no interval and makes no superiority or validated-coverage claim.
- **Prospective clustered-board design simulation:** Fixed stage-by-endpoint scenarios declare an
  exact cluster-size vector, favorable prevalence, ICC, MCAR evaluability, and two
  outcome-independent probability patterns. A deterministic beta-binomial Polya urn generates
  known-truth replicates; the production CR1 diagnostic/estimator and an IID unit-as-cluster
  reference are evaluated for bias, RMSE, coverage, width, interval yield, and all fail-closed
  statuses. Candidate gates pass only when every metric's Monte Carlo Wilson lower bounds meet
  preregistered coverage and yield targets. The aggregate synthetic report does not select a
  universal gate or validate a real board.
- **Informative-evaluability and dependence-closure stress:** Exact partitions can join multiple
  nominal clusters into synthetic dependence blocks, while separate favorable and unfavorable
  evaluability probabilities induce a known complete-record estimand shift. Every estimate is
  evaluated against both population and evaluable truths under nominal and oracle
  dependence-closed CR1 analysis. Aggregate reports retain coverage, error, width, yield, and
  fail-closed statuses without unit or replicate records. The oracle comparison diagnoses but does
  not detect hidden dependence, identify a population estimand, or apply a missing-data correction.
- **Preregistered pattern-mixture sensitivity:** A protocol fingerprint binds a unique increasing
  binary log-IMOR grid to the exact stress design. Observable prediction-stratum counts generate
  model-implied population metrics across the grid. Matched diagnostics separately test evaluable
  calibration, evaluator-only truth-aligned recovery, and mean-curve population identification;
  sparse or single-class reference strata fail closed. The point envelope contains no sampling
  interval and no real range is selected automatically.
- **Dependence-closed pattern-mixture sampling uncertainty:** A second protocol binds the exact
  stress protocol, sensitivity protocol, and point report before adding delete-one-cluster
  jackknife intervals to every fixed log-IMOR model functional. Nominal and declared
  dependence-closed modes are compared; continuous bias/width summaries carry Monte Carlo bounds;
  cluster-count, enrolled-unit dominance, leave-one-out support, and rounded-zero variance fail
  closed. Synthetic oracle closure is never discovered automatically and is not a real-board
  coverage guarantee.
- **Unequal-cluster influence calibration:** A third bound protocol compares delete-one normal,
  delete-one `t_(G-1)`, unequal delete-`m_j` `t_(G-1)`, and an experimental variance-matched Webb
  multiplier over identical seeded samples. Equal-size variance reduction, Student-t coverage
  noninferiority, multiplier RNG isolation, dominance hard stops, Monte Carlo gates, and strict
  aggregate replay are executable contracts. No method is automatically selected, and passing a
  synthetic interval gate cannot make a dominant-cluster design production eligible.
- **Built & audited:** source-derived label authority plus scoped construct-validity controls;
  callable tool/DB adapters
  (ClinicalTrials.gov, openFDA, Open Targets, ChEMBL, EMA EPAR) and multi-stage flow orchestrators;
  typed bindings for Open Targets, ChEMBL, ClinicalTrials.gov, EMA, Boltz-2, and RDKit molprops;
  a dependency-free source-pinned evidence-manifest adapter, capture/compiler CLI, and
  machine-readable receipt/job/review, disease-context, preclinical, clinical provider, and
  clinical portfolio, endpoint mapping, cross-trial synthesis, clinical evidence decision,
  cohort manifest/report/summary, clinical outcome protocol/prediction/outcome/report/summary,
  clinical outcome dependence/uncertainty protocol/report/summary, prospective clustered-board
  design protocol/report/summary, informative-evaluability/dependence stress
  protocol/report/summary, pattern-mixture sensitivity protocol/report/summary,
  pattern-mixture cluster-jackknife protocol/report/summary, unequal-cluster influence-calibration
  protocol/report/summary, and
  closed-loop transition,
  sealed-board, label-vault, policy-submission, policy-report, held-out protocol,
  curator-manifest, and stage-stratified report schemas;
  one disease/target slice (sickle cell) traversed retrospectively; one synthetic ulcerative-colitis
  cross-disease conformance slice, two payload-free public-source UC induction contract runs, and
  one payload-free induction/maintenance population-alignment run from a single non-pooled trial;
  an unscored
  prospective scaffold whose stale example is invalidated pending source refresh;
  conditional local RDKit druglikeness screening; and aggregate retrospective
  risk analysis. Local calibration cards and locked replay artifacts are excluded.
- **Mapped operations:** Open Targets disease identity and Ensembl-resolved target association;
  ChEMBL molecule-target-mechanism continuity, legacy molecule-mechanism context, molecule
  identity, and target activity volume; RDKit
  molecular properties; contextual ClinicalTrials.gov search results; source-pinned
  ClinicalTrials.gov trial designs; reviewer-approved endpoint mapping; deterministic non-pooled
  clinical benefit-risk synthesis; provenance-preserving clinical evidence tensor compilation and
  bounded evidence-action prioritization; matched multi-package policy sensitivity and provenance
  overlap diagnostics; bounded selected-action execution, reviewer-only
  refresh, and exact source-rejoined decision transition; a generic contextual-only cell-state and
  perturbation handoff with source, assay, endpoint, uncertainty, sampling, QC, and lineage
  continuity; EMA
  regulatory status; and structured
  Boltz binding output; and source-pinned unmet-need and candidate functional-effect profiles have
  conservative mappings. Disease identity does not establish unmet need, ChEMBL activity volume
  does not establish candidate functional effect, and Boltz output is contextual prediction
  evidence only. The pinned profiles advance only when both required component records pass exact
  identity, date, source, hash, typed endpoint, candidate alias, and lineage-independence checks.
- **Roadmap (not yet built):** 7 of 8 atlases (compound/ADMET/target/structure/cell) hold no
  standalone data; the CDC/PubMed unmet-need path still has no release-approved context-matched real
  composite manifest. ChEMBL functional-activity and PubMed disease-model providers now pass one
  external context-matched pair, but no real provider job or compiled manifest is release-approved.
  There is no public real per-episode trajectory corpus; broader clinical endpoint families, participant-
  level reanalysis, event-level causality, live ontology-authority resolution and terminology
  validation, statistically justified pooling, soft-verifier calibration,
  a real independently curated multi-stage held-out board, candidate edit/rank loops, and
  learned or dynamically generated replanning, operator reauthorization workflows, and a real
  independently curated, prospectively cluster-designed clinical outcome board with a
  real-scenario-justified cluster floor and dominance threshold remain future work. Boltz scoring
  needs a GPU endpoint, while RDKit molprops runs locally when installed.
- **Read the caveats first:** headline demo numbers are small-N and on one well-characterized disease;
  the 80/80 prompt result repeats the same eight assets and is a regression check, not independent
  validation. Do not read this as a finished long-horizon agent platform.

## Current Anchors

- `docs/`: design notes; `docs/12_scd_vertical_slice.md` is the audited SCD slice,
  `docs/13_target_id_governance_node.md` is the upstream target-node results card,
  `docs/14_target_identity_continuity.md` is the executable cross-stage identity contract,
  `docs/15_discovery_context_identity.md` covers disease, assay, and model-system continuity,
  `docs/16_clinical_intervention_identity.md` covers candidate, intervention, trial-design, and
  regulatory identity continuity, `docs/17_pinned_source_ingestion.md` covers exact source capture and
  payload-free compilation, `docs/18_cdc_mmwr_ingestion.md` covers provider-specific CDC article
  and evidence-location verification, `docs/19_ncbi_pubmed_ingestion.md` covers strict PubMed XML
  treatment-gap extraction and cross-population defer behavior,
  `docs/20_preclinical_provider_ingestion.md` covers ChEMBL functional-activity and PubMed
  disease-model extraction plus lineage-independent composite promotion, and
  `docs/preclinical_provider_validation_snapshot.json` is the payload-free machine snapshot of the
  external matched provider run. `docs/21_clinical_provider_ingestion.md` and
  `docs/clinical_provider_validation_snapshot.json` describe the exact ClinicalTrials.gov
  endpoint/safety design contract and its payload-free external validation.
  `docs/42_uc_provider_validation.md` and
  `docs/uc_clinical_provider_validation_snapshot.json` record two additional public-source UC
  induction runs that retain uncertain evidence on `HOLD` and advance a bounded favorable result.
  `docs/22_clinical_benefit_risk_synthesis.md` defines the explicit, source-disjoint, non-pooled
  cross-trial synthesis contract, and `docs/23_clinical_portfolio_endpoint_mapping.md` defines the
  multi-bundle portfolio transaction and append-only reviewer-approved mapping ledger.
  `docs/24_policy_replanning_and_resume.md` defines bounded policy rules, hash-bound checkpoints,
  deterministic resume, and the non-public checkpoint payload boundary.
  `docs/25_cutoff_safe_policy_evaluation.md` defines role-neutral sealed boards, external label
  commitments, policy comparison, and the external real-board boundary;
  `docs/retrospective_policy_evaluation_snapshot.json` carries aggregate-only results and hashes.
  `docs/26_independent_heldout_evaluation.md` defines preregistration, opaque curator commitments,
  blinded curation, stage minima, Wilson intervals, action coverage, and selective risk; it
  explicitly records that no real independently curated result exists yet.
  `docs/27_clinical_evidence_tensor_and_voi.md` defines exact evidence cells, policy-relative gap
  ontology, deterministic bounded VOI action ranking, budget semantics, integrity envelopes, and
  the evidence-workflow-only decision boundary.
  `docs/28_clinical_evidence_closed_loop.md` defines exact selected-action execution, compact
  provider receipts, reviewer-verifier refresh bounds, source rejoin, single-use actions, and
  before/after transition validation.
  `docs/29_clinical_cohort_diagnostics.md` defines exact package/state rosters, evidence-unit
  identity, package and policy strata, matched policy sensitivity, provenance-overlap reporting,
  and the explicit no-outcome/no-calibration boundary.
  `docs/30_preregistered_clinical_outcome_evaluation.md` defines package-bound probabilistic
  forecasts, cutoff-safe endpoint/safety outcomes, conservative composite labels, aggregate
  calibration and threshold metrics, paired policy evaluation, and the evaluator-only unit-level
  boundary. `docs/31_cluster_robust_clinical_outcome_uncertainty.md` defines private dependence
  assignments, known-overlap closure, stage-by-endpoint strata, aggregate CR1 inference, explicit
  non-estimable states, and the no-superiority boundary.
  `docs/32_prospective_clinical_outcome_design_simulation.md` defines deterministic beta-binomial
  scenario generation, analytic metric truths, production-estimator parity, IID diagnostic
  comparison, Monte Carlo target checks, and the no-automatic-selection boundary.
  `docs/33_informative_evaluability_and_dependence_stress.md` defines analytic population and
  evaluable targets, exact dependence blocks, nominal/oracle-closure CR1 comparison, reproducible
  stress signatures, and the no-automatic-correction boundary.
  `docs/34_preregistered_pattern_mixture_sensitivity.md` defines the binary log-IMOR parameter,
  prediction-stratum observability contract, matched recovery gates, point-envelope interpretation,
  aggregate public results, and the no-automatic-range-selection boundary.
  `docs/35_dependence_closed_pattern_mixture_uncertainty.md` defines fixed-assumption model
  functionals, delete-one-cluster variance, all-grid calibration gates, nominal/closed comparison,
  Monte Carlo precision bounds, and the no-automatic-closure boundary.
  `docs/36_unequal_cluster_influence_calibration.md` defines unequal delete-`m_j` pseudovalues,
  `t_(G-1)` intervals, the experimental multiplier boundary, influence and dominance diagnostics,
  public calibration results, and the no-automatic-selection boundary.
  `docs/37_informative_cluster_size_estimands.md` defines unit-weighted and cluster-balanced
  pattern-mixture functionals, fixed block-specific prevalence profiles, estimand-direction drift,
  aggregate max-block influence diagnostics, conditional calibration results, and the
  no-automatic-estimand-selection boundary.
  `docs/38_cluster_superpopulation_sampling.md` defines uniform empirical-template cluster
  resampling, exact preservation of unit- and cluster-weighted known truths, conditional versus
  superpopulation calibration, realized-design and tie-aware influence diagnostics, and the
  no-transportability/no-post-hoc-filtering boundary.
  `docs/public_evidence_summary.json` is the
  aggregate claim ledger.
- `agentic_drug_discovery/`: typed state, bounded planning, tool execution, semantic promotion,
  bounded multi-stage program orchestration, matched and sealed evaluation, strict
  serialization/replay, verifier contracts, and the fail-closed transition engine.
- `tests/`: deterministic regression tests for planning, promotion, matched evaluation, advance,
  defer, pivot, temporal leakage, evidence polarity, action provenance, candidate presence,
  contradictions, budget enforcement, and verifier failure.
- `rl_env/specs/`: state, action, observation, and case-bank schema sketches.
- `rl_env/specs/pinned_evidence_manifest.schema.json`: machine contract for payload-free,
  source-pinned composite-gate records; the adjacent example is synthetic.
- `rl_env/specs/discovery_context_identity.schema.json`: strict disease, assay, and model-system
  record contract; the adjacent example is synthetic.
- `rl_env/specs/clinical_intervention_identity.schema.json`: strict intervention, trial, and atomic
  trial-design record contract; the adjacent example is synthetic.
- `rl_env/specs/clinical_benefit_risk_synthesis.schema.json`: strict reviewed selection contract for
  mapping-gated source-ledger cross-trial harmonization without supplied measurements or automatic
  pooling; the adjacent example is synthetic.
- `rl_env/specs/clinical_evidence_decision_package.schema.json`: strict integrity-bound policy,
  tensor, gap, action-catalog, and bounded-VOI plan contract; the adjacent compiler-generated
  example is synthetic.
- `rl_env/specs/clinical_evidence_closed_loop_transition.schema.json`: strict integrity-bound
  execution-batch, selected-action receipt, reviewer-refresh, source-rejoin, and before/after
  decision contract; the adjacent compiler-generated example is synthetic.
- `rl_env/specs/clinicaltrials_gov_portfolio_job.schema.json` and
  `rl_env/specs/clinical_endpoint_mapping.schema.json`: exact portfolio-set and reviewer-approved
  endpoint-family mapping contracts; adjacent examples are synthetic.
- `rl_env/specs/source_receipt.schema.json` and
  `rl_env/specs/pinned_evidence_ingestion_job.schema.json`: exact source receipt and
  reviewer-authored compilation contracts; adjacent examples are synthetic.
- `rl_env/specs/cdc_mmwr_ingestion_job.schema.json`: CDC MMWR article, context, value, unit, and
  evidence-location contract; the adjacent example is synthetic.
- `rl_env/specs/ncbi_pubmed_ingestion_job.schema.json`: NCBI PubMed article identity, structured
  abstract context, typed treatment-gap value, and anchor contract; the adjacent example is
  synthetic.
- `rl_env/specs/chembl_activity_ingestion_job.schema.json`: release-bound ChEMBL activity, assay,
  document, molecule, target, endpoint, and functional-readout contract; the adjacent example is
  synthetic.
- `rl_env/specs/ncbi_pubmed_disease_model_ingestion_job.schema.json`: NCBI PubMed article,
  candidate/model anchors, exposure regimen, typed endpoint, variation, and p-value contract; the
  adjacent example is synthetic.
- `rl_env/specs/clinicaltrials_gov_ingestion_job.schema.json`: exact ClinicalTrials.gov study,
  candidate/comparator arm, population, posted endpoint, and analysis contract; the adjacent
  example and source fixture are synthetic.
- `adapters/`, `chains/`: callable adapters and flow orchestrators are implemented;
  `adapters/execution_registry.py` maps explicitly supplied adapter instances into typed contracts,
  and `adapters/pinned_evidence_adapter.py` validates public evidence manifests.
- `verifiers/`: legacy evaluator-facing contracts and scaffold; executable deterministic transition
  verifiers live in `agentic_drug_discovery/verifiers.py`.

## Artifact Map

| Path | Audience | Purpose |
| --- | --- | --- |
| `docs/public_release_readiness_plan.md` | Humans | Public-readiness plan, gates, and boundary checklist. |
| `docs/public_launch_checklist.md` | Humans | Final private-to-public launch checklist and approval gates. |
| `docs/release_boundary.md` | Humans + reviewers | What can and cannot enter Git/HF release surfaces. |
| `docs/release_trust_report.md` | Humans + machines | Trust claims, evidence anchors, interpretation warnings, and HF package reproducibility path. |
| `docs/12_scd_vertical_slice.md` | Humans + reviewers | Caveats-first description of the audited SCD vertical slice. |
| `docs/13_target_id_governance_node.md` | Humans + reviewers | Small-N upstream target-identification results card. |
| `docs/14_target_identity_continuity.md` | Humans + agents | Canonical target ledger, stage requirements, and fail-closed identity rules. |
| `docs/15_discovery_context_identity.md` | Humans + agents | Disease, assay, and model-system ledgers, links, stage gates, and matched failure contract. |
| `docs/16_clinical_intervention_identity.md` | Humans + agents | Candidate-to-intervention-to-trial-design continuity, source checks, regulatory extension, and failure contract. |
| `docs/17_pinned_source_ingestion.md` | Humans + agents | Exact external source capture, payload-free compilation, review gates, and control-plane integration. |
| `docs/18_cdc_mmwr_ingestion.md` | Humans + agents | CDC MMWR article binding, reviewer evidence checks, payload-free extraction, and matched stage behavior. |
| `docs/19_ncbi_pubmed_ingestion.md` | Humans + agents | PubMed XML identity, structured abstract anchors, payload-free extraction, and context-mismatch behavior. |
| `docs/20_preclinical_provider_ingestion.md` | Humans + agents | ChEMBL functional-activity and PubMed disease-model contracts, external payload-free validation snapshot, and lineage-independence failure control. |
| `docs/preclinical_provider_validation_snapshot.json` | Machines + reviewers | Payload-free provider ids, typed values, source/job/output hashes, matched outcomes, and limitations for the external validation run. |
| `docs/21_clinical_provider_ingestion.md` | Humans + agents | ClinicalTrials.gov receipt, arm, population, endpoint, serious-adverse-event summary, bounded promotion, and atomic-failure contract. |
| `docs/clinical_provider_validation_snapshot.json` | Machines + reviewers | Payload-free NCT/design ids, typed values, artifact hashes, stage outcome, matched control, and limitations. |
| `docs/42_uc_provider_validation.md` | Humans + agents | Two public-source UC induction contract runs, direction-aware gating, phase identity, safety aggregates, and non-pooling limits. |
| `docs/uc_clinical_provider_validation_snapshot.json` | Machines + reviewers | Payload-free UC source/job/output/manifest hashes, selected typed values, decisions, and replay limits. |
| `docs/22_clinical_benefit_risk_synthesis.md` | Humans + agents | Explicit cross-trial selection, retained trial values, source-disjoint provenance, non-pooling boundary, and fail-closed behavior. |
| `docs/23_clinical_portfolio_endpoint_mapping.md` | Humans + agents | Multi-bundle preflight, approved ontology identity, exact endpoint bindings, mapping ledger, synthesis dependency, and release limitations. |
| `docs/24_policy_replanning_and_resume.md` | Humans + agents | Typed non-advance observations, bounded replan rules, hash-bound checkpoints, deterministic resume, and release boundaries. |
| `docs/25_cutoff_safe_policy_evaluation.md` | Humans + agents | Cutoff-safe cached packets, role-neutral pair sealing, external label commitments, policy scoring, and claim boundaries. |
| `docs/26_independent_heldout_evaluation.md` | Humans + agents | Preregistered cohort/label/curator contracts, curation validation, stage minima, action coverage, selective risk, and uncertainty boundaries. |
| `docs/27_clinical_evidence_tensor_and_voi.md` | Humans + agents | Exact clinical evidence cells, policy-relative gap ontology, bounded VOI action ranking, budget behavior, provenance replay, and interpretation boundaries. |
| `docs/28_clinical_evidence_closed_loop.md` | Humans + agents | Exact selected-action execution, compact receipts, reviewer-only refresh, source rejoin, single-use catalog behavior, and before/after validation. |
| `docs/29_clinical_cohort_diagnostics.md` | Humans + agents | Exact package/state rosters, evidence-unit identity, matched policy sensitivity, action/gap diagnostics, provenance overlap, and calibration boundaries. |
| `docs/30_preregistered_clinical_outcome_evaluation.md` | Humans + agents | Preregistered package-bound forecasts, cutoff-safe endpoint/safety outcomes, aggregate calibration, paired policy metrics, and private evaluator boundaries. |
| `docs/31_cluster_robust_clinical_outcome_uncertainty.md` | Humans + agents | Dependence-manifest commitments, known-overlap closure, stage-by-endpoint CR1 intervals, fail-closed diagnostics, and interpretation boundaries. |
| `docs/32_prospective_clinical_outcome_design_simulation.md` | Humans + agents | Beta-binomial design scenarios, analytic truths, CR1/IID coverage comparison, Monte Carlo target checks, and gate-selection boundaries. |
| `docs/33_informative_evaluability_and_dependence_stress.md` | Humans + agents | Outcome-dependent evaluability, analytic estimand shifts, residual dependence blocks, nominal/oracle-closure CR1 comparison, and correction boundaries. |
| `docs/34_preregistered_pattern_mixture_sensitivity.md` | Humans + agents | Prediction-stratified binary log-IMOR sensitivity, observable aggregate inputs, matched estimand/recovery gates, public synthetic results, and claim boundaries. |
| `docs/35_dependence_closed_pattern_mixture_uncertainty.md` | Humans + agents | Conditional sampling intervals across fixed log-IMOR assumptions, dependence-closed jackknife calibration, Monte Carlo precision, public synthetic results, and claim boundaries. |
| `docs/36_unequal_cluster_influence_calibration.md` | Humans + agents | Few, unequal, and dominant-cluster calibration; Student-t and delete-mj comparisons; experimental multiplier diagnostics; and operational boundaries. |
| `docs/37_informative_cluster_size_estimands.md` | Humans + agents | Unit-weighted versus cluster-balanced functionals, informative-size direction drift, fixed-profile calibration, influence concentration, and estimand-selection boundaries. |
| `docs/38_cluster_superpopulation_sampling.md` | Humans + agents | Empirical-template cluster-superpopulation sampling, preserved known truths, conditional calibration comparison, realized-design diagnostics, and transport boundaries. |
| `docs/retrospective_policy_evaluation_snapshot.json` | Machines + reviewers | Aggregate 4-pair/8-episode policy metrics, payload-free artifact hashes, real gate outcomes, and limitations. |
| `docs/public_evidence_summary.json` | Machines + reviewers | Aggregate-only metrics, provenance limits, and claim boundaries. |
| `agentic_drug_discovery/` | Developers + agents | Bounded planning, typed execution, semantic promotion, multi-stage stop semantics, matched evaluation, replay, and verifier-gated transitions. |
| `agentic_drug_discovery/ingestion.py` | Developers + agents | Immutable source receipts, external bundles, manifest compilation, and review reports. |
| `agentic_drug_discovery/cdc_mmwr.py` | Developers + agents | Strict CDC MMWR article and evidence-location verification with excerpt removal. |
| `agentic_drug_discovery/ncbi_pubmed.py` | Developers + agents | Strict NCBI PubMed EFetch identity and treatment-gap evidence verification with excerpt and anchor removal. |
| `agentic_drug_discovery/chembl_activity.py` | Developers + agents | Strict release-bound ChEMBL resource reconciliation and typed functional-activity extraction with assay-text removal. |
| `agentic_drug_discovery/clinicaltrials_gov.py` | Developers + agents | Strict ClinicalTrials.gov study, endpoint, and serious-adverse-event reconciliation with payload-free trial-design extraction. |
| `agentic_drug_discovery/clinical_portfolio.py` | Developers + agents | Atomic exact-set verification and payload-free extraction for multiple ClinicalTrials.gov jobs and bundles. |
| `agentic_drug_discovery/clinical_endpoint_mapping.py` | Developers + agents | Strict reviewer-approved mapping parser, exact ledger compiler, fingerprints, and continuity recompilation. |
| `agentic_drug_discovery/clinical_synthesis.py` | Developers + agents | Deterministic reviewed-selection compiler for source-disjoint, non-pooled trial-level benefit-risk records. |
| `agentic_drug_discovery/clinical_decision.py` | Developers + agents | Committed-synthesis tensor compiler, typed evidence gaps, deterministic budget-aware VOI planner, strict integrity readers, and state replay. |
| `agentic_drug_discovery/clinical_workflow.py` | Users + agents | Stable config parser, accepted-packet provenance checks, compiler wrapper, validation report, and compact decision summary. |
| `agentic_drug_discovery/clinical_cohort.py` | Developers + agents | State-bindable package rosters, deterministic cohort aggregation, matched policy comparisons, strict integrity readers, and cross-unit provenance overlap. |
| `agentic_drug_discovery/clinical_outcome_evaluation.py` | Developers + evaluators | Clinical outcome protocols, package-bound probability submissions, post-deadline outcome provenance, aggregate calibration, paired policy comparisons, and strict replay. |
| `agentic_drug_discovery/clinical_outcome_uncertainty.py` | Developers + evaluators | Private dependence assignments, known-overlap closure, CR1 diagnostics and intervals, paired covariance, fixed-stratum reporting, strict readers, and full replay. |
| `agentic_drug_discovery/clinical_outcome_design_simulation.py` | Developers + evaluators | Bounded deterministic beta-binomial simulation, analytic metric truths, production-estimator parity, IID diagnostics, candidate-gate evaluation, strict readers, and replay. |
| `agentic_drug_discovery/clinical_outcome_stress_simulation.py` | Developers + evaluators | Bounded block-Polya simulation, analytic population/evaluable truths, nominal/dependence-closed CR1 comparison, strict claim boundaries, readers, summaries, and replay. |
| `agentic_drug_discovery/clinical_outcome_pattern_mixture.py` | Developers + evaluators | Exact stress-bound binary log-IMOR grids, prediction-stratified aggregate estimators, matched calibration/recovery/identification diagnostics, strict readers, summaries, and replay. |
| `agentic_drug_discovery/clinical_outcome_pattern_mixture_uncertainty.py` | Developers + evaluators | Exact point-report binding, nominal/dependence-closed delete-one-cluster jackknife inference, model-functional coverage, Monte Carlo bounds, fail-closed statuses, strict readers, summaries, and replay. |
| `agentic_drug_discovery/clinical_outcome_pattern_mixture_influence_calibration.py` | Developers + evaluators | Student-t critical values, unequal delete-mj pseudovalues, experimental multiplier intervals, production eligibility, Monte Carlo calibration, strict readers, summaries, and replay. |
| `agentic_drug_discovery/clinical_decision_cli.py` | Users + agents | JSON CLI for package/cohort compilation, outcome and uncertainty evaluation, prospective design, stress, pattern-mixture, and cluster-jackknife simulation, full replay validation, and compact summaries. |
| `agentic_drug_discovery/clinical_closed_loop.py` | Developers + agents | State-bound selected-action batches, bounded runner integration, compact execution and refresh receipts, source-rejoined transition compilation, strict readers, and two-state replay validation. |
| `agentic_drug_discovery/policy.py` | Developers + agents | Deterministic policy rules, queue-bound replanning, checkpoint integrity, and exact resume orchestration. |
| `agentic_drug_discovery/sealed_evaluation.py` | Developers + agents | Role-neutral sealed boards, salted label vaults, fingerprint-bound submissions, strict envelope readers, and matched policy metrics. |
| `agentic_drug_discovery/heldout_evaluation.py` | Developers + agents | Preregistered held-out protocols, opaque independent-curator manifests, stage-stratified Wilson metrics, strict readers, and report integrity. |
| `adapters/pinned_evidence_adapter.py` | Developers + agents | Validates payload-free source records for composite unmet-need and functional-effect gates. |
| `adapters/clinical_synthesis_adapter.py` | Developers + agents | Normalizes explicit synthesis specs locally without retrieving or supplying source measurements. |
| `rl_env/specs/pinned_evidence_manifest.schema.json` | Machines + reviewers | JSON Schema for pinned source identity, dates, hashes, contexts, and typed summaries. |
| `rl_env/specs/target_identity_record.schema.json` | Machines + agents | JSON Schema for the evidence-backed cross-stage target record. |
| `rl_env/specs/discovery_context_identity.schema.json` | Machines + agents | JSON Schema for evidence-backed disease, assay, and model-system records. |
| `rl_env/specs/clinical_intervention_identity.schema.json` | Machines + agents | JSON Schema for evidence-backed clinical intervention, trial, and atomic design records. |
| `rl_env/specs/clinical_benefit_risk_synthesis.schema.json` | Machines + agents | JSON Schema for reviewed multi-trial endpoint/safety selections with no supplied measurements. |
| `rl_env/specs/clinical_evidence_decision_config.schema.json` | Machines + agents | JSON Schema for the accepted-synthesis id, policy, action catalog, and stable package identifiers consumed by `adds-clinical-evidence compile`; the adjacent example is synthetic. |
| `rl_env/specs/clinical_evidence_decision_summary.schema.json` | Machines + agents | JSON Schema shared by compact `summarize` output and optional state-replay validation reports. |
| `rl_env/specs/clinical_evidence_decision_package.schema.json` | Machines + agents | JSON Schema for the integrity-bound policy, exact evidence tensor, gaps, action catalog, budget, and bounded-VOI plan; the adjacent example is synthetic. |
| `rl_env/specs/clinical_evidence_decision_package.relaxed.example.json` | Machines + agents | Compiler-generated synthetic `ADVANCE` package over the same evidence unit for reproducible matched-policy sensitivity; no clinical judgment is implied. |
| `rl_env/specs/clinical_evidence_cohort_manifest.schema.json` | Machines + agents | JSON Schema for an exact package roster with optional all-or-none accepted-state SHA-256 bindings; the adjacent example is synthetic. |
| `rl_env/specs/clinical_evidence_cohort_report.schema.json` | Machines + agents | JSON Schema for package/policy strata, matched policy transitions, gap/action diagnostics, provenance overlaps, and explicit no-outcome calibration status; the adjacent example is synthetic. |
| `rl_env/specs/clinical_evidence_cohort_summary.schema.json` | Machines + agents | JSON Schema for compact cohort summaries and optional validation status. |
| `rl_env/specs/clinical_outcome_evaluation_protocol.schema.json` | Machines + reviewers | JSON Schema for exact cohort, cutoff, outcome/harmonization, curator-roster, threshold, bin, and minimum-unit preregistration; the adjacent example is synthetic. |
| `rl_env/specs/clinical_prediction_submission.schema.json` | Machines + evaluators | JSON Schema for package/evidence-unit-bound favorable composite outcome probabilities; adjacent examples are synthetic. |
| `rl_env/specs/clinical_outcome_manifest.schema.json` | Evaluators | JSON Schema for endpoint/safety assessments, post-deadline source provenance, and adjudication commitments; real manifests remain external. |
| `rl_env/specs/clinical_outcome_evaluation_report.schema.json` | Machines + reviewers | JSON Schema for aggregate attrition, Wilson, Brier/calibration/threshold, paired-policy, and provenance-overlap metrics; the adjacent example is synthetic. |
| `rl_env/specs/clinical_outcome_evaluation_summary.schema.json` | Humans + machines | JSON Schema for compact aggregate calibration, paired-policy, and optional replay-validation status. |
| `rl_env/specs/clinical_outcome_dependence_manifest.schema.json` | Evaluators | JSON Schema for exact evaluator-only unit-to-cluster assignments and dependence-basis commitments; the adjacent example is synthetic. |
| `rl_env/specs/clinical_outcome_uncertainty_protocol.schema.json` | Machines + reviewers | JSON Schema for preregistered dependence construction, confidence, cluster floor, dominance, strata, and metric commitments; the adjacent example is synthetic. |
| `rl_env/specs/clinical_outcome_uncertainty_report.schema.json` | Machines + reviewers | JSON Schema for aggregate cluster diagnostics and CR1 policy, stratum, and paired-policy intervals; the adjacent example is synthetic. |
| `rl_env/specs/clinical_outcome_uncertainty_summary.schema.json` | Humans + machines | JSON Schema for compact dependence-aware uncertainty and validation status. |
| `rl_env/specs/clinical_outcome_design_simulation_protocol.schema.json` | Machines + reviewers | JSON Schema for seeded stage-by-endpoint cluster-size, prevalence, ICC, evaluability, prediction-pattern, candidate-gate, and Monte Carlo commitments; the adjacent example is synthetic. |
| `rl_env/specs/clinical_outcome_design_simulation_report.schema.json` | Machines + reviewers | JSON Schema for analytic truths, aggregate replicate diagnostics, IID and CR1 metric performance, gate statuses, and fixed privacy/claim boundaries; the adjacent example is synthetic. |
| `rl_env/specs/clinical_outcome_design_simulation_summary.schema.json` | Humans + machines | JSON Schema for compact scenario/gate coverage, yield, width, error, status, and optional replay-validation output. |
| `rl_env/specs/clinical_outcome_stress_simulation_protocol.schema.json` | Machines + reviewers | JSON Schema for exact dependence partitions, outcome-specific evaluability, both estimand targets, both analysis modes, gates, RNG, and Monte Carlo commitments; the adjacent example is synthetic. |
| `rl_env/specs/clinical_outcome_stress_simulation_report.schema.json` | Machines + reviewers | JSON Schema for analytic estimand shifts, mode-specific structures/diagnostics, target-specific performance, and fixed aggregate-only claim boundaries; the adjacent example is synthetic. |
| `rl_env/specs/clinical_outcome_stress_simulation_summary.schema.json` | Humans + machines | JSON Schema for compact evaluable-only target passage and dependence-closure recovery signatures. |
| `rl_env/specs/clinical_outcome_pattern_mixture_protocol.schema.json` | Machines + reviewers | JSON Schema for exact stress binding, binary log-IMOR grid, analyzability, mean-envelope width, bias, method, and metadata commitments; the adjacent example is synthetic. |
| `rl_env/specs/clinical_outcome_pattern_mixture_report.schema.json` | Machines + reviewers | JSON Schema for aggregate prediction-stratified grid curves, estimand bias, recovery, point-envelope inclusion, fail-closed support, and fixed claim boundaries; the adjacent example is synthetic. |
| `rl_env/specs/clinical_outcome_pattern_mixture_summary.schema.json` | Humans + machines | JSON Schema for compact log-IMOR, analyzability, matched recovery, identification, and claim-boundary diagnostics. |
| `rl_env/specs/clinical_outcome_pattern_mixture_uncertainty_protocol.schema.json` | Machines + reviewers | JSON Schema for exact stress/protocol/report binding, fixed analysis modes, cluster gates, coverage/yield/SE targets, and the preregistered closure anchor; the adjacent example is synthetic. |
| `rl_env/specs/clinical_outcome_pattern_mixture_uncertainty_report.schema.json` | Machines + reviewers | JSON Schema for aggregate grid-level model-functional coverage, population recovery, Monte Carlo bounds, jackknife diagnostics, closure comparisons, and fixed claim boundaries; the adjacent example is synthetic. |
| `rl_env/specs/clinical_outcome_pattern_mixture_uncertainty_summary.schema.json` | Humans + machines | JSON Schema for compact all-grid calibration, truth-aligned coverage, dependence-closure response, and claim-boundary diagnostics. |
| `rl_env/specs/clinical_evidence_closed_loop_transition.schema.json` | Machines + agents | JSON Schema for integrity-bound execution batches, compact provider/reviewer receipts, exact source rejoin, costs, gap transitions, and nested before/after decision packages; the adjacent example is synthetic. |
| `rl_env/specs/clinical_endpoint_mapping.schema.json` | Machines + agents | JSON Schema for approved reviewer, ontology identity, and exact endpoint/safety bindings without measurements. |
| `rl_env/specs/clinicaltrials_gov_portfolio_job.schema.json` | Machines + reviewers | JSON Schema for the exact set of single-trial jobs, receipts, and mapping-bound identities. |
| `rl_env/specs/policy_checkpoint.schema.json` | Machines + reviewers | JSON Schema for hash-bound policy checkpoints, typed pending plans, observations, directives, and replan history. |
| `rl_env/specs/sealed_evaluation_board.schema.json` | Machines + reviewers | JSON Schema for cutoff-safe role-neutral observations and cached policy-visible packets. |
| `rl_env/specs/sealed_evaluation_vault.schema.json` | Evaluators | JSON Schema for external arm, outcome, failure-cause, and commitment-nonce labels. |
| `rl_env/specs/policy_evaluation_submission.schema.json` | Machines + reviewers | JSON Schema for complete observation-fingerprint-bound policy predictions. |
| `rl_env/specs/policy_evaluation_report.schema.json` | Machines + reviewers | JSON Schema for aggregate arm, pair, unsafe-advance, and confidence diagnostics. |
| `rl_env/specs/heldout_evaluation_protocol.schema.json` | Machines + reviewers | JSON Schema for preregistered cohort, label, curator-roster, stage, and metric commitments; the adjacent example is synthetic. |
| `rl_env/specs/heldout_curation_manifest.schema.json` | Evaluators | JSON Schema for opaque curator declarations, votes, consensus, and adjudication; real manifests remain external. |
| `rl_env/specs/stage_stratified_evaluation_report.schema.json` | Machines + reviewers | JSON Schema for exact counts, Wilson intervals, stage sufficiency, action coverage, selective risk, and aggregate provenance; the adjacent example is synthetic. |
| `rl_env/specs/source_receipt.schema.json` | Machines + reviewers | JSON Schema for exact source version, locator, SHA-256, size, retrieval time, and transport. |
| `rl_env/specs/pinned_evidence_ingestion_job.schema.json` | Machines + reviewers | JSON Schema for reviewer-authored summaries linked to captured receipts. |
| `rl_env/specs/cdc_mmwr_ingestion_job.schema.json` | Machines + reviewers | JSON Schema for reviewer-selected CDC MMWR article, context, value, unit, and excerpt fields. |
| `rl_env/specs/ncbi_pubmed_ingestion_job.schema.json` | Machines + reviewers | JSON Schema for reviewer-selected PubMed article, METHODS/RESULTS evidence, typed gap value, and context anchors. |
| `rl_env/specs/chembl_activity_ingestion_job.schema.json` | Machines + reviewers | JSON Schema for linked ChEMBL release resources, typed functional endpoint, target, candidate aliases, and publication lineage. |
| `rl_env/specs/ncbi_pubmed_disease_model_ingestion_job.schema.json` | Machines + reviewers | JSON Schema for a typed in-vivo exposure, endpoint, variation, p-value, model, and candidate review job. |
| `rl_env/specs/clinicaltrials_gov_ingestion_job.schema.json` | Machines + reviewers | JSON Schema for exact registry, arm, population, endpoint, measurement, analysis, and serious-adverse-event review fields. |
| `tests/` | Developers + CI | Fail-closed control-plane regression tests. |
| `tests/test_clinical_benefit_risk_synthesis.py` | Developers + reviewers | Two-source tool-to-replay synthesis and clinical decision paths plus mismatch, overlap, pooling, forgery, unbound support, safety-signal, budget, deterministic-ranking, integrity, and removal controls. |
| `tests/test_clinical_decision_cli.py` | Users + CI | Config/schema synchronization, exact public-package reproduction, accepted-packet provenance, strict JSON, atomic output, CLI validation, and compact-summary coverage. |
| `tests/test_clinical_cohort.py` | Users + CI | State-bound roster replay, matched policy sensitivity, provenance overlap, strict schema/readers, tamper rejection, and atomic cohort CLI coverage. |
| `tests/test_clinical_outcome_evaluation.py` | Users + evaluators + CI | Cutoff leakage, source novelty, package/policy/roster binding, attrition, Brier/calibration math, paired comparisons, strict schemas/readers, and atomic outcome CLI coverage. |
| `tests/test_clinical_outcome_uncertainty.py` | Users + evaluators + CI | CR1 math, paired covariance, fixed strata, chronology, known-overlap closure, small/dominant/zero-variance cluster states, strict readers, privacy, and atomic CLI coverage. |
| `tests/test_clinical_outcome_design_simulation.py` | Users + evaluators + CI | Analytic truths, exact seeded replay, ICC undercoverage stress, floor/dominance/attrition states, strict bounds/readers, privacy, schemas, and atomic simulation CLI coverage. |
| `tests/test_clinical_outcome_stress_simulation.py` | Users + evaluators + CI | Analytic estimand shifts, informative-selection bias, hidden-linkage undercoverage, oracle-closure recovery, combined stress, exact partitions, strict readers, privacy, schemas, and atomic CLI coverage. |
| `tests/test_clinical_outcome_pattern_mixture.py` | Users + evaluators + CI | Binary log-IMOR recovery, grid-exclusion controls, MCAR, sparse-stratum failure, exact binding/replay, strict readers, privacy, schemas, and atomic CLI coverage. |
| `tests/test_clinical_outcome_pattern_mixture_uncertainty.py` | Users + evaluators + CI | All-grid jackknife calibration, hidden-linkage repair, independent-mode equivalence, model-functional/population separation, Monte Carlo bounds, fail-closed states, exact replay, privacy, schemas, and CLI coverage. |
| `tests/test_clinical_outcome_pattern_mixture_influence_calibration.py` | Users + evaluators + CI | Student-t references, delete-mj algebra, seed isolation, dominant-cluster hard stops, strict schemas/readers, public exact replay, and CLI coverage. |
| `tests/test_clinical_portfolio.py` | Developers + reviewers | Multi-job/bundle extraction, schema, source-disjointness, payload removal, and atomic no-output failure controls. |
| `benchmark/` | Users + CI | Installable scorer and tests for the linked external clinical-trial decision dataset. |
| `release_manifest.json` | Machines + reviewers | Canonical GitHub/HF release scope and required checks. |
| `release_decision_packet.json` | Machines + reviewers | Machine-readable public launch decision packet. |
| `huggingface/README.md` | Humans + HF Hub | Dataset card for the public Hugging Face mirror. |
| `huggingface/release_manifest.json` | Machines + reviewers | Hugging Face-specific include/exclude manifest. |
| `scripts/audit/` | CI + maintainers | Fail-closed release-boundary validators. |

## Executable Backbone

The execution core requires Python 3.11 or newer and has no third-party runtime dependencies.
Run the deterministic, non-benchmark eight-stage control-plane fixture:

```bash
python3 -m agentic_drug_discovery.demo
```

Run a real one-stage planner-to-transition fixture using an Open Targets-shaped public payload:

```bash
adds-bounded-agent-demo
```

Both commands emit JSON so humans and machines can inspect the applied transitions. The bounded
fixture is deterministic and dependency-free; it is a control-flow test, not benchmark evidence.
Run the core regression suite with no third-party runtime dependencies:

```bash
python3 -m unittest discover -s tests -v
```

Replay a version-1 JSON bundle from a file or stdin. The command exits nonzero when a packet is
blocked and emits the exact blocking codes:

```bash
adds-replay-bundle bundle.json
cat bundle.json | adds-replay-bundle
```

Capture exact source bytes outside Git, then compile a reviewer-authored job into a payload-free
manifest and review report:

```bash
adds-pinned-ingestion capture --help
adds-pinned-ingestion extract-cdc-mmwr --help
adds-pinned-ingestion extract-ncbi-pubmed --help
adds-pinned-ingestion extract-chembl-activity --help
adds-pinned-ingestion extract-ncbi-pubmed-disease-model --help
adds-pinned-ingestion extract-clinicaltrials-gov --help
adds-pinned-ingestion extract-clinicaltrials-gov-portfolio --help
adds-pinned-ingestion compile --help
```

The generic workflow and release boundary are in `docs/17_pinned_source_ingestion.md`; disease-
context provider contracts are in `docs/18_cdc_mmwr_ingestion.md` and
`docs/19_ncbi_pubmed_ingestion.md`; preclinical provider contracts are in
`docs/20_preclinical_provider_ingestion.md`; the ClinicalTrials.gov design contract is in
`docs/21_clinical_provider_ingestion.md`; the explicit cross-trial synthesis contract is in
`docs/22_clinical_benefit_risk_synthesis.md`; portfolio ingestion and approved endpoint mapping are
in `docs/23_clinical_portfolio_endpoint_mapping.md`.

`tests/test_adapter_bindings.py` also executes a five-stage registry path from target nomination
through preclinical review. It advances through matched target, modality, candidate, and
developability evidence, then defers because activity-count context is not functional-effect
evidence. This is an integration fixture, not a discovery-performance result.

`tests/test_pinned_evidence_adapter.py` adds the full provider-backed path: an eight-stage program
starts with independent pinned disease-burden/treatment-gap records, uses Open Targets, ChEMBL,
molecular properties, and independent pinned functional/disease-model evidence, then promotes an
exact ClinicalTrials.gov endpoint/safety design and extends the intervention through EMA review.
It reaches `COMPLETED` on one cumulative ledger and replays exactly. The suite also pairs the successful
independent-source case with a same-source defer case.
`tests/test_target_identity_continuity.py` adds a matched ChEMBL symbol-match/symbol-mismatch pair
plus rebinding, collision, and broken-candidate-link attacks. All records are synthetic contract
fixtures, not efficacy evidence.
`tests/test_context_identity_continuity.py` adds disease/model rebinding, assay namespace collision,
and unknown-candidate evidence attacks. The pinned-evidence suite also includes a matched
assay-target-link pair whose one-field mismatch defers instead of partially updating state.
`tests/test_clinical_identity_continuity.py` adds intervention rebinding, trial namespace collision,
unknown-intervention linkage, support-removal, and strict intervention/trial/design example checks.
`tests/test_clinicaltrials_gov_ingestion.py` verifies exact receipt, NCT, protocol/result/safety
arm, population, endpoint, serious-adverse-event aggregate, statistical-analysis, payload-removal,
and CLI-hash behavior. It also rejects
arm-role rebinding and endpoint/safety-support removal, then pairs atomic design advance with
missing-safety defer. The semantic-mapping suite keeps the legacy search path contextual and
checks EMA source identity mismatch.
`tests/test_clinical_portfolio.py` verifies two-job/two-bundle exact-set extraction, source
disjointness, payload removal, manifest compilation, and no output after failed CLI preflight.
`tests/test_clinical_benefit_risk_synthesis.py` independently promotes two synthetic exact-study
bundles, commits and replays a reviewer-approved endpoint mapping, then executes mapping-gated
endpoint/safety harmonization through the local tool, semantic mapper, decision packet, continuity
verifier, serialization, and replay path. It rejects missing or mismatched mapping, overlapping
source hashes, automatic pooling, forged copied values, direct commits, and committed record removal.
`tests/test_pinned_evidence_ingestion.py` verifies receipt/job parsing, external bundle integrity,
tamper and raw-field rejection, deterministic compilation, CLI path hygiene, and a matched
independent-source/reused-source pair executed through the bounded disease-stage runner.
`tests/test_cdc_mmwr_ingestion.py` verifies article identity, section, excerpt, value, unit,
geography, and reference-period mismatches; confirms excerpt removal; and evaluates matched
independent-source advance versus same-document defer behavior.
`tests/test_ncbi_pubmed_ingestion.py` verifies direct article identity, exact EFetch request,
structured abstract sections, typed comparator/value/unit, context anchors, retraction and XML
security boundaries, excerpt removal, context-matched advance, and cross-population defer behavior.
`tests/test_chembl_activity_ingestion.py` verifies release and linked-resource identity, clean
standardized point estimates, source assay classification, candidate aliases, target components,
publication lineage, text removal, and CLI hashes.
`tests/test_ncbi_pubmed_disease_model_ingestion.py` verifies article identity, typed exposure and
endpoint semantics, candidate/model anchors, retraction rejection, text removal, and CLI hashes.
`tests/test_preclinical_provider_pair.py` joins both sanitized outputs into matched advance and
shared-publication-lineage defer arms, checks zero partial promotion on abstention, and validates
the payload-free external-run snapshot for machine consumption.

The central execution path is:

```text
external source bytes -> immutable receipt/bundle -> reviewed payload-free manifest
  -> PinnedEvidenceAdapter
  -> BoundedProgramRunner + ordered ProgramStep records + one cumulative ledger
  -> ProgramState + StagePlan
  -> BoundedPlanner + registered ToolContract preflight
  -> bounded ToolRequest batch
  -> ToolOutcome + immutable ToolExecutionLedger
  -> operation-specific SemanticMapperRegistry
  -> optional exact-set clinical portfolio extraction outside the state ledger
  -> reviewer-approved endpoint mapping bound to committed trial-design records
  -> optional mapping-gated cross-trial synthesis
  -> DecisionPacket proposal
  -> deterministic and soft verifiers
  -> accepted ProgramState, accepted DEFER recovery, or unchanged fail-closed state
  -> continue only after accepted ADVANCE; otherwise pause, terminate, block, or exhaust
```

Default advance gates require cutoff-safe evidence linked to a supported current-stage claim;
disease context and preclinical validation additionally require two distinct source ids, two
distinct valid source-content SHA-256 values, and no exact-byte relabeling. Preclinical validation
also requires disjoint canonical upstream lineage ids and candidate-name resolution through the
functional record's declared aliases. Target nomination
requires Ensembl and gene-symbol bindings;
modality through preclinical stages require the same record plus a ChEMBL target binding.
Candidate-generation and later stages also require at least one active or selected candidate, and
candidate through preclinical advances require that candidate to link to the qualifying target.
Every advance requires one canonical, evidence-backed disease record. Preclinical advance also
requires current-packet assay and model-system records whose evidence links resolve to the same
disease and viable candidate; the assay must additionally preserve target and organism identity.
Clinical advance requires current-packet intervention, trial, and atomic trial-design records tied
to that candidate and disease, plus source-content SHA-256, efficacy and safety predicates, both
candidate and comparator arms, and a posted serious-adverse-event summary covering those arms.
Regulatory advance requires a current-packet intervention update backed by matched EMA status
evidence while preserving the accepted clinical identity and trial-design ledger.
`StageGate.minimum_benefit_risk_synthesis_records` can additionally require a current-packet,
source-disjoint synthesis. Its default remains zero until a real, independently reviewed multi-trial
portfolio is release-approved and wired into the standard eight-stage fixture.
`ToolExecutionLedger.total_cost` counts invoked attempts. `ProgramState.budget` records actions in
accepted packets, so callers that bill blocked proposal attempts should use the execution ledger.
`StageRun.attempted_packets` preserves proposals for audit, while `StageRun.accepted_packets`
contains only the packets that can enter a deterministic `ReplayBundle`.

## GitHub Boundary

The GitHub repo is a sanitized execution, benchmark-control, and protocol surface. Full case banks, raw source snapshots, evaluator-only labels, generated verifier results, run logs, machine-specific paths, and working research notes stay outside Git unless a separate release packaging step explicitly promotes an audited artifact.

Public-release readiness is tracked in:

- `docs/release_boundary.md` — what can and cannot enter Git history.
- `docs/release_trust_report.md` — trust claims, machine anchors, and interpretation warnings.
- `docs/12_scd_vertical_slice.md` — caveats-first audited SCD vertical slice.
- `docs/13_target_id_governance_node.md` — upstream target-node aggregate results.
- `docs/14_target_identity_continuity.md` — canonical target identity contract.
- `docs/15_discovery_context_identity.md` — disease, assay, and model-system identity contract.
- `docs/16_clinical_intervention_identity.md` — clinical intervention and trial-design identity contract.
- `docs/17_pinned_source_ingestion.md` — source capture and manifest compilation contract.
- `docs/18_cdc_mmwr_ingestion.md` — CDC MMWR provider extraction contract.
- `docs/19_ncbi_pubmed_ingestion.md` — NCBI PubMed treatment-gap extraction and context-bound
  combination contract.
- `docs/20_preclinical_provider_ingestion.md` — ChEMBL functional-activity and PubMed disease-model
  extraction, typed endpoint continuity, and lineage-independent composite promotion.
- `docs/preclinical_provider_validation_snapshot.json` — machine-readable, payload-free external
  provider validation record; exact replay artifacts remain excluded.
- `docs/21_clinical_provider_ingestion.md` — source-pinned ClinicalTrials.gov design extraction and
  bounded promotion contract.
- `docs/22_clinical_benefit_risk_synthesis.md` — explicit, source-disjoint, non-pooled cross-trial
  endpoint/safety harmonization contract.
- `docs/23_clinical_portfolio_endpoint_mapping.md` — atomic multi-bundle portfolio extraction and
  reviewer-approved endpoint mapping ledger contract.
- `docs/clinical_provider_validation_snapshot.json` — payload-free exact-NCT validation hashes,
  typed identities, matched outcome, and limitations.
- `docs/42_uc_provider_validation.md` and
  `docs/uc_clinical_provider_validation_snapshot.json` — public-source UC induction contract
  validation, retained uncertainty, typed phase boundaries, and payload-free hashes.
- `docs/public_evidence_summary.json` — machine-readable aggregate claim ledger.
- `docs/public_release_readiness_plan.md` — current public GitHub readiness plan.
- `docs/public_launch_checklist.md` — final human launch checklist.
- `release_manifest.json` — machine-readable release boundary and required checks.
- `release_decision_packet.json` — machine-readable public launch decision packet.
- `codemeta.json` and `.zenodo.json` — machine-readable citation and archive metadata.
- `huggingface/` — Hugging Face Dataset-card package mirrored on the Hub.

Before release-surface changes, run:

```bash
python3 -m pip install -e ".[test]" -e ./benchmark build ruff
python3 scripts/audit/github_release_file_audit.py
python3 scripts/audit/validate_hf_release_package.py
python3 scripts/audit/validate_public_launch_packet.py
python3 scripts/audit/validate_vertical_slice_doc.py
python3 scripts/audit/validate_policy_evaluation_snapshot.py
python3 scripts/audit/validate_biohub_research_readiness.py
python3 scripts/audit/validate_translational_handoff.py
python3 -m unittest discover -s tests -v
python3 -m ruff check agentic_drug_discovery tests adapters/boltz_adapter.py adapters/chembl_adapter.py adapters/opentargets_adapter.py adapters/execution_registry.py adapters/pinned_evidence_adapter.py adapters/clinical_synthesis_adapter.py scripts/audit
python3 -m pytest -q benchmark/tests
python3 -m build --wheel . --outdir /tmp/agentic-core-dist
python3 scripts/audit/smoke_test_core_wheel.py --wheel-dir /tmp/agentic-core-dist
python3 scripts/audit/build_hf_release_package.py --output /tmp/agentic-hf-release-package --force
python3 scripts/audit/validate_hf_release_package.py --package /tmp/agentic-hf-release-package
git diff --check
python3 -m compileall agentic_drug_discovery adapters chains benchmark/src scripts/audit tests
```

## Immediate Use

Start with:

1. `agentic_drug_discovery/models.py`
2. `agentic_drug_discovery/planning.py`
3. `agentic_drug_discovery/execution.py`
4. `agentic_drug_discovery/promotion.py`
5. `agentic_drug_discovery/orchestration.py`
6. `agentic_drug_discovery/program.py`
7. `agentic_drug_discovery/environment.py`
8. `agentic_drug_discovery/serialization.py`
9. `agentic_drug_discovery/matched_evaluation.py`
10. `agentic_drug_discovery/pinned_evidence.py`
11. `agentic_drug_discovery/ingestion.py`
12. `agentic_drug_discovery/cdc_mmwr.py`
13. `agentic_drug_discovery/ncbi_pubmed.py`
14. `agentic_drug_discovery/chembl_activity.py`
15. `agentic_drug_discovery/clinicaltrials_gov.py`
16. `agentic_drug_discovery/ingestion_cli.py`
17. `tests/test_agent_loop.py`
18. `tests/test_program_runner.py`
19. `tests/test_semantic_mappings.py`
20. `tests/test_matched_evaluation.py`
21. `tests/test_target_identity_continuity.py`
22. `tests/test_context_identity_continuity.py`
23. `tests/test_clinical_identity_continuity.py`
24. `tests/test_pinned_evidence_ingestion.py`
25. `tests/test_cdc_mmwr_ingestion.py`
26. `tests/test_ncbi_pubmed_ingestion.py`
27. `tests/test_chembl_activity_ingestion.py`
28. `tests/test_ncbi_pubmed_disease_model_ingestion.py`
29. `tests/test_preclinical_provider_pair.py`
30. `tests/test_clinicaltrials_gov_ingestion.py`
31. `adapters/execution_registry.py`
32. `adapters/pinned_evidence_adapter.py`
33. `PROJECT_BRIEF.md`
34. `docs/release_trust_report.md`
35. `docs/14_target_identity_continuity.md`
36. `docs/15_discovery_context_identity.md`
37. `docs/16_clinical_intervention_identity.md`
38. `docs/17_pinned_source_ingestion.md`
39. `docs/18_cdc_mmwr_ingestion.md`
40. `docs/19_ncbi_pubmed_ingestion.md`
41. `docs/20_preclinical_provider_ingestion.md`
42. `docs/preclinical_provider_validation_snapshot.json`
43. `docs/21_clinical_provider_ingestion.md`
44. `docs/clinical_provider_validation_snapshot.json`
45. `rl_env/specs/target_identity_record.schema.json`
46. `rl_env/specs/discovery_context_identity.schema.json`
47. `rl_env/specs/clinical_intervention_identity.schema.json`
48. `rl_env/specs/clinicaltrials_gov_ingestion_job.schema.json`
49. `rl_env/specs/source_receipt.schema.json`
50. `rl_env/specs/pinned_evidence_ingestion_job.schema.json`
51. `rl_env/specs/cdc_mmwr_ingestion_job.schema.json`
52. `rl_env/specs/ncbi_pubmed_ingestion_job.schema.json`
53. `rl_env/specs/chembl_activity_ingestion_job.schema.json`
54. `rl_env/specs/ncbi_pubmed_disease_model_ingestion_job.schema.json`
55. `docs/12_scd_vertical_slice.md`
56. `docs/13_target_id_governance_node.md`
57. `docs/public_evidence_summary.json`
58. `docs/00_problem_framing.md`
59. `docs/01_long_horizon_chain_design.md`
60. `docs/03_deterministic_soft_verifier.md`
61. `docs/04_rl_environment_design.md`
62. `rl_env/specs/case_bank_schema_v0.md`
63. `agentic_drug_discovery/clinical_synthesis.py`
64. `adapters/clinical_synthesis_adapter.py`
65. `tests/test_clinical_benefit_risk_synthesis.py`
66. `docs/22_clinical_benefit_risk_synthesis.md`
67. `rl_env/specs/clinical_benefit_risk_synthesis.schema.json`
68. `agentic_drug_discovery/clinical_portfolio.py`
69. `agentic_drug_discovery/clinical_endpoint_mapping.py`
70. `tests/test_clinical_portfolio.py`
71. `docs/23_clinical_portfolio_endpoint_mapping.md`
72. `rl_env/specs/clinicaltrials_gov_portfolio_job.schema.json`
73. `rl_env/specs/clinical_endpoint_mapping.schema.json`

## Design Bias

This project should stay implementation-facing. Research notes are useful only insofar as they help define:

- state/action/observation schemas,
- verifier contracts,
- tool adapters,
- trajectory records,
- reward signals,
- compute-specific experiment plans.

## Release Posture

The public artifact presents an executable control plane, protocol, benchmark-control layer, and
limited decision-prototype surface, not a complete autonomous discovery or wet-lab capability.
The release surface favors typed interfaces, schemas, audit scripts, adapters, governance notes,
and reproducible smoke paths. Raw source bundles, real provider review jobs, and raw clinical or
regulatory source snapshots,
hidden labels, generated trajectories, scheduler logs, machine paths,
credentials, and unpublished working notes remain outside the repository.

## License

Apache License 2.0. See `LICENSE`.
