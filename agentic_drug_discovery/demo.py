"""Run an illustrative, non-benchmark SCD-shaped end-to-end trajectory.

The fixture exercises control-plane semantics only. Its evidence records point to
the public vertical-slice documentation and must not be interpreted as clinical or
regulatory recommendations.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone

from .environment import DEFAULT_STAGE_PREDICATES, GatedDiscoveryEnvironment
from .models import (
    ActionRecord,
    ActionType,
    AssayRecord,
    BudgetState,
    CandidateRecord,
    CandidateStatus,
    ClaimDisposition,
    Decision,
    DecisionPacket,
    DEFAULT_STAGE_SEQUENCE,
    DiseaseRecord,
    EvidenceEvent,
    EvidenceRelation,
    InterventionRecord,
    ModelSystemRecord,
    ProgramState,
    ProgramStatus,
    ScientificClaim,
    SourceReference,
    Stage,
    TargetRecord,
    TrialArmRecord,
    TrialArmRole,
    TrialDesignRecord,
    TrialEndpointRecord,
    TrialPopulationRecord,
    TrialRecord,
    TrialSafetyArmRecord,
    TrialSafetyRecord,
    TransitionResult,
)


_STAGE_OBJECTS: dict[Stage, str] = {
    Stage.DISEASE_CONTEXT: "illustrative unmet-need definition is explicit",
    Stage.TARGET_NOMINATION: "illustrative target-disease rationale is represented",
    Stage.MODALITY_SELECTION: "illustrative modality matches the intervention hypothesis",
    Stage.CANDIDATE_GENERATION: "illustrative candidate identity is normalized",
    Stage.LEAD_OPTIMIZATION: "illustrative developability package is reviewed",
    Stage.PRECLINICAL_VALIDATION: "illustrative functional effect is represented",
    Stage.CLINICAL_STRATEGY: "illustrative clinical evidence package is assessed",
    Stage.REGULATORY_POSTMARKET: "illustrative regulatory and safety status is assessed",
}


def build_scd_control_plane_demo() -> tuple[
    GatedDiscoveryEnvironment,
    ProgramState,
    tuple[DecisionPacket, ...],
]:
    """Build a deterministic eight-stage fixture with no hidden evaluator labels."""

    environment = GatedDiscoveryEnvironment()
    initial_state = ProgramState(
        program_id="public-scd-control-plane-demo",
        disease="sickle cell disease",
        therapeutic_hypothesis=(
            "An evidence-governed intervention program can be evaluated across the "
            "full discovery and development chain."
        ),
        as_of_date=date(2025, 1, 1),
        current_stage=Stage.DISEASE_CONTEXT,
        budget=BudgetState(limit=10.0),
        target_product_profile={
            "fixture_kind": "illustrative_non_benchmark",
            "intended_use": "transition_and_verifier_smoke_test",
        },
    )

    packets: list[DecisionPacket] = []
    target_record: TargetRecord | None = None
    intervention_record: InterventionRecord | None = None
    for index, stage in enumerate(DEFAULT_STAGE_SEQUENCE):
        predicate = DEFAULT_STAGE_PREDICATES[stage]
        evidence_additions: list[EvidenceEvent] = []
        for evidence_index, evidence_predicate in enumerate(
            environment.stage_gates[stage].required_evidence_predicates,
            start=1,
        ):
            fixture_content = (
                f"illustrative-control-plane-v1:{stage.value}:"
                f"{evidence_predicate}:{_STAGE_OBJECTS[stage]}"
            )
            if stage is Stage.CLINICAL_STRATEGY:
                fixture_content = "illustrative-clinicaltrials-gov-study-snapshot-v1"
            biological_context = {
                "fixture": True,
                "disease": "sickle cell disease",
                "disease_id": "MONDO_0011382",
            }
            if evidence_predicate == "candidate_target_functional_activity_supported":
                biological_context.update(
                    {
                        "candidate_id": "scd-demo-candidate",
                        "target_id": "CHEMBL_DEMO_TARGET",
                        "target_record_id": "ENSG00000119866",
                        "organism": "Homo sapiens",
                        "assay_id": "ASSAY_SCD_DEMO_001",
                    }
                )
            elif evidence_predicate == "disease_model_effect_supported":
                biological_context.update(
                    {
                        "candidate_id": "scd-demo-candidate",
                        "organism": "Mus musculus",
                        "model_system_id": "MODEL_SCD_DEMO_001",
                    }
                )
            elif evidence_predicate == "clinical_evidence_assessed":
                biological_context.update(
                    {
                        "candidate_id": "scd-demo-candidate",
                        "intervention_id": "scd-demo-candidate",
                        "trial_id": "NCT00000001",
                        "design_id": "NCT00000001:design",
                        "population_id": "NCT00000001:population:primary-0",
                        "endpoint_id": "NCT00000001:endpoint:primary-0",
                        "arm_ids": [
                            "NCT00000001:arm:OG000",
                            "NCT00000001:arm:OG001",
                        ],
                        "registry": "ClinicalTrials.gov",
                    }
                )
            elif evidence_predicate == "clinical_safety_assessed":
                biological_context.update(
                    {
                        "candidate_id": "scd-demo-candidate",
                        "intervention_id": "scd-demo-candidate",
                        "trial_id": "NCT00000001",
                        "design_id": "NCT00000001:design",
                        "safety_id": (
                            "NCT00000001:safety:serious-adverse-events"
                        ),
                        "arm_ids": [
                            "NCT00000001:arm:OG000",
                            "NCT00000001:arm:OG001",
                        ],
                        "registry": "ClinicalTrials.gov",
                    }
                )
            elif evidence_predicate == "regulatory_status_assessed":
                biological_context.update(
                    {
                        "candidate_id": "scd-demo-candidate",
                        "intervention_id": "scd-demo-candidate",
                    }
                )
            evidence_additions.append(
                EvidenceEvent(
                    evidence_id=(
                        f"scd-demo-evidence-{index + 1:02d}-{evidence_index:02d}"
                    ),
                    stage=stage,
                    subject="public-scd-control-plane-demo",
                    predicate=evidence_predicate,
                    object_value=_STAGE_OBJECTS[stage],
                    source=SourceReference(
                        source_id=(
                            "illustrative-clinicaltrials-gov-fixture"
                            if stage is Stage.CLINICAL_STRATEGY
                            else f"illustrative-{evidence_predicate}-fixture"
                        ),
                        source_version="illustrative-control-plane-v1",
                        locator=(
                            "fixture://clinical_strategy/exact-study-snapshot"
                            if stage is Stage.CLINICAL_STRATEGY
                            else f"fixture://{stage.value}/{evidence_predicate}"
                        ),
                        content_hash=hashlib.sha256(
                            fixture_content.encode("utf-8")
                        ).hexdigest(),
                    ),
                    observed_at=date(2024, index + 1, 1),
                    available_at=date(2024, index + 1, 2),
                    relation=EvidenceRelation.SUPPORTS,
                    biological_context=biological_context,
                    metadata={
                        "non_benchmark": True,
                        "fixture_content": fixture_content,
                    },
                )
            )
        if stage is Stage.CLINICAL_STRATEGY:
            clinical_source = evidence_additions[0].source
            clinical_context = {
                "fixture": True,
                "disease": "sickle cell disease",
                "candidate_id": "scd-demo-candidate",
                "intervention_id": "scd-demo-candidate",
                "disease_id": "MONDO_0011382",
                "trial_id": "NCT00000001",
                "design_id": "NCT00000001:design",
                "registry": "ClinicalTrials.gov",
            }
            identity_specs = (
                (
                    "trial-identity",
                    "clinical_trial_identity_resolved",
                    "NCT00000001",
                    {},
                ),
                (
                    "candidate-arm",
                    "clinical_trial_arm_identity_resolved",
                    "NCT00000001:arm:OG000",
                    {"arm_id": "NCT00000001:arm:OG000"},
                ),
                (
                    "comparator-arm",
                    "clinical_trial_arm_identity_resolved",
                    "NCT00000001:arm:OG001",
                    {"arm_id": "NCT00000001:arm:OG001"},
                ),
                (
                    "population",
                    "clinical_trial_population_identity_resolved",
                    "NCT00000001:population:primary-0",
                    {"population_id": "NCT00000001:population:primary-0"},
                ),
                (
                    "endpoint",
                    "clinical_trial_endpoint_identity_resolved",
                    "NCT00000001:endpoint:primary-0",
                    {
                        "population_id": "NCT00000001:population:primary-0",
                        "endpoint_id": "NCT00000001:endpoint:primary-0",
                    },
                ),
                (
                    "safety",
                    "clinical_trial_safety_identity_resolved",
                    "NCT00000001:safety:serious-adverse-events",
                    {
                        "safety_id": (
                            "NCT00000001:safety:serious-adverse-events"
                        ),
                        "arm_ids": [
                            "NCT00000001:arm:OG000",
                            "NCT00000001:arm:OG001",
                        ],
                    },
                ),
            )
            evidence_additions.extend(
                EvidenceEvent(
                    evidence_id=f"scd-demo-clinical-{suffix}",
                    stage=stage,
                    subject="public-scd-control-plane-demo",
                    predicate=identity_predicate,
                    object_value=object_value,
                    source=clinical_source,
                    observed_at=date(2024, index + 1, 1),
                    available_at=date(2024, index + 1, 2),
                    relation=EvidenceRelation.SUPPORTS,
                    biological_context={**clinical_context, **extra_context},
                    metadata={"non_benchmark": True, "fixture": True},
                )
                for suffix, identity_predicate, object_value, extra_context in identity_specs
            )
        evidence_ids = tuple(item.evidence_id for item in evidence_additions)
        claim_evidence_ids = (
            (evidence_additions[0].evidence_id,)
            if stage is Stage.CLINICAL_STRATEGY
            else evidence_ids
        )
        claim = ScientificClaim(
            claim_id=f"scd-demo-claim-{index + 1:02d}",
            stage=stage,
            subject="public-scd-control-plane-demo",
            predicate=predicate,
            object_value=_STAGE_OBJECTS[stage],
            disposition=ClaimDisposition.SUPPORTED,
            supporting_evidence=claim_evidence_ids,
            confidence=0.8,
            biological_context={"fixture": True},
        )
        claim_updates = (claim,)
        if stage is Stage.CLINICAL_STRATEGY:
            claim_updates = (
                claim,
                ScientificClaim(
                    claim_id="scd-demo-claim-07-safety",
                    stage=stage,
                    subject="public-scd-control-plane-demo",
                    predicate="clinical_safety_assessed",
                    object_value=_STAGE_OBJECTS[stage],
                    disposition=ClaimDisposition.SUPPORTED,
                    supporting_evidence=(evidence_additions[1].evidence_id,),
                    confidence=0.8,
                    biological_context={"fixture": True},
                ),
            )

        candidate_updates: tuple[CandidateRecord, ...] = ()
        disease_updates: tuple[DiseaseRecord, ...] = ()
        target_updates: tuple[TargetRecord, ...] = ()
        assay_updates: tuple[AssayRecord, ...] = ()
        model_system_updates: tuple[ModelSystemRecord, ...] = ()
        intervention_updates: tuple[InterventionRecord, ...] = ()
        trial_updates: tuple[TrialRecord, ...] = ()
        trial_design_updates: tuple[TrialDesignRecord, ...] = ()
        if stage is Stage.DISEASE_CONTEXT:
            disease_updates = (
                DiseaseRecord(
                    disease_id="MONDO_0011382",
                    name="sickle cell disease",
                    stage=stage,
                    identifiers={"canonical": "MONDO_0011382"},
                    supporting_evidence=evidence_ids,
                    attributes={"fixture": True},
                ),
            )
        if stage is Stage.TARGET_NOMINATION:
            target_record = TargetRecord(
                target_id="ENSG00000119866",
                symbol="BCL11A",
                disease_id="MONDO_0011382",
                organism="Homo sapiens",
                stage=stage,
                identifiers={
                    "ensembl_gene": "ENSG00000119866",
                    "gene_symbol": "BCL11A",
                },
                supporting_evidence=evidence_ids,
                attributes={"fixture": True},
            )
            target_updates = (target_record,)
        elif stage is Stage.MODALITY_SELECTION:
            assert target_record is not None
            target_record = TargetRecord(
                target_id=target_record.target_id,
                symbol=target_record.symbol,
                disease_id=target_record.disease_id,
                organism=target_record.organism,
                stage=stage,
                identifiers={
                    **dict(target_record.identifiers),
                    "chembl_target": "CHEMBL_DEMO_TARGET",
                },
                supporting_evidence=(
                    *target_record.supporting_evidence,
                    *evidence_ids,
                ),
                attributes={
                    **dict(target_record.attributes),
                    "fixture_target_profile": True,
                },
            )
            target_updates = (target_record,)

        target_links = {
            "target_record_id": "ENSG00000119866",
            "target_chembl_id": "CHEMBL_DEMO_TARGET",
            "target_symbol": "BCL11A",
            "disease_id": "MONDO_0011382",
        }
        if stage is Stage.CANDIDATE_GENERATION:
            candidate_updates = (
                CandidateRecord(
                    candidate_id="scd-demo-candidate",
                    name="Illustrative small-molecule candidate",
                    modality="small molecule",
                    stage=stage,
                    attributes={
                        "fixture": True,
                        "identity_resolved": True,
                        **target_links,
                    },
                ),
            )
        elif stage is Stage.LEAD_OPTIMIZATION:
            candidate_updates = (
                CandidateRecord(
                    candidate_id="scd-demo-candidate",
                    name="Illustrative small-molecule candidate",
                    modality="small molecule",
                    stage=stage,
                    status=CandidateStatus.SELECTED,
                    attributes={
                        "fixture": True,
                        "developability_reviewed": True,
                        **target_links,
                    },
                ),
            )
        elif stage is Stage.PRECLINICAL_VALIDATION:
            assay_updates = (
                AssayRecord(
                    assay_id="ASSAY_SCD_DEMO_001",
                    name="Illustrative BCL11A functional assay",
                    assay_type="functional",
                    target_id="ENSG00000119866",
                    disease_id="MONDO_0011382",
                    organism="Homo sapiens",
                    stage=stage,
                    identifiers={"canonical": "ASSAY_SCD_DEMO_001"},
                    supporting_evidence=(evidence_ids[0],),
                    attributes={"fixture": True},
                ),
            )
            model_system_updates = (
                ModelSystemRecord(
                    model_system_id="MODEL_SCD_DEMO_001",
                    name="Illustrative sickle-cell disease model",
                    model_type="animal model",
                    disease_id="MONDO_0011382",
                    organism="Mus musculus",
                    stage=stage,
                    identifiers={"canonical": "MODEL_SCD_DEMO_001"},
                    supporting_evidence=(evidence_ids[1],),
                    attributes={"fixture": True},
                ),
            )
        elif stage is Stage.CLINICAL_STRATEGY:
            clinical_evidence_id = evidence_additions[0].evidence_id
            safety_evidence_id = evidence_additions[1].evidence_id
            trial_identity_id = "scd-demo-clinical-trial-identity"
            candidate_arm_evidence_id = "scd-demo-clinical-candidate-arm"
            comparator_arm_evidence_id = "scd-demo-clinical-comparator-arm"
            population_evidence_id = "scd-demo-clinical-population"
            endpoint_evidence_id = "scd-demo-clinical-endpoint"
            safety_identity_id = "scd-demo-clinical-safety"
            intervention_record = InterventionRecord(
                intervention_id="scd-demo-candidate",
                name="Illustrative small-molecule candidate",
                candidate_id="scd-demo-candidate",
                disease_id="MONDO_0011382",
                modality="small molecule",
                stage=stage,
                identifiers={"canonical": "scd-demo-candidate"},
                supporting_evidence=(
                    clinical_evidence_id,
                    safety_evidence_id,
                    trial_identity_id,
                ),
                attributes={
                    "fixture": True,
                    "clinical_trial_ids": ["NCT00000001"],
                },
            )
            intervention_updates = (intervention_record,)
            trial_updates = (
                TrialRecord(
                    trial_id="NCT00000001",
                    registry="ClinicalTrials.gov",
                    intervention_id=intervention_record.intervention_id,
                    disease_id="MONDO_0011382",
                    stage=stage,
                    identifiers={
                        "canonical": "NCT00000001",
                        "clinicaltrials_gov": "NCT00000001",
                    },
                    supporting_evidence=(
                        clinical_evidence_id,
                        safety_evidence_id,
                        trial_identity_id,
                    ),
                    attributes={"fixture": True},
                ),
            )
            trial_design_updates = (
                TrialDesignRecord(
                    design_id="NCT00000001:design",
                    trial_id="NCT00000001",
                    intervention_id=intervention_record.intervention_id,
                    disease_id="MONDO_0011382",
                    stage=stage,
                    arms=(
                        TrialArmRecord(
                            arm_id="NCT00000001:arm:OG000",
                            trial_id="NCT00000001",
                            label="Illustrative candidate arm",
                            arm_type="EXPERIMENTAL",
                            role=TrialArmRole.CANDIDATE,
                            stage=stage,
                            intervention_id=intervention_record.intervention_id,
                            intervention_names=(
                                "Drug: Illustrative small-molecule candidate",
                            ),
                            identifiers={
                                "canonical": "NCT00000001:arm:OG000",
                                "clinicaltrials_gov_group": "OG000",
                            },
                            supporting_evidence=(candidate_arm_evidence_id,),
                            attributes={"fixture": True},
                        ),
                        TrialArmRecord(
                            arm_id="NCT00000001:arm:OG001",
                            trial_id="NCT00000001",
                            label="Illustrative comparator arm",
                            arm_type="ACTIVE_COMPARATOR",
                            role=TrialArmRole.COMPARATOR,
                            stage=stage,
                            intervention_names=("Drug: Illustrative comparator",),
                            identifiers={
                                "canonical": "NCT00000001:arm:OG001",
                                "clinicaltrials_gov_group": "OG001",
                            },
                            supporting_evidence=(comparator_arm_evidence_id,),
                            attributes={"fixture": True},
                        ),
                    ),
                    populations=(
                        TrialPopulationRecord(
                            population_id="NCT00000001:population:primary-0",
                            trial_id="NCT00000001",
                            disease_id="MONDO_0011382",
                            description="Illustrative randomized population",
                            enrollment_count=120,
                            enrollment_type="ACTUAL",
                            sex="ALL",
                            minimum_age="18 Years",
                            maximum_age="75 Years",
                            healthy_volunteers=False,
                            stage=stage,
                            identifiers={
                                "canonical": "NCT00000001:population:primary-0"
                            },
                            supporting_evidence=(population_evidence_id,),
                            attributes={"fixture": True},
                        ),
                    ),
                    endpoints=(
                        TrialEndpointRecord(
                            endpoint_id="NCT00000001:endpoint:primary-0",
                            trial_id="NCT00000001",
                            population_id="NCT00000001:population:primary-0",
                            name="Illustrative primary endpoint",
                            outcome_type="PRIMARY",
                            time_frame="24 months",
                            parameter_type="MEDIAN",
                            unit="months",
                            reporting_status="POSTED",
                            arm_ids=(
                                "NCT00000001:arm:OG000",
                                "NCT00000001:arm:OG001",
                            ),
                            stage=stage,
                            identifiers={
                                "canonical": "NCT00000001:endpoint:primary-0",
                                "clinicaltrials_gov_outcome": (
                                    "NCT00000001:outcome:0"
                                ),
                            },
                            supporting_evidence=(
                                endpoint_evidence_id,
                                clinical_evidence_id,
                            ),
                            attributes={"fixture": True},
                        ),
                    ),
                    safety_records=(
                        TrialSafetyRecord(
                            safety_id=(
                                "NCT00000001:safety:serious-adverse-events"
                            ),
                            trial_id="NCT00000001",
                            event_category="SERIOUS",
                            reporting_status="POSTED",
                            time_frame=(
                                "From first dose through 30 days after last dose"
                            ),
                            event_term_count=2,
                            arm_summaries=(
                                TrialSafetyArmRecord(
                                    safety_arm_id=(
                                        "NCT00000001:safety:"
                                        "serious-adverse-events:arm:EG000"
                                    ),
                                    safety_id=(
                                        "NCT00000001:safety:serious-adverse-events"
                                    ),
                                    trial_id="NCT00000001",
                                    arm_id="NCT00000001:arm:OG000",
                                    role=TrialArmRole.CANDIDATE,
                                    source_group_id="EG000",
                                    source_group_title=(
                                        "Illustrative candidate arm"
                                    ),
                                    serious_num_affected=12,
                                    serious_num_at_risk=60,
                                    stage=stage,
                                    identifiers={
                                        "canonical": (
                                            "NCT00000001:safety:"
                                            "serious-adverse-events:arm:EG000"
                                        ),
                                        (
                                            "clinicaltrials_gov_"
                                            "adverse_event_group"
                                        ): "EG000",
                                    },
                                    supporting_evidence=(
                                        safety_identity_id,
                                        safety_evidence_id,
                                    ),
                                    attributes={"fixture": True},
                                ),
                                TrialSafetyArmRecord(
                                    safety_arm_id=(
                                        "NCT00000001:safety:"
                                        "serious-adverse-events:arm:EG001"
                                    ),
                                    safety_id=(
                                        "NCT00000001:safety:serious-adverse-events"
                                    ),
                                    trial_id="NCT00000001",
                                    arm_id="NCT00000001:arm:OG001",
                                    role=TrialArmRole.COMPARATOR,
                                    source_group_id="EG001",
                                    source_group_title=(
                                        "Illustrative comparator arm"
                                    ),
                                    serious_num_affected=18,
                                    serious_num_at_risk=60,
                                    stage=stage,
                                    identifiers={
                                        "canonical": (
                                            "NCT00000001:safety:"
                                            "serious-adverse-events:arm:EG001"
                                        ),
                                        (
                                            "clinicaltrials_gov_"
                                            "adverse_event_group"
                                        ): "EG001",
                                    },
                                    supporting_evidence=(
                                        safety_identity_id,
                                        safety_evidence_id,
                                    ),
                                    attributes={"fixture": True},
                                ),
                            ),
                            stage=stage,
                            description=(
                                "Posted aggregate serious adverse events for the "
                                "illustrative safety population."
                            ),
                            identifiers={
                                "canonical": (
                                    "NCT00000001:safety:serious-adverse-events"
                                ),
                                "clinicaltrials_gov": "NCT00000001",
                            },
                            supporting_evidence=(
                                safety_identity_id,
                                safety_evidence_id,
                            ),
                            attributes={"fixture": True},
                        ),
                    ),
                    identifiers={
                        "canonical": "NCT00000001:design",
                        "clinicaltrials_gov": "NCT00000001",
                    },
                    supporting_evidence=evidence_ids,
                    attributes={"fixture": True},
                ),
            )
        elif stage is Stage.REGULATORY_POSTMARKET:
            assert intervention_record is not None
            intervention_record = InterventionRecord(
                intervention_id=intervention_record.intervention_id,
                name=intervention_record.name,
                candidate_id=intervention_record.candidate_id,
                disease_id=intervention_record.disease_id,
                modality=intervention_record.modality,
                stage=stage,
                identifiers={
                    **dict(intervention_record.identifiers),
                    "ema_asset": "Illustrative small-molecule candidate",
                },
                supporting_evidence=(
                    *intervention_record.supporting_evidence,
                    *evidence_ids,
                ),
                attributes={
                    **dict(intervention_record.attributes),
                    "ema_status": "illustrative assessed status",
                },
            )
            intervention_updates = (intervention_record,)

        next_stage = (
            DEFAULT_STAGE_SEQUENCE[index + 1]
            if index + 1 < len(DEFAULT_STAGE_SEQUENCE)
            else None
        )
        packets.append(
            DecisionPacket(
                packet_id=f"scd-demo-packet-{index + 1:02d}",
                program_id=initial_state.program_id,
                expected_state_version=index,
                stage=stage,
                decision=Decision.ADVANCE,
                rationale="Illustrative evidence and the configured stage gate support advance.",
                confidence=0.8,
                actions=(
                    ActionRecord(
                        action_id=f"scd-demo-action-{index + 1:02d}",
                        action_type=ActionType.RETRIEVE_EVIDENCE,
                        purpose=f"Populate the typed evidence ledger for {stage.value}.",
                        cost=0.25,
                        evidence_ids=evidence_ids,
                    ),
                ),
                evidence_additions=tuple(evidence_additions),
                claim_updates=claim_updates,
                disease_updates=disease_updates,
                target_updates=target_updates,
                candidate_updates=candidate_updates,
                assay_updates=assay_updates,
                model_system_updates=model_system_updates,
                intervention_updates=intervention_updates,
                trial_updates=trial_updates,
                trial_design_updates=trial_design_updates,
                next_stage=next_stage,
                created_at=datetime(2025, 1, 1, index, tzinfo=timezone.utc),
                metadata={"fixture": "illustrative_scd_control_plane"},
            )
        )
    return environment, initial_state, tuple(packets)


def run_scd_control_plane_demo() -> tuple[ProgramState, tuple[TransitionResult, ...]]:
    environment, state, packets = build_scd_control_plane_demo()
    results: list[TransitionResult] = []
    for packet in packets:
        result = environment.transition(state, packet)
        results.append(result)
        if not result.applied:
            break
        state = result.state
    return state, tuple(results)


def build_demo_report() -> dict[str, object]:
    state, results = run_scd_control_plane_demo()
    transitions = []
    for result in results:
        transitions.append(
            {
                "packet_id": result.packet.packet_id,
                "stage": result.packet.stage.value,
                "decision": result.packet.decision.value,
                "applied": result.applied,
                "reason": result.reason,
                "blocking_codes": [item.code for item in result.blocking_results],
                "state_version_after": result.state.version,
                "stage_after": result.state.current_stage.value,
                "status_after": result.state.status.value,
            }
        )
    return {
        "demo": "illustrative_scd_control_plane",
        "non_benchmark": True,
        "completed": state.status is ProgramStatus.COMPLETED,
        "transition_count": len(results),
        "transitions": transitions,
        "final_state": {
            "program_id": state.program_id,
            "version": state.version,
            "stage": state.current_stage.value,
            "status": state.status.value,
            "evidence_count": len(state.evidence),
            "claim_count": len(state.claims),
            "candidate_count": len(state.candidates),
            "disease_count": len(state.diseases),
            "target_count": len(state.targets),
            "assay_count": len(state.assays),
            "model_system_count": len(state.model_systems),
            "intervention_count": len(state.interventions),
            "trial_count": len(state.trials),
            "trial_design_count": len(state.trial_designs),
            "trial_arm_count": sum(
                len(design.arms) for design in state.trial_designs
            ),
            "trial_population_count": sum(
                len(design.populations) for design in state.trial_designs
            ),
            "trial_endpoint_count": sum(
                len(design.endpoints) for design in state.trial_designs
            ),
            "trial_safety_count": sum(
                len(design.safety_records) for design in state.trial_designs
            ),
            "trial_safety_arm_count": sum(
                len(safety.arm_summaries)
                for design in state.trial_designs
                for safety in design.safety_records
            ),
            "action_count": len(state.action_history),
            "accepted_packet_count": len(state.packet_history),
            "budget_spent": state.budget.spent,
            "budget_remaining": state.budget.remaining,
        },
    }


def main() -> int:
    report = build_demo_report()
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["completed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
