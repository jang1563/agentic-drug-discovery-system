from __future__ import annotations

import json
import unittest
from datetime import date, datetime, timedelta, timezone

from agentic_drug_discovery import (
    ActionType,
    BudgetState,
    ClaimDisposition,
    Decision,
    DecisionPacket,
    DiseaseRecord,
    EvidenceDraft,
    EvidenceEvent,
    EvidenceRelation,
    ExecutionMode,
    GatedDiscoveryEnvironment,
    ProgramState,
    RecordParseError,
    ReplayBundle,
    ScientificClaim,
    SourceReference,
    Stage,
    TargetRecord,
    ToolContract,
    ToolExecutionLedger,
    ToolRegistry,
    ToolRequest,
    ToolResponse,
    ToolStatus,
    evidence_from_outcome,
    packet_from_tool_outcomes,
    replay_bundle_from_json,
    replay_bundle_to_json,
    replay_program,
    tool_execution_ledger_from_dict,
    tool_outcome_from_dict,
    tool_request_from_dict,
)
from agentic_drug_discovery.demo import (
    build_scd_control_plane_demo,
    run_scd_control_plane_demo,
)


REQUEST_AT = datetime(2025, 1, 1, tzinfo=timezone.utc)
COMPLETED_AT = REQUEST_AT + timedelta(minutes=1)
TOOL_SOURCE = SourceReference(
    source_id="test-tool-source",
    source_version="v1",
    locator="https://example.invalid/test-tool",
)
SECOND_TOOL_SOURCE = SourceReference(
    source_id="second-test-tool-source",
    source_version="snapshot-2024-12-01",
    locator="https://example.invalid/second-test-tool",
    content_hash="2" * 64,
)


def make_state(
    *,
    stage: Stage = Stage.TARGET_NOMINATION,
    budget_limit: float = 2.0,
) -> ProgramState:
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
                locator="fixture://tests/execution/disease",
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
        program_id="tool-program",
        disease="test disease",
        therapeutic_hypothesis="A tool-backed hypothesis can be verified.",
        as_of_date=date(2025, 1, 1),
        current_stage=stage,
        budget=BudgetState(limit=budget_limit),
        evidence=evidence,
        diseases=diseases,
    )


def make_contract(*, cost: float = 0.25) -> ToolContract:
    return ToolContract(
        tool_id="testdb",
        operation="association",
        action_type=ActionType.QUERY_DATABASE,
        description="Return a deterministic target-disease score.",
        allowed_stages=(Stage.TARGET_NOMINATION,),
        required_arguments=("target",),
        optional_arguments=("disease",),
        default_cost=cost,
    )


def make_request(
    state: ProgramState,
    *,
    request_id: str = "tool-request-1",
    arguments: dict | None = None,
    max_cost: float = 1.0,
) -> ToolRequest:
    return ToolRequest(
        request_id=request_id,
        program_id=state.program_id,
        expected_state_version=state.version,
        stage=state.current_stage,
        tool_id="testdb",
        operation="association",
        action_type=ActionType.QUERY_DATABASE,
        purpose="Retrieve target-disease evidence.",
        arguments=arguments or {"target": "TEST1", "disease": "test disease"},
        max_cost=max_cost,
        created_at=REQUEST_AT,
    )


def successful_registry() -> ToolRegistry:
    registry = ToolRegistry(clock=lambda: COMPLETED_AT)

    def handler(arguments):
        return ToolResponse(
            status=ToolStatus.SUCCEEDED,
            payload={"target": arguments["target"], "score": 0.91},
            execution_mode=ExecutionMode.CACHE,
            sources=(TOOL_SOURCE,),
            message="Deterministic test query completed.",
        )

    registry.register(make_contract(), handler)
    return registry


