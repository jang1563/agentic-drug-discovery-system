# Public Launch Checklist

This checklist is the human-readable companion to `release_decision_packet.json`.
It records the `candidate_pending_human_approval` state for the 0.3.0.dev3
candidate while preserving the approved 0.3.0.dev2 public baseline. The 0.2.0
tag remains the latest stable release. No candidate may update either public
surface without a new exact-package review and explicit human approval.
Scientific anchors: `docs/12_scd_vertical_slice.md`,
`docs/13_target_id_governance_node.md`, and
`docs/public_evidence_summary.json`. Execution contracts:
`docs/14_target_identity_continuity.md` and
`docs/15_discovery_context_identity.md`, and
`docs/16_clinical_intervention_identity.md`. The source capture/compiler contract is
`docs/17_pinned_source_ingestion.md`; the CDC MMWR provider contract is
`docs/18_cdc_mmwr_ingestion.md`; the NCBI PubMed provider contract is
`docs/19_ncbi_pubmed_ingestion.md`; the preclinical provider and lineage-independence contract is
`docs/20_preclinical_provider_ingestion.md`; the ClinicalTrials.gov trial-design contract is
`docs/21_clinical_provider_ingestion.md`; the cross-trial synthesis contract is
`docs/22_clinical_benefit_risk_synthesis.md`; portfolio ingestion and approved endpoint mapping
are in `docs/23_clinical_portfolio_endpoint_mapping.md`; typed policy replanning and checkpoint
resume are in `docs/24_policy_replanning_and_resume.md`; cutoff-safe matched and sealed policy
evaluation is in `docs/25_cutoff_safe_policy_evaluation.md`; independently curated held-out
preregistration and stage-stratified uncertainty are in
`docs/26_independent_heldout_evaluation.md`; the synthetic cross-disease UC conformance boundary is
in `docs/41_ulcerative_colitis_conformance_slice.md`, and the separate public-source UC provider
execution is in `docs/42_uc_provider_validation.md`; its single-trial induction/maintenance
population boundary is in `docs/43_uc_phase_population_alignment.md`, and the independent primary
maintenance percentage-point replication is in
`docs/44_uc_maintenance_risk_difference_replication.md`; the second-disease RA HOLD replication is
in `docs/45_ra_acr20_risk_difference_hold_replication.md`; the first real source-disjoint additive
tensor is in `docs/46_ra_olokizumab_source_disjoint_additive_tensor.md`. The external scorer is under `benchmark/`,
`scripts/audit/validate_vertical_slice_doc.py` checks the vertical-slice claims, and
`scripts/audit/validate_policy_evaluation_snapshot.py` checks the sealed-evaluation aggregate.

## Current Launch State

| Surface | Current state | Publication record |
| --- | --- | --- |
| GitHub | 0.3.0.dev2 public baseline on `main`; 0.3.0.dev3 candidate not approved or merged | Baseline content published through PR 18 at `ea9cc3575fa687a3f05b6e0f9bf81a85413e5436` |
| Hugging Face | 0.3.0.dev2 public exact-source mirror; 0.3.0.dev3 candidate not uploaded | Baseline upload `8125fcfdb4984045948c2ffacb37c2c6f0c3ae70`; 169 files |

Machine status is `candidate_pending_human_approval`. The public repositories
remain at 0.3.0.dev2 while the 0.3.0.dev3 exact candidate is reviewed and
validated.

## 0.3.0.dev3 Candidate Gate

- [x] Unequal/influential-cluster calibration code, CLI, schemas, exact synthetic artifacts,
  research note, and fail-closed tests are present.
- [x] Public outputs are aggregate-only and preserve the dominant-cluster production hard stop.
- [x] Empirical-template cluster-superpopulation calibration binds the exact conditional report,
  preserves all known truths, reports realized dominance without filtering, and carries an explicit
  no-external-transportability boundary.
- [x] Hazard-, odds-, and risk-ratio semantics use one fixed measure/direction contract across
  provider extraction, semantic promotion, endpoint mapping, synthesis, and evidence cells.
- [x] Percentage-point risk differences use null 0, explicit percent units, endpoint-declared
  direction, and candidate-first sign binding through non-pooled synthesis; the decision tensor
  uses a separate preregistered percentage-point CI-width threshold.
- [x] The ulcerative-colitis synthetic conformance surface remains distinct from two public-source
  provider-only induction runs; neither is represented as pooled efficacy, safety acceptability,
  independent disease-slice review, or a therapeutic claim.
- [x] The UC induction/maintenance population-alignment run preserves distinct phase counts,
  treats the shared NCT/source as one trial, and never infers participant identity or longitudinal
  exchangeability.
