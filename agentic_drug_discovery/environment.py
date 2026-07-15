"""Fail-closed transition engine for long-horizon discovery decisions."""

from __future__ import annotations

from dataclasses import replace
from typing import Mapping, Sequence

from .models import (
    Decision,
    DecisionPacket,
    DecisionRecord,
    DEFAULT_STAGE_SEQUENCE,
    ProgramState,
    ProgramStatus,
    Stage,
    StageGate,
    TransitionResult,
    VerifierKind,
    VerifierResult,
    VerifierStatus,
)
from .verifiers import (
    BudgetVerifier,
    ClinicalIdentityContinuityVerifier,
    ClinicalEndpointMappingContinuityVerifier,
    ClinicalSynthesisContinuityVerifier,
    ContextIdentityContinuityVerifier,
    ContradictionGateVerifier,
    EvidenceChronologyVerifier,
    EvidenceReferenceVerifier,
    PacketContextVerifier,
    PacketIntegrityVerifier,
    StageReadinessVerifier,
    StageTransitionVerifier,
    TargetIdentityContinuityVerifier,
    TransitionVerifier,
)


DEFAULT_STAGE_PREDICATES: Mapping[Stage, str] = {
    Stage.DISEASE_CONTEXT: "unmet_need_defined",
    Stage.TARGET_NOMINATION: "target_disease_supported",
    Stage.MODALITY_SELECTION: "modality_matches_mechanism",
    Stage.CANDIDATE_GENERATION: "candidate_identity_resolved",
    Stage.LEAD_OPTIMIZATION: "developability_reviewed",
    Stage.PRECLINICAL_VALIDATION: "functional_effect_supported",
    Stage.CLINICAL_STRATEGY: "clinical_evidence_assessed",
    Stage.REGULATORY_POSTMARKET: "regulatory_status_assessed",
}

COMPOSITE_STAGE_EVIDENCE_PREDICATES: Mapping[Stage, tuple[str, ...]] = {
    Stage.DISEASE_CONTEXT: (
        "disease_burden_supported",
        "treatment_gap_supported",
    ),
    Stage.TARGET_NOMINATION: (
        "target_identity_resolved",
        "target_disease_supported",
    ),
    Stage.MODALITY_SELECTION: (
        "target_identity_continuous",
        "modality_matches_mechanism",
    ),
    Stage.PRECLINICAL_VALIDATION: (
        "candidate_target_functional_activity_supported",
        "disease_model_effect_supported",
    ),
    Stage.CLINICAL_STRATEGY: (
        "clinical_evidence_assessed",
        "clinical_safety_assessed",
    ),
}

TARGET_IDENTIFIER_NAMESPACES: Mapping[Stage, tuple[str, ...]] = {
    Stage.TARGET_NOMINATION: ("ensembl_gene", "gene_symbol"),
    Stage.MODALITY_SELECTION: ("ensembl_gene", "gene_symbol", "chembl_target"),
    Stage.CANDIDATE_GENERATION: ("ensembl_gene", "gene_symbol", "chembl_target"),
    Stage.LEAD_OPTIMIZATION: ("ensembl_gene", "gene_symbol", "chembl_target"),
    Stage.PRECLINICAL_VALIDATION: (
        "ensembl_gene",
        "gene_symbol",
        "chembl_target",
    ),
}


