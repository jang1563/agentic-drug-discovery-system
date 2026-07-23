from __future__ import annotations

import json
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

from jsonschema import Draft202012Validator

from agentic_drug_discovery import (
    BudgetState,
    CandidateRecord,
    CandidateStatus,
    Decision,
    DecisionPacket,
    DiseaseRecord,
    EvidenceEvent,
    EvidenceRelation,
    GatedDiscoveryEnvironment,
    InterventionRecord,
    ProgramState,
    SourceReference,
    Stage,
    TargetRecord,
    TrialRecord,
    intervention_record_from_dict,
    trial_design_record_from_dict,
    trial_record_from_dict,
)


ROOT = Path(__file__).resolve().parents[1]
CREATED_AT = datetime(2025, 1, 1, tzinfo=timezone.utc)
SOURCE = SourceReference(
    source_id="clinical-identity-fixture",
    source_version="fixture-v1",
    locator="fixture://tests/clinical-identity",
    content_hash="0" * 64,
)


def evidence(
    evidence_id: str,
    *,
    trial_id: str,
    intervention_id: str = "CHEMBL_TEST",
    candidate_id: str = "CHEMBL_TEST",
) -> EvidenceEvent:
    return EvidenceEvent(
        evidence_id=evidence_id,
        stage=Stage.CLINICAL_STRATEGY,
        subject="Test Drug",
        predicate="clinical_trial_identity_resolved",
        object_value=trial_id,
        source=SOURCE,
        observed_at=date(2024, 1, 1),
        available_at=date(2024, 1, 2),
        relation=EvidenceRelation.SUPPORTS,
        biological_context={
            "candidate_id": candidate_id,
            "intervention_id": intervention_id,
            "disease_id": "MONDO_TEST",
            "trial_id": trial_id,
            "registry": "ClinicalTrials.gov",
        },
    )


def base_state() -> ProgramState:
    disease_evidence = EvidenceEvent(
        evidence_id="disease-evidence",
        stage=Stage.DISEASE_CONTEXT,
        subject="test disease",
        predicate="disease_context_resolved",
        object_value="MONDO_TEST",
        source=SOURCE,
        observed_at=date(2024, 1, 1),
        available_at=date(2024, 1, 2),
        relation=EvidenceRelation.SUPPORTS,
        biological_context={"disease_id": "MONDO_TEST"},
    )
    trial_evidence = evidence(
        "clinical-trial-identity-evidence",
        trial_id="NCT00000001",
    )
    return ProgramState(
        program_id="clinical-identity-program",
        disease="test disease",
        therapeutic_hypothesis="Clinical identities must remain continuous.",
        as_of_date=date(2025, 1, 1),
        current_stage=Stage.CLINICAL_STRATEGY,
        budget=BudgetState(limit=1.0),
        evidence=(disease_evidence, trial_evidence),
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
        interventions=(
            InterventionRecord(
                intervention_id="CHEMBL_TEST",
                name="Test Drug",
                candidate_id="CHEMBL_TEST",
                disease_id="MONDO_TEST",
                modality="small molecule",
                stage=Stage.CLINICAL_STRATEGY,
                identifiers={
                    "canonical": "CHEMBL_TEST",
                    "chembl_molecule": "CHEMBL_TEST",
                },
                supporting_evidence=(trial_evidence.evidence_id,),
                attributes={"clinical_trial_ids": ["NCT00000001"]},
            ),
        ),
        trials=(
            TrialRecord(
                trial_id="NCT00000001",
                registry="ClinicalTrials.gov",
                intervention_id="CHEMBL_TEST",
                disease_id="MONDO_TEST",
                stage=Stage.CLINICAL_STRATEGY,
                identifiers={
                    "canonical": "NCT00000001",
                    "clinicaltrials_gov": "NCT00000001",
                },
                supporting_evidence=(trial_evidence.evidence_id,),
            ),
        ),
    )


def defer_packet(
    state: ProgramState,
    *,
    packet_id: str,
    evidence_additions: tuple[EvidenceEvent, ...] = (),
    intervention_updates: tuple[InterventionRecord, ...] = (),
    trial_updates: tuple[TrialRecord, ...] = (),
) -> DecisionPacket:
    return DecisionPacket(
        packet_id=packet_id,
        program_id=state.program_id,
        expected_state_version=state.version,
        stage=state.current_stage,
        decision=Decision.DEFER,
        rationale="Exercise clinical identity continuity independently of readiness.",
        confidence=0.9,
        evidence_additions=evidence_additions,
        intervention_updates=intervention_updates,
        trial_updates=trial_updates,
        created_at=CREATED_AT,
    )


def blocking_codes(result) -> set[str]:
    return {item.code for item in result.blocking_results}


