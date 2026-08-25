# Changelog

All notable public-surface changes to this repository will be documented here.

## Unreleased

- Added a registry-record-wide ClinicalTrials.gov pre-review inventory. One exact API v2 source
  bundle now yields every protocol primary/secondary/other outcome, posted outcome, safety group,
  serious event, other event, and group-level event statistic with source-order indices, JSON
  pointers, record/scope hashes, structural counts, and explicit module-presence flags. Protocol
  and posted arrays are never joined by index; all exact normalized title/time-frame candidates are
  retained with unmatched and ambiguous two-sided states. Strict schemas, duplicate-safe readers,
  CLI/wheel execution, full-bundle replay, source-drift, pointer-rebinding, count-tamper, missing
  module, and non-finite JSON controls pass. Endpoint selection, semantic equivalence, clinical
  comparability, safety inference, synthesis, and treatment-choice flags remain false.
- Added a provenance-bound pre-review endpoint candidate layer. An exact design-set compiler now
  retains every population, endpoint, and safety record in explicit candidate or mechanically
  excluded partitions, including posted secondary endpoints. It enumerates every eligible
  same-design endpoint pair and endpoint-by-serious-safety link with exact source evidence,
  record/content hashes, population/phase/window/arm diagnostics, raw safety counts, strict JSON
  schemas/readers, integrity envelopes, and full-state recompilation. Synthetic omission,
  exclusion, heterogeneity, phase-rebinding, source-rebinding, and rehashed-tamper controls pass;
  endpoint family, ontology mapping, estimand equivalence, comparability, safety relationship,
  benefit-risk synthesis, and treatment-choice claims remain fixed to false.
- Added a project-internal, outcome-specific risk-of-bias contract and real two-trial olokizumab
  MTX-IR execution. Exact ClinicalTrials.gov fields and registry-labeled protocol/SAP PDF hashes,
  pages, sections, excerpts, and dates now support five canonical domain judgments per Week-12
  ACR20 outcome. The compiler verifies source-specific flow/result arm titles, endpoint identity,
  selected analysis pairs, 173/181-page PDF boundaries, and cited text. STARTED counts match ITT
  analysis denominators, but public sources do not establish complete observed outcomes or a
  standalone final pre-unblinding SAP. Four domains and both overall judgments therefore remain
  conservatively `some_concerns`; only outcome measurement is `low`. The follow-on resolves only
  `risk_of_bias_not_assessed`; four transport blockers remain and pooling, transport, treatment,
  and independent-review flags stay false.
- Added an independent olokizumab MTX-inadequate-response phase 3 replication using
  `NCT02760368` and `NCT02760407`. The exact provider, mapping, non-pooled synthesis, decision, and
  population-diagnostic path now records two trials in one reviewed stratum, removing the prior
  distinct-strata and no-within-stratum-replication blockers without estimating a pooled or
  transported effect. ClinicalTrials.gov day, month, and year date precision is now preserved in
  sanitized chronology metadata; partial periods use a declared conservative period-end boundary
  and incorrect boundaries fail closed. The public research note, reviewed spec, integrity-bound
  report, and regression tests retain five unresolved transport blockers and a workflow `HOLD`.
- Added a reviewed, source-bound population-stratified transport diagnostic. Exact olokizumab
  synthesis, trial, endpoint, ITT population, registry-document, and official-title hashes now
  preserve methotrexate- and TNF-inhibitor-inadequate-response strata without free-text inference.
  The real replay completes descriptive stratification but emits `transport_not_estimable`: each
  stratum has one trial and the evidence lacks a target population, individual-level covariates, a
  preregistered transport model, and risk-of-bias assessment. Strict specs, schemas, integrity
  readers, source-rebinding tests, a human research note, and a machine report are public.
