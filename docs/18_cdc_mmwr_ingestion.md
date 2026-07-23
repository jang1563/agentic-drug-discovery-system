# CDC MMWR Evidence Ingestion

Status: implemented in the 0.3.0.dev0 candidate

Scope: provider-specific disease-burden and treatment-gap extraction from captured CDC MMWR HTML

Scientific posture: deterministic extraction checks source identity and reviewer-selected evidence;
it does not infer claims or replace scientific review

## Why This Provider Is First

The generic pinned-source compiler proves that a summary is attached to exact captured bytes, but
it cannot prove that a reviewer copied a value from the declared article or section. The CDC MMWR
adapter closes that narrower gap for one authoritative public HTML format.

The first manually verified external fixture is CDC's Sickle Cell Data Collection report,
`Surveillance for Sickle Cell Disease - Sickle Cell Data Collection Program, Two States,
2004-2018`, DOI `10.15585/mmwr.ss7109a1`. The captured bytes and reviewer job remain outside Git and
Hugging Face. The repository ships only the extractor, schema, synthetic example, and deterministic
tests.

Official article: <https://www.cdc.gov/mmwr/volumes/71/ss/ss7109a1.htm>

## Bounded Flow

```text
captured CDC MMWR HTML bundle outside Git
  + reviewer-authored adds.cdc-mmwr-ingestion-job.v1
  -> article identity checks
     -> receipt id, canonical CDC URL/port, exact DOI-bound source version
     -> citation title, DOI, publication year, visible publication date
  -> evidence checks
     -> declared section id and exactly one matching excerpt
     -> exactly one selected numeric token
     -> numeric equality and explicit unit
     -> explicit geography and reference period
  -> payload-free adds.pinned-ingestion-job.v1
     -> provider/article/location metadata
     -> SHA-256 of the normalized excerpt, not the excerpt
  -> generic compile + mandatory review report
  -> PinnedEvidenceAdapter -> semantic promotion -> stage verifier
```

The provider adapter is intentionally not a general natural-language extractor. A human selects a
short evidence excerpt and typed value. The adapter checks that selection against the immutable
source and removes the excerpt before the generic job is written.

## Machine Contract

`rl_env/specs/cdc_mmwr_ingestion_job.schema.json` defines:

- one CDC MMWR article identity: title, DOI, publication date, and canonical URL;
- one captured `source_receipt_id` for every record in the job;
- either `disease_burden_supported` or `treatment_gap_supported`;
- a stable `disease_id` and `evidence_context_id`;
- population, geography, and reference period fields shared by the composite disease-context gate;
- burden value/type/unit or treatment-gap value/context/unit;
- reviewer-only `location_id`, `excerpt`, and `value_text` evidence fields.

The adjacent example is synthetic. It is safe for schema and wheel tests and makes no scientific
claim.

## CLI

First capture the HTML outside the repository using the generic command from
`docs/17_pinned_source_ingestion.md`. Then verify the provider job:

```bash
adds-pinned-ingestion extract-cdc-mmwr \
  --job /external/review/cdc_mmwr_job.json \
  --bundle /external/review/cdc_mmwr_bundle \
  --output /external/review/cdc_mmwr_generic_job.json
```

Compile the resulting generic job only after a human checks the typed summary:

```bash
adds-pinned-ingestion compile \
  --job /external/review/cdc_mmwr_generic_job.json \
  --bundle /external/review/cdc_mmwr_bundle \
  --bundle /external/review/independent_treatment_gap_bundle \
  --manifest-out /external/review/pinned_manifest.json \
  --review-out /external/review/pinned_manifest.review.json
```

The extraction output status is `provider_job_extracted_requires_human_review`. Its report includes
the captured source-content SHA-256 and sanitized output SHA-256. The later compiler review remains
`requires_human_review`; provider extraction does not grant release approval.

## Fail-Closed Checks

Extraction rejects:

- a receipt id, media type, canonical locator/port, exact DOI-bound source version, or
  publication-before-retrieval mismatch;
- missing or conflicting citation title, DOI, publication year, canonical URL, or visible date;
- a title, DOI, year, or canonical URL that differs from the reviewer job;
- an unsupported predicate, malformed date, post-publication availability claim, or non-finite
  value;
- a missing section, an excerpt that does not occur exactly once in one section block, or a
  selected numeric token that does not occur exactly once;
- a numeric value, unit, geography, or reference period not supported by the selected excerpt;
- reviewer attempts to pre-populate provider-owned provenance fields;
- generic raw-payload, local-path, chronology, or schema violations in the sanitized output.

The output retains article identity, section id, selected value text, and excerpt SHA-256. It does
not retain source HTML, the excerpt, local paths, credentials, or a source bundle.

## Stage And Evaluation Behavior

`tests/test_cdc_mmwr_ingestion.py` proves two matched control paths:

- a CDC MMWR burden record plus a separately captured, context-matched treatment-gap record compiles
  with two independent source contents and advances the bounded disease-context stage;
- burden and treatment-gap records extracted from the same MMWR bundle defer because one document
  cannot satisfy the two-source composite gate.

The success and failure arms share disease, stage, modality, population, endpoint family,
mechanism, and decision-time context. Both expected decisions are required for balanced accuracy
1.0. This is a deterministic control test, not a measured drug-discovery result.

## What This Proves

This provider path proves that a reviewer-selected CDC MMWR value can be bound to an exact captured
article, exact section, normalized excerpt hash, unit, geography, reference period, source receipt,
and downstream stage decision without publishing raw bytes.

It does not prove that the article is complete, that the chosen measure is clinically sufficient,
that two different documents are scientifically independent, that surveillance values generalize
outside the declared context, or that the resulting drug-discovery decision is correct. Those
remain reviewer and evaluation responsibilities.
