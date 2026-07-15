"""Deterministic verifier contracts for discovery-stage transitions."""

from __future__ import annotations

from typing import Mapping, Protocol, Sequence

from .clinical_endpoint_mapping import validate_clinical_endpoint_mapping
from .clinical_synthesis import validate_benefit_risk_synthesis
from .models import (
    CandidateStatus,
    ClaimDisposition,
    Decision,
    DecisionPacket,
    DEFAULT_STAGE_SEQUENCE,
    EvidenceRelation,
    ProgramState,
    Stage,
    StageGate,
    TrialArmRole,
    VerifierKind,
    VerifierResult,
    VerifierStatus,
)


class TransitionVerifier(Protocol):
    verifier_id: str
    kind: VerifierKind

    def verify(
        self,
        state: ProgramState,
        packet: DecisionPacket,
        proposed_state: ProgramState,
    ) -> VerifierResult: ...


def _pass(
    verifier_id: str,
    stage: Stage,
    code: str,
    message: str,
    *,
    details: Mapping[str, object] | None = None,
) -> VerifierResult:
    return VerifierResult(
        verifier_id=verifier_id,
        kind=VerifierKind.DETERMINISTIC,
        status=VerifierStatus.PASS,
        code=code,
        message=message,
        stage=stage,
        details=details or {},
    )


def _fail(
    verifier_id: str,
    stage: Stage,
    code: str,
    message: str,
    *,
    details: Mapping[str, object] | None = None,
) -> VerifierResult:
    return VerifierResult(
        verifier_id=verifier_id,
        kind=VerifierKind.DETERMINISTIC,
        status=VerifierStatus.FAIL,
        code=code,
        message=message,
        stage=stage,
        blocking=True,
        details=details or {},
    )


def _is_sha256(value: str | None) -> bool:
    if value is None or len(value) != 64:
        return False
    try:
        int(value, 16)
    except ValueError:
        return False
    return value == value.lower()


class PacketContextVerifier:
    verifier_id = "packet_context"
    kind = VerifierKind.DETERMINISTIC

    def verify(
        self,
        state: ProgramState,
        packet: DecisionPacket,
        proposed_state: ProgramState,
    ) -> VerifierResult:
        failures: list[str] = []
        if packet.program_id != state.program_id:
            failures.append("program_id_mismatch")
        if packet.expected_state_version != state.version:
            failures.append("stale_state_version")
        if packet.stage is not state.current_stage:
            failures.append("stage_mismatch")
        if state.is_terminal:
            failures.append("terminal_state")
        if failures:
            return _fail(
                self.verifier_id,
                state.current_stage,
                "packet_context_invalid",
                "Decision packet does not match the current program state.",
                details={"failures": failures},
            )
        return _pass(
            self.verifier_id,
            state.current_stage,
            "packet_context_valid",
            "Decision packet targets the current program state.",
        )


class PacketIntegrityVerifier:
    verifier_id = "packet_integrity"
    kind = VerifierKind.DETERMINISTIC

    def verify(
        self,
        state: ProgramState,
        packet: DecisionPacket,
        proposed_state: ProgramState,
    ) -> VerifierResult:
        failures: list[str] = []
        if packet.packet_id in {item.packet_id for item in state.decision_history}:
            failures.append("duplicate_packet_id")
        existing_evidence = set(state.evidence_by_id)
        repeated_evidence = [
            item.evidence_id
            for item in packet.evidence_additions
            if item.evidence_id in existing_evidence
        ]
        if repeated_evidence:
            failures.append("evidence_id_already_exists")
        existing_actions = set(state.actions_by_id)
        repeated_actions = [
            item.action_id
            for item in packet.actions
            if item.action_id in existing_actions
        ]
        if repeated_actions:
            failures.append("action_id_already_exists")
        if failures:
            return _fail(
                self.verifier_id,
                state.current_stage,
                "packet_integrity_invalid",
                "Decision packet violates identifier integrity rules.",
                details={
                    "failures": failures,
                    "repeated_evidence": repeated_evidence,
                    "repeated_actions": repeated_actions,
                },
            )
        return _pass(
            self.verifier_id,
            state.current_stage,
            "packet_integrity_valid",
            "Decision packet identifiers are valid.",
        )


class StageTransitionVerifier:
    verifier_id = "stage_transition"
    kind = VerifierKind.DETERMINISTIC

    def __init__(
        self, stage_sequence: Sequence[Stage] = DEFAULT_STAGE_SEQUENCE
    ) -> None:
        self.stage_sequence = tuple(stage_sequence)
        if not self.stage_sequence or len(self.stage_sequence) != len(
            set(self.stage_sequence)
        ):
            raise ValueError("stage_sequence must be non-empty and unique")

    def verify(
        self,
        state: ProgramState,
        packet: DecisionPacket,
        proposed_state: ProgramState,
    ) -> VerifierResult:
        failures: list[str] = []
        try:
            index = self.stage_sequence.index(state.current_stage)
        except ValueError:
            return _fail(
                self.verifier_id,
                state.current_stage,
                "unknown_current_stage",
                "Current stage is absent from the environment stage sequence.",
            )

        expected_next = (
            self.stage_sequence[index + 1]
            if index + 1 < len(self.stage_sequence)
            else None
        )
        if packet.decision is Decision.ADVANCE:
            if packet.next_stage is not expected_next:
                failures.append("invalid_next_stage")
            if packet.backtrack_stage is not None:
                failures.append("advance_cannot_backtrack")
        elif packet.decision is Decision.PIVOT:
            if packet.next_stage is not None:
                failures.append("pivot_cannot_set_next_stage")
            if packet.backtrack_stage is None:
                failures.append("pivot_requires_backtrack_stage")
            elif packet.backtrack_stage not in self.stage_sequence:
                failures.append("unknown_backtrack_stage")
            elif self.stage_sequence.index(packet.backtrack_stage) >= index:
                failures.append("pivot_must_backtrack")
        elif packet.next_stage is not None or packet.backtrack_stage is not None:
            failures.append("terminal_or_pause_decision_cannot_move_stage")

        if failures:
            return _fail(
                self.verifier_id,
                state.current_stage,
                "stage_transition_invalid",
                "Requested stage movement is inconsistent with the decision.",
                details={
                    "failures": failures,
                    "expected_next_stage": expected_next.value
                    if expected_next
                    else None,
                },
            )
        return _pass(
            self.verifier_id,
            state.current_stage,
            "stage_transition_valid",
            "Requested stage movement is valid.",
            details={
                "expected_next_stage": expected_next.value if expected_next else None
            },
        )


class BudgetVerifier:
    verifier_id = "budget"
    kind = VerifierKind.DETERMINISTIC

    def verify(
        self,
        state: ProgramState,
        packet: DecisionPacket,
        proposed_state: ProgramState,
    ) -> VerifierResult:
        if not state.budget.can_afford(packet.action_cost):
            return _fail(
                self.verifier_id,
                state.current_stage,
                "budget_exceeded",
                "Decision packet exceeds the remaining action budget.",
                details={
                    "action_cost": packet.action_cost,
                    "remaining": state.budget.remaining,
                },
            )
        return _pass(
            self.verifier_id,
            state.current_stage,
            "budget_available",
            "Decision packet is within the remaining action budget.",
            details={
                "action_cost": packet.action_cost,
                "remaining": state.budget.remaining,
            },
        )


class EvidenceChronologyVerifier:
    verifier_id = "evidence_chronology"
    kind = VerifierKind.DETERMINISTIC

    def verify(
        self,
        state: ProgramState,
        packet: DecisionPacket,
        proposed_state: ProgramState,
    ) -> VerifierResult:
        future_ids = sorted(
            item.evidence_id
            for item in proposed_state.evidence
            if not item.is_visible_at(state.as_of_date)
        )
        if future_ids:
            return _fail(
                self.verifier_id,
                state.current_stage,
                "future_evidence_leak",
                "Evidence unavailable at the program cutoff cannot exist in the proposed state.",
                details={
                    "as_of_date": state.as_of_date.isoformat(),
                    "future_evidence_ids": future_ids,
                },
            )
        return _pass(
            self.verifier_id,
            state.current_stage,
            "evidence_within_cutoff",
            "All proposed-state evidence was available by the program cutoff.",
        )