- Added the first real source-disjoint additive clinical evidence tensor. Two phase 3 olokizumab
  rheumatoid-arthritis records (`NCT02760407` and `NCT02760433`) now execute through exact provider
  promotion, reviewer-declared Week-12 ACR20 mapping, non-pooled synthesis, tensor compilation, and
  package replay. Binary-count endpoints retain source risk differences as bounded proportions;
  only decision precision is normalized to percentage points. Explicit source-declared and
  candidate-ledger-approved aliases reconcile `Olokizumab` with `OKZ`. The two inadequate-response
  populations remain non-exchangeable, a higher observed serious-event risk triggers `HOLD`, and
  the payload-free public snapshot makes no pooled efficacy, comparative-safety, clinical-
  acceptability, or treatment claim.
- Added independent public-source UC maintenance replication for `NCT01458574`. The shared
  clinical effect contract now supports explicit percentage-point `risk_difference` labels with
  null 0, endpoint-declared direction, percent-unit validation, and candidate-then-comparator sign
  binding through extraction, promotion, endpoint mapping, typed study records, and non-pooled
  synthesis. The exact source replay committed and promoted a bounded `ADVANCE`; the payload-free
  snapshot records source/output/manifest hashes, role-aligned endpoint and serious-safety counts,
  five screened exclusion/defer controls, and no same-candidate, pooling, participant-identity,
  safety-acceptability, or treatment claim. The log-ratio decision tensor remains ratio-only and
  rejects additive effects explicitly.
- Added two public-source ulcerative-colitis ClinicalTrials.gov induction contract runs. Valid
  `benefit`, `harm`, and `null_or_uncertain` ratio intervals now survive extraction and promotion;
  only benefit recommends `ADVANCE`, while other directions commit on `HOLD`. The v3 reviewer
  contract binds endpoint and safety treatment phase, preserves registry analysis-group order,
  permits zero denominators only for unselected groups, and keeps raw bytes/jobs external. The
  payload-free NCT01647516/NCT02435992 snapshot records exact hashes, selected aggregates,
  decisions, and explicit non-pooling and no-safety-acceptability boundaries.
- Expanded cross-disease clinical conformance beyond the hazard-ratio-only path. Shared
  ratio-effect semantics now support hazard ratio with `lower_is_better` and odds/risk ratios with
  `higher_is_better` across ClinicalTrials.gov ingestion, reviewer mapping, non-pooled synthesis,
  typed study records, and clinical evidence tensors. Added an explicitly synthetic ulcerative-
  colitis (`MONDO:0005101`) M6-to-clinical conformance slice; it contains no real intervention,
  trial, measurement, reviewer, clinical conclusion, or Biohub integration.
- Added the first generic M6 cell-state and perturbation handoff. A dependency-free strict reader,
  Draft 2020-12 Schema, synthetic two-source fixture, public API, console command, release audit,
  and adversarial tests preserve disease/target/perturbation/cell/tissue/model/assay/endpoint
  identities, effect intervals, sampling, QC, source hashes, chronology, and independent lineage.
  Compilation is fixed to contextual evidence and cannot emit a mechanism, efficacy, safety,
  clinical-readiness, or treatment claim. No Biohub source, platform, authorization, affiliation,
  or endorsement is integrated.
- Added a strict Biohub-context research-readiness profile that positions the project as a
  translational evidence-governance bridge rather than a virtual-cell or therapeutic-design
  system. The machine profile binds official public alignment sources, 19 local artifact hashes,
  implemented/synthetic/proposed maturity, a ten-slide claim ledger, six open gaps, and a
  preregistered 90-day immune-perturbation handoff pilot with five immutable acceptance gates.
  A dependency-free reader, public API, console command, JSON Schema, blocking release audit,
  presentation-ready review, and adversarial tests reject duplicate keys, non-finite values,
  affiliation claims, evidence drift, maturity promotion, and threshold relaxation. No Biohub
  affiliation, data integration, endorsement, completed pilot, or external validation is claimed.
- Added empirical-template cluster-superpopulation calibration bound to the exact fixed-profile
  informative-cluster-size report. Five 500-replicate scenarios resample cluster size, prediction
  layout, and mean risk jointly while preserving every unit-weighted and cluster-balanced known
  truth. Aggregate SE calibration moves from `280/600` conditional cells to `600/600`; full
  calibration reaches `520/600` because dominant-profile unit-weighted methods retain finite-
  cluster bias and undercoverage. Strict schemas/readers, deterministic RNG substreams, tie-aware
  influence and realized-design diagnostics, exact replay, CLI paths, public artifacts,
  documentation, and tests are included. No external transportability, post-hoc eligibility
  filtering, automatic estimand or method selection, or dominant-cluster override is claimed.
