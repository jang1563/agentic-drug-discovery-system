# Scripts

Script groups:

- `audit/`: repository-boundary and dependency checks.
- `audit/build_hf_release_package.py`: creates the local Hugging Face Dataset mirror package from `huggingface/release_manifest.json` without uploading it.
- `adds-pinned-ingestion` is installed from `agentic_drug_discovery.ingestion_cli`. It captures
  immutable raw source bundles outside Git, verifies reviewer-selected CDC MMWR evidence with
  `extract-cdc-mmwr`, verifies NCBI PubMed treatment-gap evidence with `extract-ncbi-pubmed`, and
  verifies ChEMBL functional activity with `extract-chembl-activity`, verifies NCBI PubMed in-vivo
  evidence with `extract-ncbi-pubmed-disease-model`, verifies exact ClinicalTrials.gov study design
  evidence with `extract-clinicaltrials-gov`, verifies an exact source-disjoint multi-trial bundle
  with `extract-clinicaltrials-gov-portfolio`, and compiles reviewer-authored, payload-free
  manifests.
- Endpoint-family approval and benefit-risk synthesis are intentionally not ingestion subcommands.
  The registered `clinical_synthesis.register_endpoint_mapping` tool commits a reviewed ontology
  binding, and `clinical_synthesis.harmonize_benefit_risk` accepts only that exact mapping before
  recompiling all measurements and provenance from committed trial-design state.

Execution and sync wrappers are kept outside Git until they are sanitized for a specific release target. Scripts should avoid embedding secrets, machine-specific paths, or local account names.
