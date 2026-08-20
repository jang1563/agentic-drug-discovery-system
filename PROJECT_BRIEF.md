# Project Brief

## Working Name

Agentic Drug Discovery System

## One-Line Aim

Build an evidence-governed execution and evaluation environment for end-to-end drug-discovery agents, constrained by deterministic checks and informed by calibrated soft scientific verifiers.

## Hypothesis

Drug discovery can be modeled as a sequence of structured decision points rather than a single prompt-response task. If each step records the state, evidence, tools used, model outputs, verifier results, and decision rationale, then both successful and failed discovery paths can become reusable training and evaluation trajectories.

## Biohub-Context Research Position

The strongest collaborator-facing position is not as a virtual-cell or therapeutic-design model.
It is a provenance-preserving translational decision layer downstream of cell measurement,
perturbation, and biomodel science. A strict Biohub-context profile binds official public sources,
implemented versus synthetic versus proposed maturity, local evidence hashes, a ten-slide claim
ledger, and a 90-day immune-perturbation handoff pilot with frozen acceptance gates. No Biohub
affiliation, data integration, endorsement, completed pilot, or real clinical calibration is
claimed. See `docs/39_biohub_translational_evidence_bridge.md` and
`docs/biohub_research_readiness.json`.

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
  selections that exactly match a committed approved mapping and recompiles supported hazard,
  odds, or risk ratios under fixed favorable-direction contracts,
  confidence intervals, source arm measurements, and
  serious-event participant risks from committed ledgers. It requires at least two source-disjoint
  trials, retains trial-level values and hashes, and prohibits automatic endpoint mapping, pooling,
  benefit-risk scoring, population comparability inference, and clinical acceptability inference.
- A clinical evidence decision layer requires that committed synthesis to pass complete history and
  continuity replay, then projects exact trial cells into ten ordered workflow dimensions and
  typed provenance-linked gaps. A preregistered policy and action catalog bound trial-count,
  precision, safety-exposure, alignment, action-count, cost, and minimum-VOI criteria. The
  deterministic planner ranks marginal gap coverage by declared resolution probability,
  decision relevance, and cost against the live budget ledger; integrity envelopes and state
  recompilation bind the synthesis, policy, tensor, catalog, scores, gap partition, and plan.
  `ADVANCE` means evidence-workflow readiness only. Pooling, clinical acceptability, treatment
  recommendations, terminal decisions, and calibrated economic VOI claims are prohibited.
- A synthetic ulcerative-colitis conformance slice (`MONDO:0005101`) exercises a second disease
  geometry from contextual M6 handoff through clinical-remission odds-ratio mapping, non-pooled
  synthesis, and decision-tensor direction checks. Separately, two public ClinicalTrials.gov UC
  induction snapshots execute the provider contract: one uncertain interval is retained on
  `HOLD`, while one bounded favorable interval advances. Neither surface is a pooled efficacy,
  safety-acceptability, or therapeutic validation set. A separate real-source run binds induction
  and maintenance endpoint/safety populations within `NCT02435992` without treating them as
  independent trials or inferring participant identity.
- A clinical cohort diagnostics layer binds exact package rosters and can require accepted-state
  hashes plus committed-ledger replay. It separates packages, programs, and synthesis-bound
  evidence units; reports complete decision/dimension/gap/action denominators; performs matched
  policy sensitivity only on shared evidence units; and exposes cross-unit source-hash or trial-id
  reuse. It includes no outcome labels or performance metrics and therefore cannot estimate
  correctness, utility, safety, policy superiority, or calibration.
- A preregistered clinical outcome layer binds favorable composite benefit-risk probabilities to
  exact package and evidence-unit hashes before a fixed deadline. A public protocol commits the
  outcome definition, endpoint/safety harmonization rules, curator roster, outcome window,
  threshold, bins, confidence level, and minimum evaluable units. Evaluator-only manifests require
  independently curated endpoint and safety assessments backed by post-deadline source hashes;
  aggregate reports retain attrition, Wilson intervals, Brier/calibration/threshold metrics,
  matched policy comparisons, and provenance-overlap counts without unit-level labels. Package
  workflow decisions are not scored as outcomes. The public example is synthetic and does not
  establish calibration, utility, efficacy, safety, or policy superiority.
