from __future__ import annotations

import json
import unittest
from dataclasses import replace
from datetime import date, datetime, timezone

from agentic_drug_discovery import (
    ActionRecord,
    ActionType,
    BudgetState,
    CandidateRecord,
    ClaimDisposition,
    Decision,
    DecisionPacket,
    DiseaseRecord,
    EvidenceEvent,
    EvidenceRelation,
    GatedDiscoveryEnvironment,
    ProgramState,
    ProgramStatus,
    ScientificClaim,
    SourceReference,
    Stage,
    VerifierKind,
    VerifierResult,
    VerifierStatus,
)
from agentic_drug_discovery.demo import build_demo_report, run_scd_control_plane_demo


SOURCE = SourceReference(
    source_id="test-source",
    source_version="v1",
    locator="tests/test_environment.py",
)
CREATED_AT = datetime(2025, 1, 1, tzinfo=timezone.utc)


def make_state(
    *,
    stage: Stage = Stage.DISEASE_CONTEXT,
    status: ProgramStatus = ProgramStatus.ACTIVE,
    version: int = 0,
    budget_limit: float = 5.0,
    evidence: tuple[EvidenceEvent, ...] = (),
    claims: tuple[ScientificClaim, ...] = (),
    candidates: tuple[CandidateRecord, ...] = (),
    action_history: tuple[ActionRecord, ...] = (),
) -> ProgramState:
    return ProgramState(
        program_id="test-program",
        disease="test disease",
        therapeutic_hypothesis="testable therapeutic hypothesis",
        as_of_date=date(2025, 1, 1),
        current_stage=stage,
        budget=BudgetState(limit=budget_limit),
        evidence=evidence,
        claims=claims,
        candidates=candidates,
        action_history=action_history,
        status=status,
        version=version,
    )


def make_evidence(
    evidence_id: str,
    *,
    stage: Stage,
    predicate: str,
    available_at: date = date(2024, 1, 2),
    relation: EvidenceRelation = EvidenceRelation.SUPPORTS,
    source: SourceReference = SOURCE,
) -> EvidenceEvent:
    observed_at = date(2024, 1, 1) if available_at >= date(2024, 1, 1) else available_at
    return EvidenceEvent(
        evidence_id=evidence_id,
        stage=stage,
        subject="test-program",
        predicate=predicate,
        object_value="test observation",
        source=source,
        observed_at=observed_at,
        available_at=available_at,
        relation=relation,
        biological_context=(
            {"disease_id": "MONDO_TEST"}
            if stage is Stage.DISEASE_CONTEXT
            else {}
        ),
    )


def make_claim(
    claim_id: str,
    *,
    stage: Stage,
    predicate: str,
    disposition: ClaimDisposition = ClaimDisposition.SUPPORTED,
    supporting: tuple[str, ...] = (),
    contradicting: tuple[str, ...] = (),
) -> ScientificClaim:
    return ScientificClaim(
        claim_id=claim_id,
        stage=stage,
        subject="test-program",
        predicate=predicate,
        object_value="test claim",
        disposition=disposition,
        supporting_evidence=supporting,
        contradicting_evidence=contradicting,
        confidence=0.8,
    )


def make_action(
    evidence_id: str,
    *,
    cost: float = 0.25,
    action_id: str | None = None,
) -> ActionRecord:
    return ActionRecord(
        action_id=action_id or f"action-{evidence_id}",
        action_type=ActionType.RETRIEVE_EVIDENCE,
        purpose="Retrieve typed test evidence.",
        cost=cost,
        evidence_ids=(evidence_id,),
    )