- Added informative-cluster-size calibration that separates unit-weighted and
  cluster-balanced pattern-mixture functionals. Five exact 500-replicate profiles cover balanced
  and unequal null association, positive and negative size-outcome association with opposite
  threshold directions, and a production-ineligible dominant block. Three Student-t methods
  aggregate one shared block-specific functional with declared weights, then report own- and
  alternate-estimand bias, conditional coverage and SE calibration, support yield, and aggregate
  max-block influence without replicate, block, or unit records. Results
  show near-zero own-target bias, material cross-estimand drift, overconservative jackknife
  uncertainty under fixed block heterogeneity, and no estimand correction from delete-mj. Strict
  schemas/readers, exact replay, CLI paths, public artifacts, documentation, and regression tests
  are included; automatic estimand selection and cluster-superpopulation claims are excluded.
- Added unequal- and influential-cluster calibration for fixed binary log-IMOR model functionals.
  Four exact synthetic scenarios compare delete-one normal, delete-one Student-t, unequal
  delete-mj Student-t, and an experimental variance-matched Webb multiplier over shared seeded
  outcomes. Strict contracts enforce equal-size variance reduction, Student-t coverage
  noninferiority, multiplier substream isolation, production cluster-count/dominance hard stops,
  Monte Carlo calibration gates, aggregate-only output, and exact replay. Public schemas, a
  deterministic artifact builder, 500-replicate report and compact summary, CLI paths,
  documentation, and regression tests are included. No method is selected automatically, and the
  multiplier is not claimed as a regression wild-cluster bootstrap.
- Added dependence-closed delete-one-cluster jackknife uncertainty around every fixed point of the
  preregistered binary log-IMOR pattern-mixture curve. A second protocol binds the exact stress
  protocol, sensitivity protocol, and point report before replaying the complete nonlinear
  estimator. Aggregate reports separate model-functional coverage from truth-aligned population
  recovery, retain Wilson and continuous Monte Carlo bounds, compare nominal with declared
  dependence-closed clusters, and fail closed for inadequate cluster structure or leave-one-out
  support. The synthetic study shows hidden-linkage undercoverage and recovery after oracle
  closure without inferring dependence, selecting a clinical log-IMOR range, or exposing
  unit-, cluster-, or replicate-level records.
- Added preregistered prediction-stratified binary log-IMOR pattern-mixture sensitivity analysis.
  Exact stress-protocol binding reuses the deterministic outcome/evaluability streams while
  operational grid estimates consume only aggregate total/evaluable/favorable counts within fixed
  policy-prediction strata. Reports separate naive population drift, evaluable calibration,
  evaluator-only truth-aligned recovery, and mean-curve population identification; empty or
  single-class reference strata fail closed. Strict schemas/readers, exact replay, bounded work,
  CLI paths, synchronized 1,000-replicate examples, grid-exclusion controls, and explicit
  no-sampling-coverage/no-automatic-range-selection boundaries are included.
- Added deterministic informative-evaluability and residual-dependence stress simulation for
  clustered clinical outcome boards. Exact synthetic dependence blocks can span nominal clusters,
  while separate favorable/unfavorable evaluability probabilities induce analytic
  population-versus-evaluable estimand shifts. The same aggregate CR1 estimates are evaluated
  under nominal and oracle dependence-closed cluster assignments against both targets. Strict
  protocols, reports, summaries, schemas, replay, bounded work, CLI paths, and adversarial tests
  preserve informative-selection, hidden-linkage, and combined signatures without unit/replicate
  records, automatic gate selection, hidden-link detection, or missing-data correction.
