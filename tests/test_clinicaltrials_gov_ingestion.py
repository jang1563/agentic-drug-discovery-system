from __future__ import annotations

import copy
import json
import re
import subprocess
import sys
import tempfile
import unittest
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from jsonschema import Draft202012Validator

from adapters.execution_registry import register_existing_adapters
from adapters.pinned_evidence_adapter import PinnedEvidenceAdapter
from agentic_drug_discovery import (
    ActionType,
    BoundedPlanner,
    BoundedStageRunner,
    BudgetState,
    CandidateRecord,
    CandidateStatus,
    Decision,
    DecisionPacket,
    DiseaseRecord,
    EpisodeArm,
    EpisodeMatchKey,
    EvidenceEvent,
    EvidenceRelation,
    FailureCause,
    GatedDiscoveryEnvironment,
    MatchedEpisodePair,
    ProgramState,
    PromotionContext,
    PromotionStatus,
    SourceReference,
    Stage,
    StagePlan,
    TargetRecord,
    ToolCallSpec,
    ToolRegistry,
    build_default_semantic_mapper_registry,
    capture_source_bytes,
    compile_pinned_evidence_manifest,
    evaluate_matched_pair,
    evaluation_episode_from_stage_run,
    extract_clinicaltrials_gov_ingestion_job,
    normalize_clinicaltrials_gov_ingestion_job,
    trial_design_record_from_dict,
    write_source_bundle,
)


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "rl_env/specs/clinicaltrials_gov_ingestion_job.example.json"
SCHEMA = ROOT / "rl_env/specs/clinicaltrials_gov_ingestion_job.schema.json"
SOURCE = ROOT / "tests/fixtures/clinicaltrials_gov_study.synthetic.json"
REQUEST_AT = datetime(2025, 1, 2, 1, tzinfo=timezone.utc)
COMPLETED_AT = REQUEST_AT + timedelta(minutes=1)
SHA256 = re.compile(r"[0-9a-f]{64}")


def clinical_job() -> dict:
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


def clinical_bundle(*, payload: bytes | None = None):
    return capture_source_bytes(
        payload or SOURCE.read_bytes(),
        receipt_id="ctgov-test-trial",
        source_id="clinicaltrials-gov-NCT00000001",
        source_version="clinicaltrials-gov-NCT00000001-version-2025-01-01",
        locator="https://clinicaltrials.gov/api/v2/studies/NCT00000001",
        retrieved_at=datetime(2025, 1, 2, tzinfo=timezone.utc),
        media_type="application/json",
        capture_method="https",
        http_status=200,
    )


def clinical_manifest() -> tuple[dict, dict]:
    bundle = clinical_bundle()
    extracted = extract_clinicaltrials_gov_ingestion_job(clinical_job(), bundle)
    return compile_pinned_evidence_manifest(
        extracted,
        {bundle.receipt.receipt_id: bundle},
    )


