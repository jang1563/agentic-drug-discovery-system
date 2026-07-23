# Cutoff-Safe Matched and Sealed Policy Evaluation

Date: 2026-07-23

Status: executable development contract plus one external real retrospective board

Public payload policy: schemas, implementation, synthetic tests, aggregate metrics, hashes, and
limitations may be public. Full real observations, cached episode packets, label vaults,
commitment nonces, per-episode scores, source bytes, review jobs, and local paths remain external.

## Purpose

`agentic_drug_discovery/sealed_evaluation.py` turns complete matched episodes into two artifacts:

1. a policy-visible board with cutoff-safe state, a sanitized cached tool packet, an opaque
   episode id, a role-neutral pair index, and a salted label commitment;
2. an evaluator-only vault with arm assignment, gold decision, failure causes, metadata, and the
   commitment nonce.

The split prevents a rollout policy from reading its answer from the serialized observation.
`success` and `failure` describe contract-complete and controlled contract-failure trajectories;
they do not mean a drug succeeded or failed clinically.

## Fail-Closed Bindings

Each observation enforces:

- exact disease, stage, modality, population, endpoint family, target/mechanism, and time-bin match;
- `visible_state.as_of_date == decision_cutoff`;
- no state evidence after the cutoff;
- no evaluator-only keys in state, board metadata, cached packet, or submission metadata;
- a cached-packet availability date at or before the decision cutoff;
- board creation at or after every episode cutoff and submission creation at or after board
  creation;
- exact SHA-256 verification of the embedded label-free cached packet;
- runtime-validated opaque HMAC-derived episode, pair, packet, program, and label identifiers;
- canonical episode, pair, label, and prediction ordering for stable artifact fingerprints;
- a salted label commitment that must open against the separately stored vault.

Each policy submission covers every observation exactly and binds every prediction to the exact
observation fingerprint and board fingerprint. Non-empty predictions require explicit confidence;
missing, stale, duplicate, or extra identities fail closed.

## Machine Contracts

| Artifact | JSON Schema |
|---|---|
| Role-neutral board | `rl_env/specs/sealed_evaluation_board.schema.json` |
| Evaluator label vault | `rl_env/specs/sealed_evaluation_vault.schema.json` |
| Policy submission | `rl_env/specs/policy_evaluation_submission.schema.json` |
| Aggregate comparison report | `rl_env/specs/policy_evaluation_report.schema.json` |

The reference implementation also validates semantic invariants that JSON Schema alone cannot
express, including cutoff chronology, ProgramState history consistency, commitment opening, exact
board coverage, pair arm balance, and observation fingerprint binding. Strict `from_dict` and
`from_json` readers round-trip all four envelopes and reject duplicate JSON keys, non-finite
values, unknown fields, unsupported schema versions, integrity drift, and canonical-identity
changes.

## Development Board

`tests/test_sealed_evaluation.py` is the public development board. Its two synthetic matched pairs
exercise:

- deterministic, role-neutral sealing;
- label and source-id leakage removal;
- commitment tamper rejection;
- stale observation fingerprint rejection;
- explicit-confidence enforcement;
- complete-submission enforcement;
- strict typed envelope round-trip and JSON tamper rejection;
- governed, always-advance, and defer-safe comparison;
- all four public JSON Schemas.

These synthetic labels are intentionally visible to developers and are not a benchmark result.

## External Real Board

The external board was sealed before aggregate scoring from four matched pairs and eight episodes
drawn from the source-pinned senicapoc and PALOMA execution paths. The bounded controls isolate:

- complete versus missing clinical corroboration;
- approved versus unapproved candidate alias continuity;
- approved versus unapproved disease-context continuity;
- source-disjoint versus content-hash-overlapping multi-trial endpoint mapping.

The positive PALOMA path also re-executed non-pooled PFS/serious-event synthesis and retained
`source_disjoint=true` and `pooling_performed=false`.

| Policy | Exact | Success arm | Failure arm | Both-correct pairs | Unsafe advance |
|---|---:|---:|---:|---:|---:|
| Deterministic gated output | 8/8 | 4/4 | 4/4 | 4/4 | 0/7 |
| Always advance, counterfactual | 1/8 | 1/4 | 0/4 | 0/4 | 7/7 |
| Defer safe, counterfactual | 4/8 | 0/4 | 4/4 | 0/4 | 0/7 |

The constant policies are evaluator baselines only. They have no transition authority and cannot
bypass deterministic gates. Top-label Brier and ECE values are emitted as diagnostics, but eight
episodes cannot support a calibration claim.

The public aggregate and exact payload-free hashes are in
`docs/retrospective_policy_evaluation_snapshot.json`.

## Verification

```bash
python -m unittest tests.test_sealed_evaluation -v
python -m unittest tests.test_matched_evaluation tests.test_policy_replanning -v
python -m ruff check agentic_drug_discovery/sealed_evaluation.py tests/test_sealed_evaluation.py
```

The external run additionally verified every artifact against its SHA-256 manifest, validated the
board, vault, three submissions, and report against their public schemas, scanned the policy board
for evaluator fields and source pair names, and reproduced the full package in an independent
deterministic rerun.

## Claim Boundary

This result establishes a working provenance and control-flow evaluation surface. It does not
establish discovery performance, policy optimality, confidence calibration, clinical
acceptability, or prospective utility. The next valid expansion is a larger independently curated
held-out board with predeclared label policy and enough episodes for stage-stratified uncertainty
analysis.
