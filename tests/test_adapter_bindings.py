from __future__ import annotations

import json
import unittest
from datetime import date, datetime, timedelta, timezone

from adapters.ctgov_adapter import CtgovAdapter
from adapters.execution_registry import register_existing_adapters
from adapters.opentargets_adapter import OpenTargetsAdapter
from agentic_drug_discovery import (
    ActionType,
    BoundedPlanner,
    BoundedProgramRunner,
    BoundedStageRunner,
    BudgetState,
    Decision,
    DiseaseRecord,
    EvidenceEvent,
    EvidenceRelation,
    ExecutionMode,
    ProgramRunStatus,
    ProgramStatus,
    ProgramStep,
    PromotionBinding,
    PromotionContext,
    ProgramState,
    Stage,
    StagePlan,
    SourceReference,
    ToolCallSpec,
    ToolRegistry,
    ToolRequest,
    ToolStatus,
    build_default_semantic_mapper_registry,
    replay_program_run,
)


REQUEST_AT = datetime(2025, 1, 1, tzinfo=timezone.utc)
COMPLETED_AT = REQUEST_AT + timedelta(minutes=1)


def make_state(*, stage: Stage = Stage.TARGET_NOMINATION) -> ProgramState:
    evidence = ()
    diseases = ()
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
                locator="fixture://tests/adapter-bindings/disease",
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
    return ProgramState(
        program_id="adapter-binding-program",
        disease="test disease",
        therapeutic_hypothesis="Adapter availability must remain explicit.",
        as_of_date=date(2025, 1, 1),
        current_stage=stage,
        budget=BudgetState(limit=2.0),
        evidence=evidence,
        diseases=diseases,
    )


class TickClock:
    def __init__(self) -> None:
        self.current = REQUEST_AT

    def __call__(self) -> datetime:
        self.current += timedelta(seconds=1)
        return self.current


def program_step(
    *,
    plan_id: str,
    stage: Stage,
    next_stage: Stage,
    call_id: str,
    tool_id: str,
    operation: str,
    action_type: ActionType,
    purpose: str,
    arguments: dict,
    max_cost: float,
    context: PromotionContext,
) -> ProgramStep:
    return ProgramStep(
        stage_plan=StagePlan(
            plan_id=plan_id,
            stage=stage,
            calls=(
                ToolCallSpec(
                    call_id=call_id,
                    tool_id=tool_id,
                    operation=operation,
                    action_type=action_type,
                    purpose=purpose,
                    arguments=arguments,
                    max_cost=max_cost,
                ),
            ),
            max_steps=1,
            max_total_cost=max_cost,
            success_confidence=0.9,
            failure_confidence=0.95,
            next_stage=next_stage,
        ),
        promotion_bindings=(PromotionBinding(call_id=call_id, context=context),),
    )