def clinical_state(*, program_id: str) -> ProgramState:
    disease_evidence = EvidenceEvent(
        evidence_id=f"{program_id}:disease",
        stage=Stage.DISEASE_CONTEXT,
        subject="test disease",
        predicate="disease_context_resolved",
        object_value="MONDO_TEST",
        source=SourceReference(
            source_id="test-disease-source",
            source_version="fixture-2024-01-01",
            locator="https://example.invalid/test-disease",
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


def clinical_plan() -> StagePlan:
    return StagePlan(
        plan_id="pinned-clinical-trial-design-plan",
        stage=Stage.CLINICAL_STRATEGY,
        calls=(
            ToolCallSpec(
                call_id="clinical-design",
                tool_id="pinned_evidence",
                operation="clinical_trial_design",
                action_type=ActionType.QUERY_DATABASE,
                purpose="Resolve one exact posted endpoint and its design identities.",
                arguments={
                    "candidate_id": "CHEMBL_TEST",
                    "disease_id": "MONDO_TEST",
                    "trial_id": "NCT00000001",
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


def run_manifest(
    manifest: dict,
    *,
    program_id: str,
    state: ProgramState | None = None,
):
    selected_state = state or clinical_state(program_id=program_id)
    candidate = selected_state.candidates[0]
    registry = register_existing_adapters(
        ToolRegistry(clock=lambda: COMPLETED_AT),
        pinned_evidence=PinnedEvidenceAdapter(manifest),
    )
    runner = BoundedStageRunner(
        tool_registry=registry,
        mapper_registry=build_default_semantic_mapper_registry(
            target_association_minimum_score=0.5
        ),
        planner=BoundedPlanner(clock=lambda: REQUEST_AT),
        clock=lambda: COMPLETED_AT,
    )
    return runner.run_stage(
        run_id=f"{program_id}-run",
        state=selected_state,
        stage_plan=clinical_plan(),
        promotion_contexts={
            "clinical-design": PromotionContext(
                observed_at=date(2024, 6, 1),
                available_at=date(2024, 9, 15),
                subject=candidate.name,
                object_value=selected_state.disease,
                confidence=0.9,
                candidate_id=candidate.candidate_id,
                candidate_name=candidate.name,
                modality=candidate.modality,
                biological_context={
                    "disease_id": "MONDO_TEST",
                    "intervention_id": "CHEMBL_TEST",
                },
            )
        },
    )


class ClinicalTrialsGovIngestionTests(unittest.TestCase):
    def test_ra_acr20_risk_difference_snapshot_retains_hold_boundary(self) -> None:
        snapshot_path = (
            ROOT / "docs/ra_acr20_risk_difference_validation_snapshot.json"
        )
        snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
        self.assertEqual(
            snapshot["schema_version"],
            "adds.ra-acr20-risk-difference-validation-snapshot.v1",
        )
        policy = snapshot["public_payload_policy"]
        self.assertFalse(policy["contains_source_bytes"])
        self.assertFalse(policy["contains_reviewer_text"])
        self.assertFalse(policy["contains_review_jobs"])
        self.assertFalse(policy["contains_local_paths"])
        self.assertTrue(policy["external_artifacts_required_for_exact_replay"])

        selected = snapshot["selected_trial"]
        self.assertEqual(selected["trial_id"], "NCT00383188")
        for field_name in (
            "source_content_sha256",
            "sanitized_provider_output_sha256",
            "compiled_manifest_sha256",
            "compile_review_sha256",
        ):
            self.assertRegex(selected[field_name], SHA256)
        effect = selected["endpoint"]["effect"]
        self.assertEqual(effect["canonical_measure"], "risk_difference")
        self.assertEqual(effect["direction"], "null_or_uncertain")
        self.assertEqual(
            effect["confidence_interval_width_percentage_points"],
            31.229,
        )
        self.assertLess(effect["confidence_interval_lower"], 0)
        self.assertGreater(effect["confidence_interval_upper"], 0)
        self.assertEqual(
            selected["execution"],
            {
                "run_status": "committed",
                "promotion_status": "promoted",
                "recommended_decision": "hold",
                "final_stage": "clinical_strategy",
                "bounded_interpretation": (
                    "posted_primary_risk_difference_null_or_uncertain"
                ),
            },
        )
        self.assertFalse(selected["population_boundary"]["rolewise_counts_match"])
        self.assertFalse(
            selected["population_boundary"]["same_participants_inferred"]
        )
        self.assertFalse(
            snapshot["decision_layer"]["real_multi_trial_additive_tensor_compiled"]
        )
        self.assertEqual(len(snapshot["screened_controls"]), 4)
        for item in snapshot["screened_controls"]:
            self.assertRegex(item["source_content_sha256"], SHA256)
            self.assertTrue(item["reason_codes"])
        self.assertFalse(snapshot["claims"]["cross_trial_pooling_performed"])
        self.assertFalse(snapshot["claims"]["clinical_acceptability_inferred"])
        self.assertFalse(snapshot["claims"]["therapeutic_recommendation_made"])

        encoded = snapshot_path.read_text(encoding="utf-8")
        self.assertNotRegex(encoded, r"/(Users|home|tmp|private)/")
        self.assertNotIn("eligibilityCriteria", encoded)
        self.assertNotIn("raw_payload", encoded)

    def test_uc_maintenance_risk_difference_snapshot_is_bounded(self) -> None:
        snapshot_path = (
            ROOT
            / "docs/uc_maintenance_risk_difference_validation_snapshot.json"
        )
        snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
        self.assertEqual(
            snapshot["schema_version"],
            "adds.uc-maintenance-risk-difference-validation-snapshot.v1",
        )
        policy = snapshot["public_payload_policy"]
        self.assertFalse(policy["contains_source_bytes"])
        self.assertFalse(policy["contains_reviewer_text"])
        self.assertFalse(policy["contains_review_jobs"])
        self.assertFalse(policy["contains_local_paths"])
        self.assertTrue(policy["external_artifacts_required_for_exact_replay"])

        selected = snapshot["selected_trial"]
        self.assertEqual(selected["trial_id"], "NCT01458574")
        for field_name in (
            "source_content_sha256",
            "sanitized_provider_output_sha256",
            "compiled_manifest_sha256",
            "compile_review_sha256",
        ):
            self.assertRegex(selected[field_name], SHA256)
        self.assertEqual(
            len(
                {
                    selected[field_name]
                    for field_name in (
                        "source_content_sha256",
                        "sanitized_provider_output_sha256",
                        "compiled_manifest_sha256",
                        "compile_review_sha256",
                    )
                }
            ),
            4,
        )
        self.assertEqual(
            selected["endpoint"]["effect"],
            {
                "registry_parameter_type": "Difference in percentage",
                "canonical_measure": "risk_difference",
                "scale": "percentage_points",
                "null_value": 0.0,
                "estimate": 23.2,
                "confidence_interval_percent": 95.0,
                "confidence_interval_lower": 15.3,
                "confidence_interval_upper": 31.2,
                "p_value_relation": "lt",
                "p_value": 0.0001,
                "direction": "benefit",
            },
        )
        self.assertEqual(
            selected["population_alignment"],
            {
                "treatment_phase": "maintenance",
                "study_enrollment_count": 593,
                "endpoint_analysis_participant_count": 396,
                "safety_at_risk_participant_count": 396,
                "rolewise_counts_match": True,
                "same_participants_inferred": False,
            },
        )
        self.assertEqual(
            [item["role"] for item in selected["arms"]],
            ["candidate", "comparator"],
        )
        self.assertEqual(
            selected["execution"],
            {
                "run_status": "committed",
                "promotion_status": "promoted",
                "recommended_decision": "advance",
                "final_stage": "regulatory_postmarket",
                "bounded_interpretation": (
                    "posted_primary_risk_difference_benefit"
                ),
            },
        )
        self.assertEqual(len(snapshot["screened_controls"]), 5)
        self.assertEqual(
            {item["disposition"] for item in snapshot["screened_controls"]},
            {"excluded", "deferred"},
        )
        for item in snapshot["screened_controls"]:
            self.assertRegex(item["source_content_sha256"], SHA256)
            self.assertTrue(item["reason_codes"])
        self.assertFalse(snapshot["claims"]["same_candidate_cross_trial_replication"])
        self.assertFalse(snapshot["claims"]["cross_trial_pooling_performed"])
        self.assertFalse(snapshot["claims"]["participant_identity_inferred"])
        self.assertFalse(snapshot["claims"]["clinical_acceptability_inferred"])
        self.assertFalse(snapshot["claims"]["therapeutic_recommendation_made"])

        encoded = snapshot_path.read_text(encoding="utf-8")
        self.assertNotRegex(encoded, r"/(Users|home|tmp|private)/")
        self.assertNotIn("eligibilityCriteria", encoded)
        self.assertNotIn("raw_payload", encoded)

    def test_uc_phase_population_snapshot_is_bounded_and_reproducible(self) -> None:
        snapshot = json.loads(
            (ROOT / "docs/uc_phase_population_validation_snapshot.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(
            snapshot["schema_version"],
            "adds.uc-phase-population-validation-snapshot.v1",
        )
        policy = snapshot["public_payload_policy"]
        self.assertFalse(policy["contains_source_bytes"])
        self.assertFalse(policy["contains_reviewer_text"])
        self.assertFalse(policy["contains_review_jobs"])
        self.assertFalse(policy["contains_local_paths"])
        self.assertTrue(policy["external_artifacts_required_for_exact_replay"])

        phases = {item["treatment_phase"]: item for item in snapshot["phases"]}
        self.assertEqual(phases.keys(), {"induction", "maintenance"})
        self.assertEqual(
            phases["induction"]["population_alignment"],
            {
                "treatment_phase": "induction",
                "study_enrollment_count": 1012,
                "endpoint_analysis_participant_count": 645,
                "safety_at_risk_participant_count": 645,
                "rolewise_counts_match": True,
                "same_participants_inferred": False,
            },
        )
        self.assertEqual(
            phases["maintenance"]["population_alignment"],
            {
                "treatment_phase": "maintenance",
                "study_enrollment_count": 1012,
                "endpoint_analysis_participant_count": 457,
                "safety_at_risk_participant_count": 457,
                "rolewise_counts_match": True,
                "same_participants_inferred": False,
            },
        )
        source_hashes = {
            item["artifact_hashes"]["source_content_sha256"] for item in phases.values()
        }
        self.assertEqual(
            source_hashes,
            {"fa48160bf981705439b8c3a759a2a17fbedead3d77cb3ee484afaeef16dd533c"},
        )
        for phase in phases.values():
            self.assertTrue(
                all(
                    SHA256.fullmatch(value)
                    for value in phase["artifact_hashes"].values()
                )
            )
            self.assertEqual(phase["validation"]["stage_run_status"], "committed")
            self.assertTrue(phase["validation"]["committed_history_valid"])

        boundary = snapshot["cross_phase_boundary"]
        self.assertEqual(boundary["independent_trial_count"], 1)
        self.assertFalse(boundary["pooled_effect_estimate_computed"])
        self.assertFalse(boundary["participant_overlap_inferred"])
        self.assertFalse(boundary["longitudinal_exchangeability_approved"])
        encoded = json.dumps(snapshot, sort_keys=True)
        self.assertNotIn("/tmp/", encoded)
        report = (ROOT / "docs/43_uc_phase_population_alignment.md").read_text(
            encoding="utf-8"
        )
        for phase in phases.values():
            for value in phase["artifact_hashes"].values():
                self.assertIn(value, report)

    def test_uc_provider_snapshot_preserves_uncertainty_and_phase_boundaries(
        self,
    ) -> None:
        snapshot = json.loads(
            (ROOT / "docs/uc_clinical_provider_validation_snapshot.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(
            snapshot["schema_version"],
            "adds.uc-clinical-provider-validation-snapshot.v1",
        )
        policy = snapshot["public_payload_policy"]
        self.assertFalse(policy["contains_source_bytes"])
        self.assertFalse(policy["contains_reviewer_text"])
        self.assertFalse(policy["contains_review_jobs"])
        self.assertFalse(policy["contains_local_paths"])
        self.assertTrue(policy["external_artifacts_required_for_exact_replay"])

        studies = {item["nct_id"]: item for item in snapshot["studies"]}
        self.assertEqual(studies.keys(), {"NCT01647516", "NCT02435992"})
        phase_2 = studies["NCT01647516"]
        phase_3 = studies["NCT02435992"]
        self.assertEqual(phase_2["endpoint"]["source_group_ids"], ["OG000", "OG002"])
        self.assertEqual(phase_2["endpoint"]["effect_direction"], "null_or_uncertain")
        self.assertEqual(phase_2["validation"]["accepted_decision"], "hold")
        self.assertEqual(phase_2["validation"]["final_program_status"], "held")
        self.assertEqual(phase_2["validation"]["final_stage"], "clinical_strategy")
        self.assertEqual(phase_3["endpoint"]["effect_direction"], "benefit")
        self.assertEqual(phase_3["validation"]["accepted_decision"], "advance")
        self.assertEqual(
            phase_3["validation"]["final_stage"],
            "regulatory_postmarket",
        )
        for study in studies.values():
            self.assertEqual(study["disease_id"], "MONDO:0005101")
            self.assertEqual(study["candidate_id"], "OZANIMOD")
            self.assertEqual(study["treatment_phase"], "induction")
            self.assertEqual(study["safety"]["treatment_phase"], "induction")
            self.assertEqual(study["validation"]["promotion_status"], "promoted")
            self.assertEqual(study["validation"]["trial_design_count"], 1)
            self.assertEqual(study["validation"]["new_clinical_evidence_count"], 8)
            self.assertTrue(study["validation"]["committed_history_valid"])
            self.assertTrue(
                all(
                    SHA256.fullmatch(value)
                    for value in study["artifact_hashes"].values()
                )
            )

        boundary = snapshot["cross_study_boundary"]
        self.assertFalse(boundary["pooled_effect_estimate_computed"])
        self.assertFalse(boundary["benefit_risk_acceptability_inferred"])
        self.assertFalse(boundary["maintenance_endpoint_promoted"])
        encoded = json.dumps(snapshot, sort_keys=True)
        self.assertNotIn("/tmp/", encoded)
        report = (ROOT / "docs/42_uc_provider_validation.md").read_text(
            encoding="utf-8"
        )
        for study in studies.values():
            self.assertIn(study["nct_id"], report)
            for value in study["artifact_hashes"].values():
                self.assertIn(value, report)

    def test_public_validation_snapshot_is_payload_free_and_documented(self) -> None:
        snapshot = json.loads(
            (ROOT / "docs/clinical_provider_validation_snapshot.json").read_text(
                encoding="utf-8"
            )
        )
        policy = snapshot["public_payload_policy"]
        self.assertEqual(
            snapshot["schema_version"],
            "adds.clinical-provider-validation-snapshot.v2",
        )
        self.assertFalse(policy["contains_source_bytes"])
        self.assertFalse(policy["contains_reviewer_text"])
        self.assertFalse(policy["contains_review_jobs"])
        self.assertFalse(policy["contains_local_paths"])
        self.assertTrue(policy["external_artifacts_required_for_exact_replay"])

        provider = snapshot["provider"]
        design = snapshot["selected_design"]
        hashes = list(snapshot["artifact_hashes"].values())
        self.assertTrue(all(SHA256.fullmatch(value) for value in hashes))
        self.assertEqual(design["design_id"], f"{provider['nct_id']}:design")
        self.assertEqual(len(design["arms"]), 2)
        self.assertEqual(
            {arm["role"] for arm in design["arms"]}, {"candidate", "comparator"}
        )
        safety = design["safety"]
        self.assertEqual(safety["event_category"], "SERIOUS")
        self.assertEqual(len(safety["arms"]), 2)
        self.assertIn("acceptability", safety["bounded_interpretation"])
        self.assertIn("not inferred", safety["bounded_interpretation"])

        live = snapshot["live_stage_validation"]
        matched = snapshot["matched_pair"]
        self.assertEqual(live["decision"], "advance")
        self.assertTrue(live["committed_history_valid"])
        self.assertEqual(live["new_clinical_evidence_count"], 8)
        self.assertEqual(live["safety_record_count"], 1)
        self.assertEqual(live["safety_arm_count"], 2)
        self.assertEqual(matched["success"]["decision"], "advance")
        self.assertEqual(matched["failure"]["decision"], "defer")
        self.assertEqual(matched["failure"]["new_clinical_evidence_count"], 0)
        self.assertEqual(matched["failure"]["new_trial_design_count"], 0)
        self.assertEqual(matched["balanced_accuracy"], 1.0)

        human_report = (ROOT / "docs/21_clinical_provider_ingestion.md").read_text(
            encoding="utf-8"
        )
        documented_values = [
            provider["nct_id"],
            provider["registry_version"],
            provider["source_version"],
            design["arms"][0]["source_group_id"],
            design["arms"][1]["source_group_id"],
            safety["safety_id"],
            safety["arms"][0]["source_group_id"],
            safety["arms"][1]["source_group_id"],
            live["promotion_code"],
            matched["failure"]["promotion_code"],
            *hashes,
        ]
        for value in documented_values:
            self.assertIn(str(value), human_report)

    def test_example_round_trips_and_validates_against_schema(self) -> None:
        source = clinical_job()
        self.assertEqual(normalize_clinicaltrials_gov_ingestion_job(source), source)
        Draft202012Validator.check_schema(json.loads(SCHEMA.read_text()))
        Draft202012Validator(json.loads(SCHEMA.read_text())).validate(source)

    def test_endpoint_and_safety_treatment_phases_must_match(self) -> None:
        job = clinical_job()
        job["trial"]["safety"]["treatment_phase"] = "maintenance"

        with self.assertRaisesRegex(ValueError, "treatment phases must match"):
            normalize_clinicaltrials_gov_ingestion_job(job)

    def test_invalid_ratio_analysis_fails_during_job_normalization(self) -> None:
        cases = (("p_value", 1.01), ("parameter_value", 1.2))

        for field_name, value in cases:
            with self.subTest(field_name=field_name):
                job = clinical_job()
                job["trial"]["endpoint"]["analysis"][field_name] = value
                with self.assertRaisesRegex(ValueError, "effect analysis is invalid"):
                    normalize_clinicaltrials_gov_ingestion_job(job)

    def test_source_declared_treatment_phase_cannot_be_omitted(self) -> None:
        source = json.loads(SOURCE.read_text())
        source["protocolSection"]["identificationModule"]["officialTitle"] = (
            "An Induction Study of Test Drug"
        )
        payload = (json.dumps(source, sort_keys=True) + "\n").encode()

        with self.assertRaisesRegex(ValueError, "declares a treatment phase"):
            extract_clinicaltrials_gov_ingestion_job(
                clinical_job(),
                clinical_bundle(payload=payload),
            )

    def test_extractor_binds_design_and_removes_source_payload(self) -> None:
        extracted = extract_clinicaltrials_gov_ingestion_job(
            clinical_job(), clinical_bundle()
        )
        record = extracted["records"][0]
        metadata = record["metadata"]

        self.assertEqual(record["predicate"], "clinical_trial_design_supported")
        self.assertEqual(metadata["provider_id"], "clinicaltrials_gov")
        self.assertEqual(
            metadata["endpoint"]["analysis"]["parameter_type"],
            "Hazard Ratio (HR)",
        )
        self.assertEqual(
            [item["role"] for item in metadata["arms"]],
            ["candidate", "comparator"],
        )
        self.assertEqual(
            [item["role"] for item in metadata["safety"]["arms"]],
            ["candidate", "comparator"],
        )
        self.assertEqual(metadata["safety"]["event_category"], "SERIOUS")
        self.assertEqual(metadata["safety"]["event_term_count"], 2)
        self.assertEqual(
            metadata["population_alignment"],
            {
                "treatment_phase": "not_applicable",
                "study_enrollment_count": 120,
                "endpoint_analysis_participant_count": 120,
                "safety_at_risk_participant_count": 120,
                "rolewise_counts_match": True,
                "same_participants_inferred": False,
            },
        )
        encoded = json.dumps(extracted, sort_keys=True).casefold()
        self.assertNotIn("eligibilitycriteria", encoded)
        self.assertNotIn("protocolsection", encoded)
        self.assertNotIn("resultsection", encoded)
        self.assertNotIn("raw_payload", encoded)

    def test_rolewise_population_count_difference_is_preserved(self) -> None:
        source = json.loads(SOURCE.read_text())
        job = clinical_job()
        source["protocolSection"]["identificationModule"]["officialTitle"] = (
            "An Induction Study of Test Drug"
        )
        job["trial"]["endpoint"]["treatment_phase"] = "induction"
        job["trial"]["safety"]["treatment_phase"] = "induction"
        source["resultsSection"]["adverseEventsModule"]["eventGroups"][1][
            "seriousNumAtRisk"
        ] = 59
        job["trial"]["safety"]["arms"][1]["serious_num_at_risk"] = 59
        payload = (json.dumps(source, sort_keys=True) + "\n").encode()
        bundle = clinical_bundle(payload=payload)
        extracted = extract_clinicaltrials_gov_ingestion_job(job, bundle)
        alignment = extracted["records"][0]["metadata"]["population_alignment"]

        self.assertEqual(alignment["endpoint_analysis_participant_count"], 120)
        self.assertEqual(alignment["safety_at_risk_participant_count"], 119)
        self.assertFalse(alignment["rolewise_counts_match"])
        self.assertFalse(alignment["same_participants_inferred"])
        manifest, _ = compile_pinned_evidence_manifest(
            extracted,
            {bundle.receipt.receipt_id: bundle},
        )
        result = run_manifest(manifest, program_id="clinical-design-count-difference")
        self.assertEqual(result.promotions[0].status, PromotionStatus.PROMOTED)
        design_alignment = result.final_state.trial_designs[0].attributes[
            "population_alignment"
        ]
        self.assertEqual(dict(design_alignment), alignment)

    def test_maintenance_phase_accepts_bounded_intervention_title_qualifier(
        self,
    ) -> None:
        source = json.loads(SOURCE.read_text())
        job = clinical_job()
        job["trial"]["endpoint"]["treatment_phase"] = "maintenance"
        job["trial"]["safety"]["treatment_phase"] = "maintenance"
        source["protocolSection"]["identificationModule"]["officialTitle"] = (
            "A Maintenance Study of Test Drug"
        )
        outcome_groups = source["resultsSection"]["outcomeMeasuresModule"][
            "outcomeMeasures"
        ][0]["groups"]
        outcome_groups[0]["title"] = "Test Drug (Maintenance Period)"
        outcome_groups[1]["title"] = "Comparator Drug (Maintenance Period)"
        job["trial"]["arms"][0]["source_group_title"] = outcome_groups[0]["title"]
        job["trial"]["arms"][1]["source_group_title"] = outcome_groups[1]["title"]
        safety_groups = source["resultsSection"]["adverseEventsModule"]["eventGroups"]
        safety_groups[0]["title"] = (
            "Intervention (Maintenance Period): Test Drug 100 mg"
        )
        safety_groups[1]["title"] = "Comparator Drug (Maintenance Period)"
        job["trial"]["safety"]["arms"][0]["source_group_title"] = safety_groups[0][
            "title"
        ]
        job["trial"]["safety"]["arms"][1]["source_group_title"] = safety_groups[1][
            "title"
        ]
        payload = (json.dumps(source, sort_keys=True) + "\n").encode()

        extracted = extract_clinicaltrials_gov_ingestion_job(
            job,
            clinical_bundle(payload=payload),
        )

        self.assertEqual(
            extracted["records"][0]["metadata"]["population_alignment"][
                "treatment_phase"
            ],
            "maintenance",
        )

    def test_bounded_registry_harmonization_preserves_source_values(self) -> None:
        source = json.loads(SOURCE.read_text())
        job = clinical_job()
        outcome = source["resultsSection"]["outcomeMeasuresModule"]["outcomeMeasures"][
            0
        ]
        outcome["classes"][0]["categories"][0]["measurements"][0]["value"] = "NA"
        job["trial"]["arms"][0]["measurement"]["value"] = "NA"
        analysis = outcome["analyses"][0]
        analysis["pValue"] = "0.01"
        analysis["paramType"] = "Cox Proportional Hazard"
        job_analysis = job["trial"]["endpoint"]["analysis"]
        job_analysis["p_value_relation"] = "eq"
        job_analysis["parameter_type"] = "Cox Proportional Hazard"
        outcome["groups"][0]["title"] = "Test Drug 100mg"
        job["trial"]["arms"][0]["source_group_title"] = "Test Drug 100mg"
        source_safety = source["resultsSection"]["adverseEventsModule"]
        source_safety["eventGroups"][0]["title"] = "Test Drug 100 mg (On-treatment)"
        job["trial"]["safety"]["arms"][0]["source_group_title"] = (
            "Test Drug 100 mg (On-treatment)"
        )
        payload = (json.dumps(source, sort_keys=True) + "\n").encode()

        extracted = extract_clinicaltrials_gov_ingestion_job(
            job,
            clinical_bundle(payload=payload),
        )
        metadata = extracted["records"][0]["metadata"]

        self.assertEqual(metadata["arms"][0]["measurement"]["value"], "NA")
        self.assertEqual(metadata["endpoint"]["analysis"]["p_value_relation"], "eq")
        self.assertEqual(
            metadata["endpoint"]["analysis"]["parameter_type"],
            "Cox Proportional Hazard",
        )
        self.assertEqual(
            metadata["safety"]["arms"][0]["source_group_title"],
            "Test Drug 100 mg (On-treatment)",
        )

    def test_bounded_registry_harmonization_accepts_beneficial_odds_ratio(self) -> None:
        source = json.loads(SOURCE.read_text())
        job = clinical_job()
        source_analysis = source["resultsSection"]["outcomeMeasuresModule"][
            "outcomeMeasures"
        ][0]["analyses"][0]
        source_analysis.update(
            {
                "statisticalMethod": "Cochran-Mantel-Haenszel Test",
                "paramType": "Odds Ratio (OR)",
                "paramValue": "1.80",
                "ciLowerLimit": "1.40",
                "ciUpperLimit": "2.20",
            }
        )
        job_analysis = job["trial"]["endpoint"]["analysis"]
        job_analysis.update(
            {
                "statistical_method": "Cochran-Mantel-Haenszel Test",
                "parameter_type": "Odds Ratio (OR)",
                "parameter_value": 1.8,
                "confidence_interval_lower": 1.4,
                "confidence_interval_upper": 2.2,
            }
        )
        payload = (json.dumps(source, sort_keys=True) + "\n").encode()

        bundle = clinical_bundle(payload=payload)
        extracted = extract_clinicaltrials_gov_ingestion_job(
            job,
            bundle,
        )

        analysis = extracted["records"][0]["metadata"]["endpoint"]["analysis"]
        self.assertEqual(analysis["parameter_type"], "Odds Ratio (OR)")
        self.assertEqual(analysis["parameter_value"], 1.8)
        manifest, _ = compile_pinned_evidence_manifest(
            extracted,
            {bundle.receipt.receipt_id: bundle},
        )
        result = run_manifest(
            manifest,
            program_id="clinical-design-odds-ratio",
        )
        self.assertEqual(result.accepted_packets[0].decision, Decision.ADVANCE)
        self.assertEqual(len(result.final_state.trial_designs), 1)

    def test_percentage_point_risk_difference_advances_with_endpoint_direction(
        self,
    ) -> None:
        source = json.loads(SOURCE.read_text())
        job = clinical_job()
        outcome = source["resultsSection"]["outcomeMeasuresModule"][
            "outcomeMeasures"
        ][0]
        outcome.update(
            {
                "title": "Percentage of Participants in Remission",
                "paramType": "NUMBER",
                "unitOfMeasure": "Percentage of Participants",
            }
        )
        source["protocolSection"]["outcomesModule"]["primaryOutcomes"][0][
            "measure"
        ] = "Percentage of Participants in Remission"
        measurements = outcome["classes"][0]["categories"][0]["measurements"]
        measurements[0]["value"] = "34.3"
        measurements[1]["value"] = "11.1"
        outcome["analyses"][0].update(
            {
                "pValue": "<0.0001",
                "statisticalMethod": "CMH chi-square test",
                "paramType": "Difference in percentage",
                "paramValue": "23.2",
                "ciLowerLimit": "15.3",
                "ciUpperLimit": "31.2",
            }
        )
        endpoint = job["trial"]["endpoint"]
        endpoint.update(
            {
                "name": "Percentage of Participants in Remission",
                "parameter_type": "NUMBER",
                "unit": "Percentage of Participants",
                "favorable_direction": "higher_is_better",
            }
        )
        job["trial"]["arms"][0]["measurement"]["value"] = "34.3"
        job["trial"]["arms"][1]["measurement"]["value"] = "11.1"
        endpoint["analysis"].update(
            {
                "p_value": 0.0001,
                "statistical_method": "CMH chi-square test",
                "parameter_type": "Difference in percentage",
                "parameter_value": 23.2,
                "confidence_interval_lower": 15.3,
                "confidence_interval_upper": 31.2,
            }
        )
        payload = (json.dumps(source, sort_keys=True) + "\n").encode()
        bundle = clinical_bundle(payload=payload)
        extracted = extract_clinicaltrials_gov_ingestion_job(job, bundle)
        metadata = extracted["records"][0]["metadata"]

        self.assertEqual(metadata["effect_direction"], "benefit")
        self.assertEqual(
            metadata["endpoint"]["analysis"]["parameter_type"],
            "Difference in percentage",
        )
        manifest, _ = compile_pinned_evidence_manifest(
            extracted,
            {bundle.receipt.receipt_id: bundle},
        )
        result = run_manifest(
            manifest,
            program_id="clinical-design-risk-difference",
        )
        self.assertEqual(result.promotions[0].status, PromotionStatus.PROMOTED)
        self.assertEqual(result.accepted_packets[0].decision, Decision.ADVANCE)
        clinical_evidence = next(
            item
            for item in result.final_state.evidence
            if item.predicate == "clinical_evidence_assessed"
        )
        self.assertEqual(
            clinical_evidence.metadata["bounded_interpretation"],
            "posted_primary_risk_difference_benefit",
        )

        invalid_unit_job = copy.deepcopy(job)
        invalid_unit_job["trial"]["endpoint"]["unit"] = "participants"
        with self.assertRaisesRegex(ValueError, "effect analysis is invalid"):
            normalize_clinicaltrials_gov_ingestion_job(invalid_unit_job)

        reversed_job = copy.deepcopy(job)
        reversed_job["trial"]["arms"].reverse()
        reversed_job["trial"]["safety"]["arms"].reverse()
        reversed_job["trial"]["endpoint"]["analysis"]["source_group_ids"].reverse()
        with self.assertRaisesRegex(ValueError, "effect analysis is invalid"):
            normalize_clinicaltrials_gov_ingestion_job(reversed_job)

    def test_valid_uncertain_and_harmful_ratio_results_are_retained_on_hold(
        self,
    ) -> None:
        cases = (
            (
                "null_or_uncertain",
                "3.262",
                "0.969",
                "10.984",
                "0.0482",
            ),
            ("harm", "0.65", "0.40", "0.90", "0.02"),
        )

        for direction, estimate, lower, upper, p_value in cases:
            with self.subTest(direction=direction):
                source = json.loads(SOURCE.read_text())
                job = clinical_job()
                source_analysis = source["resultsSection"]["outcomeMeasuresModule"][
                    "outcomeMeasures"
                ][0]["analyses"][0]
                source_analysis.update(
                    {
                        "pValue": p_value,
                        "statisticalMethod": "Cochran-Mantel-Haenszel Test",
                        "paramType": "Odds Ratio (OR)",
                        "paramValue": estimate,
                        "ciLowerLimit": lower,
                        "ciUpperLimit": upper,
                    }
                )
                job_analysis = job["trial"]["endpoint"]["analysis"]
                job_analysis.update(
                    {
                        "p_value_relation": "eq",
                        "p_value": float(p_value),
                        "statistical_method": "Cochran-Mantel-Haenszel Test",
                        "parameter_type": "Odds Ratio (OR)",
                        "parameter_value": float(estimate),
                        "confidence_interval_lower": float(lower),
                        "confidence_interval_upper": float(upper),
                    }
                )
                payload = (json.dumps(source, sort_keys=True) + "\n").encode()
                bundle = clinical_bundle(payload=payload)
                extracted = extract_clinicaltrials_gov_ingestion_job(job, bundle)

                self.assertEqual(
                    extracted["records"][0]["metadata"]["effect_direction"],
                    direction,
                )
                manifest, _ = compile_pinned_evidence_manifest(
                    extracted,
                    {bundle.receipt.receipt_id: bundle},
                )
                result = run_manifest(
                    manifest,
                    program_id=f"clinical-design-{direction}",
                )

                self.assertEqual(
                    result.promotions[0].status,
                    PromotionStatus.PROMOTED,
                )
                self.assertEqual(
                    result.promotions[0].details["effect_direction"],
                    direction,
                )
                self.assertEqual(
                    result.accepted_packets[0].decision,
                    Decision.HOLD,
                )
                self.assertEqual(
                    result.final_state.current_stage, Stage.CLINICAL_STRATEGY
                )
                self.assertEqual(len(result.final_state.trial_designs), 1)
                clinical_evidence = next(
                    item
                    for item in result.final_state.evidence
                    if item.predicate == "clinical_evidence_assessed"
                )
                self.assertEqual(clinical_evidence.direction, direction)

    def test_tampered_ratio_effect_direction_abstains(self) -> None:
        bundle = clinical_bundle()
        extracted = extract_clinicaltrials_gov_ingestion_job(
            clinical_job(),
            bundle,
        )
        extracted["records"][0]["metadata"]["effect_direction"] = "harm"
        manifest, _ = compile_pinned_evidence_manifest(
            extracted,
            {bundle.receipt.receipt_id: bundle},
        )

        result = run_manifest(
            manifest,
            program_id="clinical-design-tampered-direction",
        )

        self.assertEqual(result.promotions[0].status, PromotionStatus.ABSTAINED)
        self.assertEqual(
            result.promotions[0].code,
            "pinned_clinical_design_endpoint_not_supportive",
        )
        self.assertEqual(result.accepted_packets[0].decision, Decision.DEFER)
        self.assertEqual(result.final_state.trial_designs, ())

    def test_tampered_population_alignment_abstains(self) -> None:
        bundle = clinical_bundle()
        extracted = extract_clinicaltrials_gov_ingestion_job(
            clinical_job(),
            bundle,
        )
        extracted["records"][0]["metadata"]["population_alignment"][
            "safety_at_risk_participant_count"
        ] = 121
        manifest, _ = compile_pinned_evidence_manifest(
            extracted,
            {bundle.receipt.receipt_id: bundle},
        )

        result = run_manifest(
            manifest,
            program_id="clinical-design-tampered-population-alignment",
        )

        self.assertEqual(result.promotions[0].status, PromotionStatus.ABSTAINED)
        self.assertEqual(
            result.promotions[0].code,
            "pinned_clinical_design_endpoint_not_supportive",
        )
        self.assertEqual(result.accepted_packets[0].decision, Decision.DEFER)
        self.assertEqual(result.final_state.trial_designs, ())

    def test_bounded_registry_harmonization_rejects_unfrozen_variants(self) -> None:
        cases = []

        arbitrary_measurement_source = json.loads(SOURCE.read_text())
        arbitrary_measurement_job = clinical_job()
        arbitrary_measurement_source["resultsSection"]["outcomeMeasuresModule"][
            "outcomeMeasures"
        ][0]["classes"][0]["categories"][0]["measurements"][0][
            "value"
        ] = "pending review"
        arbitrary_measurement_job["trial"]["arms"][0]["measurement"]["value"] = (
            "pending review"
        )
        cases.append(
            (
                "arbitrary-measurement",
                arbitrary_measurement_source,
                arbitrary_measurement_job,
            )
        )

        unrelated_safety_source = json.loads(SOURCE.read_text())
        unrelated_safety_job = clinical_job()
        unrelated_safety_source["resultsSection"]["adverseEventsModule"]["eventGroups"][
            0
        ]["title"] = "Unrelated Cohort"
        unrelated_safety_job["trial"]["safety"]["arms"][0]["source_group_title"] = (
            "Unrelated Cohort"
        )
        cases.append(
            (
                "unrelated-safety-title",
                unrelated_safety_source,
                unrelated_safety_job,
            )
        )

        unapproved_qualifier_source = json.loads(SOURCE.read_text())
        unapproved_qualifier_job = clinical_job()
        unapproved_qualifier_source["resultsSection"]["adverseEventsModule"][
            "eventGroups"
        ][0]["title"] = "Test Drug Exploratory Cohort"
        unapproved_qualifier_job["trial"]["safety"]["arms"][0]["source_group_title"] = (
            "Test Drug Exploratory Cohort"
        )
        cases.append(
            (
                "unapproved-safety-title-qualifier",
                unapproved_qualifier_source,
                unapproved_qualifier_job,
            )
        )

        unsupported_effect_source = json.loads(SOURCE.read_text())
        unsupported_effect_job = clinical_job()
        unsupported_effect_source["resultsSection"]["outcomeMeasuresModule"][
            "outcomeMeasures"
        ][0]["analyses"][0]["paramType"] = "Mean Difference"
        unsupported_effect_job["trial"]["endpoint"]["analysis"]["parameter_type"] = (
            "Mean Difference"
        )
        cases.append(
            (
                "unsupported-effect-alias",
                unsupported_effect_source,
                unsupported_effect_job,
            )
        )

        for name, source, job in cases:
            with self.subTest(name=name):
                payload = (json.dumps(source, sort_keys=True) + "\n").encode()
                with self.assertRaises(ValueError):
                    extract_clinicaltrials_gov_ingestion_job(
                        job,
                        clinical_bundle(payload=payload),
                    )

    def test_source_identity_arm_and_analysis_mismatches_fail_closed(self) -> None:
        cases = []

        wrong_nct = json.loads(SOURCE.read_text())
        wrong_nct["protocolSection"]["identificationModule"]["nctId"] = "NCT00000002"
        cases.append(("nct", wrong_nct, clinical_job()))

        wrong_group = clinical_job()
        wrong_group["trial"]["arms"][0]["source_group_title"] = "Other Arm"
        cases.append(("arm", json.loads(SOURCE.read_text()), wrong_group))

        wrong_analysis = clinical_job()
        wrong_analysis["trial"]["endpoint"]["analysis"]["confidence_interval_upper"] = (
            1.1
        )
        cases.append(("analysis", json.loads(SOURCE.read_text()), wrong_analysis))

        wrong_safety_group = clinical_job()
        wrong_safety_group["trial"]["safety"]["arms"][0]["serious_num_affected"] = 13
        cases.append(
            (
                "safety-summary",
                json.loads(SOURCE.read_text()),
                wrong_safety_group,
            )
        )

        missing_safety = json.loads(SOURCE.read_text())
        del missing_safety["resultsSection"]["adverseEventsModule"]
        cases.append(("safety-module", missing_safety, clinical_job()))

        wrong_safety_arm_id = clinical_job()
        wrong_safety_arm_id["trial"]["safety"]["arms"][0]["safety_arm_id"] = (
            "NCT00000001:safety:serious-adverse-events:arm:EG999"
        )
        cases.append(
            (
                "safety-arm-id",
                json.loads(SOURCE.read_text()),
                wrong_safety_arm_id,
            )
        )

        for name, source, job in cases:
            with self.subTest(name=name):
                payload = (json.dumps(source, sort_keys=True) + "\n").encode()
                with self.assertRaises(ValueError):
                    extract_clinicaltrials_gov_ingestion_job(
                        job, clinical_bundle(payload=payload)
                    )

    def test_zero_serious_event_terms_are_representable(self) -> None:
        source = json.loads(SOURCE.read_text())
        job = clinical_job()
        source_safety = source["resultsSection"]["adverseEventsModule"]
        del source_safety["seriousEvents"]
        job["trial"]["safety"]["event_term_count"] = 0
        for source_group, job_arm in zip(
            source_safety["eventGroups"],
            job["trial"]["safety"]["arms"],
            strict=True,
        ):
            source_group["seriousNumAffected"] = 0
            job_arm["serious_num_affected"] = 0
        payload = (json.dumps(source, sort_keys=True) + "\n").encode()

        extracted = extract_clinicaltrials_gov_ingestion_job(
            job,
            clinical_bundle(payload=payload),
        )

        self.assertEqual(
            extracted["records"][0]["metadata"]["safety"]["event_term_count"],
            0,
        )

    def test_unselected_zero_risk_safety_groups_allow_sparse_zero_counts(
        self,
    ) -> None:
        source = json.loads(SOURCE.read_text())
        source_safety = source["resultsSection"]["adverseEventsModule"]
        source_safety["eventGroups"].append(
            {
                "id": "EG002",
                "title": "Post-treatment Follow-up",
                "seriousNumAffected": 0,
                "seriousNumAtRisk": 0,
            }
        )
        for event in source_safety["seriousEvents"]:
            event["stats"].append({"groupId": "EG002", "numAtRisk": 0})
        payload = (json.dumps(source, sort_keys=True) + "\n").encode()

        extracted = extract_clinicaltrials_gov_ingestion_job(
            clinical_job(),
            clinical_bundle(payload=payload),
        )

        self.assertEqual(
            extracted["records"][0]["metadata"]["safety"]["event_term_count"],
            2,
        )

    def test_unselected_zero_endpoint_denominator_is_allowed(self) -> None:
        source = json.loads(SOURCE.read_text())
        outcome = source["resultsSection"]["outcomeMeasuresModule"]["outcomeMeasures"][
            0
        ]
        outcome["groups"].append({"id": "OG002", "title": "Later-period arm"})
        outcome["denoms"][0]["counts"].append({"groupId": "OG002", "value": "0"})
        payload = (json.dumps(source, sort_keys=True) + "\n").encode()

        extracted = extract_clinicaltrials_gov_ingestion_job(
            clinical_job(),
            clinical_bundle(payload=payload),
        )

        self.assertEqual(
            len(extracted["records"][0]["metadata"]["arms"]),
            2,
        )

    def test_selected_zero_risk_safety_group_still_fails(self) -> None:
        source = json.loads(SOURCE.read_text())
        source_safety = source["resultsSection"]["adverseEventsModule"]
        source_safety["eventGroups"][0]["seriousNumAffected"] = 0
        source_safety["eventGroups"][0]["seriousNumAtRisk"] = 0
        for event in source_safety["seriousEvents"]:
            stat = next(item for item in event["stats"] if item["groupId"] == "EG000")
            stat["numAtRisk"] = 0
            stat.pop("numAffected", None)
        job = clinical_job()
        job["trial"]["safety"]["arms"][0]["serious_num_affected"] = 0
        job["trial"]["safety"]["arms"][0]["serious_num_at_risk"] = 1
        payload = (json.dumps(source, sort_keys=True) + "\n").encode()

        with self.assertRaisesRegex(ValueError, "selected ClinicalTrials.gov"):
            extract_clinicaltrials_gov_ingestion_job(
                job,
                clinical_bundle(payload=payload),
            )

    def test_committed_design_rejects_role_rebinding_and_endpoint_support_removal(
        self,
    ) -> None:
        manifest, _ = clinical_manifest()
        state = run_manifest(
            manifest, program_id="clinical-design-continuity"
        ).final_state
        design = state.trial_designs[0]
        stage = state.current_stage
        arms = tuple(replace(item, stage=stage) for item in design.arms)
        populations = tuple(replace(item, stage=stage) for item in design.populations)
        endpoint = replace(design.endpoints[0], stage=stage)
        safety_records = tuple(
            replace(
                item,
                stage=stage,
                arm_summaries=tuple(
                    replace(summary, stage=stage) for summary in item.arm_summaries
                ),
            )
            for item in design.safety_records
        )

        swapped_arms = (
            replace(
                arms[0],
                role=arms[1].role,
                intervention_id=arms[1].intervention_id,
            ),
            replace(
                arms[1],
                role=arms[0].role,
                intervention_id=arms[0].intervention_id,
            ),
        )
        swapped_safety_records = (
            replace(
                safety_records[0],
                arm_summaries=(
                    replace(
                        safety_records[0].arm_summaries[0],
                        role=swapped_arms[0].role,
                    ),
                    replace(
                        safety_records[0].arm_summaries[1],
                        role=swapped_arms[1].role,
                    ),
                ),
            ),
        )
        unsupported_endpoint = replace(
            endpoint,
            supporting_evidence=(endpoint.supporting_evidence[0],),
        )
        cases = (
            (
                "arm-role-rebound",
                replace(
                    design,
                    stage=stage,
                    arms=swapped_arms,
                    populations=populations,
                    endpoints=(endpoint,),
                    safety_records=swapped_safety_records,
                ),
                "trial_arm_core_identity_rebound",
            ),
            (
                "endpoint-support-removal",
                replace(
                    design,
                    stage=stage,
                    arms=arms,
                    populations=populations,
                    endpoints=(unsupported_endpoint,),
                    safety_records=safety_records,
                ),
                "trial_endpoint_support_removed",
            ),
            (
                "safety-support-removal",
                replace(
                    design,
                    stage=stage,
                    arms=arms,
                    populations=populations,
                    endpoints=(endpoint,),
                    safety_records=(
                        replace(
                            safety_records[0],
                            supporting_evidence=(
                                safety_records[0].supporting_evidence[0],
                            ),
                        ),
                    ),
                ),
                "trial_safety_support_removed",
            ),
        )

        for packet_id, changed_design, expected_failure in cases:
            with self.subTest(packet_id=packet_id):
                result = GatedDiscoveryEnvironment().transition(
                    state,
                    DecisionPacket(
                        packet_id=packet_id,
                        program_id=state.program_id,
                        expected_state_version=state.version,
                        stage=stage,
                        decision=Decision.DEFER,
                        rationale="Continuity violations must fail closed.",
                        confidence=0.9,
                        trial_design_updates=(changed_design,),
                        created_at=COMPLETED_AT,
                    ),
                )
                self.assertFalse(result.applied)
                self.assertEqual(result.state, state)
                continuity = next(
                    item
                    for item in result.blocking_results
                    if item.code == "clinical_identity_continuity_invalid"
                )
                self.assertTrue(
                    any(
                        failure.startswith(expected_failure)
                        for failure in continuity.details["failures"]
                    )
                )

    def test_cli_reports_source_and_output_hashes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bundle_path = root / "bundle"
            output = root / "extracted.json"
            job_path = root / "job.json"
            job_path.write_text(json.dumps(clinical_job()), encoding="utf-8")
            bundle = clinical_bundle()
            write_source_bundle(bundle_path, bundle)
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "agentic_drug_discovery.ingestion_cli",
                    "extract-clinicaltrials-gov",
                    "--job",
                    str(job_path),
                    "--bundle",
                    str(bundle_path),
                    "--output",
                    str(output),
                ],
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
            )
            report = json.loads(result.stdout)
            self.assertEqual(report["provider_id"], "clinicaltrials_gov")
            self.assertEqual(report["source_content_hash"], bundle.receipt.content_hash)
            self.assertTrue(output.exists())

    def test_exact_design_advances_and_condition_mismatch_defers_atomically(
        self,
    ) -> None:
        manifest, review = clinical_manifest()
        mismatched = copy.deepcopy(manifest)
        mismatched["records"][0]["metadata"]["source_conditions"] = ["other disease"]

        success = run_manifest(manifest, program_id="clinical-design-success")
        failure = run_manifest(mismatched, program_id="clinical-design-mismatch")

        self.assertEqual(review["independent_source_count"], 1)
        self.assertEqual(success.accepted_packets[0].decision, Decision.ADVANCE)
        self.assertEqual(success.final_state.current_stage, Stage.REGULATORY_POSTMARKET)
        self.assertEqual(len(success.final_state.trial_designs), 1)
        design = success.final_state.trial_designs[0]
        self.assertEqual(len(design.arms), 2)
        self.assertEqual(len(design.populations), 1)
        self.assertEqual(len(design.endpoints), 1)
        self.assertEqual(len(design.safety_records), 1)
        self.assertEqual(len(design.safety_records[0].arm_summaries), 2)
        self.assertEqual(
            {item.role.value for item in design.safety_records[0].arm_summaries},
            {"candidate", "comparator"},
        )
        self.assertIn(
            "clinical_safety_assessed",
            {item.predicate for item in success.final_state.evidence},
        )
        self.assertEqual(
            trial_design_record_from_dict(design.to_dict()),
            design,
        )

        self.assertEqual(failure.accepted_packets[0].decision, Decision.DEFER)
        self.assertEqual(failure.final_state.evidence, failure.initial_state.evidence)
        self.assertEqual(failure.final_state.interventions, ())
        self.assertEqual(failure.final_state.trials, ())
        self.assertEqual(failure.final_state.trial_designs, ())
        self.assertEqual(failure.promotions[0].status, PromotionStatus.REJECTED)
        self.assertEqual(
            failure.promotions[0].code,
            "pinned_clinical_design_disease_alias_unapproved",
        )

        match_key = EpisodeMatchKey(
            disease="test disease",
            stage=Stage.CLINICAL_STRATEGY,
            modality="small molecule",
            population="all randomized participants",
            endpoint_family="posted primary time-to-event endpoint",
            target_or_mechanism="TEST1",
            decision_time_bin="2025",
        )
        pair_id = "clinical-design-condition-pair"
        pair = MatchedEpisodePair(
            pair_id=pair_id,
            success=evaluation_episode_from_stage_run(
                success,
                episode_id="clinical-design-condition-match",
                pair_id=pair_id,
                arm=EpisodeArm.SUCCESS,
                match_key=match_key,
                asset_or_candidate_id="CHEMBL_TEST",
                target_or_mechanism_id="TEST1",
                condition_or_context_id="MONDO_TEST",
                available_evidence_packet_id="clinical-design-match-packet",
                evaluator_label_id="clinical-design-match-label",
                gold_decision=Decision.ADVANCE,
            ),
            failure=evaluation_episode_from_stage_run(
                failure,
                episode_id="clinical-design-condition-mismatch",
                pair_id=pair_id,
                arm=EpisodeArm.FAILURE,
                match_key=match_key,
                asset_or_candidate_id="CHEMBL_TEST",
                target_or_mechanism_id="TEST1",
                condition_or_context_id="MONDO_TEST",
                available_evidence_packet_id="clinical-design-mismatch-packet",
                evaluator_label_id="clinical-design-mismatch-label",
                gold_decision=Decision.DEFER,
                failure_causes=(FailureCause.MECHANISM_OR_CONTEXT,),
            ),
        )
        score = evaluate_matched_pair(pair)
        self.assertTrue(score.both_correct)
        self.assertEqual(score.balanced_accuracy, 1.0)

    def test_source_candidate_alias_requires_preapproved_identity_binding(
        self,
    ) -> None:
        manifest, _ = clinical_manifest()
        aliased = copy.deepcopy(manifest)
        record = aliased["records"][0]
        record["subject"] = "Legacy Test Drug"
        record["metadata"]["candidate_aliases"] = ["Legacy Test Drug"]
        record["metadata"]["source_interventions"] = [
            "Drug: Legacy Test Drug",
            "Drug: Placebo",
        ]
        candidate_arm = next(
            item for item in record["metadata"]["arms"] if item["role"] == "candidate"
        )
        candidate_arm["intervention_names"] = ["Drug: Legacy Test Drug"]
        approved_state = clinical_state(program_id="clinical-design-approved-alias")
        approved_candidate = replace(
            approved_state.candidates[0],
            attributes={
                **dict(approved_state.candidates[0].attributes),
                "identity_aliases": ("Test Drug", "Legacy Test Drug"),
            },
        )
        approved_state = replace(
            approved_state,
            candidates=(approved_candidate,),
        )

        approved = run_manifest(
            aliased,
            program_id="clinical-design-approved-alias",
            state=approved_state,
        )
        unapproved = run_manifest(
            aliased,
            program_id="clinical-design-unapproved-alias",
        )
        mixed_aliases = copy.deepcopy(aliased)
        mixed_record = mixed_aliases["records"][0]
        mixed_record["metadata"]["candidate_aliases"] = [
            "Test Drug",
            "Legacy Test Drug",
        ]
        mixed_unapproved = run_manifest(
            mixed_aliases,
            program_id="clinical-design-mixed-unapproved-alias",
        )

        self.assertEqual(approved.accepted_packets[0].decision, Decision.ADVANCE)
        self.assertEqual(len(approved.final_state.trial_designs), 1)
        self.assertEqual(unapproved.accepted_packets[0].decision, Decision.DEFER)
        self.assertEqual(unapproved.final_state.trial_designs, ())
        self.assertEqual(
            unapproved.promotions[0].code,
            "pinned_clinical_design_candidate_alias_unapproved",
        )
        self.assertEqual(
            mixed_unapproved.accepted_packets[0].decision,
            Decision.DEFER,
        )
        self.assertEqual(mixed_unapproved.final_state.trial_designs, ())
        self.assertEqual(
            mixed_unapproved.promotions[0].code,
            "pinned_clinical_design_candidate_alias_unapproved",
        )

    def test_source_disease_alias_requires_preapproved_identity_binding(
        self,
    ) -> None:
        manifest, _ = clinical_manifest()
        aliased = copy.deepcopy(manifest)
        aliased["records"][0]["metadata"]["source_conditions"] = ["Legacy Disease Name"]
        approved_state = clinical_state(program_id="clinical-disease-approved-alias")
        approved_disease = replace(
            approved_state.diseases[0],
            attributes={"identity_aliases": ("Legacy Disease Name",)},
        )
        approved_state = replace(
            approved_state,
            diseases=(approved_disease,),
        )

        approved = run_manifest(
            aliased,
            program_id="clinical-disease-approved-alias",
            state=approved_state,
        )
        unapproved = run_manifest(
            aliased,
            program_id="clinical-disease-unapproved-alias",
        )

        self.assertEqual(approved.accepted_packets[0].decision, Decision.ADVANCE)
        self.assertEqual(len(approved.final_state.trial_designs), 1)
        self.assertEqual(unapproved.accepted_packets[0].decision, Decision.DEFER)
        self.assertEqual(unapproved.final_state.trial_designs, ())
        self.assertEqual(
            unapproved.promotions[0].code,
            "pinned_clinical_design_disease_alias_unapproved",
        )

    def test_missing_safety_metadata_defers_without_partial_state(self) -> None:
        manifest, _ = clinical_manifest()
        missing_safety = copy.deepcopy(manifest)
        del missing_safety["records"][0]["metadata"]["safety"]

        failure = run_manifest(
            missing_safety,
            program_id="clinical-design-missing-safety",
        )

        self.assertEqual(failure.accepted_packets[0].decision, Decision.DEFER)
        self.assertEqual(failure.final_state.evidence, failure.initial_state.evidence)
        self.assertEqual(failure.final_state.interventions, ())
        self.assertEqual(failure.final_state.trials, ())
        self.assertEqual(failure.final_state.trial_designs, ())
        self.assertEqual(
            failure.promotions[0].code,
            "pinned_clinical_design_metadata_invalid",
        )


if __name__ == "__main__":
    unittest.main()
