---
pretty_name: Agentic Drug Discovery System
license: apache-2.0
viewer: false
language:
  - en
tags:
  - agentic-drug-discovery
  - scientific-verification
  - bioinformatics
  - ai-safety
  - benchmark
  - decision-support
---

# Agentic Drug Discovery System

This card describes the unuploaded 0.3.0.dev3 update candidate for the public 0.3.0.dev2 Agentic Drug Discovery System mirror. It contains the executable control plane, tests, documentation, schemas, aggregate evidence, release metadata, safety boundaries, and the `ctdbench` scorer. It is not a row dataset or model release and does not contain raw source bundles, real provider review jobs, ingestion runs, raw clinical/regulatory source snapshots, hidden labels, real curator manifests, real clinical decision, cohort, outcome-evaluation, uncertainty, design/stress/sensitivity-scenario, or closed-loop policies/manifests/submissions/catalogs/batches/receipts/packages/unit results, real scenario elicitation or hidden-dependence working records, unit-to-cluster assignments, replicate- or cluster-level results, locked episodes, generated trajectories, scheduler logs, local paths, credentials, or unpublished working notes. Upload requires exact-package review and explicit approval.

## At a Glance

- **Surface:** Hugging Face Dataset repository.
- **Public baseline:** 0.3.0.dev2 exact-source mirror, published after explicit approval.
- **Candidate state:** 0.3.0.dev3, not uploaded and pending exact-package approval.
- **Release lineage:** 0.2.0 remains the latest tagged stable release.
- **Contents:** Bounded planner, typed execution core, deterministic policy replanning and hash-bound checkpoint resume, cross-stage disease/target/assay/model-system/intervention/trial/design identity ledgers, atomic multi-trial portfolio extraction, reviewer-approved endpoint mapping, mapping-gated source-disjoint non-pooled benefit-risk synthesis, bounded source-preserving ClinicalTrials.gov harmonization, ten-dimension provenance-preserving clinical evidence tensor compilation and bounded VOI action planning, accepted-state-bindable cohort diagnostics with matched policy sensitivity and provenance-overlap reporting, preregistered package-bound clinical outcome forecasts with aggregate calibration and paired policy evaluation, dependence-audited CR1 uncertainty for additive outcome metrics, deterministic aggregate prospective clustered-board design simulation, informative-evaluability and residual-dependence stress comparison over population/evaluable targets and nominal/dependence-closed clustering, prediction-stratified binary log-IMOR pattern-mixture sensitivity with matched calibration/recovery/identification diagnostics, fingerprint-bound nominal/dependence-closed cluster-jackknife sampling calibration around every fixed log-IMOR model functional, unequal-cluster influence calibration comparing normal, Student-t, delete-mj, and experimental multiplier intervals, bounded selected-action execution with compact receipts, reviewer-only refresh and exact source-rejoined transition validation, source capture and payload-free manifest compiler, semantic mappings, dependency-free pinned-evidence adapter and binding, stage and multi-stage program runners, matched and sealed evaluators, preregistered held-out curation contracts, stage-stratified uncertainty, synthetic evaluation tests, aggregate external evaluation evidence, manifests, audit code, and the `ctdbench` scorer.
- **Excludes:** Raw source data, real sealed or held-out boards, curator identities/attestations/votes/adjudications, curation manifests, real clinical decision policies/action catalogs/evidence tensors/packages, real clinical cohort manifests/accepted-state bindings/package diagnostics/reports, real clinical prediction submissions/outcome or dependence manifests/unit labels/source assessments/unit-to-cluster assignments/cluster-level or per-unit scores, real design/stress/sensitivity scenarios, pilot or log-IMOR elicitation, prediction-stratum working records, latent outcomes, replicate records, correction-selection deliberations, real closed-loop policies/execution batches/provider requests or outcomes/receipts/reviewer refresh records/transitions, cached episode packets, label vaults, policy submissions, per-episode evaluations, hidden labels, generated trajectories, logs, credentials, local paths, or model weights.
- **Source:** Exact commit and tree are recorded in `upload_manifest.json`.

## Intended Use

- Review the public system architecture and release boundary.
- Read the caveats-first SCD vertical slice before citing benchmark numbers.
- Read the small-N target-identification results card and aggregate claim ledger.
- Inspect schema and verifier-contract documentation.
- Run the illustrative, non-benchmark eight-stage control-plane demo.
- Run the dependency-free `adds-bounded-agent-demo` planner-to-transition fixture.
- Inspect `tests/test_program_runner.py` for cumulative-ledger multi-stage stopping and exact replay.
- Inspect `tests/test_semantic_mappings.py` for the explicit unmet-need and functional-effect non-implication boundaries.
- Inspect `tests/test_pinned_evidence_adapter.py` for composite pinned-source gates, matched
  independent/same-source cases, eight-stage provider-backed execution through clinical
  endpoint/safety design and regulatory review, and exact replay.
- Inspect `docs/14_target_identity_continuity.md` and
  `tests/test_target_identity_continuity.py` for the canonical Ensembl-to-ChEMBL target ledger,
  namespace invariants, candidate links, and matched target-symbol success/failure pair.
- Inspect `docs/15_discovery_context_identity.md` and
  `tests/test_context_identity_continuity.py` for the disease, assay, and model-system ledgers,
  evidence links, stage requirements, rebinding/collision attacks, and fail-closed behavior.
