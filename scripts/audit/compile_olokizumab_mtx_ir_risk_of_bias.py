#!/usr/bin/env python3
"""Compile the reviewed olokizumab MTX-IR ACR20 risk-of-bias assessment."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agentic_drug_discovery import (  # noqa: E402
    ClinicalRiskOfBiasDomainAssessment,
    ClinicalRiskOfBiasReview,
    ClinicalRiskOfBiasSourceCitation,
    ClinicalRiskOfBiasSpec,
    ClinicalRiskOfBiasTrialAssessment,
    clinical_population_transport_report_from_json,
    clinical_population_transport_report_integrity_sha256,
    clinical_risk_of_bias_report_envelope,
    clinical_risk_of_bias_spec_to_dict,
    compile_clinical_risk_of_bias_report,
)


TRANSPORT_REPORT = ROOT / "docs/ra_olokizumab_mtx_ir_replication_report.json"
REGISTRY_POINTERS = {
    "design": "/protocolSection/designModule/designInfo",
    "flow": "/resultsSection/participantFlowModule/periods",
    "outcome": "/resultsSection/outcomeMeasuresModule/outcomeMeasures/0",
}
TRIAL_CONFIG = {
    "NCT02760407": {
        "document_date": "2018-05-28",
        "candidate_group": "000",
        "comparator_group": "003",
        "pages": {
            "randomization": 89,
            "blinding": 95,
            "measurement": 54,
            "missing": 143,
            "analysis": 141,
        },
    },
    "NCT02760368": {
        "document_date": "2018-03-30",
        "candidate_group": "000",
        "comparator_group": "002",
        "pages": {
            "randomization": 96,
            "blinding": 101,
            "measurement": 53,
            "missing": 152,
            "analysis": 151,
        },
    },
}


def _canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")
    return hashlib.sha256(payload).hexdigest()


def _json_pointer(document: Any, pointer: str) -> Any:
    current = document
    for token in pointer[1:].split("/"):
        token = token.replace("~1", "/").replace("~0", "~")
        current = current[int(token)] if isinstance(current, list) else current[token]
    return current


def _registry_citation(
    citation_id: str,
    trial_id: str,
    source_hash: str,
    pointer: str,
    document: dict[str, Any],
) -> ClinicalRiskOfBiasSourceCitation:
    return ClinicalRiskOfBiasSourceCitation(
        citation_id=citation_id,
        source_role="registry_results",
        source_document_format="clinicaltrials.gov-study-v2",
        source_locator=f"https://clinicaltrials.gov/api/v2/studies/{trial_id}",
        source_content_sha256=source_hash,
        source_field_pointer=pointer,
        source_field_sha256=_canonical_sha256(_json_pointer(document, pointer)),
    )


def _pdf_citation(
    citation_id: str,
    trial_id: str,
    source_hash: str,
    document_date: str,
    page: int,
    section: str,
) -> ClinicalRiskOfBiasSourceCitation:
    suffix = trial_id[-2:]
    return ClinicalRiskOfBiasSourceCitation(
        citation_id=citation_id,
        source_role="protocol_sap",
        source_document_format="application/pdf",
        source_locator=(
            f"https://cdn.clinicaltrials.gov/large-docs/{suffix}/"
            f"{trial_id}/Prot_SAP_000.pdf"
        ),
        source_content_sha256=source_hash,
        source_document_date=document_date,
        source_page=page,
        source_section=section,
    )


def _assessment(
    trial_id: str,
    registry_payload: bytes,
    pdf_payload: bytes,
) -> ClinicalRiskOfBiasTrialAssessment:
    config = TRIAL_CONFIG[trial_id]
    document = json.loads(registry_payload)
    registry_hash = hashlib.sha256(registry_payload).hexdigest()
    pdf_hash = hashlib.sha256(pdf_payload).hexdigest()
    pages = config["pages"]
    citations = (
        _registry_citation(
            "registry_design",
            trial_id,
            registry_hash,
            REGISTRY_POINTERS["design"],
            document,
        ),
        _registry_citation(
            "registry_flow",
            trial_id,
            registry_hash,
            REGISTRY_POINTERS["flow"],
            document,
        ),
        _registry_citation(
            "registry_outcome",
            trial_id,
            registry_hash,
            REGISTRY_POINTERS["outcome"],
            document,
        ),
        _pdf_citation(
            "protocol_randomization",
            trial_id,
            pdf_hash,
            config["document_date"],
            pages["randomization"],
            "6.5 Method of Assigning Subjects to Treatment Group",
        ),
        _pdf_citation(
            "protocol_blinding",
            trial_id,
            pdf_hash,
            config["document_date"],
            pages["blinding"],
            "6.12 Blinding",
        ),
        _pdf_citation(
            "protocol_measurement",
            trial_id,
            pdf_hash,
            config["document_date"],
            pages["measurement"],
            "Schedule of Events joint-assessor footnote",
        ),
        _pdf_citation(
            "sap_missing_data",
            trial_id,
            pdf_hash,
            config["document_date"],
            pages["missing"],
            "9.4.9.1 Primary Analysis of Efficacy Endpoints",
        ),
        _pdf_citation(
            "sap_primary_analysis",
            trial_id,
            pdf_hash,
            config["document_date"],
            pages["analysis"],
            "9.4.7 Primary Efficacy Analysis",
        ),
    )
    return ClinicalRiskOfBiasTrialAssessment(
        trial_id=trial_id,
        design_id=f"{trial_id}:design",
        endpoint_id=f"{trial_id}:endpoint:primary-0",
        candidate_result_group_id=f"OG{config['candidate_group']}",
        comparator_result_group_id=f"OG{config['comparator_group']}",
        candidate_flow_group_id=f"FG{config['candidate_group']}",
        comparator_flow_group_id=f"FG{config['comparator_group']}",
        citations=citations,
        domains=(
            ClinicalRiskOfBiasDomainAssessment(
                domain_id="randomization_process",
                judgment="some_concerns",
                rationale=(
                    "The registry and protocol document randomized parallel assignment by "
                    "blinded staff through automated IWRS allocation. Public sources do not "
                    "provide the sequence-generation algorithm or an allocation audit."
                ),
                citation_ids=("registry_design", "protocol_randomization"),
            ),
            ClinicalRiskOfBiasDomainAssessment(
                domain_id="deviations_from_intended_interventions",
                judgment="some_concerns",
                rationale=(
                    "Participant and investigator masking, matched injections, and restricted "
                    "treatment-code access were planned. Aggregate public sources do not "
                    "enumerate realized unblinding or all important protocol deviations."
                ),
                citation_ids=("registry_design", "protocol_blinding"),
            ),
            ClinicalRiskOfBiasDomainAssessment(
                domain_id="missing_outcome_data",
                judgment="low",
                rationale=(
                    "The Week-12 ACR20 denominators equal the randomized STARTED counts in "
                    "both selected arms, and the SAP classifies premature discontinuation as "
                    "non-response for binary endpoints."
                ),
                citation_ids=("registry_flow", "sap_missing_data"),
            ),
            ClinicalRiskOfBiasDomainAssessment(
                domain_id="measurement_of_the_outcome",
                judgment="low",
                rationale=(
                    "The posted ACR20 definition matches the prespecified composite, and the "
                    "protocol assigns joint counts to an independent assessor blinded to "
                    "other assessments and dose regimen."
                ),
                citation_ids=("registry_outcome", "protocol_measurement"),
            ),
            ClinicalRiskOfBiasDomainAssessment(
                domain_id="selection_of_the_reported_result",
                judgment="low",
                rationale=(
                    "The dated protocol/SAP precedes primary completion and prespecifies the "
                    "Week-12 ACR20 ITT analysis, multiplicity control, risk difference, and "
                    "97.5% two-sided interval reported in the registry."
                ),
                citation_ids=("registry_outcome", "sap_primary_analysis"),
            ),
        ),
        overall_judgment="some_concerns",
        unresolved_concerns=(
            "The public protocol/SAP does not disclose the IWRS sequence-generation algorithm or allocation audit.",
            "Aggregate public sources do not enumerate realized unblinding or all important protocol deviations.",
        ),
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    for trial_id in TRIAL_CONFIG:
        option = trial_id.lower()
        parser.add_argument(f"--{option}-registry", type=Path, required=True)
        parser.add_argument(f"--{option}-protocol-sap", type=Path, required=True)
    parser.add_argument("--reviewed-at", required=True)
    parser.add_argument("--spec-output", type=Path, required=True)
    parser.add_argument("--report-output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    reviewed_at = datetime.fromisoformat(args.reviewed_at.replace("Z", "+00:00"))
    if reviewed_at.tzinfo is None or reviewed_at.utcoffset() is None:
        raise ValueError("--reviewed-at must be timezone-aware")
    transport = clinical_population_transport_report_from_json(
        TRANSPORT_REPORT.read_bytes()
    )
    registry_payloads: dict[str, bytes] = {}
    pdf_payloads: dict[str, bytes] = {}
    for trial_id in TRIAL_CONFIG:
        option = trial_id.lower()
        registry_payloads[trial_id] = getattr(args, f"{option}_registry").read_bytes()
        pdf_payloads[trial_id] = getattr(args, f"{option}_protocol_sap").read_bytes()
    assessments = tuple(
        _assessment(trial_id, registry_payloads[trial_id], pdf_payloads[trial_id])
        for trial_id in TRIAL_CONFIG
    )
    spec = ClinicalRiskOfBiasSpec(
        analysis_id="CHEMBL1743050:MONDO:0008383:acr20-mtx-ir-risk-of-bias:v1",
        transport_analysis_id=transport.analysis_id,
        transport_report_integrity_sha256=(
            clinical_population_transport_report_integrity_sha256(transport)
        ),
        endpoint_family=transport.endpoint_family,
        outcome_time_frame="at Week 12",
        assessments=assessments,
        review=ClinicalRiskOfBiasReview(
            status="approved_for_project_internal_risk_of_bias",
            reviewer_id="project-scientific-owner",
            reviewer_role="project_scientific_owner",
            reviewed_at=reviewed_at,
        ),
    )
    sources = {
        hashlib.sha256(payload).hexdigest(): payload
        for payload in (*registry_payloads.values(), *pdf_payloads.values())
    }
    report = compile_clinical_risk_of_bias_report(transport, sources, spec)
    args.spec_output.parent.mkdir(parents=True, exist_ok=True)
    args.report_output.parent.mkdir(parents=True, exist_ok=True)
    args.spec_output.write_text(
        json.dumps(
            clinical_risk_of_bias_spec_to_dict(spec), indent=2, ensure_ascii=False
        )
        + "\n",
        encoding="utf-8",
    )
    args.report_output.write_text(
        json.dumps(
            clinical_risk_of_bias_report_envelope(report), indent=2, ensure_ascii=False
        )
        + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "analysis_id": report.analysis_id,
                "spec_sha256": report.spec_sha256,
                "report_integrity_sha256": (
                    clinical_risk_of_bias_report_envelope(report)["integrity_sha256"]
                ),
                "trial_judgments": {
                    item.trial_id: item.overall_judgment for item in report.trials
                },
                "resolved_transportability_blockers": (
                    report.resolved_transportability_blockers
                ),
                "remaining_transportability_blockers": (
                    report.remaining_transportability_blockers
                ),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
