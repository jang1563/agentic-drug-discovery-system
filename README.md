# Agentic Drug Discovery System

Release-gated research scaffold for long-horizon drug-discovery decision environments. The project combines tool/database adapters, scientific foundation-model interfaces, LLM policy seams, deterministic verifiers, soft scientific verifiers, and RL-style feedback design.

Scaffold date: 2026-06-27

## At A Glance

| Field | Value |
| --- | --- |
| Purpose | Build a verified, auditable decision environment for drug-discovery agents. |
| Release status | Public GitHub repository with a public Hugging Face Dataset mirror. |
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

This is, concretely, a **retrospective clinical/regulatory decision benchmark with source-derived
(no-human) labels plus one validated end-to-end vertical slice** — not yet the full 8-stage
trajectory atlas the roadmap describes. Honest status:

- **Built & validated:** source-derived label authority + enforced construct validity (a masked
  agent surface kills a no-reasoning structural-tell shortcut); callable tool/DB adapters
  (ClinicalTrials.gov, openFDA, Open Targets, ChEMBL, EMA EPAR) and multi-stage flow orchestrators;
  one disease/target slice (sickle cell) traversed end-to-end in both retrospective and a prospective
  decision-support demo; a calibration card (conformal/RCPS) and a hash-pinned locked replay set.
- **Roadmap (not yet built):** 7 of 8 atlases (compound/ADMET/target/structure/cell) hold no
  standalone data; the multi-stage flow is demonstrated on one disease; SFM (Boltz-2) scoring needs
  a GPU endpoint.
- **Read the caveats first:** headline demo numbers are small-N and on one well-characterized disease;
  autonomous tool-use is higher-variance than the curated pipeline. Do not read this as a finished
  long-horizon agent platform.

## Current Anchors

- `docs/`: design notes; `docs/11_full_flow_retrospective_and_prospective_plan.md` is the current plan.
- `rl_env/specs/`: state, action, observation, and case-bank schema sketches.
- `adapters/`, `chains/`, `verifiers/`: **implemented** — callable adapters + flow orchestrators + verifiers (not just scaffold).

## Artifact Map

| Path | Audience | Purpose |
| --- | --- | --- |
| `docs/public_release_readiness_plan.md` | Humans | Public-readiness plan, gates, and boundary checklist. |
| `docs/public_launch_checklist.md` | Humans | Final private-to-public launch checklist and approval gates. |
| `docs/release_boundary.md` | Humans + reviewers | What can and cannot enter Git/HF release surfaces. |
| `release_manifest.json` | Machines + reviewers | Canonical GitHub/HF release scope and required checks. |
| `release_decision_packet.json` | Machines + reviewers | Machine-readable public launch decision packet. |
| `huggingface/README.md` | Humans + HF Hub | Dataset card for the public Hugging Face mirror. |
| `huggingface/release_manifest.json` | Machines + reviewers | Hugging Face-specific include/exclude manifest. |
| `scripts/audit/` | CI + maintainers | Fail-closed release-boundary validators. |

## GitHub Boundary

The GitHub repo is a sanitized scaffold. Full case banks, raw source snapshots, evaluator-only labels, generated verifier results, run logs, machine-specific paths, and working research notes stay outside Git unless a separate release packaging step explicitly promotes an audited artifact.

Public-release readiness is tracked in:

- `docs/release_boundary.md` — what can and cannot enter Git history.
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
git diff --check
python3 -m compileall adapters chains scripts/audit
```

## Immediate Use

Start with:

1. `PROJECT_BRIEF.md`
2. `docs/00_problem_framing.md`
3. `docs/01_long_horizon_chain_design.md`
4. `docs/03_deterministic_soft_verifier.md`
5. `docs/04_rl_environment_design.md`
6. `docs/06_episode_label_ontology_v0.md`
7. `rl_env/specs/case_bank_schema_v0.md`

## Design Bias

This project should stay implementation-facing. Research notes are useful only insofar as they help define:

- state/action/observation schemas,
- verifier contracts,
- tool adapters,
- trajectory records,
- reward signals,
- compute-specific experiment plans.

## Release Posture

The public artifact should present a protocol and benchmark-control layer, not a capability release. The release surface should favor schemas, audit scripts, adapters, governance notes, and reproducible smoke paths. Raw clinical/regulatory snapshots, hidden labels, generated trajectories, scheduler logs, machine paths, credentials, and unpublished working notes remain outside the repository.

## License

Apache License 2.0. See `LICENSE`.