- Inspect `docs/16_clinical_intervention_identity.md` and
  `tests/test_clinical_identity_continuity.py` for candidate-to-intervention-to-trial-design
  continuity, source identity checks, regulatory extension, and fail-closed attacks.
- Inspect `docs/17_pinned_source_ingestion.md` and
  `tests/test_pinned_evidence_ingestion.py` for exact source receipts, external bundle integrity,
  payload-free compilation, review gates, and matched bounded-stage integration.
- Inspect `docs/18_cdc_mmwr_ingestion.md` and `tests/test_cdc_mmwr_ingestion.py` for the CDC
  provider-specific article, section, value, unit, context, excerpt-removal, and matched
  independent-source/same-document controls.
- Inspect `docs/19_ncbi_pubmed_ingestion.md` and `tests/test_ncbi_pubmed_ingestion.py` for strict
  EFetch request and article identity, structured abstract evidence, typed treatment-gap values,
  excerpt removal, matched-context advance, and cross-population defer behavior.
- Inspect `docs/20_preclinical_provider_ingestion.md`,
  `tests/test_chembl_activity_ingestion.py`,
  `tests/test_ncbi_pubmed_disease_model_ingestion.py`, and
  `tests/test_preclinical_provider_pair.py` for release-bound ChEMBL activity, typed PubMed in-vivo
  evidence, candidate aliases, publication lineage, and matched advance/shared-lineage defer
  behavior.
- Inspect `docs/preclinical_provider_validation_snapshot.json` for the payload-free machine record
  of external source ids, typed values, hashes, matched outcomes, and limitations.
- Inspect `docs/21_clinical_provider_ingestion.md`,
  `docs/clinical_provider_validation_snapshot.json`, and
  `tests/test_clinicaltrials_gov_ingestion.py` for exact ClinicalTrials.gov receipt, NCT, arm,
  population, endpoint, posted serious-adverse-event aggregate, atomic promotion, external hashes,
  and matched missing-safety behavior.
- Inspect `docs/22_clinical_benefit_risk_synthesis.md` and
  `tests/test_clinical_benefit_risk_synthesis.py` for explicit multi-trial endpoint/safety
  selections, retained trial values and hashes, non-pooling boundaries, exact replay, and tamper
  controls.
- Inspect `docs/23_clinical_portfolio_endpoint_mapping.md` and
  `tests/test_clinical_portfolio.py` for exact-set multi-job/bundle preflight, payload-free output,
  reviewer-approved ontology identity, append-only mapping continuity, and atomic failure controls.
- Inspect `docs/24_policy_replanning_and_resume.md` and `tests/test_policy_replanning.py` for typed
  observations, bounded rule application, append-only queue revisions, hash-bound checkpoints, and
  deterministic resume.
- Inspect `docs/25_cutoff_safe_policy_evaluation.md`,
  `docs/retrospective_policy_evaluation_snapshot.json`, and
  `tests/test_sealed_evaluation.py` for role-neutral board sealing, externally separated labels,
  commitment opening, strict JSON round-trip, exact submission binding, aggregate policy
  comparison, and leakage controls.
- Inspect `docs/26_independent_heldout_evaluation.md` and
  `tests/test_heldout_evaluation.py` for preregistered cohort/label/curator contracts,
  strict-majority and independent-adjudication validation, stage minima, Wilson intervals, action
  coverage, selective risk, and the explicit no-real-result boundary.
- Inspect `docs/27_clinical_evidence_tensor_and_voi.md`,
  `agentic_drug_discovery/clinical_decision.py`, and
  `tests/test_clinical_benefit_risk_synthesis.py` for committed-synthesis tensor compilation,
  provenance-linked gaps, deterministic bounded VOI ranking, budget failure, safety-signal hold,
  integrity checks, and the evidence-workflow-only decision boundary.
- Inspect `docs/28_clinical_evidence_closed_loop.md`,
  `agentic_drug_discovery/clinical_closed_loop.py`, and the adjacent transition schema/example for
  exact selected-action execution, compact payload-free receipts, bounded reviewer-verifier
  refresh, single-use actions, exact source rejoin, and two-state transition replay.
- Inspect `docs/29_clinical_cohort_diagnostics.md`,
  `agentic_drug_discovery/clinical_cohort.py`, and the adjacent manifest/report schemas and
  compiler-generated examples for accepted-state binding, evidence-unit identity, matched policy
  sensitivity, exact gap/action denominators, cross-unit provenance overlap, and the explicit
  no-outcome/no-calibration boundary.
- Inspect `docs/30_preregistered_clinical_outcome_evaluation.md`,
  `agentic_drug_discovery/clinical_outcome_evaluation.py`, and the adjacent protocol/submission/
  manifest/report schemas for cutoff-safe package-bound forecasts, endpoint/safety provenance,
  aggregate calibration, paired policy comparisons, and the evaluator-only unit-label boundary.
- Inspect `docs/31_cluster_robust_clinical_outcome_uncertainty.md`,
  `agentic_drug_discovery/clinical_outcome_uncertainty.py`, and the adjacent dependence/protocol/
  report schemas for exact assignment coverage, known-overlap closure, aggregate CR1 intervals,
  fixed stage-by-endpoint strata, explicit no-interval states, and the private assignment boundary.
