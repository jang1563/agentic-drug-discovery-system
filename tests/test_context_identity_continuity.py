from __future__ import annotations

import json
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

from agentic_drug_discovery import (
    AssayRecord,
    BudgetState,
    CandidateRecord,
    CandidateStatus,
    Decision,
    DecisionPacket,
    DiseaseRecord,
    EvidenceEvent,
    EvidenceRelation,
    GatedDiscoveryEnvironment,
    ModelSystemRecord,
    ProgramState,
    SourceReference,
    Stage,
    TargetRecord,
    assay_record_from_dict,
    disease_record_from_dict,
    model_system_record_from_dict,
)


ROOT = Path(__file__).resolve().parents[1]
CREATED_AT = datetime(2025, 1, 1, tzinfo=timezone.utc)
SOURCE = SourceReference(
    source_id="context-identity-fixture",
    source_version="fixture-v1",
    locator="fixture://tests/context-identity",
    content_hash="0" * 64,
)


def evidence(
    evidence_id: str,
    *,
    predicate: str,
    biological_context: dict,
    stage: Stage,
) -> EvidenceEvent:
    return EvidenceEvent(
        evidence_id=evidence_id,
        stage=stage,
        subject="Test Drug",
        predicate=predicate,
        object_value="typed identity fixture",
        source=SOURCE,
        observed_at=date(2024, 1, 1),
        available_at=date(2024, 1, 2),
        relation=EvidenceRelation.SUPPORTS,
        biological_context=biological_context,
    )


def base_state() -> ProgramState:
    disease_evidence = evidence(
        "disease-evidence",
        predicate="disease_context_resolved",
        biological_context={"disease_id": "MONDO_TEST"},
        stage=Stage.DISEASE_CONTEXT,
    )
    assay_evidence = evidence(
        "assay-evidence",
        predicate="candidate_target_functional_activity_supported",
        biological_context={
            "candidate_id": "CHEMBL_TEST",
            "assay_id": "ASSAY_TEST1_FUNCTION",
            "target_record_id": "ENSG_TEST1",
            "disease_id": "MONDO_TEST",
            "organism": "Homo sapiens",
        },
        stage=Stage.PRECLINICAL_VALIDATION,
    )
    model_evidence = evidence(
        "model-system-evidence",
        predicate="disease_model_effect_supported",
        biological_context={
            "candidate_id": "CHEMBL_TEST",
            "model_system_id": "MODEL_TEST_DISEASE",
            "disease_id": "MONDO_TEST",
            "organism": "Mus musculus",
        },
        stage=Stage.PRECLINICAL_VALIDATION,
    )
    return ProgramState(
        program_id="context-identity-program",
        disease="test disease",
        therapeutic_hypothesis="Experimental identities must remain stable.",
        as_of_date=date(2025, 1, 1),
        current_stage=Stage.PRECLINICAL_VALIDATION,
        budget=BudgetState(limit=1.0),
        evidence=(disease_evidence, assay_evidence, model_evidence),
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
        assays=(
            AssayRecord(
                assay_id="ASSAY_TEST1_FUNCTION",
                name="Test target functional assay",
                assay_type="functional",
                target_id="ENSG_TEST1",
                disease_id="MONDO_TEST",
                organism="Homo sapiens",
                stage=Stage.PRECLINICAL_VALIDATION,
                identifiers={
                    "canonical": "ASSAY_TEST1_FUNCTION",
                    "source_assay": "SOURCE_ASSAY_1",
                },
                supporting_evidence=(assay_evidence.evidence_id,),
            ),
        ),
        model_systems=(
            ModelSystemRecord(
                model_system_id="MODEL_TEST_DISEASE",
                name="Illustrative disease model",
                model_type="animal model",
                disease_id="MONDO_TEST",
                organism="Mus musculus",
                stage=Stage.PRECLINICAL_VALIDATION,
                identifiers={"canonical": "MODEL_TEST_DISEASE"},
                supporting_evidence=(model_evidence.evidence_id,),
            ),
        ),
    )


def defer_packet(
    state: ProgramState,
    *,
    packet_id: str,
    evidence_additions: tuple[EvidenceEvent, ...] = (),
    disease_updates: tuple[DiseaseRecord, ...] = (),
    assay_updates: tuple[AssayRecord, ...] = (),
    model_system_updates: tuple[ModelSystemRecord, ...] = (),
) -> DecisionPacket:
    return DecisionPacket(
        packet_id=packet_id,
        program_id=state.program_id,
        expected_state_version=state.version,
        stage=state.current_stage,
        decision=Decision.DEFER,
        rationale="Exercise context identity continuity independently of readiness.",
        confidence=0.9,
        evidence_additions=evidence_additions,
        disease_updates=disease_updates,
        assay_updates=assay_updates,
        model_system_updates=model_system_updates,
        created_at=CREATED_AT,
    )


def blocking_codes(result) -> set[str]:
    return {item.code for item in result.blocking_results}