- Added deterministic prospective design simulation for clustered clinical outcome boards. Public
  protocols freeze stage-by-endpoint cluster sizes, prevalence, ICC, MCAR evaluability, fixed
  prediction patterns, candidate cluster gates, Monte Carlo precision, and RNG streams. The
  beta-binomial Polya-urn generator has analytic targets for all eight additive outcome metrics
  and calls the production CR1 diagnostic/estimator for every replicate, with an IID
  unit-as-cluster reference. Aggregate reports retain bias, RMSE, empirical and reported
  uncertainty, interval width, Wilson-bounded coverage/yield, and fail-closed status counts while
  excluding replicate/unit records and automatic gate selection. Strict schemas/readers, exact
  replay, bounded workload, CLI paths, synchronized synthetic results, and high-ICC
  undercoverage/floor/dominance/attrition tests are included. No real board threshold is selected.
- Added dependence-aware uncertainty for preregistered clinical outcome evaluation. A public
  protocol binds the exact outcome protocol, cohort report, private dependence-manifest commitment,
  cluster construction, confidence level, cluster floor, dominance threshold, fixed
  stage-by-endpoint strata, and additive metrics before submissions. Evaluator-only assignments
  must cover the exact unit roster and cannot split known shared program, baseline trial/source, or
  outcome trial/source links. The evaluator fully replays and fingerprints the later base outcome
  report. Aggregate CR1 policy and paired-Brier intervals fail closed when clusters are
  insufficient or dominant, or when cluster uncertainty rounds to zero at the 12-decimal
  reporting precision; strict schemas/readers, privacy-preserving reports, CLI paths, synthetic
  CR1 math, and chronology/leakage/tamper tests are included. The one-cluster public example
  intentionally emits no interval and adds no performance claim.
  Wilson bounds are serialized at the established 12-decimal metric precision so report hashes
  replay consistently across supported Python runtimes.
- Added preregistered clinical outcome evaluation over exact outcome-free cohort reports. Frozen
  policy submissions bind favorable composite benefit-risk probabilities to package and
  evidence-unit hashes before the outcome deadline; evaluator-only manifests retain independently
  curated endpoint/safety labels and post-deadline source provenance. Aggregate reports preserve
  indeterminate attrition, Wilson intervals, threshold metrics, Brier score, fixed-bin calibration,
  matched policy comparisons, and provenance-overlap counts without exposing unit-level labels or
  scoring package workflow decisions as clinical outcomes. Strict schemas/readers, synchronized
  synthetic artifacts, CLI evaluate/validate/summarize paths, and leakage/tamper controls are
  included. No real outcome board or calibration claim is added.
- Added integrity-bound multi-package clinical cohort diagnostics. Exact manifests bind package
  identities and can require canonical accepted-state hashes plus committed-ledger replay;
  reports distinguish packages, programs, and synthesis-bound evidence units, retain exact
  decision/dimension/gap/action denominators, compare policies only on shared evidence units, and
  expose cross-unit source-hash or trial-id reuse. Strict schemas/readers, compiler-generated
  synthetic examples, CLI compile/validate/summarize paths, and adversarial tests are included.
  The report contains no outcomes or performance metrics and explicitly marks calibration as not
  estimable without independent outcomes.
- Added the `adds-clinical-evidence` compile, validate, and summarize interface over accepted-ledger
  clinical syntheses. Strict config and summary schemas, duplicate-key/non-finite rejection, exact
  mapping/synthesis packet provenance, state replay, atomic output, public-package reproduction,
  and isolated-wheel CLI coverage make the clinical tensor/VOI path usable without constructing
  internal dataclasses. Root `pytest -q` now discovers both core and benchmark tests, and runtime
  `__version__` is synchronized with package metadata.

## 0.3.0.dev2 - 2026-07-31

- Extended the strict ClinicalTrials.gov harmonization boundary for source-preserving registry
  variants: exact numeric p-values, a frozen hazard-ratio alias set, approved missing descriptive
  arm markers, dose-unit and `on-treatment` safety-title qualifiers, and sparse omitted affected
  counts only in nonselected zero-risk groups. Missing arm summaries remain `null` with the raw
  source marker retained and now produce a tenth typed evidence dimension and the
  `missing_descriptive_arm_measurement` workflow gap. Unsupported aliases, qualifiers, selected
  zero-risk safety groups, imputation, pooling, and clinical acceptability inference still fail
  closed.

