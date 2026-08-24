from __future__ import annotations

import copy
import hashlib
import json
import unittest
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

from jsonschema import Draft202012Validator

from agentic_drug_discovery import (
    ClinicalEndpointOntology,
    ClinicalEndpointSelection,
    ClinicalStudySelection,
    Decision,
    StageRunStatus,
)
from agentic_drug_discovery.clinical_benefit_risk_portfolio import (
    compile_clinical_benefit_risk_portfolio,
)
from agentic_drug_discovery.clinical_benefit_risk_portfolio_stress import (
    ClinicalBenefitRiskPortfolioStressError,
    clinical_benefit_risk_portfolio_stress_report_envelope,
    clinical_benefit_risk_portfolio_stress_report_from_dict,
    clinical_benefit_risk_portfolio_stress_report_from_json,
    clinical_benefit_risk_portfolio_stress_report_summary,
    compile_clinical_benefit_risk_portfolio_stress_report,
    validate_clinical_benefit_risk_portfolio_stress_report,
)
from tests.test_clinical_benefit_risk_portfolio import (
    _commit_two_domains,
    _portfolio_spec,
    _selection,
    _study_selection,
    _unmapped_state,
)
from tests.test_clinical_benefit_risk_synthesis import (
    COMPLETED_AT,
    MAPPING_COMPLETED_AT,
    MAPPING_REQUEST_AT,
    REQUEST_AT,
    _mapping_spec,
    _run_mapping,
    _run_synthesis,
    _spec,
)


ROOT = Path(__file__).resolve().parents[1]
REPORT_SCHEMA = (
    ROOT
    / "rl_env/specs/clinical_benefit_risk_portfolio_stress_report.schema.json"
)


def _secondary_endpoint_selections(
    trial_ids: tuple[str, ...],
) -> tuple[ClinicalEndpointSelection, ...]:
    return tuple(
        ClinicalEndpointSelection(
            trial_id=trial_id,
            design_id=f"{trial_id}:design",
            endpoint_id=f"{trial_id}:endpoint:secondary-0",
            safety_id=f"{trial_id}:safety:serious-adverse-events",
        )
        for trial_id in trial_ids
    )


def _secondary_study_selections(
    trial_ids: tuple[str, ...],
) -> tuple[ClinicalStudySelection, ...]:
    return tuple(
        ClinicalStudySelection(
            trial_id=item.trial_id,
            design_id=item.design_id,
            endpoint_id=item.endpoint_id,
            safety_id=item.safety_id,
        )
        for item in _secondary_endpoint_selections(trial_ids)
    )


