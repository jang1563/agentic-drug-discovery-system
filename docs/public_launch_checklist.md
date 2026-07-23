# Public Launch Checklist

This checklist is the human-readable companion to `release_decision_packet.json`.
It separates the existing 0.2.0 public baseline from the 0.3.0.dev0 candidate;
approval of the baseline is not approval of the candidate.
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
evaluation is in `docs/25_cutoff_safe_policy_evaluation.md`. The external scorer is under `benchmark/`,
`scripts/audit/validate_vertical_slice_doc.py` checks the vertical-slice claims, and
`scripts/audit/validate_policy_evaluation_snapshot.py` checks the sealed-evaluation aggregate.

## Current Launch State

| Surface | Current state | Candidate action allowed now? |
| --- | --- | --- |
| GitHub | 0.2.0 public baseline; 0.3.0.dev0 candidate not approved or merged | No |
| Hugging Face | 0.2.0 public baseline; 0.3.0.dev0 candidate not uploaded | No |

Machine status is `candidate_pending_human_approval`. Do not merge the candidate
into public `main` or update the public Hub Dataset before explicit human approval
of the exact committed package.

## 0.2.0 Baseline Record

- [x] GitHub remained private until the final boundary review was approved.
- [x] Hugging Face remained private until the final boundary review was approved.
- [x] The prior public release is recorded by GitHub PR 7 and the 2026-07-12 owner approval.

## 0.3.0.dev0 Candidate Gates

- [x] The README distinguishes the executable control plane from roadmap-only functionality.
- [x] `docs/release_boundary.md` still excludes raw source snapshots, hidden
  labels, locked episodes, generated trajectories, run logs, credentials,
  machine-local paths, and model weights.
- [x] `release_manifest.json` and `huggingface/release_manifest.json` match the
  candidate release surface.
- [x] `release_decision_packet.json` says `candidate_pending_human_approval`.
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
- [ ] The candidate is committed to an exact reviewed source commit.
- [ ] GitHub Actions `release-audit` is green for that exact commit.
- [ ] The Hugging Face package is built from that commit and its exact file set,
  source tree, byte sizes, and SHA-256 values are validated.
- [ ] The owner explicitly approves the exact candidate commit and package.
- [ ] The approved candidate is merged to public `main`.
- [ ] The approved package is uploaded and anonymous GitHub/Hub reads verify the
  source commit and upload manifest.

## Required Local Commands

```bash
python3 -m pip install -e ".[test]" -e ./benchmark build ruff
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

## Launch Decision Rule

The candidate may update the public release only when every candidate gate is
checked, every required command is green, the GitHub Actions release audit is
green for the exact commit, and the owner explicitly approves that commit and
its Hugging Face package.

If any release-boundary check regresses, hold the candidate and leave the 0.2.0
public baseline unchanged until the issue is fixed.