## 0.3.0.dev1 - 2026-07-26

- Added a bounded clinical evidence closed loop over the existing execution core. Exact
  selected-action batches now bind decision-package, tensor, plan, policy, state version, tool
  contract, arguments, targeted gaps, and cost; compact receipts retain request/payload/source/
  packet/action/evidence provenance without provider payloads. Bounded reviewer-verifier refresh
  runs append new mappings and syntheses, attempted actions are single-use, and a resolved gap
  requires a successful targeted receipt that promotes evidence whose new source hash enters the
  after tensor. A strict transition schema, compiler-generated `HOLD`-to-`ADVANCE` synthetic
  example, two-state replay validator, and adversarial controls are included.
- Added a provenance-preserving clinical evidence decision layer over committed, replay-valid
  multi-trial synthesis records. Exact endpoint/safety cells feed nine ordered workflow
  dimensions and typed source-linked gaps; preregistered action catalogs are ranked by
  deterministic marginal bounded VOI under live and policy budgets. Package construction replays
  scores, ranks, gap partitions, and budget accounting, while strict integrity readers and state
  recompilation reject tampering. Public schema, compiler-generated synthetic example,
  safety-signal/budget/adversarial tests, and explicit non-clinical interpretation boundaries are
  included.
- Added preregistered held-out evaluation protocols that bind cohort, label/exclusion guidance,
  opaque curator roster, outcome window, stage minima, and metric policy before board sealing.
  Evaluator-only curation manifests now enforce policy-blinded independent affiliations,
  strict-majority or independent-adjudication rules, chronology, complete episode coverage, and
  exact vault labels. Aggregate reports emit exact overall/stage counts, Wilson intervals, action
  coverage, selective risk, unsafe-advance rates, and explicit sufficiency flags. Public schemas,
  strict readers, synthetic examples, and adversarial tests are included; no real independently
  curated result is claimed.
- Declared the release lint rule set in `pyproject.toml` so unpinned Ruff upgrades cannot silently
  expand blocking CI policy across the already-public legacy surface.

## 0.3.0.dev0 - 2026-07-23

- Updated release CI to immutable Node 24-based checkout and Python setup actions.
- Added an installable `agentic_drug_discovery` execution core with typed evidence, claims,
  candidates, accepted-packet/action/decision/verifier ledgers, decision packets, program state,
  configurable stage gates, and fail-closed transitions across the eight-stage discovery chain.
- Added an explicitly non-benchmark SCD-shaped control-plane demo plus regression coverage for
  temporal leakage, stale packets, evidence polarity and conflicts, upstream pivots, action
  provenance, candidate-presence gates, budgets, terminal states, duplicate identifiers,
  serialization, and malformed or failing verifiers.
- Added a blocking isolated-wheel smoke test so CI validates the installed console entry point,
  not only the editable source tree and wheel build.
- Added typed tool contracts, state/version-bound requests, structured outcomes, explicit
  cache/live/local modes, payload hashes, and an immutable execution ledger.
- Added conservative bindings for the existing Open Targets, ChEMBL, ClinicalTrials.gov, EMA,
  Boltz-2, and RDKit molprops adapters; unresolved legacy return values remain unavailable rather
  than being promoted to evidence, and endpoint error details are redacted from typed outcomes.
- Added explicit tool-outcome-to-evidence promotion, strict JSON record ingestion, replay-bundle
  integrity checks for status, cost, contract, chronology, and provenance links, plus the
  `adds-replay-bundle` machine-readable CLI.
- Added a bounded planner that validates state/version, stage, contracts, duplicate requests,
  chronology, step limits, and the complete required-call budget before invoking any tool.
- Added operation-specific semantic mappings for Open Targets, ChEMBL, RDKit molecular properties,
  ClinicalTrials.gov, EMA, and structured Boltz output. Boltz predictions remain contextual-only
  and cannot satisfy hard stage readiness.
- Added a bounded stage runner that preserves an attempt journal, stops after required tool
  failure, rejects missing or post-cutoff promotion context before invocation, preserves plan
  metadata, aggregates decisions conservatively, and can recover only readiness-blocked advance
  proposals to an accepted, replayable defer packet.
