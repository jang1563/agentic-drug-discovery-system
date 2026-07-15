from __future__ import annotations

import json
import math
import unittest
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from jsonschema import Draft202012Validator

from adapters.clinical_synthesis_adapter import ClinicalSynthesisAdapter
from adapters.execution_registry import register_existing_adapters
from adapters.pinned_evidence_adapter import PinnedEvidenceAdapter
from agentic_drug_discovery import (
    ActionType,
    BoundedPlanner,
    BoundedStageRunner,
    BudgetState,
    CandidateRecord,
    CandidateStatus,
    ClinicalEndpointMappingReview,
    ClinicalEndpointMappingSpec,
    ClinicalEndpointOntology,
    ClinicalEndpointSelection,
    ClinicalStudySelection,
    ClinicalSynthesisSpec,
    Decision,
    DecisionPacket,
    DiseaseRecord,
    EvidenceEvent,
    EvidenceRelation,
    GatedDiscoveryEnvironment,
    ProgramState,
    ProgramStatus,
    PromotionContext,
    ReplayBundle,
    SourceReference,
    Stage,
    StageGate,
    StagePlan,
    StageRunStatus,
    TargetRecord,
    ToolCallSpec,
    ToolExecutionLedger,
    ToolRegistry,
    build_default_semantic_mapper_registry,
    capture_source_bytes,
    clinical_endpoint_mapping_spec_to_dict,
    clinical_synthesis_spec_from_dict,
    clinical_synthesis_spec_to_dict,
    compile_benefit_risk_synthesis,
    compile_clinical_endpoint_mapping,
    compile_pinned_evidence_manifest,
    default_stage_gates,
    extract_clinicaltrials_gov_ingestion_job,
    program_state_from_dict,
    replay_program,
    to_primitive,
    validate_benefit_risk_synthesis,
    validate_clinical_endpoint_mapping,
)


ROOT = Path(__file__).resolve().parents[1]
JOB = ROOT / "rl_env/specs/clinicaltrials_gov_ingestion_job.example.json"
SOURCE = ROOT / "tests/fixtures/clinicaltrials_gov_study.synthetic.json"
SYNTHESIS_SCHEMA = ROOT / "rl_env/specs/clinical_benefit_risk_synthesis.schema.json"
SYNTHESIS_EXAMPLE = ROOT / "rl_env/specs/clinical_benefit_risk_synthesis.example.json"
REQUEST_AT = datetime(2025, 1, 2, 1, tzinfo=timezone.utc)
COMPLETED_AT = REQUEST_AT + timedelta(minutes=1)
MAPPING_REQUEST_AT = REQUEST_AT - timedelta(minutes=2)
MAPPING_COMPLETED_AT = REQUEST_AT - timedelta(minutes=1)


def _clinical_state(program_id: str) -> ProgramState:
    disease_evidence = EvidenceEvent(
        evidence_id=f"{program_id}:disease",
        stage=Stage.DISEASE_CONTEXT,
        subject="test disease",
        predicate="disease_context_resolved",
        object_value="MONDO_TEST",
        source=SourceReference(
            source_id=f"{program_id}:disease-source",
            source_version="fixture-2024-01-01",
            locator=f"https://example.invalid/{program_id}/disease",
            content_hash="0" * 64,
        ),
        observed_at=date(2024, 1, 1),
        available_at=date(2024, 1, 1),
        relation=EvidenceRelation.SUPPORTS,
        biological_context={"disease_id": "MONDO_TEST"},
    )
    return ProgramState(
        program_id=program_id,
        disease="test disease",
        therapeutic_hypothesis="Exact clinical identities govern stage progression.",
        as_of_date=date(2025, 1, 2),
        current_stage=Stage.CLINICAL_STRATEGY,
        budget=BudgetState(limit=1.0),
        evidence=(disease_evidence,),
        diseases=(
            DiseaseRecord(
                disease_id="MONDO_TEST",
                name="test disease",
                stage=Stage.DISEASE_CONTEXT,
                identifiers={"canonical": "MONDO_TEST"},
                supporting_evidence=(disease_evidence.evidence_id,),
            ),
        ),
        targets=(
            TargetRecord(
                target_id="ENSG_TEST1",
                symbol="TEST1",
                disease_id="MONDO_TEST",
                organism="Homo sapiens",
                stage=Stage.MODALITY_SELECTION,
                identifiers={
                    "canonical": "ENSG_TEST1",
                    "ensembl_gene": "ENSG_TEST1",
                    "gene_symbol": "TEST1",
                    "chembl_target": "CHEMBL_TARGET",
                },
            ),
        ),
        candidates=(
            CandidateRecord(
                candidate_id="CHEMBL_TEST",
                name="Test Drug",
                modality="small molecule",
                stage=Stage.LEAD_OPTIMIZATION,
                status=CandidateStatus.SELECTED,
                attributes={
                    "target_record_id": "ENSG_TEST1",
                    "target_chembl_id": "CHEMBL_TARGET",
                    "target_symbol": "TEST1",
                    "disease_id": "MONDO_TEST",
                },
            ),
        ),
    )


