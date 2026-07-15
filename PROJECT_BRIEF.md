# Project Brief

## Working Name

Agentic Drug Discovery System

## One-Line Aim

Build an evidence-governed execution and evaluation environment for end-to-end drug-discovery agents, constrained by deterministic checks and informed by calibrated soft scientific verifiers.

## Hypothesis

Drug discovery can be modeled as a sequence of structured decision points rather than a single prompt-response task. If each step records the state, evidence, tools used, model outputs, verifier results, and decision rationale, then both successful and failed discovery paths can become reusable training and evaluation trajectories.

## Current Executable Baseline

- Immutable, JSON-serializable evidence, claim, disease, target, candidate, assay, model-system,
  intervention, trial, trial-arm, trial-population, trial-endpoint, trial-safety, safety-arm,
  atomic trial-design, clinical endpoint-binding, approved endpoint-mapping, action, packet,
  decision, verifier, budget, and program-state records.
- Eight explicit stages from disease context through regulatory/post-market reasoning.
- Fail-closed advance, hold, defer, pivot, and kill transitions with stale-state, chronology, provenance, contradiction, budget, and stage-readiness gates.
- Accepted packet, action, decision, and verifier histories that cross-check each other and retain replay inputs.
- Typed tool contracts, state-bound requests, structured outcomes, explicit execution modes,
  payload hashes, and an immutable execution ledger.
- Explicit evidence promotion: adapter payloads cannot assign scientific polarity or confidence
  until a caller supplies a typed evidence draft.
- Multi-source promotion requires an explicit source id for each evidence draft; external source
  hashes remain distinct from tool-payload hashes.
- Strict JSON round-trip and deterministic replay bundles with packet/action/evidence-to-tool-ledger
  integrity checks and a machine-readable replay CLI.
- A bounded stage planner that validates the full required call batch against contracts, state,
  chronology, step limits, and both state and invocation-ledger budgets before execution.
- A stage runner that connects planning, typed tool execution, operation-specific semantic
  promotion, packet construction, verifier-gated transition, conservative decision aggregation,
  and accepted-only replay while preserving rejected attempts for audit. Missing or post-cutoff
  promotion context is blocked before tool invocation.
- A bounded multi-stage program runner that carries one cumulative execution ledger across ordered
  stage plans, checks state and packet continuity, continues only after accepted advance decisions,
  and records completed, terminated, paused, blocked, or plan-exhausted outcomes.
- A typed deterministic policy layer that converts exact paused/blocked observations into only
  predeclared replacement plans, bounds rule/global revisions, and resumes from hash-bound state,
  ledger, queue, and policy-history checkpoints.
- Conservative built-in mappings for Open Targets disease identity and target association; ChEMBL
  modality-mechanism matching, molecule identity, and target activity volume; RDKit molecular
  properties; contextual ClinicalTrials.gov search results; source-pinned ClinicalTrials.gov trial
  designs; reviewer-approved endpoint mapping; explicit mapping-gated non-pooled cross-trial
  benefit-risk synthesis; EMA regulatory status; and
  structured Boltz binding output. Disease identity, activity
  volume, search results, and Boltz predictions remain contextual where their payloads cannot
  establish the stronger scientific gate.
- Composite source-pinned mappings for disease burden plus treatment gap and for candidate-target
  function plus disease-model effect. These mappings use manifest record dates, require exact
  identities and independent SHA-256-pinned sources, and emit one umbrella claim linked to both
  component evidence events. The preclinical gate additionally requires typed endpoints,
  candidate-alias continuity, and disjoint canonical upstream publication lineages.
- A source-ingestion layer captures exact HTTPS or reviewed local bytes into immutable bundles
  outside Git, records strict payload-free receipts, and compiles reviewer-authored summaries into
  validated pinned manifests plus deterministic review reports. Hash, size, chronology, raw-field,
  summary-size, finite-number, local-path, source-conflict, and duplicate-content checks fail closed;
  exact bytes relabeled with different source ids cannot satisfy independence, and scientific
  interpretation always remains approval-gated.
- A CDC MMWR provider layer verifies a reviewer-selected burden or treatment-gap record against the
  captured article's receipt, DOI-bound source version, canonical URL, citation metadata, section,
  excerpt, numeric value, unit, geography, and reference period. It emits only a payload-free
  generic job with an excerpt hash. The real snapshot and reviewer job remain external, and no real
  manifest is release-approved by this implementation.
- An NCBI PubMed provider layer verifies one reviewer-selected treatment-gap record against an
  exact EFetch XML request. It reconciles direct PMID, PMCID, DOI, title, and electronic-publication
  identity; rejects retractions and ambiguous XML structure; verifies METHODS/RESULTS excerpts,
  typed comparator/value/unit, and population/geography/period/treatment anchors; then emits hashes
  instead of abstract text. The real PMID 32147964 capture and reviewer job remain external.