class EvidenceReferenceVerifier:
    verifier_id = "evidence_references"
    kind = VerifierKind.DETERMINISTIC

    def verify(
        self,
        state: ProgramState,
        packet: DecisionPacket,
        proposed_state: ProgramState,
    ) -> VerifierResult:
        evidence_by_id = proposed_state.evidence_by_id
        known_ids = set(evidence_by_id)
        failures: list[str] = []
        missing_ids: set[str] = set()
        invalid_support_relations: set[str] = set()
        invalid_contradiction_relations: set[str] = set()

        for action in (*state.action_history, *packet.actions):
            missing_ids.update(set(action.evidence_ids) - known_ids)

        for claim in proposed_state.claims:
            support = set(claim.supporting_evidence)
            contradiction = set(claim.contradicting_evidence)
            missing_ids.update((support | contradiction) - known_ids)
            invalid_support_relations.update(
                evidence_id
                for evidence_id in support & known_ids
                if evidence_by_id[evidence_id].relation is not EvidenceRelation.SUPPORTS
            )
            invalid_contradiction_relations.update(
                evidence_id
                for evidence_id in contradiction & known_ids
                if evidence_by_id[evidence_id].relation
                is not EvidenceRelation.CONTRADICTS
            )
            if support & contradiction:
                failures.append(f"claim_reference_overlap:{claim.claim_id}")
            if claim.disposition is ClaimDisposition.SUPPORTED and not support:
                failures.append(f"supported_claim_without_support:{claim.claim_id}")
            if claim.disposition is ClaimDisposition.REJECTED and not contradiction:
                failures.append(
                    f"rejected_claim_without_contradiction:{claim.claim_id}"
                )
            if claim.disposition is ClaimDisposition.CONTESTED and not (
                support and contradiction
            ):
                failures.append(f"contested_claim_requires_both_sides:{claim.claim_id}")
            if (
                support
                and contradiction
                and claim.disposition is not ClaimDisposition.CONTESTED
            ):
                if not claim.resolution_rationale:
                    failures.append(f"conflict_without_resolution:{claim.claim_id}")

        supported_entities = (
            *proposed_state.diseases,
            *proposed_state.targets,
            *proposed_state.assays,
            *proposed_state.model_systems,
            *proposed_state.interventions,
            *proposed_state.trials,
            *proposed_state.trial_designs,
            *proposed_state.clinical_endpoint_mappings,
            *proposed_state.benefit_risk_syntheses,
            *(
                item
                for design in proposed_state.trial_designs
                for item in design.arms
            ),
            *(
                item
                for design in proposed_state.trial_designs
                for item in design.populations
            ),
            *(
                item
                for design in proposed_state.trial_designs
                for item in design.endpoints
            ),
            *(
                item
                for design in proposed_state.trial_designs
                for item in design.safety_records
            ),
            *(
                summary
                for design in proposed_state.trial_designs
                for safety in design.safety_records
                for summary in safety.arm_summaries
            ),
        )
        for entity in supported_entities:
            support = set(entity.supporting_evidence)
            missing_ids.update(support - known_ids)
            invalid_support_relations.update(
                evidence_id
                for evidence_id in support & known_ids
                if evidence_by_id[evidence_id].relation is not EvidenceRelation.SUPPORTS
            )

        if missing_ids:
            failures.append("unknown_evidence_reference")
        if invalid_support_relations:
            failures.append("support_reference_has_non_support_relation")
        if invalid_contradiction_relations:
            failures.append("contradiction_reference_has_non_contradict_relation")
        if failures:
            return _fail(
                self.verifier_id,
                state.current_stage,
                "evidence_reference_invalid",
                "Claims, identity records, or actions contain invalid evidence references.",
                details={
                    "failures": failures,
                    "missing_evidence_ids": sorted(missing_ids),
                    "invalid_support_relation_ids": sorted(invalid_support_relations),
                    "invalid_contradiction_relation_ids": sorted(
                        invalid_contradiction_relations
                    ),
                },
            )
        return _pass(
            self.verifier_id,
            state.current_stage,
            "evidence_references_valid",
            "Claims, identity records, and actions reference available evidence records.",
        )


class TargetIdentityContinuityVerifier:
    """Prevent target namespace rebinding and broken candidate-target links."""

    verifier_id = "target_identity_continuity"
    kind = VerifierKind.DETERMINISTIC
    _CANDIDATE_LINK_FIELDS = (
        "target_record_id",
        "target_chembl_id",
        "target_symbol",
        "disease_id",
    )

    @staticmethod
    def _normalized(value: str) -> str:
        return " ".join(value.casefold().split())

    def verify(
        self,
        state: ProgramState,
        packet: DecisionPacket,
        proposed_state: ProgramState,
    ) -> VerifierResult:
        failures: list[str] = []
        conflicting_bindings: list[str] = []
        broken_candidates: list[str] = []

        for target_id, previous in state.targets_by_id.items():
            current = proposed_state.targets_by_id.get(target_id)
            if current is None:
                failures.append(f"target_removed:{target_id}")
                continue
            if (
                current.symbol != previous.symbol
                or current.disease_id != previous.disease_id
                or current.organism != previous.organism
            ):
                failures.append(f"target_core_identity_rebound:{target_id}")
            for namespace, value in previous.identifiers.items():
                if current.identifiers.get(namespace) != value:
                    failures.append(
                        f"target_namespace_rebound:{target_id}:{namespace}"
                    )
            if not set(previous.supporting_evidence).issubset(
                current.supporting_evidence
            ):
                failures.append(f"target_support_removed:{target_id}")

        for update in packet.target_updates:
            if update.stage is not state.current_stage:
                failures.append(f"target_update_stage_mismatch:{update.target_id}")

        owner_by_binding: dict[tuple[str, str], str] = {}
        for target in proposed_state.targets:
            ensembl_gene = target.identifiers.get("ensembl_gene")
            gene_symbol = target.identifiers.get("gene_symbol")
            if ensembl_gene is not None and ensembl_gene != target.target_id:
                failures.append(f"target_canonical_id_mismatch:{target.target_id}")
            if gene_symbol is not None and self._normalized(
                gene_symbol
            ) != self._normalized(target.symbol):
                failures.append(f"target_symbol_binding_mismatch:{target.target_id}")
            for namespace, value in target.identifiers.items():
                binding = (self._normalized(namespace), self._normalized(value))
                owner = owner_by_binding.get(binding)
                if owner is not None and owner != target.target_id:
                    conflicting_bindings.append(f"{namespace}:{value}")
                else:
                    owner_by_binding[binding] = target.target_id

        for candidate in proposed_state.candidates:
            attributes = candidate.attributes
            present = [field for field in self._CANDIDATE_LINK_FIELDS if field in attributes]
            if not present:
                continue
            if len(present) != len(self._CANDIDATE_LINK_FIELDS):
                broken_candidates.append(candidate.candidate_id)
                continue
            values = {field: attributes[field] for field in self._CANDIDATE_LINK_FIELDS}
            if any(not isinstance(value, str) or not value.strip() for value in values.values()):
                broken_candidates.append(candidate.candidate_id)
                continue
            target = proposed_state.targets_by_id.get(values["target_record_id"])
            if target is None or (
                target.identifiers.get("chembl_target") != values["target_chembl_id"]
                or target.symbol != values["target_symbol"]
                or target.disease_id != values["disease_id"]
            ):
                broken_candidates.append(candidate.candidate_id)

        if conflicting_bindings:
            failures.append("target_namespace_collision")
        if broken_candidates:
            failures.append("candidate_target_link_invalid")
        if failures:
            return _fail(
                self.verifier_id,
                state.current_stage,
                "target_identity_continuity_invalid",
                "Target identifiers or candidate-target links violate continuity rules.",
                details={
                    "failures": sorted(set(failures)),
                    "conflicting_bindings": sorted(set(conflicting_bindings)),
                    "broken_candidate_ids": sorted(set(broken_candidates)),
                },
            )
        return _pass(
            self.verifier_id,
            state.current_stage,
            "target_identity_continuity_valid",
            "Target namespace bindings and candidate links preserve identity continuity.",
        )