class ClinicalIdentityContinuityTests(unittest.TestCase):
    def test_machine_example_round_trips_through_strict_parsers(self) -> None:
        path = ROOT / "rl_env/specs/clinical_intervention_identity.example.json"
        example = json.loads(path.read_text(encoding="utf-8"))
        schema = json.loads(
            (
                ROOT / "rl_env/specs/clinical_intervention_identity.schema.json"
            ).read_text(encoding="utf-8")
        )

        intervention = intervention_record_from_dict(example["intervention"])
        trial = trial_record_from_dict(example["trial"])
        trial_design = trial_design_record_from_dict(example["trial_design"])

        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(example)
        self.assertEqual(intervention.to_dict(), example["intervention"])
        self.assertEqual(trial.to_dict(), example["trial"])
        self.assertEqual(trial_design.to_dict(), example["trial_design"])
        with self.assertRaises(ValueError):
            intervention_record_from_dict(
                {**example["intervention"], "undeclared_field": True}
            )

    def test_intervention_core_identity_cannot_be_rebound(self) -> None:
        state = base_state()
        previous = state.interventions[0]
        rebound = InterventionRecord(
            intervention_id=previous.intervention_id,
            name="Different Drug",
            candidate_id=previous.candidate_id,
            disease_id=previous.disease_id,
            modality=previous.modality,
            stage=state.current_stage,
            identifiers=previous.identifiers,
            supporting_evidence=previous.supporting_evidence,
            attributes=previous.attributes,
        )

        result = GatedDiscoveryEnvironment().transition(
            state,
            defer_packet(
                state,
                packet_id="intervention-rebind",
                intervention_updates=(rebound,),
            ),
        )

        self.assertFalse(result.applied)
        self.assertIn("clinical_identity_continuity_invalid", blocking_codes(result))

    def test_two_trials_cannot_claim_one_registry_alias(self) -> None:
        state = base_state()
        previous = state.trials[0]
        updated_previous = TrialRecord(
            trial_id=previous.trial_id,
            registry=previous.registry,
            intervention_id=previous.intervention_id,
            disease_id=previous.disease_id,
            stage=state.current_stage,
            identifiers={**dict(previous.identifiers), "registry_alias": "shared"},
            supporting_evidence=previous.supporting_evidence,
            attributes=previous.attributes,
        )
        second_evidence = evidence(
            "second-trial-identity-evidence",
            trial_id="NCT00000002",
        )
        second = TrialRecord(
            trial_id="NCT00000002",
            registry="ClinicalTrials.gov",
            intervention_id="CHEMBL_TEST",
            disease_id="MONDO_TEST",
            stage=state.current_stage,
            identifiers={
                "canonical": "NCT00000002",
                "clinicaltrials_gov": "NCT00000002",
                "registry_alias": "shared",
            },
            supporting_evidence=(second_evidence.evidence_id,),
        )

        result = GatedDiscoveryEnvironment().transition(
            state,
            defer_packet(
                state,
                packet_id="trial-namespace-collision",
                evidence_additions=(second_evidence,),
                trial_updates=(updated_previous, second),
            ),
        )

        self.assertFalse(result.applied)
        self.assertIn("clinical_identity_continuity_invalid", blocking_codes(result))
        details = next(
            item.details
            for item in result.blocking_results
            if item.code == "clinical_identity_continuity_invalid"
        )
        self.assertIn("trial_namespace_collision", details["failures"])

    def test_trial_must_link_an_accepted_intervention(self) -> None:
        state = base_state()
        unlinked_evidence = evidence(
            "unlinked-trial-identity-evidence",
            trial_id="NCT00000003",
            intervention_id="CHEMBL_UNKNOWN",
            candidate_id="CHEMBL_UNKNOWN",
        )
        unlinked = TrialRecord(
            trial_id="NCT00000003",
            registry="ClinicalTrials.gov",
            intervention_id="CHEMBL_UNKNOWN",
            disease_id="MONDO_TEST",
            stage=state.current_stage,
            identifiers={
                "canonical": "NCT00000003",
                "clinicaltrials_gov": "NCT00000003",
            },
            supporting_evidence=(unlinked_evidence.evidence_id,),
        )

        result = GatedDiscoveryEnvironment().transition(
            state,
            defer_packet(
                state,
                packet_id="trial-unlinked-intervention",
                evidence_additions=(unlinked_evidence,),
                trial_updates=(unlinked,),
            ),
        )

        self.assertFalse(result.applied)
        self.assertIn("clinical_identity_continuity_invalid", blocking_codes(result))

    def test_intervention_support_cannot_be_removed(self) -> None:
        state = base_state()
        previous = state.interventions[0]
        unsupported = InterventionRecord(
            intervention_id=previous.intervention_id,
            name=previous.name,
            candidate_id=previous.candidate_id,
            disease_id=previous.disease_id,
            modality=previous.modality,
            stage=state.current_stage,
            identifiers=previous.identifiers,
            supporting_evidence=(),
            attributes=previous.attributes,
        )

        result = GatedDiscoveryEnvironment().transition(
            state,
            defer_packet(
                state,
                packet_id="intervention-support-removal",
                intervention_updates=(unsupported,),
            ),
        )

        self.assertFalse(result.applied)
        self.assertIn("clinical_identity_continuity_invalid", blocking_codes(result))


if __name__ == "__main__":
    unittest.main()
