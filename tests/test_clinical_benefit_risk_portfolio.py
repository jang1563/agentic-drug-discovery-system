from __future__ import annotations

import copy
import hashlib
import json
import unittest
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

from jsonschema import Draft202012Validator

from agentic_drug_discovery.clinical_benefit_risk_portfolio import (
    ClinicalBenefitRiskPortfolioError,
    ClinicalBenefitRiskPortfolioSpec,
    clinical_benefit_risk_portfolio_report_envelope,
    clinical_benefit_risk_portfolio_report_from_dict,
    clinical_benefit_risk_portfolio_report_from_json,
    clinical_benefit_risk_portfolio_report_summary,
    clinical_benefit_risk_portfolio_spec_envelope,
    clinical_benefit_risk_portfolio_spec_from_dict,
    clinical_benefit_risk_portfolio_spec_from_json,
    compile_clinical_benefit_risk_portfolio,
    validate_clinical_benefit_risk_portfolio,
)
from agentic_drug_discovery.models import (
    BudgetState,
    ClinicalEndpointMappingRecord,
    ProgramState,
    Stage,
)
from agentic_drug_discovery import (
    ClinicalEndpointOntology,
    ClinicalEndpointSelection,
    ClinicalStudySelection,
    Decision,
    StageRunStatus,
)
from tests.test_clinical_benefit_risk_synthesis import (
    COMPLETED_AT,
    MAPPING_COMPLETED_AT,
    MAPPING_REQUEST_AT,
    REQUEST_AT,
    _mapping_spec,
    _run_clinical_trial,
    _run_mapping,
    _run_synthesis,
    _spec,
)


ROOT = Path(__file__).resolve().parents[1]
SPEC_SCHEMA = ROOT / "rl_env/specs/clinical_benefit_risk_portfolio_spec.schema.json"
REPORT_SCHEMA = (
    ROOT / "rl_env/specs/clinical_benefit_risk_portfolio_report.schema.json"
)


def _selection(trial_ids: tuple[str, ...]) -> tuple[ClinicalEndpointSelection, ...]:
    return tuple(
        ClinicalEndpointSelection(
            trial_id=trial_id,
            design_id=f"{trial_id}:design",
            endpoint_id=f"{trial_id}:endpoint:primary-0",
            safety_id=f"{trial_id}:safety:serious-adverse-events",
        )
        for trial_id in trial_ids
    )


def _study_selection(trial_ids: tuple[str, ...]) -> tuple[ClinicalStudySelection, ...]:
    return tuple(
        ClinicalStudySelection(
            trial_id=item.trial_id,
            design_id=item.design_id,
            endpoint_id=item.endpoint_id,
            safety_id=item.safety_id,
        )
        for item in _selection(trial_ids)
    )


def _unmapped_state(trial_ids: tuple[str, ...]) -> ProgramState:
    states = tuple(
        _run_clinical_trial(trial_id, f"portfolio-{index}")
        for index, trial_id in enumerate(trial_ids, start=1)
    )
    first = states[0]
    first_intervention = first.interventions[0]
    merged_intervention = replace(
        first_intervention,
        supporting_evidence=tuple(
            dict.fromkeys(
                evidence_id
                for state in states
                for evidence_id in state.interventions[0].supporting_evidence
            )
        ),
        attributes={
            **dict(first_intervention.attributes),
            "clinical_trial_ids": sorted(
                trial.trial_id for state in states for trial in state.trials
            ),
        },
    )
    return ProgramState(
        program_id="multi-endpoint-benefit-risk-program",
        disease=first.disease,
        therapeutic_hypothesis=first.therapeutic_hypothesis,
        as_of_date=first.as_of_date,
        current_stage=Stage.REGULATORY_POSTMARKET,
        budget=BudgetState(limit=5.0),
        evidence=tuple(item for state in states for item in state.evidence),
        claims=tuple(item for state in states for item in state.claims),
        diseases=first.diseases,
        targets=first.targets,
        candidates=first.candidates,
        interventions=(merged_intervention,),
        trials=tuple(item for state in states for item in state.trials),
        trial_designs=tuple(
            item for state in states for item in state.trial_designs
        ),
    )


