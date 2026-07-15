# RL Environment

This directory is for the environment abstraction that turns long-horizon discovery workflows into replayable tasks.

## Subdirectories

- `specs/`: state/action/observation/trajectory schemas.
- `rewards/`: reward decomposition and scoring functions.
- `tasks/`: task instances and benchmark splits.
- `trajectories/`: recorded or generated trajectories.
- `baselines/`: rule, retrieval, prompt-only, and verifier-ablation baselines.

## First Build Target

Start with cached-output replay. The first environment should not require live expensive model or tool calls.

Current repository scope:

- Keep schemas and reward-component definitions in Git.
- Use `specs/pinned_evidence_manifest.schema.json` for payload-free composite evidence records,
  `specs/target_identity_record.schema.json` for serialized cross-stage target identity records,
  and `specs/discovery_context_identity.schema.json` for disease, assay, and model-system identity
  records. Use `specs/clinical_intervention_identity.schema.json` for candidate-linked clinical
  intervention, trial, and atomic arm/population/endpoint design records. All adjacent examples are
  synthetic contract fixtures.
- Use `specs/clinical_endpoint_mapping.schema.json` for reviewer-approved endpoint-family ontology
  bindings across two or more committed trial/design/endpoint/safety records. The schema accepts
  identity selections and review metadata only: measurements remain ledger-derived, source hashes
  must be disjoint, and ontology-authority verification stays explicitly unresolved. Use
  `specs/clinical_benefit_risk_synthesis.schema.json` for the subsequent mapping-bound synthesis.
  It preserves trial-level evidence without automatic mapping, pooling, benefit-risk scoring, or
  clinical acceptability inference. Both adjacent examples are synthetic.
- Use `specs/source_receipt.schema.json`,
  `specs/pinned_evidence_ingestion_job.schema.json`, and
  `specs/pinned_evidence_ingestion_review.schema.json` for the external raw-source capture and
  payload-free manifest compilation boundary. Raw bundles and real ingestion runs stay outside Git.
- Use `specs/cdc_mmwr_ingestion_job.schema.json` for CDC article, context, numeric value, unit, and
  evidence-location review. Use `specs/ncbi_pubmed_ingestion_job.schema.json` for strict PubMed
  article identity, structured-abstract treatment-gap evidence, typed comparison, and context
  anchors. Adjacent examples are synthetic; real snapshots and reviewer jobs stay outside Git.
- Use `specs/chembl_activity_ingestion_job.schema.json` for linked release status, activity, assay,
  document, molecule, target, typed endpoint, functional-readout, alias, and lineage review. Use
  `specs/ncbi_pubmed_disease_model_ingestion_job.schema.json` for exact PubMed article identity,
  candidate/model anchors, typed exposure regimen, endpoint variation, p-value, and lineage review.
  Adjacent examples are synthetic; real provider bundles and jobs stay outside Git.
- Use `specs/clinicaltrials_gov_ingestion_job.schema.json` for one exact registry version, selected
  candidate/comparator arms, population, posted endpoint, measurements, and statistical analysis.
  Use `specs/clinicaltrials_gov_portfolio_job.schema.json` to bind an exact, pairwise source-disjoint
  set of those single-trial review jobs to one approved endpoint mapping before emitting a
  payload-free portfolio ingestion job. Adjacent jobs and study fixtures are synthetic; real API
  bytes, portfolio selections, and reviewer approvals stay outside Git.
- Keep concrete task instances, trajectories, evaluator labels, generated reward outputs, and case-bank-specific scripts outside Git until a release package is explicitly prepared.
