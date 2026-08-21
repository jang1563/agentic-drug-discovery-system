from __future__ import annotations

import hashlib
import json
import unittest
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from agentic_drug_discovery import (
    ClinicalRiskOfBiasDomainAssessment,
    ClinicalRiskOfBiasError,
    ClinicalRiskOfBiasReview,
    ClinicalRiskOfBiasSourceCitation,
    ClinicalRiskOfBiasSpec,
    ClinicalRiskOfBiasTrialAssessment,
    clinical_population_transport_report_from_json,
    clinical_population_transport_report_integrity_sha256,
    clinical_risk_of_bias_report_envelope,
    clinical_risk_of_bias_report_from_dict,
    clinical_risk_of_bias_spec_from_dict,
    clinical_risk_of_bias_spec_integrity_sha256,
    clinical_risk_of_bias_spec_to_dict,
    compile_clinical_risk_of_bias_report,
)


ROOT = Path(__file__).resolve().parents[1]
TRANSPORT_REPORT = ROOT / "docs/ra_olokizumab_mtx_ir_replication_report.json"
RISK_SPEC_SCHEMA = ROOT / "rl_env/specs/clinical_risk_of_bias_spec.schema.json"
RISK_REPORT_SCHEMA = ROOT / "rl_env/specs/clinical_risk_of_bias_report.schema.json"
REAL_RISK_SPEC = ROOT / "docs/ra_olokizumab_mtx_ir_risk_of_bias_spec.json"
REAL_RISK_REPORT = ROOT / "docs/ra_olokizumab_mtx_ir_risk_of_bias_report.json"


def _canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")
    return hashlib.sha256(payload).hexdigest()


def _registry_document(
    trial_id: str,
    candidate_started: int,
    comparator_started: int,
    comparator_group_suffix: str,
    *,
    candidate_denominator: int | None = None,
    primary_completion_date: str | None = None,
) -> dict[str, Any]:
    candidate_denominator = (
        candidate_started if candidate_denominator is None else candidate_denominator
    )
    primary_completion_date = primary_completion_date or (
        "2019-08-02" if trial_id.endswith("407") else "2018-08"
    )
    return {
        "protocolSection": {
            "identificationModule": {"nctId": trial_id},
            "statusModule": {
                "primaryCompletionDateStruct": {"date": primary_completion_date}
            },
            "designModule": {
                "designInfo": {
                    "allocation": "RANDOMIZED",
                    "interventionModel": "PARALLEL",
                    "maskingInfo": {
                        "masking": "DOUBLE",
                        "whoMasked": ["PARTICIPANT", "INVESTIGATOR"],
                    },
                }
            },
        },
        "resultsSection": {
            "participantFlowModule": {
                "periods": [
                    {
                        "title": "Overall Study",
                        "milestones": [
                            {
                                "type": "STARTED",
                                "achievements": [
                                    {
                                        "groupId": "FG000",
                                        "numSubjects": str(candidate_started),
                                    },
                                    {
                                        "groupId": f"FG{comparator_group_suffix}",
                                        "numSubjects": str(comparator_started),
                                    },
                                ],
                            }
                        ],
                    }
                ]
            },
            "outcomeMeasuresModule": {
                "outcomeMeasures": [
                    {
                        "type": "PRIMARY",
                        "title": "ACR20 response",
                        "description": "Week-12 ACR20 response while remaining on treatment and in study.",
                        "populationDescription": "All randomized participants were analyzed as assigned.",
                        "timeFrame": "at Week 12",
                        "denoms": [
                            {
                                "units": "Participants",
                                "counts": [
                                    {
                                        "groupId": "OG000",
                                        "value": str(candidate_denominator),
                                    },
                                    {
                                        "groupId": f"OG{comparator_group_suffix}",
                                        "value": str(comparator_started),
                                    },
                                ],
                            }
                        ],
                    }
                ]
            },
        },
    }


def _citation(
    citation_id: str,
    trial_id: str,
    registry_hash: str,
    pointer: str,
    value: Any,
) -> ClinicalRiskOfBiasSourceCitation:
    return ClinicalRiskOfBiasSourceCitation(
        citation_id=citation_id,
        source_role="registry_results",
        source_document_format="clinicaltrials.gov-study-v2",
        source_locator=f"https://clinicaltrials.gov/api/v2/studies/{trial_id}",
        source_content_sha256=registry_hash,
        source_field_pointer=pointer,
        source_field_sha256=_canonical_sha256(value),
    )