class ContextIdentityContinuityVerifier:
    """Preserve disease, assay, and model-system identity across replayed stages."""

    verifier_id = "context_identity_continuity"
    kind = VerifierKind.DETERMINISTIC

    @staticmethod
    def _normalized(value: str) -> str:
        return " ".join(value.casefold().split())

    def _same(self, left: object, right: str) -> bool:
        return isinstance(left, str) and self._normalized(left) == self._normalized(
            right
        )

    def _continuity_failures(
        self,
        *,
        kind: str,
        id_field: str,
        core_fields: tuple[str, ...],
        previous_by_id: Mapping[str, object],
        current_by_id: Mapping[str, object],
    ) -> list[str]:
        failures: list[str] = []
        for entity_id, previous in previous_by_id.items():
            current = current_by_id.get(entity_id)
            if current is None:
                failures.append(f"{kind}_removed:{entity_id}")
                continue
            if any(
                getattr(current, field_name) != getattr(previous, field_name)
                for field_name in core_fields
            ):
                failures.append(f"{kind}_core_identity_rebound:{entity_id}")
            for namespace, value in previous.identifiers.items():
                if current.identifiers.get(namespace) != value:
                    failures.append(
                        f"{kind}_namespace_rebound:{entity_id}:{namespace}"
                    )
            if not set(previous.supporting_evidence).issubset(
                current.supporting_evidence
            ):
                failures.append(f"{kind}_support_removed:{entity_id}")
            if getattr(current, id_field) != entity_id:
                failures.append(f"{kind}_ledger_key_mismatch:{entity_id}")
        return failures

    def _namespace_collisions(
        self,
        *,
        records: tuple[object, ...],
        id_field: str,
    ) -> list[str]:
        owner_by_binding: dict[tuple[str, str], str] = {}
        collisions: list[str] = []
        for record in records:
            record_id = getattr(record, id_field)
            for namespace, value in record.identifiers.items():
                binding = (self._normalized(namespace), self._normalized(value))
                owner = owner_by_binding.get(binding)
                if owner is not None and owner != record_id:
                    collisions.append(f"{namespace}:{value}")
                else:
                    owner_by_binding[binding] = record_id
        return collisions

    def verify(
        self,
        state: ProgramState,
        packet: DecisionPacket,
        proposed_state: ProgramState,
    ) -> VerifierResult:
        failures: list[str] = []
        broken_assays: list[str] = []
        broken_model_systems: list[str] = []
        conflicting_bindings: list[str] = []

        failures.extend(
            self._continuity_failures(
                kind="disease",
                id_field="disease_id",
                core_fields=("name",),
                previous_by_id=state.diseases_by_id,
                current_by_id=proposed_state.diseases_by_id,
            )
        )
        failures.extend(
            self._continuity_failures(
                kind="assay",
                id_field="assay_id",
                core_fields=(
                    "name",
                    "assay_type",
                    "target_id",
                    "disease_id",
                    "organism",
                ),
                previous_by_id=state.assays_by_id,
                current_by_id=proposed_state.assays_by_id,
            )
        )
        failures.extend(
            self._continuity_failures(
                kind="model_system",
                id_field="model_system_id",
                core_fields=("name", "model_type", "disease_id", "organism"),
                previous_by_id=state.model_systems_by_id,
                current_by_id=proposed_state.model_systems_by_id,
            )
        )

        for kind, updates, id_field in (
            ("disease", packet.disease_updates, "disease_id"),
            ("assay", packet.assay_updates, "assay_id"),
            ("model_system", packet.model_system_updates, "model_system_id"),
        ):
            for update in updates:
                if update.stage is not state.current_stage:
                    failures.append(
                        f"{kind}_update_stage_mismatch:{getattr(update, id_field)}"
                    )

        if len(proposed_state.diseases) > 1:
            failures.append("program_disease_identity_ambiguous")
        disease_ids = set(proposed_state.diseases_by_id)
        evidence_by_id = proposed_state.evidence_by_id
        candidate_by_id = proposed_state.candidates_by_id

        for disease in proposed_state.diseases:
            if not self._same(disease.name, proposed_state.disease):
                failures.append(f"program_disease_name_mismatch:{disease.disease_id}")
            if disease.identifiers.get("canonical") != disease.disease_id:
                failures.append(f"disease_canonical_id_mismatch:{disease.disease_id}")
            if not disease.supporting_evidence or any(
                evidence_id not in evidence_by_id
                or not self._same(
                    evidence_by_id[evidence_id].biological_context.get("disease_id"),
                    disease.disease_id,
                )
                for evidence_id in disease.supporting_evidence
            ):
                failures.append(f"disease_evidence_link_invalid:{disease.disease_id}")

        for target in proposed_state.targets:
            if disease_ids and target.disease_id not in disease_ids:
                failures.append(f"target_disease_link_invalid:{target.target_id}")
        for candidate in proposed_state.candidates:
            disease_id = candidate.attributes.get("disease_id")
            if disease_ids and disease_id is not None and disease_id not in disease_ids:
                failures.append(
                    f"candidate_disease_link_invalid:{candidate.candidate_id}"
                )

        for assay in proposed_state.assays:
            target = proposed_state.targets_by_id.get(assay.target_id)
            if assay.identifiers.get("canonical") != assay.assay_id:
                broken_assays.append(assay.assay_id)
            if (
                target is None
                or assay.disease_id not in disease_ids
                or target.disease_id != assay.disease_id
                or self._normalized(target.organism)
                != self._normalized(assay.organism)
            ):
                broken_assays.append(assay.assay_id)
                continue
            linked = False
            for evidence_id in assay.supporting_evidence:
                evidence = evidence_by_id.get(evidence_id)
                if evidence is None:
                    continue
                context = evidence.biological_context
                candidate_id = context.get("candidate_id")
                candidate = (
                    candidate_by_id.get(candidate_id)
                    if isinstance(candidate_id, str)
                    else None
                )
                if (
                    evidence.predicate
                    == "candidate_target_functional_activity_supported"
                    and self._same(context.get("assay_id"), assay.assay_id)
                    and self._same(context.get("target_record_id"), assay.target_id)
                    and self._same(context.get("disease_id"), assay.disease_id)
                    and self._same(context.get("organism"), assay.organism)
                    and candidate is not None
                    and candidate.attributes.get("target_record_id") == assay.target_id
                    and candidate.attributes.get("disease_id") == assay.disease_id
                ):
                    linked = True
                    break
            if not linked:
                broken_assays.append(assay.assay_id)

        for model_system in proposed_state.model_systems:
            if (
                model_system.identifiers.get("canonical")
                != model_system.model_system_id
                or model_system.disease_id not in disease_ids
            ):
                broken_model_systems.append(model_system.model_system_id)
                continue
            linked = False
            for evidence_id in model_system.supporting_evidence:
                evidence = evidence_by_id.get(evidence_id)
                if evidence is None:
                    continue
                context = evidence.biological_context
                candidate_id = context.get("candidate_id")
                candidate = (
                    candidate_by_id.get(candidate_id)
                    if isinstance(candidate_id, str)
                    else None
                )
                if (
                    evidence.predicate == "disease_model_effect_supported"
                    and self._same(
                        context.get("model_system_id"),
                        model_system.model_system_id,
                    )
                    and self._same(
                        context.get("disease_id"), model_system.disease_id
                    )
                    and self._same(context.get("organism"), model_system.organism)
                    and candidate is not None
                    and candidate.attributes.get("disease_id")
                    == model_system.disease_id
                ):
                    linked = True
                    break
            if not linked:
                broken_model_systems.append(model_system.model_system_id)

        for kind, records, id_field in (
            ("disease", proposed_state.diseases, "disease_id"),
            ("assay", proposed_state.assays, "assay_id"),
            ("model_system", proposed_state.model_systems, "model_system_id"),
        ):
            collisions = self._namespace_collisions(
                records=records,
                id_field=id_field,
            )
            if collisions:
                failures.append(f"{kind}_namespace_collision")
                conflicting_bindings.extend(f"{kind}:{item}" for item in collisions)

        if broken_assays:
            failures.append("assay_identity_link_invalid")
        if broken_model_systems:
            failures.append("model_system_identity_link_invalid")
        if failures:
            return _fail(
                self.verifier_id,
                state.current_stage,
                "context_identity_continuity_invalid",
                "Disease, assay, or model-system identity violates continuity rules.",
                details={
                    "failures": sorted(set(failures)),
                    "conflicting_bindings": sorted(set(conflicting_bindings)),
                    "broken_assay_ids": sorted(set(broken_assays)),
                    "broken_model_system_ids": sorted(set(broken_model_systems)),
                },
            )
        return _pass(
            self.verifier_id,
            state.current_stage,
            "context_identity_continuity_valid",
            "Disease, assay, and model-system identities preserve continuity.",
        )


