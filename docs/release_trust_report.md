# Release Trust Report

Last reviewed: 2026-08-20

This report summarizes what the public GitHub repository and Hugging Face Dataset mirror are intended to prove, what they do not prove, and which files machines should inspect first. The 0.3.0.dev2 evidence-governed execution, held-out evaluation, clinical planning, closed-loop, and bounded registry-harmonization update remains the approved public development baseline. The 0.3.0.dev3 clinical outcome and uncertainty research extension is an unapproved, unmerged, and not-uploaded candidate; 0.2.0 remains the latest tagged stable release.

## Trust Claims

| Claim | Evidence | Boundary |
| --- | --- | --- |
| The public artifact is intentionally scoped. | `docs/release_boundary.md`, `release_manifest.json`, `huggingface/release_manifest.json` | Raw source snapshots, evaluator-only labels, locked episodes, generated trajectories, logs, credentials, local paths, and model weights are excluded. |
| The release decision is machine-readable. | `release_decision_packet.json` | The 0.3.0.dev3 candidate records a hold pending explicit approval while preserving the 0.3.0.dev2 public baseline; merge and Hub upload remain blocked until a new exact-package approval record exists. |
| The SCD vertical slice is caveats-first. | `docs/12_scd_vertical_slice.md`, `scripts/audit/validate_vertical_slice_doc.py` | The slice is one disease, small-N, and not evidence of broad clinical prediction or autonomous drug design capability. |
| Aggregate claims are machine-readable. | `docs/public_evidence_summary.json`, `docs/13_target_id_governance_node.md` | Raw runs and per-record gold remain excluded; aggregate values are not independent replication. |
| Sealed policy evaluation preserves the answer boundary. | `docs/25_cutoff_safe_policy_evaluation.md`, `docs/retrospective_policy_evaluation_snapshot.json`, `agentic_drug_discovery/sealed_evaluation.py`, `tests/test_sealed_evaluation.py` | Role-neutral observations carry cutoff-safe cached packets and salted commitments while labels remain in an external vault. One external 4-pair/8-episode run reports aggregate contract metrics only; it does not establish discovery performance, calibration, policy optimality, or prospective utility. |
| Held-out evaluation is preregistered and stage-stratified. | `docs/26_independent_heldout_evaluation.md`, `agentic_drug_discovery/heldout_evaluation.py`, `rl_env/specs/heldout_evaluation_protocol.schema.json`, `rl_env/specs/heldout_curation_manifest.schema.json`, `rl_env/specs/stage_stratified_evaluation_report.schema.json`, `tests/test_heldout_evaluation.py` | Protocol, opaque roster, consensus/adjudication, chronology, stage minima, exact denominators, Wilson intervals, action coverage, and selective risk fail closed in synthetic tests. Real identity and attestation truth remains a human-governance responsibility, vote-level artifacts stay external, and no real independently curated result is claimed. |
| The control plane fails closed on invalid transitions. | `agentic_drug_discovery/`, `tests/test_environment.py` | Tests cover state, evidence, action, budget, chronology, contradiction, and verifier contracts; they validate control semantics, not scientific efficacy. |
| Tool execution is typed and replay-linked. | `agentic_drug_discovery/execution.py`, `agentic_drug_discovery/serialization.py`, `tests/test_execution.py` | Adapter payloads remain observations until explicit evidence promotion; replay verifies request, payload-hash, packet, action, and evidence links but does not establish scientific truth. |
| Composite scientific gates require pinned independent sources. | `agentic_drug_discovery/environment.py`, `agentic_drug_discovery/verifiers.py`, `adapters/pinned_evidence_adapter.py`, `rl_env/specs/pinned_evidence_manifest.schema.json`, `tests/test_pinned_evidence_adapter.py` | Disease context requires burden plus treatment gap; preclinical validation requires candidate-target function plus disease-model effect. Source identity, dates, exact bytes, typed endpoints, candidate aliases, and upstream publication lineages are checked, but the repository does not certify source truth or publish real source payloads. |
| Public-source bytes can be pinned without entering the release surface. | `docs/17_pinned_source_ingestion.md`, `agentic_drug_discovery/ingestion.py`, `rl_env/specs/source_receipt.schema.json`, `tests/test_pinned_evidence_ingestion.py` | Capture writes immutable receipt/payload bundles only outside Git; compilation rechecks bytes and emits payload-free summaries plus a mandatory review report. Exact-byte reuse cannot be relabeled into machine independence. Hash and schema checks do not prove source authority, summary fidelity, scientific independence, or validity. |
| Reviewer-selected CDC MMWR evidence is bound to a captured article and location. | `docs/18_cdc_mmwr_ingestion.md`, `agentic_drug_discovery/cdc_mmwr.py`, `rl_env/specs/cdc_mmwr_ingestion_job.schema.json`, `tests/test_cdc_mmwr_ingestion.py` | The provider path checks receipt/article identity, section, excerpt, value, unit, geography, and reference period, then removes the excerpt. A verified real snapshot remains external; public fixtures are synthetic, and these checks do not prove source authority, clinical sufficiency, or scientific correctness. |
| Reviewer-selected PubMed treatment-gap evidence is bound to one EFetch record and structured abstract context. | `docs/19_ncbi_pubmed_ingestion.md`, `agentic_drug_discovery/ncbi_pubmed.py`, `rl_env/specs/ncbi_pubmed_ingestion_job.schema.json`, `tests/test_ncbi_pubmed_ingestion.py` | The provider checks exact request identity, direct PMID/PMCID/DOI/title/date fields, retraction state, METHODS/RESULTS excerpts, typed gap value, and context anchors, then removes all excerpt and anchor text. The verified real record remains external. The real PubMed cohort and CDC burden do not share one population and correctly defer. This does not prove full-text coverage, representativeness, efficacy, or scientific correctness. |
| Preclinical provider evidence is typed and lineage-bound before composite promotion. | `docs/20_preclinical_provider_ingestion.md`, `docs/preclinical_provider_validation_snapshot.json`, `agentic_drug_discovery/chembl_activity.py`, `agentic_drug_discovery/ncbi_pubmed.py`, `tests/test_chembl_activity_ingestion.py`, `tests/test_ncbi_pubmed_disease_model_ingestion.py`, `tests/test_preclinical_provider_pair.py` | ChEMBL release resources and one PubMed in-vivo record are reconciled into payload-free typed jobs. One external context-matched pair advances; a counterfactual shared-publication lineage defers with no partial promotion. Raw payloads and jobs remain external. The machine snapshot records ids, hashes, outcomes, and replay limits. This proves the implemented contract path, not source authority, assay validity, model translation, candidate efficacy, or discovery performance. |
| Target identity remains continuous across implemented stages. | `docs/14_target_identity_continuity.md`, `agentic_drug_discovery/models.py`, `agentic_drug_discovery/verifiers.py`, `rl_env/specs/target_identity_record.schema.json`, `tests/test_target_identity_continuity.py` | Open Targets creates the Ensembl/gene-symbol record; ChEMBL may extend it only after target-profile, molecule, and mechanism agreement. This proves deterministic identity handling, not that the target or mechanism is scientifically valid. |
| Disease, assay, and model-system identities remain evidence-linked. | `docs/15_discovery_context_identity.md`, `rl_env/specs/discovery_context_identity.schema.json`, `tests/test_context_identity_continuity.py`, `tests/test_pinned_evidence_adapter.py` | Every advance requires a canonical disease. Preclinical advance additionally requires current-packet assay and model-system records linked to the accepted candidate and pinned evidence. This verifies identity continuity, not assay validity, model relevance, or efficacy. |
| Clinical intervention, trial, design, and safety identities remain source-linked. | `docs/16_clinical_intervention_identity.md`, `rl_env/specs/clinical_intervention_identity.schema.json`, `tests/test_clinical_identity_continuity.py` | Accepted intervention, trial, arm-role, population, endpoint, safety-record, safety-arm, namespace, and evidence links cannot be removed or rebound; EMA source asset or INN must match the accepted intervention. This verifies deterministic identity handling, not source truth, efficacy, safety acceptability, or regulatory validity. |
| Source-pinned ClinicalTrials.gov evidence promotes atomically. | `docs/21_clinical_provider_ingestion.md`, `docs/clinical_provider_validation_snapshot.json`, `docs/48_ra_olokizumab_mtx_ir_same_stratum_replication.md`, `agentic_drug_discovery/clinicaltrials_gov.py`, `rl_env/specs/clinicaltrials_gov_ingestion_job.schema.json`, `tests/test_clinicaltrials_gov_ingestion.py` | One exact registry receipt is reconciled through NCT/version, candidate/condition, protocol/result/adverse-event arms, population, posted endpoint, analysis, and serious-adverse-event affected/at-risk counts. Registry day/month/year precision is retained; partial periods map to a declared conservative period end and incorrect boundaries fail closed. The bounded external examples advance; removing only safety metadata defers with no partial identity state. This proves exact aggregate reconciliation, not registry authority, endpoint/event validity, participant-level results, safety acceptability, efficacy, or discovery performance. |
| Cross-trial benefit-risk synthesis preserves source-level provenance without pooling. | `docs/22_clinical_benefit_risk_synthesis.md`, `docs/46_ra_olokizumab_source_disjoint_additive_tensor.md`, `docs/ra_olokizumab_additive_tensor_validation_snapshot.json`, `docs/retrospective_policy_evaluation_snapshot.json`, `agentic_drug_discovery/clinical_effects.py`, `agentic_drug_discovery/clinical_synthesis.py`, `agentic_drug_discovery/clinical_decision.py`, `rl_env/specs/clinical_benefit_risk_synthesis.schema.json`, `tests/test_clinical_benefit_risk_synthesis.py` | Reviewed trial/design/endpoint/safety selections are recompiled from committed source-pinned ledgers. Hazard, odds, and risk ratios use fixed favorable-direction contracts. Risk differences use null 0, endpoint direction, candidate-first sign binding, and either a percentage-point source scale or a bounded binary-count/proportion scale. The decision tensor applies log-CI width only to ratios and normalizes additive precision to percentage points, requiring the matching policy threshold. Confidence intervals, arm measurements, serious-event counts, evidence IDs, and source hashes remain trial-level and source-disjoint. External PALOMA-2/3 and olokizumab executions confirm ratio and additive non-pooled paths; full states and review artifacts remain external. This is descriptive harmonization, not a meta-analysis, benefit-risk score, population comparability claim, clinical acceptability judgment, or treatment recommendation. |
| Population-stratified transport diagnostics fail closed at estimability. | `docs/47_ra_olokizumab_population_stratified_transport.md`, `docs/ra_olokizumab_population_transport_report.json`, `docs/48_ra_olokizumab_mtx_ir_same_stratum_replication.md`, `docs/ra_olokizumab_mtx_ir_replication_spec.json`, `docs/ra_olokizumab_mtx_ir_replication_report.json`, `agentic_drug_discovery/clinical_population_transport.py`, `rl_env/specs/clinical_population_transport_spec.schema.json`, `rl_env/specs/clinical_population_transport_report.schema.json`, `tests/test_clinical_benefit_risk_synthesis.py` | The first exact olokizumab replay retains distinct MTX-IR and TNFi-IR strata. The follow-on source-disjoint execution places `NCT02760407` and `NCT02760368` in one reviewed MTX-IR stratum with two-trial support, removing only the distinct-strata and no-within-stratum-replication blockers. Trial effects remain side by side with no pooling or contrast. The immutable v1 report records the then-current absence of a target population, individual-level covariates, preregistered transport model, and risk-of-bias assessment. Source, population, field, spec, and report hashes fail closed under rebinding or tampering. This is descriptive project-internal stratification, not independent review, causal transport, comparative safety, clinical acceptability, or treatment choice. |
| Outcome-specific public-source risk-of-bias judgments are source- and blocker-bound. | `docs/49_ra_olokizumab_mtx_ir_outcome_risk_of_bias.md`, `docs/ra_olokizumab_mtx_ir_risk_of_bias_spec.json`, `docs/ra_olokizumab_mtx_ir_risk_of_bias_report.json`, `agentic_drug_discovery/clinical_risk_of_bias.py`, `rl_env/specs/clinical_risk_of_bias_spec.schema.json`, `rl_env/specs/clinical_risk_of_bias_report.schema.json`, `tests/test_clinical_risk_of_bias.py` | Five ordered domains per Week-12 ACR20 outcome cite exact registry fields and registry-labeled protocol/SAP PDF hashes, pages, sections, excerpts, and dates. Source-specific flow/result arm titles, endpoint identity, selected analysis pairs, PDF page bounds, title-page dates, and cited text fail closed. STARTED counts replay against ITT analysis denominators without asserting complete observed outcomes; a standalone final pre-unblinding SAP is not verified. Both trials remain `some_concerns`, only outcome measurement is `low`, and four transport blockers remain after resolving only `risk_of_bias_not_assessed`. This is project-internal and not official RoB 2, independent adjudication, pooling, transport, comparative safety, or treatment choice. |
| Multiple immune-inflammatory diseases separate synthetic breadth from public-source execution. | `docs/41_ulcerative_colitis_conformance_slice.md`, `docs/42_uc_provider_validation.md`, `docs/43_uc_phase_population_alignment.md`, `docs/44_uc_maintenance_risk_difference_replication.md`, `docs/45_ra_acr20_risk_difference_hold_replication.md`, `docs/46_ra_olokizumab_source_disjoint_additive_tensor.md`, `docs/uc_clinical_provider_validation_snapshot.json`, `docs/uc_phase_population_validation_snapshot.json`, `docs/uc_maintenance_risk_difference_validation_snapshot.json`, `docs/ra_acr20_risk_difference_validation_snapshot.json`, `docs/ra_olokizumab_additive_tensor_validation_snapshot.json`, `tests/test_cross_disease_clinical_conformance.py`, `tests/test_clinicaltrials_gov_ingestion.py`, `tests/test_clinical_benefit_risk_synthesis.py` | The synthetic UC fixture preserves `MONDO:0005101` from contextual handoff through non-pooled synthesis. Source-pinned UC records preserve exact ratio and percentage-point intervals, arm order, treatment phase, safety aggregates, and population boundaries. Independent RA `NCT00383188` adds a null-crossing ACR20 interval and committed `HOLD`. The olokizumab pair adds two source-disjoint phase 3 ACR20 cells while retaining methotrexate- and TNF-inhibitor-inadequate-response contexts separately. Raw bytes, jobs, states, and decision packages remain external. These runs validate provider, harmonization, and workflow contracts, not pooled efficacy, population exchangeability, comparative safety, independent scientific review, or treatment choice. |
| Clinical evidence gaps and bounded actions are provenance- and budget-bound. | `docs/27_clinical_evidence_tensor_and_voi.md`, `agentic_drug_discovery/clinical_decision.py`, `rl_env/specs/clinical_evidence_decision_package.schema.json`, `tests/test_clinical_benefit_risk_synthesis.py` | A committed synthesis is replayed into exact trial cells, ordered workflow dimensions, typed provenance-linked gaps, and a deterministic action plan. Policy, tensor, catalog, scores, gap partition, and budget are integrity-bound. `ADVANCE` is evidence-workflow readiness only; gap mass and bounded VOI are uncalibrated heuristics, selected actions do not resolve evidence, and no treatment, clinical acceptability, terminal, pooling, or economic-VOI claim is made. |
| Multi-package clinical workflow behavior is cohort- and provenance-bound. | `docs/29_clinical_cohort_diagnostics.md`, `agentic_drug_discovery/clinical_cohort.py`, `rl_env/specs/clinical_evidence_cohort_manifest.schema.json`, `rl_env/specs/clinical_evidence_cohort_report.schema.json`, `tests/test_clinical_cohort.py` | Exact manifests bind package identities and can bind accepted-state hashes for committed-ledger replay. Reports distinguish packages, programs, and synthesis-bound evidence units; preserve exact denominators; compare policies only on shared evidence; and expose cross-unit source/trial reuse. The public example is synthetic and includes no outcomes or performance metrics, so correctness, utility, safety, superiority, and calibration are not estimable. |
| Clinical outcome forecasts are preregistered, cutoff-safe, and aggregate-only after evaluation. | `docs/30_preregistered_clinical_outcome_evaluation.md`, `agentic_drug_discovery/clinical_outcome_evaluation.py`, `rl_env/specs/clinical_outcome_evaluation_protocol.schema.json`, `rl_env/specs/clinical_outcome_evaluation_report.schema.json`, `tests/test_clinical_outcome_evaluation.py` | Public protocols bind the exact outcome-free cohort, deadline, outcome/harmonization definitions, curator-roster commitment, and metric policy. Frozen probabilities bind exact packages; evaluator manifests require post-deadline endpoint/safety provenance; reports retain attrition, Brier/calibration/threshold metrics, Wilson intervals, paired comparisons, and overlap counts without unit labels. Workflow decisions are not scored as outcomes. The one-unit synthetic example proves contract execution only and cannot establish calibration, utility, efficacy, safety, or policy superiority. |
| Clinical outcome uncertainty preserves declared dependence without exposing assignments. | `docs/31_cluster_robust_clinical_outcome_uncertainty.md`, `agentic_drug_discovery/clinical_outcome_uncertainty.py`, `rl_env/specs/clinical_outcome_uncertainty_protocol.schema.json`, `rl_env/specs/clinical_outcome_uncertainty_report.schema.json`, `tests/test_clinical_outcome_uncertainty.py` | A public protocol binds the exact outcome protocol, cohort report, and private dependence-manifest commitment before submissions; the evaluator later fully replays and fingerprints the base outcome report. Exact roster coverage and known shared program, baseline trial/source, and outcome trial/source links fail closed if split. Public reports retain aggregate CR1 diagnostics and additive-metric intervals overall and by fixed stage-by-endpoint strata, while assignments and cluster-level results remain external. Insufficient or dominant clusters, and cluster uncertainty that rounds to zero at reporting precision, emit no interval. The one-cluster synthetic example proves contract behavior only; computed intervals do not establish validated coverage or policy superiority. |
| Prospective clustered-board design is known-truth, bounded, and replayable. | `docs/32_prospective_clinical_outcome_design_simulation.md`, `agentic_drug_discovery/clinical_outcome_design_simulation.py`, `rl_env/specs/clinical_outcome_design_simulation_protocol.schema.json`, `rl_env/specs/clinical_outcome_design_simulation_report.schema.json`, `tests/test_clinical_outcome_design_simulation.py` | Fixed stage-by-endpoint scenarios declare cluster sizes, prevalence, ICC, MCAR evaluability, prediction patterns, candidate gates, seed, and Monte Carlo targets. A beta-binomial Polya urn provides analytic additive-metric truths, and every replicate invokes the production CR1 estimator plus an IID diagnostic reference. Aggregate reports retain Wilson-bounded coverage/yield and error/width/status diagnostics without replicate or unit records. Synthetic target passage does not select a universal gate or validate a real board. |
| Informative evaluability and residual dependence are separated by known-truth stress tests. | `docs/33_informative_evaluability_and_dependence_stress.md`, `agentic_drug_discovery/clinical_outcome_stress_simulation.py`, `rl_env/specs/clinical_outcome_stress_simulation_protocol.schema.json`, `rl_env/specs/clinical_outcome_stress_simulation_report.schema.json`, `tests/test_clinical_outcome_stress_simulation.py` | Exact synthetic dependence blocks and outcome-specific evaluability probabilities define analytic population/evaluable targets. The same estimates are evaluated under nominal and oracle dependence-closed CR1 assignments. Aggregate reports retain estimand shifts, mode diagnostics, coverage/yield/error/width/status results, and deterministic recovery signatures without unit or replicate records. Oracle closure does not discover hidden links, identify a population estimand, or perform a missing-data correction. |
| Pattern-mixture sensitivity separates evaluable calibration from population identification. | `docs/34_preregistered_pattern_mixture_sensitivity.md`, `agentic_drug_discovery/clinical_outcome_pattern_mixture.py`, `rl_env/specs/clinical_outcome_pattern_mixture_protocol.schema.json`, `rl_env/specs/clinical_outcome_pattern_mixture_report.schema.json`, `tests/test_clinical_outcome_pattern_mixture.py` | A prediction-stratified binary log-IMOR grid is fingerprint-bound to the exact stress protocol and uses observable total/evaluable/favorable counts for operational estimates. Aggregate diagnostics distinguish naive population drift, evaluable calibration, evaluator-only truth-aligned recovery, and mean-curve population identification. Sparse reference strata fail closed. Point-envelope inclusion is not sampling coverage, continuous bias/width gates do not yet carry Monte Carlo confidence bounds, latent truth does not choose the operational grid, and synthetic passage does not validate a real missingness range or board. |
| Pattern-mixture sampling uncertainty is calibrated against declared dependence structure. | `docs/35_dependence_closed_pattern_mixture_uncertainty.md`, `agentic_drug_discovery/clinical_outcome_pattern_mixture_uncertainty.py`, `rl_env/specs/clinical_outcome_pattern_mixture_uncertainty_protocol.schema.json`, `rl_env/specs/clinical_outcome_pattern_mixture_uncertainty_report.schema.json`, `tests/test_clinical_outcome_pattern_mixture_uncertainty.py` | A second protocol binds the exact stress protocol, sensitivity protocol, and point report before adding delete-one-cluster intervals at every fixed log-IMOR. Aggregate results separate grid-specific model-functional coverage from truth-aligned population recovery, retain Wilson and continuous Monte Carlo bounds, compare nominal with declared dependence-closed clusters, and fail closed for inadequate cluster structure or leave-one-out support. The public synthetic study shows nominal hidden-linkage undercoverage and all-grid recovery after oracle closure; it does not infer dependence, select a real log-IMOR range, or validate a clinical board. |
| Unequal-cluster interval behavior is calibrated without bypassing design hard stops. | `docs/36_unequal_cluster_influence_calibration.md`, `agentic_drug_discovery/clinical_outcome_pattern_mixture_influence_calibration.py`, `rl_env/specs/clinical_outcome_pattern_mixture_influence_report.schema.json`, `tests/test_clinical_outcome_pattern_mixture_influence_calibration.py` | Four exact synthetic scenarios compare delete-one normal, delete-one Student-t, unequal delete-mj Student-t, and an experimental one-step multiplier across every fixed log-IMOR and metric. The public study preserves Student-t coverage noninferiority, equal-size jackknife variance equivalence, deterministic substreams, and a dominant-cluster hard stop. It supports a narrow small-cluster candidate hierarchy but does not select a universal method, operationalize the multiplier, or validate a real dependence board. |
| Informative cluster size is treated as an estimand choice before interval calibration. | `docs/37_informative_cluster_size_estimands.md`, `agentic_drug_discovery/clinical_outcome_informative_cluster_size.py`, `rl_env/specs/clinical_outcome_informative_cluster_size_report.schema.json`, `tests/test_clinical_outcome_informative_cluster_size.py` | Five exact synthetic profiles separate unit-weighted and cluster-balanced known truths, including positive and negative direction reversals and a dominant-block hard stop. Three Student-t methods retain explicit target labels, cross-estimand bias, support yield, conditional SE calibration, and aggregate influence concentration. The fixed-profile study shows near-zero own-target bias and overconservative resampling uncertainty under informative heterogeneity, but performs no automatic estimand selection, cluster-superpopulation inference, or treatment claim. |
| Cluster-superpopulation sampling separates conditional and sampling-frame variance without changing known truths. | `docs/38_cluster_superpopulation_sampling.md`, `agentic_drug_discovery/clinical_outcome_cluster_superpopulation.py`, `rl_env/specs/clinical_outcome_cluster_superpopulation_report.schema.json`, `tests/test_clinical_outcome_cluster_superpopulation.py` | Uniform empirical-template resampling jointly samples cluster size, stratum layout, and mean risk while retaining the source cluster count. Exact report binding proves zero truth drift in all 600 cells; SE calibration moves from 280/600 to 600/600, while full calibration reaches only 520/600 because dominant-profile unit-weighted methods retain finite-cluster bias and undercoverage. Realized eligibility is aggregate-only and never filters inference. This supports one sampling-frame explanation, not external transportability, automatic method or estimand selection, operational eligibility, or a treatment claim. |
| Biohub-context presentation claims are maturity- and hash-bound. | `docs/39_biohub_translational_evidence_bridge.md`, `docs/biohub_research_readiness.json`, `rl_env/specs/biohub_research_readiness.schema.json`, `agentic_drug_discovery/research_readiness.py`, `tests/test_research_readiness.py` | The independent public-source review distinguishes implemented, synthetic-validated, and proposed capabilities; verifies official-source references and 31 local artifact hashes; freezes five pilot gates; and prohibits affiliation, virtual-cell, therapeutic-design, clinical-calibration, disease-breadth, and transportability overclaims. It contains no Biohub data, endorsement, completed pilot, or external validation result. |
| Upstream perturbation observations remain contextual at the translational handoff. | `docs/40_upstream_translational_handoff.md`, `agentic_drug_discovery/translational_handoff.py`, `rl_env/specs/translational_handoff.schema.json`, `rl_env/specs/translational_handoff.example.json`, `tests/test_translational_handoff.py` | The generic M6 contract binds program, perturbation, biological context, source lineage, assay, endpoint, effect interval, sampling, QC, review, and immutable non-claims. The compiler emits `contextualizes` evidence only. The public fixture is synthetic and does not verify source truth, establish mechanism or efficacy, or integrate a Biohub platform. |
| Clinical evidence actions close the loop only through committed source rejoin. | `docs/28_clinical_evidence_closed_loop.md`, `agentic_drug_discovery/clinical_closed_loop.py`, `rl_env/specs/clinical_evidence_closed_loop_transition.schema.json`, `tests/test_clinical_benefit_risk_synthesis.py` | Selected actions compile into exact state-bound calls and compact payload-free receipts. Reviewer-only verifier runs append refreshed mappings and syntheses. An attempted action is consumed, and a gap can resolve only when a successful targeted receipt promotes evidence whose exact source hash enters the after tensor. The public control is synthetic; it proves execution, provenance, budget, and replay invariants, not provider truth, action efficacy, clinical utility, calibrated VOI, or a treatment decision. |
| Multi-trial portfolio ingestion and endpoint mapping are exact-set and replay-bound. | `docs/23_clinical_portfolio_endpoint_mapping.md`, `docs/retrospective_policy_evaluation_snapshot.json`, `agentic_drug_discovery/clinical_portfolio.py`, `agentic_drug_discovery/clinical_endpoint_mapping.py`, `rl_env/specs/clinicaltrials_gov_portfolio_job.schema.json`, `rl_env/specs/clinical_endpoint_mapping.schema.json`, `tests/test_clinical_portfolio.py` | Every declared single-trial job and external bundle must verify before payload-free output. A reviewer-approved mapping retains exact endpoint/safety fingerprints and source hashes, and synthesis must reference it. A real external PALOMA exact set executed under this contract, while the public package retains only aggregate outcomes and hashes; the portfolio review, authority payloads, full state, and per-episode artifacts are not release-approved. |
| Planning is bounded before required calls spend budget. | `agentic_drug_discovery/planning.py`, `tests/test_agent_loop.py` | Preflight covers state/version, stage, contracts, chronology, duplicate requests, steps, and declared cost. It does not prove that a chosen tool plan is scientifically optimal. |
| Policy replanning and resume preserve deterministic boundaries. | `docs/24_policy_replanning_and_resume.md`, `agentic_drug_discovery/policy.py`, `rl_env/specs/policy_checkpoint.schema.json`, `tests/test_policy_replanning.py` | Only predeclared typed replacement plans can follow a paused or blocked observation. Rule/global limits, queue identity, policy identity, observation hashes, checkpoint hashes, state/ledger chains, and stale resume tokens fail closed. Real senicapoc and PALOMA runs exercised this layer, but their checkpoints remain external. This proves control-flow continuity, not plan optimality or scientific validity. |
| Selected tool operations have explicit semantic mappings. | `agentic_drug_discovery/promotion.py`, `tests/test_semantic_mappings.py` | The mappings validate known payload shapes and conservative interpretation rules; they do not prove payload truth, external database completeness, or cross-disease validity. |
| Bounded multi-stage execution reaches every verifier-gated stage. | `agentic_drug_discovery/orchestration.py`, `agentic_drug_discovery/program.py`, `tests/test_program_runner.py`, `tests/test_adapter_bindings.py`, `tests/test_pinned_evidence_adapter.py` | Ordered stage runs share one cumulative ledger and continue only after accepted advance decisions. One five-stage fixture intentionally defers on activity-count context; one synthetic provider-backed fixture preserves disease, target, candidate, preclinical, trial-design, and intervention identities through all eight stages and replays exactly. This is control-path completeness, not autonomous discovery or a performance result. |
| Evaluation requires matched success and failure arms. | `agentic_drug_discovery/matched_evaluation.py`, `tests/test_matched_evaluation.py`, `tests/test_target_identity_continuity.py`, `tests/test_pinned_evidence_adapter.py`, `tests/test_pinned_evidence_ingestion.py`, `tests/test_cdc_mmwr_ingestion.py`, `tests/test_ncbi_pubmed_ingestion.py`, `tests/test_preclinical_provider_pair.py`, `tests/test_clinicaltrials_gov_ingestion.py`, `tests/test_semantic_mappings.py` | The schema enforces cutoff and context matching. Target-symbol, assay-target-link, compiled source independence, CDC same-document reuse, PubMed cross-population context, preclinical publication-lineage reuse, and ClinicalTrials.gov condition/source-identity pairs each isolate a bounded failure, but this package does not publish a real matched episode corpus or claim measured discovery performance. |
| A Hugging Face mirror is reproducible from an exact Git commit. | `scripts/audit/build_hf_release_package.py`, `scripts/audit/validate_hf_release_package.py`, `upload_manifest.json` on the Hub | The builder reads Git commit objects, and the validator checks the exact file set, source tree, sizes, and SHA-256 values. The public 0.3.0.dev2 Hub snapshot was downloaded again and validated after upload; the 0.3.0.dev3 candidate remains unuploaded. |
| The scorer is separate from its row dataset. | `benchmark/`, `huggingface/release_manifest.json` | `ctdbench` targets `jang1563/clinical-trial-decision-benchmark`; its rows and Croissant metadata are not copied into this artifact mirror. |
| The public surface is checked before release changes. | `.github/workflows/release-audit.yml`, `scripts/audit/` | Passing checks reduce release-boundary risk but do not certify scientific correctness. |