- A dependence-aware uncertainty layer adds a second preregistered protocol and an evaluator-only
  exact unit-to-cluster manifest. It requires full outcome-report replay, exact roster coverage,
  and closure of known shared program, baseline trial/source, and outcome trial/source links before
  computing aggregate CR1 intervals for additive policy metrics overall and within fixed
  stage-by-endpoint strata, plus overall paired Brier differences. Insufficient or dominant
  clusters, and cluster uncertainty that rounds to zero at the reporting precision, produce
  explicit no-interval states. Public reports never expose unit assignments or cluster-level
  results, and a computed interval is not a validated coverage or superiority claim.
- A prospective clustered-board design layer freezes synthetic stage-by-endpoint cluster-size,
  prevalence, ICC, MCAR evaluability, prediction-pattern, candidate-gate, seed, and Monte Carlo
  commitments. Its beta-binomial Polya urn has analytic truths for all additive outcome metrics
  and invokes the production CR1 diagnostic/estimator plus an explicit IID reference on every
  replicate. Aggregate reports preserve bias, RMSE, empirical and reported uncertainty, interval
  width, Wilson-bounded coverage/yield, and all no-interval statuses without replicate/unit
  records. Candidate gates are screened against declared lower-bound targets but never selected
  automatically, and the synthetic example does not justify a real-board threshold.
- An informative-evaluability and residual-dependence stress layer partitions nominal clusters
  into exact synthetic dependence blocks and assigns separate favorable/unfavorable evaluability
  probabilities. Analytic population and evaluable truths are compared against the same estimates
  under nominal and oracle dependence-closed CR1 analysis. Aggregate reports expose estimand drift,
  standard-error calibration, coverage, yield, and fail-closed states without unit/replicate
  records. Oracle closure neither discovers hidden links nor identifies or corrects a population
  estimand.
- A preregistered pattern-mixture layer binds a prediction-stratified binary log-IMOR grid to the
  exact stress protocol. Observable total/evaluable/favorable counts generate model-implied
  population metrics across the fixed grid. Aggregate matched diagnostics separately test
  evaluable calibration, evaluator-only truth-aligned recovery, and mean-curve population
  identification; unsupported reference strata fail closed. Point-envelope inclusion is not
  treated as sampling coverage, and no real missingness range is learned automatically.
- A dependence-closed sampling layer binds that exact point report before applying a complete
  delete-one-cluster jackknife at every fixed log-IMOR. It reports model-functional and
  truth-aligned population coverage separately, retains Monte Carlo uncertainty for bias and
  interval width, and compares nominal clusters with declared dependence blocks. Hidden-linkage
  scenarios require a preregistered outcome-blind closure response while independent clusters must
  remain exactly equivalent. The public study uses synthetic oracle blocks and does not infer a
  real dependence structure or combine sampling and identification uncertainty into one interval.
- An unequal-cluster influence layer binds dedicated balanced, unequal, and dominant-cluster
  scenarios before comparing delete-one normal, delete-one `t_(G-1)`, unequal delete-`m_j`
  `t_(G-1)`, and an experimental variance-matched multiplier. The public study verifies exact
  equal-size variance reduction, Student-t coverage noninferiority, multiplier RNG isolation,
  production hard stops, and full aggregate replay. It does not select a universal method or let
  synthetic calibration passage rescue a production-ineligible cluster structure.
- An informative-cluster-size layer binds fixed block-specific prevalence profiles before
  separating unit-weighted and cluster-balanced pattern-mixture truths. Positive and negative
  size-outcome association reverse the precommitted benefit-risk direction while all three
  estimators remain close to their declared target. Aggregate max-block diagnostics expose
  influence concentration, and fixed-profile calibration reveals overconservative jackknife
  uncertainty without selecting an estimand.
- A cluster-superpopulation layer binds the exact fixed-profile protocol and report, then samples
  the finite empirical cluster templates uniformly with replacement. Cluster size, stratum layout,
  and mean risk remain jointly attached, preserving both known truths while adding cluster-sampling
  variance. Aggregate conditional comparisons, realized-design rates, and tie-aware influence
  diagnostics show SE calibration recovery in all 320 prior failure cells, but dominant-profile
  unit-weighted undercoverage limits full calibration to 520/600 cells. The layer neither filters
  by realized eligibility nor claims that the finite template support transports externally.