def _commit_two_domains(*, overlap: bool) -> tuple[ProgramState, tuple[str, str]]:
    first_trials = ("NCT00000001", "NCT00000002")
    second_trials = first_trials if overlap else ("NCT00000003", "NCT00000004")
    trial_ids = tuple(dict.fromkeys((*first_trials, *second_trials)))
    state = _unmapped_state(trial_ids)

    first_mapping = replace(
        _mapping_spec(),
        portfolio_id="CHEMBL_TEST:MONDO_TEST:multi-endpoint-mappings:v1",
        bindings=_selection(first_trials),
    )
    second_mapping = replace(
        _mapping_spec(),
        mapping_id="CHEMBL_TEST:MONDO_TEST:os-map:v1",
        portfolio_id="CHEMBL_TEST:MONDO_TEST:multi-endpoint-mappings:v1",
        endpoint_family_id="overall_survival",
        endpoint_family_label="Overall survival",
        ontology=ClinicalEndpointOntology(
            system="urn:adds:synthetic-endpoint-ontology",
            version="1.0",
            code="OS",
            label="Overall survival",
        ),
        bindings=_selection(second_trials),
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
        selections=_study_selection(first_trials),
    )
    second_synthesis = replace(
        _spec(),
        synthesis_id="CHEMBL_TEST:MONDO_TEST:os-benefit-risk:v1",
        endpoint_mapping_id=second_mapping.mapping_id,
        endpoint_family=second_mapping.endpoint_family_id,
        selections=_study_selection(second_trials),
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
    return final_state, tuple(
        sorted((first_synthesis.synthesis_id, second_synthesis.synthesis_id))
    )


def _portfolio_spec(
    synthesis_ids: tuple[str, str],
    *,
    require_distinct_endpoint_records: bool = True,
) -> ClinicalBenefitRiskPortfolioSpec:
    return ClinicalBenefitRiskPortfolioSpec(
        portfolio_id="CHEMBL_TEST:MONDO_TEST:multi-endpoint-benefit-risk:v1",
        candidate_id="CHEMBL_TEST",
        intervention_id="CHEMBL_TEST",
        disease_id="MONDO_TEST",
        synthesis_ids=synthesis_ids,
        require_distinct_endpoint_records=require_distinct_endpoint_records,
        metadata={
            "maturity": "synthetic_contract_test",
            "semantic_endpoint_truth_claimed": False,
        },
    )


class ClinicalBenefitRiskPortfolioTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.strict_state, cls.strict_synthesis_ids = _commit_two_domains(
            overlap=False
        )
        cls.overlap_state, cls.overlap_synthesis_ids = _commit_two_domains(
            overlap=True
        )

    def test_strict_multi_endpoint_portfolio_replays_every_synthesis(self) -> None:
        spec = _portfolio_spec(self.strict_synthesis_ids)
        report = compile_clinical_benefit_risk_portfolio(self.strict_state, spec)

        self.assertEqual(report.synthesis_count, 2)
        self.assertEqual(report.endpoint_family_count, 2)
        self.assertEqual(report.endpoint_reference_count, 4)
        self.assertEqual(report.unique_endpoint_count, 4)
        self.assertEqual(report.endpoint_reuse_count, 0)
        self.assertEqual(report.unique_trial_count, 4)
        self.assertEqual(report.trial_reuse_count, 0)
        self.assertEqual(report.unique_safety_unit_count, 4)
        self.assertEqual(report.safety_reuse_count, 0)
        self.assertEqual(report.unique_source_count, 4)
        self.assertEqual(report.source_reuse_count, 0)
        self.assertTrue(report.distinct_endpoint_records_across_domains)
        self.assertTrue(report.full_state_replay_performed)
        self.assertFalse(report.pooling_performed)
        self.assertFalse(report.benefit_risk_score_computed)
        self.assertFalse(report.clinical_acceptability_inferred)
        for domain in report.endpoint_domains:
            synthesis = self.strict_state.benefit_risk_syntheses_by_id[
                domain.synthesis_id
            ]
            self.assertEqual(domain.safety_measure, synthesis.safety_measure)
            self.assertEqual(
                domain.harmonization_policy_id,
                synthesis.harmonization_policy_id,
            )
            self.assertEqual(
                domain.safety_direction_consistent,
                synthesis.safety_direction_consistent,
            )
        self.assertEqual(
            validate_clinical_benefit_risk_portfolio(
                self.strict_state,
                spec,
                report,
            ),
            (),
        )

    def test_diagnostic_mode_counts_endpoint_safety_and_source_reuse(self) -> None:
        spec = _portfolio_spec(
            self.overlap_synthesis_ids,
            require_distinct_endpoint_records=False,
        )
        report = compile_clinical_benefit_risk_portfolio(self.overlap_state, spec)

        self.assertEqual(report.endpoint_reference_count, 4)
        self.assertEqual(report.unique_endpoint_count, 2)
        self.assertEqual(report.endpoint_reuse_count, 2)
        self.assertEqual(report.trial_reference_count, 4)
        self.assertEqual(report.unique_trial_count, 2)
        self.assertEqual(report.trial_reuse_count, 2)
        self.assertEqual(report.safety_reference_count, 4)
        self.assertEqual(report.unique_safety_unit_count, 2)
        self.assertEqual(report.safety_reuse_count, 2)
        self.assertEqual(report.source_reference_count, 4)
        self.assertEqual(report.unique_source_count, 2)
        self.assertEqual(report.source_reuse_count, 2)
        self.assertFalse(report.distinct_endpoint_records_across_domains)
        self.assertTrue(
            all(item.reference_count == 2 for item in report.safety_units)
        )
        self.assertTrue(
            all(item.reference_count == 2 for item in report.source_units)
        )
        self.assertEqual(
            report.metadata["cross_domain_trial_overlap_count"],
            2,
        )

    def test_strict_mode_rejects_endpoint_relabeling_across_domains(self) -> None:
        with self.assertRaisesRegex(
            ClinicalBenefitRiskPortfolioError,
            "reuses endpoint records",
        ):
            compile_clinical_benefit_risk_portfolio(
                self.overlap_state,
                _portfolio_spec(self.overlap_synthesis_ids),
            )

    def test_missing_or_tampered_committed_synthesis_fails_closed(self) -> None:
        spec = _portfolio_spec(self.strict_synthesis_ids)
        missing = replace(
            spec,
            synthesis_ids=tuple(sorted((spec.synthesis_ids[0], "missing-synthesis"))),
        )
        with self.assertRaisesRegex(
            ClinicalBenefitRiskPortfolioError,
            "absent from state",
        ):
            compile_clinical_benefit_risk_portfolio(self.strict_state, missing)

        syntheses = list(self.strict_state.benefit_risk_syntheses)
        syntheses[0] = replace(
            syntheses[0],
            identifiers={"canonical": "tampered-synthesis"},
        )
        tampered_state = replace(
            self.strict_state,
            benefit_risk_syntheses=tuple(syntheses),
        )
        with self.assertRaisesRegex(
            ClinicalBenefitRiskPortfolioError,
            "committed-history replay",
        ):
            compile_clinical_benefit_risk_portfolio(tampered_state, spec)

    def test_report_validation_detects_aggregate_tampering(self) -> None:
        spec = _portfolio_spec(self.strict_synthesis_ids)
        report = compile_clinical_benefit_risk_portfolio(self.strict_state, spec)
        tampered = replace(report, metadata={"tampered": True})
        self.assertEqual(
            validate_clinical_benefit_risk_portfolio(
                self.strict_state,
                spec,
                tampered,
            ),
            ("portfolio_recompiled_report_mismatch",),
        )

    def test_spec_envelope_is_integrity_bound_and_duplicate_safe(self) -> None:
        spec = _portfolio_spec(self.strict_synthesis_ids)
        envelope = clinical_benefit_risk_portfolio_spec_envelope(spec)
        self.assertEqual(
            clinical_benefit_risk_portfolio_spec_from_dict(envelope),
            spec,
        )
        encoded = json.dumps(envelope, sort_keys=True)
        self.assertEqual(
            clinical_benefit_risk_portfolio_spec_from_json(encoded),
            spec,
        )
        tampered = copy.deepcopy(envelope)
        tampered["spec"]["portfolio_id"] = "tampered"
        with self.assertRaisesRegex(
            ClinicalBenefitRiskPortfolioError,
            "integrity mismatch",
        ):
            clinical_benefit_risk_portfolio_spec_from_dict(tampered)
        duplicate = encoded.replace(
            '"schema_version":',
            '"schema_version":"duplicate","schema_version":',
            1,
        )
        with self.assertRaisesRegex(
            ClinicalBenefitRiskPortfolioError,
            "duplicate JSON key",
        ):
            clinical_benefit_risk_portfolio_spec_from_json(duplicate)

    def test_public_envelopes_match_json_schemas_and_summary(self) -> None:
        spec = _portfolio_spec(self.strict_synthesis_ids)
        report = compile_clinical_benefit_risk_portfolio(self.strict_state, spec)
        spec_schema = json.loads(SPEC_SCHEMA.read_text(encoding="utf-8"))
        report_schema = json.loads(REPORT_SCHEMA.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(spec_schema)
        Draft202012Validator.check_schema(report_schema)
        Draft202012Validator(spec_schema).validate(
            clinical_benefit_risk_portfolio_spec_envelope(spec)
        )
        Draft202012Validator(report_schema).validate(
            clinical_benefit_risk_portfolio_report_envelope(report)
        )
        report_envelope = clinical_benefit_risk_portfolio_report_envelope(report)
        self.assertEqual(
            clinical_benefit_risk_portfolio_report_from_dict(report_envelope),
            report,
        )
        self.assertEqual(
            clinical_benefit_risk_portfolio_report_from_json(
                json.dumps(report_envelope, sort_keys=True)
            ),
            report,
        )
        summary = clinical_benefit_risk_portfolio_report_summary(report)
        self.assertEqual(summary["endpoint_families"], [
            "overall_survival",
            "progression_free_survival",
        ])
        self.assertEqual(summary["integrity_sha256"], report.fingerprint)

    def test_report_reader_rejects_rehashed_cross_link_rebinding(self) -> None:
        spec = _portfolio_spec(self.strict_synthesis_ids)
        report = compile_clinical_benefit_risk_portfolio(self.strict_state, spec)
        envelope = clinical_benefit_risk_portfolio_report_envelope(report)
        tampered = copy.deepcopy(envelope)
        domains = tampered["report"]["endpoint_domains"]
        domains[0]["cells"][0]["safety_unit_id"] = domains[0]["cells"][1][
            "safety_unit_id"
        ]
        encoded = json.dumps(
            tampered["report"],
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
        tampered["integrity_sha256"] = hashlib.sha256(encoded).hexdigest()
        with self.assertRaisesRegex(
            ValueError,
            "exact safety units|endpoint-to-safety identity is rebound",
        ):
            clinical_benefit_risk_portfolio_report_from_dict(tampered)

    def test_report_reader_rejects_rehashed_semantic_tampering(self) -> None:
        spec = _portfolio_spec(self.strict_synthesis_ids)
        report = compile_clinical_benefit_risk_portfolio(self.strict_state, spec)

        def rehash(envelope: dict[str, object]) -> None:
            encoded = json.dumps(
                envelope["report"],
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
                allow_nan=False,
            ).encode("utf-8")
            envelope["integrity_sha256"] = hashlib.sha256(encoded).hexdigest()

        benefit_tampered = copy.deepcopy(
            clinical_benefit_risk_portfolio_report_envelope(report)
        )
        benefit_cell = benefit_tampered["report"]["endpoint_domains"][0]["cells"][0]
        benefit_cell["benefit_direction"] = (
            "benefit"
            if benefit_cell["benefit_direction"] != "benefit"
            else "harm"
        )
        rehash(benefit_tampered)
        with self.assertRaisesRegex(ValueError, "benefit direction"):
            clinical_benefit_risk_portfolio_report_from_dict(benefit_tampered)

        safety_tampered = copy.deepcopy(
            clinical_benefit_risk_portfolio_report_envelope(report)
        )
        safety_unit = safety_tampered["report"]["safety_units"][0]
        safety_unit["safety_direction"] = (
            "higher_observed_serious_event_risk"
            if safety_unit["safety_direction"]
            != "higher_observed_serious_event_risk"
            else "lower_observed_serious_event_risk"
        )
        rehash(safety_tampered)
        with self.assertRaisesRegex(ValueError, "safety_direction does not match"):
            clinical_benefit_risk_portfolio_report_from_dict(safety_tampered)

        identity_tampered = copy.deepcopy(
            clinical_benefit_risk_portfolio_report_envelope(report)
        )
        old_unit_id = identity_tampered["report"]["safety_units"][0][
            "safety_unit_id"
        ]
        new_unit_id = "0" * 64
        identity_tampered["report"]["safety_units"][0]["safety_unit_id"] = (
            new_unit_id
        )
        for domain in identity_tampered["report"]["endpoint_domains"]:
            for cell in domain["cells"]:
                if cell["safety_unit_id"] == old_unit_id:
                    cell["safety_unit_id"] = new_unit_id
        for source_unit in identity_tampered["report"]["source_units"]:
            source_unit["safety_unit_ids"] = [
                new_unit_id if item == old_unit_id else item
                for item in source_unit["safety_unit_ids"]
            ]
        rehash(identity_tampered)
        with self.assertRaisesRegex(ValueError, "bound identity"):
            clinical_benefit_risk_portfolio_report_from_dict(identity_tampered)

    def test_program_state_requires_mapping_record_type(self) -> None:
        self.assertTrue(
            all(
                isinstance(item, ClinicalEndpointMappingRecord)
                for item in self.strict_state.clinical_endpoint_mappings
            )
        )


if __name__ == "__main__":
    unittest.main()