## Required Human Read Order

1. `README.md`
2. `docs/release_trust_report.md`
3. `docs/12_scd_vertical_slice.md`
4. `docs/13_target_id_governance_node.md`
5. `docs/14_target_identity_continuity.md`
6. `docs/15_discovery_context_identity.md`
7. `docs/16_clinical_intervention_identity.md`
8. `docs/17_pinned_source_ingestion.md`
9. `docs/18_cdc_mmwr_ingestion.md`
10. `docs/19_ncbi_pubmed_ingestion.md`
11. `docs/20_preclinical_provider_ingestion.md`
12. `docs/preclinical_provider_validation_snapshot.json`
13. `docs/21_clinical_provider_ingestion.md`
14. `docs/clinical_provider_validation_snapshot.json`
15. `docs/public_evidence_summary.json`
16. `docs/release_boundary.md`
17. `release_manifest.json`
18. `release_decision_packet.json`
19. `huggingface/README.md`
20. `huggingface/release_manifest.json`
21. `agentic_drug_discovery/models.py`
22. `agentic_drug_discovery/planning.py`
23. `agentic_drug_discovery/execution.py`
24. `agentic_drug_discovery/promotion.py`
25. `agentic_drug_discovery/pinned_evidence.py`
26. `agentic_drug_discovery/ingestion.py`
27. `agentic_drug_discovery/cdc_mmwr.py`
28. `agentic_drug_discovery/ncbi_pubmed.py`
29. `agentic_drug_discovery/chembl_activity.py`
30. `agentic_drug_discovery/clinicaltrials_gov.py`
31. `agentic_drug_discovery/ingestion_cli.py`
32. `adapters/pinned_evidence_adapter.py`
33. `rl_env/specs/pinned_evidence_manifest.schema.json`
34. `rl_env/specs/source_receipt.schema.json`
35. `rl_env/specs/pinned_evidence_ingestion_job.schema.json`
36. `rl_env/specs/cdc_mmwr_ingestion_job.schema.json`
37. `rl_env/specs/ncbi_pubmed_ingestion_job.schema.json`
38. `rl_env/specs/chembl_activity_ingestion_job.schema.json`
39. `rl_env/specs/ncbi_pubmed_disease_model_ingestion_job.schema.json`
40. `rl_env/specs/clinicaltrials_gov_ingestion_job.schema.json`
41. `rl_env/specs/pinned_evidence_ingestion_review.schema.json`
42. `rl_env/specs/target_identity_record.schema.json`
43. `rl_env/specs/discovery_context_identity.schema.json`
44. `rl_env/specs/clinical_intervention_identity.schema.json`
45. `agentic_drug_discovery/orchestration.py`
46. `agentic_drug_discovery/program.py`
47. `agentic_drug_discovery/environment.py`
48. `agentic_drug_discovery/serialization.py`
49. `agentic_drug_discovery/matched_evaluation.py`
50. `tests/test_pinned_evidence_adapter.py`
51. `tests/test_pinned_evidence_ingestion.py`
52. `tests/test_cdc_mmwr_ingestion.py`
53. `tests/test_ncbi_pubmed_ingestion.py`
54. `tests/test_chembl_activity_ingestion.py`
55. `tests/test_ncbi_pubmed_disease_model_ingestion.py`
56. `tests/test_preclinical_provider_pair.py`
57. `tests/test_clinicaltrials_gov_ingestion.py`
58. `tests/test_target_identity_continuity.py`
59. `tests/test_context_identity_continuity.py`
60. `tests/test_clinical_identity_continuity.py`
61. `tests/test_agent_loop.py`
62. `tests/test_program_runner.py`
63. `tests/test_semantic_mappings.py`
64. `tests/test_matched_evaluation.py`
65. `benchmark/README.md`
66. `docs/22_clinical_benefit_risk_synthesis.md`
67. `agentic_drug_discovery/clinical_synthesis.py`
68. `adapters/clinical_synthesis_adapter.py`
69. `rl_env/specs/clinical_benefit_risk_synthesis.schema.json`
70. `tests/test_clinical_benefit_risk_synthesis.py`
71. `docs/23_clinical_portfolio_endpoint_mapping.md`
72. `agentic_drug_discovery/clinical_portfolio.py`
73. `agentic_drug_discovery/clinical_endpoint_mapping.py`
74. `rl_env/specs/clinicaltrials_gov_portfolio_job.schema.json`
75. `rl_env/specs/clinical_endpoint_mapping.schema.json`
76. `tests/test_clinical_portfolio.py`
77. `docs/24_policy_replanning_and_resume.md`
78. `agentic_drug_discovery/policy.py`
79. `rl_env/specs/policy_checkpoint.schema.json`
80. `tests/test_policy_replanning.py`
81. `docs/25_cutoff_safe_policy_evaluation.md`
82. `docs/retrospective_policy_evaluation_snapshot.json`
83. `agentic_drug_discovery/sealed_evaluation.py`
84. `rl_env/specs/sealed_evaluation_board.schema.json`
85. `rl_env/specs/sealed_evaluation_vault.schema.json`
86. `rl_env/specs/policy_evaluation_submission.schema.json`
87. `rl_env/specs/policy_evaluation_report.schema.json`
88. `tests/test_sealed_evaluation.py`
89. `docs/27_clinical_evidence_tensor_and_voi.md`
90. `agentic_drug_discovery/clinical_decision.py`
91. `docs/28_clinical_evidence_closed_loop.md`
92. `agentic_drug_discovery/clinical_closed_loop.py`
93. `docs/29_clinical_cohort_diagnostics.md`
94. `agentic_drug_discovery/clinical_cohort.py`
95. `tests/test_clinical_cohort.py`
96. `docs/30_preregistered_clinical_outcome_evaluation.md`
97. `agentic_drug_discovery/clinical_outcome_evaluation.py`
98. `tests/test_clinical_outcome_evaluation.py`
99. `docs/31_cluster_robust_clinical_outcome_uncertainty.md`
100. `agentic_drug_discovery/clinical_outcome_uncertainty.py`
101. `tests/test_clinical_outcome_uncertainty.py`
102. `docs/32_prospective_clinical_outcome_design_simulation.md`
103. `agentic_drug_discovery/clinical_outcome_design_simulation.py`
104. `tests/test_clinical_outcome_design_simulation.py`
105. `docs/33_informative_evaluability_and_dependence_stress.md`
106. `agentic_drug_discovery/clinical_outcome_stress_simulation.py`
107. `tests/test_clinical_outcome_stress_simulation.py`
108. `docs/34_preregistered_pattern_mixture_sensitivity.md`
109. `agentic_drug_discovery/clinical_outcome_pattern_mixture.py`
110. `tests/test_clinical_outcome_pattern_mixture.py`
111. `docs/35_dependence_closed_pattern_mixture_uncertainty.md`
112. `agentic_drug_discovery/clinical_outcome_pattern_mixture_uncertainty.py`
113. `tests/test_clinical_outcome_pattern_mixture_uncertainty.py`
114. `docs/42_uc_provider_validation.md`
115. `docs/uc_clinical_provider_validation_snapshot.json`