def _pdf_citation(
    citation_id: str,
    trial_id: str,
    pdf_hash: str,
    source_date: str,
    page: int,
    section: str,
) -> ClinicalRiskOfBiasSourceCitation:
    return ClinicalRiskOfBiasSourceCitation(
        citation_id=citation_id,
        source_role="protocol_sap",
        source_document_format="application/pdf",
        source_locator=(
            f"https://cdn.clinicaltrials.gov/large-docs/00/{trial_id}/Prot_SAP_000.pdf"
        ),
        source_content_sha256=pdf_hash,
        source_document_date=source_date,
        source_page=page,
        source_section=section,
    )


def _assessment(
    trial_id: str,
    registry: dict[str, Any],
    registry_hash: str,
    pdf_hash: str,
    comparator_group_suffix: str,
) -> ClinicalRiskOfBiasTrialAssessment:
    design = registry["protocolSection"]["designModule"]["designInfo"]
    flow = registry["resultsSection"]["participantFlowModule"]["periods"]
    outcome = registry["resultsSection"]["outcomeMeasuresModule"]["outcomeMeasures"][0]
    citations = (
        _citation(
            "registry_design",
            trial_id,
            registry_hash,
            "/protocolSection/designModule/designInfo",
            design,
        ),
        _citation(
            "registry_flow",
            trial_id,
            registry_hash,
            "/resultsSection/participantFlowModule/periods",
            flow,
        ),
        _citation(
            "registry_outcome",
            trial_id,
            registry_hash,
            "/resultsSection/outcomeMeasuresModule/outcomeMeasures/0",
            outcome,
        ),
        _pdf_citation(
            "protocol_randomization",
            trial_id,
            pdf_hash,
            "2018-03-30",
            10,
            "Method of Assigning Subjects to Treatment Group",
        ),
        _pdf_citation(
            "protocol_blinding",
            trial_id,
            pdf_hash,
            "2018-03-30",
            11,
            "Blinding",
        ),
        _pdf_citation(
            "protocol_measurement",
            trial_id,
            pdf_hash,
            "2018-03-30",
            12,
            "Schedule of Events",
        ),
        _pdf_citation(
            "sap_missing_data",
            trial_id,
            pdf_hash,
            "2018-03-30",
            20,
            "Handling of Missing Data",
        ),
        _pdf_citation(
            "sap_primary_analysis",
            trial_id,
            pdf_hash,
            "2018-03-30",
            19,
            "Primary Efficacy Analysis",
        ),
    )
    return ClinicalRiskOfBiasTrialAssessment(
        trial_id=trial_id,
        design_id=f"{trial_id}:design",
        endpoint_id=f"{trial_id}:endpoint:primary-0",
        candidate_result_group_id="OG000",
        comparator_result_group_id=f"OG{comparator_group_suffix}",
        candidate_flow_group_id="FG000",
        comparator_flow_group_id=f"FG{comparator_group_suffix}",
        citations=citations,
        domains=(
            ClinicalRiskOfBiasDomainAssessment(
                domain_id="randomization_process",
                judgment="low",
                rationale="Automated concealed allocation was documented for blinded staff.",
                citation_ids=("registry_design", "protocol_randomization"),
            ),
            ClinicalRiskOfBiasDomainAssessment(
                domain_id="deviations_from_intended_interventions",
                judgment="some_concerns",
                rationale="Masking was planned, but aggregate sources omit realized unblinding counts.",
                citation_ids=("registry_design", "protocol_blinding"),
            ),
            ClinicalRiskOfBiasDomainAssessment(
                domain_id="missing_outcome_data",
                judgment="low",
                rationale="The endpoint denominator includes every randomized participant in both arms.",
                citation_ids=("registry_flow", "sap_missing_data"),
            ),
            ClinicalRiskOfBiasDomainAssessment(
                domain_id="measurement_of_the_outcome",
                judgment="low",
                rationale="The prespecified ACR20 composite was measured under blinded procedures.",
                citation_ids=("registry_outcome", "protocol_measurement"),
            ),
            ClinicalRiskOfBiasDomainAssessment(
                domain_id="selection_of_the_reported_result",
                judgment="low",
                rationale="The primary outcome and analysis preceded completion and match posted results.",
                citation_ids=("registry_outcome", "sap_primary_analysis"),
            ),
        ),
        overall_judgment="some_concerns",
        unresolved_concerns=(
            "Aggregate public sources do not enumerate every realized unblinding or protocol deviation.",
        ),
    )