def _manifest(trial_id: str) -> dict:
    original_trial_id = "NCT00000001"
    job_text = JOB.read_text(encoding="utf-8").replace(
        original_trial_id, trial_id
    )
    source_bytes = SOURCE.read_text(encoding="utf-8").replace(
        original_trial_id, trial_id
    ).encode("utf-8")
    job = json.loads(job_text)
    receipt_id = f"ctgov-test-{trial_id}"
    job["source_receipt_id"] = receipt_id
    bundle = capture_source_bytes(
        source_bytes,
        receipt_id=receipt_id,
        source_id=f"clinicaltrials-gov-{trial_id}",
        source_version=f"clinicaltrials-gov-{trial_id}-version-2025-01-01",
        locator=f"https://clinicaltrials.gov/api/v2/studies/{trial_id}",
        retrieved_at=datetime(2025, 1, 2, tzinfo=timezone.utc),
        media_type="application/json",
        capture_method="https",
        http_status=200,
    )
    extracted = extract_clinicaltrials_gov_ingestion_job(job, bundle)
    manifest, _ = compile_pinned_evidence_manifest(
        extracted,
        {bundle.receipt.receipt_id: bundle},
    )
    return manifest


def _run_clinical_trial(trial_id: str, program_id: str) -> ProgramState:
    registry = register_existing_adapters(
        ToolRegistry(clock=lambda: COMPLETED_AT),
        pinned_evidence=PinnedEvidenceAdapter(_manifest(trial_id)),
    )
    runner = BoundedStageRunner(
        tool_registry=registry,
        mapper_registry=build_default_semantic_mapper_registry(
            target_association_minimum_score=0.5
        ),
        planner=BoundedPlanner(clock=lambda: REQUEST_AT),
        clock=lambda: COMPLETED_AT,
    )
    plan = StagePlan(
        plan_id=f"clinical-design-{trial_id}",
        stage=Stage.CLINICAL_STRATEGY,
        calls=(
            ToolCallSpec(
                call_id="clinical-design",
                tool_id="pinned_evidence",
                operation="clinical_trial_design",
                action_type=ActionType.QUERY_DATABASE,
                purpose="Resolve one exact posted endpoint and safety summary.",
                arguments={
                    "candidate_id": "CHEMBL_TEST",
                    "disease_id": "MONDO_TEST",
                    "trial_id": trial_id,
                },
                max_cost=0.1,
            ),
        ),
        max_steps=1,
        max_total_cost=0.1,
        success_confidence=0.9,
        failure_confidence=0.95,
        next_stage=Stage.REGULATORY_POSTMARKET,
    )
    result = runner.run_stage(
        run_id=f"{program_id}:clinical",
        state=_clinical_state(program_id),
        stage_plan=plan,
        promotion_contexts={
            "clinical-design": PromotionContext(
                observed_at=date(2024, 6, 1),
                available_at=date(2024, 9, 15),
                subject="Test Drug",
                object_value="test disease",
                confidence=0.9,
                candidate_id="CHEMBL_TEST",
                candidate_name="Test Drug",
                modality="small molecule",
                biological_context={
                    "disease_id": "MONDO_TEST",
                    "intervention_id": "CHEMBL_TEST",
                },
            )
        },
    )
    if result.status is not StageRunStatus.COMMITTED:
        raise AssertionError(result.code)
    return result.final_state


