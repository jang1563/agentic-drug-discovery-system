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
    def test_public_validation_snapshot_is_payload_free_and_documented(self) -> None:
        snapshot = json.loads(
            (
                ROOT / "docs/clinical_provider_validation_snapshot.json"
            ).read_text(encoding="utf-8")
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
        self.assertEqual({arm["role"] for arm in design["arms"]}, {"candidate", "comparator"})
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

        human_report = (
            ROOT / "docs/21_clinical_provider_ingestion.md"
        ).read_text(encoding="utf-8")
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
        encoded = json.dumps(extracted, sort_keys=True).casefold()
        self.assertNotIn("eligibilitycriteria", encoded)
        self.assertNotIn("protocolsection", encoded)
        self.assertNotIn("resultsection", encoded)
        self.assertNotIn("raw_payload", encoded)

    def test_source_identity_arm_and_analysis_mismatches_fail_closed(self) -> None:
        cases = []

        wrong_nct = json.loads(SOURCE.read_text())
        wrong_nct["protocolSection"]["identificationModule"]["nctId"] = "NCT00000002"
        cases.append(("nct", wrong_nct, clinical_job()))

        wrong_group = clinical_job()
        wrong_group["trial"]["arms"][0]["source_group_title"] = "Other Arm"
        cases.append(("arm", json.loads(SOURCE.read_text()), wrong_group))

        wrong_analysis = clinical_job()
        wrong_analysis["trial"]["endpoint"]["analysis"][
            "confidence_interval_upper"
        ] = 1.1
        cases.append(("analysis", json.loads(SOURCE.read_text()), wrong_analysis))

        wrong_safety_group = clinical_job()
        wrong_safety_group["trial"]["safety"]["arms"][0][
            "serious_num_affected"
        ] = 13
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
        wrong_safety_arm_id["trial"]["safety"]["arms"][0][
            "safety_arm_id"
        ] = "NCT00000001:safety:serious-adverse-events:arm:EG999"
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
        populations = tuple(
            replace(item, stage=stage) for item in design.populations
        )
        endpoint = replace(design.endpoints[0], stage=stage)
        safety_records = tuple(
            replace(
                item,
                stage=stage,
                arm_summaries=tuple(
                    replace(summary, stage=stage)
                    for summary in item.arm_summaries
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
        mismatched["records"][0]["metadata"]["source_conditions"] = [
            "other disease"
        ]

        success = run_manifest(manifest, program_id="clinical-design-success")
        failure = run_manifest(mismatched, program_id="clinical-design-mismatch")

        self.assertEqual(review["independent_source_count"], 1)
        self.assertEqual(success.accepted_packets[0].decision, Decision.ADVANCE)
        self.assertEqual(
            success.final_state.current_stage, Stage.REGULATORY_POSTMARKET
        )
        self.assertEqual(len(success.final_state.trial_designs), 1)
        design = success.final_state.trial_designs[0]
        self.assertEqual(len(design.arms), 2)
        self.assertEqual(len(design.populations), 1)
        self.assertEqual(len(design.endpoints), 1)
        self.assertEqual(len(design.safety_records), 1)
        self.assertEqual(len(design.safety_records[0].arm_summaries), 2)
        self.assertEqual(
            {
                item.role.value
                for item in design.safety_records[0].arm_summaries
            },
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
            item
            for item in record["metadata"]["arms"]
            if item["role"] == "candidate"
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
        aliased["records"][0]["metadata"]["source_conditions"] = [
            "Legacy Disease Name"
        ]
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