- A ChEMBL functional-activity provider layer reconciles one exact release status plus linked
  activity, assay, document, molecule, and target resources. It requires a clean standardized point
  estimate, preserves ChEMBL's source assay classification, verifies functional-readout text,
  candidate aliases, direct single-protein assignment, target component identity, and publication
  lineage, then removes assay evidence text from the sanitized job.
- An NCBI PubMed disease-model provider layer binds one unstructured abstract to typed candidate,
  model, exposure-regimen, endpoint, variation, and p-value fields. It rejects article-identity,
  retraction, anchor, unit, and value mismatches and removes all reviewer evidence text. One
  external ChEMBL 37/PubMed pair advances to clinical strategy; a counterfactual that changes only
  upstream publication lineage defers with zero promoted evidence. Public fixtures are synthetic.
- A ClinicalTrials.gov provider layer binds one exact API study receipt to NCT and registry
  version, candidate aliases, condition, protocol arms, posted result groups, denominators,
  population, primary endpoint, statistical analysis, and posted serious-adverse-event group
  summaries. It emits a payload-free generic job and atomically promotes typed candidate/comparator
  arms, population, endpoint, and safety records only under one bounded supportive rule. It does
  not infer safety acceptability. One exact public NCT snapshot passes externally; source bytes and
  the reviewer job remain outside Git.
- A ClinicalTrials.gov portfolio layer verifies the complete set of independently reviewed
  single-trial jobs and external bundles before emitting one payload-free generic job. It requires
  exact job/receipt/trial/design/endpoint/safety and candidate/intervention/disease agreement plus
  pairwise-distinct source hashes; any failed member aborts before output.
- A reviewer-approved endpoint mapping layer preserves endpoint-family and ontology identities,
  approval identity/time, exact ordered trial bindings, fingerprints, source evidence, and source
  hashes in an append-only ledger. It does not infer endpoint similarity or claim live
  ontology-authority validation.
- A deterministic cross-trial synthesis layer takes explicit reviewed trial/design/endpoint/safety
  selections that exactly match a committed approved mapping and recompiles hazard ratios,
  confidence intervals, source arm measurements, and
  serious-event participant risks from committed ledgers. It requires at least two source-disjoint
  trials, retains trial-level values and hashes, and prohibits automatic endpoint mapping, pooling,
  benefit-risk scoring, population comparability inference, and clinical acceptability inference.
- An evidence-backed `TargetRecord` ledger carries Open Targets Ensembl/gene-symbol identity into
  a ChEMBL target-profile check, then into candidate and preclinical records. Deterministic checks
  reject namespace rebinding, collisions, partial or broken candidate links, and mismatched target
  symbols or organisms.
- Evidence-backed `DiseaseRecord`, `AssayRecord`, and `ModelSystemRecord` ledgers preserve the
  disease context and preclinical experimental identities. The default gates require one canonical
  disease at every advance and current-packet assay/model records at preclinical advance. Broken
  disease, target, candidate, organism, evidence, or namespace links fail closed.
- Evidence-backed `InterventionRecord`, `TrialRecord`, and atomic `TrialDesignRecord` ledgers
  preserve candidate-to-clinical identity. The default clinical gate requires source-pinned
  efficacy and safety-assessment evidence plus linked candidate/comparator arms, population, posted
  endpoint, and posted safety summary; the legacy search path remains contextual. EMA requires an
  accepted intervention and matching source asset or INN.
  Rebinds, role swaps, support removal, ambiguity, namespace collisions, and broken parent or
  evidence links fail closed.
- Append-only `StudyBenefitRiskRecord` and `BenefitRiskSynthesisRecord` ledgers preserve the exact
  selected clinical identities, source evidence, and source hashes. A continuity verifier
  recompiles every proposed synthesis and blocks copied-value changes or committed-record removal.
- Append-only `ClinicalEndpointMappingRecord` ledgers preserve reviewer approval, ontology identity,
  exact endpoint/safety fingerprints, and source-disjoint trial bindings. A separate continuity
  verifier blocks direct commits, rebinding, mutation, removal, and stale source identities.
- Matched success/failure evaluation records with exact context matching, evidence cutoffs,
  evaluator-label separation, explicit failure causes, and separate arm/pair summary metrics.