def default_stage_gates() -> dict[Stage, StageGate]:
    """Return conservative, domain-neutral gates for the eight-stage chain."""

    candidate_stages = set(DEFAULT_STAGE_SEQUENCE[3:])
    gates: dict[Stage, StageGate] = {}
    for stage, predicate in DEFAULT_STAGE_PREDICATES.items():
        evidence_predicates = COMPOSITE_STAGE_EVIDENCE_PREDICATES.get(
            stage, (predicate,)
        )
        requires_independent_pinned_sources = stage in (
            Stage.DISEASE_CONTEXT,
            Stage.PRECLINICAL_VALIDATION,
            Stage.CLINICAL_STRATEGY,
        )
        gates[stage] = StageGate(
            stage=stage,
            required_claim_predicates=(
                evidence_predicates
                if stage is Stage.CLINICAL_STRATEGY
                else (predicate,)
            ),
            required_evidence_predicates=evidence_predicates,
            required_target_identifier_namespaces=TARGET_IDENTIFIER_NAMESPACES.get(
                stage, ()
            ),
            minimum_evidence_events=len(evidence_predicates),
            minimum_independent_sources=(
                (
                    1
                    if stage is Stage.CLINICAL_STRATEGY
                    else len(evidence_predicates)
                )
                if requires_independent_pinned_sources
                else 0
            ),
            require_source_content_hashes=requires_independent_pinned_sources,
            minimum_viable_candidates=1 if stage in candidate_stages else 0,
            minimum_disease_records=1,
            minimum_assay_records=(
                1 if stage is Stage.PRECLINICAL_VALIDATION else 0
            ),
            minimum_model_system_records=(
                1 if stage is Stage.PRECLINICAL_VALIDATION else 0
            ),
            minimum_intervention_records=(
                1
                if stage
                in {Stage.CLINICAL_STRATEGY, Stage.REGULATORY_POSTMARKET}
                else 0
            ),
            minimum_trial_records=(
                1 if stage is Stage.CLINICAL_STRATEGY else 0
            ),
            minimum_trial_design_records=(
                1 if stage is Stage.CLINICAL_STRATEGY else 0
            ),
            minimum_confidence=0.6,
        )
    return gates


