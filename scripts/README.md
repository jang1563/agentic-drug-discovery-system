# Scripts

Script groups:

- `audit/`: repository-boundary and dependency checks.
- `audit/build_hf_release_package.py`: creates the local Hugging Face Dataset mirror package from `huggingface/release_manifest.json` without uploading it.
- `audit/build_pattern_mixture_influence_study.py`: deterministically rebuilds the public unequal-
  cluster stress protocol, bound pattern-mixture point report, influence-calibration protocol/report,
  and compact summary.
- `audit/build_informative_cluster_size_study.py`: deterministically rebuilds the public fixed-
  profile unit-weighted/cluster-balanced estimand study, aggregate influence report, and compact
  summary.
- `audit/validate_policy_evaluation_snapshot.py`: binds the public payload-free sealed-evaluation
  aggregate to the current evaluation and clinical-promotion implementations and checks its
  claim and release boundaries.
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
- `adds-clinical-evidence` is installed from
  `agentic_drug_discovery.clinical_decision_cli`. It compiles and validates decision packages and
  cohort diagnostics, then exposes atomic analyze/validate/summarize command trios for package-
  bound outcomes, CR1 uncertainty, prospective design, informative-evaluability stress, binary
  log-IMOR pattern-mixture sensitivity, and dependence-closed cluster-jackknife calibration.
  It also compares normal, Student-t, unequal delete-mj, and experimental multiplier intervals on
  the dedicated influence-calibration study, then compares unit-weighted and cluster-balanced
  functionals under informative cluster size.
  Validation commands perform exact bound replay; summary commands emit compact JSON for people
  and automation.

Execution and sync wrappers are kept outside Git until they are sanitized for a specific release target. Scripts should avoid embedding secrets, machine-specific paths, or local account names.