def _phase_bound_multi_endpoint_design(
    design,
    evidence_by_id,
    *,
    population_mismatch: bool,
    timeframe_mismatch: bool,
):
    endpoint = design.endpoints[0]
    population = next(
        item
        for item in design.populations
        if item.population_id == endpoint.population_id
    )
    safety = design.safety_records[0]
    endpoint_counts = {
        arm.role.value: arm.attributes["measurement"]["denominator"]
        for arm in design.arms
        if arm.arm_id in endpoint.arm_ids
    }
    safety_counts = {
        item.role.value: item.serious_num_at_risk for item in safety.arm_summaries
    }
    alignment = {
        "treatment_phase": "maintenance",
        "study_enrollment_count": population.enrollment_count,
        "endpoint_analysis_participant_count": sum(endpoint_counts.values()),
        "safety_at_risk_participant_count": sum(safety_counts.values()),
        "rolewise_counts_match": endpoint_counts == safety_counts,
        "same_participants_inferred": False,
    }
    phase_attributes = {
        "treatment_phase": "maintenance",
        "population_alignment": alignment,
    }
    primary_population = replace(
        population,
        attributes={**dict(population.attributes), **phase_attributes},
    )
    primary_endpoint = replace(
        endpoint,
        attributes={**dict(endpoint.attributes), **phase_attributes},
    )
    secondary_endpoint_id = f"{design.trial_id}:endpoint:secondary-0"
    secondary_population_evidence = []
    populations = [primary_population]
    secondary_population_id = primary_population.population_id
    if population_mismatch:
        secondary_population_id = f"{design.trial_id}:population:secondary"
        population_evidence = evidence_by_id[population.supporting_evidence[0]]
        secondary_population_evidence.append(
            replace(
                population_evidence,
                evidence_id=f"{population_evidence.evidence_id}:secondary",
                object_value=secondary_population_id,
                biological_context={
                    **dict(population_evidence.biological_context),
                    "population_id": secondary_population_id,
                },
            )
        )
        populations.append(
            replace(
                primary_population,
                population_id=secondary_population_id,
                description=(
                    f"Synthetic secondary analysis population for {design.trial_id}"
                ),
                identifiers={"canonical": secondary_population_id},
                supporting_evidence=tuple(
                    item.evidence_id for item in secondary_population_evidence
                ),
            )
        )
    secondary_endpoint_evidence = []
    for evidence_id in endpoint.supporting_evidence:
        source_event = evidence_by_id[evidence_id]
        secondary_endpoint_evidence.append(
            replace(
                source_event,
                evidence_id=f"{source_event.evidence_id}:secondary",
                object_value=(
                    secondary_endpoint_id
                    if source_event.predicate
                    == "clinical_trial_endpoint_identity_resolved"
                    else source_event.object_value
                ),
                biological_context={
                    **dict(source_event.biological_context),
                    "population_id": secondary_population_id,
                    "endpoint_id": secondary_endpoint_id,
                },
                metadata={
                    **dict(source_event.metadata),
                    **(
                        {
                            "name": "Synthetic overall survival endpoint",
                            "time_frame": (
                                "36 months"
                                if timeframe_mismatch
                                else endpoint.time_frame
                            ),
                        }
                        if source_event.predicate
                        == "clinical_trial_endpoint_identity_resolved"
                        else {}
                    ),
                },
            )
        )
    secondary_endpoint = replace(
        primary_endpoint,
        endpoint_id=secondary_endpoint_id,
        population_id=secondary_population_id,
        name="Synthetic overall survival endpoint",
        time_frame=("36 months" if timeframe_mismatch else endpoint.time_frame),
        identifiers={
            "canonical": secondary_endpoint_id,
            "clinicaltrials_gov_outcome": f"{design.trial_id}:outcome:1",
        },
        supporting_evidence=tuple(
            item.evidence_id for item in secondary_endpoint_evidence
        ),
    )
    phase_bound_safety = replace(
        safety,
        attributes={**dict(safety.attributes), **phase_attributes},
    )
    cloned_evidence = tuple(
        (*secondary_population_evidence, *secondary_endpoint_evidence)
    )
    transformed = replace(
        design,
        populations=tuple(populations),
        endpoints=(primary_endpoint, secondary_endpoint),
        safety_records=(phase_bound_safety,),
        supporting_evidence=(
            *design.supporting_evidence,
            *(item.evidence_id for item in cloned_evidence),
        ),
        attributes={**dict(design.attributes), **phase_attributes},
    )
    return transformed, cloned_evidence


def _commit_same_trial_distinct_endpoints(
    *,
    population_mismatch: bool = False,
    timeframe_mismatch: bool = False,
):
    trial_ids = ("NCT00000001", "NCT00000002")
    state = _unmapped_state(trial_ids)
    transformed = tuple(
        _phase_bound_multi_endpoint_design(
            design,
            state.evidence_by_id,
            population_mismatch=population_mismatch,
            timeframe_mismatch=timeframe_mismatch,
        )
        for design in state.trial_designs
    )
    state = replace(
        state,
        evidence=(
            *state.evidence,
            *(event for _, events in transformed for event in events),
        ),
        trial_designs=tuple(design for design, _ in transformed),
    )
    first_mapping = replace(
        _mapping_spec(),
        portfolio_id="CHEMBL_TEST:MONDO_TEST:same-trial-stress-mappings:v1",
        bindings=_selection(trial_ids),
    )
    second_mapping = replace(
        _mapping_spec(),
        mapping_id="CHEMBL_TEST:MONDO_TEST:stress-os-map:v1",
        portfolio_id="CHEMBL_TEST:MONDO_TEST:same-trial-stress-mappings:v1",
        endpoint_family_id="overall_survival",
        endpoint_family_label="Overall survival",
        ontology=ClinicalEndpointOntology(
            system="urn:adds:synthetic-endpoint-ontology",
            version="1.0",
            code="OS",
            label="Overall survival",
        ),
        bindings=_secondary_endpoint_selections(trial_ids),
    )
    first_mapping_result, _ = _run_mapping(state, first_mapping)
    if first_mapping_result.status is not StageRunStatus.COMMITTED:
        raise AssertionError(first_mapping_result.code)
    second_mapping_result, _ = _run_mapping(
        first_mapping_result.final_state,
        second_mapping,
        request_at=MAPPING_REQUEST_AT + timedelta(minutes=3),
        completed_at=MAPPING_COMPLETED_AT + timedelta(minutes=3),
    )
    if second_mapping_result.status is not StageRunStatus.COMMITTED:
        raise AssertionError(second_mapping_result.code)

    first_synthesis = replace(
        _spec(),
        selections=_study_selection(trial_ids),
    )
    second_synthesis = replace(
        _spec(),
        synthesis_id="CHEMBL_TEST:MONDO_TEST:stress-os-benefit-risk:v1",
        endpoint_mapping_id=second_mapping.mapping_id,
        endpoint_family=second_mapping.endpoint_family_id,
        selections=_secondary_study_selections(trial_ids),
    )
    first_synthesis_result, _ = _run_synthesis(
        second_mapping_result.final_state,
        first_synthesis,
        request_at=REQUEST_AT + timedelta(minutes=10),
        completed_at=COMPLETED_AT + timedelta(minutes=10),
        success_decision=Decision.HOLD,
    )
    if first_synthesis_result.status is not StageRunStatus.COMMITTED:
        raise AssertionError(first_synthesis_result.code)
    second_synthesis_result, _ = _run_synthesis(
        first_synthesis_result.final_state,
        second_synthesis,
        request_at=REQUEST_AT + timedelta(minutes=20),
        completed_at=COMPLETED_AT + timedelta(minutes=20),
        success_decision=Decision.HOLD,
    )
    if second_synthesis_result.status is not StageRunStatus.COMMITTED:
        raise AssertionError(second_synthesis_result.code)
    final_state = second_synthesis_result.final_state
    final_state.validate_committed_history()
    synthesis_ids = tuple(
        sorted((first_synthesis.synthesis_id, second_synthesis.synthesis_id))
    )
    return final_state, synthesis_ids


