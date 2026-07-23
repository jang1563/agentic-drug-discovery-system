# NCBI PubMed Treatment-Gap Ingestion

Status: implemented in the 0.3.0.dev0 candidate

Scope: provider-specific treatment-gap extraction from one captured NCBI PubMed EFetch XML record

Scientific posture: deterministic extraction checks article identity, structured abstract context,
and reviewer-selected evidence; it does not infer claims or replace scientific review

## Why Add This Provider

The CDC MMWR contract binds a disease-burden value to one surveillance article. A composite
disease-context gate also needs an independently captured treatment-gap source, but two public
documents must not be treated as context-matched merely because both concern the same disease.

The first manually verified external fixture is the PubMed record `32147964`, `Impact of Medicaid
expansion on access and healthcare among individuals with sickle cell disease.`, PMCID
`PMC7096276`, DOI `10.1002/pbc.28152`. Its structured abstract describes a California Medicaid
cohort during 2011-2016 and reports that fewer than 20% of the cohort filled a hydroxyurea
prescription. The captured XML and reviewer job remain outside Git and Hugging Face.

Official records:

- PubMed: <https://pubmed.ncbi.nlm.nih.gov/32147964/>
- PMC: <https://pmc.ncbi.nlm.nih.gov/articles/PMC7096276/>
- NCBI EFetch XML endpoint: <https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=pubmed&id=32147964&retmode=xml>

The article is not in the Europe PMC open-access full-text subset. This provider therefore verifies
only the official PubMed XML metadata and structured abstract. It does not claim access to, or
verification of, the full article body.

## Bounded Flow

```text
captured NCBI PubMed EFetch XML bundle outside Git
  + reviewer-authored adds.ncbi-pubmed-ingestion-job.v1
  -> source request checks
     -> receipt id, XML media type, HTTPS host/port/path, exact query
     -> PMID- and retrieval-date-bound source version
  -> article identity checks
     -> direct MedlineCitation PMID, ArticleId PMID/PMCID/DOI
     -> Article ELocation DOI, title, electronic publication date
     -> no retracted-publication type or retraction relationship
  -> structured abstract checks
     -> exactly one reviewer-selected METHODS and RESULTS section
     -> exactly one matching context and result excerpt
     -> typed comparator, numeric value, and unit
     -> population, geography, period, and treatment anchors
  -> payload-free adds.pinned-ingestion-job.v1
     -> provider/article/section metadata
     -> SHA-256 values for excerpts and anchors, not their text
  -> generic compile + mandatory review report
  -> PinnedEvidenceAdapter -> semantic promotion -> stage verifier
```

The provider is deliberately limited to `treatment_gap_supported`. A human selects the structured
abstract excerpts and anchors. The extractor verifies those selections against immutable source
bytes and removes all reviewer evidence text before writing the generic job.

## Machine Contract

`rl_env/specs/ncbi_pubmed_ingestion_job.schema.json` defines:

- one PubMed article identity: title, PMID, PMCID, DOI, electronic publication date, and canonical
  PubMed URL;
- one captured `source_receipt_id` shared by every record in the job;
- only the `treatment_gap_supported` predicate;
- stable `disease_id` and `evidence_context_id` values;
- treatment context, gap summary, typed comparison operator/value/unit, population, geography, and
  canonical `YYYY-YYYY` reference period;
- reviewer-only METHODS/RESULTS labels, excerpts, selected value, and population, geography,
  reference-period, and treatment anchors.

The adjacent example and XML used by tests are synthetic contract fixtures. They make no
scientific claim.

## CLI

Capture the EFetch response outside the repository using the generic command from
`docs/17_pinned_source_ingestion.md`. The locator must be the exact PubMed XML request:

```bash
adds-pinned-ingestion capture \
  --url 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=pubmed&id=32147964&retmode=xml' \
  --receipt-id ncbi-pubmed-32147964-receipt \
  --source-id ncbi-pubmed-32147964 \
  --source-version pmid-32147964-pubmed-xml-YYYY-MM-DD \
  --output /external/review/pubmed_32147964_bundle
```

Then verify the reviewer job:

```bash
adds-pinned-ingestion extract-ncbi-pubmed \
  --job /external/review/pubmed_treatment_gap_job.json \
  --bundle /external/review/pubmed_32147964_bundle \
  --output /external/review/pubmed_treatment_gap_generic_job.json
```

The extraction status is `provider_job_extracted_requires_human_review`. Its report binds the
captured source-content SHA-256 and sanitized output SHA-256. Extraction never grants release or
scientific approval.

## Fail-Closed Checks

Extraction rejects:

- a receipt id, XML media type, EFetch HTTPS host/port/path/query, source version, or chronology
  mismatch;
- a malformed or conflicting PMID, PMCID, DOI, title, canonical URL, or electronic publication
  date;
- broad descendant lookup ambiguity: identity values are read only from expected direct XML
  parents;
- entity declarations, malformed XML, multiple PubMed articles, retracted publication types, or
  retraction relationships;
- missing, duplicate, or identical METHODS/RESULTS labels;
- excerpts, values, or anchors that do not occur exactly once in their selected section;
- comparator, numeric value, percent sign or other unit, geography, treatment context, or reference
  period disagreement;
- reviewer attempts to pre-populate normalized variants of provider-owned provenance fields;
- generic raw-payload, local-path, chronology, or schema violations in the sanitized output.

The output retains article identity, selected section labels, typed value text, comparator, and
SHA-256 values. It does not retain XML, abstract excerpts, anchor text, local paths, credentials, or
a source bundle.

## Stage And Evaluation Behavior

`tests/test_ncbi_pubmed_ingestion.py` proves a matched contract pair:

- the PubMed treatment gap plus a separately captured synthetic burden with the same explicit
  California Medicaid context advances the bounded disease-context stage;
- the same treatment gap plus a broader California surveillance burden defers with
  `pinned_unmet_need_context_mismatch` and promotes no evidence.

The matched success fixture is a contract control, not a claim that the real CDC and PubMed
articles describe one population. In the external real-source check, the CDC MMWR record describes
the broader California SCDC population in 2018, whereas the PubMed record describes California
Medicaid enrollees during 2011-2016. Their independent source ids are insufficient to overcome that
population and evidence-context mismatch; the bounded agent correctly defers.

## What This Proves

This provider path proves that a reviewer-selected PubMed treatment-gap statement can be bound to
an exact EFetch request, exact captured XML, direct article identifiers, structured abstract
sections, typed comparison, context anchors, source receipt, and downstream stage decision without
publishing source text.

It does not prove full-text coverage, causal effect, treatment efficacy, representativeness outside
the declared cohort, scientific independence beyond source ids, or correctness of a drug-discovery
decision. Those remain reviewer and evaluation responsibilities.
