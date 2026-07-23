# Typed Policy Replanning and Resume

Status: implemented as a deterministic control-plane layer in the 0.3.0.dev0 candidate

Public payload policy: schemas, code, synthetic tests, and claim boundaries may be public; real
checkpoints and policy-run artifacts remain outside Git until separately sanitized and approved

## Purpose

The original `BoundedProgramRunner` executes a fixed ordered tuple of stage plans and stops at the
first blocked or non-advance result. That behavior remains unchanged. This layer adds an explicit,
typed control loop above it so a program can:

1. observe a committed `DEFER`, `HOLD`, or `PIVOT`, or a fail-closed blocked stage;
2. select only a predeclared replacement plan through a deterministic rule;
3. preserve the complete state, execution ledger, queue mutation, and policy decision;
4. stop after configured rule and global revision limits; and
5. serialize a hash-bound checkpoint and resume from the exact cursor later.

Replanning cannot manufacture evidence, alter an accepted packet, skip transition verifiers, or
turn a pause into an `ADVANCE`. Every replacement step still passes the existing planner, tool
contract preflight, semantic mapper, packet construction, deterministic verifiers, state commit,
budget accounting, and replay checks.

## Execution Model

```text
PolicyCheckpoint(READY)
  -> execute exactly one ProgramStep with BoundedProgramRunner
  -> ADVANCE
       -> consume the next declared step, or EXHAUSTED
  -> COMPLETED / KILL
       -> terminal checkpoint with an empty queue
  -> DEFER / HOLD / PIVOT / BLOCKED
       -> ReplanObservation
       -> ordered BoundedReplanPolicy rules
       -> ReplanDirective(REPLAN)
            -> append or replace with predeclared ProgramStep values
            -> READY checkpoint
       -> ReplanDirective(PAUSE)
            -> PAUSED or BLOCKED checkpoint
```

The policy runner invokes one plan at a time. This makes every checkpoint boundary align with one
complete `BoundedProgramRun`, rather than saving an uncommitted partial transition.

## Typed Contracts

| Record | Bound information |
| --- | --- |
| `ReplanObservation` | Program/state version, current stage/status, program and stage-run codes, accepted non-advance decision if any, blocking verifier codes, consumed plan, and remaining plan ids. |
| `ReplanRule` | Exact stage, eligible run statuses/codes/decisions, required blocking codes, action, predeclared replacement steps, queue-preservation behavior, and application limit. |
| `ReplanDirective` | Policy id/version, matched rule, monotonic revision index, observation SHA-256, action, reason code, and exact replacement steps. |
| `ReplanRecord` | Observation, directive, prior queue, and resulting queue. |
| `PolicyCheckpoint` | Full committed `ProgramState`, cumulative `ToolExecutionLedger`, pending steps, consumed plan ids, append-only replan history, invocation count, disposition, and parent-checkpoint SHA-256. |
| `PolicyDrivenProgramRun` | Every single-step bounded run bracketed by its input and output checkpoints. |

The machine envelope is `rl_env/specs/policy_checkpoint.schema.json`. Embedded program state and
execution-ledger objects are then parsed by the existing strict native parsers; the JSON Schema is
not a substitute for those executable invariants.

## Deterministic Policy Semantics

`BoundedReplanPolicy` evaluates rules in declared order. A rule matches only when all declared
dimensions match. Replacement steps are concrete `ProgramStep` records, not free text or generated
code. The first replacement stage must equal the rule stage.

The policy returns `PAUSE` when:

- no rule matches;
- the matching rule reached its application limit;
- the global replan limit was reached;
- a replacement would reuse a consumed plan id; or
- runtime policy identity or observation binding fails.

`PAUSE` preserves the remaining queue but marks the checkpoint non-ready. Calling the runner again
does not silently continue it; a non-ready checkpoint returns without invoking a tool. Scientific
termination still requires an accepted `KILL` packet from the normal stage path.

## Checkpoint Integrity and Resume

`policy_checkpoint_to_json()` wraps the complete checkpoint in:

```json
{
  "schema_version": "adds.policy-checkpoint-envelope.v1",
  "integrity_sha256": "<canonical checkpoint SHA-256>",
  "checkpoint": {}
}
```

The parser rejects duplicate JSON keys, non-finite numbers, unknown fields, malformed nested plan
records, invalid program or execution history, changed queue/history identities, and integrity-hash
mismatch. Resume additionally requires the caller to supply the expected checkpoint fingerprint and
requires exact policy id/version equality. Every emitted checkpoint stores the previous checkpoint
fingerprint, while `PolicyDrivenProgramRun` verifies the complete state, ledger, plan-consumption,
invocation-count, and append-only history chain.

The SHA-256 envelope is an integrity and identity mechanism, not a digital signature. A trusted
caller must retain the expected fingerprint (or bind it in a signed outer manifest) before resume;
an attacker who can replace both a checkpoint and its expected token is outside this contract.

## Verified Controls

`tests/test_policy_replanning.py` covers:

- a low-confidence target result that commits `DEFER`, selects a predeclared fallback target plan,
  advances on the second plan, and exactly replays both accepted packets;
- one-invocation checkpointing, JSON round trip, and later deterministic resume;
- JSON Schema validation of the checkpoint envelope;
- payload tampering and stale resume-token rejection;
- policy-id/version mismatch rejection;
- consumed plan-id reinsertion rejection; and
- a repeated `DEFER` loop stopped by the global replan limit.

Run the focused checks with:

```bash
python -m unittest tests.test_policy_replanning -v
python -m unittest tests.test_agent_loop tests.test_program_runner -v
```

## Release Boundary and Limitations

- Real checkpoints can contain complete tool payloads, local run context, or evidence not approved
  for release. `policy_checkpoints/` and `policy_runs/` are ignored by Git.
- The shipped policy is deterministic and rule-based. It is evaluation infrastructure for policy
  comparison, not an LLM planner and not a learned policy.
- Replacement plans must already be typed and reviewed. Dynamic plan generation, policy training,
  calibration, sealed evaluation, and operator reauthorization of a paused checkpoint remain
  separate milestones.
- Resume proves execution and state continuity. It does not prove that source evidence is true or
  that a scientific recommendation is clinically valid.