- Inspect `docs/32_prospective_clinical_outcome_design_simulation.md`,
  `agentic_drug_discovery/clinical_outcome_design_simulation.py`, and the adjacent design
  protocol/report schemas for beta-binomial known-truth simulation, production CR1 parity, IID
  diagnostic comparison, Monte Carlo target checks, and the no-automatic-selection boundary.
- Inspect `docs/33_informative_evaluability_and_dependence_stress.md`,
  `agentic_drug_discovery/clinical_outcome_stress_simulation.py`, and the adjacent stress
  protocol/report schemas for analytic estimand shifts, exact dependence blocks,
  nominal/oracle-closure CR1 comparison, combined stress signatures, and the
  no-automatic-correction boundary.
- Inspect `docs/34_preregistered_pattern_mixture_sensitivity.md`,
  `agentic_drug_discovery/clinical_outcome_pattern_mixture.py`, and the adjacent pattern-mixture
  protocol/report schemas for exact stress binding, binary log-IMOR grids, prediction-stratum
  observability, matched recovery controls, point-envelope interpretation, and the
  no-automatic-range-selection boundary.
- Inspect `docs/35_dependence_closed_pattern_mixture_uncertainty.md`,
  `agentic_drug_discovery/clinical_outcome_pattern_mixture_uncertainty.py`, and the adjacent
  protocol/report schemas for fixed-assumption model functionals, delete-one-cluster variance,
  nominal/dependence-closed calibration, Monte Carlo bounds, explicit no-interval states, and the
  no-automatic-closure boundary.
- Inspect `docs/36_unequal_cluster_influence_calibration.md`,
  `agentic_drug_discovery/clinical_outcome_pattern_mixture_influence_calibration.py`, and the
  adjacent protocol/report/summary schemas for Student-t critical values, unequal delete-mj
  pseudovalues, experimental multiplier diagnostics, dominance hard stops, and the
  no-automatic-selection boundary.
- Inspect `rl_env/specs/pinned_evidence_manifest.schema.json` and its synthetic example before
  constructing a source manifest.
- Inspect `rl_env/specs/target_identity_record.schema.json` and its synthetic example before
  producing or consuming serialized target records.
- Inspect `rl_env/specs/discovery_context_identity.schema.json` and its synthetic example before
  producing or consuming serialized disease, assay, or model-system records.
- Inspect `rl_env/specs/clinical_intervention_identity.schema.json` and its synthetic example before
  producing or consuming serialized clinical intervention, trial, or atomic design records.
- Inspect `rl_env/specs/clinical_benefit_risk_synthesis.schema.json` and its synthetic example before
  selecting source-ledger trials for cross-trial harmonization.
- Inspect `rl_env/specs/clinical_evidence_decision_package.schema.json` and its compiler-generated
  synthetic example before producing or consuming policy-bound evidence tensors or action plans.
- Inspect `rl_env/specs/clinical_evidence_decision_config.schema.json` and its synthetic example,
  then use `adds-clinical-evidence` to compile, validate, or summarize a package without importing
  internal dataclasses.
- Use `adds-clinical-evidence cohort`, `validate-cohort`, and `summarize-cohort` with the cohort
  manifest/report contracts to compare exact package rosters without treating policy variants as
  independent clinical observations.
- Use `adds-clinical-evidence evaluate-outcomes`, `validate-outcomes`, and `summarize-outcomes`
  with frozen package forecasts and an evaluator-controlled outcome manifest. The checked-in
  one-unit example verifies contract execution only and is not calibration evidence.
- Inspect `rl_env/specs/clinical_endpoint_mapping.schema.json` and
  `rl_env/specs/clinicaltrials_gov_portfolio_job.schema.json` before approving an endpoint family or
  assembling an exact multi-trial source bundle.
- Inspect `rl_env/specs/source_receipt.schema.json` and
  `rl_env/specs/pinned_evidence_ingestion_job.schema.json` before capturing or compiling a source.
- Inspect `rl_env/specs/cdc_mmwr_ingestion_job.schema.json` before authoring a CDC MMWR review job.
- Inspect `rl_env/specs/ncbi_pubmed_ingestion_job.schema.json` before authoring an NCBI PubMed
  treatment-gap review job.
- Inspect `rl_env/specs/chembl_activity_ingestion_job.schema.json` and
  `rl_env/specs/ncbi_pubmed_disease_model_ingestion_job.schema.json` before authoring preclinical
  provider review jobs.
- Inspect `rl_env/specs/clinicaltrials_gov_ingestion_job.schema.json` before authoring a reviewed
  registry study, selected-arm, population, endpoint, analysis, and serious-adverse-event contract.
- Inspect strict replay bundles and run the machine-readable `adds-replay-bundle` CLI.
- Use `benchmark/` to score the separately hosted clinical-trial decision dataset.
- Track provenance for the public artifact surface.
- Inspect the mirrored GitHub release surface and source-commit provenance.

## Sealed Retrospective Evaluation

The external evaluator executed four matched pairs and eight cutoff-safe episodes built from the
real senicapoc continuous program and PALOMA-2/PALOMA-3 clinical portfolio. Only the payload-free
aggregate and artifact hashes are included here.

