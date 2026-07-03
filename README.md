# Agentic Drug Discovery System

Workspace for designing a long-horizon drug discovery agentic system that combines databases, tools, scientific foundation models, LLM agents, deterministic verifiers, soft verifiers, and RL-style feedback.

Scaffold date: 2026-06-27

## Core Question

Can a long-horizon discovery process be represented as an agentic environment where:

- intermediate states are explicit and queryable,
- tools and SFMs generate structured evidence,
- deterministic verifiers enforce hard constraints,
- soft verifiers score uncertainty, evidence quality, and scientific plausibility,
- success and failure trajectories become training/evaluation data,
- reward design can support RL or RLVR-style optimization?

## Current Anchors

- `docs/`: high-level design notes.
- `rl_env/specs/`: state, action, observation, and case-bank schema sketches.
- `rl_env/rewards/`: reward component sketches.
- `adapters/`, `chains/`, and `verifiers/`: scaffold directories for implementation.

## GitHub Boundary

The GitHub repo is a sanitized scaffold. Full case banks, raw source snapshots, evaluator-only labels, generated verifier results, run logs, machine-specific paths, and working research notes stay outside Git unless a separate release packaging step explicitly promotes an audited artifact.

Public-release readiness is tracked in:

- `docs/release_boundary.md` — what can and cannot enter Git history.
- `docs/public_release_readiness_plan.md` — current public GitHub readiness plan.
- `release_manifest.json` — machine-readable release boundary and required checks.
- `codemeta.json` and `.zenodo.json` — machine-readable citation and archive metadata.

Before pushing or changing visibility, run:

```bash
python3 scripts/audit/github_release_file_audit.py
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