- [x] The independent UC maintenance replication records its screened exclusions and exact hashes,
  and is not represented as same-candidate replication, pooled efficacy, safety acceptability, or
  a treatment recommendation.
- [x] The RA ACR20 replication commits a source-valid null-crossing result on `HOLD`, records
  denominator mismatch and screened controls.
- [x] The olokizumab RA pair compiles two source-disjoint Week-12 ACR20 cells, preserves source
  proportions and distinct inadequate-response populations, and remains on `HOLD` without a
  pooled efficacy, comparative-safety, population-exchangeability, or treatment claim.
- [x] Release metadata records an unmerged and not-uploaded candidate.
- [ ] The exact committed source and generated Hugging Face package pass every blocking command.
- [ ] GitHub Actions passes for the exact candidate commit.
- [ ] The owner approves that exact commit and package before merge or upload.

## 0.2.0 Baseline Record

- [x] GitHub remained private until the final boundary review was approved.
- [x] Hugging Face remained private until the final boundary review was approved.
- [x] The prior public release is recorded by GitHub PR 7 and the 2026-07-12 owner approval.

## 0.3.0.dev0 Publication Record

- [x] The README distinguishes the executable control plane from roadmap-only functionality.
- [x] `docs/release_boundary.md` still excludes raw source snapshots, hidden
  labels, locked episodes, generated trajectories, run logs, credentials,
  machine-local paths, and model weights.
- [x] `release_manifest.json` and `huggingface/release_manifest.json` match the
  public release surface.
- [x] `release_decision_packet.json` says `public_released_after_human_approval`.
- [x] Local control-plane, benchmark, lint, compile, wheel, and source-boundary checks pass.
- [x] The linked external dataset's Croissant
  metadata is absent from this artifact mirror.
- [x] The SCD and target-node aggregate claims match
  `docs/public_evidence_summary.json`; raw runs and per-record gold remain excluded.
- [x] Disease, target, candidate, assay, model-system, intervention, trial, arm, population,
  endpoint, and atomic design identity contracts are mirrored in machine schemas and fail-closed
  tests.
- [x] Multi-trial portfolio and endpoint-mapping contracts have strict schemas, synthetic examples,
  payload-free extraction, append-only replay, and direct-commit/removal attack controls; no real
  portfolio or reviewer artifact is included.
- [x] Source receipt, ingestion job, and review-report contracts are mirrored in machine schemas;
  raw bundles, real provider review jobs, and ingestion runs remain outside both release surfaces.
- [x] The CDC MMWR provider schema, synthetic example, extractor, and matched controls are mirrored;
  the real snapshot, reviewer job, and any real manifest remain outside both release surfaces.
- [x] The NCBI PubMed provider schema, synthetic example, extractor, and matched context controls
  are mirrored; the real XML, reviewer job, and external CDC/PubMed defer check remain outside both
  release surfaces.
- [x] The ChEMBL functional-activity and PubMed disease-model schemas, synthetic examples,
  extractors, typed endpoint checks, and matched lineage controls are mirrored. Real API/XML
  bundles, reviewer jobs, and external run artifacts remain outside both release surfaces; only
  payload-free ids, hashes, outcomes, and limitations are documented.
- [x] `docs/preclinical_provider_validation_snapshot.json` is machine-readable, payload-free,
  self-consistent under the provider-pair test, and explicit that exact replay requires external
  artifacts.
- [x] The ClinicalTrials.gov schema, synthetic exact-study fixture, extractor, atomic promotion,
  endpoint/safety arm reconciliation, arm-role/endpoint/safety-support attacks, and matched
  missing-safety control are mirrored. The real API bytes and reviewer job remain external.
- [x] `docs/clinical_provider_validation_snapshot.json` is machine-readable, payload-free,
  self-consistent under the clinical-provider test, and explicit that exact replay requires
  external artifacts.
- [x] The cross-trial synthesis schema, synthetic selection, local adapter, typed trial/synthesis
  records, source-disjoint recompilation, non-pooling guard, serialization, exact replay, and
  mismatch/overlap/forgery/removal controls are mirrored. No real review selection, pooled result,
  benefit-risk score, or clinical judgment is included.
- [x] Typed replan observations/rules/directives, per-rule and global limits, checkpoint SHA-256
  envelopes, stale-token/tamper controls, and deterministic resume tests are mirrored. Real
  checkpoints and policy-run artifacts remain outside both release surfaces.
- [x] Role-neutral sealed-board, external label-vault, policy-submission, and aggregate-report
  schemas are mirrored with synthetic fail-closed tests. The real 4-pair/8-episode run publishes
  aggregate metrics and hashes only; full states, cached packets, labels, nonces, submissions, and
  per-episode scores remain external.