| Policy | Exact | Success arm | Failure arm | Both correct | Unsafe advance |
| --- | ---: | ---: | ---: | ---: | ---: |
| Deterministic gated stage output | 8/8 | 4/4 | 4/4 | 4/4 | 0/7 |
| Always advance counterfactual | 1/8 | 1/4 | 0/4 | 0/4 | 7/7 |
| Defer-safe counterfactual | 4/8 | 0/4 | 4/4 | 0/4 | 0/7 |

This is a small contract diagnostic. It does not establish drug-discovery performance,
prospective clinical utility, policy optimality, or confidence calibration. The complete board,
cached real packets, label vault, commitment nonces, submissions, and per-episode evaluations stay
outside both public release surfaces.

## Artifact Map

| Path | Purpose |
| --- | --- |
| `README.md` | This Hugging Face Dataset card. |
| `github/README.md` | GitHub README preserved inside the Hub mirror. |
| `release_manifest.json` | Cross-surface release manifest. |
| `release_decision_packet.json` | Machine-readable launch decision packet. |
| `huggingface/release_manifest.json` | Hugging Face-specific include/exclude manifest. |
| `upload_manifest.json` | Exact uploaded file list and source commit. |
| `docs/release_boundary.md` | Public-release boundary and exclusion rules. |
| `docs/release_trust_report.md` | Trust claims, machine anchors, and interpretation warnings. |
| `docs/12_scd_vertical_slice.md` | Audited SCD vertical slice, with small-N caveats. |
| `docs/13_target_id_governance_node.md` | Upstream target-identification results card. |
| `docs/14_target_identity_continuity.md` | Executable target ledger, stage namespace requirements, and fail-closed identity rules. |
| `docs/15_discovery_context_identity.md` | Disease, assay, and model-system ledgers, evidence links, stage gates, and matched failure contract. |
| `docs/16_clinical_intervention_identity.md` | Candidate-to-intervention-to-trial-design continuity, source checks, regulatory extension, and failure contract. |
| `docs/17_pinned_source_ingestion.md` | Exact external source capture, payload-free compilation, review gates, and control-plane integration. |
| `docs/18_cdc_mmwr_ingestion.md` | CDC MMWR article binding, evidence-location checks, payload-free extraction, and matched stage behavior. |
| `docs/19_ncbi_pubmed_ingestion.md` | NCBI PubMed XML identity, structured abstract anchors, payload-free extraction, and context-mismatch behavior. |
| `docs/20_preclinical_provider_ingestion.md` | ChEMBL functional-activity and PubMed disease-model contracts, payload-free external validation snapshot, and lineage-independence failure control. |
| `docs/preclinical_provider_validation_snapshot.json` | Payload-free machine record of provider ids, typed values, hashes, matched outcomes, and limitations. |
| `docs/21_clinical_provider_ingestion.md` | ClinicalTrials.gov source receipt, endpoint/safety design identities, bounded promotion, and matched failure contract. |
| `docs/clinical_provider_validation_snapshot.json` | Payload-free NCT/design/safety identities, artifact hashes, live stage outcome, matched control, and limitations. |
| `docs/22_clinical_benefit_risk_synthesis.md` | Explicit reviewed selection, retained trial values, source-disjoint provenance, non-pooling boundary, and fail-closed synthesis behavior. |
| `docs/23_clinical_portfolio_endpoint_mapping.md` | Exact multi-bundle portfolio transaction, reviewer-approved endpoint mapping ledger, synthesis dependency, and release boundary. |
| `docs/24_policy_replanning_and_resume.md` | Typed policy observations, bounded replans, checkpoint integrity, and deterministic resume. |
| `docs/25_cutoff_safe_policy_evaluation.md` | Cutoff-safe sealing, submission, scoring, real aggregate results, and interpretation limits. |
| `docs/26_independent_heldout_evaluation.md` | Preregistered held-out protocol, evaluator-only curator manifest, stage uncertainty, and release boundary. |
| `docs/27_clinical_evidence_tensor_and_voi.md` | Exact evidence cells, typed workflow gaps, bounded VOI ranking, budget behavior, provenance replay, and interpretation boundaries. |
| `docs/29_clinical_cohort_diagnostics.md` | Exact package/state rosters, evidence-unit identity, matched policy sensitivity, provenance overlap, and calibration boundaries. |
| `docs/30_preregistered_clinical_outcome_evaluation.md` | Package-bound probability forecasts, cutoff-safe endpoint/safety outcomes, aggregate calibration, paired policy metrics, and evaluator-only boundaries. |
| `docs/31_cluster_robust_clinical_outcome_uncertainty.md` | Dependence commitments, known-overlap closure, aggregate CR1 intervals, fixed strata, fail-closed diagnostics, and interpretation boundaries. |
| `docs/32_prospective_clinical_outcome_design_simulation.md` | Beta-binomial design scenarios, analytic truths, CR1/IID coverage comparison, Monte Carlo target checks, and gate-selection boundaries. |
| `docs/33_informative_evaluability_and_dependence_stress.md` | Outcome-dependent evaluability, analytic population/evaluable shifts, residual dependence blocks, nominal/oracle-closure CR1 comparison, and correction boundaries. |
| `docs/34_preregistered_pattern_mixture_sensitivity.md` | Prediction-stratified binary log-IMOR sensitivity, observable aggregate inputs, matched recovery gates, public synthetic results, and claim boundaries. |
| `docs/35_dependence_closed_pattern_mixture_uncertainty.md` | Fixed log-IMOR model functionals, dependence-closed cluster jackknife, all-grid calibration, Monte Carlo precision, synthetic results, and claim boundaries. |
| `docs/36_unequal_cluster_influence_calibration.md` | Few, unequal, and dominant-cluster interval calibration, Student-t and delete-mj comparisons, experimental multiplier diagnostics, and operational boundaries. |
| `docs/retrospective_policy_evaluation_snapshot.json` | Payload-free machine aggregate with policy metrics, artifact hashes, gate outcomes, and withheld-data boundary. |
| `docs/public_evidence_summary.json` | Machine-readable aggregate claims and limitations. |
| `agentic_drug_discovery/` | Bounded planning, typed tool execution, semantic promotion, stage and program orchestration, matched evaluation, replay, and fail-closed transitions. |
| `agentic_drug_discovery/sealed_evaluation.py` | Role-neutral board sealing, external label vaults, commitments, strict envelope readers, submission validation, and aggregate scoring. |
| `agentic_drug_discovery/heldout_evaluation.py` | Preregistered protocol binding, independent curation validation, Wilson intervals, action coverage, selective risk, and strict aggregate reporting. |
| `agentic_drug_discovery/ingestion.py` | Immutable source receipts, external bundle verification, payload-free manifest compilation, and review reports. |
| `agentic_drug_discovery/cdc_mmwr.py` | CDC MMWR article and reviewer-selected evidence verification with excerpt removal. |
| `agentic_drug_discovery/ncbi_pubmed.py` | NCBI PubMed EFetch article and treatment-gap evidence verification with excerpt and anchor removal. |
| `agentic_drug_discovery/chembl_activity.py` | ChEMBL release/resource reconciliation and typed functional-activity verification with assay-text removal. |
| `agentic_drug_discovery/clinicaltrials_gov.py` | ClinicalTrials.gov study, arm, population, endpoint, statistical-analysis, and serious-adverse-event verification with payload removal. |
| `agentic_drug_discovery/clinical_portfolio.py` | Atomic exact-set multi-trial extraction with source-hash disjointness and payload-free output. |
| `agentic_drug_discovery/clinical_endpoint_mapping.py` | Strict approved-mapping parser, endpoint/safety fingerprint compiler, approval chronology, and replay validation. |
| `agentic_drug_discovery/clinical_synthesis.py` | Deterministic source-ledger compiler for trial-level hazard ratios and serious-event risk differences without pooling. |
| `agentic_drug_discovery/clinical_decision.py` | Committed-synthesis tensor compiler, typed gaps, deterministic budget-aware bounded VOI planner, integrity envelopes, and state replay. |
| `agentic_drug_discovery/clinical_cohort.py` | Accepted-state-bindable package rosters, deterministic cohort aggregation, matched policy comparisons, strict readers, and cross-unit provenance overlap. |
| `agentic_drug_discovery/clinical_outcome_evaluation.py` | Preregistered protocol and submission binding, post-deadline outcome provenance, aggregate Brier/calibration/threshold metrics, paired policy comparisons, and full replay. |
| `agentic_drug_discovery/clinical_outcome_uncertainty.py` | Frozen dependence commitments, exact assignment coverage, known-overlap closure, CR1 policy/stratum/paired intervals, strict readers, and full replay. |
| `agentic_drug_discovery/clinical_outcome_design_simulation.py` | Bounded deterministic beta-binomial simulation, analytic truths, production CR1 parity, IID diagnostics, candidate-gate evaluation, strict readers, and replay. |
| `agentic_drug_discovery/clinical_outcome_stress_simulation.py` | Bounded block-Polya stress simulation, analytic population/evaluable truths, nominal/dependence-closed CR1 comparison, strict boundaries, readers, summaries, and replay. |
| `agentic_drug_discovery/clinical_outcome_pattern_mixture.py` | Exact stress-bound binary log-IMOR grids, prediction-stratified aggregate estimators, matched calibration/recovery/identification diagnostics, strict readers, summaries, and replay. |
| `agentic_drug_discovery/clinical_outcome_pattern_mixture_uncertainty.py` | Exact point-report binding, nominal/dependence-closed delete-one-cluster jackknife inference, model-functional coverage, Monte Carlo bounds, fail-closed statuses, strict readers, summaries, and replay. |
| `agentic_drug_discovery/clinical_outcome_pattern_mixture_influence_calibration.py` | Student-t critical values, unequal delete-mj pseudovalues, experimental multiplier intervals, production eligibility, Monte Carlo calibration, strict readers, summaries, and replay. |
| `adapters/pinned_evidence_adapter.py` | Dependency-free validation and lookup for source-pinned, payload-free evidence manifests. |
| `adapters/clinical_synthesis_adapter.py` | Local normalization of approved endpoint mappings and reviewed synthesis selections without supplied source measurements. |
| `adapters/execution_registry.py` | Typed contracts for the pinned adapter and caller-supplied GitHub adapter instances. |
| `rl_env/specs/pinned_evidence_manifest.schema.json` | Machine-readable pinned-record schema; the adjacent example is synthetic. |
| `rl_env/specs/target_identity_record.schema.json` | Machine-readable cross-stage target record; the adjacent example is synthetic. |
| `rl_env/specs/discovery_context_identity.schema.json` | Machine-readable disease, assay, and model-system records; the adjacent example is synthetic. |
| `rl_env/specs/clinical_intervention_identity.schema.json` | Machine-readable clinical intervention, trial, endpoint, safety, and atomic design records; the adjacent example is synthetic. |
| `rl_env/specs/clinical_endpoint_mapping.schema.json` | Machine-readable approved reviewer, ontology identity, and exact endpoint/safety binding contract; the adjacent example is synthetic. |
| `rl_env/specs/clinical_benefit_risk_synthesis.schema.json` | Machine-readable reviewed multi-trial selection contract; the adjacent example is synthetic. |
| `rl_env/specs/clinical_evidence_decision_package.schema.json` | Integrity-bound policy, exact tensor, gaps, action catalog, budget, and bounded-VOI plan contract; the adjacent example is synthetic. |
| `rl_env/specs/clinical_evidence_decision_package.relaxed.example.json` | Compiler-generated synthetic `ADVANCE` package over the same evidence unit for reproducible matched-policy sensitivity. |
| `rl_env/specs/clinical_evidence_cohort_manifest.schema.json` | Exact package roster and optional all-or-none accepted-state SHA-256 binding contract; the adjacent example is synthetic. |
| `rl_env/specs/clinical_evidence_cohort_report.schema.json` | Package/policy strata, matched transitions, gap/action diagnostics, provenance overlap, and explicit no-outcome calibration-status contract; the adjacent example is synthetic. |
| `rl_env/specs/clinical_evidence_cohort_summary.schema.json` | Compact cohort summary and optional validation-status contract. |
| `rl_env/specs/clinical_outcome_evaluation_protocol.schema.json` | Public cohort/cutoff/outcome/harmonization/curation/metric preregistration contract; the adjacent example is synthetic. |
| `rl_env/specs/clinical_prediction_submission.schema.json` | Exact package/evidence-unit-bound favorable-outcome probability contract; adjacent examples are synthetic. |
| `rl_env/specs/clinical_outcome_manifest.schema.json` | Evaluator-only endpoint/safety assessment and post-deadline source-provenance contract; the adjacent example is synthetic. |
| `rl_env/specs/clinical_outcome_evaluation_report.schema.json` | Aggregate attrition, Wilson, Brier/calibration/threshold, paired-policy, and provenance-overlap contract; the adjacent example is synthetic. |
| `rl_env/specs/clinical_outcome_dependence_manifest.schema.json` | Evaluator-only exact unit-to-cluster assignment and dependence-basis contract; the adjacent example is synthetic. |
| `rl_env/specs/clinical_outcome_uncertainty_protocol.schema.json` | Public dependence-construction, confidence, cluster-floor, dominance, strata, and metric preregistration contract; the adjacent example is synthetic. |
| `rl_env/specs/clinical_outcome_uncertainty_report.schema.json` | Aggregate cluster diagnostics and CR1 policy, stratum, and paired-policy interval contract; the adjacent example is synthetic. |
| `rl_env/specs/clinical_outcome_uncertainty_summary.schema.json` | Compact dependence-aware uncertainty and optional validation-status contract. |
| `rl_env/specs/clinical_outcome_design_simulation_protocol.schema.json` | Seeded cluster-size, prevalence, ICC, evaluability, prediction-pattern, gate, and Monte Carlo design contract; the adjacent example is synthetic. |
| `rl_env/specs/clinical_outcome_design_simulation_report.schema.json` | Aggregate analytic truth, replicate diagnostic, IID/CR1 performance, gate status, and privacy-boundary contract; the adjacent example is synthetic. |
| `rl_env/specs/clinical_outcome_design_simulation_summary.schema.json` | Compact scenario/gate coverage, yield, width, error, status, and optional replay-validation contract. |
| `rl_env/specs/clinical_outcome_stress_simulation_protocol.schema.json` | Exact dependence partitions, outcome-specific evaluability, fixed estimand/mode comparison, gate, RNG, and Monte Carlo commitments; the adjacent example is synthetic. |
| `rl_env/specs/clinical_outcome_stress_simulation_report.schema.json` | Aggregate analytic shifts, mode diagnostics, target performance, and fixed claim-boundary contract; the adjacent example is synthetic. |
| `rl_env/specs/clinical_outcome_stress_simulation_summary.schema.json` | Compact evaluable-only target passage and dependence-closure recovery contract. |
| `rl_env/specs/clinical_outcome_pattern_mixture_protocol.schema.json` | Exact stress binding, log-IMOR grid, analyzability, mean-envelope width, bias, and method commitments; the adjacent example is synthetic. |
| `rl_env/specs/clinical_outcome_pattern_mixture_report.schema.json` | Aggregate grid curves, estimand bias, matched recovery, point-envelope inclusion, fail-closed support, and claim boundaries; the adjacent example is synthetic. |
| `rl_env/specs/clinical_outcome_pattern_mixture_summary.schema.json` | Compact log-IMOR, analyzability, recovery, identification, and claim-boundary contract. |
| `rl_env/specs/clinical_outcome_pattern_mixture_uncertainty_protocol.schema.json` | Exact stress/protocol/report binding, fixed analysis modes, cluster gates, calibration targets, and closure anchor; the adjacent example is synthetic. |
| `rl_env/specs/clinical_outcome_pattern_mixture_uncertainty_report.schema.json` | Aggregate grid-level model-functional coverage, population recovery, Monte Carlo bounds, jackknife diagnostics, closure comparisons, and claim boundaries; the adjacent example is synthetic. |
| `rl_env/specs/clinical_outcome_pattern_mixture_uncertainty_summary.schema.json` | Compact all-grid calibration, truth-aligned coverage, dependence-closure response, and claim-boundary contract. |
| `rl_env/specs/clinical_outcome_pattern_mixture_influence_protocol.schema.json` | Exact stress/point-report binding, canonical method order, calibration gates, production eligibility, and multiplier commitments. |
| `rl_env/specs/clinical_outcome_pattern_mixture_influence_report.schema.json` | Aggregate method-grid-metric calibration, unequal-cluster structure, hard-stop, RNG, and claim-boundary contract. |
| `rl_env/specs/clinical_outcome_pattern_mixture_influence_summary.schema.json` | Compact method comparison, primary-grid diagnostics, production eligibility, and claim-boundary contract. |
| `rl_env/specs/sealed_evaluation_board.schema.json` | Policy-visible, role-neutral cutoff episode and matched-pair board contract. |
| `rl_env/specs/sealed_evaluation_vault.schema.json` | Evaluator-only label, failure-cause, arm-role, and commitment-opening contract. |
| `rl_env/specs/policy_evaluation_submission.schema.json` | Exact board-bound policy prediction and confidence contract. |
| `rl_env/specs/policy_evaluation_report.schema.json` | Aggregate and evaluator-only per-episode scoring report contract. |
| `rl_env/specs/heldout_evaluation_protocol.schema.json` | Public preregistration contract for cohort, labels, opaque roster, stages, and metrics; the adjacent example is synthetic. |
| `rl_env/specs/heldout_curation_manifest.schema.json` | Evaluator-only opaque declarations, votes, consensus, and adjudication contract. |
| `rl_env/specs/stage_stratified_evaluation_report.schema.json` | Aggregate exact counts, Wilson intervals, sufficiency flags, action coverage, and selective-risk contract; the adjacent example is synthetic. |
| `rl_env/specs/source_receipt.schema.json` | Machine-readable exact source version, locator, hash, size, retrieval time, and transport. |
| `rl_env/specs/pinned_evidence_ingestion_job.schema.json` | Machine-readable reviewer-authored summaries linked to external source receipts. |
| `rl_env/specs/cdc_mmwr_ingestion_job.schema.json` | Machine-readable CDC MMWR article, context, value, unit, and excerpt review contract. |
| `rl_env/specs/ncbi_pubmed_ingestion_job.schema.json` | Machine-readable PubMed article, METHODS/RESULTS, typed treatment-gap value, and context-anchor contract. |
| `rl_env/specs/chembl_activity_ingestion_job.schema.json` | Machine-readable ChEMBL release, linked resource, typed endpoint, candidate alias, target, and lineage contract. |
| `rl_env/specs/ncbi_pubmed_disease_model_ingestion_job.schema.json` | Machine-readable PubMed in-vivo exposure, endpoint, model, candidate, and lineage contract. |
| `rl_env/specs/clinicaltrials_gov_ingestion_job.schema.json` | Machine-readable exact study, arm, population, endpoint, measurement, analysis, and serious-adverse-event contract. |
| `rl_env/specs/clinicaltrials_gov_portfolio_job.schema.json` | Machine-readable exact set of single-trial jobs, receipts, identities, and approved mapping bindings. |
| `rl_env/specs/clinical_evidence_decision_config.schema.json` | Machine-readable accepted-synthesis, policy, action-catalog, and output-identity compiler contract; the adjacent example is synthetic. |
| `rl_env/specs/clinical_evidence_decision_summary.schema.json` | Machine-readable compact package summary and optional state-replay validation-report contract. |
| `tests/test_target_identity_continuity.py` | Namespace rebinding/collision, broken candidate link, and matched target-symbol coverage. |
| `tests/test_context_identity_continuity.py` | Disease/model rebinding, assay collision, unknown-candidate evidence, and strict example parsing. |
| `tests/test_clinical_identity_continuity.py` | Intervention rebinding, trial collision, unknown-intervention linkage, support removal, and strict example parsing. |
| `tests/test_pinned_evidence_ingestion.py` | Receipt/job parsing, source tamper checks, compiler boundaries, CLI capture, and matched source-independence coverage. |
| `tests/test_cdc_mmwr_ingestion.py` | Provider identity, location, value, unit, excerpt removal, stage transition, and matched-pair coverage. |
| `tests/test_ncbi_pubmed_ingestion.py` | PubMed identity, request, XML/retraction, section, value, anchor, stage transition, and matched-pair coverage. |
| `tests/test_chembl_activity_ingestion.py` | ChEMBL release/resource identity, endpoint, target, alias, lineage, text-removal, and CLI-hash coverage. |
| `tests/test_ncbi_pubmed_disease_model_ingestion.py` | PubMed article, exposure, endpoint, model/candidate anchor, text-removal, and CLI-hash coverage. |
| `tests/test_preclinical_provider_pair.py` | Matched independent-lineage advance and shared-lineage defer integration coverage. |
| `tests/test_clinicaltrials_gov_ingestion.py` | Strict registry extraction, payload removal, atomic promotion, continuity attacks, and matched mismatch coverage. |
| `tests/test_clinical_benefit_risk_synthesis.py` | Two-source tool-to-replay synthesis plus mismatch, overlap, pooling, forgery, unbound-support, direct-commit, and removal controls. |
| `tests/test_clinical_portfolio.py` | Exact-set portfolio extraction, source chronology/disjointness, strict schemas, payload removal, and atomic CLI failure controls. |
| `tests/test_clinical_decision_cli.py` | Exact package reproduction, accepted-packet provenance, strict config parsing, atomic CLI output, replay validation, and compact summary coverage. |
| `tests/test_clinical_cohort.py` | State-bound roster replay, matched policy sensitivity, provenance overlap, strict readers/schemas, tamper rejection, and atomic cohort CLI coverage. |
| `tests/test_clinical_outcome_evaluation.py` | Cutoff/source/package/roster controls, attrition, calibration math, paired comparison, strict schemas/readers, and atomic outcome CLI coverage. |
| `tests/test_clinical_outcome_uncertainty.py` | CR1 math, paired covariance, fixed strata, chronology, known-overlap closure, non-estimable states, privacy, strict readers, and atomic CLI coverage. |
| `tests/test_clinical_outcome_design_simulation.py` | Analytic truths, seeded replay, ICC undercoverage stress, floor/dominance/attrition states, strict bounds/readers, privacy, schemas, and atomic CLI coverage. |
| `tests/test_clinical_outcome_stress_simulation.py` | Analytic estimand shifts, informative-selection bias, hidden-linkage undercoverage, oracle-closure recovery, combined stress, exact partitions, strict readers, privacy, schemas, and atomic CLI coverage. |
| `tests/test_clinical_outcome_pattern_mixture.py` | Binary log-IMOR recovery, excluded-grid controls, MCAR alignment, sparse-stratum failure, exact replay, privacy, schemas, and atomic CLI coverage. |
| `tests/test_clinical_outcome_pattern_mixture_uncertainty.py` | All-grid jackknife calibration, hidden-linkage repair, independent-mode equivalence, model-functional/population separation, Monte Carlo bounds, fail-closed states, exact replay, privacy, schemas, and CLI coverage. |
| `tests/test_clinical_outcome_pattern_mixture_influence_calibration.py` | Student-t references, delete-mj algebra, seed isolation, dominant-cluster hard stops, strict schemas/readers, public exact replay, and CLI coverage. |
| `tests/test_sealed_evaluation.py` | Synthetic board determinism, commitment, submission, confidence, schema, leakage, and baseline-policy coverage. |
| `tests/` | Dependency-free planning, multi-stage stopping, mapping, evaluation, execution, replay, and transition regression tests. |
| `benchmark/` | Installable `ctdbench` scorer and tests. |
| `docs/public_launch_checklist.md` | Human launch checklist before any visibility change. |
| `scripts/audit/*.py` | Local release audits and reproducible Hub package builder. |