def _combined_state() -> ProgramState:
    first = _run_clinical_trial("NCT00000001", "trial-one")
    second = _run_clinical_trial("NCT00000002", "trial-two")
    first_intervention = first.interventions[0]
    second_intervention = second.interventions[0]
    merged_intervention = replace(
        first_intervention,
        supporting_evidence=tuple(
            dict.fromkeys(
                (
                    *first_intervention.supporting_evidence,
                    *second_intervention.supporting_evidence,
                )
            )
        ),
        attributes={
            **dict(first_intervention.attributes),
            "clinical_trial_ids": sorted(
                {
                    *first_intervention.attributes["clinical_trial_ids"],
                    *second_intervention.attributes["clinical_trial_ids"],
                }
            ),
        },
    )
    return ProgramState(
        program_id="benefit-risk-program",
        disease=first.disease,
        therapeutic_hypothesis=first.therapeutic_hypothesis,
        as_of_date=first.as_of_date,
        current_stage=Stage.REGULATORY_POSTMARKET,
        budget=BudgetState(limit=2.0),
        evidence=(*first.evidence, *second.evidence),
        claims=(*first.claims, *second.claims),
        diseases=first.diseases,
        targets=first.targets,
        candidates=first.candidates,
        interventions=(merged_intervention,),
        trials=(*first.trials, *second.trials),
        trial_designs=(*first.trial_designs, *second.trial_designs),
    )


def _spec() -> ClinicalSynthesisSpec:
    return ClinicalSynthesisSpec(
        synthesis_id="CHEMBL_TEST:MONDO_TEST:pfs-benefit-risk:v1",
        candidate_id="CHEMBL_TEST",
        intervention_id="CHEMBL_TEST",
        disease_id="MONDO_TEST",
        endpoint_mapping_id="CHEMBL_TEST:MONDO_TEST:pfs-map:v1",
        endpoint_family="progression_free_survival",
        effect_measure="hazard_ratio",
        effect_measure_favorable_direction="lower_is_better",
        safety_measure="serious_adverse_event_risk_difference",
        harmonization_policy_id="adds.descriptive-cross-trial-benefit-risk.v1",
        selections=(
            ClinicalStudySelection(
                trial_id="NCT00000001",
                design_id="NCT00000001:design",
                endpoint_id="NCT00000001:endpoint:primary-0",
                safety_id="NCT00000001:safety:serious-adverse-events",
            ),
            ClinicalStudySelection(
                trial_id="NCT00000002",
                design_id="NCT00000002:design",
                endpoint_id="NCT00000002:endpoint:primary-0",
                safety_id="NCT00000002:safety:serious-adverse-events",
            ),
        ),
        metadata={"review_status": "synthetic_test_selection"},
    )


def _mapping_spec() -> ClinicalEndpointMappingSpec:
    return ClinicalEndpointMappingSpec(
        mapping_id="CHEMBL_TEST:MONDO_TEST:pfs-map:v1",
        portfolio_id="CHEMBL_TEST-MONDO_TEST-ctgov-portfolio-v1",
        candidate_id="CHEMBL_TEST",
        intervention_id="CHEMBL_TEST",
        disease_id="MONDO_TEST",
        endpoint_family_id="progression_free_survival",
        endpoint_family_label="Progression-free survival",
        ontology=ClinicalEndpointOntology(
            system="urn:adds:synthetic-endpoint-ontology",
            version="1.0",
            code="PFS",
            label="Progression-free survival",
        ),
        effect_measure="hazard_ratio",
        favorable_direction="lower_is_better",
        safety_measure="serious_adverse_event_risk_difference",
        bindings=tuple(
            ClinicalEndpointSelection(
                trial_id=item.trial_id,
                design_id=item.design_id,
                endpoint_id=item.endpoint_id,
                safety_id=item.safety_id,
            )
            for item in _spec().selections
        ),
        review=ClinicalEndpointMappingReview(
            status="approved",
            reviewer_id="reviewer:synthetic-test",
            reviewed_at=datetime(2025, 1, 2, tzinfo=timezone.utc),
        ),
        metadata={
            "review_note": "Synthetic test approval.",
            "review_protocol_id": "adds.endpoint-mapping-review.v1",
        },
    )


