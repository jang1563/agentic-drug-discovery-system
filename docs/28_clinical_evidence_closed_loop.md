# Clinical Evidence Closed Loop

## Purpose

The clinical evidence tensor and bounded-VOI planner identify policy-relative
gaps and select a bounded batch of evidence actions. This layer carries that
plan through the existing execution core and proves what changed afterward.

The closed loop is deliberately narrower than an autonomous clinical agent:

1. compile exact selected actions into state-bound tool calls;
2. execute them through registered contracts and explicit semantic mappers;
3. commit provider observations without allowing providers to decide;
4. run bounded reviewer-verifier transformations;
5. recompile a new clinical evidence tensor from the committed state;
6. prove each resolved gap is linked to new action-bound source provenance.

`ADVANCE` still means evidence-workflow readiness only. It is not a treatment,
regulatory, clinical acceptability, or terminal development recommendation.

## State Machine

```mermaid
flowchart LR
    A["Committed state and HOLD decision package"] --> B["Exact execution batch"]
    B --> C["ToolRequest and ToolOutcome"]
    C --> D["Explicit semantic promotion"]
    D --> E["Verifier-gated acquisition commit"]
    E --> F["Reviewer-only mapping refresh"]
    F --> G["Reviewer-only synthesis refresh"]
    G --> H["Recompiled tensor and bounded-VOI plan"]
    H --> I["Integrity-bound transition package"]
```

Provider output cannot bypass semantic promotion, the standard decision packet,
or deterministic state verifiers. The closed-loop compiler consumes accepted
state transitions; it does not write directly to a `ProgramState`.

## Preregistered Bounds

`ClinicalClosedLoopPolicy` declares:

- maximum reviewer refresh runs;
- maximum reviewer refresh actions;
- maximum reviewer refresh cost;
- committed-run requirement;
- reviewer-verifier-only refresh requirement;
- source-rejoin requirement for gap resolution;
- single-use attempted action identifiers;
- provider decision prohibition;
- terminal decision prohibition.

Every safety boundary is mandatory in v1. A policy cannot disable one by
setting it to `false`.

## Exact Execution Batch

`compile_clinical_execution_batch` accepts only:

- a non-terminal, replay-valid committed `ProgramState`;
- a decision package that recompiles exactly from that state;
- a `HOLD` plan with at least one selected action;
- a closed-loop policy registered no later than the program cutoff;
- a state stage identical to the evidence tensor stage.

Each `ClinicalEvidenceExecutionCall` binds:

- selected rank, action id, action fingerprint, and selection fingerprint;
- targeted gap codes and exact gap ids;
- tool id, operation, action type, purpose, arguments, and maximum cost;
- a deterministic call id derived from batch id, rank, and action id.

`clinical_execution_stage_plan` translates this batch into the existing
`StagePlan` contract. It fixes both successful and failed execution to
non-moving `HOLD` or `DEFER` decisions and embeds the package, tensor, plan, and
closed-loop policy fingerprints in stage-plan metadata.

## Execution

`execute_clinical_evidence_batch` recompiles the batch before invoking the
existing `BoundedStageRunner`. The runner still controls:

- contract registration and allowed stage;
- stale-state and terminal-state checks;
- step and budget bounds;
- replay-ledger duplicate prevention;
- provider invocation;
- operation-specific semantic promotion;
- packet assembly;
- all standard continuity and readiness verifiers;
- accepted-only state commit.

A successful provider outcome remains an observation. It can enter the evidence
ledger only through an explicit `EvidenceDraft` produced by a registered mapper.
The acquisition commit cannot change stage or terminate the program.

## Compact Receipts

`ClinicalToolOutcomeReceipt` excludes the provider payload while retaining:

- request id, state version, fingerprint, arguments, and timestamps;
- tool operation, contract id, action type, and cost bounds;
- outcome status, execution mode, payload SHA-256, and error code;
- exact provider-declared sources or the canonical payload-hash fallback;
- accepted packet id, action-ledger id, and promoted evidence ids.

Every receipt source requires a lowercase SHA-256 content hash. The action
ledger id must equal the deterministic request id, and unsuccessful outcomes
cannot claim promoted evidence. External validation resolves every promoted
evidence id in the committed ledger and verifies its exact source against the
receipt.

`ClinicalSelectedActionReceipt` adds the bounded-VOI action and targeted-gap
binding. `ClinicalRefreshRunReceipt` records a subsequent committed refresh run
and accepts only successful `RUN_VERIFIER` outcomes under a non-terminal
`HOLD`.

## Reviewer Refresh

Clinical endpoint mappings and benefit-risk syntheses are append-only. New
evidence therefore does not mutate an old mapping or synthesis. The expected
refresh path is:

1. commit the selected provider observation;
2. register a new reviewer-approved endpoint mapping when the selected trial
   set or exact safety binding changes;
3. compile a new source-ledger synthesis under that mapping;
4. keep every refresh run at the same stage with decision `HOLD`;
5. compile the after-package from the final committed synthesis.

The closed-loop policy bounds the number, action count, and aggregate cost of
these governance transformations. The acquisition commit cannot directly add
endpoint mappings or benefit-risk syntheses. A changed after synthesis must
appear in a committed reviewer refresh packet. Each refresh must append at
least one mapping or synthesis and may carry its bound evidence and claims; it
cannot update disease, target, candidate, assay, model-system, intervention,
trial, or trial-design ledgers.

