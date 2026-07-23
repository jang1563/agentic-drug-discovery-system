from __future__ import annotations

import unittest
from datetime import date, datetime, timedelta, timezone

from agentic_drug_discovery import (
    ActionType,
    BoundedPlanner,
    BoundedStageRunner,
    BudgetState,
    CandidateRecord,
    CandidateStatus,
    ClaimDisposition,
    Decision,
    DiseaseRecord,
    EvidenceEvent,
    EvidenceRelation,
    ExecutionMode,
    InterventionRecord,
    ProgramState,
    ProgramStatus,
    PromotionContext,
    SourceReference,
    Stage,
    StagePlan,
    TargetRecord,
    TrialRecord,
    ToolCallSpec,
    ToolContract,
    ToolRegistry,
    ToolResponse,
    ToolStatus,
    build_default_semantic_mapper_registry,
)


REQUEST_AT = datetime(2025, 1, 1, tzinfo=timezone.utc)
COMPLETED_AT = REQUEST_AT + timedelta(minutes=1)


def candidate() -> CandidateRecord:
    return CandidateRecord(
        candidate_id="CHEMBL_TEST",
        name="Test Drug",
        modality="small molecule",
        stage=Stage.CANDIDATE_GENERATION,
        status=CandidateStatus.ACTIVE,
        attributes={
            "origin": "test",
            "target_record_id": "ENSG_TEST1",
            "target_chembl_id": "CHEMBL_TARGET",
            "target_symbol": "TEST1",
            "disease_id": "MONDO_TEST",
        },
    )


def target(*, with_chembl: bool) -> TargetRecord:
    identifiers = {"ensembl_gene": "ENSG_TEST1", "gene_symbol": "TEST1"}
    if with_chembl:
        identifiers["chembl_target"] = "CHEMBL_TARGET"
    return TargetRecord(
        target_id="ENSG_TEST1",
        symbol="TEST1",
        disease_id="MONDO_TEST",
        organism="Homo sapiens",
        stage=(
            Stage.MODALITY_SELECTION
            if with_chembl
            else Stage.TARGET_NOMINATION
        ),
        identifiers=identifiers,
    )


def state(
    stage: Stage,
    *,
    with_candidate: bool = False,
    program_id: str | None = None,
    clinical_intervention_id: str = "CHEMBL_TEST",
) -> ProgramState:
    targets = ()
    if stage is Stage.MODALITY_SELECTION:
        targets = (target(with_chembl=False),)
    elif stage in {
        Stage.CANDIDATE_GENERATION,
        Stage.LEAD_OPTIMIZATION,
        Stage.PRECLINICAL_VALIDATION,
    } or with_candidate:
        targets = (target(with_chembl=True),)
    evidence = ()
    diseases = ()
    interventions = ()
    trials = ()
    if stage is not Stage.DISEASE_CONTEXT:
        disease_evidence = EvidenceEvent(
            evidence_id=f"{stage.value}:preloaded-disease-identity",
            stage=Stage.DISEASE_CONTEXT,
            subject="test disease",
            predicate="disease_context_resolved",
            object_value="MONDO_TEST",
            source=SourceReference(
                source_id="test-disease-identity",
                source_version="fixture-v1",
                locator="fixture://tests/semantic-mappings/disease",
                content_hash="0" * 64,
            ),
            observed_at=date(2024, 1, 1),
            available_at=date(2024, 1, 2),
            relation=EvidenceRelation.SUPPORTS,
            biological_context={"disease_id": "MONDO_TEST"},
        )
        evidence = (disease_evidence,)
        diseases = (
            DiseaseRecord(
                disease_id="MONDO_TEST",
                name="test disease",
                stage=Stage.DISEASE_CONTEXT,
                identifiers={"canonical": "MONDO_TEST"},
                supporting_evidence=(disease_evidence.evidence_id,),
            ),
        )
        if stage is Stage.REGULATORY_POSTMARKET and with_candidate:
            clinical_identity = EvidenceEvent(
                evidence_id="clinical:preloaded-intervention-identity",
                stage=Stage.CLINICAL_STRATEGY,
                subject="Test Drug",
                predicate="clinical_trial_identity_resolved",
                object_value="NCT00000001",
                source=SourceReference(
                    source_id="test-clinical-identity",
                    source_version="fixture-v1",
                    locator="fixture://tests/semantic-mappings/clinical",
                    content_hash="1" * 64,
                ),
                observed_at=date(2024, 6, 1),
                available_at=date(2024, 6, 2),
                relation=EvidenceRelation.SUPPORTS,
                biological_context={
                    "candidate_id": "CHEMBL_TEST",
                    "intervention_id": clinical_intervention_id,
                    "disease_id": "MONDO_TEST",
                    "trial_id": "NCT00000001",
                    "registry": "ClinicalTrials.gov",
                },
            )
            evidence = (*evidence, clinical_identity)
            interventions = (
                InterventionRecord(
                    intervention_id=clinical_intervention_id,
                    name="Test Drug",
                    candidate_id="CHEMBL_TEST",
                    disease_id="MONDO_TEST",
                    modality="small molecule",
                    stage=Stage.CLINICAL_STRATEGY,
                    identifiers={
                        "canonical": clinical_intervention_id,
                        "chembl_molecule": "CHEMBL_TEST",
                    },
                    supporting_evidence=(clinical_identity.evidence_id,),
                    attributes={"clinical_trial_ids": ["NCT00000001"]},
                ),
            )
            trials = (
                TrialRecord(
                    trial_id="NCT00000001",
                    registry="ClinicalTrials.gov",
                    intervention_id=clinical_intervention_id,
                    disease_id="MONDO_TEST",
                    stage=Stage.CLINICAL_STRATEGY,
                    identifiers={
                        "canonical": "NCT00000001",
                        "clinicaltrials_gov": "NCT00000001",
                    },
                    supporting_evidence=(clinical_identity.evidence_id,),
                ),
            )
    return ProgramState(
        program_id=program_id or f"semantic-program-{stage.value}",
        disease="test disease",
        therapeutic_hypothesis="Operation-specific evidence controls the next decision.",
        as_of_date=date(2025, 1, 1),
        current_stage=stage,
        budget=BudgetState(limit=3.0),
        evidence=evidence,
        diseases=diseases,
        targets=targets,
        candidates=(candidate(),) if with_candidate else (),
        interventions=interventions,
        trials=trials,
    )


