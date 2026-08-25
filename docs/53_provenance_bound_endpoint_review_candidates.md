# Provenance-Bound Endpoint Review Candidates

Status: implemented with identity-closed synthetic controls

Scope: exhaustive pre-review enumeration of ClinicalTrials.gov-derived endpoint, population, and
safety records without endpoint-family, ontology, estimand, comparability, or safety approval

## Research Question

Can the system prepare a complete, reviewer-readable evidence packet before human endpoint-family
review without silently making the semantic decisions that the reviewer is supposed to make?

The implemented answer is yes. A packet is compiled from an exact `ProgramState` snapshot and an
explicit sorted set of `TrialDesignRecord` ids. It retains every population, endpoint, and safety
record in that scope, including mechanically excluded records, and binds every retained record to
its visible source evidence and source-content SHA-256 values.

Completeness is relative to those committed design records. This module does not reopen raw
ClinicalTrials.gov bytes or recover outcomes omitted by upstream ingestion. The implemented
registry-record-wide inventory in `docs/54_clinicaltrials_gov_registry_record_inventory.md`
enumerates protocol, posted-result, and safety arrays before endpoint selection. This downstream
packet still cannot reconstruct an upstream omission and must be interpreted relative to its
committed design set.

## Boundary

This module sits before `ClinicalEndpointMappingRecord`:

```text
ClinicalTrials.gov-derived ProgramState
  -> exhaustive provenance-bound review candidates
  -> external scientific review
  -> separately declared approved endpoint mapping
  -> non-pooled benefit-risk synthesis
```

Candidate enumeration never reads endpoint mappings already present in the state and cannot emit
one. The packet fixes all of the following to `false`:

- reviewer approval performed;
- endpoint family assigned;
- ontology mapping approved;
- estimand equivalence inferred;
- clinical comparability inferred;
- comparative safety inferred;
- benefit-risk synthesis performed; and
- treatment choice inferred.

## Exhaustive Partition

The spec names candidate, intervention, disease, and the exact design-id set. Compilation verifies
that every design and trial remains identity-continuous with those ledger records.

For each selected design, the compiler retains:

| Record | Mechanical candidate rule | Excluded record remains visible as |
| --- | --- | --- |
| Endpoint | `reporting_status=posted` | `reporting_status_not_posted` |
| Safety | posted and `event_category=serious` | one or both exact reason codes |
| Population | referenced by at least one posted endpoint | `not_referenced_by_posted_endpoint` |

Outcome type is preserved but is not an eligibility filter. A posted secondary or otherwise named
endpoint therefore cannot disappear because a downstream synthesis currently accepts only primary
endpoints. This is a high-recall review boundary, not a synthesis eligibility decision.

Among mechanically eligible records, the packet enumerates:

1. every unordered endpoint pair within each design, exactly `n * (n - 1) / 2`; and
2. every endpoint-by-serious-safety relationship candidate within each design, exactly the
   Cartesian product of those eligible sets.

No pair or link is selected as preferred. Structural facts remain diagnostic.

## Provenance and Replay

Each source event retains evidence id, source id, source version, locator, content hash, observation
date, and availability date. Each population, endpoint, and safety record retains its exact support
ids, source-content hashes, and a canonical record SHA-256. Population descriptions and endpoint
names remain readable; the population description also carries its own digest.

The compiler rejects missing evidence, non-support relations, evidence after the state cutoff, and
unpinned source content. The packet binds the full spec and full `ProgramState` fingerprints.
`validate_clinical_endpoint_review_candidate_packet` recompiles the complete packet from state and
requires byte-equivalent typed content.

Strict JSON readers reject duplicate keys, unknown fields, non-finite constants, integrity
mismatches, noncanonical ordering, inconsistent derived counts, rebound eligibility status, and
attempts to set any semantic nonclaim to `true`.

## Structural Diagnostics

Endpoint pairs expose population identity/hash equality, endpoint time-frame equality, treatment
phase equality, phase-population alignment-hash equality, shared source hashes, and deterministic
heterogeneity codes. A structural match does not establish a shared estimand or clinical
comparability.

Endpoint-safety links replay `validate_phase_bound_population_alignment` and report one of:

- `phase_bound_alignment_valid`;
- `legacy_phase_undeclared`; or
- `population_alignment_invalid`.

The link preserves both time frames, both phase/alignment declarations, exact arm ids, source
hashes, and raw serious-event arm counts. Alignment does not approve a causal relationship, common
risk window, comparative safety claim, or benefit-risk interpretation.

## Synthetic Results

The identity-closed two-design control contains one primary and one secondary endpoint per design.

| Quantity | Result |
| --- | ---: |
| Selected designs | 2 |
| Retained endpoint records | 4 |
| Endpoint review candidates | 4 |
| Retained population records | 2 |
| Serious-safety candidates | 2 |
| Same-design endpoint pairs | 2 |
| Endpoint-safety candidate links | 4 |

Matched population/time-frame controls remain structural matches. Changed endpoint population and
time frame remain two heterogeneous pair diagnostics. A phase-rebound endpoint remains in the
packet with `population_alignment_invalid`; it is not silently dropped. Non-posted endpoint,
non-serious safety, and unreferenced population controls remain in explicit excluded partitions.

These are contract results, not estimates of reviewer recall, mapping accuracy, clinical utility,
or drug-discovery performance.

## Public Contracts

- `agentic_drug_discovery/clinical_endpoint_review_candidates.py`
- `rl_env/specs/clinical_endpoint_review_candidate_spec.schema.json`
- `rl_env/specs/clinical_endpoint_review_candidate_packet.schema.json`
- `tests/test_clinical_endpoint_review_candidates.py`

Real review packets, reviewer notes, source payload bytes, and approved mappings remain external to
the repository.

## Verification

```bash
python -m unittest tests.test_clinical_endpoint_review_candidates -v
python -m unittest discover -s tests -v
```