- Added a typed bounded program runner that chains ordered stage plans over one cumulative execution
  ledger, validates state and packet continuity, stops on non-advance or blocked outcomes, and
  requires exact accepted-packet replay of the recorded final state.
- Added typed deterministic policy replanning over paused/blocked observations, predeclared
  replacement steps, per-rule/global revision limits, append-only queue history, SHA-256-bound
  checkpoints, duplicate-key/tamper/stale-token rejection, and exact checkpoint resume.
- Added a cutoff-safe sealed evaluation contract with role-neutral opaque episode and pair
  identities, externally separated evaluator labels, salted commitments, board-bound submissions,
  explicit per-episode confidence, strict JSON Schemas and envelope readers, and synthetic
  tamper/leakage tests.
- Executed an external four-pair/eight-episode retrospective policy board over the real senicapoc
  continuous program and PALOMA-2/PALOMA-3 portfolio. The governed deterministic output was exact
  on 8/8 episodes with zero unsafe advances, while always-advance was exact on 1/8 with 7/7 unsafe
  advances and defer-safe was exact on 4/8 with zero unsafe advances. Only payload-free aggregate
  metrics, implementation/artifact hashes, gate outcomes, and explicit small-N limitations are
  released; this is not a discovery-performance or calibration claim.
- Added Open Targets disease-profile and ChEMBL molecule-mechanism profile bindings plus conservative
  disease-context, modality-mechanism, and preclinical activity-volume mappings. Disease identity
  cannot establish unmet need, and target activity volume cannot establish candidate functional
  effect.
- Added a five-stage real-registry integration path that advances through target, modality,
  candidate, and lead gates, then intentionally defers at the preclinical functional-effect gate.
- Added composite disease-context and preclinical hard gates. Each requires two linked component
  evidence predicates, two distinct source ids, two distinct valid source-content SHA-256 values,
  and no exact-byte relabeling. The preclinical gate additionally requires typed endpoint
  semantics, candidate alias resolution, and disjoint canonical upstream publication lineages.
- Added a dependency-free, payload-free pinned-evidence manifest adapter, JSON Schema, synthetic
  example, registry contracts, and conservative semantic mappings for disease burden plus treatment
  gap and candidate-target function plus disease-model effect.
- Added the dependency-free `adds-pinned-ingestion` capture/compiler path. It stores exact source
  bytes only in immutable external bundles, emits strict payload-free receipts, verifies bytes and
  chronology during compilation, and produces a pinned manifest plus mandatory human-review report.
- Hardened ingestion against signed-token URL parameters, invalid or raced size bounds, obfuscated
  raw-payload keys, non-finite summary values, and partial two-output compilation. Exact source bytes
  relabeled under different source ids now remain one independent-content unit and defer at
  composite gates.
- Added the first provider-specific ingestion contract for captured CDC MMWR HTML. It verifies
  receipt and article identity, DOI-bound source version, citation metadata, section, excerpt,
  numeric value, unit, geography, and reference period before emitting a payload-free generic job
  with an excerpt hash. Noncanonical ports, inexact DOI versions, prepublication retrieval,
  provider-field spoofing, and malformed DOI suffixes fail closed; CLI reports bind both source and
  sanitized output SHA-256. Synthetic tests cover matched independent-source advance and
  same-document defer behavior; real source bytes and reviewer jobs remain outside the release.
- Added a strict NCBI PubMed EFetch XML treatment-gap contract. It reconciles direct PMID, PMCID,
  DOI, title, canonical URL, electronic publication date, exact request identity, and
  retrieval-date-bound source version; rejects entities, retractions, ambiguous records, duplicate
  sections, provider-field spoofing, and unsupported predicates; and verifies reviewer-selected
  METHODS/RESULTS excerpts, typed comparator/value/unit, and context anchors before removing all
  excerpt and anchor text. Synthetic tests pair context-matched advance with cross-population
  defer, while an external PMID 32147964 extraction plus the broader CDC burden correctly abstains
  with `pinned_unmet_need_context_mismatch`.
