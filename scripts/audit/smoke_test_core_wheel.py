#!/usr/bin/env python3
"""Install the built core wheel in isolation and validate its console demo."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import venv
from pathlib import Path


def fail(message: str) -> int:
    print(f"ERROR: {message}", file=sys.stderr)
    return 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--wheel-dir", type=Path, required=True)
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[2]
    clinical_source = (
        repo_root / "tests/fixtures/clinicaltrials_gov_study.synthetic.json"
    )
    clinical_job_path = (
        repo_root
        / "rl_env/specs/clinicaltrials_gov_ingestion_job.example.json"
    )
    clinical_portfolio_path = (
        repo_root
        / "rl_env/specs/clinicaltrials_gov_portfolio_job.example.json"
    )
    for fixture in (clinical_source, clinical_job_path, clinical_portfolio_path):
        if not fixture.is_file():
            return fail(f"required wheel-smoke fixture is missing: {fixture}")

    wheel_dir = args.wheel_dir.resolve()
    wheels = sorted(wheel_dir.glob("agentic_drug_discovery_system-*.whl"))
    if len(wheels) != 1:
        return fail(
            f"expected exactly one core wheel in {wheel_dir}, found {len(wheels)}"
        )

    clean_env = os.environ.copy()
    clean_env.pop("PYTHONPATH", None)
    with tempfile.TemporaryDirectory(prefix="agentic-core-wheel-smoke-") as temp_dir:
        env_dir = Path(temp_dir) / "venv"
        scripts_dir = env_dir / ("Scripts" if os.name == "nt" else "bin")
        python = scripts_dir / ("python.exe" if os.name == "nt" else "python")
        demo = scripts_dir / (
            "adds-control-plane-demo.exe"
            if os.name == "nt"
            else "adds-control-plane-demo"
        )
        bounded_demo = scripts_dir / (
            "adds-bounded-agent-demo.exe"
            if os.name == "nt"
            else "adds-bounded-agent-demo"
        )
        replay = scripts_dir / (
            "adds-replay-bundle.exe" if os.name == "nt" else "adds-replay-bundle"
        )
        ingestion = scripts_dir / (
            "adds-pinned-ingestion.exe"
            if os.name == "nt"
            else "adds-pinned-ingestion"
        )

        burden_source = Path(temp_dir) / "burden.json"
        gap_source = Path(temp_dir) / "gap.json"
        burden_source.write_text('{"measure": 12.5}', encoding="utf-8")
        gap_source.write_text('{"limitation": "residual need"}', encoding="utf-8")
        job_path = Path(temp_dir) / "ingestion-job.json"
        job_path.write_text(
            json.dumps(
                {
                    "schema_version": "adds.pinned-ingestion-job.v1",
                    "job_id": "wheel-ingestion-smoke",
                    "records": [
                        {
                            "source_receipt_id": "wheel-burden-receipt",
                            "record_id": "wheel-burden",
                            "predicate": "disease_burden_supported",
                            "subject": "test disease",
                            "object_value": "A bounded burden summary is present.",
                            "observed_at": "2024-06-01",
                            "available_at": "2024-06-10",
                            "confidence": 0.8,
                            "biological_context": {
                                "disease_id": "MONDO_TEST",
                                "evidence_context_id": "wheel-population-context",
                            },
                            "metadata": {
                                "measure_type": "prevalence",
                                "measure_value": 12.5,
                                "measure_unit": "persons per 100,000",
                                "population": "illustrative population",
                                "geography": "illustrative geography",
                                "reference_period": "2024",
                            },
                        },
                        {
                            "source_receipt_id": "wheel-gap-receipt",
                            "record_id": "wheel-treatment-gap",
                            "predicate": "treatment_gap_supported",
                            "subject": "test disease",
                            "object_value": "A bounded treatment-gap summary is present.",
                            "observed_at": "2024-06-02",
                            "available_at": "2024-06-11",
                            "confidence": 0.8,
                            "biological_context": {
                                "disease_id": "MONDO_TEST",
                                "evidence_context_id": "wheel-population-context",
                            },
                            "metadata": {
                                "treatment_context": "illustrative standard of care",
                                "gap_summary": "A residual need remains.",
                                "population": "illustrative population",
                                "geography": "illustrative geography",
                                "reference_period": "2024",
                            },
                        },
                    ],
                },
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        burden_bundle = Path(temp_dir) / "burden-bundle"
        gap_bundle = Path(temp_dir) / "gap-bundle"
        manifest_path = Path(temp_dir) / "pinned-manifest.json"
        review_path = Path(temp_dir) / "pinned-manifest.review.json"
        mmwr_url = "https://www.cdc.gov/mmwr/volumes/71/ss/synthetic.htm"
        mmwr_excerpt = (
            "The 2018 annual prevalence count was 6,027 cases for California."
        )
        mmwr_source = Path(temp_dir) / "synthetic-mmwr.html"
        mmwr_source.write_text(
            f"""<!doctype html>
<html><head>
<meta name="citation_title" content="Synthetic CDC MMWR SCD Report">
<meta name="citation_doi" content="10.15585/mmwr.synthetic">
<meta name="citation_publication_date" content="2022">
<link rel="canonical" href="{mmwr_url}">
</head><body>
<p>October 7, 2022</p>
<h2><a id="results">Results</a></h2>
<p>{mmwr_excerpt}</p>
</body></html>
""",
            encoding="utf-8",
        )
        mmwr_source_hash = hashlib.sha256(mmwr_source.read_bytes()).hexdigest()
        mmwr_job_path = Path(temp_dir) / "cdc-mmwr-job.json"
        mmwr_job_path.write_text(
            json.dumps(
                {
                    "schema_version": "adds.cdc-mmwr-ingestion-job.v1",
                    "job_id": "wheel-cdc-mmwr-ingestion-smoke",
                    "source_receipt_id": "wheel-cdc-mmwr-receipt",
                    "article": {
                        "title": "Synthetic CDC MMWR SCD Report",
                        "doi": "10.15585/mmwr.synthetic",
                        "publication_date": "2022-10-07",
                        "canonical_url": mmwr_url,
                    },
                    "records": [
                        {
                            "record_id": "wheel-cdc-mmwr-burden",
                            "predicate": "disease_burden_supported",
                            "subject": "test disease",
                            "object_value": "A synthetic burden count is present.",
                            "observed_at": "2018-12-31",
                            "available_at": "2022-10-07",
                            "confidence": 0.8,
                            "biological_context": {
                                "disease_id": "MONDO_TEST",
                                "evidence_context_id": "wheel-california-2018",
                            },
                            "metadata": {
                                "measure_type": "annual prevalence count",
                                "measure_value": 6027,
                                "measure_unit": "cases",
                                "population": "synthetic surveillance population",
                                "geography": "California",
                                "reference_period": "2018",
                            },
                            "evidence": {
                                "location_id": "results",
                                "excerpt": mmwr_excerpt,
                                "value_text": "6,027",
                            },
                        }
                    ],
                },
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        mmwr_bundle = Path(temp_dir) / "cdc-mmwr-bundle"
        mmwr_output = Path(temp_dir) / "cdc-mmwr-extracted.json"
        pubmed_pmid = "12345678"
        pubmed_pmcid = "PMC1234567"
        pubmed_doi = "10.1000/synthetic.scd.1"
        pubmed_title = "Synthetic PubMed SCD Access Study."
        pubmed_url = f"https://pubmed.ncbi.nlm.nih.gov/{pubmed_pmid}/"
        pubmed_efetch_url = (
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
            f"?db=pubmed&id={pubmed_pmid}&retmode=xml"
        )
        pubmed_result = (
            "The cohort included 3,635 individuals. Although <20% of the cohort had "
            "a hydroxyurea prescription filled, utilization increased after 2014."
        )
        pubmed_context = (
            "Individuals with synthetic SCD (<=65 years and enrolled in Medicaid for "
            ">=6 total calendar months any year between 2011 and 2016) were identified "
            "in a multisource database maintained by the California Sickle Cell Data "
            "Collection Program."
        )
        pubmed_source = Path(temp_dir) / "synthetic-pubmed.xml"
        pubmed_source.write_text(
            f"""<?xml version="1.0" encoding="UTF-8"?>