class AdapterBindingTests(unittest.TestCase):
    def test_disease_profile_is_contextual_and_cannot_claim_unmet_need(self) -> None:
        class FakeOpenTargets:
            def disease_profile(self, disease_efo=None):
                return {
                    "disease_efo": disease_efo or "MONDO_TEST",
                    "disease": "test disease",
                    "resolved": True,
                    "evidence_status": "resolved",
                    "loaded_targets": 50,
                    "total_associated_targets": 75,
                    "page_complete": False,
                }

        state = make_state(stage=Stage.DISEASE_CONTEXT)
        registry = register_existing_adapters(
            ToolRegistry(clock=lambda: COMPLETED_AT),
            opentargets=FakeOpenTargets(),
        )
        plan = StagePlan(
            plan_id="adapter-disease-context-plan",
            stage=Stage.DISEASE_CONTEXT,
            calls=(
                ToolCallSpec(
                    call_id="disease",
                    tool_id="opentargets",
                    operation="disease_profile",
                    action_type=ActionType.QUERY_DATABASE,
                    purpose="Resolve disease identity without inferring unmet need.",
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
        runner = BoundedStageRunner(
            tool_registry=registry,
            mapper_registry=build_default_semantic_mapper_registry(
                target_association_minimum_score=0.5
            ),
            planner=BoundedPlanner(clock=lambda: REQUEST_AT),
            clock=lambda: COMPLETED_AT,
        )

        run = runner.run_stage(
            run_id="adapter-disease-context-run",
            state=state,
            stage_plan=plan,
            promotion_contexts={
                "disease": PromotionContext(
                    observed_at=date(2024, 12, 1),
                    available_at=date(2024, 12, 2),
                    subject="test disease",
                    object_value="MONDO_TEST",
                    confidence=0.9,
                )
            },
        )

        self.assertEqual(run.accepted_packets[0].decision, Decision.DEFER)
        self.assertFalse(run.recovered_to_defer)
        self.assertEqual(run.final_state.status, ProgramStatus.DEFERRED)
        self.assertEqual(
            run.final_state.evidence[0].predicate,
            "disease_context_resolved",
        )
        self.assertEqual(
            run.final_state.evidence[0].relation,
            EvidenceRelation.CONTEXTUALIZES,
        )
        self.assertNotIn(
            "unmet_need_defined",
            {item.predicate for item in run.final_state.evidence},
        )
        self.assertEqual(run.final_state.claims, ())

    def test_opentargets_initialized_disease_mismatch_is_explicit(self) -> None:
        adapter = OpenTargetsAdapter.__new__(OpenTargetsAdapter)
        adapter.efo = "MONDO_TEST"
        adapter.disease_name = "test disease"
        adapter.loaded = True
        adapter.loaded_count = 10
        adapter.total_count = 10
        adapter.map = {}
        state = make_state(stage=Stage.DISEASE_CONTEXT)
        registry = register_existing_adapters(
            ToolRegistry(clock=lambda: COMPLETED_AT),
            opentargets=adapter,
        )
        request = ToolRequest(
            request_id="ot-disease-mismatch",
            program_id=state.program_id,
            expected_state_version=state.version,
            stage=state.current_stage,
            tool_id="opentargets",
            operation="disease_profile",
            action_type=ActionType.QUERY_DATABASE,
            purpose="Resolve the requested disease context.",
            arguments={"disease_efo": "MONDO_OTHER"},
            max_cost=0.05,
            created_at=REQUEST_AT,
        )

        outcome = registry.execute(state, request)

        self.assertEqual(outcome.status, ToolStatus.FAILED)
        self.assertEqual(outcome.error_code, "opentargets_disease_context_mismatch")
        self.assertEqual(outcome.payload["initialized_disease_efo"], "MONDO_TEST")

    def test_opentargets_binding_drives_typed_stage_transition(self) -> None:
        class FakeOpenTargets:
            def target_disease_association(self, symbol, disease_efo=None):
                return {
                    "target": symbol,
                    "target_id": "ENSG_TEST1",
                    "disease": "test disease",
                    "disease_efo": disease_efo,
                    "organism": "Homo sapiens",
                    "found": True,
                    "score": 0.91,
                    "rank": 1,
                    "datatypes": {"genetic_association": 0.88},
                }

        state = make_state()
        registry = register_existing_adapters(
            ToolRegistry(clock=lambda: COMPLETED_AT),
            opentargets=FakeOpenTargets(),
        )
        plan = StagePlan(
            plan_id="adapter-target-plan",
            stage=Stage.TARGET_NOMINATION,
            calls=(
                ToolCallSpec(
                    call_id="association",
                    tool_id="opentargets",
                    operation="target_disease_association",
                    action_type=ActionType.QUERY_DATABASE,
                    purpose="Retrieve target-disease association evidence.",
                    arguments={"symbol": "TEST1", "disease_efo": "MONDO_TEST"},
                    max_cost=0.1,
                ),
            ),
            max_steps=1,
            max_total_cost=0.1,
            success_confidence=0.9,
            failure_confidence=0.95,
            next_stage=Stage.MODALITY_SELECTION,
        )
        runner = BoundedStageRunner(
            tool_registry=registry,
            mapper_registry=build_default_semantic_mapper_registry(
                target_association_minimum_score=0.5
            ),
            planner=BoundedPlanner(clock=lambda: REQUEST_AT),
            clock=lambda: COMPLETED_AT,
        )

        run = runner.run_stage(
            run_id="adapter-target-run",
            state=state,
            stage_plan=plan,
            promotion_contexts={
                "association": PromotionContext(
                    observed_at=date(2024, 12, 1),
                    available_at=date(2024, 12, 2),
                    subject="TEST1",
                    object_value="test disease",
                    confidence=0.9,
                )
            },
        )

        self.assertEqual(run.final_state.current_stage, Stage.MODALITY_SELECTION)
        self.assertEqual(run.final_state.status, ProgramStatus.ACTIVE)
        self.assertEqual(
            run.outcomes[0].contract_id, "opentargets.target_disease_association@1"
        )
        self.assertEqual(run.promotions[0].code, "opentargets_association_promoted")

    def test_five_stage_real_registry_chain_defers_at_functional_evidence_gate(
        self,
    ) -> None:
        class FakeOpenTargets:
            def target_disease_association(self, symbol, disease_efo=None):
                return {
                    "target": symbol,
                    "target_id": "ENSG_TEST1",
                    "disease": "test disease",
                    "disease_efo": disease_efo,
                    "organism": "Homo sapiens",
                    "found": True,
                    "score": 0.91,
                    "rank": 1,
                    "datatypes": {"genetic_association": 0.88},
                }

        class FakeChembl:
            def molecule(self, chembl_id=None, name=None):
                return {
                    "found": True,
                    "chembl_id": chembl_id or "CHEMBL_TEST",
                    "name": "Test Drug",
                    "type": "Small molecule",
                    "max_phase": 2,
                    "first_approval": None,
                }

            def mechanism(self, chembl_id):
                return [
                    {
                        "moa": "TEST1 inhibitor",
                        "target": "CHEMBL_TARGET",
                        "action": "INHIBITOR",
                    }
                ]

            def target(self, target_id):
                return {
                    "found": True,
                    "target_id": target_id,
                    "preferred_name": "Test target",
                    "target_type": "SINGLE PROTEIN",
                    "organism": "Homo sapiens",
                    "gene_symbols": ["TEST1"],
                    "accessions": ["P00001"],
                }

            def target_activity_count(self, target_id):
                return 42

        class FakeMolProps:
            ok = True

            def compute(self, spec):
                return {
                    "smiles": spec,
                    "qed": 0.7,
                    "molecular_weight": 46.1,
                    "logp": -0.2,
                    "hbd": 1,
                    "hba": 1,
                    "lipinski_violations": 0,
                    "verdict": "drug-like",
                }

        clock = TickClock()
        registry = register_existing_adapters(
            ToolRegistry(clock=clock),
            opentargets=FakeOpenTargets(),
            chembl=FakeChembl(),
            molprops=FakeMolProps(),
        )
        candidate_context = PromotionContext(
            observed_at=date(2024, 12, 1),
            available_at=date(2024, 12, 2),
            subject="Test Drug",
            object_value="CHEMBL_TARGET",
            confidence=0.9,
            candidate_id="CHEMBL_TEST",
            candidate_name="Test Drug",
            modality="small molecule",
        )
        steps = (
            program_step(
                plan_id="e2e-target",
                stage=Stage.TARGET_NOMINATION,
                next_stage=Stage.MODALITY_SELECTION,
                call_id="association",
                tool_id="opentargets",
                operation="target_disease_association",
                action_type=ActionType.QUERY_DATABASE,
                purpose="Support the target-disease relationship.",
                arguments={"symbol": "TEST1", "disease_efo": "MONDO_TEST"},
                max_cost=0.1,
                context=PromotionContext(
                    observed_at=date(2024, 12, 1),
                    available_at=date(2024, 12, 2),
                    subject="TEST1",
                    object_value="test disease",
                    confidence=0.9,
                ),
            ),
            program_step(
                plan_id="e2e-modality",
                stage=Stage.MODALITY_SELECTION,
                next_stage=Stage.CANDIDATE_GENERATION,
                call_id="mechanism",
                tool_id="chembl",
                operation="molecule_target_mechanism_profile",
                action_type=ActionType.QUERY_DATABASE,
                purpose="Match molecule modality to the declared target mechanism.",
                arguments={
                    "chembl_id": "CHEMBL_TEST",
                    "target_id": "CHEMBL_TARGET",
                    "target_record_id": "ENSG_TEST1",
                },
                max_cost=0.25,
                context=candidate_context,
            ),
            program_step(
                plan_id="e2e-candidate",
                stage=Stage.CANDIDATE_GENERATION,
                next_stage=Stage.LEAD_OPTIMIZATION,
                call_id="identity",
                tool_id="chembl",
                operation="molecule",
                action_type=ActionType.QUERY_DATABASE,
                purpose="Resolve candidate identity.",
                arguments={"chembl_id": "CHEMBL_TEST"},
                max_cost=0.1,
                context=candidate_context,
            ),
            program_step(
                plan_id="e2e-lead",
                stage=Stage.LEAD_OPTIMIZATION,
                next_stage=Stage.PRECLINICAL_VALIDATION,
                call_id="properties",
                tool_id="molprops",
                operation="properties",
                action_type=ActionType.SCORE_CANDIDATE,
                purpose="Review bounded molecular developability signals.",
                arguments={"spec": "CCO"},
                max_cost=0.05,
                context=candidate_context,
            ),
            program_step(
                plan_id="e2e-preclinical",
                stage=Stage.PRECLINICAL_VALIDATION,
                next_stage=Stage.CLINICAL_STRATEGY,
                call_id="activity-landscape",
                tool_id="chembl",
                operation="target_activity_count",
                action_type=ActionType.QUERY_DATABASE,
                purpose="Contextualize target activity volume without claiming efficacy.",
                arguments={"target_id": "CHEMBL_TARGET"},
                max_cost=0.1,
                context=candidate_context,
            ),
        )
        runner = BoundedProgramRunner(
            stage_runner=BoundedStageRunner(
                tool_registry=registry,
                mapper_registry=build_default_semantic_mapper_registry(
                    target_association_minimum_score=0.5
                ),
                planner=BoundedPlanner(clock=clock),
                clock=clock,
            )
        )

        run = runner.run_program(
            run_id="five-stage-adapter-chain",
            state=make_state(),
            steps=steps,
        )

        self.assertEqual(run.status, ProgramRunStatus.PAUSED)
        self.assertEqual(run.code, "program_paused_on_defer")
        self.assertEqual(run.final_state.current_stage, Stage.PRECLINICAL_VALIDATION)
        self.assertEqual(run.final_state.status, ProgramStatus.DEFERRED)
        self.assertEqual(run.final_state.version, 5)
        self.assertEqual(len(run.accepted_packets), 5)
        self.assertEqual(len(run.execution_ledger.outcomes), 5)
        self.assertAlmostEqual(run.execution_ledger.total_cost, 0.6)
        self.assertEqual(
            run.stage_runs[-1].promotions[0].code,
            "chembl_activity_landscape_contextualized",
        )
        self.assertEqual(
            run.stage_runs[-1].outcomes[0].contract_id,
            "chembl.target_activity_count@1",
        )
        predicates = {item.predicate for item in run.final_state.evidence}
        self.assertIn("modality_matches_mechanism", predicates)
        self.assertIn("target_activity_landscape_available", predicates)
        self.assertNotIn("functional_effect_supported", predicates)
        self.assertNotIn(
            "functional_effect_supported",
            {item.predicate for item in run.final_state.claims},
        )
        self.assertEqual(
            run.final_state.evidence[-1].relation,
            EvidenceRelation.CONTEXTUALIZES,
        )
        self.assertEqual(replay_program_run(run).final_state, run.final_state)

    def test_ctgov_plausibility_adapter_runs_through_registry(self) -> None:
        state = make_state(stage=Stage.CLINICAL_STRATEGY)
        adapter = CtgovAdapter.__new__(CtgovAdapter)
        registry = register_existing_adapters(
            ToolRegistry(clock=lambda: COMPLETED_AT),
            ctgov=adapter,
        )
        request = ToolRequest(
            request_id="ctgov-plausibility-1",
            program_id=state.program_id,
            expected_state_version=state.version,
            stage=state.current_stage,
            tool_id="ctgov",
            operation="check_value_plausibility",
            action_type=ActionType.RUN_VERIFIER,
            purpose="Check a declared numeric validity range.",
            arguments={
                "records": [{"hazard_ratio": 12.0}],
                "rule": {
                    "field": "hazard_ratio",
                    "numeric_min": 0.0,
                    "numeric_max": 10.0,
                },
            },
            max_cost=0.0,
            created_at=REQUEST_AT,
        )

        outcome = registry.execute(state, request)

        self.assertEqual(outcome.status, ToolStatus.SUCCEEDED)
        self.assertTrue(outcome.payload["items"][0]["out_of_range"])
        self.assertEqual(outcome.execution_mode, ExecutionMode.LOCAL)

    def test_bindings_preserve_unavailable_adapter_states(self) -> None:
        class FakeOpenTargets:
            def target_disease_association(self, symbol, disease_efo=None):
                return {
                    "target": symbol,
                    "found": False,
                    "evidence_status": "dataset_unavailable",
                }

        class FakeChembl:
            def molecule(self, chembl_id=None, name=None):
                return {"found": False}

            def mechanism(self, chembl_id):
                return []

            def target_activity_count(self, target_id):
                return None

        class FakeBoltz:
            endpoint = None

            def predict_binding(self, spec):
                return "boltz2 UNAVAILABLE: configured GPU endpoint required"

        class FakeMolProps:
            ok = False

            def compute(self, spec):
                return None

        registry = register_existing_adapters(
            ToolRegistry(clock=lambda: COMPLETED_AT),
            opentargets=FakeOpenTargets(),
            chembl=FakeChembl(),
            boltz=FakeBoltz(),
            molprops=FakeMolProps(),
        )
        target_state = make_state()
        candidate_state = make_state(stage=Stage.CANDIDATE_GENERATION)
        cases = (
            (
                target_state,
                ToolRequest(
                    request_id="ot-unavailable",
                    program_id=target_state.program_id,
                    expected_state_version=target_state.version,
                    stage=target_state.current_stage,
                    tool_id="opentargets",
                    operation="target_disease_association",
                    action_type=ActionType.QUERY_DATABASE,
                    purpose="Query Open Targets.",
                    arguments={"symbol": "TEST1", "disease_efo": "MONDO_TEST"},
                    max_cost=0.1,
                    created_at=REQUEST_AT,
                ),
                "opentargets_dataset_unavailable",
            ),
            (
                target_state,
                ToolRequest(
                    request_id="chembl-unavailable",
                    program_id=target_state.program_id,
                    expected_state_version=target_state.version,
                    stage=target_state.current_stage,
                    tool_id="chembl",
                    operation="molecule",
                    action_type=ActionType.QUERY_DATABASE,
                    purpose="Query ChEMBL.",
                    arguments={"name": "missing"},
                    max_cost=0.1,
                    created_at=REQUEST_AT,
                ),
                "chembl_molecule_unresolved",
            ),
            (
                candidate_state,
                ToolRequest(
                    request_id="boltz-unavailable",
                    program_id=candidate_state.program_id,
                    expected_state_version=candidate_state.version,
                    stage=candidate_state.current_stage,
                    tool_id="boltz2",
                    operation="predict_binding",
                    action_type=ActionType.RUN_SFM,
                    purpose="Run a binding prediction.",
                    arguments={"spec": "TEST1|CCO"},
                    max_cost=1.0,
                    created_at=REQUEST_AT,
                ),
                "boltz_prediction_unavailable",
            ),
            (
                candidate_state,
                ToolRequest(
                    request_id="rdkit-unavailable",
                    program_id=candidate_state.program_id,
                    expected_state_version=candidate_state.version,
                    stage=candidate_state.current_stage,
                    tool_id="molprops",
                    operation="properties",
                    action_type=ActionType.SCORE_CANDIDATE,
                    purpose="Compute molecular properties.",
                    arguments={"spec": "CCO"},
                    max_cost=0.05,
                    created_at=REQUEST_AT,
                ),
                "rdkit_unavailable",
            ),
        )

        for state, request, error_code in cases:
            with self.subTest(request_id=request.request_id):
                outcome = registry.execute(state, request)
                self.assertEqual(outcome.status, ToolStatus.UNAVAILABLE)
                self.assertEqual(outcome.error_code, error_code)

    def test_boltz_endpoint_error_details_are_redacted(self) -> None:
        class FakeBoltz:
            endpoint = "https://private.example.invalid/internal-detail"

            def predict_binding(self, spec):
                return f"boltz2: endpoint error ({self.endpoint})"

        state = make_state(stage=Stage.CANDIDATE_GENERATION)
        registry = register_existing_adapters(
            ToolRegistry(clock=lambda: COMPLETED_AT),
            boltz=FakeBoltz(),
        )
        request = ToolRequest(
            request_id="boltz-endpoint-error",
            program_id=state.program_id,
            expected_state_version=state.version,
            stage=state.current_stage,
            tool_id="boltz2",
            operation="predict_binding",
            action_type=ActionType.RUN_SFM,
            purpose="Run a binding prediction.",
            arguments={"spec": "TEST1|CCO"},
            max_cost=1.0,
            created_at=REQUEST_AT,
        )

        outcome = registry.execute(state, request)
        encoded = json.dumps(outcome.to_dict(), sort_keys=True)

        self.assertEqual(outcome.status, ToolStatus.FAILED)
        self.assertEqual(outcome.error_code, "boltz_endpoint_error")
        self.assertEqual(outcome.payload, {"adapter_status": "endpoint_error"})
        self.assertNotIn("private.example.invalid", encoded)
        self.assertNotIn("internal-detail", encoded)

    def test_structured_boltz_binding_remains_soft_in_stage_runner(self) -> None:
        class FakeStructuredBoltz:
            endpoint = "configured"

            def predict_binding_record(self, spec):
                target, ligand = spec.split("|", 1)
                return {
                    "status": "predicted",
                    "target": target,
                    "ligand": ligand,
                    "affinity": 0.7,
                    "affinity_units": "service-defined",
                    "confidence": 0.8,
                    "iptm": 0.75,
                    "source_kind": "boltz2_live",
                }

        state = make_state(stage=Stage.CANDIDATE_GENERATION)
        registry = register_existing_adapters(
            ToolRegistry(clock=lambda: COMPLETED_AT),
            boltz=FakeStructuredBoltz(),
        )
        plan = StagePlan(
            plan_id="adapter-boltz-plan",
            stage=Stage.CANDIDATE_GENERATION,
            calls=(
                ToolCallSpec(
                    call_id="binding",
                    tool_id="boltz2",
                    operation="predict_binding",
                    action_type=ActionType.RUN_SFM,
                    purpose="Use Boltz-2 as a soft binding prefilter.",
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
        runner = BoundedStageRunner(
            tool_registry=registry,
            mapper_registry=build_default_semantic_mapper_registry(
                target_association_minimum_score=0.5
            ),
            planner=BoundedPlanner(clock=lambda: REQUEST_AT),
            clock=lambda: COMPLETED_AT,
        )

        run = runner.run_stage(
            run_id="adapter-boltz-run",
            state=state,
            stage_plan=plan,
            promotion_contexts={
                "binding": PromotionContext(
                    observed_at=date(2024, 12, 1),
                    available_at=date(2024, 12, 2),
                    subject="candidate-1",
                    object_value="TEST1",
                    confidence=0.8,
                )
            },
        )

        self.assertEqual(run.outcomes[0].status, ToolStatus.SUCCEEDED)
        self.assertEqual(run.promotions[0].code, "boltz_prediction_contextualized")
        self.assertTrue(run.recovered_to_defer)
        self.assertEqual(run.final_state.status, ProgramStatus.DEFERRED)
        self.assertEqual(run.accepted_packets[0].decision, Decision.DEFER)

    def test_unknown_structured_boltz_status_is_redacted(self) -> None:
        class FakeStructuredBoltz:
            endpoint = "configured"

            def predict_binding_record(self, spec):
                return {"status": "https://private.example.invalid/internal-detail"}

        state = make_state(stage=Stage.CANDIDATE_GENERATION)
        registry = register_existing_adapters(
            ToolRegistry(clock=lambda: COMPLETED_AT),
            boltz=FakeStructuredBoltz(),
        )
        request = ToolRequest(
            request_id="boltz-unknown-status",
            program_id=state.program_id,
            expected_state_version=state.version,
            stage=state.current_stage,
            tool_id="boltz2",
            operation="predict_binding",
            action_type=ActionType.RUN_SFM,
            purpose="Run a binding prediction.",
            arguments={"spec": "TEST1|CCO"},
            max_cost=1.0,
            created_at=REQUEST_AT,
        )

        outcome = registry.execute(state, request)
        encoded = json.dumps(outcome.to_dict(), sort_keys=True)

        self.assertEqual(outcome.status, ToolStatus.FAILED)
        self.assertEqual(outcome.error_code, "boltz_response_contract_invalid")
        self.assertEqual(
            outcome.payload,
            {"adapter_status": "invalid_structured_response"},
        )
        self.assertNotIn("private.example.invalid", encoded)


if __name__ == "__main__":
    unittest.main()