class ClinicalIdentityContinuityVerifier:
    """Preserve candidate-to-intervention-to-trial identity across clinical stages."""

    verifier_id = "clinical_identity_continuity"
    kind = VerifierKind.DETERMINISTIC

    @staticmethod
    def _normalized(value: str) -> str:
        return " ".join(value.casefold().split())

    def _same(self, left: object, right: str) -> bool:
        return isinstance(left, str) and self._normalized(left) == self._normalized(
            right
        )

    def _continuity_failures(
        self,
        *,
        kind: str,
        id_field: str,
        core_fields: tuple[str, ...],
        previous_by_id: Mapping[str, object],
        current_by_id: Mapping[str, object],
    ) -> list[str]:
        failures: list[str] = []
        for entity_id, previous in previous_by_id.items():
            current = current_by_id.get(entity_id)
            if current is None:
                failures.append(f"{kind}_removed:{entity_id}")
                continue
            if any(
                getattr(current, field_name) != getattr(previous, field_name)
                for field_name in core_fields
            ):
                failures.append(f"{kind}_core_identity_rebound:{entity_id}")
            for namespace, value in previous.identifiers.items():
                if current.identifiers.get(namespace) != value:
                    failures.append(
                        f"{kind}_namespace_rebound:{entity_id}:{namespace}"
                    )
            if not set(previous.supporting_evidence).issubset(
                current.supporting_evidence
            ):
                failures.append(f"{kind}_support_removed:{entity_id}")
        return failures

    def _namespace_collisions(
        self,
        records: tuple[object, ...],
        *,
        id_field: str,
        scope_field: str | None = None,
        scoped_namespaces: tuple[str, ...] = (),
    ) -> list[str]:
        owners: dict[tuple[str, str, str], str] = {}
        collisions: list[str] = []
        normalized_scoped_namespaces = {
            self._normalized(item) for item in scoped_namespaces
        }
        for record in records:
            record_id = getattr(record, id_field)
            for namespace, value in record.identifiers.items():
                normalized_namespace = self._normalized(namespace)
                scope = (
                    self._normalized(str(getattr(record, scope_field)))
                    if scope_field is not None
                    and normalized_namespace in normalized_scoped_namespaces
                    else "global"
                )
                binding = (
                    scope,
                    normalized_namespace,
                    self._normalized(value),
                )
                owner = owners.get(binding)
                if owner is not None and owner != record_id:
                    collisions.append(f"{namespace}:{value}")
                else:
                    owners[binding] = record_id
        return collisions

    def verify(
        self,
        state: ProgramState,
        packet: DecisionPacket,
        proposed_state: ProgramState,
    ) -> VerifierResult:
        failures: list[str] = []
        broken_interventions: list[str] = []
        broken_trials: list[str] = []
        broken_designs: list[str] = []
        broken_arms: list[str] = []
        broken_populations: list[str] = []
        broken_endpoints: list[str] = []
        broken_safety_records: list[str] = []
        broken_safety_arms: list[str] = []
        conflicting_bindings: list[str] = []

        failures.extend(
            self._continuity_failures(
                kind="intervention",
                id_field="intervention_id",
                core_fields=("name", "candidate_id", "disease_id", "modality"),
                previous_by_id=state.interventions_by_id,
                current_by_id=proposed_state.interventions_by_id,
            )
        )
        failures.extend(
            self._continuity_failures(
                kind="trial",
                id_field="trial_id",
                core_fields=("registry", "intervention_id", "disease_id"),
                previous_by_id=state.trials_by_id,
                current_by_id=proposed_state.trials_by_id,
            )
        )
        failures.extend(
            self._continuity_failures(
                kind="trial_design",
                id_field="design_id",
                core_fields=("trial_id", "intervention_id", "disease_id"),
                previous_by_id=state.trial_designs_by_id,
                current_by_id=proposed_state.trial_designs_by_id,
            )
        )
        nested_groups = (
            (
                "trial_arm",
                "arm_id",
                (
                    "trial_id",
                    "label",
                    "arm_type",
                    "role",
                    "intervention_id",
                    "intervention_names",
                ),
                tuple(item for design in state.trial_designs for item in design.arms),
                tuple(
                    item for design in proposed_state.trial_designs for item in design.arms
                ),
            ),
            (
                "trial_population",
                "population_id",
                (
                    "trial_id",
                    "disease_id",
                    "description",
                    "enrollment_count",
                    "enrollment_type",
                    "sex",
                    "minimum_age",
                    "maximum_age",
                    "healthy_volunteers",
                ),
                tuple(
                    item for design in state.trial_designs for item in design.populations
                ),
                tuple(
                    item
                    for design in proposed_state.trial_designs
                    for item in design.populations
                ),
            ),
            (
                "trial_endpoint",
                "endpoint_id",
                (
                    "trial_id",
                    "population_id",
                    "name",
                    "outcome_type",
                    "time_frame",
                    "parameter_type",
                    "unit",
                    "reporting_status",
                    "arm_ids",
                ),
                tuple(
                    item for design in state.trial_designs for item in design.endpoints
                ),
                tuple(
                    item
                    for design in proposed_state.trial_designs
                    for item in design.endpoints
                ),
            ),
            (
                "trial_safety",
                "safety_id",
                (
                    "trial_id",
                    "event_category",
                    "reporting_status",
                    "time_frame",
                    "event_term_count",
                    "description",
                ),
                tuple(
                    item
                    for design in state.trial_designs
                    for item in design.safety_records
                ),
                tuple(
                    item
                    for design in proposed_state.trial_designs
                    for item in design.safety_records
                ),
            ),
            (
                "trial_safety_arm",
                "safety_arm_id",
                (
                    "safety_id",
                    "trial_id",
                    "arm_id",
                    "role",
                    "source_group_id",
                    "source_group_title",
                    "serious_num_affected",
                    "serious_num_at_risk",
                ),
                tuple(
                    summary
                    for design in state.trial_designs
                    for safety in design.safety_records
                    for summary in safety.arm_summaries
                ),
                tuple(
                    summary
                    for design in proposed_state.trial_designs
                    for safety in design.safety_records
                    for summary in safety.arm_summaries
                ),
            ),
        )
        for kind, id_field, core_fields, previous_records, current_records in nested_groups:
            failures.extend(
                self._continuity_failures(
                    kind=kind,
                    id_field=id_field,
                    core_fields=core_fields,
                    previous_by_id={
                        getattr(item, id_field): item for item in previous_records
                    },
                    current_by_id={
                        getattr(item, id_field): item for item in current_records
                    },
                )
            )
        for kind, updates, id_field in (
            ("intervention", packet.intervention_updates, "intervention_id"),
            ("trial", packet.trial_updates, "trial_id"),
            ("trial_design", packet.trial_design_updates, "design_id"),
        ):
            for update in updates:
                if update.stage is not state.current_stage:
                    failures.append(
                        f"{kind}_update_stage_mismatch:{getattr(update, id_field)}"
                    )

        disease_ids = set(proposed_state.diseases_by_id)
        candidates = proposed_state.candidates_by_id
        evidence = proposed_state.evidence_by_id
        intervention_owner_by_candidate: dict[str, str] = {}
        for intervention in proposed_state.interventions:
            candidate = candidates.get(intervention.candidate_id)
            previous_owner = intervention_owner_by_candidate.get(
                intervention.candidate_id
            )
            if (
                previous_owner is not None
                and previous_owner != intervention.intervention_id
            ):
                failures.append(
                    f"candidate_intervention_ambiguous:{intervention.candidate_id}"
                )
            intervention_owner_by_candidate[intervention.candidate_id] = (
                intervention.intervention_id
            )
            if (
                intervention.identifiers.get("canonical")
                != intervention.intervention_id
                or candidate is None
                or intervention.disease_id not in disease_ids
                or candidate.attributes.get("disease_id") != intervention.disease_id
                or self._normalized(candidate.modality)
                != self._normalized(intervention.modality)
                or not intervention.supporting_evidence
            ):
                broken_interventions.append(intervention.intervention_id)
                continue
            for evidence_id in intervention.supporting_evidence:
                item = evidence.get(evidence_id)
                context = item.biological_context if item is not None else {}
                if (
                    item is None
                    or item.predicate
                    not in {
                        "clinical_trial_identity_resolved",
                        "clinical_evidence_assessed",
                        "clinical_safety_assessed",
                        "regulatory_status_assessed",
                    }
                    or not self._same(
                        context.get("intervention_id"),
                        intervention.intervention_id,
                    )
                    or not self._same(
                        context.get("candidate_id"), intervention.candidate_id
                    )
                    or not self._same(
                        context.get("disease_id"), intervention.disease_id
                    )
                ):
                    broken_interventions.append(intervention.intervention_id)
                    break

        for trial in proposed_state.trials:
            intervention = proposed_state.interventions_by_id.get(
                trial.intervention_id
            )
            if (
                trial.identifiers.get("canonical") != trial.trial_id
                or trial.identifiers.get("clinicaltrials_gov") != trial.trial_id
                or self._normalized(trial.registry) != "clinicaltrials.gov"
                or intervention is None
                or trial.disease_id != intervention.disease_id
                or not trial.supporting_evidence
            ):
                broken_trials.append(trial.trial_id)
                continue
            for evidence_id in trial.supporting_evidence:
                item = evidence.get(evidence_id)
                context = item.biological_context if item is not None else {}
                if (
                    item is None
                    or item.predicate
                    not in {
                        "clinical_trial_identity_resolved",
                        "clinical_evidence_assessed",
                        "clinical_safety_assessed",
                    }
                    or not self._same(context.get("trial_id"), trial.trial_id)
                    or not self._same(
                        context.get("intervention_id"), trial.intervention_id
                    )
                    or not self._same(
                        context.get("candidate_id"), intervention.candidate_id
                    )
                    or not self._same(context.get("disease_id"), trial.disease_id)
                ):
                    broken_trials.append(trial.trial_id)
                    break

        allowed_design_predicates = {
            "clinical_trial_identity_resolved",
            "clinical_trial_arm_identity_resolved",
            "clinical_trial_population_identity_resolved",
            "clinical_trial_endpoint_identity_resolved",
            "clinical_trial_safety_identity_resolved",
            "clinical_evidence_assessed",
            "clinical_safety_assessed",
        }
        for design in proposed_state.trial_designs:
            trial = proposed_state.trials_by_id.get(design.trial_id)
            intervention = proposed_state.interventions_by_id.get(
                design.intervention_id
            )
            if (
                design.identifiers.get("canonical") != design.design_id
                or trial is None
                or intervention is None
                or trial.intervention_id != design.intervention_id
                or trial.disease_id != design.disease_id
                or intervention.disease_id != design.disease_id
                or len(design.arms) < 2
                or {arm.role for arm in design.arms}
                != {TrialArmRole.CANDIDATE, TrialArmRole.COMPARATOR}
                or not design.supporting_evidence
                or not design.safety_records
            ):
                broken_designs.append(design.design_id)
                continue
            for evidence_id in design.supporting_evidence:
                item = evidence.get(evidence_id)
                context = item.biological_context if item is not None else {}
                if (
                    item is None
                    or item.predicate not in allowed_design_predicates
                    or not self._same(context.get("design_id"), design.design_id)
                    or not self._same(context.get("trial_id"), design.trial_id)
                    or not self._same(
                        context.get("intervention_id"), design.intervention_id
                    )
                    or not self._same(context.get("disease_id"), design.disease_id)
                    or not self._same(
                        context.get("candidate_id"), intervention.candidate_id
                    )
                ):
                    broken_designs.append(design.design_id)
                    break

            for arm in design.arms:
                if (
                    arm.identifiers.get("canonical") != arm.arm_id
                    or not arm.identifiers.get("clinicaltrials_gov_group")
                    or not arm.supporting_evidence
                    or (
                        arm.role is TrialArmRole.CANDIDATE
                        and arm.intervention_id != design.intervention_id
                    )
                    or (
                        arm.role is TrialArmRole.COMPARATOR
                        and arm.intervention_id == design.intervention_id
                    )
                    or (
                        arm.intervention_id is not None
                        and arm.intervention_id != design.intervention_id
                    )
                ):
                    broken_arms.append(arm.arm_id)
                    continue
                for evidence_id in arm.supporting_evidence:
                    item = evidence.get(evidence_id)
                    context = item.biological_context if item is not None else {}
                    if (
                        item is None
                        or item.predicate != "clinical_trial_arm_identity_resolved"
                        or not self._same(context.get("arm_id"), arm.arm_id)
                        or not self._same(context.get("design_id"), design.design_id)
                        or not self._same(context.get("trial_id"), design.trial_id)
                    ):
                        broken_arms.append(arm.arm_id)
                        break

            for population in design.populations:
                if (
                    population.identifiers.get("canonical")
                    != population.population_id
                    or population.disease_id != design.disease_id
                    or not population.supporting_evidence
                ):
                    broken_populations.append(population.population_id)
                    continue
                for evidence_id in population.supporting_evidence:
                    item = evidence.get(evidence_id)
                    context = item.biological_context if item is not None else {}
                    if (
                        item is None
                        or item.predicate
                        != "clinical_trial_population_identity_resolved"
                        or not self._same(
                            context.get("population_id"), population.population_id
                        )
                        or not self._same(
                            context.get("design_id"), design.design_id
                        )
                        or not self._same(context.get("trial_id"), design.trial_id)
                    ):
                        broken_populations.append(population.population_id)
                        break

            arm_ids = {item.arm_id for item in design.arms}
            population_ids = {item.population_id for item in design.populations}
            for endpoint in design.endpoints:
                if (
                    endpoint.identifiers.get("canonical") != endpoint.endpoint_id
                    or endpoint.population_id not in population_ids
                    or not set(endpoint.arm_ids).issubset(arm_ids)
                    or len(endpoint.arm_ids) < 2
                    or not endpoint.supporting_evidence
                ):
                    broken_endpoints.append(endpoint.endpoint_id)
                    continue
                endpoint_predicates: set[str] = set()
                for evidence_id in endpoint.supporting_evidence:
                    item = evidence.get(evidence_id)
                    context = item.biological_context if item is not None else {}
                    if item is not None:
                        endpoint_predicates.add(item.predicate)
                    if (
                        item is None
                        or item.predicate
                        not in {
                            "clinical_trial_endpoint_identity_resolved",
                            "clinical_evidence_assessed",
                        }
                        or not self._same(
                            context.get("endpoint_id"), endpoint.endpoint_id
                        )
                        or not self._same(
                            context.get("population_id"), endpoint.population_id
                        )
                        or not self._same(
                            context.get("design_id"), design.design_id
                        )
                        or not self._same(context.get("trial_id"), design.trial_id)
                    ):
                        broken_endpoints.append(endpoint.endpoint_id)
                        break
                if endpoint_predicates != {
                    "clinical_trial_endpoint_identity_resolved",
                    "clinical_evidence_assessed",
                }:
                    broken_endpoints.append(endpoint.endpoint_id)

            arm_roles = {item.arm_id: item.role for item in design.arms}
            for safety in design.safety_records:
                safety_predicates: set[str] = set()
                safety_arm_ids = {item.arm_id for item in safety.arm_summaries}
                if (
                    safety.identifiers.get("canonical") != safety.safety_id
                    or safety.identifiers.get("clinicaltrials_gov")
                    != design.trial_id
                    or safety.trial_id != design.trial_id
                    or self._normalized(safety.event_category) != "serious"
                    or self._normalized(safety.reporting_status) != "posted"
                    or safety_arm_ids != arm_ids
                    or not safety.supporting_evidence
                ):
                    broken_safety_records.append(safety.safety_id)
                    continue
                for evidence_id in safety.supporting_evidence:
                    item = evidence.get(evidence_id)
                    context = item.biological_context if item is not None else {}
                    if item is not None:
                        safety_predicates.add(item.predicate)
                    context_arm_ids = context.get("arm_ids")
                    if (
                        item is None
                        or item.predicate
                        not in {
                            "clinical_trial_safety_identity_resolved",
                            "clinical_safety_assessed",
                        }
                        or not self._same(
                            context.get("safety_id"), safety.safety_id
                        )
                        or not self._same(context.get("design_id"), design.design_id)
                        or not self._same(context.get("trial_id"), design.trial_id)
                        or not isinstance(context_arm_ids, tuple)
                        or set(context_arm_ids) != arm_ids
                    ):
                        broken_safety_records.append(safety.safety_id)
                        break
                if safety_predicates != {
                    "clinical_trial_safety_identity_resolved",
                    "clinical_safety_assessed",
                }:
                    broken_safety_records.append(safety.safety_id)

                for summary in safety.arm_summaries:
                    if (
                        summary.identifiers.get("canonical")
                        != summary.safety_arm_id
                        or summary.identifiers.get(
                            "clinicaltrials_gov_adverse_event_group"
                        )
                        != summary.source_group_id
                        or summary.safety_id != safety.safety_id
                        or summary.trial_id != design.trial_id
                        or arm_roles.get(summary.arm_id) is not summary.role
                        or not summary.supporting_evidence
                    ):
                        broken_safety_arms.append(summary.safety_arm_id)
                        continue
                    summary_predicates: set[str] = set()
                    for evidence_id in summary.supporting_evidence:
                        item = evidence.get(evidence_id)
                        context = item.biological_context if item is not None else {}
                        if item is not None:
                            summary_predicates.add(item.predicate)
                        context_arm_ids = context.get("arm_ids")
                        if (
                            item is None
                            or item.predicate
                            not in {
                                "clinical_trial_safety_identity_resolved",
                                "clinical_safety_assessed",
                            }
                            or not self._same(
                                context.get("safety_id"), safety.safety_id
                            )
                            or not isinstance(context_arm_ids, tuple)
                            or summary.arm_id not in context_arm_ids
                        ):
                            broken_safety_arms.append(summary.safety_arm_id)
                            break
                    if summary_predicates != {
                        "clinical_trial_safety_identity_resolved",
                        "clinical_safety_assessed",
                    }:
                        broken_safety_arms.append(summary.safety_arm_id)

        for kind, records, id_field, scope_field, scoped_namespaces in (
            (
                "intervention",
                proposed_state.interventions,
                "intervention_id",
                None,
                (),
            ),
            ("trial", proposed_state.trials, "trial_id", None, ()),
            (
                "trial_design",
                proposed_state.trial_designs,
                "design_id",
                None,
                (),
            ),
            (
                "trial_arm",
                tuple(
                    item
                    for design in proposed_state.trial_designs
                    for item in design.arms
                ),
                "arm_id",
                "trial_id",
                ("clinicaltrials_gov_group",),
            ),
            (
                "trial_population",
                tuple(
                    item
                    for design in proposed_state.trial_designs
                    for item in design.populations
                ),
                "population_id",
                None,
                (),
            ),
            (
                "trial_endpoint",
                tuple(
                    item
                    for design in proposed_state.trial_designs
                    for item in design.endpoints
                ),
                "endpoint_id",
                None,
                (),
            ),
            (
                "trial_safety",
                tuple(
                    item
                    for design in proposed_state.trial_designs
                    for item in design.safety_records
                ),
                "safety_id",
                None,
                (),
            ),
            (
                "trial_safety_arm",
                tuple(
                    summary
                    for design in proposed_state.trial_designs
                    for safety in design.safety_records
                    for summary in safety.arm_summaries
                ),
                "safety_arm_id",
                "trial_id",
                ("clinicaltrials_gov_adverse_event_group",),
            ),
        ):
            collisions = self._namespace_collisions(
                records,
                id_field=id_field,
                scope_field=scope_field,
                scoped_namespaces=scoped_namespaces,
            )
            if collisions:
                failures.append(f"{kind}_namespace_collision")
                conflicting_bindings.extend(f"{kind}:{item}" for item in collisions)

        if broken_interventions:
            failures.append("intervention_identity_link_invalid")
        if broken_trials:
            failures.append("trial_identity_link_invalid")
        if broken_designs:
            failures.append("trial_design_identity_link_invalid")
        if broken_arms:
            failures.append("trial_arm_identity_link_invalid")
        if broken_populations:
            failures.append("trial_population_identity_link_invalid")
        if broken_endpoints:
            failures.append("trial_endpoint_identity_link_invalid")
        if broken_safety_records:
            failures.append("trial_safety_identity_link_invalid")
        if broken_safety_arms:
            failures.append("trial_safety_arm_identity_link_invalid")
        if failures:
            return _fail(
                self.verifier_id,
                state.current_stage,
                "clinical_identity_continuity_invalid",
                "Clinical intervention or trial identity violates continuity rules.",
                details={
                    "failures": sorted(set(failures)),
                    "conflicting_bindings": sorted(set(conflicting_bindings)),
                    "broken_intervention_ids": sorted(set(broken_interventions)),
                    "broken_trial_ids": sorted(set(broken_trials)),
                    "broken_trial_design_ids": sorted(set(broken_designs)),
                    "broken_trial_arm_ids": sorted(set(broken_arms)),
                    "broken_trial_population_ids": sorted(set(broken_populations)),
                    "broken_trial_endpoint_ids": sorted(set(broken_endpoints)),
                    "broken_trial_safety_ids": sorted(
                        set(broken_safety_records)
                    ),
                    "broken_trial_safety_arm_ids": sorted(
                        set(broken_safety_arms)
                    ),
                },
            )
        return _pass(
            self.verifier_id,
            state.current_stage,
            "clinical_identity_continuity_valid",
            "Candidate, intervention, trial, design, and safety identities preserve continuity.",
        )