## Source Rejoin

Let:

- `B` be source hashes in the before tensor;
- `A` be source hashes in the after tensor;
- `R` be source hashes declared by successful selected-action receipts;
- `P` be source hashes on evidence actually promoted by those receipts.

The compiler records:

```text
added_source_content_hashes   = A - B
removed_source_content_hashes = B - A
```

It then requires:

```text
(A - B) subset_of P subset_of R
```

For every resolved gap code, at least one successful selected action must:

1. target that exact gap code; and
2. promote evidence whose source hash is present in `A - B`.

A changed synthesis with no new action-bound source hash fails closed. This
prevents an after tensor from claiming that a selected action resolved a gap
when the new evidence came from an unplanned source or from no source at all.

## Single-Use Actions

Every attempted selected action id is removed from the after-package catalog.
An unexecuted suffix remains available when execution stops on a required
failure. Repeating an attempted semantic invocation requires a newly reviewed
catalog action id and therefore a new fingerprint.

This v1 behavior prevents silent retry loops. Retry policies, transient-error
classes, and attempt counters require a separately preregistered contract.

## Transition Package

`ClinicalEvidenceTransitionPackage` includes:

- before and after state versions;
- the closed-loop policy and exact execution batch;
- complete before and after clinical decision packages;
- selected-action and refresh receipts;
- accepted packet ids;
- consumed and remaining action ids;
- resolved, persisted, and new gap codes;
- added and removed source hashes;
- acquisition, refresh, total, and budget-delta accounting;
- before and after workflow decisions;
- mandatory interpretation limitations.

Construction validates internal relationships.
`validate_clinical_evidence_transition` additionally checks both committed state
ledgers, history prefixes, acquisition and refresh packet metadata, accepted
packet and action order, promoted-evidence source binding, budget delta, batch
recompilation, and after-package recompilation.

The public envelope binds the canonical transition with SHA-256. Strict readers
reject:

- missing or unknown fields;
- unsupported schema versions;
- duplicate JSON keys;
- non-finite numeric values;
- malformed hashes, dates, datetimes, or enums;
- integrity mismatches;
- any constructor-level provenance or budget invariant failure.

## Synthetic End-to-End Control

The compiler-generated public example begins with:

- two selected source-disjoint trials;
- one open `insufficient_independent_trials` gap;
- one selected action to verify a captured third trial;
- decision `HOLD`.

The bounded cycle commits:

- one provider verification action costing `0.05`;
- one reviewer endpoint-mapping verifier costing `0.01`;
- one reviewer synthesis verifier costing `0.01`.

The after tensor contains three exact trial cells, the third trial source hash
is present in the successful selected-action receipt, the gap is resolved, the
attempted action is consumed, and the after decision is `ADVANCE` in the
evidence-workflow-only sense.

Public artifacts:

- `rl_env/specs/clinical_evidence_closed_loop_transition.schema.json`
- `rl_env/specs/clinical_evidence_closed_loop_transition.example.json`

The synthetic example integrity SHA-256 is:

```text
3996c8157a8cd404db46d41c57ae6068afdfdeef0df66c28d0a30bcedb454e31
```

## Failure Matrix

| Condition | Result |
|---|---|
| Before package does not replay from state | Batch compilation rejected |
| State is terminal or stage differs from tensor | Batch compilation rejected |
| Tool contract, state version, step, or budget preflight fails | No provider invocation |
| Provider fails or mapper rejects | Observation is not promoted; run can only defer or hold |
| Acquisition directly adds a mapping or synthesis | Transition compilation rejected |
| Acquisition changes stage or terminates | Transition compilation rejected |
| Refresh uses a non-verifier action | Transition compilation rejected |
| Refresh appends no governed artifact or changes another identity ledger | Transition compilation rejected |
| Refresh exceeds run, action, or cost bounds | Transition compilation rejected |
| After synthesis is not exactly committed | Transition compilation rejected |
| New tensor hash is absent from successful action receipts | Transition compilation rejected |
| Resolved gap lacks targeted source rejoin | Transition compilation rejected |
| Attempted action remains in after catalog | Transition compilation rejected |
| State history, action metadata, evidence metadata, or budget is altered | External validation fails |

## Release Boundary

The public repository and Hugging Face candidate may contain:

- implementation;
- strict schema and readers;
- synthetic provider fixtures;
- compiler-generated synthetic transition example;
- deterministic and adversarial tests;
- documentation.

Real closed-loop policies, action batches, provider requests or outcomes,
receipts, reviewer refresh records, before/after tensors, and transition
packages can expose program strategy, source lineage, thresholds, costs, and
trial-level data. They remain outside both release surfaces pending separate
scientific, privacy, security, and release-boundary approval.

## Not Yet Claimed

This layer does not provide:

- live production provider credentials or provider-specific retry policy;
- calibrated action-resolution probabilities;
- calibrated economic value of information;
- causal attribution of serious adverse events;
- patient-level reanalysis or cross-trial pooling;
- autonomous endpoint ontology adjudication;
- clinical, regulatory, or treatment recommendations;
- evidence that the workflow improves prospective drug-development outcomes.