def make_ready_disease_artifacts(
    prefix: str,
) -> tuple[
    tuple[EvidenceEvent, EvidenceEvent],
    ScientificClaim,
    tuple[ActionRecord, ActionRecord],
]:
    burden = make_evidence(
        f"{prefix}-burden",
        stage=Stage.DISEASE_CONTEXT,
        predicate="disease_burden_supported",
        source=SourceReference(
            source_id=f"{prefix}-burden-source",
            source_version="snapshot-v1",
            locator=f"https://example.invalid/{prefix}/burden",
            content_hash="1" * 64,
        ),
    )
    gap = make_evidence(
        f"{prefix}-gap",
        stage=Stage.DISEASE_CONTEXT,
        predicate="treatment_gap_supported",
        source=SourceReference(
            source_id=f"{prefix}-gap-source",
            source_version="snapshot-v1",
            locator=f"https://example.invalid/{prefix}/gap",
            content_hash="2" * 64,
        ),
    )
    claim = make_claim(
        f"{prefix}-claim",
        stage=Stage.DISEASE_CONTEXT,
        predicate="unmet_need_defined",
        supporting=(burden.evidence_id, gap.evidence_id),
    )
    return (
        (burden, gap),
        claim,
        (make_action(burden.evidence_id), make_action(gap.evidence_id)),
    )


def make_packet(
    state: ProgramState,
    *,
    packet_id: str,
    decision: Decision,
    evidence: tuple[EvidenceEvent, ...] = (),
    claims: tuple[ScientificClaim, ...] = (),
    disease_updates: tuple[DiseaseRecord, ...] = (),
    actions: tuple[ActionRecord, ...] = (),
    next_stage: Stage | None = None,
    backtrack_stage: Stage | None = None,
    expected_state_version: int | None = None,
) -> DecisionPacket:
    if not disease_updates and state.current_stage is Stage.DISEASE_CONTEXT:
        supporting_evidence = tuple(
            item.evidence_id
            for item in evidence
            if item.relation is EvidenceRelation.SUPPORTS
        )
        if supporting_evidence:
            disease_updates = (
                DiseaseRecord(
                    disease_id="MONDO_TEST",
                    name="test disease",
                    stage=Stage.DISEASE_CONTEXT,
                    identifiers={"canonical": "MONDO_TEST"},
                    supporting_evidence=supporting_evidence,
                ),
            )
    return DecisionPacket(
        packet_id=packet_id,
        program_id=state.program_id,
        expected_state_version=(
            state.version if expected_state_version is None else expected_state_version
        ),
        stage=state.current_stage,
        decision=decision,
        rationale="Test decision with explicit evidence and verifier gates.",
        confidence=0.8,
        actions=actions,
        evidence_additions=evidence,
        claim_updates=claims,
        disease_updates=disease_updates,
        next_stage=next_stage,
        backtrack_stage=backtrack_stage,
        created_at=CREATED_AT,
    )


def blocking_codes(result) -> set[str]:
    return {item.code for item in result.blocking_results}


class ExplodingVerifier:
    verifier_id = "exploding_test_verifier"
    kind = VerifierKind.DETERMINISTIC

    def verify(self, state, packet, proposed_state):
        raise RuntimeError("deliberate verifier failure")


class InvalidReturnVerifier:
    verifier_id = "invalid_return_test_verifier"
    kind = VerifierKind.DETERMINISTIC

    def verify(self, state, packet, proposed_state):
        return {"status": "pass"}


class NonBlockingFailureVerifier:
    verifier_id = "nonblocking_failure_test_verifier"
    kind = VerifierKind.DETERMINISTIC

    def verify(self, state, packet, proposed_state):
        return VerifierResult(
            verifier_id=self.verifier_id,
            kind=self.kind,
            status=VerifierStatus.FAIL,
            code="nonblocking_deterministic_failure",
            message="This malformed deterministic failure must not be allowed through.",
            stage=state.current_stage,
            blocking=False,
        )


class SoftWarningVerifier:
    verifier_id = "soft_warning_test_verifier"
    kind = VerifierKind.SOFT

    def verify(self, state, packet, proposed_state):
        return VerifierResult(
            verifier_id=self.verifier_id,
            kind=self.kind,
            status=VerifierStatus.WARN,
            code="soft_scientific_warning",
            message="Soft uncertainty is recorded without bypassing hard verifiers.",
            stage=state.current_stage,
            score=0.5,
        )


