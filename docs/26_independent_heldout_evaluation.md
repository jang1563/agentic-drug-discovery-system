# Independently Curated Held-Out Evaluation

Date: 2026-07-24

Status: executable synthetic development contract; no real independently curated result yet

Public payload policy: protocol commitments, implementation, JSON Schemas, synthetic examples,
aggregate stage metrics, and limitations may be public. Real curator identities, affiliation and
attestation source documents, votes, rationales, evidence snapshots, adjudications, label vaults,
submissions, and per-episode scores remain external.

## Purpose

`agentic_drug_discovery/heldout_evaluation.py` adds a preregistered layer around the existing
cutoff-safe board and label vault. It answers two questions that the first retrospective board
could not:

1. Was the cohort, label policy, curator roster, stage composition, and metric policy fixed before
   scoring?
2. Does the aggregate report preserve exact denominators and uncertainty separately for each
   discovery stage?

The contract can reject an invalid evaluation package. It cannot prove that an attestation is
truthful or that a curated label is scientifically correct.

## Artifact Flow

1. `HeldoutEvaluationProtocol` is registered before board creation. It binds the board identity,
   cohort-specification hash, label/exclusion guidance hashes, opaque curator-roster commitment,
   consensus rule, outcome window, stage minima, coverage rule, and confidence level.
2. `seal_heldout_evaluation_board` creates the existing role-neutral board and external vault, then
   embeds the exact protocol id and fingerprint in policy-visible board metadata.
3. `HeldoutCurationManifest` opens the roster commitment inside the evaluator boundary. It records
   opaque curator declarations, affiliation commitments, evidence/rationale hashes, votes, final
   labels, and any independent adjudication.
4. Fingerprint-bound policy submissions are frozen against the board.
5. `evaluate_stage_stratified_submissions` validates every prior artifact and emits only aggregate
   overall and predeclared stage strata.

## Fail-Closed Curation

Validation requires:

- at least the preregistered number of policy-blinded, conflict-free curators;
- unique curator ids and unique affiliation commitments within each episode;
- curator declarations at or before protocol registration;
- votes only after the decision cutoff plus the preregistered outcome window;
- board-bound submissions no later than the curation freeze, with one submission per policy/version;
- exact board, vault, protocol, roster, episode, and final-label bindings;
- unanimous, strict-majority, or disagreement-triggered adjudication exactly as preregistered;
- an adjudicator who neither voted on the episode nor shares a voter affiliation commitment;
- complete curation coverage with no missing or extra episode.

Opaque commitments preserve the audit relation without publishing working identities. External
identity and conflict documentation still requires human governance.

## Stage Metrics

Every rate carries its event count, denominator, estimate, confidence level, and Wilson score
interval. A zero denominator is represented by `null`, not zero.

| Metric | Numerator | Denominator |
|---|---|---|
| Exact accuracy | Exact gold-decision matches | All episodes; missing is incorrect |
| Success/failure arm accuracy | Exact matches in that arm | Episodes in that arm |
| Both-correct rate | Pairs with both episodes exact | Matched pairs |
| Action coverage | Predictions other than missing or explicit `defer` | All episodes |
| Selective risk | Incorrect action-covered predictions | Action-covered episodes |
| Defer rate | Explicit `defer` predictions | All episodes |
| Unsafe-advance rate | `advance` against non-advance gold | Non-advance-gold episodes |

The Wilson intervals describe finite-board sampling uncertainty. Episode-level intervals do not
adjust for dependence within matched pairs or uncertainty in curator labels; the pair-level
both-correct rate and exact counts remain available for interpretation. These limitations are
required fields in every machine-readable report rather than optional prose.

The report separately flags whether each stage meets its pair minimum and whether each policy
meets the preregistered minimum action-covered episode count. It does not rank policies or choose a
winner.

## Machine Contracts

| Artifact | Visibility | Contract |
|---|---|---|
| Preregistered protocol | Public | `rl_env/specs/heldout_evaluation_protocol.schema.json` |
| Curation manifest | Evaluator only | `rl_env/specs/heldout_curation_manifest.schema.json` |
| Stage-stratified report | Aggregate public after review | `rl_env/specs/stage_stratified_evaluation_report.schema.json` |

The protocol and aggregate report have adjacent synthetic examples. No vote-level curation
example is published, so the default repository surface models that artifact as evaluator-only.
Strict readers reject unknown fields, duplicate JSON keys, non-finite values, unsupported schema
versions, integrity drift, noncanonical ordering, and recomputed metric inconsistency.

## Synthetic Development Board

`tests/test_heldout_evaluation.py` executes four matched pairs and eight episodes across target
nomination and clinical strategy. It covers:

- protocol-before-board binding and stage minimum enforcement;
- strict-majority curation and independent adjudication;
- uncommitted roster, insufficient majority, and early-vote rejection;
- governed, always-advance, and defer-safe stage metrics;
- zero-coverage selective-risk handling;
- Wilson interval recomputation;
- all three JSON Schemas and strict envelope round trips;
- exact checked-in protocol and aggregate-report examples.

These labels and metrics are synthetic contract tests, not benchmark evidence.

## Current Boundary

The previously published four-pair real retrospective aggregate remains unchanged. This module
does not retroactively make that board independently curated or sufficiently powered. The next
scientific milestone is to register a real protocol, recruit and attest independent curators,
freeze a larger multi-stage board, collect blinded labels, and publish only a separately reviewed
aggregate report.
