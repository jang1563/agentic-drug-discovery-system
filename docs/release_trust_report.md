# Release Trust Report

Last reviewed: 2026-07-15

This report summarizes what the public GitHub repository and Hugging Face Dataset mirror are intended to prove, what they do not prove, and which files machines should inspect first. The 0.2.0 surfaces are the current public baseline; the 0.3.0.dev0 execution-core update is a candidate pending exact-commit review, approval, merge, and Hub upload.

## Trust Claims

| Claim | Evidence | Boundary |
| --- | --- | --- |
| The public artifact is intentionally scoped. | `docs/release_boundary.md`, `release_manifest.json`, `huggingface/release_manifest.json` | Raw source snapshots, evaluator-only labels, locked episodes, generated trajectories, logs, credentials, local paths, and model weights are excluded. |
| The release decision is machine-readable. | `release_decision_packet.json` | The current candidate is explicitly pending; the prior 0.2.0 approval is not approval of 0.3.0.dev0. |
| The SCD vertical slice is caveats-first. | `docs/12_scd_vertical_slice.md`, `scripts/audit/validate_vertical_slice_doc.py` | The slice is one disease, small-N, and not evidence of broad clinical prediction or autonomous drug design capability. |
| Aggregate claims are machine-readable. | `docs/public_evidence_summary.json`, `docs/13_target_id_governance_node.md` | Raw runs and per-record gold remain excluded; aggregate values are not independent replication. |
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
| Source-pinned ClinicalTrials.gov evidence promotes atomically. | `docs/21_clinical_provider_ingestion.md`, `docs/clinical_provider_validation_snapshot.json`, `agentic_drug_discovery/clinicaltrials_gov.py`, `rl_env/specs/clinicaltrials_gov_ingestion_job.schema.json`, `tests/test_clinicaltrials_gov_ingestion.py` | One exact registry receipt is reconciled through NCT/version, candidate/condition, protocol/result/adverse-event arms, population, posted endpoint, analysis, and serious-adverse-event affected/at-risk counts. The bounded external example advances; removing only safety metadata defers with no partial identity state. This proves exact aggregate reconciliation, not registry authority, endpoint/event validity, participant-level results, safety acceptability, efficacy, or discovery performance. |
| Cross-trial benefit-risk synthesis preserves source-level provenance without pooling. | `docs/22_clinical_benefit_risk_synthesis.md`, `agentic_drug_discovery/clinical_synthesis.py`, `rl_env/specs/clinical_benefit_risk_synthesis.schema.json`, `tests/test_clinical_benefit_risk_synthesis.py` | Reviewed trial/design/endpoint/safety selections are recompiled from committed source-pinned ledgers. Hazard ratios, confidence intervals, arm measurements, serious-event counts, evidence IDs, and source hashes remain trial-level and source-disjoint. This is descriptive harmonization, not a meta-analysis, benefit-risk score, population comparability claim, clinical acceptability judgment, or treatment recommendation. |
| Multi-trial portfolio ingestion and endpoint mapping are exact-set and replay-bound. | `docs/23_clinical_portfolio_endpoint_mapping.md`, `agentic_drug_discovery/clinical_portfolio.py`, `agentic_drug_discovery/clinical_endpoint_mapping.py`, `rl_env/specs/clinicaltrials_gov_portfolio_job.schema.json`, `rl_env/specs/clinical_endpoint_mapping.schema.json`, `tests/test_clinical_portfolio.py` | Every declared single-trial job and external bundle must verify before payload-free output. A reviewer-approved mapping retains exact endpoint/safety fingerprints and source hashes, and synthesis must reference it. Public tests and examples are synthetic; no real multi-trial portfolio or ontology-authority resolution is release-approved. |
| Planning is bounded before required calls spend budget. | `agentic_drug_discovery/planning.py`, `tests/test_agent_loop.py` | Preflight covers state/version, stage, contracts, chronology, duplicate requests, steps, and declared cost. It does not prove that a chosen tool plan is scientifically optimal. |
| Policy replanning and resume preserve deterministic boundaries. | `docs/24_policy_replanning_and_resume.md`, `agentic_drug_discovery/policy.py`, `rl_env/specs/policy_checkpoint.schema.json`, `tests/test_policy_replanning.py` | Only predeclared typed replacement plans can follow a paused or blocked observation. Rule/global limits, queue identity, policy identity, observation hashes, checkpoint hashes, state/ledger chains, and stale resume tokens fail closed. This proves control-flow continuity, not plan optimality or scientific validity; real checkpoints remain external. |
| Selected tool operations have explicit semantic mappings. | `agentic_drug_discovery/promotion.py`, `tests/test_semantic_mappings.py` | The mappings validate known payload shapes and conservative interpretation rules; they do not prove payload truth, external database completeness, or cross-disease validity. |
| Bounded multi-stage execution reaches every verifier-gated stage. | `agentic_drug_discovery/orchestration.py`, `agentic_drug_discovery/program.py`, `tests/test_program_runner.py`, `tests/test_adapter_bindings.py`, `tests/test_pinned_evidence_adapter.py` | Ordered stage runs share one cumulative ledger and continue only after accepted advance decisions. One five-stage fixture intentionally defers on activity-count context; one synthetic provider-backed fixture preserves disease, target, candidate, preclinical, trial-design, and intervention identities through all eight stages and replays exactly. This is control-path completeness, not autonomous discovery or a performance result. |
| Evaluation requires matched success and failure arms. | `agentic_drug_discovery/matched_evaluation.py`, `tests/test_matched_evaluation.py`, `tests/test_target_identity_continuity.py`, `tests/test_pinned_evidence_adapter.py`, `tests/test_pinned_evidence_ingestion.py`, `tests/test_cdc_mmwr_ingestion.py`, `tests/test_ncbi_pubmed_ingestion.py`, `tests/test_preclinical_provider_pair.py`, `tests/test_clinicaltrials_gov_ingestion.py`, `tests/test_semantic_mappings.py` | The schema enforces cutoff and context matching. Target-symbol, assay-target-link, compiled source independence, CDC same-document reuse, PubMed cross-population context, preclinical publication-lineage reuse, and ClinicalTrials.gov condition/source-identity pairs each isolate a bounded failure, but this package does not publish a real matched episode corpus or claim measured discovery performance. |
| A Hugging Face mirror is reproducible from an exact Git commit. | `scripts/audit/build_hf_release_package.py`, `scripts/audit/validate_hf_release_package.py`, `upload_manifest.json` on the Hub | The builder reads Git commit objects, and the validator checks the exact file set, source tree, sizes, and SHA-256 values; the 0.3.0.dev0 package cannot be claimed until the candidate is committed and rebuilt. |
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