def stage_evidence(run) -> tuple:
    return tuple(
        item
        for item in run.final_state.evidence
        if item.stage is run.initial_state.current_stage
    )


def context(**overrides) -> PromotionContext:
    values = {
        "observed_at": date(2024, 12, 1),
        "available_at": date(2024, 12, 2),
        "subject": "Test Drug",
        "object_value": "test disease",
        "confidence": 0.9,
        "candidate_id": "CHEMBL_TEST",
        "candidate_name": "Test Drug",
        "modality": "small molecule",
        "biological_context": {"disease_id": "MONDO_TEST"},
    }
    values.update(overrides)
    return PromotionContext(**values)


def run_stage(
    *,
    current_state: ProgramState,
    contract: ToolContract,
    response: ToolResponse,
    plan: StagePlan,
    promotion_context: PromotionContext,
):
    registry = ToolRegistry(clock=lambda: COMPLETED_AT)
    registry.register(contract, lambda arguments: response)
    runner = BoundedStageRunner(
        tool_registry=registry,
        mapper_registry=build_default_semantic_mapper_registry(
            target_association_minimum_score=0.5
        ),
        planner=BoundedPlanner(clock=lambda: REQUEST_AT),
        clock=lambda: COMPLETED_AT,
    )
    return runner.run_stage(
        run_id=f"semantic-run-{current_state.current_stage.value}",
        state=current_state,
        stage_plan=plan,
        promotion_contexts={plan.calls[0].call_id: promotion_context},
    )


