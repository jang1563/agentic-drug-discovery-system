# CTDBench v0.2 + Audited Sickle Cell Disease Vertical Slice

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
scaffold rather than a completed public platform. The unmerged 0.3.0.dev0
candidate adds an evidence-governed execution backbone with typed program state,
verifier-gated transitions, cross-stage identity controls, source-pinned
ingestion, tool/database adapters, scientific foundation-model interfaces, and
sealed retrospective policy evaluation. Seven of eight planned atlases still do
not have standalone public data, and the demonstrated continuous multi-stage
program currently covers one disease/target slice.

## At a Glance

| Field | Value |
| --- | --- |
| Purpose | Build a verification-oriented, auditable decision environment for drug-discovery agents. |
| Release status | 0.2.0 is public on GitHub and Hugging Face; 0.3.0.dev0 is an unmerged, not-uploaded candidate pending exact-commit approval. |
| Core control frame | Verify, defer, stop, or flag rather than silently advancing uncertain claims. |
| Not included | Raw source snapshots/bundles, real provider review jobs and ingestion runs, real sealed boards, cached episode packets, label vaults, commitment nonces, policy submissions, per-episode evaluations, hidden labels, locked episodes, generated trajectories, run logs, credentials, local paths, or model weights. |
| License | Apache-2.0. |

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
curation), plus one audited end-to-end vertical slice**. The 0.3.0.dev0 candidate
adds a typed execution and evaluation backbone around those artifacts. It is not
yet the complete autonomous eight-stage system or full trajectory atlas
described in the roadmap. Honest status:

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
  the full board and labels are not released, and this is not a scientific performance result.
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
  only selections that exactly match a committed approved endpoint mapping. It recompiles hazard ratios,
  confidence intervals, source arm measurements, and serious-adverse-event affected/at-risk counts
  from at least two source-disjoint committed trial designs. Trial-level values and source hashes
  remain intact; automatic endpoint-name mapping, cross-trial pooling, benefit-risk scoring,
  population comparability, and clinical acceptability inference are prohibited by typed records
  and a replay-time continuity verifier.
- **Built & audited:** source-derived label authority plus scoped construct-validity controls;
  callable tool/DB adapters
  (ClinicalTrials.gov, openFDA, Open Targets, ChEMBL, EMA EPAR) and multi-stage flow orchestrators;
  typed bindings for Open Targets, ChEMBL, ClinicalTrials.gov, EMA, Boltz-2, and RDKit molprops;
  a dependency-free source-pinned evidence-manifest adapter, capture/compiler CLI, and
  machine-readable receipt/job/review, disease-context, preclinical, clinical provider, and
  clinical portfolio, endpoint mapping, cross-trial synthesis, sealed-board, label-vault,
  policy-submission, and policy-report schemas;
  one disease/target slice (sickle cell) traversed retrospectively; an unscored
  prospective scaffold whose stale example is invalidated pending source refresh;
  conditional local RDKit druglikeness screening; and aggregate retrospective
  risk analysis. Local calibration cards and locked replay artifacts are excluded.