- [x] The eight-stage provider-backed fixture carries one cumulative ledger from disease context
  through source-pinned clinical endpoint/safety design and EMA regulatory review, reaches
  `COMPLETED`, and replays
  exactly.
- [x] The candidate is committed to an exact reviewed source commit.
- [x] GitHub Actions `release-audit` is green for that exact commit and the
  linear-history publication commit.
- [x] The Hugging Face package is built from the public `main` commit and its exact file set,
  source tree, byte sizes, and SHA-256 values are validated.
- [x] The owner explicitly approves the exact candidate commit and package.
- [x] The approved content is merged to public `main`.
- [x] The approved package is uploaded and anonymous GitHub/Hub reads verify the
  source commit and upload manifest.

## 0.3.0.dev1 Publication Record

- [x] Held-out protocol, evaluator-only curator manifest, and stage-stratified aggregate-report
  schemas have strict readers, exact synthetic examples, majority/adjudication controls, Wilson
  intervals, and coverage sufficiency flags.
- [x] The release boundary excludes real curator identities, attestations, votes, adjudications,
  curation manifests, and per-episode curation results.
- [x] Documentation states that the existing real retrospective board is unchanged and that no
  real independently curated result is claimed.
- [x] The clinical evidence decision layer requires a committed replay-valid synthesis, preserves
  exact trial/source provenance, and deterministically replays tensor gaps, bounded VOI scores,
  action ranking, gap partition, and budget accounting.
- [x] The decision package schema and compiler-generated synthetic example are strict-reader
  compatible, and tests cover safety signals, insufficient budget, low VOI, duplicate actions,
  source overlap, direction forgery, duplicate JSON keys, and integrity tampering.
- [x] The release boundary excludes real clinical decision policies, action catalogs, evidence
  tensors, and compiled decision packages; `ADVANCE` is documented as workflow readiness only.
- [x] The clinical closed-loop layer binds selected actions to exact state/package/tensor/plan
  identities, executes through the standard fail-closed runner, bounds reviewer-verifier refresh,
  consumes attempted actions, and requires exact promoted-evidence source rejoin for every resolved
  gap.
- [x] The closed-loop schema and compiler-generated synthetic transition are strict-reader
  compatible, contain no provider payload, and replay one bounded `HOLD`-to-`ADVANCE`
  evidence-workflow transition with exact cost, packet, action, evidence, and source hashes.
- [x] The release boundary excludes real closed-loop policies, execution batches, provider
  requests/outcomes, receipts, reviewer refresh records, before/after tensors, and transition
  packages.
- [x] GitHub `main` and the public Hugging Face Dataset expose the approved 0.3.0.dev1 exact-source release.
- [x] The exact 0.3.0.dev1 candidate commit and Hugging Face package received explicit human
  approval.
- [x] The approved candidate was merged and uploaded, and the anonymous Hub snapshot passed exact
  file/hash validation.

## 0.3.0.dev2 Publication Record

- [x] The strict ClinicalTrials.gov v3 provider accepts frozen hazard-, odds-, and risk-ratio
  aliases, preserves valid benefit/harm/uncertain intervals, binds endpoint and safety treatment
  phase, and permits sparse zero counts only for unselected groups.
- [x] Missing descriptive arm summaries retain their raw source marker, serialize as `null`, and
  produce a typed tenth tensor dimension and provenance-linked workflow gap.
- [x] Unsupported effect aliases, title qualifiers, arbitrary missing markers, selected zero-risk
  safety groups, imputation, pooling, and clinical acceptability inference remain fail-closed.
- [x] The final implementation passed 250 core tests, 89 subtests, 11 benchmark tests, Ruff,
  compileall, wheel isolation, release-boundary audits, and exact schema/example replay.
- [x] Nine frozen external ClinicalTrials.gov snapshots passed the final provider contract; their
  raw bytes, reviewer jobs, and cohort artifacts remain outside both public surfaces.
- [x] PR 18 passed the GitHub release audit and merged approved content commit
  `ea9cc3575fa687a3f05b6e0f9bf81a85413e5436`.
- [x] The 169-file Hub package was built from that exact commit and validated before upload.
- [x] The owner explicitly approved this GitHub and Hugging Face update on 2026-07-31.

## Required Local Commands

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

## Launch Decision Rule

Every future candidate may update the public release only when every candidate
gate is checked, every required command is green, the GitHub Actions release
audit is green for the exact commit, and the owner explicitly approves that
commit and its Hugging Face package.

If any release-boundary check regresses, hold the future candidate and leave the
0.3.0.dev2 public baseline unchanged until the issue is fixed.