class SemanticMappingTests(unittest.TestCase):
    def test_disease_profile_context_does_not_satisfy_unmet_need_gate(self) -> None:
        current_state = state(Stage.DISEASE_CONTEXT)
        contract = ToolContract(
            tool_id="opentargets",
            operation="disease_profile",
            action_type=ActionType.QUERY_DATABASE,
            description="Resolve disease identity and page metadata.",
            allowed_stages=(Stage.DISEASE_CONTEXT,),
            optional_arguments=("disease_efo",),
            default_cost=0.05,
        )
        plan = StagePlan(
            plan_id="disease-context-plan",
            stage=Stage.DISEASE_CONTEXT,
            calls=(
                ToolCallSpec(
                    call_id="disease",
                    tool_id="opentargets",
                    operation="disease_profile",
                    action_type=ActionType.QUERY_DATABASE,
                    purpose="Resolve disease identity without claiming unmet need.",
                    arguments={"disease_efo": "MONDO_TEST"},
                    max_cost=0.05,
                ),
            ),
            max_steps=1,
            max_total_cost=0.05,
            success_confidence=0.9,
            failure_confidence=0.95,
            next_stage=Stage.TARGET_NOMINATION,
        )

        run = run_stage(
            current_state=current_state,
            contract=contract,
            response=ToolResponse(
                status=ToolStatus.SUCCEEDED,
                payload={
                    "disease_efo": "MONDO_TEST",
                    "disease": "test disease",
                    "resolved": True,
                    "loaded_targets": 25,
                    "total_associated_targets": 50,
                    "page_complete": False,
                },
                execution_mode=ExecutionMode.CACHE,
            ),
            plan=plan,
            promotion_context=context(
                subject="test disease",
                object_value="MONDO_TEST",
                candidate_id=None,
                candidate_name=None,
                modality=None,
            ),
        )

        self.assertEqual(run.promotions[0].code, "opentargets_disease_contextualized")
        self.assertEqual(run.accepted_packets[0].decision, Decision.DEFER)
        self.assertEqual(run.final_state.current_stage, Stage.DISEASE_CONTEXT)
        self.assertEqual(run.final_state.claims, ())
        self.assertEqual(
            stage_evidence(run)[0].predicate,
            "disease_context_resolved",
        )
        self.assertNotEqual(
            stage_evidence(run)[0].predicate,
            "unmet_need_defined",
        )

    def test_chembl_modality_requires_exact_identity_type_and_target(self) -> None:
        contract = ToolContract(
            tool_id="chembl",
            operation="molecule_target_mechanism_profile",
            action_type=ActionType.QUERY_DATABASE,
            description="Resolve a molecule and mechanism profile.",
            allowed_stages=(Stage.MODALITY_SELECTION,),
            required_arguments=("chembl_id", "target_id", "target_record_id"),
            default_cost=0.25,
        )
        plan = StagePlan(
            plan_id="chembl-modality-plan",
            stage=Stage.MODALITY_SELECTION,
            calls=(
                ToolCallSpec(
                    call_id="mechanism",
                    tool_id="chembl",
                    operation="molecule_target_mechanism_profile",
                    action_type=ActionType.QUERY_DATABASE,
                    purpose="Match modality to a declared target mechanism.",
                    arguments={
                        "chembl_id": "CHEMBL_TEST",
                        "target_id": "CHEMBL_TARGET",
                        "target_record_id": "ENSG_TEST1",
                    },
                    max_cost=0.25,
                ),
            ),
            max_steps=1,
            max_total_cost=0.25,
            success_confidence=0.9,
            failure_confidence=0.95,
            next_stage=Stage.CANDIDATE_GENERATION,
        )
        cases = (
            (
                "matched",
                "Small molecule",
                "CHEMBL_TARGET",
                "chembl_target_modality_continuity_promoted",
                Stage.CANDIDATE_GENERATION,
            ),
            (
                "wrong-type",
                "Protein",
                "CHEMBL_TARGET",
                "chembl_target_modality_type_mismatch",
                Stage.MODALITY_SELECTION,
            ),
            (
                "wrong-target",
                "Small molecule",
                "CHEMBL_OTHER",
                "chembl_target_mechanism_unresolved",
                Stage.MODALITY_SELECTION,
            ),
        )

        for name, molecule_type, target, expected_code, expected_stage in cases:
            with self.subTest(name=name):
                run = run_stage(
                    current_state=state(Stage.MODALITY_SELECTION),
                    contract=contract,
                    response=ToolResponse(
                        status=ToolStatus.SUCCEEDED,
                        payload={
                            "molecule": {
                                "found": True,
                                "chembl_id": "CHEMBL_TEST",
                                "name": "Test Drug",
                                "type": molecule_type,
                            },
                            "items": [
                                {
                                    "target": target,
                                    "moa": "TEST1 inhibitor",
                                    "action": "INHIBITOR",
                                }
                            ],
                            "target": {
                                "found": True,
                                "target_id": "CHEMBL_TARGET",
                                "preferred_name": "Test target",
                                "target_type": "SINGLE PROTEIN",
                                "organism": "Homo sapiens",
                                "gene_symbols": ["TEST1"],
                                "accessions": ["P00001"],
                            },
                        },
                        execution_mode=ExecutionMode.CACHE,
                    ),
                    plan=plan,
                    promotion_context=context(object_value="CHEMBL_TARGET"),
                )
                self.assertEqual(run.promotions[0].code, expected_code)
                self.assertEqual(run.final_state.current_stage, expected_stage)
                if name == "matched":
                    self.assertEqual(
                        {item.predicate for item in stage_evidence(run)},
                        {"target_identity_continuous", "modality_matches_mechanism"},
                    )
                else:
                    self.assertEqual(run.accepted_packets[0].decision, Decision.DEFER)
                    self.assertEqual(stage_evidence(run), ())

    def test_chembl_activity_volume_remains_preclinical_context_only(self) -> None:
        current_state = state(Stage.PRECLINICAL_VALIDATION, with_candidate=True)
        contract = ToolContract(
            tool_id="chembl",
            operation="target_activity_count",
            action_type=ActionType.QUERY_DATABASE,
            description="Return a target activity count.",
            allowed_stages=(Stage.PRECLINICAL_VALIDATION,),
            required_arguments=("target_id",),
            default_cost=0.1,
        )
        plan = StagePlan(
            plan_id="chembl-preclinical-context-plan",
            stage=Stage.PRECLINICAL_VALIDATION,
            calls=(
                ToolCallSpec(
                    call_id="activity",
                    tool_id="chembl",
                    operation="target_activity_count",
                    action_type=ActionType.QUERY_DATABASE,
                    purpose="Contextualize target activity volume.",
                    arguments={"target_id": "CHEMBL_TARGET"},
                    max_cost=0.1,
                ),
            ),
            max_steps=1,
            max_total_cost=0.1,
            success_confidence=0.9,
            failure_confidence=0.95,
            next_stage=Stage.CLINICAL_STRATEGY,
        )

        run = run_stage(
            current_state=current_state,
            contract=contract,
            response=ToolResponse(
                status=ToolStatus.SUCCEEDED,
                payload={"count": 42},
                execution_mode=ExecutionMode.CACHE,
            ),
            plan=plan,
            promotion_context=context(object_value="CHEMBL_TARGET"),
        )

        self.assertEqual(
            run.promotions[0].code,
            "chembl_activity_landscape_contextualized",
        )
        self.assertEqual(run.accepted_packets[0].decision, Decision.DEFER)
        self.assertEqual(run.final_state.current_stage, Stage.PRECLINICAL_VALIDATION)
        self.assertEqual(run.final_state.claims, ())
        self.assertEqual(
            stage_evidence(run)[0].predicate,
            "target_activity_landscape_available",
        )
        self.assertEqual(
            stage_evidence(run)[0].relation,
            EvidenceRelation.CONTEXTUALIZES,
        )
        self.assertNotEqual(
            stage_evidence(run)[0].predicate,
            "functional_effect_supported",
        )

    def test_chembl_identity_creates_candidate_and_advances(self) -> None:
        current_state = state(Stage.CANDIDATE_GENERATION)
        contract = ToolContract(
            tool_id="chembl",
            operation="molecule",
            action_type=ActionType.QUERY_DATABASE,
            description="Resolve a ChEMBL molecule.",
            allowed_stages=(Stage.CANDIDATE_GENERATION,),
            required_arguments=("chembl_id",),
            default_cost=0.1,
        )
        plan = StagePlan(
            plan_id="chembl-candidate-plan",
            stage=Stage.CANDIDATE_GENERATION,
            calls=(
                ToolCallSpec(
                    call_id="identity",
                    tool_id="chembl",
                    operation="molecule",
                    action_type=ActionType.QUERY_DATABASE,
                    purpose="Resolve candidate identity.",
                    arguments={"chembl_id": "CHEMBL_TEST"},
                    max_cost=0.1,
                ),
            ),
            max_steps=1,
            max_total_cost=0.1,
            success_confidence=0.9,
            failure_confidence=0.95,
            next_stage=Stage.LEAD_OPTIMIZATION,
        )

        run = run_stage(
            current_state=current_state,
            contract=contract,
            response=ToolResponse(
                status=ToolStatus.SUCCEEDED,
                payload={
                    "found": True,
                    "chembl_id": "CHEMBL_TEST",
                    "name": "Test Drug",
                    "type": "Small molecule",
                    "max_phase": 2,
                    "first_approval": None,
                },
                execution_mode=ExecutionMode.CACHE,
            ),
            plan=plan,
            promotion_context=context(
                subject="CHEMBL_TEST", object_value="CHEMBL_TARGET"
            ),
        )

        self.assertEqual(run.final_state.current_stage, Stage.LEAD_OPTIMIZATION)
        self.assertEqual(run.final_state.candidates[0].candidate_id, "CHEMBL_TEST")
        self.assertEqual(
            stage_evidence(run)[0].predicate,
            "candidate_identity_resolved",
        )

    def test_rdkit_developability_updates_candidate_and_advances(self) -> None:
        current_state = state(Stage.LEAD_OPTIMIZATION, with_candidate=True)
        contract = ToolContract(
            tool_id="molprops",
            operation="properties",
            action_type=ActionType.SCORE_CANDIDATE,
            description="Compute molecular properties.",
            allowed_stages=(Stage.LEAD_OPTIMIZATION,),
            required_arguments=("spec",),
            default_cost=0.05,
        )
        plan = StagePlan(
            plan_id="rdkit-lead-plan",
            stage=Stage.LEAD_OPTIMIZATION,
            calls=(
                ToolCallSpec(
                    call_id="properties",
                    tool_id="molprops",
                    operation="properties",
                    action_type=ActionType.SCORE_CANDIDATE,
                    purpose="Review lead developability.",
                    arguments={"spec": "CCO"},
                    max_cost=0.05,
                ),
            ),
            max_steps=1,
            max_total_cost=0.05,
            success_confidence=0.9,
            failure_confidence=0.95,
            next_stage=Stage.PRECLINICAL_VALIDATION,
        )

        run = run_stage(
            current_state=current_state,
            contract=contract,
            response=ToolResponse(
                status=ToolStatus.SUCCEEDED,
                payload={
                    "smiles": "CCO",
                    "qed": 0.7,
                    "molecular_weight": 46.1,
                    "logp": -0.2,
                    "hbd": 1,
                    "hba": 1,
                    "lipinski_violations": 0,
                    "verdict": "drug-like",
                },
                execution_mode=ExecutionMode.LOCAL,
            ),
            plan=plan,
            promotion_context=context(),
        )

        self.assertEqual(run.final_state.current_stage, Stage.PRECLINICAL_VALIDATION)
        self.assertEqual(
            run.final_state.candidates_by_id["CHEMBL_TEST"].attributes["origin"],
            "test",
        )
        self.assertEqual(
            run.final_state.candidates_by_id["CHEMBL_TEST"].attributes["molprops"][
                "verdict"
            ],
            "drug-like",
        )

    def test_rdkit_cannot_create_a_missing_lead_candidate(self) -> None:
        current_state = state(Stage.LEAD_OPTIMIZATION)
        contract = ToolContract(
            tool_id="molprops",
            operation="properties",
            action_type=ActionType.SCORE_CANDIDATE,
            description="Compute molecular properties.",
            allowed_stages=(Stage.LEAD_OPTIMIZATION,),
            required_arguments=("spec",),
            default_cost=0.05,
        )
        plan = StagePlan(
            plan_id="rdkit-missing-candidate-plan",
            stage=Stage.LEAD_OPTIMIZATION,
            calls=(
                ToolCallSpec(
                    call_id="properties",
                    tool_id="molprops",
                    operation="properties",
                    action_type=ActionType.SCORE_CANDIDATE,
                    purpose="Review a declared lead.",
                    arguments={"spec": "CCO"},
                    max_cost=0.05,
                ),
            ),
            max_steps=1,
            max_total_cost=0.05,
            success_confidence=0.9,
            failure_confidence=0.95,
            next_stage=Stage.PRECLINICAL_VALIDATION,
        )

        run = run_stage(
            current_state=current_state,
            contract=contract,
            response=ToolResponse(
                status=ToolStatus.SUCCEEDED,
                payload={
                    "smiles": "CCO",
                    "qed": 0.7,
                    "molecular_weight": 46.1,
                    "logp": -0.2,
                    "hbd": 1,
                    "hba": 1,
                    "lipinski_violations": 0,
                    "verdict": "drug-like",
                },
                execution_mode=ExecutionMode.LOCAL,
            ),
            plan=plan,
            promotion_context=context(),
        )

        self.assertEqual(run.promotions[0].code, "candidate_not_in_state")
        self.assertEqual(run.accepted_packets[0].decision, Decision.DEFER)
        self.assertEqual(run.final_state.candidates, ())
        self.assertEqual(stage_evidence(run), ())

    def test_boltz_request_payload_pair_mismatch_is_not_promoted(self) -> None:
        current_state = state(Stage.CANDIDATE_GENERATION)
        contract = ToolContract(
            tool_id="boltz2",
            operation="predict_binding",
            action_type=ActionType.RUN_SFM,
            description="Return a structured binding prediction.",
            allowed_stages=(Stage.CANDIDATE_GENERATION,),
            required_arguments=("spec",),
            default_cost=1.0,
        )
        plan = StagePlan(
            plan_id="boltz-pair-mismatch-plan",
            stage=Stage.CANDIDATE_GENERATION,
            calls=(
                ToolCallSpec(
                    call_id="binding",
                    tool_id="boltz2",
                    operation="predict_binding",
                    action_type=ActionType.RUN_SFM,
                    purpose="Use a structure prediction as a soft prefilter.",
                    arguments={"spec": "TEST1|CCO"},
                    max_cost=1.0,
                ),
            ),
            max_steps=1,
            max_total_cost=1.0,
            success_confidence=0.8,
            failure_confidence=0.95,
            next_stage=Stage.LEAD_OPTIMIZATION,
        )

        run = run_stage(
            current_state=current_state,
            contract=contract,
            response=ToolResponse(
                status=ToolStatus.SUCCEEDED,
                payload={
                    "status": "predicted",
                    "target": "TEST1",
                    "ligand": "CCC",
                    "affinity": 0.7,
                    "affinity_units": "service-defined",
                    "confidence": 0.8,
                },
                execution_mode=ExecutionMode.LIVE,
            ),
            plan=plan,
            promotion_context=context(
                subject="CHEMBL_TEST",
                object_value="TEST1",
                confidence=0.8,
            ),
        )

        self.assertEqual(run.promotions[0].code, "boltz_payload_invalid")
        self.assertEqual(run.accepted_packets[0].decision, Decision.DEFER)
        self.assertEqual(stage_evidence(run), ())

    def test_ctgov_distinguishes_benefit_mixed_and_non_significant(self) -> None:
        contract = ToolContract(
            tool_id="ctgov",
            operation="search_trials",
            action_type=ActionType.QUERY_DATABASE,
            description="Search clinical trial results.",
            allowed_stages=(Stage.CLINICAL_STRATEGY,),
            required_arguments=("drug", "condition"),
            default_cost=0.1,
        )
        plan = StagePlan(
            plan_id="ctgov-clinical-plan",
            stage=Stage.CLINICAL_STRATEGY,
            calls=(
                ToolCallSpec(
                    call_id="trials",
                    tool_id="ctgov",
                    operation="search_trials",
                    action_type=ActionType.QUERY_DATABASE,
                    purpose="Assess clinical evidence.",
                    arguments={"drug": "Test Drug", "condition": "test disease"},
                    max_cost=0.1,
                ),
            ),
            max_steps=1,
            max_total_cost=0.1,
            success_confidence=0.9,
            failure_confidence=0.95,
            next_stage=Stage.REGULATORY_POSTMARKET,
        )
        cases = (
            (
                "benefit",
                [
                    {
                        "nct": "NCT00000001",
                        "interventions": "Test Drug",
                        "conditions": "test disease",
                        "significant": True,
                        "direction": "benefit",
                        "has_results": True,
                        "mixed_within": False,
                    }
                ],
                ProgramStatus.DEFERRED,
                ClaimDisposition.SUPPORTED,
                Stage.CLINICAL_STRATEGY,
            ),
            (
                "mixed",
                [
                    {
                        "nct": "NCT00000001",
                        "interventions": "Test Drug",
                        "conditions": "test disease",
                        "significant": True,
                        "direction": "benefit",
                        "has_results": True,
                        "mixed_within": False,
                    },
                    {
                        "nct": "NCT00000002",
                        "interventions": "Test Drug",
                        "conditions": "test disease",
                        "significant": True,
                        "direction": "harm",
                        "has_results": True,
                        "mixed_within": False,
                    },
                ],
                ProgramStatus.DEFERRED,
                ClaimDisposition.CONTESTED,
                Stage.CLINICAL_STRATEGY,
            ),
            (
                "non-significant",
                [
                    {
                        "nct": "NCT00000003",
                        "interventions": "Test Drug",
                        "conditions": "test disease",
                        "significant": False,
                        "direction": "harm",
                        "has_results": True,
                        "mixed_within": False,
                    }
                ],
                ProgramStatus.DEFERRED,
                None,
                Stage.CLINICAL_STRATEGY,
            ),
        )

        for name, items, expected_status, expected_disposition, expected_stage in cases:
            with self.subTest(name=name):
                run = run_stage(
                    current_state=state(
                        Stage.CLINICAL_STRATEGY,
                        with_candidate=True,
                    ),
                    contract=contract,
                    response=ToolResponse(
                        status=ToolStatus.SUCCEEDED,
                        payload={"items": items},
                        execution_mode=ExecutionMode.CACHE,
                    ),
                    plan=plan,
                    promotion_context=context(
                        subject="Test Drug",
                        object_value="test disease",
                    ),
                )
                self.assertEqual(run.final_state.status, expected_status)
                self.assertEqual(run.final_state.current_stage, expected_stage)
                if expected_disposition is None:
                    self.assertEqual(run.final_state.claims, ())
                    self.assertEqual(
                        stage_evidence(run)[0].relation,
                        EvidenceRelation.CONTEXTUALIZES,
                    )
                else:
                    self.assertEqual(
                        run.final_state.claims[0].disposition,
                        expected_disposition,
                    )

    def test_ctgov_condition_mismatch_is_not_promoted(self) -> None:
        current_state = state(Stage.CLINICAL_STRATEGY, with_candidate=True)
        contract = ToolContract(
            tool_id="ctgov",
            operation="search_trials",
            action_type=ActionType.QUERY_DATABASE,
            description="Search clinical trial results.",
            allowed_stages=(Stage.CLINICAL_STRATEGY,),
            required_arguments=("drug", "condition"),
            default_cost=0.1,
        )
        plan = StagePlan(
            plan_id="ctgov-context-mismatch-plan",
            stage=Stage.CLINICAL_STRATEGY,
            calls=(
                ToolCallSpec(
                    call_id="trials",
                    tool_id="ctgov",
                    operation="search_trials",
                    action_type=ActionType.QUERY_DATABASE,
                    purpose="Assess condition-specific clinical evidence.",
                    arguments={"drug": "Test Drug", "condition": "other disease"},
                    max_cost=0.1,
                ),
            ),
            max_steps=1,
            max_total_cost=0.1,
            success_confidence=0.9,
            failure_confidence=0.95,
            next_stage=Stage.REGULATORY_POSTMARKET,
        )

        run = run_stage(
            current_state=current_state,
            contract=contract,
            response=ToolResponse(
                status=ToolStatus.SUCCEEDED,
                payload={
                    "items": [
                        {
                            "nct": "NCT00000004",
                            "interventions": "Test Drug",
                            "conditions": "other disease",
                            "significant": True,
                            "direction": "benefit",
                            "has_results": True,
                            "mixed_within": False,
                        }
                    ]
                },
                execution_mode=ExecutionMode.CACHE,
            ),
            plan=plan,
            promotion_context=context(
                subject="Test Drug",
                object_value="test disease",
            ),
        )

        self.assertEqual(run.promotions[0].code, "ctgov_condition_mismatch")
        self.assertEqual(run.accepted_packets[0].decision, Decision.DEFER)
        self.assertEqual(stage_evidence(run), ())

    def test_ctgov_search_identity_match_is_contextual_and_mismatch_rejects(
        self,
    ) -> None:
        contract = ToolContract(
            tool_id="ctgov",
            operation="search_trials",
            action_type=ActionType.QUERY_DATABASE,
            description="Search clinical trial results.",
            allowed_stages=(Stage.CLINICAL_STRATEGY,),
            required_arguments=("drug", "condition"),
            default_cost=0.1,
        )
        plan = StagePlan(
            plan_id="ctgov-source-identity-plan",
            stage=Stage.CLINICAL_STRATEGY,
            calls=(
                ToolCallSpec(
                    call_id="trials",
                    tool_id="ctgov",
                    operation="search_trials",
                    action_type=ActionType.QUERY_DATABASE,
                    purpose="Resolve source-linked clinical intervention identity.",
                    arguments={"drug": "Test Drug", "condition": "test disease"},
                    max_cost=0.1,
                ),
            ),
            max_steps=1,
            max_total_cost=0.1,
            success_confidence=0.9,
            failure_confidence=0.95,
            next_stage=Stage.REGULATORY_POSTMARKET,
        )

        def source_run(*, program_id: str, source_intervention: str):
            return run_stage(
                current_state=state(
                    Stage.CLINICAL_STRATEGY,
                    with_candidate=True,
                    program_id=program_id,
                ),
                contract=contract,
                response=ToolResponse(
                    status=ToolStatus.SUCCEEDED,
                    payload={
                        "items": [
                            {
                                "nct": "NCT00000005",
                                "interventions": source_intervention,
                                "conditions": "test disease",
                                "significant": True,
                                "direction": "benefit",
                                "has_results": True,
                                "mixed_within": False,
                            }
                        ]
                    },
                    execution_mode=ExecutionMode.CACHE,
                ),
                plan=plan,
                promotion_context=context(
                    subject="Test Drug",
                    object_value="test disease",
                ),
            )

        success_run = source_run(
            program_id="ctgov-source-identity-success-program",
            source_intervention="Test Drug",
        )
        failure_run = source_run(
            program_id="ctgov-source-identity-failure-program",
            source_intervention="Other Drug",
        )
        self.assertEqual(success_run.accepted_packets[0].decision, Decision.DEFER)
        self.assertEqual(
            success_run.final_state.current_stage, Stage.CLINICAL_STRATEGY
        )
        self.assertEqual(
            success_run.promotions[0].code,
            "ctgov_benefit_evidence_promoted",
        )
        self.assertEqual(
            failure_run.promotions[0].code,
            "ctgov_source_identity_mismatch",
        )
        self.assertEqual(failure_run.accepted_packets[0].decision, Decision.DEFER)
        self.assertEqual(stage_evidence(failure_run), ())

    def test_ema_withdrawal_kills_but_negated_authorization_defers(self) -> None:
        contract = ToolContract(
            tool_id="ema",
            operation="lookup",
            action_type=ActionType.QUERY_DATABASE,
            description="Read EMA medicine status.",
            allowed_stages=(Stage.REGULATORY_POSTMARKET,),
            required_arguments=("query",),
            default_cost=0.1,
        )
        plan = StagePlan(
            plan_id="ema-regulatory-plan",
            stage=Stage.REGULATORY_POSTMARKET,
            calls=(
                ToolCallSpec(
                    call_id="status",
                    tool_id="ema",
                    operation="lookup",
                    action_type=ActionType.QUERY_DATABASE,
                    purpose="Assess regulatory status.",
                    arguments={"query": "Test Drug"},
                    max_cost=0.1,
                ),
            ),
            max_steps=1,
            max_total_cost=0.1,
            success_confidence=0.9,
            failure_confidence=0.95,
            next_stage=None,
        )
        cases = (
            ("Withdrawn", ProgramStatus.TERMINATED, Decision.KILL),
            ("Not authorised", ProgramStatus.DEFERRED, Decision.DEFER),
        )

        for medicine_status, expected_status, expected_decision in cases:
            with self.subTest(medicine_status=medicine_status):
                run = run_stage(
                    current_state=state(
                        Stage.REGULATORY_POSTMARKET,
                        with_candidate=True,
                        clinical_intervention_id="INTERVENTION_TEST",
                    ),
                    contract=contract,
                    response=ToolResponse(
                        status=ToolStatus.SUCCEEDED,
                        payload={
                            "found": True,
                            "asset": "Test Drug",
                            "status": medicine_status,
                        },
                        execution_mode=ExecutionMode.CACHE,
                    ),
                    plan=plan,
                    promotion_context=context(subject="Test Drug"),
                )
                self.assertEqual(run.final_state.status, expected_status)
                self.assertEqual(run.accepted_packets[0].decision, expected_decision)
                self.assertEqual(
                    run.final_state.interventions[0].intervention_id,
                    "INTERVENTION_TEST",
                )

    def test_ema_query_subject_mismatch_cannot_kill_program(self) -> None:
        current_state = state(Stage.REGULATORY_POSTMARKET, with_candidate=True)
        contract = ToolContract(
            tool_id="ema",
            operation="lookup",
            action_type=ActionType.QUERY_DATABASE,
            description="Read EMA medicine status.",
            allowed_stages=(Stage.REGULATORY_POSTMARKET,),
            required_arguments=("query",),
            default_cost=0.1,
        )
        plan = StagePlan(
            plan_id="ema-context-mismatch-plan",
            stage=Stage.REGULATORY_POSTMARKET,
            calls=(
                ToolCallSpec(
                    call_id="status",
                    tool_id="ema",
                    operation="lookup",
                    action_type=ActionType.QUERY_DATABASE,
                    purpose="Assess regulatory status.",
                    arguments={"query": "Other Drug"},
                    max_cost=0.1,
                ),
            ),
            max_steps=1,
            max_total_cost=0.1,
            success_confidence=0.9,
            failure_confidence=0.95,
        )

        run = run_stage(
            current_state=current_state,
            contract=contract,
            response=ToolResponse(
                status=ToolStatus.SUCCEEDED,
                payload={
                    "found": True,
                    "asset": "Other Drug",
                    "status": "Withdrawn",
                },
                execution_mode=ExecutionMode.CACHE,
            ),
            plan=plan,
            promotion_context=context(subject="Test Drug"),
        )

        self.assertEqual(run.promotions[0].code, "ema_asset_context_mismatch")
        self.assertEqual(run.accepted_packets[0].decision, Decision.DEFER)
        self.assertEqual(run.final_state.status, ProgramStatus.DEFERRED)
        self.assertEqual(stage_evidence(run), ())

    def test_ema_source_identity_mismatch_cannot_kill_program(self) -> None:
        current_state = state(Stage.REGULATORY_POSTMARKET, with_candidate=True)
        contract = ToolContract(
            tool_id="ema",
            operation="lookup",
            action_type=ActionType.QUERY_DATABASE,
            description="Read EMA medicine status.",
            allowed_stages=(Stage.REGULATORY_POSTMARKET,),
            required_arguments=("query",),
            default_cost=0.1,
        )
        plan = StagePlan(
            plan_id="ema-source-identity-mismatch-plan",
            stage=Stage.REGULATORY_POSTMARKET,
            calls=(
                ToolCallSpec(
                    call_id="status",
                    tool_id="ema",
                    operation="lookup",
                    action_type=ActionType.QUERY_DATABASE,
                    purpose="Assess source-linked regulatory status.",
                    arguments={"query": "Test Drug"},
                    max_cost=0.1,
                ),
            ),
            max_steps=1,
            max_total_cost=0.1,
            success_confidence=0.9,
            failure_confidence=0.95,
        )

        run = run_stage(
            current_state=current_state,
            contract=contract,
            response=ToolResponse(
                status=ToolStatus.SUCCEEDED,
                payload={
                    "found": True,
                    "asset": "Other Drug",
                    "status": "Withdrawn",
                },
                execution_mode=ExecutionMode.CACHE,
            ),
            plan=plan,
            promotion_context=context(subject="Test Drug"),
        )

        self.assertEqual(run.promotions[0].code, "ema_source_identity_mismatch")
        self.assertEqual(run.accepted_packets[0].decision, Decision.DEFER)
        self.assertEqual(run.final_state.status, ProgramStatus.DEFERRED)
        self.assertEqual(stage_evidence(run), ())


if __name__ == "__main__":
    unittest.main()