<PubmedArticleSet><PubmedArticle>
<MedlineCitation><PMID Version="1">{pubmed_pmid}</PMID><Article>
<ArticleTitle>{pubmed_title}</ArticleTitle>
<ELocationID EIdType="doi">{pubmed_doi}</ELocationID>
<Abstract>
<AbstractText Label="METHODS">{pubmed_context.replace('<', '&lt;').replace('>', '&gt;')}</AbstractText>
<AbstractText Label="RESULTS">{pubmed_result.replace('<', '&lt;')}</AbstractText>
</Abstract>
<PublicationTypeList><PublicationType>Journal Article</PublicationType></PublicationTypeList>
<ArticleDate DateType="Electronic"><Year>2020</Year><Month>03</Month><Day>08</Day></ArticleDate>
</Article></MedlineCitation>
<PubmedData><ArticleIdList>
<ArticleId IdType="pubmed">{pubmed_pmid}</ArticleId>
<ArticleId IdType="pmc">{pubmed_pmcid}</ArticleId>
<ArticleId IdType="doi">{pubmed_doi}</ArticleId>
</ArticleIdList></PubmedData>
</PubmedArticle></PubmedArticleSet>
""",
            encoding="utf-8",
        )
        pubmed_source_hash = hashlib.sha256(pubmed_source.read_bytes()).hexdigest()
        pubmed_job_path = Path(temp_dir) / "ncbi-pubmed-job.json"
        pubmed_job_path.write_text(
            json.dumps(
                {
                    "schema_version": "adds.ncbi-pubmed-ingestion-job.v1",
                    "job_id": "wheel-ncbi-pubmed-ingestion-smoke",
                    "source_receipt_id": "wheel-ncbi-pubmed-receipt",
                    "article": {
                        "title": pubmed_title,
                        "pmid": pubmed_pmid,
                        "pmcid": pubmed_pmcid,
                        "doi": pubmed_doi,
                        "publication_date": "2020-03-08",
                        "canonical_url": pubmed_url,
                    },
                    "records": [
                        {
                            "record_id": "wheel-ncbi-pubmed-gap",
                            "predicate": "treatment_gap_supported",
                            "subject": "test disease",
                            "object_value": "A synthetic treatment gap is present.",
                            "observed_at": "2016-12-31",
                            "available_at": "2020-03-08",
                            "confidence": 0.8,
                            "biological_context": {
                                "disease_id": "MONDO_TEST",
                                "evidence_context_id": "wheel-medicaid-2011-2016",
                            },
                            "metadata": {
                                "treatment_context": "hydroxyurea prescription filled",
                                "gap_summary": "A synthetic utilization gap remains.",
                                "gap_measure_operator": "lt",
                                "gap_measure_value": 20,
                                "gap_measure_unit": "percent",
                                "population": "synthetic California Medicaid population",
                                "geography": "California",
                                "reference_period": "2011-2016",
                            },
                            "evidence": {
                                "result_label": "RESULTS",
                                "result_excerpt": pubmed_result,
                                "context_label": "METHODS",
                                "context_excerpt": pubmed_context,
                                "value_text": "<20%",
                                "population_anchor": (
                                    "Individuals with synthetic SCD (<=65 years and "
                                    "enrolled in Medicaid for >=6 total calendar months "
                                    "any year between 2011 and 2016)"
                                ),
                                "geography_anchor": "California",
                                "reference_period_anchor": "between 2011 and 2016",
                                "treatment_anchor": "hydroxyurea prescription filled",
                            },
                        }
                    ],
                },
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        pubmed_bundle = Path(temp_dir) / "ncbi-pubmed-bundle"
        pubmed_output = Path(temp_dir) / "ncbi-pubmed-extracted.json"
        chembl_assay_description = (
            "Synthetic channel inhibition in human cells assessed by a synthetic "
            "stimulated ion-efflux readout"
        )
        chembl_functional_anchor = "synthetic stimulated ion-efflux readout"
        chembl_resources = {
            "status": {
                "chembl_db_version": "ChEMBL_37",
                "chembl_release_date": "2026-05-01",
                "status": "UP",
            },
            "activity": {
                "activity_id": 9000001,
                "assay_chembl_id": "CHEMBL9000011",
                "document_chembl_id": "CHEMBL9000012",
                "molecule_chembl_id": "CHEMBL9000013",
                "target_chembl_id": "CHEMBL9000014",
                "standard_flag": 1,
                "standard_relation": "=",
                "standard_value": "12.0",
                "standard_units": "nM",
                "standard_type": "IC50",
                "standard_upper_value": None,
                "standard_text_value": None,
                "pchembl_value": "7.92",
                "data_validity_comment": None,
                "potential_duplicate": 0,
                "assay_description": chembl_assay_description,
                "assay_type": "B",
                "bao_endpoint": "BAO_0000190",
                "bao_format": "BAO_0000357",
                "target_organism": "Homo sapiens",
                "molecule_pref_name": "SYNTHETIC-CANDIDATE",
                "parent_molecule_chembl_id": "CHEMBL9000013",
                "record_id": 9900001,
            },
            "assay": {
                "assay_chembl_id": "CHEMBL9000011",
                "description": chembl_assay_description,
                "assay_type": "B",
                "assay_type_description": "Binding",
                "confidence_score": 9,
                "confidence_description": "Direct single protein target assigned",
                "relationship_type": "D",
                "document_chembl_id": "CHEMBL9000012",
                "target_chembl_id": "CHEMBL9000014",
                "bao_format": "BAO_0000357",
            },
            "document": {
                "document_chembl_id": "CHEMBL9000012",
                "doc_type": "PUBLICATION",
                "title": "Synthetic inhibitors for a contract fixture.",
                "year": 2008,
                "pubmed_id": 99999991,
                "doi": "10.1000/synthetic.chembl.activity",
            },
            "molecule": {
                "molecule_chembl_id": "CHEMBL9000013",
                "pref_name": "SYNTHETIC-CANDIDATE",
                "molecule_synonyms": [
                    {
                        "molecule_synonym": "SYNTH-CODE-1",
                        "syn_type": "RESEARCH_CODE",
                        "synonyms": "SYNTH-CODE-1",
                    },
                    {
                        "molecule_synonym": "SYNTH-CODE-2",
                        "syn_type": "RESEARCH_CODE",
                        "synonyms": "SYNTH-CODE-2",
                    },
                    {
                        "molecule_synonym": "Synthetic Candidate",
                        "syn_type": "INN",
                        "synonyms": "SYNTHETIC-CANDIDATE",
                    },
                ],
            },
            "target": {
                "target_chembl_id": "CHEMBL9000014",
                "pref_name": "Synthetic ion channel protein 1",
                "target_type": "SINGLE PROTEIN",
                "organism": "Homo sapiens",
                "tax_id": 9606,
                "target_components": [
                    {
                        "accession": "P00001",
                        "component_type": "PROTEIN",
                        "target_component_synonyms": [
                            {
                                "component_synonym": "SYN1",
                                "syn_type": "GENE_SYMBOL",
                            },
                            {
                                "component_synonym": "Synthetic channel",
                                "syn_type": "UNIPROT",
                            },
                        ],
                    }
                ],
            },
        }
        chembl_receipts = {
            resource: f"wheel-chembl-{resource}-receipt"
            for resource in chembl_resources
        }
        chembl_job = {
            "schema_version": "adds.chembl-activity-ingestion-job.v1",
            "job_id": "wheel-chembl-functional-activity",
            "source_receipt_ids": chembl_receipts,
            "release": {
                "database_version": "ChEMBL_37",
                "release_date": "2026-05-01",
            },
            "activity": {
                "activity_id": 9000001,
                "assay_chembl_id": "CHEMBL9000011",
                "document_chembl_id": "CHEMBL9000012",
                "molecule_chembl_id": "CHEMBL9000013",
                "molecule_name": "SYNTHETIC-CANDIDATE",
                "candidate_aliases": [
                    "SYNTHETIC-CANDIDATE",
                    "SYNTH-CODE-1",
                    "SYNTH-CODE-2",
                ],
                "target_chembl_id": "CHEMBL9000014",
                "target_symbol": "SYN1",
                "target_uniprot_accession": "P00001",
                "document_pubmed_id": "99999991",
                "document_doi": "10.1000/synthetic.chembl.activity",
                "source_assay_type": "B",
                "source_assay_type_description": "Binding",
            },
            "record": {
                "record_id": "wheel-chembl-functional-activity",
                "predicate": "candidate_target_functional_activity_supported",
                "subject": "SYNTHETIC-CANDIDATE",
                "object_value": (
                    "A synthetic candidate changed a synthetic readout for "
                    "contract testing only."
                ),
                "observed_at": "2008-12-31",
                "available_at": "2026-05-01",
                "confidence": 0.9,
                "biological_context": {
                    "candidate_id": "CHEMBL9000013",
                    "target_id": "CHEMBL9000014",
                    "target_record_id": "ENSG_SYNTHETIC1",
                    "disease_id": "MONDO_SYNTHETIC",
                    "organism": "Homo sapiens",
                    "assay_id": "CHEMBL9000011",
                },
                "metadata": {
                    "assay_name": "Synthetic human-cell ion-efflux assay",
                    "assay_type": "functional",
                    "functional_readout": True,
                    "endpoint": "IC50",
                    "endpoint_relation": "eq",
                    "endpoint_value": 12.0,
                    "endpoint_unit": "nM",
                    "effect_direction": "decreased",
                },
                "evidence": {
                    "assay_description": chembl_assay_description,
                    "functional_readout_anchor": chembl_functional_anchor,
                },
            },
        }
        chembl_job_path = Path(temp_dir) / "chembl-activity-job.json"
        chembl_job_path.write_text(
            json.dumps(chembl_job, sort_keys=True), encoding="utf-8"
        )
        chembl_source_paths = {}
        chembl_bundle_paths = {}
        for resource, payload in chembl_resources.items():
            source_path = Path(temp_dir) / f"chembl-{resource}.json"
            source_path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
            chembl_source_paths[resource] = source_path
            chembl_bundle_paths[resource] = Path(temp_dir) / f"chembl-{resource}-bundle"
        chembl_source_hashes = {
            resource: hashlib.sha256(path.read_bytes()).hexdigest()
            for resource, path in chembl_source_paths.items()
        }
        chembl_output = Path(temp_dir) / "chembl-activity-extracted.json"

        disease_model_pmid = "99999992"
        disease_model_doi = "10.1000/synthetic.disease-model"
        disease_model_title = "Synthetic in-vivo disease-model contract fixture."
        disease_model_url = (
            f"https://pubmed.ncbi.nlm.nih.gov/{disease_model_pmid}/"
        )
        disease_model_efetch_url = (
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
            f"?db=pubmed&id={disease_model_pmid}&retmode=xml"
        )
        disease_model_result = (
            "In a synthetic transgenic mouse disease model, treatment with "
            "SYNTH-CODE-1 (10 mg/kg orally, twice a day) for 21 days showed "
            "synthetic channel activity inhibition of 90% +/- 27%, P <.005"
        )
        disease_model_conclusion = (
            "These synthetic data indicate that SYNTH-CODE-1 improves the "
            "synthetic disease-model endpoint."
        )
        disease_model_abstract = (
            "Synthetic introduction text for a deterministic provider contract. "
            f"{disease_model_result}, followed by additional synthetic outcomes. "
            f"{disease_model_conclusion}"
        )
        disease_model_source = Path(temp_dir) / "synthetic-disease-model.xml"
        disease_model_source.write_text(
            f"""<?xml version="1.0" encoding="UTF-8"?>