class ContextIdentityContinuityTests(unittest.TestCase):
    def test_machine_example_round_trips_through_strict_parsers(self) -> None:
        path = ROOT / "rl_env/specs/discovery_context_identity.example.json"
        example = json.loads(path.read_text(encoding="utf-8"))

        disease = disease_record_from_dict(example["disease"])
        assay = assay_record_from_dict(example["assay"])
        model_system = model_system_record_from_dict(example["model_system"])

        self.assertEqual(disease.to_dict(), example["disease"])
        self.assertEqual(assay.to_dict(), example["assay"])
        self.assertEqual(model_system.to_dict(), example["model_system"])

    def test_disease_name_cannot_be_rebound(self) -> None:
        state = base_state()
        previous = state.diseases[0]
        rebound = DiseaseRecord(
            disease_id=previous.disease_id,
            name="different disease",
            stage=state.current_stage,
            identifiers=previous.identifiers,
            supporting_evidence=previous.supporting_evidence,
        )

        result = GatedDiscoveryEnvironment().transition(
            state,
            defer_packet(
                state,
                packet_id="disease-rebind",
                disease_updates=(rebound,),
            ),
        )

        self.assertFalse(result.applied)
        self.assertIn("context_identity_continuity_invalid", blocking_codes(result))

    def test_two_assays_cannot_claim_one_source_binding(self) -> None:
        state = base_state()
        second_evidence = evidence(
            "assay-evidence-2",
            predicate="candidate_target_functional_activity_supported",
            biological_context={
                "candidate_id": "CHEMBL_TEST",
                "assay_id": "ASSAY_TEST1_FUNCTION_2",
                "target_record_id": "ENSG_TEST1",
                "disease_id": "MONDO_TEST",
                "organism": "Homo sapiens",
            },
            stage=Stage.PRECLINICAL_VALIDATION,
        )
        second = AssayRecord(
            assay_id="ASSAY_TEST1_FUNCTION_2",
            name="Second target functional assay",
            assay_type="functional",
            target_id="ENSG_TEST1",
            disease_id="MONDO_TEST",
            organism="Homo sapiens",
            stage=state.current_stage,
            identifiers={
                "canonical": "ASSAY_TEST1_FUNCTION_2",
                "source_assay": "SOURCE_ASSAY_1",
            },
            supporting_evidence=(second_evidence.evidence_id,),
        )

        result = GatedDiscoveryEnvironment().transition(
            state,
            defer_packet(
                state,
                packet_id="assay-collision",
                evidence_additions=(second_evidence,),
                assay_updates=(second,),
            ),
        )

        self.assertFalse(result.applied)
        self.assertIn("context_identity_continuity_invalid", blocking_codes(result))
        details = next(
            item.details
            for item in result.blocking_results
            if item.code == "context_identity_continuity_invalid"
        )
        self.assertIn("assay_namespace_collision", details["failures"])

    def test_assay_evidence_must_link_a_known_candidate(self) -> None:
        state = base_state()
        unlinked_evidence = evidence(
            "assay-evidence-unknown-candidate",
            predicate="candidate_target_functional_activity_supported",
            biological_context={
                "candidate_id": "CHEMBL_UNKNOWN",
                "assay_id": "ASSAY_UNKNOWN_CANDIDATE",
                "target_record_id": "ENSG_TEST1",
                "disease_id": "MONDO_TEST",
                "organism": "Homo sapiens",
            },
            stage=Stage.PRECLINICAL_VALIDATION,
        )
        unlinked = AssayRecord(
            assay_id="ASSAY_UNKNOWN_CANDIDATE",
            name="Unlinked target functional assay",
            assay_type="functional",
            target_id="ENSG_TEST1",
            disease_id="MONDO_TEST",
            organism="Homo sapiens",
            stage=state.current_stage,
            identifiers={"canonical": "ASSAY_UNKNOWN_CANDIDATE"},
            supporting_evidence=(unlinked_evidence.evidence_id,),
        )

        result = GatedDiscoveryEnvironment().transition(
            state,
            defer_packet(
                state,
                packet_id="assay-unknown-candidate",
                evidence_additions=(unlinked_evidence,),
                assay_updates=(unlinked,),
            ),
        )

        self.assertFalse(result.applied)
        self.assertIn("context_identity_continuity_invalid", blocking_codes(result))

    def test_model_system_core_identity_cannot_be_rebound(self) -> None:
        state = base_state()
        previous = state.model_systems[0]
        rebound = ModelSystemRecord(
            model_system_id=previous.model_system_id,
            name="Different model",
            model_type=previous.model_type,
            disease_id=previous.disease_id,
            organism=previous.organism,
            stage=state.current_stage,
            identifiers=previous.identifiers,
            supporting_evidence=previous.supporting_evidence,
        )

        result = GatedDiscoveryEnvironment().transition(
            state,
            defer_packet(
                state,
                packet_id="model-system-rebind",
                model_system_updates=(rebound,),
            ),
        )

        self.assertFalse(result.applied)
        self.assertIn("context_identity_continuity_invalid", blocking_codes(result))


if __name__ == "__main__":
    unittest.main()