def _run_mapping(state: ProgramState, spec: ClinicalEndpointMappingSpec):
    registry = register_existing_adapters(
        ToolRegistry(clock=lambda: MAPPING_COMPLETED_AT),
        clinical_synthesis=ClinicalSynthesisAdapter(),
    )
    environment = GatedDiscoveryEnvironment()
    runner = BoundedStageRunner(
        tool_registry=registry,
        mapper_registry=build_default_semantic_mapper_registry(
            target_association_minimum_score=0.5
        ),
        planner=BoundedPlanner(clock=lambda: MAPPING_REQUEST_AT),
        environment=environment,
        clock=lambda: MAPPING_COMPLETED_AT,
    )
    plan = StagePlan(
        plan_id="reviewed-endpoint-family-mapping",
        stage=Stage.REGULATORY_POSTMARKET,
        calls=(
            ToolCallSpec(
                call_id="endpoint-mapping",
                tool_id="clinical_synthesis",
                operation="register_endpoint_mapping",
                action_type=ActionType.RUN_VERIFIER,
                purpose="Bind reviewer approval to exact endpoint ledger identities.",
                arguments={
                    "spec": clinical_endpoint_mapping_spec_to_dict(spec),
                },
                max_cost=0.01,
            ),
        ),
        max_steps=1,
        max_total_cost=0.01,
        success_confidence=0.9,
        failure_confidence=0.95,
        success_decision=Decision.HOLD,
    )
    result = runner.run_stage(
        run_id="endpoint-mapping-registration",
        state=state,
        stage_plan=plan,
        promotion_contexts={
            "endpoint-mapping": PromotionContext(
                observed_at=date(2025, 1, 2),
                available_at=date(2025, 1, 2),
                subject="Test Drug",
                object_value="test disease",
                confidence=0.9,
                candidate_id="CHEMBL_TEST",
                candidate_name="Test Drug",
                modality="small molecule",
                biological_context={
                    "disease_id": "MONDO_TEST",
                    "intervention_id": "CHEMBL_TEST",
                    "mapping_id": spec.mapping_id,
                    "portfolio_id": spec.portfolio_id,
                },
            )
        },
    )
    return result, environment


def _synthesis_environment() -> GatedDiscoveryEnvironment:
    gates = default_stage_gates()
    gates[Stage.REGULATORY_POSTMARKET] = StageGate(
        stage=Stage.REGULATORY_POSTMARKET,
        required_claim_predicates=("clinical_benefit_risk_synthesis_available",),
        required_evidence_predicates=("clinical_benefit_risk_synthesis_available",),
        minimum_evidence_events=1,
        minimum_benefit_risk_synthesis_records=1,
        minimum_confidence=0.6,
    )
    return GatedDiscoveryEnvironment(stage_gates=gates)


