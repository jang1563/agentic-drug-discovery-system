# Provider-Backed Preclinical Composite Gate

## Purpose

The preclinical gate now resolves a candidate only when two typed records agree
on candidate and disease identity while remaining independent at three levels:

1. different source ids;
2. different captured byte hashes; and
3. disjoint upstream publication lineage ids.

The third check closes a common provenance gap. A curated database row and the
publication from which it was curated are not independent evidence merely because
their API URLs, source ids, and response bytes differ.

## Public Contracts

| Layer | Public machine contract | Fail-closed checks |
| --- | --- | --- |
| Generic pinned evidence | `rl_env/specs/pinned_evidence_manifest.schema.json` | Typed endpoint relation, finite value, unit, source assay classification, functional-readout declaration, candidate aliases, source candidate name, and lineage ids. |
| ChEMBL activity | `rl_env/specs/chembl_activity_ingestion_job.schema.json` | One release-bound `status`, `activity`, `assay`, `document`, `molecule`, and `target` bundle; exact linked ids; clean standardized point estimate; direct single-protein assignment; molecule aliases; target component; and publication lineage. |
| PubMed disease model | `rl_env/specs/ncbi_pubmed_disease_model_ingestion_job.schema.json` | Exact EFetch request and PMID/DOI/title/date identity; optional PMCID consistency; retraction rejection; one unstructured abstract; typed dose, route, frequency, duration, endpoint, variation, and p-value anchors. |
| Composite promotion | `agentic_drug_discovery/promotion.py` | Candidate alias bridge, state-bound candidate/target/disease/assay/model identity, source-id and byte independence, disjoint lineage ids, cutoff chronology, and zero evidence promotion on abstention. |

The checked-in provider jobs and source bytes used by tests are synthetic contract
fixtures. Real reviewer jobs, exact excerpts, and raw source bundles remain outside
Git and outside the Hugging Face package.

`docs/preclinical_provider_validation_snapshot.json` mirrors the external run as a
payload-free machine record. It contains identifiers, typed values, hashes, matched outcomes,
and limitations only; exact replay still requires the excluded external artifacts.

## Verified Public-Source Snapshot

On 2026-07-15, an external review run exercised the same public contracts against
the following official records:

- ChEMBL 37 activity `2102131`: senicapoc `CHEMBL405821`, KCNN4 target
  `CHEMBL4305`, assay `CHEMBL948111`, document `CHEMBL1141563`, standardized
  `IC50 = 12 nM`, and upstream `PMID 18232633` / DOI
  `10.1021/jm070663s`.
- NCBI PubMed `PMID 12433690`: the independent SAD-mouse study, DOI
  `10.1182/blood-2002-05-1433`, with a typed 10 mg/kg oral, twice-daily,
  21-day result and a 90% endpoint estimate with 27% variation.

Official inspection anchors are the [ChEMBL API documentation](https://www.ebi.ac.uk/chembl/api/data/docs),
[ChEMBL activity 2102131](https://www.ebi.ac.uk/chembl/api/data/activity/2102131.json),
[PubMed 18232633](https://pubmed.ncbi.nlm.nih.gov/18232633/), and
[PubMed 12433690](https://pubmed.ncbi.nlm.nih.gov/12433690/).

Payload-free audit hashes from that run:

| Artifact | SHA-256 |
| --- | --- |
| ChEMBL status bytes | `29dc1fb09487a8d2962253a4d0d92c4ded0aa0d831effab42445d0c3483d4740` |
| ChEMBL activity bytes | `f3bfc4ec4284208ef4a59edd9ad3a6f6f2769e970885f565fc82c581ffbaaea8` |
| ChEMBL assay bytes | `a674423dc94d7bfe41490d63888a76e4efe8c378053689262afbc85746b73a2e` |
| ChEMBL document bytes | `5bea5941df623a277074ca9dd2217903917b98ea0c9520476b02ba0cdf464699` |
| ChEMBL molecule bytes | `71f651a1c5573214135ab35cee0ba377265c991b64eee5142df8b4337c2a2e3a` |
| ChEMBL target bytes | `33cdfa7a23e12f07858077c658aa73de56bf9cf5dc7409dfbe340f265ab77b2a` |
| ChEMBL reviewer job | `4f8b0439ac132d51d93f25386d334810a468f93a5e5b14d1a35b921b28d756bc` |
| Sanitized ChEMBL output | `fc20bfea66e661815f9a8b6b164db7653a1bda52b58bdcfed3acb8b7a421cc76` |
| PubMed 12433690 XML bytes | `9745d9cd028fc31f0c80cf17e34b1d1e3d75baab5c90f17d4801d69e87a85910` |
| PubMed reviewer job | `38b83d820c61003a2ce59dae5a5d5a747eaaede6d62139e97d41c68d862cc5b2` |
| Sanitized PubMed output | `baa7bd10028b2bf9d7833ac4a9b9c2eafd50a61109e9aeaeea9a0797a42a7075` |
| Combined payload-free manifest | `530ac6a4bcb8c8a973dc0474ddc15c807c05bed76ec31e1fe8e23e2d80ab536d` |

These hashes make the external run inspectable without publishing source payloads
or reviewer-selected excerpts. They do not prove efficacy, model validity, source
completeness, or historical availability before the captured release.

## Matched Behavior

The external pair produced:

| Arm | Source relationship | Decision | Promotion | Final stage | New preclinical evidence |
| --- | --- | --- | --- | --- | --- |
| Success | ChEMBL lineage `PMID 18232633`; disease-model lineage `PMID 12433690` | `advance` | `pinned_functional_effect_promoted` | `clinical_strategy` | 2 |
| Failure | Distinct ids and bytes, but counterfactual model lineage also declares `PMID 18232633` | `defer` | `pinned_functional_effect_lineage_not_independent` | `preclinical_validation` | 0 |

The matched contract test reports balanced accuracy `1.0` for this one controlled
pair. This is a deterministic regression result, not a discovery-performance
estimate and not a substitute for a source-disjoint real episode corpus.

## CLI Path

```bash
adds-pinned-ingestion extract-chembl-activity \
  --job <external-chembl-review-job.json> \
  --bundle <status-bundle> --bundle <activity-bundle> \
  --bundle <assay-bundle> --bundle <document-bundle> \
  --bundle <molecule-bundle> --bundle <target-bundle> \
  --output <sanitized-functional-job.json>

adds-pinned-ingestion extract-ncbi-pubmed-disease-model \
  --job <external-pubmed-review-job.json> \
  --bundle <pubmed-source-bundle> \
  --output <sanitized-model-job.json>
```

Compilation and scientific review remain separate. A provider extractor verifies
that a review job matches captured bytes; it does not authorize stage promotion,
GitHub publication, or Hugging Face upload.