- Added a strict ChEMBL functional-activity contract over one release-bound status/activity/assay/
  document/molecule/target bundle. It cross-checks linked ids, clean standardized point estimates,
  source assay classification, direct single-protein assignment, candidate aliases, target
  components, and publication lineage before stripping assay evidence text.
- Added a strict NCBI PubMed disease-model contract for one typed in-vivo exposure and endpoint. It
  checks direct article identity, retraction state, candidate/model anchors, dose, route, frequency,
  duration, endpoint variation, and p-value before stripping reviewer excerpts and anchors.
- Added a matched preclinical provider-pair integration test. Independent synthetic ChEMBL and
  PubMed lineages advance to clinical strategy; changing only the model record's upstream lineage
  defers with `pinned_functional_effect_lineage_not_independent` and promotes no evidence. A
  corresponding real-source validation was executed externally; only payload-free ids, hashes,
  outcomes, and limitations are documented publicly in a machine-readable snapshot.
- Added a strict ClinicalTrials.gov API study contract. It binds one exact receipt and registry
  version to NCT, candidate aliases, condition, protocol/result arms, denominators, population,
  posted primary endpoint, statistical analysis, and selected-arm serious-adverse-event aggregates
  before emitting a payload-free job. Source, NCT, arm, result/adverse-event group, analysis, and
  safety-count drift fail closed.
- Hardened source-pinned clinical promotion so every declared candidate alias must resolve through
  the accepted candidate id/name or its pre-approved identity aliases; mixing a canonical alias
  with an unapproved subject alias no longer authorizes the latter. Source disease aliases require
  an approved disease-name binding.
- Added bounded source-pinned clinical promotion with canonical intervention, trial, candidate and
  comparator arm roles, population, endpoint, safety, and safety-arm records projected as one
  atomic design. Clinical advance requires both `clinical_evidence_assessed` and
  `clinical_safety_assessed` from the exact study, without inferring safety acceptability. One exact
  external NCT01844505 snapshot advances and a missing-safety control defers with zero partial
  state; public documentation retains only typed values, hashes, outcomes, and limits.
- Added explicit multi-trial endpoint/safety harmonization at regulatory review. A local
  deterministic adapter and semantic mapper recompile reviewed trial/design/endpoint/safety
  selections into append-only study and synthesis records that retain hazard ratios, confidence
  intervals, source arm measurements, serious-event counts, evidence ids, and source hashes.
  Pairwise source-disjointness, exact replay, no automatic endpoint mapping, no pooling, no
  benefit-risk score, and no clinical acceptability inference are enforced by typed models and a
  recompiling continuity verifier; mismatch, overlap, pooling, forgery, and removal attacks fail
  closed.
- Added atomic ClinicalTrials.gov portfolio extraction over the exact set of independently reviewed
  single-trial jobs and external source bundles. Missing, extra, rebound, or content-hash-overlapping
  inputs fail before a payload-free generic job is written.
- Added reviewer-approved endpoint-family ontology mapping as an append-only typed ledger. Mapping
  records retain reviewer/time identity, exact trial/design/endpoint/safety bindings, endpoint and
  safety fingerprints, source evidence, and source hashes; direct commits, rebinding, mutation, and
  removal fail closed. Synthesis now requires `endpoint_mapping_id` and an exact approved binding-set
  match. Ontology identities are preserved but not authority-resolved automatically.
- Promoted pinned-manifest normalization into the executable core so direct adapter input and
  compiler output share raw-field, local-path, size, predicate, source, and chronology checks. Added
  source-receipt, ingestion-job, and review-report schemas with synthetic examples.
- Multi-source outcomes now require explicit per-evidence source selection. External source hashes
  are preserved as declared instead of silently substituting the tool-payload hash.
- Added a replayable eight-stage provider-backed integration from disease context through
  source-pinned clinical endpoint/safety design and EMA regulatory review. The single cumulative
  ledger reaches `COMPLETED` with 19 evidence events, nine claims, and all typed identities
  preserved. The synthetic control fixture and matched provenance tests do not claim scientific
  performance.