- A generic upstream translational-handoff layer binds program, perturbation, species, tissue,
  cell, model-system, source-lineage, assay, comparator, endpoint, effect-interval, sampling,
  quality-control, and scientific-review context. Its compiler emits contextual evidence drafts
  only and preserves explicit prohibitions on mechanism, efficacy, safety, clinical-readiness, and
  treatment claims. The public fixture is synthetic and no Biohub source or workflow is integrated.
- A clinical evidence closed-loop layer recompiles selected bounded-VOI actions into exact
  state/version/package/tensor/plan-bound calls for the existing runner. It retains compact
  request, contract, payload, source, cost, packet, action, and promoted-evidence receipts;
  permits only bounded successful reviewer-verifier refresh runs; consumes attempted action ids;
  and recompiles the after decision package from an exactly committed append-only synthesis. A
  resolved gap must be targeted by a successful selected action that promotes evidence whose exact
  new source hash enters the after tensor. Strict envelopes and two-state validation detect history,
  receipt, source, catalog, budget, and after-plan tampering without retaining provider payloads.
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
- Role-neutral sealed boards with embedded cutoff-safe cached tool packets, salted external label
  commitments, opaque identities, fingerprint-bound policy submissions, unsafe-advance scoring,
  and descriptive top-label confidence diagnostics.
- Preregistered held-out protocols that bind cohort, label/exclusion guidance, opaque curator
  roster, outcome window, stage minima, and metric policy before sealing. Evaluator-only curation
  manifests enforce independent affiliations, policy blinding, consensus/adjudication, and exact
  vault labels; aggregate reports emit stage-stratified exact counts, Wilson intervals, action
  coverage, selective risk, and sufficiency flags.
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
Two additional UC induction records (`NCT01647516` and `NCT02435992`) execute the same source-pinned
path with typed treatment-phase boundaries and direction-aware decisions. Their payload-free
values, hashes, and non-pooling limits are in
`docs/uc_clinical_provider_validation_snapshot.json`.
The `NCT02435992` induction and maintenance analyses additionally execute phase-bound population
alignment with separate `645` and `457` participant aggregates. The payload-free result is in
`docs/uc_phase_population_validation_snapshot.json`; it remains one trial and makes no
participant-identity or longitudinal-exchangeability claim.

The current external validation also runs one continuous source-pinned senicapoc program through
five governed stages and checkpoint resume, ending in the historical clinical `KILL`; executes the
approved PALOMA-2/3 exact-set portfolio through typed replan, endpoint mapping, and non-pooled
benefit-risk synthesis; and seals four real matched contract pairs for three-policy comparison.
Only aggregate metrics, payload-free hashes, gate outcomes, and limitations are public in
`docs/retrospective_policy_evaluation_snapshot.json`.

1. Review one non-sensitive external cell-state or perturbation handoff against the generic M6
   contract; keep the source fixture external until scientific ownership and release approval are
   explicit.
2. Add a genuinely context-matched, independently reviewed disease-burden/treatment-gap pair; do
   not coerce the current CDC and PubMed populations into one context.
3. Use the shipped preregistration and curation contract to build a real independently curated,
   stage-stratified held-out board; no such real-board result is claimed yet.
4. Elicit outcome-blind cluster size, prevalence, ICC, evaluability, residual-dependence, and
   log-IMOR ranges for a real multi-program clinical board. Point sensitivity and dependence-closed
   cluster-jackknife sampling layers and an unequal/influential-cluster method comparison are
   shipped. Fixed informative size-outcome profiles, dual estimands, and finite empirical-template
   cluster-superpopulation resampling are now calibrated. Externally justified sampling frames,
   structured cluster loss, non-nested dependence, misspecified block boundaries, and real locked-
   board validation remain before stage-by-endpoint gate selection.
5. Join preregistered clinical package predictions to independently curated outcomes so the shipped
   cohort diagnostics can explain policy behavior while the sealed evaluator estimates actual
   selective risk and calibration.
6. Calibrate soft verifiers against deterministic gates without allowing soft scores to bypass hard failures.
7. Add candidate ranking/edit loops, budget-aware action selection, learned-policy comparison, and
   operator reauthorization above the shipped deterministic resume/replan control layer.