## Machine Anchors

| Path | Role |
| --- | --- |
| `release_manifest.json` | Canonical GitHub and Hugging Face release scope. |
| `release_decision_packet.json` | Public launch status, approval gate, and hard stops. |
| `huggingface/release_manifest.json` | Hugging Face package include/exclude list. |
| `docs/public_evidence_summary.json` | Aggregate-only scientific claim ledger and limitation flags. |
| `docs/preclinical_provider_validation_snapshot.json` | Payload-free external provider ids, typed values, hashes, matched outcomes, and exact-replay limitations. |
| `docs/clinical_provider_validation_snapshot.json` | Payload-free NCT/design identities, typed aggregate values, artifact hashes, stage outcome, matched control, and exact-replay limitations. |
| `docs/uc_clinical_provider_validation_snapshot.json` | Payload-free UC induction source/job/output/manifest hashes, typed selected values, direction-aware decisions, and exact-replay limitations. |
| `docs/uc_maintenance_risk_difference_validation_snapshot.json` | Payload-free independent maintenance source/output hashes, percentage-point effect, role-wise safety/population alignment, execution result, screened exclusions, and exact-replay limitations. |
| `docs/46_ra_olokizumab_source_disjoint_additive_tensor.md` | Human-readable same-candidate RA selection, source-scale, non-pooling, population, decision, and interpretation contract. |
| `docs/ra_olokizumab_additive_tensor_validation_snapshot.json` | Payload-free two-source ACR20 and serious-event aggregates, artifact hashes, normalized additive precision, HOLD result, and negative claims. |
| `docs/47_ra_olokizumab_population_stratified_transport.md` | Human-readable prior-therapy stratum contract, exact replay result, estimability blockers, and interpretation boundary. |
| `docs/ra_olokizumab_population_transport_report.json` | Integrity-bound population/source hashes, trial cells, support counts, transport blockers, and prohibited-inference flags. |
| `docs/48_ra_olokizumab_mtx_ir_same_stratum_replication.md` | Human-readable independent MTX-IR replication, source-date precision, blocker delta, HOLD result, and interpretation boundary. |
| `docs/ra_olokizumab_mtx_ir_replication_spec.json` | Exact reviewed MTX-IR stratum bindings and source-field fingerprints. |
| `docs/ra_olokizumab_mtx_ir_replication_report.json` | Integrity-bound two-trial support, source effects, safety aggregates, remaining blockers, and prohibited-inference flags. |
| `docs/49_ra_olokizumab_mtx_ir_outcome_risk_of_bias.md` | Human-readable domain judgments, denominator and chronology diagnostics, exact source hashes, blocker delta, and interpretation boundary. |
| `docs/ra_olokizumab_mtx_ir_risk_of_bias_spec.json` | Reviewed trial, arm, domain, registry-field, and protocol/SAP page bindings. |
| `docs/ra_olokizumab_mtx_ir_risk_of_bias_report.json` | Integrity-bound source diagnostics, trial judgments, assessment cautions, and remaining transport blockers. |
| `docs/retrospective_policy_evaluation_snapshot.json` | Aggregate real matched-board policy metrics, payload-free hashes, real gate outcomes, and explicit limitations. |
| `agentic_drug_discovery/models.py` | Immutable, JSON-serializable evidence, claim, disease, target, candidate, assay, model-system, intervention, trial, arm, population, endpoint, safety, safety-arm, atomic design, endpoint binding/mapping, study benefit-risk, synthesis, accepted-packet, action, decision, verifier, and state records. |
| `agentic_drug_discovery/planning.py` | Declarative stage plans and fail-closed bounded request compilation. |
| `agentic_drug_discovery/environment.py` | Fail-closed transition engine and stage-gate composition. |
| `agentic_drug_discovery/execution.py` | Tool contracts, state-bound requests, structured outcomes, execution ledger, and explicit evidence promotion. |
| `agentic_drug_discovery/promotion.py` | Operation-specific payload validation and conservative evidence, claim, disease, target, candidate, assay, model-system, intervention, trial, atomic design, clinical synthesis, and decision mapping. |
| `agentic_drug_discovery/orchestration.py` | Planner-to-transition stage runner, attempt journal, conservative decision aggregation, and accepted defer recovery. |
| `agentic_drug_discovery/program.py` | Multi-stage program steps, cumulative-ledger and state-chain invariants, explicit stop statuses, and exact run replay. |
| `agentic_drug_discovery/policy.py` | Typed non-advance observations, deterministic bounded replan rules, queue mutation records, hash-bound checkpoints, and resume orchestration. |
| `agentic_drug_discovery/serialization.py` | Strict record ingestion, tool-ledger link validation, and deterministic replay bundles. |
| `agentic_drug_discovery/matched_evaluation.py` | Exact-context success/failure episode contracts and matched evaluation summaries. |
| `agentic_drug_discovery/sealed_evaluation.py` | Role-neutral boards, cached packet hashes, salted label commitments, fingerprint-bound submissions, strict envelope readers, and aggregate policy metrics. |
| `agentic_drug_discovery/pinned_evidence.py` | Shared strict normalization for direct and compiled payload-free evidence manifests. |
| `agentic_drug_discovery/ingestion.py` | Immutable source receipts/bundles, HTTPS and local capture, payload verification, manifest compilation, and review reports. |
| `agentic_drug_discovery/cdc_mmwr.py` | Provider-specific article, section, value, unit, geography, reference-period, and excerpt-hash verification. |
| `agentic_drug_discovery/ncbi_pubmed.py` | Provider-specific EFetch request, direct article identity, structured abstract, typed treatment-gap, context-anchor, and excerpt-hash verification. |
| `agentic_drug_discovery/chembl_activity.py` | Provider-specific ChEMBL release/resource identity, functional endpoint, candidate alias, target component, lineage, and assay-text-hash verification. |
| `agentic_drug_discovery/clinicaltrials_gov.py` | Provider-specific registry receipt, NCT/version, arm/result/adverse-event group, population, endpoint, analysis, and serious-adverse-event verification with source-payload removal. |
| `agentic_drug_discovery/clinical_effects.py` | Canonical hazard-, odds-, risk-ratio, and percentage-point risk-difference aliases, null values, measure/unit/direction contracts, and interval-level benefit classification shared by ingestion, promotion, mapping, synthesis, and bounded decision validation. |
| `agentic_drug_discovery/clinical_portfolio.py` | Exact-set multi-job/bundle preflight and payload-free portfolio extraction. |
| `agentic_drug_discovery/clinical_endpoint_mapping.py` | Approved reviewer/ontology declaration parsing, exact endpoint/safety fingerprint binding, and replay validation. |
| `agentic_drug_discovery/clinical_synthesis.py` | Mapping-gated selection parsing, source-disjoint trial recompilation, trial-level effect/safety records, and non-pooling invariants. |
| `agentic_drug_discovery/clinical_decision.py` | Exact evidence tensor, typed gap, bounded-VOI action plan, integrity reader, and committed-state recompilation contracts. |
| `agentic_drug_discovery/clinical_cohort.py` | Exact package/state rosters, evidence-unit identity, deterministic package/policy strata, matched policy sensitivity, provenance-overlap reporting, strict readers, and report replay. |
| `agentic_drug_discovery/clinical_outcome_evaluation.py` | Preregistered cohort/cutoff commitments, exact package-bound probability submissions, post-deadline endpoint/safety provenance, aggregate calibration and threshold metrics, paired policy comparison, strict readers, and full private-input replay. |
| `agentic_drug_discovery/clinical_outcome_uncertainty.py` | Frozen dependence commitments, exact assignment coverage, known-overlap closure, CR1 policy/stratum/paired intervals, fail-closed diagnostics, strict readers, and full private-input replay. |
| `agentic_drug_discovery/clinical_outcome_design_simulation.py` | Bounded beta-binomial scenario generation, analytic truths, production CR1 parity, IID diagnostics, Monte Carlo gate evaluation, strict readers, and exact replay. |
| `agentic_drug_discovery/clinical_outcome_informative_cluster_size.py` | Profile-bound unit-weighted and cluster-balanced pattern-mixture truths, three Student-t estimators, conditional calibration, aggregate influence concentration, strict readers, and exact replay. |
| `agentic_drug_discovery/clinical_outcome_cluster_superpopulation.py` | Empirical-template cluster resampling, preserved superpopulation truths, conditional comparison cells, realized-design rates, dynamic largest-cluster influence, strict readers, and exact replay. |
| `agentic_drug_discovery/clinical_closed_loop.py` | State-bound execution batches, compact provider/reviewer receipts, source-rejoined before/after transition compilation, and two-state validation. |
| `agentic_drug_discovery/ingestion_cli.py` | Machine-readable `capture`, disease-context, preclinical, clinical extraction, and `compile` commands for the external source path. |
| `agentic_drug_discovery/bounded_demo.py` | Dependency-free planner-to-transition fixture with machine-readable output. |
| `adapters/execution_registry.py` | Conservative typed bindings for explicitly supplied adapter instances; selected dependency-free bindings are mirrored to Hugging Face. |
| `adapters/pinned_evidence_adapter.py` | Payload-free manifest validation and exact disease/functional profile lookup. |
| `adapters/clinical_synthesis_adapter.py` | Local strict normalization of reviewed endpoint mappings and synthesis selections without source measurements. |
| `rl_env/specs/pinned_evidence_manifest.schema.json` | Machine schema for pinned records, dates, hashes, contexts, and typed summaries. |
| `rl_env/specs/pinned_evidence_manifest.example.json` | Synthetic contract example with no scientific claims. |
| `rl_env/specs/source_receipt.schema.json` | Machine schema for exact source version, locator, hash, byte size, retrieval time, and transport. |
| `rl_env/specs/source_receipt.example.json` | Synthetic payload-free source receipt. |
| `rl_env/specs/pinned_evidence_ingestion_job.schema.json` | Machine schema for reviewer-authored evidence summaries linked to receipt ids. |
| `rl_env/specs/pinned_evidence_ingestion_job.example.json` | Synthetic disease-context compilation job with no scientific claim. |
| `rl_env/specs/cdc_mmwr_ingestion_job.schema.json` | Machine schema for a reviewer-selected CDC MMWR article, context, value, unit, and evidence location. |
| `rl_env/specs/cdc_mmwr_ingestion_job.example.json` | Synthetic CDC MMWR burden job with no scientific claim. |
| `rl_env/specs/ncbi_pubmed_ingestion_job.schema.json` | Machine schema for a reviewer-selected PubMed article, structured abstract evidence, typed treatment gap, and context anchors. |
| `rl_env/specs/ncbi_pubmed_ingestion_job.example.json` | Synthetic PubMed treatment-gap job with no scientific claim. |
| `rl_env/specs/chembl_activity_ingestion_job.schema.json` | Machine schema for linked ChEMBL release resources, functional-readout evidence, typed endpoint, candidate aliases, target component, and publication lineage. |
| `rl_env/specs/chembl_activity_ingestion_job.example.json` | Synthetic ChEMBL functional-activity job with no scientific claim. |
| `rl_env/specs/ncbi_pubmed_disease_model_ingestion_job.schema.json` | Machine schema for PubMed article identity, candidate/model anchors, exposure regimen, typed endpoint, variation, p-value, and lineage. |
| `rl_env/specs/ncbi_pubmed_disease_model_ingestion_job.example.json` | Synthetic PubMed disease-model job with no scientific claim. |
| `rl_env/specs/clinical_benefit_risk_synthesis.schema.json` | Machine schema for reviewed source-ledger trial/design/endpoint/safety selections. |
| `rl_env/specs/clinical_benefit_risk_synthesis.example.json` | Synthetic two-trial selection example with no clinical judgment. |
| `rl_env/specs/clinical_evidence_decision_package.schema.json` | Machine schema for exact clinical evidence cells, typed gaps, bounded actions, budget accounting, and integrity binding. |
| `rl_env/specs/clinical_evidence_decision_package.example.json` | Compiler-generated synthetic HOLD package with no treatment or acceptability judgment. |
| `rl_env/specs/clinical_evidence_decision_package.relaxed.example.json` | Compiler-generated synthetic ADVANCE package over the same evidence unit for matched policy sensitivity; no clinical outcome is implied. |
| `rl_env/specs/clinical_evidence_cohort_manifest.schema.json` | Machine schema for exact package identities and optional accepted-state SHA-256 bindings. |
| `rl_env/specs/clinical_evidence_cohort_manifest.example.json` | Compiler-generated synthetic two-policy roster with no real program artifacts. |
| `rl_env/specs/clinical_evidence_cohort_report.schema.json` | Machine schema for package/policy diagnostics, matched transitions, actions, gaps, provenance overlap, and calibration status. |
| `rl_env/specs/clinical_evidence_cohort_report.example.json` | Compiler-generated synthetic HOLD-to-ADVANCE policy sensitivity report without outcomes or performance metrics. |
| `rl_env/specs/clinical_evidence_cohort_summary.schema.json` | Machine schema for compact cohort summaries and optional validation status. |
| `rl_env/specs/clinical_outcome_dependence_manifest.schema.json` | Evaluator-only machine schema for exact unit-to-cluster assignments and dependence-basis commitments. |
| `rl_env/specs/clinical_outcome_dependence_manifest.example.json` | Synthetic one-cluster dependence assignment used only to prove contract behavior. |
| `rl_env/specs/clinical_outcome_uncertainty_protocol.schema.json` | Public machine schema for dependence construction, confidence, cluster floor, dominance, strata, and metric commitments. |
| `rl_env/specs/clinical_outcome_uncertainty_protocol.example.json` | Synthetic frozen uncertainty protocol bound to the public outcome artifacts. |
| `rl_env/specs/clinical_outcome_uncertainty_report.schema.json` | Public machine schema for aggregate cluster diagnostics and CR1 policy, stratum, and paired intervals. |
| `rl_env/specs/clinical_outcome_uncertainty_report.example.json` | Synthetic one-cluster report with explicit no-interval states. |
| `rl_env/specs/clinical_outcome_uncertainty_summary.schema.json` | Machine schema for compact uncertainty and replay-validation status. |
| `rl_env/specs/clinical_outcome_design_simulation_protocol.schema.json` | Public machine schema for seeded cluster-size, prevalence, ICC, evaluability, prediction-pattern, gate, and Monte Carlo commitments. |
| `rl_env/specs/clinical_outcome_design_simulation_report.schema.json` | Public machine schema for aggregate known-truth IID/CR1 performance, replicate diagnostics, gate statuses, and claim boundaries. |
| `rl_env/specs/clinical_outcome_design_simulation_summary.schema.json` | Machine schema for compact scenario/gate coverage, yield, width, error, status, and replay validation. |
| `rl_env/specs/clinical_evidence_closed_loop_transition.schema.json` | Machine schema for selected-action execution, compact receipts, reviewer refresh, exact source rejoin, and nested before/after packages. |
| `rl_env/specs/clinical_evidence_closed_loop_transition.example.json` | Compiler-generated synthetic HOLD-to-ADVANCE evidence-workflow transition. |
| `rl_env/specs/clinical_endpoint_mapping.schema.json` | Machine schema for reviewer approval, ontology identity, and exact ordered endpoint/safety bindings. |
| `rl_env/specs/clinical_endpoint_mapping.example.json` | Synthetic approved mapping example; ontology authority is not implied. |
| `rl_env/specs/clinicaltrials_gov_portfolio_job.schema.json` | Machine schema for the exact set of single-trial jobs, receipts, and mapping bindings. |
| `rl_env/specs/clinicaltrials_gov_portfolio_job.example.json` | Synthetic two-trial portfolio references with no source bytes or local paths. |
| `rl_env/specs/policy_checkpoint.schema.json` | Machine schema for checkpoint envelopes, pending typed steps, observations, directives, queue histories, and SHA-256 identity. |
| `rl_env/specs/sealed_evaluation_board.schema.json` | Machine schema for cutoff-safe role-neutral observations and embedded sanitized cached packets. |
| `rl_env/specs/sealed_evaluation_vault.schema.json` | Evaluator schema for arm, gold decision, failure cause, metadata, and commitment nonce. |
| `rl_env/specs/policy_evaluation_submission.schema.json` | Machine schema for complete board- and observation-fingerprint-bound predictions. |
| `rl_env/specs/policy_evaluation_report.schema.json` | Machine schema for aggregate exact, arm, pair, unsafe-advance, and confidence diagnostics. |
| `rl_env/specs/pinned_evidence_ingestion_review.schema.json` | Machine schema for compiler checks, source reuse warnings, manifest hash, and mandatory review status. |
| `rl_env/specs/target_identity_record.schema.json` | Machine schema for canonical identity, namespace bindings, stage, and supporting evidence. |
| `rl_env/specs/target_identity_record.example.json` | Synthetic complete target binding with no scientific claim. |
| `rl_env/specs/discovery_context_identity.schema.json` | Machine schema for canonical disease, assay, and model-system identities and evidence links. |
| `rl_env/specs/discovery_context_identity.example.json` | Synthetic complete discovery-context identity graph with no scientific claim. |
| `rl_env/specs/clinical_intervention_identity.schema.json` | Machine schema for candidate-linked intervention, trial, and atomic arm/population/endpoint design identities. |
| `rl_env/specs/clinical_intervention_identity.example.json` | Synthetic complete clinical identity graph with no scientific claim. |
| `rl_env/specs/clinicaltrials_gov_ingestion_job.schema.json` | Machine schema for exact registry identity, selected arms, population, posted endpoint, measurements, and statistical analysis. |
| `rl_env/specs/clinicaltrials_gov_ingestion_job.example.json` | Synthetic reviewed ClinicalTrials.gov endpoint/safety design job with no scientific claim. |
| `adapters/opentargets_adapter.py` | GitHub-only disease profile and Ensembl-resolved target-association retrieval with explicit unavailable and disease-mismatch states. |
| `adapters/chembl_adapter.py` | GitHub-only molecule, mechanism, normalized target profile, and target activity retrieval used by the composite typed bindings. |
| `tests/test_execution.py` | Dependency-free tool failure, unavailable-state, tamper, and replay regression coverage included in the Hugging Face package. |
| `tests/test_adapter_bindings.py` | GitHub-only coverage for existing adapter instances bound through the typed execution registry. |
| `tests/test_environment.py` | Deterministic regression coverage for allowed and blocked transitions. |
| `tests/test_agent_loop.py` | Planning, required-call failure, budget, chronology, soft-only evidence, accepted recovery, and replay coverage. |
| `tests/test_program_runner.py` | Multi-stage state/ledger chaining, plan exhaustion, blocked-stage stopping, and exact replay coverage. |
| `tests/test_semantic_mappings.py` | Open Targets, ChEMBL, RDKit, ClinicalTrials.gov, EMA, and Boltz semantic interpretation coverage. |
| `tests/test_matched_evaluation.py` | Matched-pair, cutoff, leakage, missing-prediction, and empty-evaluation coverage. |
| `tests/test_sealed_evaluation.py` | Sealing determinism, label separation, cached-packet cutoff/hash checks, commitment tamper, strict JSON round-trip, stale submission, baseline scoring, and schema coverage. |
| `tests/test_pinned_evidence_adapter.py` | Composite-gate success, same-source failure, cutoff, unavailable, eight-stage provider-backed replay, and matched-pair coverage. |
| `tests/test_pinned_evidence_ingestion.py` | Receipt/job parsing, source tamper and boundary attacks, compilation, CLI capture, and matched stage integration. |
| `tests/test_cdc_mmwr_ingestion.py` | Provider identity/location/value/unit attacks, excerpt removal, bounded stage integration, and matched same-document failure. |
| `tests/test_ncbi_pubmed_ingestion.py` | PubMed identity/request/XML/retraction/value/anchor attacks, excerpt removal, bounded stage integration, and matched cross-population failure. |
| `tests/test_chembl_activity_ingestion.py` | ChEMBL release/resource identity, endpoint, target, alias, lineage, text-removal, compiler, and CLI-hash coverage. |
| `tests/test_ncbi_pubmed_disease_model_ingestion.py` | PubMed article, exposure, endpoint, model/candidate anchor, retraction, text-removal, and CLI-hash coverage. |
| `tests/test_preclinical_provider_pair.py` | End-to-end sanitized-provider advance and controlled shared-lineage defer coverage with typed ledger checks. |
| `tests/test_clinicaltrials_gov_ingestion.py` | Exact registry extraction, payload removal, atomic endpoint/safety promotion, role/support continuity attacks, snapshot consistency, and matched missing-safety coverage. |
| `tests/test_cross_disease_clinical_conformance.py` | Synthetic ulcerative-colitis identity continuity, odds-ratio favorable-direction, contextual-only handoff, schema round-trip, and direction-reversal coverage. |
| `tests/test_target_identity_continuity.py` | Namespace rebinding/collision, candidate-link, and matched target-symbol continuity coverage. |
| `tests/test_context_identity_continuity.py` | Disease/model rebinding, assay namespace collision, unknown-candidate evidence, and strict schema-example coverage. |
| `tests/test_clinical_identity_continuity.py` | Intervention rebinding, trial namespace collision, unknown-intervention linkage, support removal, and strict schema-example coverage. |
| `tests/test_clinical_outcome_uncertainty.py` | CR1 and paired-covariance math, fixed strata, chronology, exact coverage, known-overlap closure, non-estimable states, privacy, strict readers, and atomic CLI coverage. |
| `tests/test_clinical_outcome_design_simulation.py` | Analytic truths, seeded replay, ICC undercoverage stress, floor/dominance/attrition states, workload bounds, privacy, schemas, and atomic simulation CLI coverage. |
| `tests/test_clinical_outcome_pattern_mixture.py` | Binary log-IMOR recovery, excluded-grid controls, MCAR alignment, sparse-stratum failure, exact binding/replay, privacy, schemas, and atomic CLI coverage. |
| `tests/test_clinical_outcome_pattern_mixture_uncertainty.py` | All-grid jackknife calibration, hidden-linkage repair, independent-mode equivalence, model-functional/population separation, Monte Carlo bounds, fail-closed states, exact replay, privacy, schemas, and CLI coverage. |
| `tests/test_clinical_outcome_informative_cluster_size.py` | Null estimand equivalence, positive/negative direction drift, delete-mj target preservation, dominant-block hard stop, aggregate influence, strict readers, public schemas, exact replay, privacy, and CLI coverage. |
| `tests/test_clinical_outcome_cluster_superpopulation.py` | Known-truth preservation, conditional comparison, dynamic tie denominators, no post-hoc dominance filtering, exact binding/replay, strict readers, public schemas, privacy, and CLI coverage. |
| `scripts/audit/github_release_file_audit.py` | Fail-closed scan for required files, forbidden paths, large files, secrets, and machine-local breadcrumbs. |
| `scripts/audit/validate_hf_release_package.py` | Dataset-card/manifest validation plus exact built-package file, hash, source-commit, and source-tree checks. |
| `scripts/audit/validate_public_launch_packet.py` | Launch packet and public-state metadata validation. |
| `scripts/audit/validate_vertical_slice_doc.py` | Caveat and pointer validation for the SCD vertical slice. |
| `scripts/audit/build_hf_release_package.py` | Deterministic local build of the Hugging Face mirror package. |
| `scripts/audit/smoke_test_core_wheel.py` | Isolated wheel installation plus demo, replay, generic ingestion, disease-context, preclinical, and ClinicalTrials.gov extraction CLI validation outside the source tree. |