- Added matched compiled-manifest coverage: independent captured disease sources advance, while
  changing only the treatment-gap receipt to reuse the burden source defers with balanced accuracy
  1.0. This is a deterministic provenance contract test, not a scientific result.
- Added an evidence-backed `TargetRecord` ledger spanning Open Targets Ensembl identity, ChEMBL
  target-profile verification, candidate linkage, lead preservation, and pinned preclinical
  identity checks. Accepted namespace bindings cannot be removed, rebound, or shared across
  canonical targets.
- Added the typed `molecule_target_mechanism_profile` operation, target-identity JSON Schema and
  synthetic example, stage namespace gates, and matched symbol-match/symbol-mismatch coverage.
  Legacy molecule-mechanism observations no longer satisfy the default modality gate alone.
- Added evidence-backed `DiseaseRecord`, `AssayRecord`, and `ModelSystemRecord` ledgers, strict
  serialization, packet promotion, replay projection, and default stage gates. Every advance now
  requires one canonical disease; preclinical advance additionally requires current-packet assay
  and model-system records linked to the same viable candidate and pinned component evidence.
- Added a discovery-context identity schema and synthetic example plus fail-closed coverage for
  disease/model rebinding, namespace collision, unknown-candidate assay evidence, and a matched
  assay-target-link success/failure pair.
- Added evidence-backed `InterventionRecord`, `TrialRecord`, and atomic `TrialDesignRecord` ledgers
  with typed arm, population, endpoint, safety, and safety-arm children across strict
  serialization, packet promotion, replay projection, and default clinical/regulatory gates.
  Legacy ClinicalTrials.gov search observations are contextual; clinical advance requires a
  source-pinned endpoint/safety design.
- Expanded the clinical identity schema and synthetic example plus fail-closed coverage for
  intervention rebinding, trial namespace collision, unknown-intervention linkage, arm-role
  rebinding, endpoint/safety-support removal, atomic missing-safety defer, and EMA source-identity
  mismatch.
- Added exact-context matched success/failure episode contracts and arm/pair evaluation summaries
  with cutoff, ontology-key, evaluator-label, and failure-cause validation.
- Added the dependency-free `adds-bounded-agent-demo` console path and isolated-wheel coverage for
  the static demo, bounded agent loop, and replay CLI.

## 0.2.0 - 2026-07-14

- Hardened `ctdbench` 0.2.0 against class-selective abstention by separating
  all-class, conditional, and coverage-adjusted balanced accuracy; added
  per-class coverage, fail-closed label validation, and an immutable default
  Hugging Face dataset revision.
- Added public release boundary documentation, release manifest, security policy, contribution guide, citation metadata, license, and archive metadata.
- Added callable tool/database adapters (Open Targets, ChEMBL, ClinicalTrials.gov, openFDA, EMA EPAR) and multi-stage flow orchestrators (discovery_flow, episode_flow) for the first public decision-environment surface.
- Added a local RDKit-based molecular-property adapter (QED, MW, logP, H-bond donors/acceptors, Lipinski) giving the compound-design stage a computable, no-GPU druglikeness signal.
- Added `docs/12_scd_vertical_slice.md` documenting the audited end-to-end sickle cell disease (SCD) retrospective benchmark slice and prospective decision-support demo.
- Added `docs/13_target_id_governance_node.md` and
  `docs/public_evidence_summary.json` as small-N, aggregate-only scientific claim
  anchors with explicit provenance limits.
- Added the installable `benchmark/` scorer and tests for the separately hosted
  clinical-trial decision dataset; the external dataset's Croissant metadata is
  intentionally excluded from this artifact mirror.
- Added `scripts/audit/validate_vertical_slice_doc.py` to keep public benchmark numbers caveats-first and small-N scoped.
- Added `docs/release_trust_report.md` and a commit-object-based
  `scripts/audit/build_hf_release_package.py` so each Hugging Face payload is
  tied to an exact source commit/tree with per-file SHA-256 and byte sizes.
- Disambiguated stopped/withdrawn/revoked programs from serious safety signals
  on still-approved assets in both decision prompts.
- Strengthened local and CI release-audit gates for sensitive content, generated artifacts, machine-specific breadcrumbs, and public metadata completeness.