class ClinicalEndpointMappingContinuityVerifier:
    verifier_id = "clinical_endpoint_mapping_continuity"
    kind = VerifierKind.DETERMINISTIC

    def verify(
        self,
        state: ProgramState,
        packet: DecisionPacket,
        proposed_state: ProgramState,
    ) -> VerifierResult:
        previous = state.clinical_endpoint_mappings_by_id
        current = proposed_state.clinical_endpoint_mappings_by_id
        packet_updates = {
            item.mapping_id: item
            for item in packet.clinical_endpoint_mapping_updates
        }
        failures: list[str] = []
        broken_ids: set[str] = set()
        for mapping_id, record in previous.items():
            if current.get(mapping_id) != record:
                failures.append("committed_endpoint_mapping_mutated_or_removed")
                broken_ids.add(mapping_id)
        new_ids = set(current) - set(previous)
        if new_ids != set(packet_updates):
            failures.append("packet_endpoint_mapping_update_set_mismatch")
            broken_ids.update(new_ids ^ set(packet_updates))
        rebound_ids = set(previous) & set(packet_updates)
        if rebound_ids:
            failures.append("endpoint_mapping_id_rebound")
            broken_ids.update(rebound_ids)
        for mapping_id in new_ids:
            record = current[mapping_id]
            if packet_updates.get(mapping_id) != record:
                failures.append("packet_endpoint_mapping_content_mismatch")
                broken_ids.add(mapping_id)
                continue
            validation_failures = validate_clinical_endpoint_mapping(
                proposed_state,
                record,
            )
            if validation_failures:
                failures.extend(validation_failures)
                broken_ids.add(mapping_id)
        if failures:
            return _fail(
                self.verifier_id,
                state.current_stage,
                "clinical_endpoint_mapping_continuity_invalid",
                "Endpoint mapping failed approval, identity, source, or replay continuity.",
                details={
                    "failures": sorted(set(failures)),
                    "broken_mapping_ids": sorted(broken_ids),
                    "packet_mapping_ids": sorted(packet_updates),
                },
            )
        return _pass(
            self.verifier_id,
            state.current_stage,
            "clinical_endpoint_mapping_continuity_valid",
            "Approved endpoint mappings preserve exact trial and source identities.",
            details={"new_mapping_ids": sorted(new_ids)},
        )