class ClinicalRiskOfBiasTest(unittest.TestCase):
    def _fixture(
        self,
        *,
        first_candidate_denominator: int | None = None,
        first_primary_completion_date: str | None = None,
    ) -> tuple[Any, dict[str, bytes], ClinicalRiskOfBiasSpec]:
        base = clinical_population_transport_report_from_json(
            TRANSPORT_REPORT.read_bytes()
        )
        registries = (
            _registry_document(
                "NCT02760407",
                479,
                243,
                "003",
                candidate_denominator=first_candidate_denominator,
                primary_completion_date=first_primary_completion_date,
            ),
            _registry_document("NCT02760368", 142, 143, "002"),
        )
        registry_payloads = tuple(
            json.dumps(item, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            for item in registries
        )
        registry_hashes = tuple(
            hashlib.sha256(item).hexdigest() for item in registry_payloads
        )
        pdf_payloads = (b"%PDF-1.7\nsynthetic-credo-2", b"%PDF-1.7\nsynthetic-credo-1")
        pdf_hashes = tuple(hashlib.sha256(item).hexdigest() for item in pdf_payloads)
        strata = tuple(
            replace(item, source_content_sha256=registry_hash)
            for item, registry_hash in zip(base.strata, registry_hashes, strict=True)
        )
        transport = replace(
            base,
            strata=strata,
            source_content_hashes=tuple(sorted(registry_hashes)),
        )
        assessments = (
            _assessment(
                "NCT02760407",
                registries[0],
                registry_hashes[0],
                pdf_hashes[0],
                "003",
            ),
            _assessment(
                "NCT02760368",
                registries[1],
                registry_hashes[1],
                pdf_hashes[1],
                "002",
            ),
        )
        spec = ClinicalRiskOfBiasSpec(
            analysis_id="CHEMBL1743050:MONDO:0008383:acr20-rob:v1",
            transport_analysis_id=transport.analysis_id,
            transport_report_integrity_sha256=(
                clinical_population_transport_report_integrity_sha256(transport)
            ),
            endpoint_family="acr20_response_week_12",
            outcome_time_frame="at Week 12",
            assessments=assessments,
            review=ClinicalRiskOfBiasReview(
                status="approved_for_project_internal_risk_of_bias",
                reviewer_id="project-scientific-owner",
                reviewer_role="project_scientific_owner",
                reviewed_at=datetime(2026, 8, 21, 16, tzinfo=timezone.utc),
            ),
        )
        documents = {
            registry_hash: payload
            for registry_hash, payload in zip(
                registry_hashes, registry_payloads, strict=True
            )
        }
        documents.update(
            {
                pdf_hash: payload
                for pdf_hash, payload in zip(pdf_hashes, pdf_payloads, strict=True)
            }
        )
        return transport, documents, spec

    def test_compiles_exact_sources_and_narrow_blocker_delta(self) -> None:
        transport, documents, spec = self._fixture()
        report = compile_clinical_risk_of_bias_report(transport, documents, spec)

        self.assertTrue(report.risk_of_bias_assessed)
        self.assertEqual(
            report.resolved_transportability_blockers,
            ("risk_of_bias_not_assessed",),
        )
        self.assertNotIn(
            "risk_of_bias_not_assessed", report.remaining_transportability_blockers
        )
        self.assertEqual(len(report.remaining_transportability_blockers), 4)
        self.assertEqual(
            [
                (item.candidate_started, item.comparator_started)
                for item in report.trials
            ],
            [(479, 243), (142, 143)],
        )
        self.assertTrue(
            all(item.primary_endpoint_denominator_complete for item in report.trials)
        )
        self.assertTrue(
            all(item.protocol_sap_precedes_primary_completion for item in report.trials)
        )
        self.assertEqual(
            {item.overall_judgment for item in report.trials}, {"some_concerns"}
        )
        self.assertFalse(report.pooling_performed)
        self.assertFalse(report.transport_effect_estimated)

        spec_payload = clinical_risk_of_bias_spec_to_dict(spec)
        self.assertEqual(
            clinical_risk_of_bias_spec_integrity_sha256(
                clinical_risk_of_bias_spec_from_dict(spec_payload)
            ),
            clinical_risk_of_bias_spec_integrity_sha256(spec),
        )
        envelope = clinical_risk_of_bias_report_envelope(report)
        self.assertEqual(clinical_risk_of_bias_report_from_dict(envelope), report)

    def test_rejects_registry_source_tampering(self) -> None:
        transport, documents, spec = self._fixture()
        registry_hash = spec.assessments[0].citations[0].source_content_sha256
        documents[registry_hash] += b" "
        with self.assertRaisesRegex(
            ClinicalRiskOfBiasError, "registry source hash changed"
        ):
            compile_clinical_risk_of_bias_report(transport, documents, spec)

    def test_rejects_reviewed_registry_field_rebinding(self) -> None:
        transport, documents, spec = self._fixture()
        first = spec.assessments[0]
        bad_citation = replace(first.citations[0], source_field_sha256="0" * 64)
        bad_assessment = replace(first, citations=(bad_citation, *first.citations[1:]))
        bad_spec = replace(spec, assessments=(bad_assessment, spec.assessments[1]))
        with self.assertRaisesRegex(
            ClinicalRiskOfBiasError, "reviewed registry field hash changed"
        ):
            compile_clinical_risk_of_bias_report(transport, documents, bad_spec)

    def test_rejects_low_missingness_judgment_with_incomplete_denominator(self) -> None:
        transport, documents, spec = self._fixture(first_candidate_denominator=478)
        with self.assertRaisesRegex(
            ClinicalRiskOfBiasError,
            "missing-outcome-data judgment cannot be low with incomplete denominators",
        ):
            compile_clinical_risk_of_bias_report(transport, documents, spec)

    def test_rejects_low_selection_judgment_when_partial_date_is_ambiguous(
        self,
    ) -> None:
        transport, documents, spec = self._fixture(
            first_primary_completion_date="2018-03"
        )
        with self.assertRaisesRegex(
            ClinicalRiskOfBiasError,
            "reported-result selection judgment cannot be low with a post-completion SAP",
        ):
            compile_clinical_risk_of_bias_report(transport, documents, spec)

    def test_rejects_noncanonical_json_pointer_array_index(self) -> None:
        transport, documents, spec = self._fixture()
        first = spec.assessments[0]
        outcome_citation = first.citations[2]
        bad_citation = replace(
            outcome_citation,
            source_field_pointer=(
                "/resultsSection/outcomeMeasuresModule/outcomeMeasures/-1"
            ),
        )
        bad_assessment = replace(
            first,
            citations=(*first.citations[:2], bad_citation, *first.citations[3:]),
        )
        bad_spec = replace(spec, assessments=(bad_assessment, spec.assessments[1]))
        with self.assertRaisesRegex(ClinicalRiskOfBiasError, "invalid array index"):
            compile_clinical_risk_of_bias_report(transport, documents, bad_spec)

    def test_rejects_report_integrity_tampering(self) -> None:
        transport, documents, spec = self._fixture()
        report = compile_clinical_risk_of_bias_report(transport, documents, spec)
        envelope = clinical_risk_of_bias_report_envelope(report)
        envelope["trials"][0]["candidate_started"] = 480
        with self.assertRaises(ClinicalRiskOfBiasError):
            clinical_risk_of_bias_report_from_dict(envelope)

    def test_real_assessment_is_schema_valid_and_narrowly_bounded(self) -> None:
        spec_payload = json.loads(REAL_RISK_SPEC.read_text(encoding="utf-8"))
        report_payload = json.loads(REAL_RISK_REPORT.read_text(encoding="utf-8"))
        for schema_path, payload in (
            (RISK_SPEC_SCHEMA, spec_payload),
            (RISK_REPORT_SCHEMA, report_payload),
        ):
            schema = json.loads(schema_path.read_text(encoding="utf-8"))
            Draft202012Validator.check_schema(schema)
            Draft202012Validator(schema, format_checker=FormatChecker()).validate(
                payload
            )

        spec = clinical_risk_of_bias_spec_from_dict(spec_payload)
        report = clinical_risk_of_bias_report_from_dict(report_payload)
        self.assertEqual(
            report.spec_sha256, clinical_risk_of_bias_spec_integrity_sha256(spec)
        )
        self.assertEqual(
            report.resolved_transportability_blockers,
            ("risk_of_bias_not_assessed",),
        )
        self.assertEqual(
            report.remaining_transportability_blockers,
            (
                "target_population_not_declared",
                "aggregate_registry_results_only",
                "individual_level_covariates_unavailable",
                "transport_model_not_preregistered",
            ),
        )
        trials = {item.trial_id: item for item in report.trials}
        self.assertEqual(set(trials), {"NCT02760407", "NCT02760368"})
        self.assertEqual(
            (
                trials["NCT02760407"].candidate_primary_endpoint_denominator,
                trials["NCT02760407"].comparator_primary_endpoint_denominator,
            ),
            (479, 243),
        )
        self.assertEqual(
            (
                trials["NCT02760368"].candidate_primary_endpoint_denominator,
                trials["NCT02760368"].comparator_primary_endpoint_denominator,
            ),
            (142, 143),
        )
        self.assertTrue(
            all(item.primary_endpoint_denominator_complete for item in trials.values())
        )
        self.assertTrue(
            all(
                item.protocol_sap_precedes_primary_completion
                for item in trials.values()
            )
        )
        self.assertEqual(
            {item.overall_judgment for item in trials.values()}, {"some_concerns"}
        )
        self.assertFalse(report.pooling_performed)
        self.assertFalse(report.transport_effect_estimated)
        self.assertFalse(report.treatment_recommendation_supported)
        self.assertFalse(report.independent_external_review_completed)

        encoded = REAL_RISK_REPORT.read_text(encoding="utf-8")
        self.assertNotRegex(encoded, r"/(Users|home|tmp|private)/")
        self.assertNotIn("raw_payload", encoded)


if __name__ == "__main__":
    unittest.main()