<PubmedArticleSet><PubmedArticle>
<MedlineCitation><PMID Version="1">{disease_model_pmid}</PMID><Article>
<Journal><JournalIssue><PubDate><Year>2003</Year></PubDate></JournalIssue></Journal>
<ArticleTitle>{disease_model_title}</ArticleTitle>
<ELocationID EIdType="doi">{disease_model_doi}</ELocationID>
<Abstract><AbstractText>{disease_model_abstract.replace('<', '&lt;')}</AbstractText></Abstract>
<PublicationTypeList><PublicationType>Journal Article</PublicationType></PublicationTypeList>
<ArticleDate DateType="Electronic"><Year>2002</Year><Month>11</Month><Day>14</Day></ArticleDate>
</Article></MedlineCitation><PubmedData><ArticleIdList>
<ArticleId IdType="pubmed">{disease_model_pmid}</ArticleId>
<ArticleId IdType="doi">{disease_model_doi}</ArticleId>
</ArticleIdList></PubmedData></PubmedArticle></PubmedArticleSet>
""",
            encoding="utf-8",
        )
        disease_model_job = {
            "schema_version": "adds.ncbi-pubmed-disease-model-ingestion-job.v1",
            "job_id": "wheel-pubmed-disease-model",
            "source_receipt_id": "wheel-pubmed-disease-model-receipt",
            "article": {
                "title": disease_model_title,
                "pmid": disease_model_pmid,
                "pmcid": None,
                "doi": disease_model_doi,
                "publication_date": "2002-11-14",
                "canonical_url": disease_model_url,
            },
            "records": [
                {
                    "record_id": "wheel-pubmed-disease-model-effect",
                    "predicate": "disease_model_effect_supported",
                    "subject": "SYNTHETIC-CANDIDATE",
                    "object_value": (
                        "A synthetic treatment changed a synthetic model endpoint "
                        "for contract testing only."
                    ),
                    "observed_at": "2002-11-14",
                    "available_at": "2002-11-14",
                    "confidence": 0.9,
                    "biological_context": {
                        "candidate_id": "CHEMBL9000013",
                        "disease_id": "MONDO_SYNTHETIC",
                        "organism": "Mus musculus",
                        "model_system_id": "SYNTHETIC_MOUSE_MODEL",
                    },
                    "metadata": {
                        "model_system": (
                            "Synthetic transgenic mouse disease model"
                        ),
                        "model_type": "transgenic animal model",
                        "endpoint": "synthetic channel activity inhibition",
                        "endpoint_relation": "eq",
                        "endpoint_value": 90.0,
                        "endpoint_unit": "percent",
                        "endpoint_variation_value": 27.0,
                        "endpoint_variation_unit": "percent",
                        "effect_direction": "improved",
                        "disease_relevance": (
                            "Synthetic contract fixture, not a scientific claim."
                        ),
                        "source_candidate_name": "SYNTH-CODE-1",
                        "dose_value": 10.0,
                        "dose_unit": "mg/kg",
                        "route": "oral",
                        "frequency": "twice a day",
                        "duration_value": 21.0,
                        "duration_unit": "days",
                        "p_value_relation": "lt",
                        "p_value": 0.005,
                    },
                    "evidence": {
                        "result_excerpt": disease_model_result,
                        "conclusion_excerpt": disease_model_conclusion,
                        "candidate_anchor": "SYNTH-CODE-1",
                        "model_anchor": (
                            "synthetic transgenic mouse disease model"
                        ),
                        "dose_text": "10 mg/kg",
                        "route_anchor": "orally",
                        "frequency_anchor": "twice a day",
                        "duration_text": "21 days",
                        "endpoint_value_text": "90%",
                        "endpoint_variation_text": "27%",
                        "p_value_text": "<.005",
                        "conclusion_anchor": (
                            "improves the synthetic disease-model endpoint"
                        ),
                    },
                }
            ],
        }
        disease_model_job_path = Path(temp_dir) / "pubmed-disease-model-job.json"
        disease_model_job_path.write_text(
            json.dumps(disease_model_job, sort_keys=True), encoding="utf-8"
        )
        disease_model_bundle = Path(temp_dir) / "pubmed-disease-model-bundle"
        disease_model_output = Path(temp_dir) / "pubmed-disease-model-extracted.json"
        disease_model_source_hash = hashlib.sha256(
            disease_model_source.read_bytes()
        ).hexdigest()
        clinical_source_hash = hashlib.sha256(clinical_source.read_bytes()).hexdigest()
        clinical_bundle = Path(temp_dir) / "clinicaltrials-gov-bundle"
        clinical_output = Path(temp_dir) / "clinicaltrials-gov-extracted.json"
        clinical_source_two = Path(temp_dir) / "clinicaltrials-gov-study-two.json"
        clinical_source_two.write_text(
            clinical_source.read_text(encoding="utf-8").replace(
                "NCT00000001", "NCT00000002"
            ),
            encoding="utf-8",
        )
        clinical_source_two_hash = hashlib.sha256(
            clinical_source_two.read_bytes()
        ).hexdigest()
        clinical_job_two = json.loads(clinical_job_path.read_text(encoding="utf-8"))
        clinical_job_two = json.loads(
            json.dumps(clinical_job_two).replace("NCT00000001", "NCT00000002")
        )
        clinical_job_two["job_id"] = "clinicaltrials-gov-test-design-2"
        clinical_job_two["source_receipt_id"] = "ctgov-test-trial-2"
        clinical_job_two_path = Path(temp_dir) / "clinicaltrials-gov-job-two.json"
        clinical_job_two_path.write_text(
            json.dumps(clinical_job_two, sort_keys=True), encoding="utf-8"
        )
        clinical_bundle_two = Path(temp_dir) / "clinicaltrials-gov-bundle-two"
        clinical_portfolio_output = (
            Path(temp_dir) / "clinicaltrials-gov-portfolio-extracted.json"
        )

        try:
            venv.EnvBuilder(with_pip=True, clear=True).create(env_dir)
            subprocess.run(
                [str(python), "-m", "pip", "install", "--no-deps", str(wheels[0])],
                check=True,
                capture_output=True,
                text=True,
                env=clean_env,
            )
            sealed_api = subprocess.run(
                [
                    str(python),
                    "-c",
                    (
                        "from agentic_drug_discovery import ("
                        "evaluate_policy_submission, "
                        "policy_evaluation_report_from_json, "
                        "policy_evaluation_submission_from_json, "
                        "sealed_evaluation_board_from_json, "
                        "sealed_evaluation_vault_from_json"
                        "); "
                        "assert all(callable(item) for item in ("
                        "evaluate_policy_submission, "
                        "policy_evaluation_report_from_json, "
                        "policy_evaluation_submission_from_json, "
                        "sealed_evaluation_board_from_json, "
                        "sealed_evaluation_vault_from_json"
                        ")); "
                        "print('sealed-evaluation-api-ok')"
                    ),
                ],
                cwd=temp_dir,
                check=True,
                capture_output=True,
                text=True,
                env=clean_env,
            )
            completed = subprocess.run(
                [str(demo)],
                cwd=temp_dir,
                check=True,
                capture_output=True,
                text=True,
                env=clean_env,
            )
            bounded = subprocess.run(
                [str(bounded_demo)],
                cwd=temp_dir,
                check=True,
                capture_output=True,
                text=True,
                env=clean_env,
            )
            bundle = subprocess.run(
                [
                    str(python),
                    "-c",
                    (
                        "from agentic_drug_discovery import ReplayBundle, "
                        "replay_bundle_to_json; "
                        "from agentic_drug_discovery.demo import "
                        "build_scd_control_plane_demo; "
                        "_, state, packets = build_scd_control_plane_demo(); "
                        "print(replay_bundle_to_json(ReplayBundle("
                        "initial_state=state, packets=packets)), end='')"
                    ),
                ],
                cwd=temp_dir,
                check=True,
                capture_output=True,
                text=True,
                env=clean_env,
            )
            replayed = subprocess.run(
                [str(replay)],
                cwd=temp_dir,
                input=bundle.stdout,
                check=True,
                capture_output=True,
                text=True,
                env=clean_env,
            )
            for source_path, bundle_path, receipt_id, source_id in (
                (
                    burden_source,
                    burden_bundle,
                    "wheel-burden-receipt",
                    "wheel-burden-source",
                ),
                (
                    gap_source,
                    gap_bundle,
                    "wheel-gap-receipt",
                    "wheel-gap-source",
                ),
            ):
                subprocess.run(
                    [
                        str(ingestion),
                        "capture",
                        "--input-file",
                        str(source_path),
                        "--locator",
                        f"https://example.invalid/wheel/{source_id}",
                        "--receipt-id",
                        receipt_id,
                        "--source-id",
                        source_id,
                        "--source-version",
                        "snapshot-2024-06-15",
                        "--retrieved-at",
                        "2024-06-15T12:00:00Z",
                        "--output",
                        str(bundle_path),
                    ],
                    cwd=temp_dir,
                    check=True,
                    capture_output=True,
                    text=True,
                    env=clean_env,
                )
            ingested = subprocess.run(
                [
                    str(ingestion),
                    "compile",
                    "--job",
                    str(job_path),
                    "--bundle",
                    str(burden_bundle),
                    "--bundle",
                    str(gap_bundle),
                    "--manifest-out",
                    str(manifest_path),
                    "--review-out",
                    str(review_path),
                ],
                cwd=temp_dir,
                check=True,
                capture_output=True,
                text=True,
                env=clean_env,
            )
            subprocess.run(
                [
                    str(ingestion),
                    "capture",
                    "--input-file",
                    str(mmwr_source),
                    "--locator",
                    mmwr_url,
                    "--receipt-id",
                    "wheel-cdc-mmwr-receipt",
                    "--source-id",
                    "wheel-cdc-mmwr-source",
                    "--source-version",
                    "doi-10.15585-mmwr.synthetic",
                    "--retrieved-at",
                    "2022-10-08T12:00:00Z",
                    "--media-type",
                    "text/html",
                    "--output",
                    str(mmwr_bundle),
                ],
                cwd=temp_dir,
                check=True,
                capture_output=True,
                text=True,
                env=clean_env,
            )
            mmwr_extracted = subprocess.run(
                [
                    str(ingestion),
                    "extract-cdc-mmwr",
                    "--job",
                    str(mmwr_job_path),
                    "--bundle",
                    str(mmwr_bundle),
                    "--output",
                    str(mmwr_output),
                ],
                cwd=temp_dir,
                check=True,
                capture_output=True,
                text=True,
                env=clean_env,
            )
            subprocess.run(
                [
                    str(ingestion),
                    "capture",
                    "--input-file",
                    str(pubmed_source),
                    "--locator",
                    pubmed_efetch_url,
                    "--receipt-id",
                    "wheel-ncbi-pubmed-receipt",
                    "--source-id",
                    "wheel-ncbi-pubmed-source",
                    "--source-version",
                    "pmid-12345678-pubmed-xml-2026-07-15",
                    "--retrieved-at",
                    "2026-07-15T01:30:00Z",
                    "--media-type",
                    "text/xml",
                    "--output",
                    str(pubmed_bundle),
                ],
                cwd=temp_dir,
                check=True,
                capture_output=True,
                text=True,
                env=clean_env,
            )
            pubmed_extracted = subprocess.run(
                [
                    str(ingestion),
                    "extract-ncbi-pubmed",
                    "--job",
                    str(pubmed_job_path),
                    "--bundle",
                    str(pubmed_bundle),
                    "--output",
                    str(pubmed_output),
                ],
                cwd=temp_dir,
                check=True,
                capture_output=True,
                text=True,
                env=clean_env,
            )
            chembl_identifiers = {
                "status": None,
                "activity": "9000001",
                "assay": "CHEMBL9000011",
                "document": "CHEMBL9000012",
                "molecule": "CHEMBL9000013",
                "target": "CHEMBL9000014",
            }
            for resource, identifier in chembl_identifiers.items():
                if identifier is None:
                    locator = "https://www.ebi.ac.uk/chembl/api/data/status.json"
                    version_label = "status"
                    source_id = "chembl-status"
                else:
                    locator = (
                        "https://www.ebi.ac.uk/chembl/api/data/"
                        f"{resource}/{identifier}.json"
                    )
                    version_label = f"{resource}-{identifier}"
                    source_id = f"chembl-{resource}-{identifier}"
                subprocess.run(
                    [
                        str(ingestion),
                        "capture",
                        "--input-file",
                        str(chembl_source_paths[resource]),
                        "--locator",
                        locator,
                        "--receipt-id",
                        chembl_receipts[resource],
                        "--source-id",
                        source_id,
                        "--source-version",
                        f"chembl-37-{version_label}-release-2026-05-01",
                        "--retrieved-at",
                        "2026-07-15T01:00:00Z",
                        "--media-type",
                        "application/json",
                        "--output",
                        str(chembl_bundle_paths[resource]),
                    ],
                    cwd=temp_dir,
                    check=True,
                    capture_output=True,
                    text=True,
                    env=clean_env,
                )
            chembl_extract_args = [
                str(ingestion),
                "extract-chembl-activity",
                "--job",
                str(chembl_job_path),
            ]
            for resource in chembl_identifiers:
                chembl_extract_args.extend(
                    ["--bundle", str(chembl_bundle_paths[resource])]
                )
            chembl_extract_args.extend(["--output", str(chembl_output)])
            chembl_extracted = subprocess.run(
                chembl_extract_args,
                cwd=temp_dir,
                check=True,
                capture_output=True,
                text=True,
                env=clean_env,
            )
            subprocess.run(
                [
                    str(ingestion),
                    "capture",
                    "--input-file",
                    str(disease_model_source),
                    "--locator",
                    disease_model_efetch_url,
                    "--receipt-id",
                    "wheel-pubmed-disease-model-receipt",
                    "--source-id",
                    "wheel-ncbi-pubmed-disease-model",
                    "--source-version",
                    "pmid-99999992-pubmed-xml-2026-07-15",
                    "--retrieved-at",
                    "2026-07-15T01:30:00Z",
                    "--media-type",
                    "text/xml",
                    "--output",
                    str(disease_model_bundle),
                ],
                cwd=temp_dir,
                check=True,
                capture_output=True,
                text=True,
                env=clean_env,
            )
            disease_model_extracted = subprocess.run(
                [
                    str(ingestion),
                    "extract-ncbi-pubmed-disease-model",
                    "--job",
                    str(disease_model_job_path),
                    "--bundle",
                    str(disease_model_bundle),
                    "--output",
                    str(disease_model_output),
                ],
                cwd=temp_dir,
                check=True,
                capture_output=True,
                text=True,
                env=clean_env,
            )
            for source_path, bundle_path, nct_id, receipt_id in (
                (
                    clinical_source,
                    clinical_bundle,
                    "NCT00000001",
                    "ctgov-test-trial",
                ),
                (
                    clinical_source_two,
                    clinical_bundle_two,
                    "NCT00000002",
                    "ctgov-test-trial-2",
                ),
            ):
                subprocess.run(
                    [
                        str(ingestion),
                        "capture",
                        "--input-file",
                        str(source_path),
                        "--locator",
                        f"https://clinicaltrials.gov/api/v2/studies/{nct_id}",
                        "--receipt-id",
                        receipt_id,
                        "--source-id",
                        f"clinicaltrials-gov-{nct_id}",
                        "--source-version",
                        f"clinicaltrials-gov-{nct_id}-version-2025-01-01",
                        "--retrieved-at",
                        "2025-01-02T00:00:00Z",
                        "--media-type",
                        "application/json",
                        "--output",
                        str(bundle_path),
                    ],
                    cwd=temp_dir,
                    check=True,
                    capture_output=True,
                    text=True,
                    env=clean_env,
                )
            clinical_extracted = subprocess.run(
                [
                    str(ingestion),
                    "extract-clinicaltrials-gov",
                    "--job",
                    str(clinical_job_path),
                    "--bundle",
                    str(clinical_bundle),
                    "--output",
                    str(clinical_output),
                ],
                cwd=temp_dir,
                check=True,
                capture_output=True,
                text=True,
                env=clean_env,
            )
            clinical_portfolio_extracted = subprocess.run(
                [
                    str(ingestion),
                    "extract-clinicaltrials-gov-portfolio",
                    "--job",
                    str(clinical_portfolio_path),
                    "--trial-job",
                    str(clinical_job_path),
                    "--trial-job",
                    str(clinical_job_two_path),
                    "--bundle",
                    str(clinical_bundle),
                    "--bundle",
                    str(clinical_bundle_two),
                    "--output",
                    str(clinical_portfolio_output),
                ],
                cwd=temp_dir,
                check=True,
                capture_output=True,
                text=True,
                env=clean_env,
            )
        except subprocess.CalledProcessError as exc:
            detail = (exc.stderr or exc.stdout or str(exc)).strip()
            return fail(f"isolated wheel execution failed: {detail}")
        except OSError as exc:
            return fail(f"isolated wheel environment failed: {exc}")

        try:
            report = json.loads(completed.stdout)
            bounded_report = json.loads(bounded.stdout)
            replay_report = json.loads(replayed.stdout)
            ingestion_report = json.loads(ingested.stdout)
            ingestion_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            ingestion_review_text = review_path.read_text(encoding="utf-8")
            ingestion_review = json.loads(ingestion_review_text)
            mmwr_report = json.loads(mmwr_extracted.stdout)
            mmwr_output_text = mmwr_output.read_text(encoding="utf-8")
            mmwr_job = json.loads(mmwr_output_text)
            pubmed_report = json.loads(pubmed_extracted.stdout)
            pubmed_output_text = pubmed_output.read_text(encoding="utf-8")
            pubmed_job = json.loads(pubmed_output_text)
            chembl_report = json.loads(chembl_extracted.stdout)
            chembl_output_text = chembl_output.read_text(encoding="utf-8")
            chembl_extracted_job = json.loads(chembl_output_text)
            disease_model_report = json.loads(disease_model_extracted.stdout)
            disease_model_output_text = disease_model_output.read_text(
                encoding="utf-8"
            )
            disease_model_extracted_job = json.loads(disease_model_output_text)
            clinical_report = json.loads(clinical_extracted.stdout)
            clinical_output_text = clinical_output.read_text(encoding="utf-8")
            clinical_extracted_job = json.loads(clinical_output_text)
            clinical_portfolio_report = json.loads(
                clinical_portfolio_extracted.stdout
            )
            clinical_portfolio_output_text = clinical_portfolio_output.read_text(
                encoding="utf-8"
            )
            clinical_portfolio_job = json.loads(clinical_portfolio_output_text)
        except json.JSONDecodeError as exc:
            return fail(f"installed console command did not emit valid JSON: {exc}")

    final_state = report.get("final_state") or {}
    expected = {
        "completed": True,
        "non_benchmark": True,
        "transition_count": 8,
    }
    for key, value in expected.items():
        if report.get(key) != value:
            return fail(f"console demo field {key!r} must be {value!r}")
    expected_final = {
        "status": "completed",
        "version": 8,
        "accepted_packet_count": 8,
        "action_count": 8,
        "disease_count": 1,
        "assay_count": 1,
        "model_system_count": 1,
        "intervention_count": 1,
        "trial_count": 1,
        "trial_design_count": 1,
        "trial_arm_count": 2,
        "trial_population_count": 1,
        "trial_endpoint_count": 1,
        "trial_safety_count": 1,
        "trial_safety_arm_count": 2,
        "evidence_count": 19,
        "claim_count": 9,
    }
    for key, value in expected_final.items():
        if final_state.get(key) != value:
            return fail(f"console demo final_state field {key!r} must be {value!r}")

    expected_bounded = {
        "fixture": True,
        "non_benchmark": True,
        "plan_status": "ready",
        "run_status": "committed",
        "decision": "advance",
        "stage_before": "target_nomination",
        "stage_after": "modality_selection",
        "program_status": "active",
        "accepted_packet_count": 1,
        "recovered_to_defer": False,
    }
    for key, value in expected_bounded.items():
        if bounded_report.get(key) != value:
            return fail(f"bounded demo field {key!r} must be {value!r}")
    if bounded_report.get("evidence_predicates") != [
        "target_identity_resolved",
        "target_disease_supported",
    ]:
        return fail("bounded demo did not promote the expected target evidence")
    if bounded_report.get("target_ids") != ["ENSG00000119866"]:
        return fail("bounded demo did not preserve the expected target identity")
    if bounded_report.get("disease_ids") != ["MONDO_0011382"]:
        return fail("bounded demo did not preserve the expected disease identity")
    if bounded_report.get("tool_statuses") != ["succeeded"]:
        return fail("bounded demo did not record one successful tool outcome")

    replay_final = replay_report.get("final_state") or {}
    expected_replay = {
        "accepted_count": 8,
        "blocked_count": 0,
        "attempted_packet_count": 8,
    }
    for key, value in expected_replay.items():
        if replay_report.get(key) != value:
            return fail(f"replay command field {key!r} must be {value!r}")
    if replay_final.get("status") != "completed" or replay_final.get("version") != 8:
        return fail("replay command did not reproduce the completed version-8 state")

    expected_ingestion = {
        "status": "compiled_requires_human_review",
        "record_count": 2,
        "receipt_count": 2,
        "independent_source_count": 2,
    }
    for key, value in expected_ingestion.items():
        if ingestion_report.get(key) != value:
            return fail(f"ingestion command field {key!r} must be {value!r}")
    if ingestion_manifest.get("schema_version") != "adds.pinned-evidence.v1":
        return fail("ingestion command did not emit a pinned-evidence manifest")
    if ingestion_review.get("status") != "requires_human_review":
        return fail("ingestion review did not preserve the human approval gate")
    if any(
        str(source_path) in ingestion_review_text
        for source_path in (burden_source, gap_source)
    ):
        return fail("ingestion review leaked a local source path")

    expected_mmwr = {
        "status": "provider_job_extracted_requires_human_review",
        "provider_id": "cdc_mmwr",
        "record_count": 1,
    }
    for key, value in expected_mmwr.items():
        if mmwr_report.get(key) != value:
            return fail(f"CDC MMWR extraction field {key!r} must be {value!r}")
    if mmwr_job.get("schema_version") != "adds.pinned-ingestion-job.v1":
        return fail("CDC MMWR extraction did not emit a generic ingestion job")
    if mmwr_report.get("source_content_hash") != mmwr_source_hash:
        return fail("CDC MMWR extraction did not report the source content hash")
    if mmwr_report.get("output_sha256") != hashlib.sha256(
        mmwr_output_text.encode()
    ).hexdigest():
        return fail("CDC MMWR extraction did not report the output hash")
    if mmwr_excerpt in mmwr_output_text or '"evidence"' in mmwr_output_text:
        return fail("CDC MMWR extraction retained reviewer evidence text")
    mmwr_metadata = mmwr_job["records"][0].get("metadata", {})
    if mmwr_metadata.get("provider_id") != "cdc_mmwr":
        return fail("CDC MMWR extraction lost provider identity")
    if len(mmwr_metadata.get("evidence_excerpt_sha256", "")) != 64:
        return fail("CDC MMWR extraction lost the excerpt hash")

    expected_pubmed = {
        "status": "provider_job_extracted_requires_human_review",
        "provider_id": "ncbi_pubmed",
        "record_count": 1,
    }
    for key, value in expected_pubmed.items():
        if pubmed_report.get(key) != value:
            return fail(f"NCBI PubMed extraction field {key!r} must be {value!r}")
    if pubmed_job.get("schema_version") != "adds.pinned-ingestion-job.v1":
        return fail("NCBI PubMed extraction did not emit a generic ingestion job")
    if pubmed_report.get("source_content_hash") != pubmed_source_hash:
        return fail("NCBI PubMed extraction did not report the source content hash")
    if pubmed_report.get("output_sha256") != hashlib.sha256(
        pubmed_output_text.encode()
    ).hexdigest():
        return fail("NCBI PubMed extraction did not report the output hash")
    if (
        pubmed_result in pubmed_output_text
        or pubmed_context in pubmed_output_text
        or '"evidence"' in pubmed_output_text
    ):
        return fail("NCBI PubMed extraction retained reviewer evidence text")
    pubmed_metadata = pubmed_job["records"][0].get("metadata", {})
    if pubmed_metadata.get("provider_id") != "ncbi_pubmed":
        return fail("NCBI PubMed extraction lost provider identity")
    if pubmed_metadata.get("article_pmid") != pubmed_pmid:
        return fail("NCBI PubMed extraction lost article identity")
    for field_name in (
        "result_excerpt_sha256",
        "context_excerpt_sha256",
        "population_anchor_sha256",
        "geography_anchor_sha256",
        "reference_period_anchor_sha256",
        "treatment_anchor_sha256",
    ):
        if len(pubmed_metadata.get(field_name, "")) != 64:
            return fail(f"NCBI PubMed extraction lost {field_name}")

    expected_chembl = {
        "status": "provider_job_extracted_requires_human_review",
        "provider_id": "chembl",
        "record_count": 1,
    }
    for key, value in expected_chembl.items():
        if chembl_report.get(key) != value:
            return fail(f"ChEMBL extraction field {key!r} must be {value!r}")
    if chembl_extracted_job.get("schema_version") != "adds.pinned-ingestion-job.v1":
        return fail("ChEMBL extraction did not emit a generic ingestion job")
    if chembl_report.get("source_content_hashes") != chembl_source_hashes:
        return fail("ChEMBL extraction did not report all source content hashes")
    if chembl_report.get("output_sha256") != hashlib.sha256(
        chembl_output_text.encode()
    ).hexdigest():
        return fail("ChEMBL extraction did not report the output hash")
    if (
        chembl_assay_description in chembl_output_text
        or chembl_functional_anchor in chembl_output_text
        or '"evidence"' in chembl_output_text
    ):
        return fail("ChEMBL extraction retained reviewer assay text")
    chembl_metadata = chembl_extracted_job["records"][0].get("metadata", {})
    if chembl_metadata.get("endpoint_value") != 12.0:
        return fail("ChEMBL extraction lost the typed endpoint")
    if chembl_metadata.get("source_lineage_ids") != [
        "chembl-document:CHEMBL9000012",
        "pubmed:99999991",
        "doi:10.1000/synthetic.chembl.activity",
    ]:
        return fail("ChEMBL extraction lost canonical publication lineage")

    expected_disease_model = {
        "status": "provider_job_extracted_requires_human_review",
        "provider_id": "ncbi_pubmed",
        "evidence_type": "disease_model_effect",
        "record_count": 1,
    }
    for key, value in expected_disease_model.items():
        if disease_model_report.get(key) != value:
            return fail(
                f"NCBI PubMed disease-model field {key!r} must be {value!r}"
            )
    if (
        disease_model_extracted_job.get("schema_version")
        != "adds.pinned-ingestion-job.v1"
    ):
        return fail("disease-model extraction did not emit a generic ingestion job")
    if disease_model_report.get("source_content_hash") != disease_model_source_hash:
        return fail("disease-model extraction lost the source content hash")
    if disease_model_report.get("output_sha256") != hashlib.sha256(
        disease_model_output_text.encode()
    ).hexdigest():
        return fail("disease-model extraction did not report the output hash")
    if (
        disease_model_result in disease_model_output_text
        or disease_model_conclusion in disease_model_output_text
        or '"evidence"' in disease_model_output_text
    ):
        return fail("disease-model extraction retained reviewer evidence text")
    disease_model_metadata = disease_model_extracted_job["records"][0].get(
        "metadata", {}
    )
    if disease_model_metadata.get("endpoint_value") != 90.0:
        return fail("disease-model extraction lost the typed endpoint")
    if disease_model_metadata.get("source_lineage_ids") != [
        "pubmed:99999992",
        "doi:10.1000/synthetic.disease-model",
    ]:
        return fail("disease-model extraction lost canonical publication lineage")

    expected_clinical = {
        "status": "provider_job_extracted_requires_human_review",
        "provider_id": "clinicaltrials_gov",
        "record_count": 1,
    }
    for key, value in expected_clinical.items():
        if clinical_report.get(key) != value:
            return fail(f"ClinicalTrials.gov field {key!r} must be {value!r}")
    if clinical_extracted_job.get("schema_version") != "adds.pinned-ingestion-job.v1":
        return fail("ClinicalTrials.gov extraction did not emit a generic ingestion job")
    if clinical_report.get("source_content_hash") != clinical_source_hash:
        return fail("ClinicalTrials.gov extraction lost the source content hash")
    if clinical_report.get("output_sha256") != hashlib.sha256(
        clinical_output_text.encode()
    ).hexdigest():
        return fail("ClinicalTrials.gov extraction did not report the output hash")
    if any(
        forbidden in clinical_output_text.casefold()
        for forbidden in ("protocolsection", "resultssection", "raw_payload")
    ):
        return fail("ClinicalTrials.gov extraction retained source payload structure")
    clinical_metadata = clinical_extracted_job["records"][0].get("metadata", {})
    if clinical_metadata.get("provider_id") != "clinicaltrials_gov":
        return fail("ClinicalTrials.gov extraction lost provider identity")
    clinical_context = clinical_extracted_job["records"][0].get(
        "biological_context", {}
    )
    if clinical_context.get("trial_id") != "NCT00000001":
        return fail("ClinicalTrials.gov extraction lost NCT identity")
    if [arm.get("role") for arm in clinical_metadata.get("arms", [])] != [
        "candidate",
        "comparator",
    ]:
        return fail("ClinicalTrials.gov extraction lost canonical arm roles")
    clinical_safety = clinical_metadata.get("safety", {})
    if clinical_safety.get("event_category") != "SERIOUS":
        return fail("ClinicalTrials.gov extraction lost the safety event category")
    if [arm.get("role") for arm in clinical_safety.get("arms", [])] != [
        "candidate",
        "comparator",
    ]:
        return fail("ClinicalTrials.gov extraction lost safety-arm continuity")

    expected_portfolio = {
        "status": "provider_portfolio_extracted_requires_human_review",
        "provider_id": "clinicaltrials_gov",
        "portfolio_id": "CHEMBL_TEST-MONDO_TEST-ctgov-portfolio-v1",
        "endpoint_mapping_id": "CHEMBL_TEST:MONDO_TEST:pfs-map:v1",
        "record_count": 2,
    }
    for key, value in expected_portfolio.items():
        if clinical_portfolio_report.get(key) != value:
            return fail(
                f"ClinicalTrials.gov portfolio field {key!r} must be {value!r}"
            )
    if clinical_portfolio_report.get("source_receipt_ids") != [
        "ctgov-test-trial",
        "ctgov-test-trial-2",
    ]:
        return fail("ClinicalTrials.gov portfolio lost exact receipt identities")
    if clinical_portfolio_report.get("source_content_hashes") != sorted(
        [clinical_source_hash, clinical_source_two_hash]
    ):
        return fail("ClinicalTrials.gov portfolio lost source content hashes")
    if clinical_portfolio_report.get("output_sha256") != hashlib.sha256(
        clinical_portfolio_output_text.encode()
    ).hexdigest():
        return fail("ClinicalTrials.gov portfolio did not report the output hash")
    if clinical_portfolio_job.get("schema_version") != "adds.pinned-ingestion-job.v1":
        return fail("ClinicalTrials.gov portfolio did not emit a generic ingestion job")
    portfolio_records = clinical_portfolio_job.get("records", [])
    if len(portfolio_records) != 2:
        return fail("ClinicalTrials.gov portfolio did not retain both trial records")
    expected_trial_ids = ["NCT00000001", "NCT00000002"]
    for index, record in enumerate(portfolio_records):
        portfolio_metadata = record.get("metadata", {}).get("clinical_portfolio", {})
        if portfolio_metadata.get("trial_index") != index:
            return fail("ClinicalTrials.gov portfolio lost canonical trial order")
        if portfolio_metadata.get("trial_count") != 2:
            return fail("ClinicalTrials.gov portfolio lost the exact trial count")
        if portfolio_metadata.get("automatic_endpoint_mapping_performed") is not False:
            return fail("ClinicalTrials.gov portfolio claimed automatic endpoint mapping")
        if record.get("biological_context", {}).get("trial_id") != expected_trial_ids[index]:
            return fail("ClinicalTrials.gov portfolio lost trial identity")
    if any(
        forbidden in clinical_portfolio_output_text.casefold()
        for forbidden in ("protocolsection", "resultssection", "raw_payload")
    ):
        return fail("ClinicalTrials.gov portfolio retained source payload structure")

    if sealed_api.stdout.strip() != "sealed-evaluation-api-ok":
        return fail("sealed evaluation API was not importable from the wheel")

    print(
        "PASS: isolated core wheel demo, bounded agent, replay, generic ingestion, and "
        "CDC MMWR, NCBI PubMed, ChEMBL activity, PubMed disease-model, and "
        "ClinicalTrials.gov endpoint/safety design and multi-trial portfolio extraction, "
        "plus sealed evaluation API smoke tests "
        f"completed for {wheels[0].name}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