- An illustrative non-benchmark eight-stage trajectory plus deterministic regression tests.
- Existing Open Targets, ChEMBL, ClinicalTrials.gov, clinical synthesis, EMA, Boltz-2, and RDKit
  molprops adapters have
  typed bindings for the mapped operations above. The dependency-free pinned-evidence adapter reads
  a public JSON manifest without bundling source payloads. A tested eight-stage provider-backed
  path carries one continuous disease-to-Ensembl-to-ChEMBL-to-candidate-to-assay/model-to-clinical
  endpoint/safety lineage through EMA regulatory review and exact replay, while the earlier
  activity-count path still defers because volume is not functional-effect evidence. A second matched
  provider-pair test joins the
  sanitized ChEMBL functional and PubMed disease-model contracts and isolates lineage reuse as the
  only failure variable.

## System Ingredients

- LLM agent: plans, routes tools, updates hypotheses, explains decisions.
- Scientific foundation models: protein, chemical, cell, genome, and perturbation representations.
- Tools and databases: retrieval, docking/structure, ADMET/toxicity, omics, pathway, literature, and known-assay sources.
- Deterministic verifiers: schema, entity, unit, provenance, constraint, leakage, and reproducibility checks.
- Soft verifiers: evidence sufficiency, uncertainty, plausibility, novelty, risk, and actionability scores.
- Reward layer: step rewards, verifier rewards, information gain, cost penalties, and terminal outcome rewards.

## Scope

The implementation focuses on an offline, inspectable end-to-end environment, not wet-lab automation. Specialist chains include:

- target identification to hit triage,
- hit-to-lead prioritization,
- lead optimization with ADMET constraints,
- protein design / binder design,
- cell perturbation response reasoning.

## Compute Split

- Local: schemas, toy environments, deterministic verifier prototypes.
- Cluster GPU: SFM embedding, structure/chemistry validation, bridge experiments, smaller calibration runs.
- Large GPU: model serving, larger rollouts, and post-training or RL-style experiments.

## Near-Term Engineering Sequence

Completed in the current candidate: the common typed execution protocol, conservative adapter
bindings, bounded planning, operation-specific semantic promotion, single-stage execution and
accepted-defer recovery, bounded multi-stage coordination with explicit stop semantics, strict
packet ingestion, execution-ledger integrity checks, deterministic replay, and the matched-pair
evaluation contract. The current candidate also completes disease, target-to-candidate, assay, and
model-system identity continuity for the implemented pinned preclinical path, plus intervention,
trial, arm, population, endpoint, safety-record, and safety-arm continuity for source-pinned
ClinicalTrials.gov evidence and EMA extension. It additionally completes an explicit two-or-more
   trial hazard-ratio/serious-event synthesis path through local tool execution, semantic promotion,
   typed state, serialization, fail-closed recompilation, and exact replay without automatic pooling
   or clinical judgment. The path now includes atomic multi-job/multi-bundle portfolio extraction and
   an independently committed reviewer-approved endpoint mapping ledger. It also completes the generic
capture-to-manifest ingestion path and executes compiled independent/reused-source manifests as a
matched bounded-stage pair. The CDC MMWR and NCBI PubMed contracts now execute verified external
article snapshots through sanitized extraction. Synthetic matched-context records advance, while
the real broader 2018 California surveillance burden plus the 2011-2016 California Medicaid
treatment gap defers on explicit population and evidence-context mismatch. Only synthetic provider
fixtures are public. The ChEMBL functional-activity and PubMed disease-model contracts also execute
one external, context-matched senicapoc/KCNN4 pair through sanitized extraction and the composite
preclinical gate. It advances with independent source ids, bytes, and publication lineages and
defers under a controlled shared-lineage counterfactual. Raw provider payloads and jobs remain
external; the repository records only payload-free identifiers, hashes, results, and limitations in
`docs/preclinical_provider_validation_snapshot.json`. The exact ClinicalTrials.gov NCT01844505
snapshot also passes strict endpoint/safety extraction, atomic promotion, committed-history
validation, and a matched missing-safety control. Its payload-free identifiers, hashes, outcomes,
and limits are recorded
in `docs/clinical_provider_validation_snapshot.json`.

1. Add a genuinely context-matched, independently reviewed disease-burden/treatment-gap pair; do
   not coerce the current CDC and PubMed populations into one context.
2. Execute and release-review a real context-matched multi-trial provider portfolio, wire it into the
   standard clinical stage, and add external ontology-authority/version validation without weakening
   explicit review or atomic identity contracts.
3. Exercise multiple live adapter/provider stages through semantic promotion, stage gates, serialization,
   and replay as one bounded end-to-end program run.
4. Derive failure causes from verifier outputs and assemble real cutoff-safe matched episodes.
5. Calibrate soft verifiers against deterministic gates without allowing soft scores to bypass hard failures.
6. Add candidate ranking/edit loops, budget-aware action selection, learned-policy comparison, and
   operator reauthorization above the shipped deterministic resume/replan control layer.