## Not Included

- Raw source snapshots or full case banks.
- Raw source bundles, real provider review jobs, ingestion runs, multi-trial portfolio selections,
  endpoint-family reviewer approvals, ontology-authority resolutions, or reviewer working files.
- Hidden/evaluator labels or locked episode records.
- Real sealed evaluation boards, cached episode packets, label vaults, commitment nonces, policy
  submissions, or per-episode evaluations.
- Generated reward/verifier outputs or run logs.
- Credentials, local machine paths, or private infrastructure details.
- Model weights or a complete autonomous discovery or wet-lab system.
- Live adapter implementations, endpoint configuration, or raw execution ledgers.
- A real matched success/failure episode corpus or a claim of discovery performance.
- A pooled meta-analysis, benefit-risk score, clinical acceptability judgment, or treatment
  recommendation; the synthesis path is descriptive and trial-preserving only.
- Real disease-burden, treatment-gap, functional-assay, or disease-model source payloads. The
  included pinned manifest example is synthetic and demonstrates the contract only.
- Source-pinned clinical registry payloads or reviewer jobs. Typed synthetic design records and one
  payload-free external validation snapshot are included.
- Provider-specific reviewed disease/preclinical ingestion jobs or real compiled manifests.
- Croissant metadata for `jang1563/clinical-trial-decision-benchmark`; that
  metadata belongs to the separate external dataset, not this artifact mirror.

## Linked External Dataset

The scorer in `benchmark/` targets
`https://huggingface.co/datasets/jang1563/clinical-trial-decision-benchmark`.
That dataset has its own card, rows, and Croissant metadata. This repository's
Hub package intentionally does not duplicate those data or metadata.

## Validation Before Upload

Run these checks from the GitHub repository root before creating or updating the Hugging Face repository:

```bash
python3 -m pip install -e . -e ./benchmark pytest build ruff
python3 scripts/audit/github_release_file_audit.py
python3 scripts/audit/validate_hf_release_package.py
python3 scripts/audit/validate_public_launch_packet.py
python3 scripts/audit/validate_vertical_slice_doc.py
python3 scripts/audit/validate_policy_evaluation_snapshot.py
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

## Hub Placement

- Repository type: Dataset
- Repo id: `jang1563/agentic-drug-discovery-system`
- Current visibility: public and ungated
- Current public update: 0.3.0.dev2, published after explicit approval
- Candidate update: 0.3.0.dev3, not uploaded and pending exact-package approval

## Source

Primary source repository:

`https://github.com/jang1563/agentic-drug-discovery-system`