## Reproducible HF Package Build

Build a local Hugging Face package without uploading:

```bash
python3 scripts/audit/build_hf_release_package.py --output /tmp/agentic-hf-release-package --force
python3 scripts/audit/validate_hf_release_package.py --package /tmp/agentic-hf-release-package
```

The generated `upload_manifest.json` records:

- artifact name,
- repo id and repo type,
- visibility target,
- source GitHub repository,
- source commit,
- source tree,
- source commit timestamp,
- exact uploaded file list,
- per-file SHA-256 and byte size (excluding the self-referential manifest file).

The public 0.3.0.dev2 Hub package is a deliberate subset of GitHub. Live adapters, legacy chains,
evaluator-directory scaffolds, contributor/security files, and GitHub automation remain
GitHub-only. The Hub subset contains the dependency-free pinned-evidence adapter and binding,
bounded planner, semantic mappings, stage and program runners, matched and sealed evaluators, typed execution
core, source capture/compiler code, target, discovery-context, clinical-intervention, and ingestion
schemas, ChEMBL functional-activity and PubMed disease-model extractors, tests, documentation,
ClinicalTrials.gov endpoint/safety trial-design extractor, dependence-aware clinical outcome
uncertainty protocols and aggregate synthetic reports, aggregate evidence, audit code, and the `benchmark/`
scorer. Raw
source bundles, real provider review jobs, and ingestion runs are not included.

