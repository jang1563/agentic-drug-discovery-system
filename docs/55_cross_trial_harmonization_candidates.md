# Cross-Trial Endpoint Harmonization Candidates

Status: implemented and covered by synthetic adversarial tests

Scope: two or more exact ClinicalTrials.gov registry-record inventory packets to a complete,
bounded, provenance-preserving review graph containing every posted-outcome pair across distinct
trials and each trial's safety context.

## Research Role

The registry-record inventory prevents early endpoint omission within one study. The next failure
mode occurs when multi-trial review begins: an analyst may compare only familiar primary outcomes,
silently discard outcomes with incomplete fields, or detach safety data from the source snapshot
used for endpoint review.

This layer creates the high-recall review universe before semantic harmonization. It projects every
posted outcome from each exact inventory, retains its within-trial lexical reconciliation status,
and enumerates the Cartesian product for every pair of distinct trials. A trial with no posted
outcomes still contributes a source-bound safety context and an explicit zero count.

## Exact Input Contract

The spec binds each input using:

- `inventory_id`
- canonical NCT ID
- complete inventory packet SHA-256
- a fixed harmonization policy ID
- a positive `max_endpoint_candidate_count` no larger than 100,000
- a positive `max_pair_count` no larger than 100,000

Bindings must be unique, ordered by NCT ID, and contain no more than 256 trials. The compiler
accepts exactly that set of strict inventory packets, independent of command-line order. Source
receipt IDs and source-content hashes must be distinct across trials; a repeated snapshot cannot
masquerade as independent trial evidence.

The compiler computes

```text
expected_pair_count = sum(n_i * n_j for every trial pair i < j)
```

before allocating any endpoint or pair records. The total posted-endpoint count is checked against
its independent bound first. If either result exceeds its bound, compilation fails without
sampling, truncation, or partial output.

## Three-Layer Packet

### Trial Safety Context

One context per inventory retains the inventory, receipt, content, and source-scope hashes;
registry/source version and locator; results, protocol-outcome, posted-outcome, and adverse-event
module presence; protocol/posted/link counts and available safety time-frame metadata; and
source-ordered references to every safety group, serious event, and other event. Each reference
keeps its source JSON pointer, record hash, category, and event-stat count.

This is trial-level context only. It does not assert that a safety event belongs to an endpoint,
that risk windows are comparable, or that an intervention caused an event.

### Posted Endpoint Candidate

Every posted outcome retains source order, pointer, record hash, registry fields, group and
measurement structure, population-description hash, source receipt/content hashes, and its safety
context identity. All within-trial exact lexical links and protocol-outcome references are carried
forward, including `unmatched` and `ambiguous_exact_candidates` states.

### Cross-Trial Pair Candidate

For each endpoint pair, the packet records normalized exact-equality diagnostics for title, time
frame, outcome type, reporting status, parameter type, dispersion type, unit, and population
description hash. Missing left/right fields are explicit sorted codes. Safety time-frame equality
is separate from endpoint diagnostics.

Mechanical status is one of:

- `all_mechanical_fields_equal`
- `mixed_mechanical_fields`
- `incomplete_source_fields`

These labels organize review workload only. Even all-field equality does not approve endpoint
identity, endpoint family, estimand equivalence, clinical comparability, or safety comparability.

## Integrity And Replay

Strict readers reject unknown fields, duplicate JSON keys, non-finite constants, invalid hashes,
noncanonical binding or candidate order, repeated source identities, count changes, missing or
extra Cartesian pairs, rebound source pointers, pair-reference changes, diagnostic changes, fixed
nonclaim changes, and envelope-hash mismatch.

`validate_clinicaltrials_gov_harmonization_candidates` recompiles the entire graph from the exact
input inventory packets. The packet verifies inventory integrity but does not replay raw source
bundles; upstream `validate_clinicaltrials_gov_inventory` remains required when source bytes are
available.

## CLI

```bash
adds-pinned-ingestion compile-clinicaltrials-gov-harmonization-candidates \
  --spec /external/review/harmonization.spec.json \
  --inventory /external/review/NCT00000001.inventory.json \
  --inventory /external/review/NCT00000002.inventory.json \
  --output /external/review/harmonization.candidates.json
```

Repeat `--inventory` once per exact trial packet. The output is a reviewer queue, not an approved
mapping or synthesis input. Human review must still adjudicate endpoint identity, ontology,
estimand, population, analysis, risk window, and safety comparability before downstream mapping or
benefit-risk compilation. `--max-bytes` bounds the combined inventory-packet bytes before full
compilation; trial, endpoint, and pair counts have separate contract bounds.

## Test Boundary

`tests/test_clinicaltrials_gov_harmonization_candidates.py` builds three synthetic inventories with
2, 3, and 0 posted outcomes. It verifies all six cross-trial pairs, zero-outcome trial retention,
present-empty versus absent result modules, within-trial ambiguity, missing fields,
safety-window disagreement, bounded-work failure,
source-disjointness, strict schemas/readers, rehashed diagnostic tampering, full replay, and CLI
execution.

The repository includes no real inventory set, endpoint harmonization decision, safety
adjudication, pooled effect, benefit-risk result, or treatment recommendation.