class ClinicalSynthesisContinuityVerifier:
    verifier_id = "clinical_synthesis_continuity"
    kind = VerifierKind.DETERMINISTIC

    def verify(
        self,
        state: ProgramState,
        packet: DecisionPacket,
        proposed_state: ProgramState,
    ) -> VerifierResult:
        previous = state.benefit_risk_syntheses_by_id
        current = proposed_state.benefit_risk_syntheses_by_id
        packet_updates = {
            item.synthesis_id: item
            for item in packet.benefit_risk_synthesis_updates
        }
        failures: list[str] = []
        broken_ids: set[str] = set()
        for synthesis_id, record in previous.items():
            if current.get(synthesis_id) != record:
                failures.append("committed_synthesis_mutated_or_removed")
                broken_ids.add(synthesis_id)
        new_ids = set(current) - set(previous)
        if new_ids != set(packet_updates):
            failures.append("packet_synthesis_update_set_mismatch")
            broken_ids.update(new_ids ^ set(packet_updates))
        rebound_ids = set(previous) & set(packet_updates)
        if rebound_ids:
            failures.append("synthesis_id_rebound")
            broken_ids.update(rebound_ids)
        for synthesis_id in new_ids:
            record = current[synthesis_id]
            if packet_updates.get(synthesis_id) != record:
                failures.append("packet_synthesis_content_mismatch")
                broken_ids.add(synthesis_id)
                continue
            validation_failures = validate_benefit_risk_synthesis(
                proposed_state,
                record,
            )
            if validation_failures:
                failures.extend(validation_failures)
                broken_ids.add(synthesis_id)
        if failures:
            return _fail(
                self.verifier_id,
                state.current_stage,
                "clinical_synthesis_continuity_invalid",
                "Benefit-risk synthesis failed source, identity, or replay continuity.",
                details={
                    "failures": sorted(set(failures)),
                    "broken_synthesis_ids": sorted(broken_ids),
                    "packet_synthesis_ids": sorted(packet_updates),
                },
            )
        return _pass(
            self.verifier_id,
            state.current_stage,
            "clinical_synthesis_continuity_valid",
            "Benefit-risk synthesis preserves source-disjoint trial provenance.",
            details={"new_synthesis_ids": sorted(new_ids)},
        )


