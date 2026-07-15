# Clinical Portfolio Ingestion and Endpoint Mapping

## Purpose

This milestone connects multiple independently reviewed ClinicalTrials.gov snapshots to one
reviewer-approved endpoint-family identity. It adds two inspectable boundaries:

1. an all-or-nothing portfolio extraction over exact external source bundles; and
2. an append-only endpoint mapping ledger that synthesis must reference by `mapping_id`.

The implementation does not retrieve ontology records, infer mappings from endpoint names, pool
trial estimates, or make a clinical benefit-risk judgment.

## Public Contracts

| Artifact | Role |
| --- | --- |
| `clinicaltrials_gov_ingestion_job.schema.json` | Existing strict review contract for one exact study snapshot. |
| `clinicaltrials_gov_portfolio_job.schema.json` | Exact set of single-trial job, receipt, trial, design, endpoint, and safety references. |
| `clinical_endpoint_mapping.schema.json` | Reviewer, review time, endpoint family, ontology identity, and ordered exact bindings. |
| `clinical_benefit_risk_synthesis.schema.json` | Non-pooled synthesis selection that must name the committed mapping. |

All adjacent examples are synthetic. Raw source bytes, real review jobs, and local paths remain
outside the repository.

## Portfolio Transaction

The portfolio extractor receives three inputs:

- one portfolio declaration;
- the complete set of referenced single-trial review jobs; and
- the complete set of referenced external `SourceBundle` directories.

It verifies the full input set before writing output:

```text
portfolio declaration
  + exact set of single-trial jobs
  + exact set of external source bundles
  -> normalize every single-trial job
  -> match job, receipt, NCT, design, endpoint, and safety ids
  -> match candidate, intervention, and disease ids to the mapping
  -> verify every source receipt and exact source payload
  -> require mapping approval at or after every source retrieval
  -> require pairwise-distinct source-content SHA-256 values
  -> run every strict ClinicalTrials.gov extractor
  -> emit one payload-free generic ingestion job
```

A missing or extra job, missing or extra bundle, duplicate receipt, duplicate source-content hash,
identity rebound, or any single-trial extraction failure aborts before the output artifact is
written. The output records retain only typed summaries, linked receipt metadata, portfolio and
mapping ids, and an explicit `automatic_endpoint_mapping_performed=false` flag.

## Reviewer-Approved Mapping

`ClinicalEndpointMappingSpec` contains identities and review declarations, not source measurements:

- `mapping_id` and `portfolio_id`;
- candidate, intervention, and disease ids;
- canonical endpoint-family id and human label;
- reviewer-declared ontology system, version, code, and label;
- fixed v1 effect and safety measures;
- ordered trial/design/endpoint/safety bindings; and
- `review_status=approved`, reviewer id, and timezone-aware review time.

Only `review_note` and `review_protocol_id` are accepted as optional metadata. Fields such as effect
estimates or participant counts cannot be smuggled into mapping metadata.

The ontology identity is preserved exactly, but `ontology_authority_verified=false` remains
machine-readable. A reviewer may cite an external controlled terminology; this implementation does
not claim that it contacted, resolved, or validated that authority.

## Ledger Promotion

The local `clinical_synthesis/register_endpoint_mapping` operation normalizes the reviewed spec.
The approval timestamp must precede the tool request. The semantic mapper then recompiles every
binding from committed `TrialDesignRecord` objects and
creates:

- one `ClinicalEndpointBindingRecord` per selected trial;
- one append-only `ClinicalEndpointMappingRecord`;
- one `clinical_endpoint_mapping_approved` evidence event; and
- one claim limited to mapping availability and reviewer approval.

Each binding retains endpoint and safety fingerprints, source evidence ids, and source-content
hashes. Approval must occur on or after every selected evidence availability date. The mapping
record requires pairwise source-disjoint trials and begins its
`supporting_evidence` list with the canonical source-evidence union, followed by exactly one derived
approval event.

`ClinicalEndpointMappingContinuityVerifier` blocks:

- direct mapping commits without the bound approval event;
- mapping-id reuse or rebound;
- committed mapping mutation or removal;
- endpoint, safety, source, reviewer, ontology, or context changes; and
- packet/state update-set mismatch.

Committed-history replay independently checks that the mapping ledger equals accepted packet
history.

## Synthesis Dependency

`ClinicalSynthesisSpec.endpoint_mapping_id` is mandatory. Before reading trial measurements, the
synthesis compiler requires:

1. that mapping id to exist in the current ledger;
2. the mapping to recompile exactly;
3. candidate, intervention, disease, endpoint family, effect, safety, and stage dimensions to match;
4. the ordered synthesis selections to equal the complete approved binding set; and
5. source-content hashes to remain pairwise disjoint.

The resulting `BenefitRiskSynthesisRecord`, derived evidence event, and replay metadata all retain
the mapping id. Removing the mapping or changing one selected endpoint therefore invalidates the
synthesis rather than silently falling back to endpoint-name similarity.

## Commands

Capture each source snapshot outside Git and author one strict single-trial job per bundle. Then run:

```bash
python -m agentic_drug_discovery.ingestion_cli \
  extract-clinicaltrials-gov-portfolio \
  --job /external/review/portfolio.json \
  --trial-job /external/review/trial-a.json \
  --trial-job /external/review/trial-b.json \
  --bundle /external/review/bundle-a \
  --bundle /external/review/bundle-b \
  --output /external/review/portfolio-extracted.json

python -m agentic_drug_discovery.ingestion_cli compile \
  --job /external/review/portfolio-extracted.json \
  --bundle /external/review/bundle-a \
  --bundle /external/review/bundle-b \
  --manifest-out /external/review/portfolio-manifest.json \
  --review-out /external/review/portfolio-review.json
```

The portfolio job's `endpoint_mapping` object is separately submitted to the local mapping tool
after all referenced trial designs are committed. Synthesis is submitted only after that mapping
transition is accepted.

## Verification

`tests/test_clinical_portfolio.py` covers JSON Schema validation, strict round trips, two-bundle
payload-free extraction, source disjointness, generic manifest compilation, incomplete input sets,
identity rebound, measurement-metadata rejection, and CLI no-output behavior on failed preflight.

`tests/test_clinical_benefit_risk_synthesis.py` covers the full sequence:

```text
two exact trial designs
  -> reviewer-approved mapping tool and mapper
  -> mapping transition, serialization, and replay
  -> mapping-gated non-pooled synthesis
  -> synthesis transition, serialization, and replay
```

Negative controls cover missing mapping, selection mismatch, source overlap, direct mapping and
synthesis commits, forged values, unrelated support, automatic pooling, and committed-ledger
removal.

## Current Release Status

The executable contract and all public examples are synthetic. No real multi-trial portfolio,
reviewer approval, or ontology authority resolution is release-approved in this repository.
`StageGate.minimum_benefit_risk_synthesis_records` therefore remains `0` by default. Enabling it for
a real program requires an independently reviewed, context-matched portfolio and the corresponding
external source bundles.