class ToolExecutionTests(unittest.TestCase):
    def test_successful_outcome_requires_explicit_evidence_promotion(self) -> None:
        state = make_state()
        request = make_request(state)
        registry = successful_registry()

        outcome = registry.execute(state, request)

        self.assertEqual(outcome.status, ToolStatus.SUCCEEDED)
        self.assertEqual(outcome.payload["score"], 0.91)
        self.assertEqual(len(outcome.payload_sha256), 64)
        self.assertNotIn("relation", outcome.payload)

        identity_draft = EvidenceDraft(
            evidence_id="tool-target-identity-1",
            request_id=request.request_id,
            subject="TEST1",
            predicate="target_identity_resolved",
            object_value="ENSG_TEST1",
            observed_at=date(2024, 12, 1),
            available_at=date(2024, 12, 2),
            confidence=0.91,
        )
        draft = EvidenceDraft(
            evidence_id="tool-evidence-1",
            request_id=request.request_id,
            subject="TEST1",
            predicate="target_disease_supported",
            object_value="test disease",
            observed_at=date(2024, 12, 1),
            available_at=date(2024, 12, 2),
            confidence=0.91,
        )
        evidence = evidence_from_outcome(draft, outcome)
        claim = ScientificClaim(
            claim_id="tool-claim-1",
            stage=state.current_stage,
            subject="TEST1",
            predicate="target_disease_supported",
            object_value="test disease",
            disposition=ClaimDisposition.SUPPORTED,
            supporting_evidence=(identity_draft.evidence_id, evidence.evidence_id),
            confidence=0.91,
        )
        target = TargetRecord(
            target_id="ENSG_TEST1",
            symbol="TEST1",
            disease_id="MONDO_TEST",
            organism="Homo sapiens",
            stage=state.current_stage,
            identifiers={
                "ensembl_gene": "ENSG_TEST1",
                "gene_symbol": "TEST1",
            },
            supporting_evidence=(identity_draft.evidence_id, evidence.evidence_id),
        )
        packet = packet_from_tool_outcomes(
            state,
            packet_id="tool-packet-1",
            decision=Decision.ADVANCE,
            rationale="Explicitly promoted evidence satisfies the target-stage gate.",
            confidence=0.91,
            outcomes=(outcome,),
            evidence_drafts=(identity_draft, draft),
            claim_updates=(claim,),
            target_updates=(target,),
            next_stage=Stage.MODALITY_SELECTION,
            created_at=COMPLETED_AT,
        )

        result = GatedDiscoveryEnvironment().transition(state, packet)

        self.assertTrue(result.applied)
        self.assertEqual(result.state.current_stage, Stage.MODALITY_SELECTION)
        self.assertAlmostEqual(result.state.budget.spent, 0.25)
        target_evidence = [
            item
            for item in result.state.evidence
            if item.stage is Stage.TARGET_NOMINATION
        ]
        self.assertIsNone(target_evidence[0].source.content_hash)
        self.assertEqual(
            target_evidence[0].metadata["tool_payload_sha256"],
            outcome.payload_sha256,
        )
        self.assertEqual(
            result.state.action_history[0].metadata["tool_payload_sha256"],
            outcome.payload_sha256,
        )
        self.assertNotIn("score", result.state.action_history[0].metadata)

        bundle = ReplayBundle(
            initial_state=state,
            packets=(packet,),
            tool_execution_ledger=ToolExecutionLedger((outcome,)),
        )
        replayed = replay_program(
            replay_bundle_from_json(replay_bundle_to_json(bundle))
        )
        self.assertTrue(replayed.results[0].applied)

        tampered_bundle = bundle.to_dict()
        tampered_bundle["packets"][0]["actions"][0]["metadata"][
            "tool_payload_sha256"
        ] = "0" * 64
        with self.assertRaises(RecordParseError):
            replay_bundle_from_json(json.dumps(tampered_bundle))

        unavailable_bundle = bundle.to_dict()
        serialized_outcome = unavailable_bundle["tool_execution_ledger"]["outcomes"][0]
        serialized_outcome["status"] = ToolStatus.UNAVAILABLE.value
        serialized_outcome["error_code"] = "source_unavailable"
        serialized_action = unavailable_bundle["packets"][0]["actions"][0]
        serialized_action["metadata"]["tool_status"] = ToolStatus.UNAVAILABLE.value
        serialized_action["metadata"]["error_code"] = "source_unavailable"
        with self.assertRaisesRegex(
            RecordParseError,
            "non-successful outcome",
        ):
            replay_bundle_from_json(json.dumps(unavailable_bundle))

        checkpoint = ReplayBundle(
            initial_state=result.state,
            packets=(),
            tool_execution_ledger=ToolExecutionLedger((outcome,)),
        )
        self.assertEqual(replay_program(checkpoint).final_state, result.state)
        with self.assertRaises(ValueError):
            ReplayBundle(initial_state=result.state, packets=())

    def test_multi_source_outcome_requires_explicit_evidence_source(self) -> None:
        state = make_state()
        request = make_request(state)
        registry = ToolRegistry(clock=lambda: COMPLETED_AT)
        registry.register(
            make_contract(),
            lambda arguments: ToolResponse(
                status=ToolStatus.SUCCEEDED,
                payload={"target": arguments["target"], "score": 0.91},
                execution_mode=ExecutionMode.CACHE,
                sources=(TOOL_SOURCE, SECOND_TOOL_SOURCE),
                message="Two independent source records were retrieved.",
            ),
        )
        outcome = registry.execute(state, request)
        unbound = EvidenceDraft(
            evidence_id="unbound-multi-source-evidence",
            request_id=request.request_id,
            subject="TEST1",
            predicate="target_disease_supported",
            object_value="test disease",
            observed_at=date(2024, 12, 1),
            available_at=date(2024, 12, 2),
        )

        with self.assertRaisesRegex(ValueError, "explicit source_id"):
            evidence_from_outcome(unbound, outcome)

        bound = EvidenceDraft(
            evidence_id="bound-multi-source-evidence",
            request_id=request.request_id,
            subject="TEST1",
            predicate="target_disease_supported",
            object_value="test disease",
            observed_at=date(2024, 12, 1),
            available_at=date(2024, 12, 2),
            source_id=SECOND_TOOL_SOURCE.source_id,
        )
        evidence = evidence_from_outcome(bound, outcome)

        self.assertEqual(evidence.source, SECOND_TOOL_SOURCE)
        self.assertEqual(evidence.metadata["tool_source_count"], 2)
        self.assertEqual(
            evidence.metadata["selected_source_id"],
            SECOND_TOOL_SOURCE.source_id,
        )

    def test_unavailable_outcome_cannot_be_promoted_but_can_support_defer(self) -> None:
        state = make_state()
        request = make_request(state)
        registry = ToolRegistry(clock=lambda: COMPLETED_AT)
        registry.register(
            make_contract(),
            lambda arguments: ToolResponse(
                status=ToolStatus.UNAVAILABLE,
                payload={"dataset": "unavailable"},
                execution_mode=ExecutionMode.CACHE,
                error_code="dataset_unavailable",
                message="Dataset is unavailable.",
            ),
        )
        outcome = registry.execute(state, request)
        draft = EvidenceDraft(
            evidence_id="unavailable-evidence",
            request_id=request.request_id,
            subject="TEST1",
            predicate="target_disease_supported",
            object_value="test disease",
            observed_at=date(2024, 12, 1),
            available_at=date(2024, 12, 2),
        )

        with self.assertRaises(ValueError):
            evidence_from_outcome(draft, outcome)

        packet = packet_from_tool_outcomes(
            state,
            packet_id="tool-unavailable-defer",
            decision=Decision.DEFER,
            rationale="Required source was unavailable; preserve the attempt and defer.",
            confidence=0.8,
            outcomes=(outcome,),
            created_at=COMPLETED_AT,
        )
        result = GatedDiscoveryEnvironment().transition(state, packet)

        self.assertTrue(result.applied)
        self.assertAlmostEqual(result.state.budget.spent, 0.25)
        self.assertEqual(
            result.state.action_history[0].metadata["tool_status"],
            ToolStatus.UNAVAILABLE.value,
        )

    def test_handler_exception_fails_closed_without_exposing_message(self) -> None:
        state = make_state()
        request = make_request(state)
        registry = ToolRegistry(clock=lambda: COMPLETED_AT)

        def handler(arguments):
            raise RuntimeError("private endpoint detail")

        registry.register(make_contract(), handler)
        outcome = registry.execute(state, request)
        encoded = json.dumps(outcome.to_dict(), sort_keys=True)

        self.assertEqual(outcome.status, ToolStatus.FAILED)
        self.assertEqual(outcome.error_code, "tool_handler_exception")
        self.assertEqual(outcome.payload["exception_type"], "RuntimeError")
        self.assertNotIn("private endpoint detail", encoded)
        self.assertAlmostEqual(outcome.cost, 0.25)

    def test_preflight_contract_failure_does_not_invoke_handler(self) -> None:
        state = make_state()
        request = make_request(state, max_cost=0.1)
        called = False
        registry = ToolRegistry(clock=lambda: COMPLETED_AT)

        def handler(arguments):
            nonlocal called
            called = True
            return ToolResponse(status=ToolStatus.SUCCEEDED, payload={})

        registry.register(make_contract(), handler)
        outcome = registry.execute(state, request)

        self.assertFalse(called)
        self.assertEqual(outcome.status, ToolStatus.FAILED)
        self.assertEqual(outcome.error_code, "tool_request_contract_invalid")
        self.assertIn("cost_limit_exceeded", outcome.payload["failures"])
        self.assertEqual(outcome.cost, 0.0)

    def test_execution_ledger_replay_is_exact_and_rejects_mutated_request(self) -> None:
        state = make_state()
        request = make_request(state)
        registry = successful_registry()
        outcome = registry.execute(state, request)
        ledger = ToolExecutionLedger().append(outcome)

        replayed = registry.replay(state, request, ledger)

        self.assertEqual(replayed, outcome)
        self.assertAlmostEqual(ledger.total_cost, 0.25)

        changed_request = make_request(
            state,
            arguments={"target": "DIFFERENT", "disease": "test disease"},
        )
        mismatch = registry.replay(state, changed_request, ledger)
        self.assertEqual(mismatch.status, ToolStatus.FAILED)
        self.assertEqual(mismatch.error_code, "replay_request_mismatch")

    def test_duplicate_execution_request_id_is_rejected(self) -> None:
        state = make_state()
        outcome = successful_registry().execute(state, make_request(state))
        ledger = ToolExecutionLedger((outcome,))

        with self.assertRaises(ValueError):
            ledger.append(outcome)

    def test_tool_records_round_trip_and_detect_hash_tampering(self) -> None:
        state = make_state()
        request = make_request(state)
        outcome = successful_registry().execute(state, request)
        ledger = ToolExecutionLedger((outcome,))

        self.assertEqual(tool_request_from_dict(request.to_dict()), request)
        self.assertEqual(tool_outcome_from_dict(outcome.to_dict()), outcome)
        self.assertEqual(tool_execution_ledger_from_dict(ledger.to_dict()), ledger)

        tampered = outcome.to_dict()
        tampered["payload"]["score"] = 0.01
        with self.assertRaises(RecordParseError):
            tool_outcome_from_dict(tampered)

        tampered_action_type = outcome.to_dict()
        tampered_action_type["action_type"] = ActionType.RUN_SFM.value
        with self.assertRaises(ValueError):
            tool_outcome_from_dict(tampered_action_type)

        tampered_contract = outcome.to_dict()
        tampered_contract["contract_id"] = "otherdb.association@1"
        with self.assertRaisesRegex(ValueError, "requested tool operation"):
            tool_outcome_from_dict(tampered_contract)

        over_budget = outcome.to_dict()
        over_budget["cost"] = request.max_cost + 0.01
        with self.assertRaisesRegex(ValueError, "request.max_cost"):
            tool_outcome_from_dict(over_budget)

    def test_replay_bundle_round_trip_reproduces_demo_final_state(self) -> None:
        _, initial_state, packets = build_scd_control_plane_demo()
        expected_state, _ = run_scd_control_plane_demo()
        bundle = ReplayBundle(initial_state=initial_state, packets=packets)

        restored = replay_bundle_from_json(replay_bundle_to_json(bundle))
        report = replay_program(restored)

        self.assertEqual(restored, bundle)
        self.assertEqual(report.final_state, expected_state)
        self.assertEqual(report.accepted_count, 8)
        self.assertEqual(report.blocked_count, 0)
        self.assertFalse(report.stopped_on_block)

    def test_replay_stops_at_first_blocking_packet(self) -> None:
        state = make_state(stage=Stage.DISEASE_CONTEXT)
        packet = DecisionPacket(
            packet_id="blocked-replay-packet",
            program_id=state.program_id,
            expected_state_version=state.version,
            stage=state.current_stage,
            decision=Decision.ADVANCE,
            rationale="Intentionally lacks readiness evidence.",
            confidence=0.9,
            next_stage=Stage.TARGET_NOMINATION,
            created_at=REQUEST_AT,
        )
        report = replay_program(ReplayBundle(initial_state=state, packets=(packet,)))

        self.assertTrue(report.stopped_on_block)
        self.assertEqual(report.blocked_count, 1)
        self.assertIs(report.final_state, state)

    def test_strict_bundle_parser_rejects_unknown_fields(self) -> None:
        _, initial_state, packets = build_scd_control_plane_demo()
        bundle = ReplayBundle(initial_state=initial_state, packets=packets).to_dict()
        bundle["unexpected"] = True

        with self.assertRaises(RecordParseError):
            replay_bundle_from_json(json.dumps(bundle))

    def test_stale_tool_outcome_cannot_be_assembled_into_packet(self) -> None:
        state = make_state()
        outcome = successful_registry().execute(state, make_request(state))
        defer_packet = DecisionPacket(
            packet_id="advance-state-version",
            program_id=state.program_id,
            expected_state_version=state.version,
            stage=state.current_stage,
            decision=Decision.DEFER,
            rationale="Create a valid newer state for stale-outcome testing.",
            confidence=0.8,
            created_at=COMPLETED_AT,
        )
        newer_state = GatedDiscoveryEnvironment().transition(state, defer_packet).state

        with self.assertRaises(ValueError):
            packet_from_tool_outcomes(
                newer_state,
                packet_id="stale-tool-outcome-packet",
                decision=Decision.DEFER,
                rationale="Stale outcome must not enter a newer state.",
                confidence=0.8,
                outcomes=(outcome,),
                created_at=COMPLETED_AT,
            )

    def test_packet_cannot_predate_linked_tool_outcome(self) -> None:
        state = make_state()
        outcome = successful_registry().execute(state, make_request(state))

        with self.assertRaisesRegex(ValueError, "cannot predate"):
            packet_from_tool_outcomes(
                state,
                packet_id="premature-tool-outcome-packet",
                decision=Decision.DEFER,
                rationale="Packet timestamp must follow its linked tool outcome.",
                confidence=0.8,
                outcomes=(outcome,),
                created_at=REQUEST_AT,
            )


if __name__ == "__main__":
    unittest.main()
