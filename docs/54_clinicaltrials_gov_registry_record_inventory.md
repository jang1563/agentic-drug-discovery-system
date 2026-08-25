# ClinicalTrials.gov Registry-Record-Wide Inventory

Status: implemented and covered by synthetic adversarial tests

Scope: one exact ClinicalTrials.gov API v2 study snapshot to a provenance-bound, pre-review
inventory of every protocol outcome, posted outcome, safety group, serious event, other event, and
group-level event statistic present in the bounded source arrays.

## Why This Layer Exists

The strict trial-design provider in `clinicaltrials_gov.py` verifies a reviewer-authored selection
of one posted primary endpoint, one analysis, one arm pair, one population, and one serious-event
summary. The downstream endpoint-review candidate packet is exhaustive over committed
`TrialDesignRecord` values, but it cannot recover outcomes that never entered those records.

This inventory moves completeness checking in front of endpoint selection. It reads the exact raw
study bundle and retains all source-array entries before any endpoint-family, estimand, ontology,
comparability, or safety judgment. The official ClinicalTrials.gov structure distinguishes
protocol primary, secondary, and other outcomes from posted result outcome measures and adverse
events; those arrays are therefore enumerated independently rather than joined by position. See the
[official study data structure](https://clinicaltrials.gov/data-api/about-api/study-data-structure)
and [API description](https://clinicaltrials.gov/data-about-studies/learn-about-api).

## Trust Boundary

The compiler accepts only:

1. A strict inventory spec binding `inventory_id`, source receipt, NCT ID, registry version, and
   fixed policy ID.
2. A verified `SourceBundle` whose SHA-256, byte size, media type, exact HTTPS locator, source ID,
   source version, retrieval time, source `nctId`, and source `versionHolder` agree.

Raw JSON remains in the external immutable bundle. The public packet contains bounded registry
fields needed for review, field-presence flags, JSON pointers, source-order indices, per-record
hashes, the source receipt identity, and a hash of the complete outcome/safety source scope.
Descriptions, population descriptions, event notes, and module descriptions are represented only
by SHA-256.

ClinicalTrials.gov refreshes data regularly and changed its data ingest in August 2025, including
the representation of some markup fields. Exact snapshot receipt and record hashes therefore bind
replay to bytes rather than assuming stable formatting across registry revisions.

## Inventory Contract

| Source scope | Retained packet structure |
|---|---|
| `protocolSection.outcomesModule.primaryOutcomes` | every measure, time frame, source index, pointer, description hash, and record hash |
| `secondaryOutcomes` | every entry, including names that duplicate or conflict with other outcomes |
| `otherOutcomes` | every entry without promotion or exclusion |
| `resultsSection.outcomeMeasuresModule.outcomeMeasures` | every posted record with type/title/window/status/unit metadata, group IDs, denominator/measurement group IDs, analysis group sets, structural counts, pointer, and record hash |
| `adverseEventsModule.eventGroups` | every group and available serious/other affected and at-risk aggregate |
| `seriousEvents` and `otherEvents` | every term plus available organ-system/assessment metadata and every group-level affected/at-risk/event count |

Module-presence booleans distinguish a genuinely absent module from a present module containing an
empty array. Source order is retained. Missing optional registry fields become explicit `null`
values; entries are not silently dropped because a review field is absent.

## Lexical Reconciliation

Protocol and posted outcomes remain separate records. The compiler emits candidate links only when
case-folded, whitespace-collapsed title and time-frame text are exactly equal. It emits all such
links, then assigns each side one of:

- `unmatched`
- `unique_exact_candidate`
- `ambiguous_exact_candidates`

Outcome type agreement is a diagnostic boolean, not a link requirement or an approval. No fuzzy
matching, synonym expansion, ontology lookup, endpoint-family inference, or index-based join is
performed. A unique exact lexical candidate is still not endpoint identity or semantic
equivalence.

## Integrity And Replay

The JSON readers reject unknown fields, duplicate keys, non-finite constants, incorrect schemas,
rebound source IDs, noncanonical NCT/version/locator values, invalid pointers, duplicate record
identities, broken link references, inconsistent link/count partitions, altered fixed nonclaims,
and envelope hash mismatches. `validate_clinicaltrials_gov_inventory` recompiles the complete
packet from the exact bundle and spec; any source-field, record-hash, pointer, count, or packet
change yields a deterministic mismatch.

The following packet fields are fixed:

- `full_source_array_enumeration_performed = true`
- `exact_lexical_reconciliation_only = true`
- reviewer approval, endpoint selection, endpoint-family assignment, ontology approval, estimand
  equivalence, clinical comparability, comparative safety, benefit-risk synthesis, and treatment
  choice are all `false`

## CLI

Capture the raw source outside every Git worktree, then compile the inventory:

```bash
adds-pinned-ingestion capture \
  --url https://clinicaltrials.gov/api/v2/studies/NCT00000001 \
  --receipt-id ctgov-NCT00000001-2025-01-01 \
  --source-id clinicaltrials-gov-NCT00000001 \
  --source-version clinicaltrials-gov-NCT00000001-version-2025-01-01 \
  --output /external/immutable/ctgov-NCT00000001

adds-pinned-ingestion extract-clinicaltrials-gov-inventory \
  --spec /external/review/NCT00000001.inventory-spec.json \
  --bundle /external/immutable/ctgov-NCT00000001 \
  --output /external/review/NCT00000001.inventory.json
```

The output is a review input, not a generic ingestion job and not a committed trial design. A
reviewer must still resolve endpoint identity, choose the bounded analysis/population/arms, author
the strict ClinicalTrials.gov ingestion job, and pass the existing provider and promotion gates.

## Test Boundary

`tests/test_clinicaltrials_gov_inventory.py` adds secondary, duplicate lexical, unmatched, and other
adverse-event records to the synthetic study. It verifies complete two-sided partitions, exact
pointers and hashes, group-level counts, absent-module visibility, strict schemas/readers, rehashed
tampering, source drift, duplicate/non-finite source JSON rejection, CLI execution, and isolated
wheel coverage.

The tests prove deterministic contract behavior on synthetic inputs only. This repository includes
no real source bundle, real inventory packet, endpoint adjudication, safety review, clinical claim,
or treatment recommendation.