- **Mapped operations:** Open Targets disease identity and Ensembl-resolved target association;
  ChEMBL molecule-target-mechanism continuity, legacy molecule-mechanism context, molecule
  identity, and target activity volume; RDKit
  molecular properties; contextual ClinicalTrials.gov search results; source-pinned
  ClinicalTrials.gov trial designs; reviewer-approved endpoint mapping; deterministic non-pooled
  clinical benefit-risk synthesis; EMA
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
  candidate edit/rank loops, and
  learned or dynamically generated replanning, operator reauthorization workflows, and policy
  calibration remain future work. Boltz scoring needs a GPU endpoint,
  while RDKit molprops runs locally when installed.
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
  `docs/22_clinical_benefit_risk_synthesis.md` defines the explicit, source-disjoint, non-pooled
  cross-trial synthesis contract, and `docs/23_clinical_portfolio_endpoint_mapping.md` defines the
  multi-bundle portfolio transaction and append-only reviewer-approved mapping ledger.
  `docs/24_policy_replanning_and_resume.md` defines bounded policy rules, hash-bound checkpoints,
  deterministic resume, and the non-public checkpoint payload boundary.
  `docs/25_cutoff_safe_policy_evaluation.md` defines role-neutral sealed boards, external label
  commitments, policy comparison, and the external real-board boundary;
  `docs/retrospective_policy_evaluation_snapshot.json` carries aggregate-only results and hashes.
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
| `docs/22_clinical_benefit_risk_synthesis.md` | Humans + agents | Explicit cross-trial selection, retained trial values, source-disjoint provenance, non-pooling boundary, and fail-closed behavior. |
| `docs/23_clinical_portfolio_endpoint_mapping.md` | Humans + agents | Multi-bundle preflight, approved ontology identity, exact endpoint bindings, mapping ledger, synthesis dependency, and release limitations. |
| `docs/24_policy_replanning_and_resume.md` | Humans + agents | Typed non-advance observations, bounded replan rules, hash-bound checkpoints, deterministic resume, and release boundaries. |
| `docs/25_cutoff_safe_policy_evaluation.md` | Humans + agents | Cutoff-safe cached packets, role-neutral pair sealing, external label commitments, policy scoring, and claim boundaries. |
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
| `agentic_drug_discovery/policy.py` | Developers + agents | Deterministic policy rules, queue-bound replanning, checkpoint integrity, and exact resume orchestration. |
| `agentic_drug_discovery/sealed_evaluation.py` | Developers + agents | Role-neutral sealed boards, salted label vaults, fingerprint-bound submissions, strict envelope readers, and matched policy metrics. |
| `adapters/pinned_evidence_adapter.py` | Developers + agents | Validates payload-free source records for composite unmet-need and functional-effect gates. |
| `adapters/clinical_synthesis_adapter.py` | Developers + agents | Normalizes explicit synthesis specs locally without retrieving or supplying source measurements. |
| `rl_env/specs/pinned_evidence_manifest.schema.json` | Machines + reviewers | JSON Schema for pinned source identity, dates, hashes, contexts, and typed summaries. |
| `rl_env/specs/target_identity_record.schema.json` | Machines + agents | JSON Schema for the evidence-backed cross-stage target record. |
| `rl_env/specs/discovery_context_identity.schema.json` | Machines + agents | JSON Schema for evidence-backed disease, assay, and model-system records. |
| `rl_env/specs/clinical_intervention_identity.schema.json` | Machines + agents | JSON Schema for evidence-backed clinical intervention, trial, and atomic design records. |
| `rl_env/specs/clinical_benefit_risk_synthesis.schema.json` | Machines + agents | JSON Schema for reviewed multi-trial endpoint/safety selections with no supplied measurements. |
| `rl_env/specs/clinical_endpoint_mapping.schema.json` | Machines + agents | JSON Schema for approved reviewer, ontology identity, and exact endpoint/safety bindings without measurements. |
| `rl_env/specs/clinicaltrials_gov_portfolio_job.schema.json` | Machines + reviewers | JSON Schema for the exact set of single-trial jobs, receipts, and mapping-bound identities. |
| `rl_env/specs/policy_checkpoint.schema.json` | Machines + reviewers | JSON Schema for hash-bound policy checkpoints, typed pending plans, observations, directives, and replan history. |
| `rl_env/specs/sealed_evaluation_board.schema.json` | Machines + reviewers | JSON Schema for cutoff-safe role-neutral observations and cached policy-visible packets. |
| `rl_env/specs/sealed_evaluation_vault.schema.json` | Evaluators | JSON Schema for external arm, outcome, failure-cause, and commitment-nonce labels. |
| `rl_env/specs/policy_evaluation_submission.schema.json` | Machines + reviewers | JSON Schema for complete observation-fingerprint-bound policy predictions. |
| `rl_env/specs/policy_evaluation_report.schema.json` | Machines + reviewers | JSON Schema for aggregate arm, pair, unsafe-advance, and confidence diagnostics. |
| `rl_env/specs/source_receipt.schema.json` | Machines + reviewers | JSON Schema for exact source version, locator, SHA-256, size, retrieval time, and transport. |
| `rl_env/specs/pinned_evidence_ingestion_job.schema.json` | Machines + reviewers | JSON Schema for reviewer-authored summaries linked to captured receipts. |
| `rl_env/specs/cdc_mmwr_ingestion_job.schema.json` | Machines + reviewers | JSON Schema for reviewer-selected CDC MMWR article, context, value, unit, and excerpt fields. |
| `rl_env/specs/ncbi_pubmed_ingestion_job.schema.json` | Machines + reviewers | JSON Schema for reviewer-selected PubMed article, METHODS/RESULTS evidence, typed gap value, and context anchors. |
| `rl_env/specs/chembl_activity_ingestion_job.schema.json` | Machines + reviewers | JSON Schema for linked ChEMBL release resources, typed functional endpoint, target, candidate aliases, and publication lineage. |
| `rl_env/specs/ncbi_pubmed_disease_model_ingestion_job.schema.json` | Machines + reviewers | JSON Schema for a typed in-vivo exposure, endpoint, variation, p-value, model, and candidate review job. |
| `rl_env/specs/clinicaltrials_gov_ingestion_job.schema.json` | Machines + reviewers | JSON Schema for exact registry, arm, population, endpoint, measurement, analysis, and serious-adverse-event review fields. |
| `tests/` | Developers + CI | Fail-closed control-plane regression tests. |
| `tests/test_clinical_benefit_risk_synthesis.py` | Developers + reviewers | Two-source tool-to-replay synthesis path plus mismatch, overlap, pooling, forgery, unbound-support, direct-commit, and removal controls. |
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
