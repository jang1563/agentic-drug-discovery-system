# Discovery Context Identity Continuity

Status: implemented in the 0.3.0.dev0 candidate

Scope: disease, assay, and model-system identity across the typed execution backbone

Evidence posture: synthetic public fixtures plus one payload-free external provider validation;
no scientific efficacy claim

## Why This Contract Exists

An end-to-end discovery program can preserve a target identifier and still drift into a different
disease, assay, organism, or experimental model. This contract makes those identities explicit in
`ProgramState` and requires evidence-backed links before a stage may advance.

The implemented identity graph is:

```text
DiseaseRecord
  -> TargetRecord
  -> CandidateRecord
  -> AssayRecord -> candidate-target functional evidence
  -> ModelSystemRecord -> candidate disease-model evidence
```

Promotion context may request a lookup, but it is not an identity authority. Accepted identity comes
from typed records linked to evidence that passed the deterministic verifiers.

## Typed Ledgers

| Record | Canonical key | Stable identity fields | Required evidence link |
| --- | --- | --- | --- |
| `DiseaseRecord` | `disease_id` | `name`, namespace bindings | At least one evidence event whose biological context carries the same `disease_id`. |
| `AssayRecord` | `assay_id` | `name`, `assay_type`, `target_id`, `disease_id`, `organism`, namespace bindings | A `candidate_target_functional_activity_supported` event linked to the same assay, target record, disease, organism, and known candidate. |
| `ModelSystemRecord` | `model_system_id` | `name`, `model_type`, `disease_id`, `organism`, namespace bindings | A `disease_model_effect_supported` event linked to the same model system, disease, organism, and known candidate. |

Every record has a `canonical` identifier equal to its ledger key. Additional namespace bindings may
be added, but an accepted binding cannot later be removed, rebound, or assigned to another record of
the same type.

The strict machine contract and a synthetic complete example are:

- `rl_env/specs/discovery_context_identity.schema.json`
- `rl_env/specs/discovery_context_identity.example.json`

## Stage Requirements

The default environment applies these requirements to `ADVANCE` packets:

1. Every stage requires one qualifying `DiseaseRecord` whose name matches `ProgramState.disease`.
2. At disease-context advance, the qualifying disease must be updated in the current packet and
   supported by evidence linked to the current unmet-need claim.
3. Target, candidate, and later records must continue to reference that disease identity.
4. Preclinical advance requires at least one qualifying `AssayRecord` and one qualifying
   `ModelSystemRecord` created or updated in the current packet.
5. The preclinical assay must link the qualifying candidate, target, disease, organism, and
   functional-effect evidence. The model system must link the qualifying candidate, disease,
   organism, and disease-model evidence.
6. Existing source-independence, cutoff, SHA-256, claim-support, target-namespace, and candidate
   viability gates still apply. Identity records do not replace scientific evidence.

`DEFER`, `HOLD`, `PIVOT`, and `KILL` do not need to satisfy advance readiness, but any identity
updates they carry still must pass continuity and evidence-link verification.

## Pinned Evidence Path

The dependency-free `PinnedEvidenceAdapter` validates payload-free manifest records before semantic
promotion. For the implemented preclinical profile:

- the functional record declares `candidate_id`, `target_id`, `target_record_id`, `disease_id`,
  `organism`, and `assay_id`, plus typed assay metadata, endpoint relation/value/unit, source assay
  classification, a functional-readout declaration, candidate aliases, and canonical lineage ids;
- the disease-model record declares `candidate_id`, `disease_id`, `organism`, and
  `model_system_id`, plus typed model-system metadata, exposure context, endpoint
  relation/value/unit, source candidate name, and canonical lineage ids;
- both records retain source version, observation date, availability date, and source-content
  SHA-256 without embedding the raw source payload;
- the semantic mapper checks the records against the accepted disease, target, and candidate ledgers
  before emitting evidence, a supported claim, and typed assay/model-system updates;
- the composite gate requires distinct source ids, distinct exact source bytes, and disjoint
  upstream publication lineages, while the disease-model source candidate must resolve through the
  functional record's declared aliases.

A mismatch returns a conservative promotion result and the stage runner recovers to an accepted
`DEFER` only when the configured recovery contract allows it. The state does not partially absorb
the mismatched identity.

## Fail-Closed Invariants

`ContextIdentityContinuityVerifier` blocks a transition when it detects any of the following:

- removal or core-field rebinding of an accepted disease, assay, or model system;
- removal or rebinding of an accepted namespace or supporting-evidence link;
- two records of one type claiming the same normalized namespace binding;
- packet updates stamped with a different stage;
- more than one canonical disease for one program, or a disease name/canonical-id mismatch;
- target or candidate disease links that leave the canonical disease ledger;
- assay links that disagree with the target, disease, organism, candidate, or evidence context;
- model-system links that disagree with the disease, organism, candidate, or evidence context.

Failures are returned under `context_identity_continuity_invalid`, with specific failure labels and
broken record ids in verifier details. Stage-readiness failures separately report
`disease_identity_missing`, `assay_identity_missing`, or `model_system_identity_missing`.

## Serialization And Replay

`DiseaseRecord`, `AssayRecord`, and `ModelSystemRecord` are included in:

- strict dictionary parsers and JSON round trips;
- `DecisionPacket` update sets;
- `ProgramState` immutable ledgers and lookup maps;
- semantic promotion and bounded stage/program aggregation;
- replay projection and exact final-state equality checks.

Unknown fields, malformed identifiers, duplicate ledger keys, missing referenced evidence, and
replay drift fail closed.

## Matched And Adversarial Coverage

- `tests/test_context_identity_continuity.py` covers strict example parsing, disease rebinding,
  assay namespace collision, unknown-candidate assay evidence, and model-system rebinding.
- `tests/test_pinned_evidence_adapter.py` includes a matched preclinical pair. The success arm keeps
  the assay-to-target-record link and advances; the failure arm changes only `target_record_id`,
  returns `pinned_functional_effect_record_mismatch`, and defers.
- The matched pair expects both decisions to be correct and balanced accuracy to equal 1.0. This is
  a deterministic contract test, not a measured discovery result.
- `tests/test_preclinical_provider_pair.py` joins synthetic sanitized ChEMBL functional-activity and
  PubMed disease-model outputs. Independent lineages advance; a counterfactual shared PubMed
  lineage defers with no partial evidence or identity update.

## Current Boundary

This implementation proves that the control plane can preserve typed identity and block selected
cross-context errors. It does not certify the truth of a source record, the biological relevance of
an assay or model, transferability across organisms, or candidate efficacy. Real public-source
provider jobs and scientifically release-approved manifests remain outside the public artifact.
One external ChEMBL/PubMed validation is documented payload-free in
`docs/20_preclinical_provider_ingestion.md`; it is a contract check, not an efficacy or performance
result. Clinical
intervention and trial continuity is implemented separately in
`docs/16_clinical_intervention_identity.md`; trial arm and population identity remain future work.

Run the relevant checks with:

```bash
python3 -m unittest tests.test_context_identity_continuity tests.test_pinned_evidence_adapter -v
python3 -m unittest discover -s tests -v
```