## Interpretation Warnings

- This is a typed control-plane, protocol, and benchmark-control artifact, not a model release.
- The executable fixture validates orchestration semantics; it is not evidence of scientific efficacy or autonomous discovery performance.
- Fixed semantic mappings validate known payload structures and conservative policy rules; they do not establish that a database record or SFM prediction is scientifically true.
- Open Targets disease identity does not establish unmet need, and ChEMBL target activity volume does not establish candidate functional effect.
- Runtime Open Targets, ChEMBL, legacy ClinicalTrials.gov search, EMA, Boltz, and RDKit source declarations remain cache/live/local and unpinned. Caller-supplied `PromotionContext.available_at` does not prove historical availability for those operations. The separate `pinned_evidence/clinical_trial_design` path requires an exact source receipt and hash.
- Target namespace continuity proves that accepted source-declared identities remain consistent; it does not prove that external identifiers are correct, current, or biologically equivalent beyond the checked source fields.
- Clinical identity continuity proves that accepted candidate, intervention, NCT, arm-role,
  population, endpoint, posted safety-summary, asset, and INN fields remain linked under the
  implemented rules. The pinned provider additionally verifies one exact aggregate registry
  endpoint/safety design; neither path establishes source completeness, participant-level
  equivalence, endpoint or event validity, safety acceptability, efficacy, or regulatory validity.
