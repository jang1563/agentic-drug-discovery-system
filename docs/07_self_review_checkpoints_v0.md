# Self-Review Checkpoints v0

Date: 2026-06-28

## Purpose

The atlas should grow through gated iterations. Each gate is designed to catch a different failure mode before episodes become training or evaluation data.

## Review Gates

### Gate 1. Source / Version Gate

Question:

- Is every evidence record tied to a source, version, snapshot, query date, and evidence date?

Fail if:

- a dynamic API result is cited without a query date;
- a release-based database is cited without a release number or download date;
- a visible packet mixes source versions without recording it.

### Gate 2. Time-Slice / Leakage Gate

Question:

- Could the agent see any evidence that would not have been available at `decision_date`?

Fail if:

- evaluator-only outcome evidence appears in the visible packet;
- post-decision regulatory status, label, publication, or structure data is visible;
- current database aggregates are used as historical evidence without cutoff handling.

### Gate 3. Entity Normalization Gate

Question:

- Are drug, disease, target, trial, structure, and cell entities normalized at the right granularity?

Fail if:

- brand/generic/salt/formulation ambiguity changes the case label;
- disease hierarchy expansion changes direct evidence into weak analogy;
- target family is treated as a specific target;
- cell line or organism mismatch is ignored.

### Gate 4. Evidence-Status / Probativeness Gate

Question:

- Does the label distinguish what the evidence proves from what merely sounds related?

Fail if:

- same pathway evidence is treated as same target evidence;
- no evidence is treated as negative evidence;
- negative evidence is overgeneralized across population, modality, endpoint, or disease context;
- weak assay evidence is treated as program-level proof.

### Gate 5. Verifier Contract Gate

Question:

- Can deterministic and soft verifiers score the episode without relying on the LLM's rationale?

Fail if:

- a hard verifier is only described as a natural-language judgment;
- the soft verifier target is not anchored to an evidence field;
- verifier outputs cannot be logged separately from the model response.

### Gate 6. Reward Hacking Gate

Question:

- Could an agent get high reward by copying citations, always deferring, always verifying, or optimizing a proxy?

Fail if:

- citation completeness dominates scientific correctness;
- defer is always safest;
- expensive verification is always rewarded;
- proxy scores can be improved while terminal decision quality worsens.

### Gate 7. Baseline Sufficiency Gate

Question:

- Is there a no-LLM or simple specialist baseline that makes the agent's added value measurable?

Fail if:

- no rule/retrieval/SFM-only baseline exists;
- the task is solved by exact lookup with no need for planning;
- the task is impossible because evaluator-only labels are not recoverable even with valid evidence.

### Gate 8. Split / Memorization Gate

Question:

- Can the case bank test process quality rather than name memorization?

Fail if:

- all cases are famous successes or failures;
- no anonymized or scrambled controls exist;
- no temporal/target/disease/scaffold/cell holdout split is planned.

## Review Cadence

- Per source addition: Gates 1 and 2.
- Per label batch: Gates 3 and 4.
- Per schema update: Gate 5.
- Per reward update: Gate 6.
- Per benchmark split: Gates 7 and 8.
- Before any model training or evaluation: all gates.
- Per objective checkpoint: record candidate, reconstructed, locked, registry, composition, and split/reward gaps against the current milestone target.

## Stability Rule

If a gate fails, do not patch the label only. Record whether the failure came from:

- source drift,
- entity ambiguity,
- time leakage,
- weak evidence,
- bad reward,
- missing baseline,
- schema insufficiency.

This lets the atlas improve instead of silently becoming cleaner-looking but less honest.