def _compile_stress(state, synthesis_ids, *, distinct: bool = True):
    portfolio_spec = _portfolio_spec(
        synthesis_ids,
        require_distinct_endpoint_records=distinct,
    )
    portfolio_report = compile_clinical_benefit_risk_portfolio(
        state,
        portfolio_spec,
    )
    stress_report = compile_clinical_benefit_risk_portfolio_stress_report(
        state,
        portfolio_spec,
        portfolio_report,
    )
    return portfolio_spec, portfolio_report, stress_report


class ClinicalBenefitRiskPortfolioStressTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.matched_state, cls.matched_synthesis_ids = (
            _commit_same_trial_distinct_endpoints()
        )
        cls.heterogeneous_state, cls.heterogeneous_synthesis_ids = (
            _commit_same_trial_distinct_endpoints(
                population_mismatch=True,
                timeframe_mismatch=True,
            )
        )
        cls.reused_state, cls.reused_synthesis_ids = _commit_two_domains(
            overlap=True
        )
        cls.disjoint_state, cls.disjoint_synthesis_ids = _commit_two_domains(
            overlap=False
        )

    def test_matched_structure_retains_shared_safety_without_independence(self) -> None:
        spec, portfolio, report = _compile_stress(
            self.matched_state,
            self.matched_synthesis_ids,
        )

        self.assertEqual(report.same_trial_pair_count, 2)
        self.assertEqual(report.matched_structure_pair_count, 2)
        self.assertEqual(report.phase_undeclared_pair_count, 0)
        self.assertEqual(report.heterogeneous_structure_pair_count, 0)
        self.assertEqual(report.endpoint_record_reuse_pair_count, 0)
        self.assertEqual(report.population_alignment_mismatch_pair_count, 0)
        self.assertEqual(report.safety_unit_reuse_pair_count, 2)
        self.assertEqual(report.exact_source_overlap_pair_count, 2)
        self.assertFalse(report.shared_safety_counted_as_independent)
        self.assertFalse(report.clinical_comparability_inferred)
        self.assertFalse(report.endpoint_exchangeability_inferred)
        self.assertFalse(report.safety_independence_inferred)
        self.assertEqual(
            validate_clinical_benefit_risk_portfolio_stress_report(
                self.matched_state,
                spec,
                portfolio,
                report,
            ),
            (),
        )

    def test_population_and_endpoint_timeframe_heterogeneity_are_separate(self) -> None:
        _, _, report = _compile_stress(
            self.heterogeneous_state,
            self.heterogeneous_synthesis_ids,
        )

        self.assertEqual(report.same_trial_pair_count, 2)
        self.assertEqual(report.heterogeneous_structure_pair_count, 2)
        self.assertEqual(report.population_identity_mismatch_pair_count, 2)
        self.assertEqual(report.endpoint_timeframe_mismatch_pair_count, 2)
        self.assertEqual(report.treatment_phase_mismatch_pair_count, 0)
        self.assertEqual(report.safety_unit_reuse_pair_count, 2)
        self.assertTrue(
            all(
                "analysis_population_identity_mismatch" in item.diagnostic_codes
                and "endpoint_timeframe_mismatch" in item.diagnostic_codes
                for item in report.pairwise_cells
            )
        )

    def test_endpoint_relabeling_remains_visible_in_diagnostic_portfolio(self) -> None:
        _, _, report = _compile_stress(
            self.reused_state,
            self.reused_synthesis_ids,
            distinct=False,
        )

        self.assertEqual(report.endpoint_record_reuse_pair_count, 2)
        self.assertEqual(report.heterogeneous_structure_pair_count, 2)
        self.assertEqual(report.phase_undeclared_pair_count, 0)
        self.assertTrue(
            all(
                "endpoint_record_reused" in item.diagnostic_codes
                and "treatment_phase_not_declared" in item.diagnostic_codes
                for item in report.pairwise_cells
            )
        )

    def test_disjoint_trial_domains_do_not_fake_same_trial_stress(self) -> None:
        spec = _portfolio_spec(self.disjoint_synthesis_ids)
        portfolio = compile_clinical_benefit_risk_portfolio(
            self.disjoint_state,
            spec,
        )
        with self.assertRaisesRegex(
            ClinicalBenefitRiskPortfolioStressError,
            "no same-trial endpoint-domain pairs",
        ):
            compile_clinical_benefit_risk_portfolio_stress_report(
                self.disjoint_state,
                spec,
                portfolio,
            )

    def test_report_schema_roundtrip_and_summary(self) -> None:
        _, _, report = _compile_stress(
            self.matched_state,
            self.matched_synthesis_ids,
        )
        schema = json.loads(REPORT_SCHEMA.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        envelope = clinical_benefit_risk_portfolio_stress_report_envelope(report)
        Draft202012Validator(schema).validate(envelope)
        self.assertEqual(
            clinical_benefit_risk_portfolio_stress_report_from_dict(envelope),
            report,
        )
        self.assertEqual(
            clinical_benefit_risk_portfolio_stress_report_from_json(
                json.dumps(envelope, sort_keys=True)
            ),
            report,
        )
        summary = clinical_benefit_risk_portfolio_stress_report_summary(report)
        self.assertEqual(summary["same_trial_pair_count"], 2)
        self.assertEqual(summary["integrity_sha256"], report.fingerprint)

    def test_rehashed_derived_field_tampering_fails_parser(self) -> None:
        _, _, report = _compile_stress(
            self.matched_state,
            self.matched_synthesis_ids,
        )
        envelope = copy.deepcopy(
            clinical_benefit_risk_portfolio_stress_report_envelope(report)
        )
        envelope["report"]["pairwise_cells"][0]["shared_safety_unit"] = False
        encoded = json.dumps(
            envelope["report"],
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
        envelope["integrity_sha256"] = hashlib.sha256(encoded).hexdigest()
        with self.assertRaisesRegex(ValueError, "shared_safety_unit"):
            clinical_benefit_risk_portfolio_stress_report_from_dict(envelope)

        alignment_envelope = copy.deepcopy(
            clinical_benefit_risk_portfolio_stress_report_envelope(report)
        )
        alignment_envelope["report"]["pairwise_cells"][0]["right"][
            "population_alignment_sha256"
        ] = "0" * 64
        alignment_encoded = json.dumps(
            alignment_envelope["report"],
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
        alignment_envelope["integrity_sha256"] = hashlib.sha256(
            alignment_encoded
        ).hexdigest()
        with self.assertRaisesRegex(ValueError, "shared_population_alignment"):
            clinical_benefit_risk_portfolio_stress_report_from_dict(
                alignment_envelope
            )

    def test_full_recompile_detects_report_binding_tampering(self) -> None:
        spec, portfolio, report = _compile_stress(
            self.matched_state,
            self.matched_synthesis_ids,
        )
        tampered = replace(report, portfolio_report_sha256="0" * 64)
        self.assertEqual(
            validate_clinical_benefit_risk_portfolio_stress_report(
                self.matched_state,
                spec,
                portfolio,
                tampered,
            ),
            ("portfolio_stress_recompiled_report_mismatch",),
        )


if __name__ == "__main__":
    unittest.main()
