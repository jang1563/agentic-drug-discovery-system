# Target Identity Continuity

## Purpose

The executable core carries one canonical target identity from target nomination through
preclinical validation. A caller-provided symbol or ChEMBL id is not sufficient by itself.
Each accepted namespace binding is stored in a typed `TargetRecord`, linked to supporting
evidence, replayed through accepted decision packets, and checked by deterministic verifiers.

This is an identity and provenance contract. It does not establish target validity, mechanism
truth, efficacy, safety, or clinical utility.

## Canonical Record

`TargetRecord` contains:

| Field | Meaning |
| --- | --- |
| `target_id` | Stable canonical record id; the Open Targets mapper uses the Ensembl gene id. |
| `symbol` | Canonical gene symbol returned with the Open Targets target id. |
| `disease_id` | Explicit disease id used in the target-disease request. |
| `organism` | Explicit organism identity. |
| `stage` | Stage that most recently extended the record. |
| `identifiers` | Namespace-to-id bindings such as Ensembl, gene symbol, ChEMBL target, and UniProt. |
| `supporting_evidence` | Evidence ids supporting the accumulated identity bindings. |
| `attributes` | Structured source-specific profile metadata. |

The machine-readable shape is
`rl_env/specs/target_identity_record.schema.json`; the adjacent example is synthetic.

## Default Stage Requirements

| Stage | Required target namespaces | How the binding is obtained |
| --- | --- | --- |
| Target nomination | `ensembl_gene`, `gene_symbol` | Open Targets association payload with explicit disease id and organism. |
| Modality selection | `ensembl_gene`, `gene_symbol`, `chembl_target` | ChEMBL molecule, mechanism, and target profile agree on molecule id, target id, symbol, organism, and single-protein scope. |
| Candidate generation | Same as modality selection | Candidate resolves exactly one target record by `chembl_target`. |
| Lead optimization | Same as modality selection | Candidate update preserves the target link. |
| Preclinical validation | Same as modality selection | Candidate, target, disease, and pinned functional records resolve to the same target record. |

Target nomination requires both `target_identity_resolved` and
`target_disease_supported`. Modality selection requires both
`target_identity_continuous` and `modality_matches_mechanism`. The older
`molecule_mechanism_profile` observation remains available for compatibility, but it cannot
satisfy the default modality gate without the target-profile continuity evidence and target
record update.

## Fail-Closed Invariants

`TargetIdentityContinuityVerifier` blocks a transition when:

- a canonical target's symbol, disease, or organism changes;
- an accepted namespace binding is removed or rebound;
- accumulated target-support evidence is removed;
- a packet authors a target update at a stage other than the current stage;
- the canonical record id disagrees with its Ensembl binding or the symbol field disagrees with its gene-symbol binding;
- two target records claim the same normalized namespace binding;
- a candidate has a partial target link; or
- a candidate's target record, ChEMBL target, symbol, and disease do not resolve together.

Stage readiness separately requires a qualifying target record with the configured namespaces.
Target and modality advances must update that record in the current packet and link it to
current-stage support evidence. Candidate, lead, and preclinical advances require a viable
candidate linked to the qualifying target.

## Adapter Path

```text
Open Targets target_disease_association
  -> Ensembl id + symbol + disease id + organism
  -> TargetRecord(ensembl_gene, gene_symbol)
  -> ChEMBL molecule_target_mechanism_profile
  -> target profile symbol/organism/single-protein verification
  -> TargetRecord(+ chembl_target, optional unique UniProt accession)
  -> ChEMBL molecule identity
  -> CandidateRecord(target_record_id, target_chembl_id, target_symbol, disease_id)
  -> lead and pinned preclinical checks preserve the same link
```

The ChEMBL target-profile operation is unavailable when the supplied adapter does not expose a
structured `target(target_id)` method. Missing, ambiguous, malformed, or mismatched profiles do
not create evidence or namespace bindings.

## Verification Anchors

- `agentic_drug_discovery/models.py`: `TargetRecord`, state, packet, and replay ledgers.
- `agentic_drug_discovery/verifiers.py`: continuity and stage-readiness checks.
- `agentic_drug_discovery/promotion.py`: Open Targets, ChEMBL, candidate, and preclinical mappings.
- `adapters/execution_registry.py`: typed composite ChEMBL operation.
- `tests/test_target_identity_continuity.py`: rebinding, collision, broken-link, and matched
  symbol-match/symbol-mismatch coverage.
- `tests/test_pinned_evidence_adapter.py`: replayable disease-to-clinical synthetic path.

The matched target-symbol pair changes only the ChEMBL target profile's gene symbol. The matched
symbol arm advances and extends the target ledger; the mismatched arm defers without adding
evidence or a ChEMBL binding. This validates control behavior, not biological performance.
