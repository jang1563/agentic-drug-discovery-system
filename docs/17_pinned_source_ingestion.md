# Pinned Public-Source Ingestion

Status: implemented in the 0.3.0.dev0 candidate

Scope: exact source capture, payload-free evidence compilation, and bounded-stage integration

Scientific posture: compilation verifies provenance and structure; every summary still requires
human scientific review

## Why This Path Exists

The pinned-evidence adapter previously consumed a valid manifest but did not create one or prove
that its declared SHA-256 matched source bytes. The ingestion path now connects an exact external
snapshot to a public summary without putting the raw snapshot in Git or Hugging Face.

```text
public HTTPS response or reviewed local snapshot
  -> immutable external source bundle
     -> receipt.json + payload.bin
     -> exact byte-size and SHA-256 verification
  -> reviewer-authored ingestion job
  -> strict compiler
     -> payload-free adds.pinned-evidence.v1 manifest
     -> adds.pinned-ingestion-review.v1 report
  -> PinnedEvidenceAdapter
  -> typed tool outcome -> semantic promotion -> deterministic stage gate
```

Source capture and scientific interpretation are deliberately separate. The compiler never infers
burden, treatment gap, functional activity, or disease-model effect from arbitrary text.

## Machine Contracts

| Contract | Schema | Purpose |
| --- | --- | --- |
| Source receipt | `rl_env/specs/source_receipt.schema.json` | Exact source id, immutable version, public locator, SHA-256, byte size, retrieval time, media type, and transport metadata. |
| Ingestion job | `rl_env/specs/pinned_evidence_ingestion_job.schema.json` | Reviewer-authored record summaries linked by `source_receipt_id`; no source path or raw payload. |
| Review report | `rl_env/specs/pinned_evidence_ingestion_review.schema.json` | Manifest hash, receipt/record map, distinct-content count, source-id/content-hash reuse warnings, deterministic checks, and mandatory review status. |
| Final manifest | `rl_env/specs/pinned_evidence_manifest.schema.json` | Existing payload-free records consumed by `PinnedEvidenceAdapter`. |

The adjacent source-receipt and ingestion-job examples are synthetic contract fixtures.

## Capture

Capture a public HTTPS source directly:

```bash
adds-pinned-ingestion capture \
  --url https://public.example.org/versioned/source.json \
  --receipt-id burden-2024-receipt \
  --source-id public-burden-source \
  --source-version snapshot-2024-06-15 \
  --output /external/review/burden-2024
```

Capture an already reviewed local snapshot while retaining a public citation locator:

```bash
adds-pinned-ingestion capture \
  --input-file /external/raw/source.json \
  --locator https://public.example.org/versioned/source.json \
  --receipt-id burden-2024-receipt \
  --source-id public-burden-source \
  --source-version snapshot-2024-06-15 \
  --retrieved-at 2024-06-15T12:00:00Z \
  --output /external/review/burden-2024
```

The output directory is immutable and contains exactly `receipt.json` and `payload.bin`. The CLI
refuses to write this raw bundle anywhere inside a Git worktree. HTTPS capture rejects credentials
and signed-token query variants in URLs, non-HTTPS redirects, non-200 responses, empty payloads,
and payloads above the configured size limit. Local capture rejects symlinks, invalid size limits,
and bounded-read overflows, and records no local input path in the receipt.

`source_version` is caller-declared and must identify an immutable revision. Terms such as
`latest`, `current`, `unknown`, and `unpinned` are rejected, but the tool cannot prove that an
external publisher's version label is truly immutable.

## Compile

Create a reviewer-authored job that binds each summary to a receipt id, then run:

```bash
adds-pinned-ingestion compile \
  --job reviewed_ingestion_job.json \
  --bundle /external/review/burden-2024 \
  --bundle /external/review/treatment-gap-2024 \
  --manifest-out /external/review/pinned_manifest.json \
  --review-out /external/review/pinned_manifest.review.json
```

Compilation fails closed when:

- a receipt is unknown, duplicated, unused, malformed, or conflicts with another receipt using the
  same `source_id`;
- source bytes no longer match the receipt byte size or SHA-256;
- an evidence availability date follows source retrieval;
- the final pinned-evidence record contract is invalid;
- summary fields contain normalized raw-payload keys, machine-local paths, non-finite numbers,
  unsupported values, text over 4096 characters, or a record over 64 KiB;
- either output file already exists unless explicit replacement is requested; both paths are
  preflighted before the first file is written, and each file replacement is atomic.

The review report always has `status: requires_human_review`. A green compiler result proves byte
identity, chronology consistency, schema validity, and selected release-boundary checks. It does not
prove that a source is authoritative, a summary faithfully represents the source, two source ids
are scientifically independent, or the evidence supports efficacy.

`independent_source_count` is deliberately conservative: it counts distinct verified content
hashes, not labels. Reusing exact bytes under different `source_id` values is recorded in
`reused_content_hashes`, emits a warning, and cannot satisfy a composite independence gate. Distinct
bytes still do not prove scientific independence, so reviewer judgment remains mandatory.

## Control-Plane Integration

`normalize_pinned_evidence_manifest()` is now a shared core validator used by both the compiler and
`PinnedEvidenceAdapter`. Directly supplied manifests therefore receive the same raw-field, local
path, size, chronology, source, and predicate validation as compiler output.

`tests/test_pinned_evidence_ingestion.py` covers:

- strict receipt/job example parsing and immutable bundle round trips;
- source-byte tampering, false chronology, credential and signed-token locators, obfuscated
  raw-payload keys, non-finite values, and invalid bounded-read limits;
- compilation into an adapter-readable manifest and deterministic review hash;
- a matched pair created from compiled manifests. Independent burden and treatment-gap sources
  advance, while changing only the treatment-gap receipt to reuse the burden source defers. Both
  expected decisions must be correct with balanced accuracy 1.0;
- exact-byte reuse under two different source ids still defers and is explicit in the review report;
- two-output compile preflight prevents a pre-existing review file from leaving a partial manifest;
- local-source CLI capture without leaking the input path into the receipt.

## Release Boundary

Raw source bundles, capture directories, real provider review jobs, ingestion runs, and reviewer
working files stay outside Git and Hugging Face. Only sanitized schemas, synthetic examples, code,
tests, and a separately
approved payload-free manifest may enter the release surface. Provider-specific contracts add CDC
MMWR article/location checks (`docs/18_cdc_mmwr_ingestion.md`), PubMed treatment-gap identity and
context checks (`docs/19_ncbi_pubmed_ingestion.md`), and ChEMBL functional-activity plus PubMed
disease-model endpoint and lineage checks (`docs/20_preclinical_provider_ingestion.md`), plus exact
ClinicalTrials.gov arm/population/endpoint/serious-adverse-event checks
(`docs/21_clinical_provider_ingestion.md`). Real
source bytes, review jobs, and compiled provider manifests remain external and unapproved for
release.