def _run_synthesis(state: ProgramState, spec: ClinicalSynthesisSpec):
    registry = register_existing_adapters(
        ToolRegistry(clock=lambda: COMPLETED_AT),
        clinical_synthesis=ClinicalSynthesisAdapter(),
    )
    environment = _synthesis_environment()
    runner = BoundedStageRunner(
        tool_registry=registry,
        mapper_registry=build_default_semantic_mapper_registry(
            target_association_minimum_score=0.5
        ),
        planner=BoundedPlanner(clock=lambda: REQUEST_AT),
        environment=environment,
        clock=lambda: COMPLETED_AT,
    )
    plan = StagePlan(
        plan_id="cross-trial-benefit-risk-synthesis",
        stage=Stage.REGULATORY_POSTMARKET,
        calls=(
            ToolCallSpec(
                call_id="synthesis",
                tool_id="clinical_synthesis",
                operation="harmonize_benefit_risk",
                action_type=ActionType.RUN_VERIFIER,
                purpose="Compile an explicit non-pooled cross-trial synthesis.",
                arguments={"spec": clinical_synthesis_spec_to_dict(spec)},
                max_cost=0.01,
            ),
        ),
        max_steps=1,
        max_total_cost=0.01,
        success_confidence=0.9,
        failure_confidence=0.95,
    )
    result = runner.run_stage(
        run_id="benefit-risk-synthesis",
        state=state,
        stage_plan=plan,
        promotion_contexts={
            "synthesis": PromotionContext(
                observed_at=date(2025, 1, 2),
                available_at=date(2025, 1, 2),
                subject="Test Drug",
                object_value="test disease",
                confidence=0.9,
                candidate_id="CHEMBL_TEST",
                candidate_name="Test Drug",
                modality="small molecule",
                biological_context={
                    "disease_id": "MONDO_TEST",
                    "intervention_id": "CHEMBL_TEST",
                    "endpoint_mapping_id": spec.endpoint_mapping_id,
                    "synthesis_id": spec.synthesis_id,
                },
            )
        },
    )
    return result, environment


class ClinicalBenefitRiskSynthesisTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.unmapped_state = _combined_state()
        cls.mapping_result, cls.mapping_environment = _run_mapping(
            cls.unmapped_state,
            _mapping_spec(),
        )
        if cls.mapping_result.status is not StageRunStatus.COMMITTED:
            raise AssertionError(cls.mapping_result.code)
        cls.state = cls.mapping_result.final_state

    def test_mapping_tool_commit_serialization_and_replay(self) -> None:
        result = self.mapping_result
        self.assertEqual(
            result.promotions[0].code,
            "clinical_endpoint_mapping_promoted",
        )
        self.assertEqual(len(result.final_state.clinical_endpoint_mappings), 1)
        mapping = result.final_state.clinical_endpoint_mappings[0]
        self.assertEqual(mapping.review_status, "approved")
        self.assertFalse(mapping.attributes["ontology_authority_verified"])
        self.assertFalse(mapping.attributes["automatic_endpoint_mapping_performed"])
        result.final_state.validate_committed_history()
        parsed = program_state_from_dict(to_primitive(result.final_state))
        self.assertEqual(parsed, result.final_state)
        report = replay_program(
            ReplayBundle(
                initial_state=self.unmapped_state,
                packets=result.accepted_packets,
                tool_execution_ledger=result.execution_ledger,
            ),
            environment=self.mapping_environment,
        )
        self.assertFalse(report.stopped_on_block)
        self.assertEqual(report.final_state, result.final_state)

    def test_mapping_approval_must_precede_tool_request(self) -> None:
        spec = _mapping_spec()
        future_approval = replace(
            spec,
            review=replace(
                spec.review,
                reviewed_at=MAPPING_REQUEST_AT + timedelta(seconds=1),
            ),
        )
        result, _ = _run_mapping(self.unmapped_state, future_approval)
        self.assertEqual(
            result.promotions[0].code,
            "clinical_endpoint_mapping_review_not_yet_effective",
        )
        self.assertEqual(result.final_state.clinical_endpoint_mappings, ())

    def test_compiler_retains_trial_values_and_provenance_without_pooling(self) -> None:
        synthesis = compile_benefit_risk_synthesis(self.state, _spec())
        self.assertEqual(len(synthesis.studies), 2)
        self.assertEqual(len(synthesis.source_content_hashes), 2)
        self.assertTrue(synthesis.source_disjoint)
        self.assertEqual(synthesis.pooling_method, "none")
        self.assertFalse(synthesis.pooling_performed)
        self.assertFalse(synthesis.clinical_acceptability_inferred)
        self.assertFalse(synthesis.attributes["benefit_risk_score_computed"])
        for study in synthesis.studies:
            self.assertEqual(study.effect_estimate, 0.7)
            self.assertEqual(study.benefit_direction, "benefit")
            self.assertTrue(
                math.isclose(
                    study.serious_event_risk_difference,
                    -0.1,
                    rel_tol=0.0,
                    abs_tol=1e-12,
                )
            )
            self.assertEqual(
                study.safety_direction,
                "lower_observed_serious_event_risk",
            )

    def test_public_selection_schema_matches_strict_parser(self) -> None:
        schema = json.loads(SYNTHESIS_SCHEMA.read_text(encoding="utf-8"))
        example = json.loads(SYNTHESIS_EXAMPLE.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(example)
        parsed = clinical_synthesis_spec_from_dict(example)
        self.assertEqual(
            clinical_synthesis_spec_to_dict(parsed),
            example,
        )

    def test_end_to_end_tool_promotion_commit_serialization_and_replay(self) -> None:
        result, environment = _run_synthesis(self.state, _spec())
        self.assertIs(result.status, StageRunStatus.COMMITTED)
        self.assertIs(result.final_state.status, ProgramStatus.COMPLETED)
        self.assertEqual(len(result.final_state.benefit_risk_syntheses), 1)
        self.assertIn(
            "clinical_benefit_risk_synthesis_available",
            {item.predicate for item in result.final_state.evidence},
        )
        self.assertEqual(
            result.promotions[0].code,
            "clinical_benefit_risk_synthesis_promoted",
        )
        result.final_state.validate_committed_history()
        parsed = program_state_from_dict(to_primitive(result.final_state))
        self.assertEqual(parsed, result.final_state)
        report = replay_program(
            ReplayBundle(
                initial_state=self.state,
                packets=result.accepted_packets,
                tool_execution_ledger=ToolExecutionLedger(
                    outcomes=(
                        *self.mapping_result.execution_ledger.outcomes,
                        *result.execution_ledger.outcomes,
                    )
                ),
            ),
            environment=environment,
        )
        self.assertFalse(report.stopped_on_block)
        self.assertEqual(report.final_state, result.final_state)

    def test_endpoint_selection_mismatch_defers_without_partial_state(self) -> None:
        selections = list(_spec().selections)
        selections[1] = replace(
            selections[1],
            endpoint_id="NCT00000002:endpoint:unreviewed",
        )
        bad_spec = replace(_spec(), selections=tuple(selections))
        result, _ = _run_synthesis(self.state, bad_spec)
        self.assertIs(result.status, StageRunStatus.COMMITTED)
        self.assertIs(result.accepted_packets[0].decision, Decision.DEFER)
        self.assertEqual(result.final_state.benefit_risk_syntheses, ())
        self.assertEqual(
            result.promotions[0].code,
            "clinical_synthesis_not_harmonizable",
        )

    def test_overlapping_source_hashes_are_rejected(self) -> None:
        first_hash = self.unmapped_state.trial_designs[0].supporting_evidence[0]
        digest = self.unmapped_state.evidence_by_id[first_hash].source.content_hash
        second_evidence_ids = set(
            self.unmapped_state.trial_designs[1].supporting_evidence
        )
        evidence = tuple(
            replace(
                item,
                source=replace(item.source, content_hash=digest),
            )
            if item.evidence_id in second_evidence_ids
            else item
            for item in self.unmapped_state.evidence
        )
        overlapping = replace(self.unmapped_state, evidence=evidence)
        with self.assertRaisesRegex(
            ValueError,
            "sources must be disjoint",
        ):
            compile_clinical_endpoint_mapping(overlapping, _mapping_spec())

    def test_mapping_review_cannot_predate_selected_evidence(self) -> None:
        backdated = replace(
            _mapping_spec(),
            review=replace(
                _mapping_spec().review,
                reviewed_at=datetime(2024, 9, 14, tzinfo=timezone.utc),
            ),
        )
        with self.assertRaisesRegex(
            ValueError,
            "review predates selected evidence availability",
        ):
            compile_clinical_endpoint_mapping(self.unmapped_state, backdated)

    def test_mapping_rejects_endpoint_with_incompatible_effect_measure(self) -> None:
        design = self.unmapped_state.trial_designs[0]
        endpoint = design.endpoints[0]
        incompatible_endpoint = replace(
            endpoint,
            attributes={
                **dict(endpoint.attributes),
                "analysis": {
                    **dict(endpoint.attributes["analysis"]),
                    "parameter_type": "Odds Ratio",
                },
            },
        )
        incompatible_design = replace(
            design,
            endpoints=(incompatible_endpoint, *design.endpoints[1:]),
        )
        incompatible_state = replace(
            self.unmapped_state,
            trial_designs=(
                incompatible_design,
                *self.unmapped_state.trial_designs[1:],
            ),
        )
        with self.assertRaisesRegex(
            ValueError,
            "does not report the declared hazard ratio",
        ):
            compile_clinical_endpoint_mapping(incompatible_state, _mapping_spec())

    def test_synthesis_without_committed_mapping_defers_without_partial_state(self) -> None:
        result, _ = _run_synthesis(self.unmapped_state, _spec())
        self.assertIs(result.status, StageRunStatus.COMMITTED)
        self.assertIs(result.accepted_packets[0].decision, Decision.DEFER)
        self.assertEqual(result.final_state.benefit_risk_syntheses, ())
        self.assertEqual(
            result.promotions[0].code,
            "clinical_synthesis_not_harmonizable",
        )

    def test_direct_mapping_commit_requires_bound_derived_evidence(self) -> None:
        mapping = compile_clinical_endpoint_mapping(
            self.unmapped_state,
            _mapping_spec(),
        )
        packet = DecisionPacket(
            packet_id="mapping-without-derived-evidence",
            program_id=self.unmapped_state.program_id,
            expected_state_version=self.unmapped_state.version,
            stage=self.unmapped_state.current_stage,
            decision=Decision.HOLD,
            rationale="Attempt to bypass the mapping semantic promotion path.",
            confidence=0.9,
            clinical_endpoint_mapping_updates=(mapping,),
            created_at=COMPLETED_AT,
        )
        result = GatedDiscoveryEnvironment().transition(self.unmapped_state, packet)
        self.assertFalse(result.applied)
        continuity = next(
            item
            for item in result.blocking_results
            if item.code == "clinical_endpoint_mapping_continuity_invalid"
        )
        self.assertIn(
            "derived_mapping_evidence_missing",
            continuity.details["failures"],
        )

    def test_mapping_replay_rejects_non_object_selection_entries(self) -> None:
        mapping = compile_clinical_endpoint_mapping(
            self.unmapped_state,
            _mapping_spec(),
        )
        forged = replace(
            mapping,
            attributes={
                **dict(mapping.attributes),
                "selection_spec": [
                    mapping.attributes["selection_spec"][0],
                    "not-an-identity-binding",
                    mapping.attributes["selection_spec"][1],
                ],
            },
        )
        self.assertEqual(
            validate_clinical_endpoint_mapping(self.unmapped_state, forged),
            ("mapping_selection_spec_invalid",),
        )

    def test_synthesis_replay_rejects_non_object_selection_entries(self) -> None:
        synthesis = compile_benefit_risk_synthesis(self.state, _spec())
        forged = replace(
            synthesis,
            attributes={
                **dict(synthesis.attributes),
                "selection_spec": [
                    synthesis.attributes["selection_spec"][0],
                    "not-an-identity-binding",
                    synthesis.attributes["selection_spec"][1],
                ],
            },
        )
        self.assertEqual(
            validate_benefit_risk_synthesis(self.state, forged),
            ("selection_spec_invalid",),
        )

    def test_automatic_pooling_cannot_be_enabled(self) -> None:
        synthesis = compile_benefit_risk_synthesis(self.state, _spec())
        with self.assertRaisesRegex(
            ValueError,
            "automatic cross-trial pooling",
        ):
            replace(
                synthesis,
                pooling_method="fixed_effect",
                pooling_performed=True,
            )

    def test_forged_harmonized_measurement_fails_continuity(self) -> None:
        synthesis = compile_benefit_risk_synthesis(self.state, _spec())
        forged_study = replace(
            synthesis.studies[0],
            candidate_measurement=synthesis.studies[0].candidate_measurement + 1.0,
        )
        forged = replace(
            synthesis,
            studies=(forged_study, synthesis.studies[1]),
        )
        packet = DecisionPacket(
            packet_id="forged-synthesis",
            program_id=self.state.program_id,
            expected_state_version=self.state.version,
            stage=self.state.current_stage,
            decision=Decision.HOLD,
            rationale="Attempt to commit a value that does not match the source endpoint.",
            confidence=0.9,
            benefit_risk_synthesis_updates=(forged,),
            created_at=COMPLETED_AT,
        )
        result = GatedDiscoveryEnvironment().transition(self.state, packet)
        self.assertFalse(result.applied)
        self.assertIn(
            "clinical_synthesis_continuity_invalid",
            {item.code for item in result.blocking_results},
        )

    def test_direct_synthesis_commit_requires_bound_derived_evidence(self) -> None:
        synthesis = compile_benefit_risk_synthesis(self.state, _spec())
        packet = DecisionPacket(
            packet_id="synthesis-without-derived-evidence",
            program_id=self.state.program_id,
            expected_state_version=self.state.version,
            stage=self.state.current_stage,
            decision=Decision.HOLD,
            rationale="Attempt to bypass the semantic promotion path.",
            confidence=0.9,
            benefit_risk_synthesis_updates=(synthesis,),
            created_at=COMPLETED_AT,
        )
        result = GatedDiscoveryEnvironment().transition(self.state, packet)
        self.assertFalse(result.applied)
        self.assertIn(
            "clinical_synthesis_continuity_invalid",
            {item.code for item in result.blocking_results},
        )
        continuity = next(
            item
            for item in result.blocking_results
            if item.code == "clinical_synthesis_continuity_invalid"
        )
        self.assertIn(
            "derived_synthesis_evidence_missing",
            continuity.details["failures"],
        )

    def test_unrelated_support_event_cannot_be_attached_to_synthesis(self) -> None:
        synthesis = compile_benefit_risk_synthesis(self.state, _spec())
        unrelated_evidence_id = next(
            item.evidence_id
            for item in self.state.evidence
            if item.evidence_id not in synthesis.source_evidence_ids
        )
        forged = replace(
            synthesis,
            supporting_evidence=(
                *synthesis.supporting_evidence,
                unrelated_evidence_id,
            ),
        )
        packet = DecisionPacket(
            packet_id="synthesis-with-unrelated-support",
            program_id=self.state.program_id,
            expected_state_version=self.state.version,
            stage=self.state.current_stage,
            decision=Decision.HOLD,
            rationale="Attempt to attach an unrelated support event.",
            confidence=0.9,
            benefit_risk_synthesis_updates=(forged,),
            created_at=COMPLETED_AT,
        )
        result = GatedDiscoveryEnvironment().transition(self.state, packet)
        self.assertFalse(result.applied)
        self.assertIn(
            "clinical_synthesis_continuity_invalid",
            {item.code for item in result.blocking_results},
        )
        continuity = next(
            item
            for item in result.blocking_results
            if item.code == "clinical_synthesis_continuity_invalid"
        )
        self.assertIn(
            "derived_synthesis_evidence_binding_invalid",
            continuity.details["failures"],
        )

    def test_committed_synthesis_cannot_be_removed_from_replay_ledger(self) -> None:
        result, _ = _run_synthesis(self.state, _spec())
        stripped = replace(result.final_state, benefit_risk_syntheses=())
        with self.assertRaisesRegex(
            ValueError,
            "benefit-risk synthesis ledger",
        ):
            stripped.validate_committed_history()

    def test_committed_mapping_cannot_be_removed_from_replay_ledger(self) -> None:
        stripped = replace(self.state, clinical_endpoint_mappings=())
        with self.assertRaisesRegex(
            ValueError,
            "clinical endpoint mapping ledger",
        ):
            stripped.validate_committed_history()


if __name__ == "__main__":
    unittest.main()
