from __future__ import annotations

import json
import math
import unittest
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

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
    ClinicalClosedLoopError,
    ClinicalClosedLoopPolicy,
    ClinicalDecisionPolicy,
    ClinicalDimensionStatus,
    ClinicalEndpointMappingReview,
    ClinicalEndpointMappingSpec,
    ClinicalEndpointOntology,
    ClinicalEndpointSelection,
    ClinicalEvidenceActionOption,
    ClinicalEvidenceTransitionPackage,
    ClinicalEvidenceDimension,
    ClinicalEvidenceGapCode,
    ClinicalStudySelection,
    ClinicalSynthesisSpec,
    Decision,
    DecisionPacket,
    DiseaseRecord,
    EvidenceDraft,
    EvidenceEvent,
    EvidenceRelation,
    ExecutionMode,
    GatedDiscoveryEnvironment,
    ProgramState,
    ProgramStatus,
    PromotionContext,
    PromotionResult,
    PromotionStatus,
    ReplayBundle,
    RecordParseError,
    SourceReference,
    Stage,
    StageGate,
    StagePlan,
    StageRunStatus,
    TargetRecord,
    ToolCallSpec,
    ToolContract,
    ToolExecutionLedger,
    ToolRegistry,
    ToolResponse,
    ToolStatus,
    build_default_semantic_mapper_registry,
    capture_source_bytes,
    clinical_endpoint_mapping_spec_to_dict,
    clinical_decision_package_envelope,
    clinical_decision_package_from_dict,
    clinical_decision_package_from_json,
    clinical_evidence_transition_envelope,
    clinical_evidence_transition_from_dict,
    clinical_evidence_transition_from_json,
    clinical_synthesis_spec_from_dict,
    clinical_synthesis_spec_to_dict,
    compile_clinical_decision_package,
    compile_clinical_evidence_tensor,
    compile_clinical_evidence_transition,
    compile_clinical_execution_batch,
    compile_benefit_risk_synthesis,
    compile_clinical_endpoint_mapping,
    compile_pinned_evidence_manifest,
    default_stage_gates,
    execute_clinical_evidence_batch,
    extract_clinicaltrials_gov_ingestion_job,
    program_state_from_dict,
    replay_program,
    to_primitive,
    validate_benefit_risk_synthesis,
    validate_clinical_decision_package,
    validate_clinical_evidence_transition,
    validate_clinical_endpoint_mapping,
)


ROOT = Path(__file__).resolve().parents[1]
JOB = ROOT / "rl_env/specs/clinicaltrials_gov_ingestion_job.example.json"
SOURCE = ROOT / "tests/fixtures/clinicaltrials_gov_study.synthetic.json"
SYNTHESIS_SCHEMA = ROOT / "rl_env/specs/clinical_benefit_risk_synthesis.schema.json"
SYNTHESIS_EXAMPLE = ROOT / "rl_env/specs/clinical_benefit_risk_synthesis.example.json"
DECISION_SCHEMA = (
    ROOT / "rl_env/specs/clinical_evidence_decision_package.schema.json"
)
DECISION_EXAMPLE = (
    ROOT / "rl_env/specs/clinical_evidence_decision_package.example.json"
)
CLOSED_LOOP_SCHEMA = (
    ROOT
    / "rl_env/specs/clinical_evidence_closed_loop_transition.schema.json"
)
CLOSED_LOOP_EXAMPLE = (
    ROOT
    / "rl_env/specs/clinical_evidence_closed_loop_transition.example.json"
)
REQUEST_AT = datetime(2025, 1, 2, 1, tzinfo=timezone.utc)
COMPLETED_AT = REQUEST_AT + timedelta(minutes=1)
MAPPING_REQUEST_AT = REQUEST_AT - timedelta(minutes=2)
MAPPING_COMPLETED_AT = REQUEST_AT - timedelta(minutes=1)
CLOSED_LOOP_REQUEST_AT = REQUEST_AT + timedelta(hours=1)
CLOSED_LOOP_COMPLETED_AT = CLOSED_LOOP_REQUEST_AT + timedelta(minutes=1)
CLOSED_LOOP_MAPPING_REQUEST_AT = CLOSED_LOOP_COMPLETED_AT + timedelta(minutes=1)
CLOSED_LOOP_MAPPING_COMPLETED_AT = CLOSED_LOOP_MAPPING_REQUEST_AT + timedelta(minutes=1)
CLOSED_LOOP_SYNTHESIS_REQUEST_AT = (
    CLOSED_LOOP_MAPPING_COMPLETED_AT + timedelta(minutes=1)
)
CLOSED_LOOP_SYNTHESIS_COMPLETED_AT = (
    CLOSED_LOOP_SYNTHESIS_REQUEST_AT + timedelta(minutes=1)
)


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
                    "identity_aliases": ("TestDrug-1",),
                },
            ),
        ),
    )


def _manifest(
    trial_id: str,
    *,
    candidate_serious_num_affected: int = 12,
) -> dict:
    original_trial_id = "NCT00000001"
    job_text = JOB.read_text(encoding="utf-8").replace(
        original_trial_id, trial_id
    )
    source_text = SOURCE.read_text(encoding="utf-8").replace(
        original_trial_id, trial_id
    )
    job = json.loads(job_text)
    if candidate_serious_num_affected != 12:
        job["trial"]["safety"]["arms"][0]["serious_num_affected"] = (
            candidate_serious_num_affected
        )
        source = json.loads(source_text)
        source["resultsSection"]["adverseEventsModule"]["eventGroups"][0][
            "seriousNumAffected"
        ] = candidate_serious_num_affected
        source_text = json.dumps(
            source,
            sort_keys=True,
            separators=(",", ":"),
        )
    source_bytes = source_text.encode("utf-8")
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


