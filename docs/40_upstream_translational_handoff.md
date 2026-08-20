# Upstream Cell-State and Perturbation Handoff

**Status:** Implemented public contract with synthetic validation

## Purpose

The translational handoff closes one structural gap between upstream cell-state or perturbation
research and the evidence-governed drug-discovery control plane. It accepts a reviewed,
payload-minimized record of biological context, source identity, assay design, endpoint, effect,
uncertainty, sampling, quality control, and interpretation. It then emits only contextual evidence
drafts for a later state-bound tool outcome.

This is a generic interface. It does not integrate a Biohub platform, dataset, API, model output,
or experimental workflow, and it does not claim affiliation or endorsement.

## Contract

Each handoff binds:

1. Program, hypothesis, disease, and target identities.
2. Perturbation identity, type, entity namespace, direction, modality, dose, and duration.
3. Species, tissue, cell type, model system, and disease context.
4. One or more source-versioned observations with content hashes and lineage identifiers.
5. Assay, platform, comparator, endpoint identity, unit, effect scale, interval, and optional
   p-value.
6. Observation, replicate, and optional donor counts.
7. Quality-control checks, limitations, reviewer interpretation, conflicts, and uncertainty.
8. Independent-replication source identities with pairwise-disjoint declared lineages.
9. An immutable contextual-only decision boundary and canonical profile hash.

The JSON Schema is
[`rl_env/specs/translational_handoff.schema.json`](../rl_env/specs/translational_handoff.schema.json).
The public example is
[`rl_env/specs/translational_handoff.example.json`](../rl_env/specs/translational_handoff.example.json).

## Fail-Closed Semantics

The semantic validator rejects:

- duplicate JSON keys, non-finite numbers, unknown fields, and malformed identifiers;
- source availability after handoff creation or observation after availability;
- source or disease-context rebinding;
- assay, endpoint, or comparator identifier rebinding;
- effect intervals that do not contain their estimate, non-positive ratio-scale intervals, or
  effect-direction labels that contradict the estimate;
- unknown replication sources, a single claimed replication source, or shared declared lineage;
- omitted human review, relaxed non-claim boundaries, or a mismatched canonical integrity hash.

Validation does not prove the truth of a supplied source hash or reviewer statement. Real inputs
still require the existing source-capture and review process.

## Compilation Boundary

`compile_translational_handoff_evidence` emits one `EvidenceDraft` per observation with:

- relation fixed to `contextualizes`;
- predicate fixed to `upstream_perturbation_observation`;
- explicit disease, target, perturbation, species, tissue, cell, model, assay, endpoint, and
  comparator context;
- source hash and lineage, effect interval, sample structure, QC, review status, and handoff hash;
- a mandatory human-review marker and the complete prohibited-inference set.

It emits no `ScientificClaim`, assay gate, mechanism claim, efficacy claim, safety claim, clinical
readiness claim, or treatment recommendation. A downstream scientific gate therefore requires a
separate reviewed semantic mapper and independent evidence.

## Use

```bash
adds-translational-handoff validate

adds-translational-handoff summarize

adds-translational-handoff compile \
  --request-id synthetic-demo-request

python3 scripts/audit/validate_translational_handoff.py
```

## What This Advances

| Dimension | Improvement | Remaining limitation |
|---|---|---|
| Quality | Strict schema, semantic invariants, integrity hash, adversarial tests | Source bytes and reviewer truth remain external |
| Usability | One CLI supports validate, summarize, and compile | No graphical authoring or external-user study |
| Breadth | Adds a generic M6 cell-state/perturbation entry surface | M2, M3, and M5 atlases remain incomplete |
| Depth | Retains effect uncertainty, sample structure, QC, lineage, and replication | No causal transport, mechanistic validation, or real-program outcome |

## Next Research Decision

The next meaningful step is not to add more synthetic fields. It is to select one independently
reviewed, non-sensitive immune or inflammatory use case and test whether its upstream evidence can
be represented without identity loss, unsupported promotion, or reviewer ambiguity. That fixture
should remain external until scientific ownership, data rights, and release approval are explicit.