class ContradictionGateVerifier:
    verifier_id = "contradiction_gate"
    kind = VerifierKind.DETERMINISTIC

    def verify(
        self,
        state: ProgramState,
        packet: DecisionPacket,
        proposed_state: ProgramState,
    ) -> VerifierResult:
        if packet.decision is not Decision.ADVANCE:
            return _pass(
                self.verifier_id,
                state.current_stage,
                "contradiction_gate_not_required",
                "Non-advance decisions may preserve unresolved scientific conflicts.",
            )
        unresolved = [
            claim.claim_id
            for claim in proposed_state.claims
            if claim.disposition
            in {ClaimDisposition.CONTESTED, ClaimDisposition.UNRESOLVED}
        ]
        if unresolved:
            return _fail(
                self.verifier_id,
                state.current_stage,
                "unresolved_program_claims",
                "Advance is blocked while program claims remain unresolved or contested.",
                details={"claim_ids": unresolved},
            )
        return _pass(
            self.verifier_id,
            state.current_stage,
            "program_claims_resolved",
            "No unresolved program claim blocks advance.",
        )


class StageReadinessVerifier:
    verifier_id = "stage_readiness"
    kind = VerifierKind.DETERMINISTIC

    def __init__(self, gates: Mapping[Stage, StageGate]) -> None:
        self.gates = dict(gates)

    @staticmethod
    def _normalized(value: str) -> str:
        return " ".join(value.casefold().split())

    def verify(
        self,
        state: ProgramState,
        packet: DecisionPacket,
        proposed_state: ProgramState,
    ) -> VerifierResult:
        if packet.decision is not Decision.ADVANCE:
            return _pass(
                self.verifier_id,
                state.current_stage,
                "stage_gate_not_required",
                "Stage readiness gates apply only to advance decisions.",
            )
        gate = self.gates.get(state.current_stage)
        if gate is None:
            return _fail(
                self.verifier_id,
                state.current_stage,
                "stage_gate_missing",
                "No explicit readiness gate is configured for the current stage.",
            )

        supported_claims = [
            item
            for item in proposed_state.claims
            if item.stage is state.current_stage
            and item.disposition is ClaimDisposition.SUPPORTED
            and item.confidence >= gate.minimum_confidence
        ]
        linked_support_ids = {
            evidence_id
            for claim in supported_claims
            for evidence_id in claim.supporting_evidence
        }
        stage_evidence = [
            item
            for item in proposed_state.evidence
            if item.evidence_id in linked_support_ids
            and item.stage is state.current_stage
            and item.relation is EvidenceRelation.SUPPORTS
            and item.confidence >= gate.minimum_confidence
        ]
        evidence_predicates = {item.predicate for item in stage_evidence}
        claim_predicates = {item.predicate for item in supported_claims}
        independent_source_ids = {item.source.source_id for item in stage_evidence}
        unique_source_content_hashes = {
            item.source.content_hash
            for item in stage_evidence
            if _is_sha256(item.source.content_hash)
        }
        unpinned_evidence_ids = sorted(
            item.evidence_id
            for item in stage_evidence
            if not _is_sha256(item.source.content_hash)
        )
        viable_candidates = [
            item
            for item in proposed_state.candidates
            if item.status in {CandidateStatus.ACTIVE, CandidateStatus.SELECTED}
        ]
        qualifying_diseases = [
            item
            for item in proposed_state.diseases
            if item.identifiers.get("canonical") == item.disease_id
            and self._normalized(item.name) == self._normalized(proposed_state.disease)
            and bool(item.supporting_evidence)
        ]
        if state.current_stage is Stage.DISEASE_CONTEXT:
            packet_disease_ids = {
                item.disease_id for item in packet.disease_updates
            }
            qualifying_diseases = [
                item
                for item in qualifying_diseases
                if item.disease_id in packet_disease_ids
                and bool(set(item.supporting_evidence) & linked_support_ids)
            ]
        qualifying_disease_ids = {
            item.disease_id for item in qualifying_diseases
        }
        missing_evidence = sorted(
            set(gate.required_evidence_predicates) - evidence_predicates
        )
        missing_claims = sorted(set(gate.required_claim_predicates) - claim_predicates)
        required_namespaces = set(gate.required_target_identifier_namespaces)
        qualifying_targets = [
            item
            for item in proposed_state.targets
            if required_namespaces.issubset(item.identifiers)
            and (
                not qualifying_disease_ids
                or item.disease_id in qualifying_disease_ids
            )
        ]
        if state.current_stage in {
            Stage.TARGET_NOMINATION,
            Stage.MODALITY_SELECTION,
        }:
            packet_target_ids = {item.target_id for item in packet.target_updates}
            qualifying_targets = [
                item
                for item in qualifying_targets
                if item.target_id in packet_target_ids
                and set(item.supporting_evidence) & linked_support_ids
            ]
        qualifying_target_ids = {item.target_id for item in qualifying_targets}
        linked_viable_candidates = [
            item
            for item in viable_candidates
            if item.attributes.get("target_record_id") in qualifying_target_ids
            and (
                not qualifying_disease_ids
                or item.attributes.get("disease_id") in qualifying_disease_ids
            )
        ]
        linked_viable_candidate_ids = {
            item.candidate_id for item in linked_viable_candidates
        }
        packet_assay_ids = {item.assay_id for item in packet.assay_updates}
        qualifying_assays = []
        for assay in proposed_state.assays:
            linked_evidence = [
                item
                for item in stage_evidence
                if item.evidence_id in assay.supporting_evidence
                and item.biological_context.get("candidate_id")
                in linked_viable_candidate_ids
            ]
            if (
                assay.assay_id in packet_assay_ids
                and assay.target_id in qualifying_target_ids
                and assay.disease_id in qualifying_disease_ids
                and linked_evidence
            ):
                qualifying_assays.append(assay)
        packet_model_system_ids = {
            item.model_system_id for item in packet.model_system_updates
        }
        qualifying_model_systems = []
        for model_system in proposed_state.model_systems:
            linked_evidence = [
                item
                for item in stage_evidence
                if item.evidence_id in model_system.supporting_evidence
                and item.biological_context.get("candidate_id")
                in linked_viable_candidate_ids
            ]
            if (
                model_system.model_system_id in packet_model_system_ids
                and model_system.disease_id in qualifying_disease_ids
                and linked_evidence
            ):
                qualifying_model_systems.append(model_system)
        packet_intervention_ids = {
            item.intervention_id for item in packet.intervention_updates
        }
        qualifying_interventions = []
        for intervention in proposed_state.interventions:
            linked_evidence = [
                item
                for item in stage_evidence
                if item.evidence_id in intervention.supporting_evidence
                and item.biological_context.get("candidate_id")
                in linked_viable_candidate_ids
            ]
            if (
                intervention.intervention_id in packet_intervention_ids
                and intervention.candidate_id in linked_viable_candidate_ids
                and intervention.disease_id in qualifying_disease_ids
                and linked_evidence
            ):
                qualifying_interventions.append(intervention)
        qualifying_intervention_ids = {
            item.intervention_id for item in qualifying_interventions
        }
        packet_trial_ids = {item.trial_id for item in packet.trial_updates}
        qualifying_trials = []
        for trial in proposed_state.trials:
            linked_evidence = [
                item
                for item in stage_evidence
                if item.evidence_id in trial.supporting_evidence
            ]
            if (
                trial.trial_id in packet_trial_ids
                and trial.intervention_id in qualifying_intervention_ids
                and trial.disease_id in qualifying_disease_ids
                and linked_evidence
            ):
                qualifying_trials.append(trial)
        qualifying_trial_ids = {item.trial_id for item in qualifying_trials}
        packet_trial_design_ids = {
            item.design_id for item in packet.trial_design_updates
        }
        qualifying_trial_designs = []
        for design in proposed_state.trial_designs:
            linked_evidence = [
                item
                for item in stage_evidence
                if item.evidence_id in design.supporting_evidence
            ]
            candidate_arm_count = sum(
                item.role is TrialArmRole.CANDIDATE
                and item.intervention_id == design.intervention_id
                for item in design.arms
            )
            comparator_arm_count = sum(
                item.role is TrialArmRole.COMPARATOR
                and item.intervention_id != design.intervention_id
                for item in design.arms
            )
            design_arm_ids = {item.arm_id for item in design.arms}
            safety_complete = any(
                safety.trial_id == design.trial_id
                and self._normalized(safety.event_category) == "serious"
                and self._normalized(safety.reporting_status) == "posted"
                and {item.arm_id for item in safety.arm_summaries}
                == design_arm_ids
                for safety in design.safety_records
            )
            if (
                design.design_id in packet_trial_design_ids
                and design.trial_id in qualifying_trial_ids
                and design.intervention_id in qualifying_intervention_ids
                and design.disease_id in qualifying_disease_ids
                and len(design.arms) >= 2
                and candidate_arm_count >= 1
                and comparator_arm_count >= 1
                and design.populations
                and design.endpoints
                and safety_complete
                and linked_evidence
            ):
                qualifying_trial_designs.append(design)
        packet_synthesis_ids = {
            item.synthesis_id for item in packet.benefit_risk_synthesis_updates
        }
        qualifying_benefit_risk_syntheses = [
            item
            for item in proposed_state.benefit_risk_syntheses
            if item.synthesis_id in packet_synthesis_ids
            and item.stage is state.current_stage
            and bool(set(item.supporting_evidence) & linked_support_ids)
            and item.pooling_method == "none"
            and not item.pooling_performed
            and item.source_disjoint
            and not item.clinical_acceptability_inferred
        ]
        failures: list[str] = []
        if len(stage_evidence) < gate.minimum_evidence_events:
            failures.append("insufficient_evidence_count")
        if len(independent_source_ids) < gate.minimum_independent_sources:
            failures.append("insufficient_independent_sources")
        if (
            len(unique_source_content_hashes) < gate.minimum_independent_sources
        ):
            failures.append("insufficient_unique_source_content")
        if gate.require_source_content_hashes and unpinned_evidence_ids:
            failures.append("source_content_hash_missing_or_invalid")
        if len(viable_candidates) < gate.minimum_viable_candidates:
            failures.append("insufficient_viable_candidates")
        if len(qualifying_diseases) < gate.minimum_disease_records:
            failures.append("disease_identity_missing")
        if len(qualifying_assays) < gate.minimum_assay_records:
            failures.append("assay_identity_missing")
        if len(qualifying_model_systems) < gate.minimum_model_system_records:
            failures.append("model_system_identity_missing")
        if len(qualifying_interventions) < gate.minimum_intervention_records:
            failures.append("intervention_identity_missing")
        if len(qualifying_trials) < gate.minimum_trial_records:
            failures.append("trial_identity_missing")
        if len(qualifying_trial_designs) < gate.minimum_trial_design_records:
            failures.append("trial_design_identity_missing")
        if (
            len(qualifying_benefit_risk_syntheses)
            < gate.minimum_benefit_risk_synthesis_records
        ):
            failures.append("benefit_risk_synthesis_missing")
        if packet.confidence < gate.minimum_confidence:
            failures.append("decision_confidence_below_gate")
        if missing_evidence:
            failures.append("required_evidence_predicate_missing")
        if missing_claims:
            failures.append("required_supported_claim_missing")
        if required_namespaces and not qualifying_targets:
            failures.append("target_identity_namespaces_missing")
        if (
            state.current_stage
            in {
                Stage.CANDIDATE_GENERATION,
                Stage.LEAD_OPTIMIZATION,
                Stage.PRECLINICAL_VALIDATION,
            }
            and not linked_viable_candidates
        ):
            failures.append("viable_candidate_target_link_missing")

        details = {
            "failures": failures,
            "qualifying_stage_evidence_count": len(stage_evidence),
            "independent_source_count": len(independent_source_ids),
            "minimum_independent_sources": gate.minimum_independent_sources,
            "unique_source_content_count": len(unique_source_content_hashes),
            "unpinned_evidence_ids": unpinned_evidence_ids,
            "require_source_content_hashes": gate.require_source_content_hashes,
            "viable_candidate_count": len(viable_candidates),
            "minimum_viable_candidates": gate.minimum_viable_candidates,
            "qualifying_disease_ids": sorted(qualifying_disease_ids),
            "minimum_disease_records": gate.minimum_disease_records,
            "qualifying_assay_ids": sorted(
                item.assay_id for item in qualifying_assays
            ),
            "minimum_assay_records": gate.minimum_assay_records,
            "qualifying_model_system_ids": sorted(
                item.model_system_id for item in qualifying_model_systems
            ),
            "minimum_model_system_records": gate.minimum_model_system_records,
            "qualifying_intervention_ids": sorted(
                item.intervention_id for item in qualifying_interventions
            ),
            "minimum_intervention_records": gate.minimum_intervention_records,
            "qualifying_trial_ids": sorted(
                item.trial_id for item in qualifying_trials
            ),
            "minimum_trial_records": gate.minimum_trial_records,
            "qualifying_trial_design_ids": sorted(
                item.design_id for item in qualifying_trial_designs
            ),
            "minimum_trial_design_records": gate.minimum_trial_design_records,
            "qualifying_benefit_risk_synthesis_ids": sorted(
                item.synthesis_id
                for item in qualifying_benefit_risk_syntheses
            ),
            "minimum_benefit_risk_synthesis_records": (
                gate.minimum_benefit_risk_synthesis_records
            ),
            "missing_evidence_predicates": missing_evidence,
            "missing_claim_predicates": missing_claims,
            "required_target_identifier_namespaces": sorted(required_namespaces),
            "qualifying_target_ids": sorted(item.target_id for item in qualifying_targets),
            "linked_viable_candidate_ids": sorted(
                linked_viable_candidate_ids
            ),
            "minimum_confidence": gate.minimum_confidence,
            "decision_confidence": packet.confidence,
        }
        if failures:
            return _fail(
                self.verifier_id,
                state.current_stage,
                "stage_not_ready",
                "Current-stage evidence and claims do not satisfy the advance gate.",
                details=details,
            )
        return _pass(
            self.verifier_id,
            state.current_stage,
            "stage_ready",
            "Current-stage evidence and claims satisfy the advance gate.",
            details=details,
        )