def _run_clinical_trial(
    trial_id: str,
    program_id: str,
    *,
    candidate_serious_num_affected: int = 12,
) -> ProgramState:
    registry = register_existing_adapters(
        ToolRegistry(clock=lambda: COMPLETED_AT),
        pinned_evidence=PinnedEvidenceAdapter(
            _manifest(
                trial_id,
                candidate_serious_num_affected=(
                    candidate_serious_num_affected
                ),
            )
        ),
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


def _combined_state(
    *,
    second_candidate_serious_num_affected: int = 12,
) -> ProgramState:
    first = _run_clinical_trial("NCT00000001", "trial-one")
    second = _run_clinical_trial(
        "NCT00000002",
        "trial-two",
        candidate_serious_num_affected=(
            second_candidate_serious_num_affected
        ),
    )
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


def _combined_three_trial_state() -> ProgramState:
    states = (
        _run_clinical_trial("NCT00000001", "cycle-trial-one"),
        _run_clinical_trial("NCT00000002", "cycle-trial-two"),
        _run_clinical_trial("NCT00000003", "cycle-trial-three"),
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
                {
                    trial_id
                    for state in states
                    for trial_id in state.interventions[0].attributes[
                        "clinical_trial_ids"
                    ]
                }
            ),
        },
    )
    return ProgramState(
        program_id="clinical-closed-loop-program",
        disease=first.disease,
        therapeutic_hypothesis=first.therapeutic_hypothesis,
        as_of_date=first.as_of_date,
        current_stage=Stage.REGULATORY_POSTMARKET,
        budget=BudgetState(limit=3.0),
        evidence=tuple(
            item for state in states for item in state.evidence
        ),
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


def _run_mapping(
    state: ProgramState,
    spec: ClinicalEndpointMappingSpec,
    *,
    request_at: datetime = MAPPING_REQUEST_AT,
    completed_at: datetime = MAPPING_COMPLETED_AT,
):
    registry = register_existing_adapters(
        ToolRegistry(clock=lambda: completed_at),
        clinical_synthesis=ClinicalSynthesisAdapter(),
    )
    environment = GatedDiscoveryEnvironment()
    runner = BoundedStageRunner(
        tool_registry=registry,
        mapper_registry=build_default_semantic_mapper_registry(
            target_association_minimum_score=0.5
        ),
        planner=BoundedPlanner(clock=lambda: request_at),
        environment=environment,
        clock=lambda: completed_at,
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


def _run_synthesis(
    state: ProgramState,
    spec: ClinicalSynthesisSpec,
    *,
    request_at: datetime = REQUEST_AT,
    completed_at: datetime = COMPLETED_AT,
    success_decision: Decision = Decision.ADVANCE,
):
    registry = register_existing_adapters(
        ToolRegistry(clock=lambda: completed_at),
        clinical_synthesis=ClinicalSynthesisAdapter(),
    )
    environment = _synthesis_environment()
    runner = BoundedStageRunner(
        tool_registry=registry,
        mapper_registry=build_default_semantic_mapper_registry(
            target_association_minimum_score=0.5
        ),
        planner=BoundedPlanner(clock=lambda: request_at),
        environment=environment,
        clock=lambda: completed_at,
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
        success_decision=success_decision,
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


def _decision_policy(
    *,
    minimum_independent_trials: int = 2,
    maximum_log_effect_ci_width: float = 0.6,
    minimum_safety_participants_per_arm: int = 60,
    max_planned_actions: int = 2,
    max_planned_cost: float = 0.3,
    minimum_bounded_voi: float = 0.05,
) -> ClinicalDecisionPolicy:
    return ClinicalDecisionPolicy(
        policy_id="synthetic-clinical-workflow-policy",
        version="1",
        registered_on=date(2025, 1, 1),
        minimum_independent_trials=minimum_independent_trials,
        maximum_log_effect_ci_width=maximum_log_effect_ci_width,
        minimum_safety_participants_per_arm=(
            minimum_safety_participants_per_arm
        ),
        max_planned_actions=max_planned_actions,
        max_planned_cost=max_planned_cost,
        minimum_bounded_voi=minimum_bounded_voi,
        metadata={
            "payload_class": "synthetic",
            "clinical_use": "prohibited",
        },
    )


def _decision_actions() -> tuple[ClinicalEvidenceActionOption, ...]:
    return (
        ClinicalEvidenceActionOption(
            action_id="query-independent-trial",
            action_type=ActionType.QUERY_DATABASE,
            tool_id="clinical_trial_portfolio",
            operation="find_source_disjoint_trial",
            purpose="Find one additional source-disjoint eligible trial.",
            targeted_gap_codes=(
                ClinicalEvidenceGapCode.INSUFFICIENT_INDEPENDENT_TRIALS,
            ),
            expected_gap_resolution_probability=0.8,
            decision_relevance=0.9,
            max_cost=0.2,
            arguments={
                "candidate_id": "CHEMBL_TEST",
                "disease_id": "MONDO_TEST",
                "endpoint_family": "progression_free_survival",
            },
            metadata={"payload_class": "synthetic"},
        ),
        ClinicalEvidenceActionOption(
            action_id="retrieve-safety-followup",
            action_type=ActionType.RETRIEVE_EVIDENCE,
            tool_id="clinical_registry_followup",
            operation="retrieve_posted_safety_update",
            purpose="Retrieve a later posted aggregate safety follow-up.",
            targeted_gap_codes=(
                ClinicalEvidenceGapCode.HIGHER_OBSERVED_SERIOUS_EVENT_RISK,
                ClinicalEvidenceGapCode.INSUFFICIENT_SAFETY_EXPOSURE,
            ),
            expected_gap_resolution_probability=0.7,
            decision_relevance=0.8,
            max_cost=0.1,
            arguments={
                "candidate_id": "CHEMBL_TEST",
                "disease_id": "MONDO_TEST",
            },
            metadata={"payload_class": "synthetic"},
        ),
    )


def _closed_loop_mapping_spec() -> ClinicalEndpointMappingSpec:
    base = _mapping_spec()
    trial_ids = ("NCT00000001", "NCT00000002", "NCT00000003")
    return replace(
        base,
        mapping_id="CHEMBL_TEST:MONDO_TEST:pfs-map:v2",
        portfolio_id="CHEMBL_TEST-MONDO_TEST-ctgov-portfolio-v2",
        bindings=tuple(
            ClinicalEndpointSelection(
                trial_id=trial_id,
                design_id=f"{trial_id}:design",
                endpoint_id=f"{trial_id}:endpoint:primary-0",
                safety_id=f"{trial_id}:safety:serious-adverse-events",
            )
            for trial_id in trial_ids
        ),
        review=replace(
            base.review,
            reviewed_at=CLOSED_LOOP_COMPLETED_AT,
        ),
        metadata={
            "review_note": "Synthetic three-trial closed-loop approval.",
            "review_protocol_id": "adds.endpoint-mapping-review.v1",
        },
    )


def _closed_loop_synthesis_spec() -> ClinicalSynthesisSpec:
    return replace(
        _spec(),
        synthesis_id="CHEMBL_TEST:MONDO_TEST:pfs-benefit-risk:v2",
        endpoint_mapping_id="CHEMBL_TEST:MONDO_TEST:pfs-map:v2",
        selections=tuple(
            ClinicalStudySelection(
                trial_id=trial_id,
                design_id=f"{trial_id}:design",
                endpoint_id=f"{trial_id}:endpoint:primary-0",
                safety_id=f"{trial_id}:safety:serious-adverse-events",
            )
            for trial_id in ("NCT00000001", "NCT00000002", "NCT00000003")
        ),
        metadata={
            "review_status": "synthetic_closed_loop_selection",
        },
    )


def _closed_loop_action() -> ClinicalEvidenceActionOption:
    return ClinicalEvidenceActionOption(
        action_id="verify-third-source-disjoint-trial",
        action_type=ActionType.QUERY_DATABASE,
        tool_id="clinical_trial_portfolio",
        operation="verify_source_disjoint_trial",
        purpose=(
            "Verify one captured trial as source-disjoint and eligible for "
            "reviewer harmonization."
        ),
        targeted_gap_codes=(
            ClinicalEvidenceGapCode.INSUFFICIENT_INDEPENDENT_TRIALS,
        ),
        expected_gap_resolution_probability=0.9,
        decision_relevance=0.9,
        max_cost=0.05,
        arguments={
            "candidate_id": "CHEMBL_TEST",
            "disease_id": "MONDO_TEST",
            "trial_id": "NCT00000003",
        },
        metadata={
            "payload_class": "synthetic",
            "provider_auto_promotion": False,
        },
    )


def _closed_loop_policy() -> ClinicalClosedLoopPolicy:
    return ClinicalClosedLoopPolicy(
        policy_id="synthetic-clinical-closed-loop-policy",
        version="1",
        registered_on=date(2025, 1, 1),
        max_refresh_runs=2,
        max_refresh_actions=2,
        max_refresh_cost=0.02,
        metadata={
            "payload_class": "synthetic",
            "clinical_use": "prohibited",
        },
    )


def _eligibility_provider(
    state: ProgramState,
) -> tuple[ToolRegistry, object, SourceReference]:
    third_design = state.trial_designs_by_id["NCT00000003:design"]
    sources = {
        state.evidence_by_id[evidence_id].source
        for evidence_id in third_design.supporting_evidence
    }
    if len(sources) != 1:
        raise AssertionError("synthetic third trial must use one exact source")
    (source,) = tuple(sources)
    registry = ToolRegistry(clock=lambda: CLOSED_LOOP_COMPLETED_AT)
    contract = ToolContract(
        tool_id="clinical_trial_portfolio",
        operation="verify_source_disjoint_trial",
        action_type=ActionType.QUERY_DATABASE,
        description=(
            "Verify one captured trial against the reviewed source-disjoint "
            "portfolio eligibility contract."
        ),
        allowed_stages=(Stage.REGULATORY_POSTMARKET,),
        required_arguments=("candidate_id", "disease_id", "trial_id"),
        default_cost=0.05,
    )

    def handler(arguments):
        return ToolResponse(
            status=ToolStatus.SUCCEEDED,
            payload={
                "eligible": True,
                "source_disjoint": True,
                "trial_id": arguments["trial_id"],
                "candidate_id": arguments["candidate_id"],
                "disease_id": arguments["disease_id"],
            },
            execution_mode=ExecutionMode.REPLAY,
            sources=(source,),
            message="Synthetic source-disjoint trial verification completed.",
        )

    registry.register(contract, handler)
    mappers = build_default_semantic_mapper_registry(
        target_association_minimum_score=0.5
    )

    def mapper(program_state, outcome, context):
        trial_id = outcome.request.arguments["trial_id"]
        draft = EvidenceDraft(
            evidence_id=f"{outcome.request_id}:trial-eligibility",
            request_id=outcome.request_id,
            subject=context.subject,
            predicate="clinical_trial_harmonization_eligibility_verified",
            object_value=trial_id,
            observed_at=context.observed_at,
            available_at=context.available_at,
            source_id=source.source_id,
            biological_context={
                "candidate_id": outcome.request.arguments["candidate_id"],
                "disease_id": outcome.request.arguments["disease_id"],
                "trial_id": trial_id,
                "source_disjoint": True,
                "provider_auto_decision": False,
                "state_version": program_state.version,
            },
            confidence=context.confidence,
            metadata={
                "review_scope": "harmonization_eligibility_only",
                "clinical_acceptability_inferred": False,
            },
        )
        return PromotionResult(
            mapper_id="synthetic_trial_eligibility_v1",
            request_id=outcome.request_id,
            status=PromotionStatus.PROMOTED,
            code="clinical_trial_harmonization_eligibility_promoted",
            message=(
                "Source-disjoint eligibility was promoted without changing "
                "clinical artifacts."
            ),
            evidence_drafts=(draft,),
            recommended_decision=Decision.HOLD,
        )

    mappers.register(
        tool_id=contract.tool_id,
        operation=contract.operation,
        mapper_id="synthetic_trial_eligibility_v1",
        mapper=mapper,
    )
    return registry, mappers, source


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
        cls.synthesis_result, cls.synthesis_environment = _run_synthesis(
            cls.state,
            _spec(),
        )
        if cls.synthesis_result.status is not StageRunStatus.COMMITTED:
            raise AssertionError(cls.synthesis_result.code)
        cls.committed_state = cls.synthesis_result.final_state
        cls.committed_synthesis = (
            cls.committed_state.benefit_risk_syntheses[0]
        )

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

    def test_tensor_advances_workflow_without_acceptability_inference(self) -> None:
        package = compile_clinical_decision_package(
            self.committed_state,
            self.committed_synthesis,
            _decision_policy(),
            _decision_actions(),
            package_id="synthetic-clinical-decision-package",
            tensor_id="synthetic-clinical-evidence-tensor",
            plan_id="synthetic-clinical-decision-plan",
        )
        self.assertIs(package.plan.decision, Decision.ADVANCE)
        self.assertEqual(package.plan.selected_actions, ())
        self.assertEqual(package.tensor.gaps, ())
        self.assertEqual(len(package.tensor.cells), 2)
        self.assertEqual(
            package.tensor.source_content_hashes,
            self.committed_synthesis.source_content_hashes,
        )
        self.assertTrue(
            all(
                item.status is ClinicalDimensionStatus.SATISFIED
                for item in package.tensor.dimensions
            )
        )
        self.assertFalse(package.tensor.pooling_performed)
        self.assertFalse(package.tensor.clinical_acceptability_inferred)
        self.assertFalse(package.plan.clinical_acceptability_inferred)
        self.assertEqual(
            validate_clinical_decision_package(
                self.committed_state,
                package,
            ),
            (),
        )

    def test_gap_tensor_selects_marginal_voi_action_within_budget(self) -> None:
        package = compile_clinical_decision_package(
            self.committed_state,
            self.committed_synthesis,
            _decision_policy(
                minimum_independent_trials=3,
                minimum_safety_participants_per_arm=100,
                max_planned_cost=0.25,
            ),
            _decision_actions(),
            package_id="synthetic-gap-package",
            tensor_id="synthetic-gap-tensor",
            plan_id="synthetic-gap-plan",
        )
        self.assertIs(package.plan.decision, Decision.HOLD)
        self.assertEqual(
            tuple(item.code for item in package.tensor.gaps),
            (
                ClinicalEvidenceGapCode.INSUFFICIENT_INDEPENDENT_TRIALS,
                ClinicalEvidenceGapCode.INSUFFICIENT_SAFETY_EXPOSURE,
            ),
        )
        self.assertEqual(len(package.plan.selected_actions), 1)
        selection = package.plan.selected_actions[0]
        self.assertEqual(selection.action_id, "retrieve-safety-followup")
        self.assertTrue(math.isclose(package.plan.planned_cost, 0.1))
        self.assertEqual(
            package.plan.targeted_gap_ids,
            (
                "synthetic-gap-tensor:gap:"
                "insufficient_safety_exposure",
            ),
        )
        self.assertEqual(
            package.plan.untargeted_gap_ids,
            (
                "synthetic-gap-tensor:gap:"
                "insufficient_independent_trials",
            ),
        )

    def test_equal_voi_actions_use_action_id_tie_break(self) -> None:
        common = {
            "action_type": ActionType.QUERY_DATABASE,
            "tool_id": "clinical_trial_portfolio",
            "operation": "find_source_disjoint_trial",
            "purpose": "Find one additional source-disjoint eligible trial.",
            "targeted_gap_codes": (
                ClinicalEvidenceGapCode.INSUFFICIENT_INDEPENDENT_TRIALS,
            ),
            "expected_gap_resolution_probability": 0.8,
            "decision_relevance": 0.9,
            "max_cost": 0.2,
            "arguments": {"candidate_id": "CHEMBL_TEST"},
        }
        actions = (
            ClinicalEvidenceActionOption(action_id="action-b", **common),
            ClinicalEvidenceActionOption(action_id="action-a", **common),
        )
        package = compile_clinical_decision_package(
            self.committed_state,
            self.committed_synthesis,
            _decision_policy(
                minimum_independent_trials=3,
                max_planned_actions=1,
            ),
            actions,
            package_id="synthetic-tie-package",
            tensor_id="synthetic-tie-tensor",
            plan_id="synthetic-tie-plan",
        )
        self.assertEqual(
            package.plan.selected_actions[0].action_id,
            "action-a",
        )
        self.assertEqual(
            tuple(item.action_id for item in package.action_catalog),
            ("action-a", "action-b"),
        )

    def test_unaffordable_action_defers_without_partial_plan(self) -> None:
        constrained_state = replace(
            self.committed_state,
            budget=BudgetState(
                limit=self.committed_state.budget.spent + 0.05,
                spent=self.committed_state.budget.spent,
            ),
        )
        package = compile_clinical_decision_package(
            constrained_state,
            self.committed_synthesis,
            _decision_policy(minimum_independent_trials=3),
            (_decision_actions()[0],),
            package_id="synthetic-budget-package",
            tensor_id="synthetic-budget-tensor",
            plan_id="synthetic-budget-plan",
        )
        self.assertIs(package.plan.decision, Decision.DEFER)
        self.assertEqual(
            package.plan.code,
            "clinical_evidence_action_budget_insufficient",
        )
        self.assertEqual(package.plan.selected_actions, ())
        self.assertEqual(package.plan.planned_cost, 0.0)

    def test_open_gap_without_catalog_action_defers(self) -> None:
        package = compile_clinical_decision_package(
            self.committed_state,
            self.committed_synthesis,
            _decision_policy(minimum_independent_trials=3),
            (),
            package_id="synthetic-no-action-package",
            tensor_id="synthetic-no-action-tensor",
            plan_id="synthetic-no-action-plan",
        )
        self.assertIs(package.plan.decision, Decision.DEFER)
        self.assertEqual(
            package.plan.code,
            "clinical_evidence_gaps_unaddressed",
        )
        self.assertEqual(
            package.plan.untargeted_gap_ids,
            package.plan.open_gap_ids,
        )

    def test_higher_observed_safety_signal_holds_and_never_terminates(self) -> None:
        safety_unmapped = _combined_state(
            second_candidate_serious_num_affected=30
        )
        mapping_result, _ = _run_mapping(
            safety_unmapped,
            _mapping_spec(),
        )
        self.assertIs(mapping_result.status, StageRunStatus.COMMITTED)
        synthesis_result, _ = _run_synthesis(
            mapping_result.final_state,
            _spec(),
        )
        self.assertIs(synthesis_result.status, StageRunStatus.COMMITTED)
        safety_state = synthesis_result.final_state
        package = compile_clinical_decision_package(
            safety_state,
            safety_state.benefit_risk_syntheses[0],
            _decision_policy(),
            _decision_actions(),
            package_id="synthetic-safety-signal-package",
            tensor_id="synthetic-safety-signal-tensor",
            plan_id="synthetic-safety-signal-plan",
        )
        self.assertIn(
            ClinicalEvidenceGapCode.HIGHER_OBSERVED_SERIOUS_EVENT_RISK,
            {item.code for item in package.tensor.gaps},
        )
        safety_dimension = next(
            item
            for item in package.tensor.dimensions
            if item.dimension is ClinicalEvidenceDimension.SAFETY_DIRECTION
        )
        self.assertIs(
            safety_dimension.status,
            ClinicalDimensionStatus.BLOCKING_SIGNAL,
        )
        self.assertIs(package.plan.decision, Decision.HOLD)
        self.assertFalse(package.plan.terminal_decision_issued)
        self.assertFalse(package.plan.clinical_acceptability_inferred)

    def test_uncommitted_synthesis_cannot_compile_tensor(self) -> None:
        uncommitted = compile_benefit_risk_synthesis(self.state, _spec())
        with self.assertRaisesRegex(
            ValueError,
            "committed state ledger",
        ):
            compile_clinical_evidence_tensor(
                self.state,
                uncommitted,
                _decision_policy(),
                tensor_id="uncommitted-synthesis-tensor",
            )

    def test_policy_safety_boundaries_cannot_be_disabled(self) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "clinical_acceptability_inference_prohibited must be true",
        ):
            replace(
                _decision_policy(),
                clinical_acceptability_inference_prohibited=False,
            )
        with self.assertRaisesRegex(
            ValueError,
            "terminal_decisions_prohibited must be true",
        ):
            replace(
                _decision_policy(),
                terminal_decisions_prohibited=False,
            )

    def test_cell_direction_and_source_overlap_tampering_fail_closed(self) -> None:
        package = compile_clinical_decision_package(
            self.committed_state,
            self.committed_synthesis,
            _decision_policy(),
            _decision_actions(),
            package_id="synthetic-cell-integrity-package",
            tensor_id="synthetic-cell-integrity-tensor",
            plan_id="synthetic-cell-integrity-plan",
        )
        first, second = package.tensor.cells
        with self.assertRaisesRegex(
            ValueError,
            "benefit_direction does not match",
        ):
            replace(first, benefit_direction="harm")
        overlapping = replace(
            second,
            source_content_hashes=first.source_content_hashes,
        )
        with self.assertRaisesRegex(
            ValueError,
            "pairwise disjoint",
        ):
            replace(package.tensor, cells=(first, overlapping))

    def test_gap_provenance_must_equal_implicated_study_union(self) -> None:
        package = compile_clinical_decision_package(
            self.committed_state,
            self.committed_synthesis,
            _decision_policy(minimum_independent_trials=3),
            _decision_actions(),
            package_id="synthetic-gap-provenance-package",
            tensor_id="synthetic-gap-provenance-tensor",
            plan_id="synthetic-gap-provenance-plan",
        )
        gap = package.tensor.gaps[0]
        forged_gap = replace(
            gap,
            study_record_ids=(
                package.tensor.cells[0].study_record_id,
            ),
            source_evidence_ids=package.tensor.source_evidence_ids,
        )
        with self.assertRaisesRegex(
            ValueError,
            "does not match implicated studies",
        ):
            replace(package.tensor, gaps=(forged_gap,))

    def test_post_cutoff_policy_and_duplicate_actions_fail_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "after the program cutoff"):
            compile_clinical_evidence_tensor(
                self.committed_state,
                self.committed_synthesis,
                replace(
                    _decision_policy(),
                    registered_on=date(2025, 1, 3),
                ),
                tensor_id="post-cutoff-policy-tensor",
            )
        duplicate = _decision_actions()[0]
        with self.assertRaisesRegex(
            ValueError,
            "action ids must be unique",
        ):
            compile_clinical_decision_package(
                self.committed_state,
                self.committed_synthesis,
                _decision_policy(minimum_independent_trials=3),
                (duplicate, duplicate),
                package_id="duplicate-action-package",
                tensor_id="duplicate-action-tensor",
                plan_id="duplicate-action-plan",
            )

    def test_actions_below_voi_threshold_defer_without_selection(self) -> None:
        package = compile_clinical_decision_package(
            self.committed_state,
            self.committed_synthesis,
            _decision_policy(
                minimum_independent_trials=3,
                minimum_bounded_voi=0.5,
            ),
            (_decision_actions()[0],),
            package_id="synthetic-low-voi-package",
            tensor_id="synthetic-low-voi-tensor",
            plan_id="synthetic-low-voi-plan",
        )
        self.assertIs(package.plan.decision, Decision.DEFER)
        self.assertEqual(
            package.plan.code,
            "clinical_evidence_actions_below_voi_threshold",
        )
        self.assertEqual(package.plan.selected_actions, ())

    def test_package_strict_envelope_round_trip(self) -> None:
        package = compile_clinical_decision_package(
            self.committed_state,
            self.committed_synthesis,
            _decision_policy(minimum_independent_trials=3),
            _decision_actions(),
            package_id="synthetic-round-trip-package",
            tensor_id="synthetic-round-trip-tensor",
            plan_id="synthetic-round-trip-plan",
        )
        envelope = clinical_decision_package_envelope(package)
        self.assertEqual(
            clinical_decision_package_from_dict(envelope),
            package,
        )
        self.assertEqual(
            clinical_decision_package_from_json(
                json.dumps(envelope, sort_keys=True)
            ),
            package,
        )

    def test_package_integrity_and_duplicate_keys_fail_closed(self) -> None:
        package = compile_clinical_decision_package(
            self.committed_state,
            self.committed_synthesis,
            _decision_policy(),
            _decision_actions(),
            package_id="synthetic-integrity-package",
            tensor_id="synthetic-integrity-tensor",
            plan_id="synthetic-integrity-plan",
        )
        envelope = clinical_decision_package_envelope(package)
        forged = json.loads(json.dumps(envelope))
        forged["package"]["plan"]["code"] = "forged"
        with self.assertRaisesRegex(
            RecordParseError,
            "integrity hash does not match",
        ):
            clinical_decision_package_from_dict(forged)
        payload = json.dumps(envelope, sort_keys=True)
        duplicated = payload.replace(
            '"schema_version":',
            '"schema_version":"forged","schema_version":',
            1,
        )
        with self.assertRaisesRegex(RecordParseError, "duplicates key"):
            clinical_decision_package_from_json(duplicated)

    def test_package_constructor_rejects_plan_tamper(self) -> None:
        package = compile_clinical_decision_package(
            self.committed_state,
            self.committed_synthesis,
            _decision_policy(),
            _decision_actions(),
            package_id="synthetic-replay-package",
            tensor_id="synthetic-replay-tensor",
            plan_id="synthetic-replay-plan",
        )
        with self.assertRaisesRegex(
            ValueError,
            "deterministic bounded-VOI replay",
        ):
            replace(
                package,
                plan=replace(
                    package.plan,
                    code="self-consistent-but-not-recompiled",
                ),
            )

    def test_public_decision_schema_matches_strict_reader(self) -> None:
        schema = json.loads(DECISION_SCHEMA.read_text(encoding="utf-8"))
        example = json.loads(DECISION_EXAMPLE.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(example)
        parsed = clinical_decision_package_from_dict(example)
        self.assertEqual(
            clinical_decision_package_envelope(parsed),
            example,
        )


class ClinicalClosedLoopTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.unmapped_state = _combined_three_trial_state()
        mapping_result, _ = _run_mapping(
            cls.unmapped_state,
            _mapping_spec(),
        )
        if mapping_result.status is not StageRunStatus.COMMITTED:
            raise AssertionError(mapping_result.code)
        synthesis_result, _ = _run_synthesis(
            mapping_result.final_state,
            _spec(),
            success_decision=Decision.HOLD,
        )
        if synthesis_result.status is not StageRunStatus.COMMITTED:
            raise AssertionError(synthesis_result.code)
        cls.before_state = synthesis_result.final_state
        if cls.before_state.is_terminal:
            raise AssertionError("closed-loop fixture must remain active")
        cls.before_synthesis = cls.before_state.benefit_risk_syntheses_by_id[
            _spec().synthesis_id
        ]
        cls.decision_policy = _decision_policy(
            minimum_independent_trials=3,
            minimum_safety_participants_per_arm=60,
            max_planned_actions=1,
            max_planned_cost=0.05,
            minimum_bounded_voi=0.05,
        )
        cls.before_package = compile_clinical_decision_package(
            cls.before_state,
            cls.before_synthesis,
            cls.decision_policy,
            (_closed_loop_action(),),
            package_id="synthetic-closed-loop-before-package",
            tensor_id="synthetic-closed-loop-before-tensor",
            plan_id="synthetic-closed-loop-before-plan",
        )
        cls.closed_loop_policy = _closed_loop_policy()
        cls.execution_batch = compile_clinical_execution_batch(
            cls.before_state,
            cls.before_package,
            cls.closed_loop_policy,
            batch_id="synthetic-closed-loop-batch",
        )
        tool_registry, mapper_registry, source = _eligibility_provider(
            cls.before_state
        )
        cls.third_source = source
        call_id = cls.execution_batch.calls[0].call_id
        cls.acquisition_run = execute_clinical_evidence_batch(
            cls.before_state,
            cls.before_package,
            cls.execution_batch,
            tool_registry=tool_registry,
            mapper_registry=mapper_registry,
            promotion_contexts={
                call_id: PromotionContext(
                    observed_at=date(2025, 1, 2),
                    available_at=date(2025, 1, 2),
                    subject="Test Drug",
                    object_value="NCT00000003",
                    confidence=1.0,
                    candidate_id="CHEMBL_TEST",
                    candidate_name="Test Drug",
                    modality="small molecule",
                    biological_context={
                        "candidate_id": "CHEMBL_TEST",
                        "disease_id": "MONDO_TEST",
                        "trial_id": "NCT00000003",
                    },
                )
            },
            planner=BoundedPlanner(clock=lambda: CLOSED_LOOP_REQUEST_AT),
            clock=lambda: CLOSED_LOOP_COMPLETED_AT,
            run_id="synthetic-closed-loop-acquisition",
        )
        if cls.acquisition_run.status is not StageRunStatus.COMMITTED:
            raise AssertionError(cls.acquisition_run.code)
        cls.mapping_refresh_run, _ = _run_mapping(
            cls.acquisition_run.final_state,
            _closed_loop_mapping_spec(),
            request_at=CLOSED_LOOP_MAPPING_REQUEST_AT,
            completed_at=CLOSED_LOOP_MAPPING_COMPLETED_AT,
        )
        if cls.mapping_refresh_run.status is not StageRunStatus.COMMITTED:
            raise AssertionError(cls.mapping_refresh_run.code)
        cls.synthesis_refresh_run, _ = _run_synthesis(
            cls.mapping_refresh_run.final_state,
            _closed_loop_synthesis_spec(),
            request_at=CLOSED_LOOP_SYNTHESIS_REQUEST_AT,
            completed_at=CLOSED_LOOP_SYNTHESIS_COMPLETED_AT,
            success_decision=Decision.HOLD,
        )
        if cls.synthesis_refresh_run.status is not StageRunStatus.COMMITTED:
            raise AssertionError(cls.synthesis_refresh_run.code)
        cls.after_state = cls.synthesis_refresh_run.final_state
        cls.after_synthesis = cls.after_state.benefit_risk_syntheses_by_id[
            _closed_loop_synthesis_spec().synthesis_id
        ]
        cls.transition = compile_clinical_evidence_transition(
            cls.before_state,
            cls.before_package,
            cls.execution_batch,
            cls.acquisition_run,
            (cls.mapping_refresh_run, cls.synthesis_refresh_run),
            cls.after_synthesis,
            transition_id="synthetic-clinical-evidence-transition",
            after_package_id="synthetic-closed-loop-after-package",
            after_tensor_id="synthetic-closed-loop-after-tensor",
            after_plan_id="synthetic-closed-loop-after-plan",
        )

    def test_end_to_end_cycle_resolves_gap_with_exact_source_rejoin(self) -> None:
        transition = self.transition
        self.assertIsInstance(transition, ClinicalEvidenceTransitionPackage)
        self.assertIs(transition.before_decision, Decision.HOLD)
        self.assertIs(transition.after_decision, Decision.ADVANCE)
        self.assertEqual(
            transition.resolved_gap_codes,
            (ClinicalEvidenceGapCode.INSUFFICIENT_INDEPENDENT_TRIALS,),
        )
        self.assertEqual(transition.persisted_gap_codes, ())
        self.assertEqual(transition.new_gap_codes, ())
        self.assertEqual(
            transition.added_source_content_hashes,
            (self.third_source.content_hash,),
        )
        receipt = transition.selected_action_receipts[0]
        self.assertIn(
            self.third_source.content_hash,
            receipt.outcome.source_content_hashes,
        )
        self.assertIs(receipt.outcome.status, ToolStatus.SUCCEEDED)
        self.assertEqual(len(receipt.outcome.evidence_ids), 1)
        self.assertEqual(
            validate_clinical_evidence_transition(
                self.before_state,
                self.after_state,
                transition,
            ),
            (),
        )

    def test_cycle_is_bounded_and_consumes_attempted_action(self) -> None:
        transition = self.transition
        self.assertEqual(
            transition.consumed_action_ids,
            ("verify-third-source-disjoint-trial",),
        )
        self.assertEqual(transition.remaining_action_ids, ())
        self.assertEqual(transition.after_package.action_catalog, ())
        self.assertTrue(math.isclose(transition.acquisition_cost, 0.05))
        self.assertTrue(math.isclose(transition.refresh_cost, 0.02))
        self.assertTrue(math.isclose(transition.total_cost, 0.07))
        self.assertTrue(
            math.isclose(
                transition.budget_spent_after
                - transition.budget_spent_before,
                transition.total_cost,
            )
        )
        self.assertEqual(
            transition.after_state_version,
            transition.before_state_version + 3,
        )

    def test_execution_batch_is_exactly_bound_to_selected_voi_action(self) -> None:
        batch = self.execution_batch
        selection = self.before_package.plan.selected_actions[0]
        option = self.before_package.action_catalog[0]
        call = batch.calls[0]
        self.assertEqual(call.rank, selection.rank)
        self.assertEqual(call.action_id, option.action_id)
        self.assertEqual(call.action_fingerprint, option.fingerprint)
        self.assertEqual(call.targeted_gap_ids, selection.targeted_gap_ids)
        self.assertEqual(call.arguments, option.arguments)
        self.assertEqual(batch.max_total_cost, selection.max_cost)
        self.assertEqual(
            self.acquisition_run.plan_result.details["stage_plan_metadata"][
                "clinical_execution_batch_fingerprint"
            ],
            batch.fingerprint,
        )

    def test_refresh_receipts_are_reviewer_verifier_only(self) -> None:
        self.assertEqual(len(self.transition.refresh_receipts), 2)
        for receipt in self.transition.refresh_receipts:
            self.assertIs(receipt.decision, Decision.HOLD)
            self.assertEqual(len(receipt.outcomes), 1)
            self.assertIs(
                receipt.outcomes[0].action_type,
                ActionType.RUN_VERIFIER,
            )
            self.assertIs(receipt.outcomes[0].status, ToolStatus.SUCCEEDED)

    def test_refresh_receipt_lineage_matches_committed_packet(self) -> None:
        original = self.transition.refresh_receipts[0]
        for forged in (
            replace(original, run_id="forged-refresh-run"),
            replace(original, plan_id="forged-refresh-plan"),
            replace(original, promotion_codes=("forged_promotion",)),
        ):
            with self.subTest(forged=forged):
                transition = replace(
                    self.transition,
                    refresh_receipts=(
                        forged,
                        self.transition.refresh_receipts[1],
                    ),
                )
                self.assertEqual(
                    validate_clinical_evidence_transition(
                        self.before_state,
                        self.after_state,
                        transition,
                    ),
                    ("refresh_packet_metadata_mismatch",),
                )

    def test_refresh_run_must_append_governed_artifact(self) -> None:
        original = self.mapping_refresh_run
        forged_packet = replace(
            original.accepted_packets[0],
            claim_updates=(),
            clinical_endpoint_mapping_updates=(),
        )
        forged_result = GatedDiscoveryEnvironment().transition(
            original.initial_state,
            forged_packet,
        )
        self.assertTrue(forged_result.applied, forged_result.reason)
        forged_run = replace(
            original,
            final_state=forged_result.state,
            attempted_packets=(forged_packet,),
            transition_results=(forged_result,),
        )
        with self.assertRaisesRegex(
            ClinicalClosedLoopError,
            "must append only governed mapping or synthesis artifacts",
        ):
            compile_clinical_evidence_transition(
                self.before_state,
                self.before_package,
                self.execution_batch,
                self.acquisition_run,
                (forged_run,),
                self.before_synthesis,
                transition_id="no-op-refresh-transition",
                after_package_id="no-op-refresh-after-package",
                after_tensor_id="no-op-refresh-after-tensor",
                after_plan_id="no-op-refresh-after-plan",
            )

    def test_stale_execution_batch_fails_before_provider_invocation(self) -> None:
        with self.assertRaisesRegex(
            ClinicalClosedLoopError,
            "before decision package failed replay",
        ):
            execute_clinical_evidence_batch(
                self.acquisition_run.final_state,
                self.before_package,
                self.execution_batch,
                tool_registry=ToolRegistry(),
                mapper_registry=build_default_semantic_mapper_registry(
                    target_association_minimum_score=0.5
                ),
                promotion_contexts={},
            )

    def test_acquisition_cannot_bypass_reviewer_synthesis_refresh(self) -> None:
        forged_synthesis = compile_benefit_risk_synthesis(
            self.before_state,
            replace(
                _spec(),
                synthesis_id="forged-acquisition-synthesis",
            ),
        )
        source_count = len(forged_synthesis.supporting_evidence)
        template_evidence = self.before_state.evidence_by_id[
            self.before_synthesis.supporting_evidence[source_count]
        ]
        forged_evidence_id = "forged-acquisition-synthesis:evidence"
        forged_context = to_primitive(template_evidence.biological_context)
        forged_context["synthesis_id"] = forged_synthesis.synthesis_id
        forged_evidence = replace(
            template_evidence,
            evidence_id=forged_evidence_id,
            biological_context=forged_context,
        )
        forged_synthesis = replace(
            forged_synthesis,
            supporting_evidence=(
                *forged_synthesis.supporting_evidence,
                forged_evidence_id,
            ),
        )
        forged_packet = replace(
            self.acquisition_run.accepted_packets[0],
            evidence_additions=(
                *self.acquisition_run.accepted_packets[0].evidence_additions,
                forged_evidence,
            ),
            benefit_risk_synthesis_updates=(forged_synthesis,),
        )
        forged_result = GatedDiscoveryEnvironment().transition(
            self.before_state,
            forged_packet,
        )
        self.assertTrue(
            forged_result.applied,
            to_primitive(forged_result.verifier_results),
        )
        forged_run = replace(
            self.acquisition_run,
            final_state=forged_result.state,
            attempted_packets=(forged_packet,),
            transition_results=(forged_result,),
        )
        with self.assertRaisesRegex(
            ClinicalClosedLoopError,
            "cannot directly refresh governed clinical artifacts",
        ):
            compile_clinical_evidence_transition(
                self.before_state,
                self.before_package,
                self.execution_batch,
                forged_run,
                (),
                forged_synthesis,
                transition_id="forged-acquisition-transition",
                after_package_id="forged-acquisition-after-package",
                after_tensor_id="forged-acquisition-after-tensor",
                after_plan_id="forged-acquisition-after-plan",
            )

    def test_transition_envelope_round_trips_strictly(self) -> None:
        envelope = clinical_evidence_transition_envelope(self.transition)
        self.assertEqual(
            clinical_evidence_transition_from_dict(envelope),
            self.transition,
        )
        self.assertEqual(
            clinical_evidence_transition_from_json(
                json.dumps(envelope, sort_keys=True)
            ),
            self.transition,
        )

    def test_public_closed_loop_schema_matches_compiler_and_reader(self) -> None:
        schema = json.loads(CLOSED_LOOP_SCHEMA.read_text(encoding="utf-8"))
        decision_schema = json.loads(
            DECISION_SCHEMA.read_text(encoding="utf-8")
        )
        example = json.loads(CLOSED_LOOP_EXAMPLE.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        registry = Registry().with_resource(
            decision_schema["$id"],
            Resource.from_contents(decision_schema),
        )
        Draft202012Validator(schema, registry=registry).validate(example)
        self.assertEqual(
            clinical_evidence_transition_envelope(self.transition),
            example,
        )
        parsed = clinical_evidence_transition_from_dict(example)
        self.assertEqual(parsed, self.transition)

    def test_transition_integrity_and_duplicate_keys_fail_closed(self) -> None:
        envelope = clinical_evidence_transition_envelope(self.transition)
        forged = json.loads(json.dumps(envelope))
        forged["transition"]["after_decision"] = "defer"
        with self.assertRaisesRegex(
            RecordParseError,
            "integrity hash does not match",
        ):
            clinical_evidence_transition_from_dict(forged)
        payload = json.dumps(envelope, sort_keys=True)
        duplicated = payload.replace(
            '"schema_version":',
            '"schema_version":"forged","schema_version":',
            1,
        )
        with self.assertRaisesRegex(RecordParseError, "duplicates key"):
            clinical_evidence_transition_from_json(duplicated)

    def test_resolved_gap_rejects_unbound_source_provenance(self) -> None:
        receipt = self.transition.selected_action_receipts[0]
        forged_source = replace(
            receipt.outcome.sources[0],
            content_hash="f" * 64,
        )
        forged_outcome = replace(
            receipt.outcome,
            sources=(forged_source,),
        )
        with self.assertRaisesRegex(
            ValueError,
            "new tensor sources are not bound",
        ):
            replace(
                self.transition,
                selected_action_receipts=(
                    replace(receipt, outcome=forged_outcome),
                ),
            )

    def test_refresh_cost_above_preregistered_bound_is_rejected(self) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "refresh_cost exceeds",
        ):
            replace(
                self.transition,
                closed_loop_policy=replace(
                    self.closed_loop_policy,
                    max_refresh_cost=0.01,
                ),
                execution_batch=replace(
                    self.execution_batch,
                    closed_loop_policy=replace(
                        self.closed_loop_policy,
                        max_refresh_cost=0.01,
                    ),
                ),
            )

    def test_terminal_state_cannot_compile_execution_batch(self) -> None:
        terminal_result, _ = _run_synthesis(
            self.mapping_refresh_run.final_state,
            _closed_loop_synthesis_spec(),
            request_at=CLOSED_LOOP_SYNTHESIS_REQUEST_AT,
            completed_at=CLOSED_LOOP_SYNTHESIS_COMPLETED_AT,
        )
        self.assertTrue(terminal_result.final_state.is_terminal)
        terminal_synthesis = terminal_result.final_state.benefit_risk_syntheses_by_id[
            _closed_loop_synthesis_spec().synthesis_id
        ]
        terminal_package = compile_clinical_decision_package(
            terminal_result.final_state,
            terminal_synthesis,
            self.decision_policy,
            (),
            package_id="terminal-package",
            tensor_id="terminal-tensor",
            plan_id="terminal-plan",
        )
        with self.assertRaisesRegex(
            ValueError,
            "terminal programs",
        ):
            compile_clinical_execution_batch(
                terminal_result.final_state,
                terminal_package,
                self.closed_loop_policy,
                batch_id="terminal-batch",
            )


if __name__ == "__main__":
    unittest.main()