- Pinned-evidence mappings instead use each manifest record's `observed_at` and `available_at`, require source-content SHA-256 values, and preserve the tool-payload hash separately. Preclinical promotion also checks canonical lineage ids and candidate aliases. This proves contract and provenance handling only; hashes and declared lineages do not establish scientific validity, source completeness, or true biological independence.
- Source capture proves that retained bytes match a receipt. It cannot prove that a caller-declared source version is immutable, that a local snapshot came from its declared public locator, or that reviewer-authored summaries faithfully represent the payload.
- Structured Boltz output remains contextual prediction evidence and cannot independently advance a stage.
- The four-pair external sealed run is a small contract evaluation, not a released real-world
  episode corpus, calibration study, or discovery-performance benchmark.
- Clinical evidence gap mass, resolution probability, decision relevance, and bounded VOI are
  declared workflow-priority inputs, not calibrated probabilities, causal estimates, or
  health-economic value. Real policies, catalogs, tensors, and decision packages remain external.
- Closed-loop source rejoin proves that a selected action promoted evidence whose exact source
  entered a refreshed committed tensor under bounded reviewer verification. It does not prove that
  the source is true, that the action caused the gap to resolve scientifically, or that the
  resulting workflow-ready state is clinically acceptable. Real execution batches, receipts,
  refresh records, and transitions remain external.
- This is not a clinical decision tool.
- The SCD slice is an audited small-N vertical slice, not a broad multi-disease atlas.
- Public benchmark numbers should be cited only with the caveats in `docs/12_scd_vertical_slice.md`.
- The repository intentionally avoids publishing raw source bundles, real provider review jobs,
  raw clinical/regulatory source snapshots, evaluator-only labels, locked episodes, generated
  trajectories, and local execution records.
