# CTDBench v0.2 + Audited Sickle Cell Disease Vertical Slice

[![release-audit](https://github.com/jang1563/agentic-drug-discovery-system/actions/workflows/release-audit.yml/badge.svg?branch=main)](https://github.com/jang1563/agentic-drug-discovery-system/actions/workflows/release-audit.yml)
[![GitHub release](https://img.shields.io/github/v/release/jang1563/agentic-drug-discovery-system)](https://github.com/jang1563/agentic-drug-discovery-system/releases/latest)
[![Hugging Face dataset](https://img.shields.io/badge/Hugging%20Face-Dataset-FFD21E?logo=huggingface&logoColor=000)](https://huggingface.co/datasets/jang1563/clinical-trial-decision-benchmark)

Version 0.2.0 provides two concrete public artifacts: `ctdbench`, a reproducible
runner and scorer for the public
[clinical trial decision benchmark](https://huggingface.co/datasets/jang1563/clinical-trial-decision-benchmark),
and an audited, retrospective vertical slice spanning the end-to-end workflow
for sickle cell disease (SCD). Callable evidence adapters, verifier contracts,
and release checks make these artifacts inspectable and reproducible within
their stated scope.

The repository name reflects the longer-term research direction. The proposed
eight-stage, long-horizon agentic drug discovery system remains a
**roadmap and research scaffold**, not a completed public platform: seven of the
eight planned atlases do not yet have standalone public data, and the
demonstrated multi-stage flow currently covers only one disease–target slice.

## At a Glance

| Field | Value |
| --- | --- |
| Purpose | Build a verification-oriented, auditable decision environment for drug-discovery agents. |
| Release status | Public GitHub repository; Hugging Face dataset mirror built from an exact reviewed source commit. |
| Core control frame | Verify, defer, stop, or flag rather than silently advancing uncertain claims. |
| Not included | Raw source snapshots, hidden labels, locked episodes, generated trajectories, run logs, credentials, local paths, or model weights. |
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

Concretely, this repository provides a **retrospective clinical and regulatory decision benchmark
with source-derived labels (generated without human curation), plus one audited end-to-end vertical
slice**. It is not yet the full eight-stage trajectory atlas described in the roadmap. Honest status:

- **Built & audited:** source-derived label authority plus scoped construct-validity controls;
  callable tool/DB adapters
  (ClinicalTrials.gov, openFDA, Open Targets, ChEMBL, EMA EPAR) and multi-stage flow orchestrators;
  one disease/target slice (sickle cell) traversed retrospectively; an unscored
  prospective scaffold whose stale example is invalidated pending source refresh;
  conditional local RDKit druglikeness screening; and aggregate retrospective
  risk analysis. Local calibration cards and locked replay artifacts are excluded.
- **Roadmap (not yet built):** 7 of 8 atlases (compound/ADMET/target/structure/cell) hold no
  standalone data; the multi-stage flow is demonstrated on one disease; SFM (Boltz-2) scoring needs
  a GPU endpoint, while RDKit molprops runs locally when its dependency is installed.
- **Read the caveats first:** headline demo numbers are small-N and on one well-characterized disease;
  the 80/80 prompt result repeats the same eight assets and is a regression check, not independent
  validation. Do not read this as a finished long-horizon agent platform.

## Current Anchors

- `docs/`: design notes; `docs/12_scd_vertical_slice.md` is the audited SCD slice,
  `docs/13_target_id_governance_node.md` is the upstream target-node results card,
  and `docs/public_evidence_summary.json` is the aggregate claim ledger.
- `rl_env/specs/`: state, action, observation, and case-bank schema sketches.
- `adapters/`, `chains/`: callable adapters and flow orchestrators are implemented.
- `verifiers/`: public contracts and scaffold only; evaluator implementations remain outside the release boundary.

## Artifact Map

| Path | Audience | Purpose |
| --- | --- | --- |
| `docs/public_release_readiness_plan.md` | Humans | Public-readiness plan, gates, and boundary checklist. |
| `docs/public_launch_checklist.md` | Humans | Final private-to-public launch checklist and approval gates. |
| `docs/release_boundary.md` | Humans + reviewers | What can and cannot enter Git/HF release surfaces. |
| `docs/release_trust_report.md` | Humans + machines | Trust claims, evidence anchors, interpretation warnings, and HF package reproducibility path. |
| `docs/12_scd_vertical_slice.md` | Humans + reviewers | Caveats-first description of the audited SCD vertical slice. |
| `docs/13_target_id_governance_node.md` | Humans + reviewers | Small-N upstream target-identification results card. |
| `docs/public_evidence_summary.json` | Machines + reviewers | Aggregate-only metrics, provenance limits, and claim boundaries. |
| `benchmark/` | Users + CI | Installable scorer and tests for the linked external clinical-trial decision dataset. |
| `release_manifest.json` | Machines + reviewers | Canonical GitHub/HF release scope and required checks. |
| `release_decision_packet.json` | Machines + reviewers | Machine-readable public launch decision packet. |
| `huggingface/README.md` | Humans + HF Hub | Dataset card for the public Hugging Face mirror. |
| `huggingface/release_manifest.json` | Machines + reviewers | Hugging Face-specific include/exclude manifest. |
| `scripts/audit/` | CI + maintainers | Fail-closed release-boundary validators. |

## GitHub Boundary

The GitHub repo is a sanitized scaffold. Full case banks, raw source snapshots, evaluator-only labels, generated verifier results, run logs, machine-specific paths, and working research notes stay outside Git unless a separate release packaging step explicitly promotes an audited artifact.

Public-release readiness is tracked in:

- `docs/release_boundary.md` — what can and cannot enter Git history.
- `docs/release_trust_report.md` — trust claims, machine anchors, and interpretation warnings.
- `docs/12_scd_vertical_slice.md` — caveats-first audited SCD vertical slice.
- `docs/13_target_id_governance_node.md` — upstream target-node aggregate results.
- `docs/public_evidence_summary.json` — machine-readable aggregate claim ledger.
- `docs/public_release_readiness_plan.md` — current public GitHub readiness plan.
- `docs/public_launch_checklist.md` — final human launch checklist.
- `release_manifest.json` — machine-readable release boundary and required checks.
- `release_decision_packet.json` — machine-readable public launch decision packet.
- `codemeta.json` and `.zenodo.json` — machine-readable citation and archive metadata.
- `huggingface/` — Hugging Face Dataset-card package mirrored on the Hub.

Before release-surface changes, run:

```bash
python3 scripts/audit/github_release_file_audit.py
python3 scripts/audit/validate_hf_release_package.py
python3 scripts/audit/validate_public_launch_packet.py
python3 scripts/audit/validate_vertical_slice_doc.py
python3 -m pytest -q benchmark/tests
python3 scripts/audit/build_hf_release_package.py --output /tmp/agentic-hf-release-package --force
python3 scripts/audit/validate_hf_release_package.py --package /tmp/agentic-hf-release-package
git diff --check
python3 -m compileall adapters chains benchmark/src scripts/audit
```

## Immediate Use

Start with:

1. `PROJECT_BRIEF.md`
2. `docs/release_trust_report.md`
3. `docs/12_scd_vertical_slice.md`
4. `docs/13_target_id_governance_node.md`
5. `docs/public_evidence_summary.json`
6. `docs/00_problem_framing.md`
7. `docs/01_long_horizon_chain_design.md`
8. `docs/03_deterministic_soft_verifier.md`
9. `docs/04_rl_environment_design.md`
10. `docs/06_episode_label_ontology_v0.md`
11. `rl_env/specs/case_bank_schema_v0.md`

## Design Bias

This project should stay implementation-facing. Research notes are useful only insofar as they help define:

- state/action/observation schemas,
- verifier contracts,
- tool adapters,
- trajectory records,
- reward signals,
- compute-specific experiment plans.

## Release Posture

The public artifact presents a protocol, benchmark-control layer, and limited
decision-prototype surface—not a complete autonomous discovery or wet-lab
capability. The release surface favors schemas, audit scripts, adapters,
governance notes, and reproducible smoke paths. Raw clinical/regulatory
snapshots, hidden labels, generated trajectories, scheduler logs, machine paths,
credentials, and unpublished working notes remain outside the repository.

## License

Apache License 2.0. See `LICENSE`.