class GatedDiscoveryEnvironment:
    """Apply decision packets only when every blocking verifier passes."""

    def __init__(
        self,
        *,
        stage_sequence: Sequence[Stage] = DEFAULT_STAGE_SEQUENCE,
        stage_gates: Mapping[Stage, StageGate] | None = None,
        extra_verifiers: Sequence[TransitionVerifier] = (),
    ) -> None:
        self.stage_sequence = tuple(stage_sequence)
        if not self.stage_sequence or len(self.stage_sequence) != len(
            set(self.stage_sequence)
        ):
            raise ValueError("stage_sequence must be non-empty and unique")
        if any(not isinstance(stage, Stage) for stage in self.stage_sequence):
            raise TypeError("stage_sequence entries must be Stage values")
        resolved_gates = (
            default_stage_gates() if stage_gates is None else dict(stage_gates)
        )
        if any(not isinstance(stage, Stage) for stage in resolved_gates):
            raise TypeError("stage_gates keys must be Stage values")
        if any(not isinstance(gate, StageGate) for gate in resolved_gates.values()):
            raise TypeError("stage_gates values must be StageGate records")
        mismatched_gates = [
            stage for stage, gate in resolved_gates.items() if gate.stage is not stage
        ]
        if mismatched_gates:
            mismatch = ", ".join(sorted(item.value for item in mismatched_gates))
            raise ValueError(f"stage_gates keys do not match gate.stage: {mismatch}")
        missing_gates = set(self.stage_sequence) - set(resolved_gates)
        if missing_gates:
            missing = ", ".join(sorted(item.value for item in missing_gates))
            raise ValueError(f"stage_gates missing stages: {missing}")
        self.stage_gates = resolved_gates
        self.verifiers: tuple[TransitionVerifier, ...] = (
            PacketContextVerifier(),
            PacketIntegrityVerifier(),
            StageTransitionVerifier(self.stage_sequence),
            BudgetVerifier(),
            EvidenceChronologyVerifier(),
            EvidenceReferenceVerifier(),
            TargetIdentityContinuityVerifier(),
            ContextIdentityContinuityVerifier(),
            ClinicalIdentityContinuityVerifier(),
            ClinicalEndpointMappingContinuityVerifier(),
            ClinicalSynthesisContinuityVerifier(),
            ContradictionGateVerifier(),
            StageReadinessVerifier(self.stage_gates),
            *tuple(extra_verifiers),
        )

    def transition(
        self, state: ProgramState, packet: DecisionPacket
    ) -> TransitionResult:
        try:
            state.validate_committed_history()
        except Exception as exc:
            result = VerifierResult(
                verifier_id="input_state_integrity",
                kind=VerifierKind.DETERMINISTIC,
                status=VerifierStatus.FAIL,
                code="input_state_integrity_invalid",
                message="Input state failed committed-history validation; transition failed closed.",
                stage=state.current_stage,
                blocking=True,
                details={"exception_type": type(exc).__name__},
            )
            return TransitionResult(
                applied=False,
                state=state,
                packet=packet,
                verifier_results=(result,),
                reason="blocked:input_state_integrity_invalid",
            )
        try:
            proposed_state = self._project_content(state, packet)
        except Exception as exc:
            result = VerifierResult(
                verifier_id="state_projection",
                kind=VerifierKind.DETERMINISTIC,
                status=VerifierStatus.FAIL,
                code="state_projection_exception",
                message="Decision packet could not be projected; transition failed closed.",
                stage=state.current_stage,
                blocking=True,
                details={"exception_type": type(exc).__name__},
            )
            return TransitionResult(
                applied=False,
                state=state,
                packet=packet,
                verifier_results=(result,),
                reason="blocked:state_projection_exception",
            )
        results = tuple(
            self._run_verifier(verifier, state, packet, proposed_state)
            for verifier in self.verifiers
        )
        blocking = tuple(item for item in results if item.blocking)
        if blocking:
            return TransitionResult(
                applied=False,
                state=state,
                packet=packet,
                verifier_results=results,
                reason="blocked:" + ",".join(item.code for item in blocking),
            )

        try:
            next_stage, next_status = self._resolve_destination(state, packet)
            charged_budget = state.budget.charge(packet.action_cost)
            record = DecisionRecord(
                packet_id=packet.packet_id,
                decision=packet.decision,
                stage_before=state.current_stage,
                stage_after=next_stage,
                status_after=next_status,
                confidence=packet.confidence,
                rationale=packet.rationale,
                verifier_codes=tuple(item.code for item in results),
                verifier_result_start=len(state.verifier_history),
                verifier_result_count=len(results),
                action_ids=tuple(item.action_id for item in packet.actions),
                action_cost=packet.action_cost,
                created_at=packet.created_at,
            )
            committed = replace(
                proposed_state,
                current_stage=next_stage,
                budget=charged_budget,
                action_history=(*state.action_history, *packet.actions),
                packet_history=(*state.packet_history, packet),
                decision_history=(*state.decision_history, record),
                verifier_history=(*state.verifier_history, *results),
                status=next_status,
                version=state.version + 1,
            )
            committed.validate_committed_history()
        except Exception as exc:
            result = VerifierResult(
                verifier_id="state_commit",
                kind=VerifierKind.DETERMINISTIC,
                status=VerifierStatus.FAIL,
                code="state_commit_exception",
                message="Verified transition could not be committed; transition failed closed.",
                stage=state.current_stage,
                blocking=True,
                details={"exception_type": type(exc).__name__},
            )
            return TransitionResult(
                applied=False,
                state=state,
                packet=packet,
                verifier_results=(*results, result),
                reason="blocked:state_commit_exception",
            )
        return TransitionResult(
            applied=True,
            state=committed,
            packet=packet,
            verifier_results=results,
            reason="applied",
        )

    @staticmethod
    def _run_verifier(
        verifier: TransitionVerifier,
        state: ProgramState,
        packet: DecisionPacket,
        proposed_state: ProgramState,
    ) -> VerifierResult:
        fallback_id = type(verifier).__name__
        try:
            verifier_id = getattr(verifier, "verifier_id", fallback_id)
        except Exception:
            verifier_id = fallback_id
        if not isinstance(verifier_id, str) or not verifier_id.strip():
            verifier_id = fallback_id
        try:
            verifier_kind = getattr(verifier, "kind", VerifierKind.DETERMINISTIC)
        except Exception:
            verifier_kind = VerifierKind.DETERMINISTIC
        if not isinstance(verifier_kind, VerifierKind):
            verifier_kind = VerifierKind.DETERMINISTIC
        try:
            result = verifier.verify(state, packet, proposed_state)
        except Exception as exc:
            return VerifierResult(
                verifier_id=verifier_id,
                kind=verifier_kind,
                status=VerifierStatus.FAIL,
                code="verifier_exception",
                message="Verifier raised an exception; transition failed closed.",
                stage=state.current_stage,
                blocking=True,
                details={"exception_type": type(exc).__name__},
            )
        if not isinstance(result, VerifierResult):
            return VerifierResult(
                verifier_id=verifier_id,
                kind=verifier_kind,
                status=VerifierStatus.FAIL,
                code="verifier_contract_invalid",
                message="Verifier returned an invalid result; transition failed closed.",
                stage=state.current_stage,
                blocking=True,
                details={"return_type": type(result).__name__},
            )
        contract_failures: list[str] = []
        if result.verifier_id != verifier_id:
            contract_failures.append("verifier_id_mismatch")
        if result.kind is not verifier_kind:
            contract_failures.append("verifier_kind_mismatch")
        if result.stage is not state.current_stage:
            contract_failures.append("verifier_stage_mismatch")
        if verifier_kind is VerifierKind.DETERMINISTIC:
            if result.status is VerifierStatus.WARN:
                contract_failures.append("deterministic_verifier_cannot_warn")
            if result.status is VerifierStatus.FAIL and not result.blocking:
                contract_failures.append("deterministic_failure_must_block")
        if contract_failures:
            return VerifierResult(
                verifier_id=verifier_id,
                kind=verifier_kind,
                status=VerifierStatus.FAIL,
                code="verifier_contract_invalid",
                message="Verifier result violates its declared contract; transition failed closed.",
                stage=state.current_stage,
                blocking=True,
                details={"failures": contract_failures},
            )
        return result

    @staticmethod
    def _project_content(state: ProgramState, packet: DecisionPacket) -> ProgramState:
        evidence_by_id = state.evidence_by_id
        for evidence in packet.evidence_additions:
            if evidence.evidence_id not in evidence_by_id:
                evidence_by_id[evidence.evidence_id] = evidence

        claims = state.claims_by_id
        for claim in packet.claim_updates:
            claims[claim.claim_id] = claim

        diseases = state.diseases_by_id
        for disease in packet.disease_updates:
            diseases[disease.disease_id] = disease

        targets = state.targets_by_id
        for target in packet.target_updates:
            targets[target.target_id] = target

        candidates = state.candidates_by_id
        for candidate in packet.candidate_updates:
            candidates[candidate.candidate_id] = candidate

        assays = state.assays_by_id
        for assay in packet.assay_updates:
            assays[assay.assay_id] = assay

        model_systems = state.model_systems_by_id
        for model_system in packet.model_system_updates:
            model_systems[model_system.model_system_id] = model_system

        interventions = state.interventions_by_id
        for intervention in packet.intervention_updates:
            interventions[intervention.intervention_id] = intervention

        trials = state.trials_by_id
        for trial in packet.trial_updates:
            trials[trial.trial_id] = trial

        trial_designs = state.trial_designs_by_id
        for design in packet.trial_design_updates:
            trial_designs[design.design_id] = design

        clinical_endpoint_mappings = state.clinical_endpoint_mappings_by_id
        for mapping in packet.clinical_endpoint_mapping_updates:
            clinical_endpoint_mappings[mapping.mapping_id] = mapping

        benefit_risk_syntheses = state.benefit_risk_syntheses_by_id
        for synthesis in packet.benefit_risk_synthesis_updates:
            benefit_risk_syntheses[synthesis.synthesis_id] = synthesis

        return replace(
            state,
            evidence=tuple(evidence_by_id.values()),
            claims=tuple(claims.values()),
            diseases=tuple(diseases.values()),
            targets=tuple(targets.values()),
            candidates=tuple(candidates.values()),
            assays=tuple(assays.values()),
            model_systems=tuple(model_systems.values()),
            interventions=tuple(interventions.values()),
            trials=tuple(trials.values()),
            trial_designs=tuple(trial_designs.values()),
            clinical_endpoint_mappings=tuple(clinical_endpoint_mappings.values()),
            benefit_risk_syntheses=tuple(benefit_risk_syntheses.values()),
        )

    def _resolve_destination(
        self,
        state: ProgramState,
        packet: DecisionPacket,
    ) -> tuple[Stage, ProgramStatus]:
        if packet.decision is Decision.ADVANCE:
            if packet.next_stage is None:
                return state.current_stage, ProgramStatus.COMPLETED
            return packet.next_stage, ProgramStatus.ACTIVE
        if packet.decision is Decision.PIVOT:
            if packet.backtrack_stage is None:
                raise RuntimeError(
                    "pivot packet reached commit without a backtrack stage"
                )
            return packet.backtrack_stage, ProgramStatus.ACTIVE
        if packet.decision is Decision.HOLD:
            return state.current_stage, ProgramStatus.HELD
        if packet.decision is Decision.DEFER:
            return state.current_stage, ProgramStatus.DEFERRED
        return state.current_stage, ProgramStatus.TERMINATED