class GatedDiscoveryEnvironmentTests(unittest.TestCase):
    def test_illustrative_demo_completes_all_eight_stages(self) -> None:
        state, results = run_scd_control_plane_demo()

        self.assertEqual(len(results), 8)
        self.assertTrue(all(result.applied for result in results))
        self.assertEqual(state.status, ProgramStatus.COMPLETED)
        self.assertEqual(state.version, 8)
        self.assertEqual(len(state.evidence), 19)
        self.assertEqual(len(state.claims), 9)
        self.assertEqual(len(state.candidates), 1)
        self.assertEqual(len(state.trial_designs), 1)
        self.assertEqual(len(state.trial_designs[0].safety_records), 1)
        self.assertEqual(len(state.action_history), 8)
        self.assertEqual(len(state.packet_history), 8)
        self.assertEqual(
            state.decision_history[-1].action_ids,
            (state.action_history[-1].action_id,),
        )
        self.assertEqual(
            state.packet_history[-1].packet_id,
            state.decision_history[-1].packet_id,
        )
        self.assertAlmostEqual(state.budget.spent, 2.0)

    def test_future_evidence_fails_closed_and_preserves_state(self) -> None:
        state = make_state()
        predicate = "unmet_need_defined"
        evidence = make_evidence(
            "future-evidence",
            stage=state.current_stage,
            predicate=predicate,
            available_at=date(2026, 1, 1),
        )
        claim = make_claim(
            "future-claim",
            stage=state.current_stage,
            predicate=predicate,
            supporting=(evidence.evidence_id,),
        )
        packet = make_packet(
            state,
            packet_id="future-packet",
            decision=Decision.ADVANCE,
            evidence=(evidence,),
            claims=(claim,),
            actions=(make_action(evidence.evidence_id),),
            next_stage=Stage.TARGET_NOMINATION,
        )

        result = GatedDiscoveryEnvironment().transition(state, packet)

        self.assertFalse(result.applied)
        self.assertIs(result.state, state)
        self.assertIn("future_evidence_leak", blocking_codes(result))
        self.assertEqual(state.version, 0)

    def test_future_evidence_preloaded_in_state_blocks_any_transition(self) -> None:
        future = make_evidence(
            "preloaded-future-evidence",
            stage=Stage.DISEASE_CONTEXT,
            predicate="unmet_need_defined",
            available_at=date(2026, 1, 1),
        )
        state = make_state(evidence=(future,))
        packet = make_packet(
            state,
            packet_id="preloaded-future-packet",
            decision=Decision.DEFER,
        )

        result = GatedDiscoveryEnvironment().transition(state, packet)

        self.assertFalse(result.applied)
        self.assertIs(result.state, state)
        self.assertIn("future_evidence_leak", blocking_codes(result))

    def test_stale_packet_is_blocked(self) -> None:
        state = make_state()
        packet = make_packet(
            state,
            packet_id="stale-packet",
            decision=Decision.DEFER,
            expected_state_version=1,
        )

        result = GatedDiscoveryEnvironment().transition(state, packet)

        self.assertFalse(result.applied)
        self.assertIn("packet_context_invalid", blocking_codes(result))

    def test_advance_requires_configured_stage_evidence_and_claim(self) -> None:
        state = make_state()
        packet = make_packet(
            state,
            packet_id="empty-advance",
            decision=Decision.ADVANCE,
            next_stage=Stage.TARGET_NOMINATION,
        )

        result = GatedDiscoveryEnvironment().transition(state, packet)

        self.assertFalse(result.applied)
        self.assertIn("stage_not_ready", blocking_codes(result))

    def test_composite_gate_accepts_independent_pinned_component_evidence(
        self,
    ) -> None:
        state = make_state()
        evidence, claim, actions = make_ready_disease_artifacts("ready-disease")
        packet = make_packet(
            state,
            packet_id="ready-composite-disease-packet",
            decision=Decision.ADVANCE,
            evidence=evidence,
            claims=(claim,),
            actions=actions,
            next_stage=Stage.TARGET_NOMINATION,
        )

        result = GatedDiscoveryEnvironment().transition(state, packet)

        self.assertTrue(result.applied)
        readiness = next(
            item
            for item in result.verifier_results
            if item.verifier_id == "stage_readiness"
        )
        self.assertEqual(readiness.details["independent_source_count"], 2)
        self.assertEqual(readiness.details["unpinned_evidence_ids"], ())

    def test_composite_gate_rejects_one_source_for_two_components(self) -> None:
        state = make_state()
        shared_source = SourceReference(
            source_id="shared-source",
            source_version="snapshot-v1",
            locator="https://example.invalid/shared",
            content_hash="3" * 64,
        )
        burden = make_evidence(
            "shared-burden",
            stage=state.current_stage,
            predicate="disease_burden_supported",
            source=shared_source,
        )
        gap = make_evidence(
            "shared-gap",
            stage=state.current_stage,
            predicate="treatment_gap_supported",
            source=shared_source,
        )
        claim = make_claim(
            "shared-source-unmet-need",
            stage=state.current_stage,
            predicate="unmet_need_defined",
            supporting=(burden.evidence_id, gap.evidence_id),
        )
        packet = make_packet(
            state,
            packet_id="shared-source-composite-packet",
            decision=Decision.ADVANCE,
            evidence=(burden, gap),
            claims=(claim,),
            actions=(make_action(burden.evidence_id), make_action(gap.evidence_id)),
            next_stage=Stage.TARGET_NOMINATION,
        )

        result = GatedDiscoveryEnvironment().transition(state, packet)

        self.assertFalse(result.applied)
        readiness = next(
            item
            for item in result.verifier_results
            if item.verifier_id == "stage_readiness"
        )
        self.assertIn("insufficient_independent_sources", readiness.details["failures"])

    def test_stage_gate_rejects_unlinked_evidence_laundering(self) -> None:
        state = make_state()
        linked_evidence = make_evidence(
            "linked-context-evidence",
            stage=state.current_stage,
            predicate="contextual_observation",
        )
        unlinked_gate_evidence = make_evidence(
            "unlinked-gate-evidence",
            stage=state.current_stage,
            predicate="unmet_need_defined",
        )
        claim = make_claim(
            "gate-claim-with-wrong-link",
            stage=state.current_stage,
            predicate="unmet_need_defined",
            supporting=(linked_evidence.evidence_id,),
        )
        packet = make_packet(
            state,
            packet_id="unlinked-gate-evidence-packet",
            decision=Decision.ADVANCE,
            evidence=(linked_evidence, unlinked_gate_evidence),
            claims=(claim,),
            actions=(
                make_action(linked_evidence.evidence_id),
                make_action(unlinked_gate_evidence.evidence_id),
            ),
            next_stage=Stage.TARGET_NOMINATION,
        )

        result = GatedDiscoveryEnvironment().transition(state, packet)

        self.assertFalse(result.applied)
        self.assertIn("stage_not_ready", blocking_codes(result))

    def test_candidate_generation_cannot_advance_without_candidate_record(self) -> None:
        stage = Stage.CANDIDATE_GENERATION
        predicate = "candidate_identity_resolved"
        state = make_state(stage=stage)
        evidence = make_evidence(
            "candidate-identity-evidence",
            stage=stage,
            predicate=predicate,
        )
        claim = make_claim(
            "candidate-identity-claim",
            stage=stage,
            predicate=predicate,
            supporting=(evidence.evidence_id,),
        )
        packet = make_packet(
            state,
            packet_id="candidate-free-advance",
            decision=Decision.ADVANCE,
            evidence=(evidence,),
            claims=(claim,),
            actions=(make_action(evidence.evidence_id),),
            next_stage=Stage.LEAD_OPTIMIZATION,
        )

        result = GatedDiscoveryEnvironment().transition(state, packet)

        self.assertFalse(result.applied)
        self.assertIn("stage_not_ready", blocking_codes(result))

    def test_contested_claim_blocks_advance_but_allows_defer(self) -> None:
        stage = Stage.TARGET_NOMINATION
        predicate = "target_disease_supported"
        support = make_evidence("support", stage=stage, predicate=predicate)
        original_claim = make_claim(
            "target-claim",
            stage=stage,
            predicate=predicate,
            supporting=(support.evidence_id,),
        )
        state = make_state(stage=stage, evidence=(support,), claims=(original_claim,))
        contradiction = make_evidence(
            "contradiction",
            stage=stage,
            predicate=predicate,
            relation=EvidenceRelation.CONTRADICTS,
        )
        contested = make_claim(
            original_claim.claim_id,
            stage=stage,
            predicate=predicate,
            disposition=ClaimDisposition.CONTESTED,
            supporting=(support.evidence_id,),
            contradicting=(contradiction.evidence_id,),
        )

        advance = make_packet(
            state,
            packet_id="contested-advance",
            decision=Decision.ADVANCE,
            evidence=(contradiction,),
            claims=(contested,),
            actions=(make_action(contradiction.evidence_id),),
            next_stage=Stage.MODALITY_SELECTION,
        )
        advance_result = GatedDiscoveryEnvironment().transition(state, advance)

        self.assertFalse(advance_result.applied)
        self.assertIn("unresolved_program_claims", blocking_codes(advance_result))

        defer = make_packet(
            state,
            packet_id="contested-defer",
            decision=Decision.DEFER,
            evidence=(contradiction,),
            claims=(contested,),
            actions=(make_action(contradiction.evidence_id),),
        )
        defer_result = GatedDiscoveryEnvironment().transition(state, defer)

        self.assertTrue(defer_result.applied)
        self.assertEqual(defer_result.state.status, ProgramStatus.DEFERRED)
        self.assertEqual(
            defer_result.state.claims_by_id[original_claim.claim_id].disposition,
            ClaimDisposition.CONTESTED,
        )

    def test_later_stage_evidence_can_trigger_upstream_pivot(self) -> None:
        support = make_evidence(
            "target-support",
            stage=Stage.TARGET_NOMINATION,
            predicate="target_disease_supported",
        )
        original_claim = make_claim(
            "upstream-target-claim",
            stage=Stage.TARGET_NOMINATION,
            predicate="target_disease_supported",
            supporting=(support.evidence_id,),
        )
        state = make_state(
            stage=Stage.CLINICAL_STRATEGY,
            evidence=(support,),
            claims=(original_claim,),
        )
        contradiction = make_evidence(
            "clinical-contradiction",
            stage=Stage.CLINICAL_STRATEGY,
            predicate="target_translation_contradicted",
            relation=EvidenceRelation.CONTRADICTS,
        )
        contested = make_claim(
            original_claim.claim_id,
            stage=Stage.TARGET_NOMINATION,
            predicate=original_claim.predicate,
            disposition=ClaimDisposition.CONTESTED,
            supporting=(support.evidence_id,),
            contradicting=(contradiction.evidence_id,),
        )
        packet = make_packet(
            state,
            packet_id="clinical-to-target-pivot",
            decision=Decision.PIVOT,
            evidence=(contradiction,),
            claims=(contested,),
            actions=(make_action(contradiction.evidence_id),),
            backtrack_stage=Stage.TARGET_NOMINATION,
        )

        result = GatedDiscoveryEnvironment().transition(state, packet)

        self.assertTrue(result.applied)
        self.assertEqual(result.state.current_stage, Stage.TARGET_NOMINATION)
        self.assertEqual(result.state.status, ProgramStatus.ACTIVE)
        self.assertEqual(result.state.version, 1)
        self.assertEqual(
            result.state.claims_by_id[original_claim.claim_id].disposition,
            ClaimDisposition.CONTESTED,
        )

    def test_action_cost_cannot_exceed_budget(self) -> None:
        state = make_state(budget_limit=0.1)
        evidence = make_evidence(
            "costly-evidence",
            stage=state.current_stage,
            predicate="unmet_need_defined",
        )
        claim = make_claim(
            "costly-claim",
            stage=state.current_stage,
            predicate="unmet_need_defined",
            supporting=(evidence.evidence_id,),
        )
        packet = make_packet(
            state,
            packet_id="over-budget",
            decision=Decision.ADVANCE,
            evidence=(evidence,),
            claims=(claim,),
            actions=(make_action(evidence.evidence_id, cost=1.0),),
            next_stage=Stage.TARGET_NOMINATION,
        )

        result = GatedDiscoveryEnvironment().transition(state, packet)

        self.assertFalse(result.applied)
        self.assertIn("budget_exceeded", blocking_codes(result))
        self.assertEqual(result.state.budget.spent, 0.0)

    def test_terminal_state_rejects_new_packets(self) -> None:
        state = make_state(
            stage=Stage.REGULATORY_POSTMARKET,
            status=ProgramStatus.COMPLETED,
        )
        packet = make_packet(
            state,
            packet_id="after-completion",
            decision=Decision.DEFER,
        )

        result = GatedDiscoveryEnvironment().transition(state, packet)

        self.assertFalse(result.applied)
        self.assertIn("packet_context_invalid", blocking_codes(result))

    def test_verifier_exception_fails_closed(self) -> None:
        state = make_state()
        packet = make_packet(
            state,
            packet_id="verifier-exception",
            decision=Decision.DEFER,
        )
        environment = GatedDiscoveryEnvironment(extra_verifiers=(ExplodingVerifier(),))

        result = environment.transition(state, packet)

        self.assertFalse(result.applied)
        self.assertIn("verifier_exception", blocking_codes(result))
        self.assertIs(result.state, state)

    def test_invalid_verifier_return_fails_closed(self) -> None:
        state = make_state()
        packet = make_packet(
            state,
            packet_id="invalid-verifier-return",
            decision=Decision.DEFER,
        )
        environment = GatedDiscoveryEnvironment(
            extra_verifiers=(InvalidReturnVerifier(),)
        )

        result = environment.transition(state, packet)

        self.assertFalse(result.applied)
        self.assertIn("verifier_contract_invalid", blocking_codes(result))
        self.assertIs(result.state, state)

    def test_deterministic_nonblocking_failure_is_rejected(self) -> None:
        state = make_state()
        packet = make_packet(
            state,
            packet_id="nonblocking-deterministic-failure",
            decision=Decision.DEFER,
        )
        environment = GatedDiscoveryEnvironment(
            extra_verifiers=(NonBlockingFailureVerifier(),)
        )

        result = environment.transition(state, packet)

        self.assertFalse(result.applied)
        self.assertIn("verifier_contract_invalid", blocking_codes(result))
        self.assertIs(result.state, state)

    def test_soft_warning_is_recorded_without_blocking(self) -> None:
        state = make_state()
        packet = make_packet(
            state,
            packet_id="soft-warning-defer",
            decision=Decision.DEFER,
        )
        environment = GatedDiscoveryEnvironment(
            extra_verifiers=(SoftWarningVerifier(),)
        )

        result = environment.transition(state, packet)

        self.assertTrue(result.applied)
        self.assertEqual(result.state.status, ProgramStatus.DEFERRED)
        self.assertEqual(result.state.verifier_history[-1].status, VerifierStatus.WARN)
        self.assertEqual(result.state.verifier_history[-1].score, 0.5)

    def test_duplicate_evidence_id_is_structurally_blocked(self) -> None:
        existing = make_evidence(
            "duplicate-evidence",
            stage=Stage.DISEASE_CONTEXT,
            predicate="unmet_need_defined",
        )
        state = make_state(evidence=(existing,))
        packet = make_packet(
            state,
            packet_id="duplicate-evidence-packet",
            decision=Decision.DEFER,
            evidence=(existing,),
            actions=(make_action(existing.evidence_id),),
        )

        result = GatedDiscoveryEnvironment().transition(state, packet)

        self.assertFalse(result.applied)
        self.assertIn("packet_integrity_invalid", blocking_codes(result))

    def test_duplicate_action_id_is_blocked_across_packets(self) -> None:
        initial_state = make_state()
        evidence, claim, actions = make_ready_disease_artifacts("existing-action")
        existing_action = make_action(
            evidence[0].evidence_id,
            action_id="globally-unique-action",
        )
        first_actions = (existing_action, actions[1])
        first_packet = make_packet(
            initial_state,
            packet_id="first-action-packet",
            decision=Decision.ADVANCE,
            evidence=evidence,
            claims=(claim,),
            actions=first_actions,
            next_stage=Stage.TARGET_NOMINATION,
        )
        first_result = GatedDiscoveryEnvironment().transition(
            initial_state, first_packet
        )
        self.assertTrue(first_result.applied)

        state = first_result.state
        repeated_action = make_action(
            evidence[0].evidence_id,
            action_id=existing_action.action_id,
        )
        packet = make_packet(
            state,
            packet_id="duplicate-action-packet",
            decision=Decision.DEFER,
            actions=(repeated_action,),
        )

        result = GatedDiscoveryEnvironment().transition(state, packet)

        self.assertFalse(result.applied)
        self.assertIn("packet_integrity_invalid", blocking_codes(result))

    def test_tampered_committed_state_fails_closed_before_projection(self) -> None:
        initial_state = make_state()
        evidence, claim, actions = make_ready_disease_artifacts("integrity")
        packet = make_packet(
            initial_state,
            packet_id="integrity-source-packet",
            decision=Decision.ADVANCE,
            evidence=evidence,
            claims=(claim,),
            actions=actions,
            next_stage=Stage.TARGET_NOMINATION,
        )
        committed = GatedDiscoveryEnvironment().transition(initial_state, packet).state
        tampered_claim = replace(
            committed.claims[0], object_value="tampered after commit"
        )
        tampered_state = replace(committed, claims=(tampered_claim,))
        next_packet = make_packet(
            tampered_state,
            packet_id="tampered-state-packet",
            decision=Decision.DEFER,
        )

        result = GatedDiscoveryEnvironment().transition(tampered_state, next_packet)

        self.assertFalse(result.applied)
        self.assertIs(result.state, tampered_state)
        self.assertIn("input_state_integrity_invalid", blocking_codes(result))

    def test_claim_reference_polarity_must_match_evidence_relation(self) -> None:
        contradiction = make_evidence(
            "misclassified-contradiction",
            stage=Stage.DISEASE_CONTEXT,
            predicate="unmet_need_defined",
            relation=EvidenceRelation.CONTRADICTS,
        )
        claim = make_claim(
            "polarity-mismatch-claim",
            stage=Stage.DISEASE_CONTEXT,
            predicate="unmet_need_defined",
            supporting=(contradiction.evidence_id,),
        )
        state = make_state()
        packet = make_packet(
            state,
            packet_id="polarity-mismatch-packet",
            decision=Decision.DEFER,
            evidence=(contradiction,),
            claims=(claim,),
            actions=(make_action(contradiction.evidence_id),),
        )

        result = GatedDiscoveryEnvironment().transition(state, packet)

        self.assertFalse(result.applied)
        self.assertIn("evidence_reference_invalid", blocking_codes(result))

    def test_mapping_fields_reject_sequence_values(self) -> None:
        with self.assertRaises(TypeError):
            ActionRecord(
                action_id="invalid-metadata-action",
                action_type=ActionType.RETRIEVE_EVIDENCE,
                purpose="Exercise runtime model validation.",
                metadata=["not", "a", "mapping"],
            )

    def test_demo_report_and_model_records_are_json_serializable(self) -> None:
        state, _ = run_scd_control_plane_demo()

        encoded_report = json.dumps(build_demo_report(), sort_keys=True)
        encoded_state = json.dumps(state.to_dict(), sort_keys=True)

        self.assertIn('"completed": true', encoded_report)
        self.assertIn('"status": "completed"', encoded_state)


if __name__ == "__main__":
    unittest.main()
