---
pretty_name: Agentic Drug Discovery System
license: apache-2.0
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

This is the candidate Hugging Face Dataset-card package for the Agentic Drug Discovery System public artifact. The existing public Dataset is the 0.2.0 baseline; this 0.3.0.dev0 package is not uploaded until its exact source commit passes review and receives explicit approval. The package mirrors the executable control plane, tests, documentation, schemas, aggregate evidence, release metadata, safety boundaries, and the `ctdbench` scorer. It is not a row dataset or model release and does not contain raw source bundles, real provider review jobs, ingestion runs, raw clinical/regulatory source snapshots, hidden labels, locked episodes, generated trajectories, scheduler logs, local paths, credentials, or unpublished working notes.

## At A Glance

- **Surface:** Hugging Face Dataset repository.
- **Public state:** 0.2.0 baseline.
- **Candidate:** 0.3.0.dev0 source prepared; not uploaded; approval pending.
- **Contents:** Bounded planner, typed execution core, deterministic policy replanning and hash-bound checkpoint resume, cross-stage disease/target/assay/model-system/intervention/trial/design identity ledgers, atomic multi-trial portfolio extraction, reviewer-approved endpoint mapping, mapping-gated source-disjoint non-pooled benefit-risk synthesis, source capture and payload-free manifest compiler, semantic mappings, dependency-free pinned-evidence adapter and binding, stage and multi-stage program runners, matched evaluator, tests, documentation, schemas, aggregate evidence, manifests, audit code, and the `ctdbench` scorer.
- **Excludes:** Raw source data, hidden labels, generated trajectories, logs, credentials, local paths, or model weights.
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
| `docs/public_evidence_summary.json` | Machine-readable aggregate claims and limitations. |
| `agentic_drug_discovery/` | Bounded planning, typed tool execution, semantic promotion, stage and program orchestration, matched evaluation, replay, and fail-closed transitions. |
| `agentic_drug_discovery/ingestion.py` | Immutable source receipts, external bundle verification, payload-free manifest compilation, and review reports. |
| `agentic_drug_discovery/cdc_mmwr.py` | CDC MMWR article and reviewer-selected evidence verification with excerpt removal. |
| `agentic_drug_discovery/ncbi_pubmed.py` | NCBI PubMed EFetch article and treatment-gap evidence verification with excerpt and anchor removal. |
| `agentic_drug_discovery/chembl_activity.py` | ChEMBL release/resource reconciliation and typed functional-activity verification with assay-text removal. |
| `agentic_drug_discovery/clinicaltrials_gov.py` | ClinicalTrials.gov study, arm, population, endpoint, statistical-analysis, and serious-adverse-event verification with payload removal. |
| `agentic_drug_discovery/clinical_portfolio.py` | Atomic exact-set multi-trial extraction with source-hash disjointness and payload-free output. |
| `agentic_drug_discovery/clinical_endpoint_mapping.py` | Strict approved-mapping parser, endpoint/safety fingerprint compiler, approval chronology, and replay validation. |
| `agentic_drug_discovery/clinical_synthesis.py` | Deterministic source-ledger compiler for trial-level hazard ratios and serious-event risk differences without pooling. |
| `adapters/pinned_evidence_adapter.py` | Dependency-free validation and lookup for source-pinned, payload-free evidence manifests. |
| `adapters/clinical_synthesis_adapter.py` | Local normalization of approved endpoint mappings and reviewed synthesis selections without supplied source measurements. |
| `adapters/execution_registry.py` | Typed contracts for the pinned adapter and caller-supplied GitHub adapter instances. |
| `rl_env/specs/pinned_evidence_manifest.schema.json` | Machine-readable pinned-record schema; the adjacent example is synthetic. |
| `rl_env/specs/target_identity_record.schema.json` | Machine-readable cross-stage target record; the adjacent example is synthetic. |
| `rl_env/specs/discovery_context_identity.schema.json` | Machine-readable disease, assay, and model-system records; the adjacent example is synthetic. |
| `rl_env/specs/clinical_intervention_identity.schema.json` | Machine-readable clinical intervention, trial, endpoint, safety, and atomic design records; the adjacent example is synthetic. |
| `rl_env/specs/clinical_endpoint_mapping.schema.json` | Machine-readable approved reviewer, ontology identity, and exact endpoint/safety binding contract; the adjacent example is synthetic. |
| `rl_env/specs/clinical_benefit_risk_synthesis.schema.json` | Machine-readable reviewed multi-trial selection contract; the adjacent example is synthetic. |
| `rl_env/specs/source_receipt.schema.json` | Machine-readable exact source version, locator, hash, size, retrieval time, and transport. |
| `rl_env/specs/pinned_evidence_ingestion_job.schema.json` | Machine-readable reviewer-authored summaries linked to external source receipts. |
| `rl_env/specs/cdc_mmwr_ingestion_job.schema.json` | Machine-readable CDC MMWR article, context, value, unit, and excerpt review contract. |
| `rl_env/specs/ncbi_pubmed_ingestion_job.schema.json` | Machine-readable PubMed article, METHODS/RESULTS, typed treatment-gap value, and context-anchor contract. |
| `rl_env/specs/chembl_activity_ingestion_job.schema.json` | Machine-readable ChEMBL release, linked resource, typed endpoint, candidate alias, target, and lineage contract. |
| `rl_env/specs/ncbi_pubmed_disease_model_ingestion_job.schema.json` | Machine-readable PubMed in-vivo exposure, endpoint, model, candidate, and lineage contract. |
| `rl_env/specs/clinicaltrials_gov_ingestion_job.schema.json` | Machine-readable exact study, arm, population, endpoint, measurement, analysis, and serious-adverse-event contract. |
| `rl_env/specs/clinicaltrials_gov_portfolio_job.schema.json` | Machine-readable exact set of single-trial jobs, receipts, identities, and approved mapping bindings. |
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
| `tests/` | Dependency-free planning, multi-stage stopping, mapping, evaluation, execution, replay, and transition regression tests. |
| `benchmark/` | Installable `ctdbench` scorer and tests. |
| `docs/public_launch_checklist.md` | Human launch checklist before any visibility change. |
| `scripts/audit/*.py` | Local release audits and reproducible Hub package builder. |

## Not Included

- Raw source snapshots or full case banks.
- Raw source bundles, real provider review jobs, ingestion runs, multi-trial portfolio selections,
  endpoint-family reviewer approvals, ontology-authority resolutions, or reviewer working files.
- Hidden/evaluator labels or locked episode records.
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
- Current visibility: public 0.2.0 baseline
- Candidate update: 0.3.0.dev0, not uploaded, explicit approval required

## Source

Primary source repository:

`https://github.com/jang1563/agentic-drug-discovery-system`