## Machine Anchors

| Path | Role |
| --- | --- |
| `release_manifest.json` | Canonical GitHub and Hugging Face release scope. |
| `release_decision_packet.json` | Public launch status, approval gate, and hard stops. |
| `huggingface/release_manifest.json` | Hugging Face package include/exclude list. |
| `docs/public_evidence_summary.json` | Aggregate-only scientific claim ledger and limitation flags. |
| `docs/preclinical_provider_validation_snapshot.json` | Payload-free external provider ids, typed values, hashes, matched outcomes, and exact-replay limitations. |
| `docs/clinical_provider_validation_snapshot.json` | Payload-free NCT/design identities, typed aggregate values, artifact hashes, stage outcome, matched control, and exact-replay limitations. |
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
| `agentic_drug_discovery/pinned_evidence.py` | Shared strict normalization for direct and compiled payload-free evidence manifests. |
| `agentic_drug_discovery/ingestion.py` | Immutable source receipts/bundles, HTTPS and local capture, payload verification, manifest compilation, and review reports. |
| `agentic_drug_discovery/cdc_mmwr.py` | Provider-specific article, section, value, unit, geography, reference-period, and excerpt-hash verification. |
| `agentic_drug_discovery/ncbi_pubmed.py` | Provider-specific EFetch request, direct article identity, structured abstract, typed treatment-gap, context-anchor, and excerpt-hash verification. |
| `agentic_drug_discovery/chembl_activity.py` | Provider-specific ChEMBL release/resource identity, functional endpoint, candidate alias, target component, lineage, and assay-text-hash verification. |
| `agentic_drug_discovery/clinicaltrials_gov.py` | Provider-specific registry receipt, NCT/version, arm/result/adverse-event group, population, endpoint, analysis, and serious-adverse-event verification with source-payload removal. |
| `agentic_drug_discovery/clinical_portfolio.py` | Exact-set multi-job/bundle preflight and payload-free portfolio extraction. |
| `agentic_drug_discovery/clinical_endpoint_mapping.py` | Approved reviewer/ontology declaration parsing, exact endpoint/safety fingerprint binding, and replay validation. |
| `agentic_drug_discovery/clinical_synthesis.py` | Mapping-gated selection parsing, source-disjoint trial recompilation, trial-level effect/safety records, and non-pooling invariants. |
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
| `rl_env/specs/clinical_endpoint_mapping.schema.json` | Machine schema for reviewer approval, ontology identity, and exact ordered endpoint/safety bindings. |
| `rl_env/specs/clinical_endpoint_mapping.example.json` | Synthetic approved mapping example; ontology authority is not implied. |
| `rl_env/specs/clinicaltrials_gov_portfolio_job.schema.json` | Machine schema for the exact set of single-trial jobs, receipts, and mapping bindings. |
| `rl_env/specs/clinicaltrials_gov_portfolio_job.example.json` | Synthetic two-trial portfolio references with no source bytes or local paths. |
| `rl_env/specs/policy_checkpoint.schema.json` | Machine schema for checkpoint envelopes, pending typed steps, observations, directives, queue histories, and SHA-256 identity. |
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
| `tests/test_pinned_evidence_adapter.py` | Composite-gate success, same-source failure, cutoff, unavailable, eight-stage provider-backed replay, and matched-pair coverage. |
| `tests/test_pinned_evidence_ingestion.py` | Receipt/job parsing, source tamper and boundary attacks, compilation, CLI capture, and matched stage integration. |
| `tests/test_cdc_mmwr_ingestion.py` | Provider identity/location/value/unit attacks, excerpt removal, bounded stage integration, and matched same-document failure. |
| `tests/test_ncbi_pubmed_ingestion.py` | PubMed identity/request/XML/retraction/value/anchor attacks, excerpt removal, bounded stage integration, and matched cross-population failure. |
| `tests/test_chembl_activity_ingestion.py` | ChEMBL release/resource identity, endpoint, target, alias, lineage, text-removal, compiler, and CLI-hash coverage. |
| `tests/test_ncbi_pubmed_disease_model_ingestion.py` | PubMed article, exposure, endpoint, model/candidate anchor, retraction, text-removal, and CLI-hash coverage. |
| `tests/test_preclinical_provider_pair.py` | End-to-end sanitized-provider advance and controlled shared-lineage defer coverage with typed ledger checks. |
| `tests/test_clinicaltrials_gov_ingestion.py` | Exact registry extraction, payload removal, atomic endpoint/safety promotion, role/support continuity attacks, snapshot consistency, and matched missing-safety coverage. |
| `tests/test_target_identity_continuity.py` | Namespace rebinding/collision, candidate-link, and matched target-symbol continuity coverage. |
| `tests/test_context_identity_continuity.py` | Disease/model rebinding, assay namespace collision, unknown-candidate evidence, and strict schema-example coverage. |
| `tests/test_clinical_identity_continuity.py` | Intervention rebinding, trial namespace collision, unknown-intervention linkage, support removal, and strict schema-example coverage. |
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

The 0.3.0.dev0 candidate package is a deliberate subset of GitHub. Live adapters, legacy chains,
evaluator-directory scaffolds, contributor/security files, and GitHub automation remain
GitHub-only. The Hub subset contains the dependency-free pinned-evidence adapter and binding,
bounded planner, semantic mappings, stage and program runners, matched evaluator, typed execution
core, source capture/compiler code, target, discovery-context, clinical-intervention, and ingestion
schemas, ChEMBL functional-activity and PubMed disease-model extractors, tests, documentation,
ClinicalTrials.gov endpoint/safety trial-design extractor, aggregate evidence, audit code, and the `benchmark/`
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
- Matched episode types and scoring code do not substitute for a cutoff-safe real-world episode corpus.
- This is not a clinical decision tool.
- The SCD slice is an audited small-N vertical slice, not a broad multi-disease atlas.
- Public benchmark numbers should be cited only with the caveats in `docs/12_scd_vertical_slice.md`.
- The repository intentionally avoids publishing raw source bundles, real provider review jobs,
  raw clinical/regulatory source snapshots, evaluator-only labels, locked episodes, generated
  trajectories, and local execution records.
