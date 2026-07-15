from __future__ import annotations

import json
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from adapters.execution_registry import register_existing_adapters
from adapters.pinned_evidence_adapter import PinnedEvidenceAdapter
from agentic_drug_discovery import (
    ActionType,
    BoundedPlanner,
    BoundedProgramRunner,
    BoundedStageRunner,
    BudgetState,
    CandidateRecord,
    CandidateStatus,
    Decision,
    DiseaseRecord,
    EpisodeArm,
    EpisodeMatchKey,
    FailureCause,
    EvidenceEvent,
    EvidenceRelation,
    MatchedEpisodePair,
    ProgramState,
    ProgramStatus,
    ProgramRunStatus,
    ProgramStep,
    PromotionBinding,
    PromotionContext,
    Stage,
    StagePlan,
    SourceReference,
    TargetRecord,
    ToolCallSpec,
    ToolRegistry,
    ToolRequest,
    ToolStatus,
    build_default_semantic_mapper_registry,
    capture_source_bytes,
    compile_pinned_evidence_manifest,
    evaluate_matched_pair,
    evaluation_episode_from_stage_run,
    extract_clinicaltrials_gov_ingestion_job,
    replay_program_run,
)


REQUEST_AT = datetime(2025, 1, 1, tzinfo=timezone.utc)
COMPLETED_AT = REQUEST_AT + timedelta(minutes=1)
ROOT = Path(__file__).resolve().parents[1]


class TickClock:
    def __init__(self) -> None:
        self.current = REQUEST_AT

    def __call__(self) -> datetime:
        self.current += timedelta(seconds=1)
        return self.current


def record(
    *,
    record_id: str,
    predicate: str,
    subject: str,
    object_value: str,
    source_id: str,
    content_hash: str,
    biological_context: dict,
    metadata: dict,
    observed_at: str = "2024-10-01",
    available_at: str = "2024-10-15",
) -> dict:
    return {
        "record_id": record_id,
        "predicate": predicate,
        "subject": subject,
        "object_value": object_value,
        "observed_at": observed_at,
        "available_at": available_at,
        "confidence": 0.85,
        "source": {
            "source_id": source_id,
            "source_version": "snapshot-2024-10",
            "locator": f"https://example.invalid/evidence/{record_id}",
            "content_hash": content_hash,
        },
        "biological_context": biological_context,
        "metadata": metadata,
    }


def manifest(*, shared_disease_source: bool = False) -> dict:
    treatment_source = "burden-source" if shared_disease_source else "gap-source"
    treatment_hash = "1" * 64 if shared_disease_source else "2" * 64
    value = {
        "schema_version": "adds.pinned-evidence.v1",
        "records": [
            record(
                record_id="example-burden",
                predicate="disease_burden_supported",
                subject="test disease",
                object_value="A quantified disease-burden measure is available.",
                source_id="burden-source",
                content_hash="1" * 64,
                biological_context={
                    "disease_id": "MONDO_TEST",
                    "evidence_context_id": "test-population-context",
                },
                metadata={
                    "measure_type": "prevalence",
                    "measure_value": 12.5,
                    "measure_unit": "persons per 100,000",
                    "population": "illustrative population",
                    "geography": "illustrative geography",
                    "reference_period": "2024",
                },
            ),
            record(
                record_id="example-gap",
                predicate="treatment_gap_supported",
                subject="test disease",
                object_value="A treatment limitation is explicitly documented.",
                source_id=treatment_source,
                content_hash=treatment_hash,
                biological_context={
                    "disease_id": "MONDO_TEST",
                    "evidence_context_id": "test-population-context",
                },
                metadata={
                    "treatment_context": "illustrative standard of care",
                    "gap_summary": "A bounded residual-need statement.",
                    "population": "illustrative population",
                    "geography": "illustrative geography",
                    "reference_period": "2024",
                },
            ),
            record(
                record_id="example-target-function",
                predicate="candidate_target_functional_activity_supported",
                subject="Test Drug",
                object_value="Functional target modulation was measured.",
                source_id="functional-assay-source",
                content_hash="3" * 64,
                biological_context={
                    "candidate_id": "CHEMBL_TEST",
                    "target_id": "CHEMBL_TARGET",
                    "target_record_id": "ENSG_TEST1",
                    "disease_id": "MONDO_TEST",
                    "organism": "Homo sapiens",
                    "assay_id": "ASSAY_TEST1_FUNCTION",
                },
                metadata={
                    "assay_name": "Test target functional assay",
                    "assay_type": "functional",
                    "source_assay_type": "B",
                    "source_assay_type_description": "Binding",
                    "functional_readout": True,
                    "endpoint": "illustrative pathway response",
                    "endpoint_relation": "eq",
                    "endpoint_value": 12.0,
                    "endpoint_unit": "nM",
                    "effect_direction": "decreased",
                    "candidate_aliases": ["Test Drug", "CHEMBL_TEST"],
                    "source_lineage_ids": ["doi:10.1000/synthetic-functional"],
                },
            ),
            record(
                record_id="example-disease-model",
                predicate="disease_model_effect_supported",
                subject="Test Drug",
                object_value="A disease-model endpoint changed in the intended direction.",
                source_id="disease-model-source",
                content_hash="4" * 64,
                biological_context={
                    "candidate_id": "CHEMBL_TEST",
                    "disease_id": "MONDO_TEST",
                    "organism": "Mus musculus",
                    "model_system_id": "MODEL_TEST_DISEASE",
                },
                metadata={
                    "model_system": "illustrative disease model",
                    "model_type": "animal model",
                    "endpoint": "illustrative phenotype",
                    "endpoint_relation": "eq",
                    "endpoint_value": 80.0,
                    "endpoint_unit": "percent",
                    "effect_direction": "improved",
                    "disease_relevance": "Directly declared in the source record.",
                    "source_candidate_name": "Test Drug",
                    "source_lineage_ids": ["doi:10.1000/synthetic-model"],
                },
            ),
        ],
    }
    if shared_disease_source:
        value["records"][1]["source"]["locator"] = value["records"][0]["source"][
            "locator"
        ]
    return value


def full_chain_manifest() -> dict:
    job = json.loads(
        (
            ROOT / "rl_env/specs/clinicaltrials_gov_ingestion_job.example.json"
        ).read_text(encoding="utf-8")
    )
    source = ROOT / "tests/fixtures/clinicaltrials_gov_study.synthetic.json"
    bundle = capture_source_bytes(
        source.read_bytes(),
        receipt_id="ctgov-test-trial",
        source_id="clinicaltrials-gov-NCT00000001",
        source_version="clinicaltrials-gov-NCT00000001-version-2025-01-01",
        locator="https://clinicaltrials.gov/api/v2/studies/NCT00000001",
        retrieved_at=REQUEST_AT,
        media_type="application/json",
        capture_method="https",
        http_status=200,
    )
    extracted = extract_clinicaltrials_gov_ingestion_job(job, bundle)
    clinical, _ = compile_pinned_evidence_manifest(
        extracted,
        {bundle.receipt.receipt_id: bundle},
    )
    combined = manifest()
    combined["records"].extend(clinical["records"])
    return combined


def state(
    stage: Stage,
    *,
    as_of_date: date = date(2025, 1, 1),
    program_id: str | None = None,
) -> ProgramState:
    candidates = ()
    targets = ()
    evidence = ()
    diseases = ()
    if stage is not Stage.DISEASE_CONTEXT:
        disease_evidence = EvidenceEvent(
            evidence_id="preloaded-disease-identity",
            stage=Stage.DISEASE_CONTEXT,
            subject="test disease",
            predicate="disease_context_resolved",
            object_value="MONDO_TEST",
            source=SourceReference(
                source_id="preloaded-disease-source",
                source_version="fixture-v1",
                locator="fixture://tests/pinned/disease",
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
    if stage is Stage.PRECLINICAL_VALIDATION:
        targets = (
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
        )
        candidates = (
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
        )
    return ProgramState(
        program_id=program_id or f"pinned-evidence-{stage.value}",
        disease="test disease",
        therapeutic_hypothesis="Independent pinned sources govern stage readiness.",
        as_of_date=as_of_date,
        current_stage=stage,
        budget=BudgetState(limit=1.0),
        evidence=evidence,
        diseases=diseases,
        targets=targets,
        candidates=candidates,
    )


def runner(adapter: PinnedEvidenceAdapter) -> BoundedStageRunner:
    registry = register_existing_adapters(
        ToolRegistry(clock=lambda: COMPLETED_AT),
        pinned_evidence=adapter,
    )
    return BoundedStageRunner(
        tool_registry=registry,
        mapper_registry=build_default_semantic_mapper_registry(
            target_association_minimum_score=0.5
        ),
        planner=BoundedPlanner(clock=lambda: REQUEST_AT),
        clock=lambda: COMPLETED_AT,
    )


def disease_plan() -> StagePlan:
    return StagePlan(
        plan_id="pinned-disease-plan",
        stage=Stage.DISEASE_CONTEXT,
        calls=(
            ToolCallSpec(
                call_id="unmet-need",
                tool_id="pinned_evidence",
                operation="disease_unmet_need",
                action_type=ActionType.QUERY_DATABASE,
                purpose="Resolve burden and treatment gap from independent pinned sources.",
                arguments={"disease_id": "MONDO_TEST"},
                max_cost=0.05,
            ),
        ),
        max_steps=1,
        max_total_cost=0.05,
        success_confidence=0.9,
        failure_confidence=0.95,
        next_stage=Stage.TARGET_NOMINATION,
    )


def function_plan() -> StagePlan:
    return StagePlan(
        plan_id="pinned-function-plan",
        stage=Stage.PRECLINICAL_VALIDATION,
        calls=(
            ToolCallSpec(
                call_id="functional-effect",
                tool_id="pinned_evidence",
                operation="candidate_functional_effect",
                action_type=ActionType.QUERY_DATABASE,
                purpose="Resolve candidate function and disease-model effect.",
                arguments={
                    "candidate_id": "CHEMBL_TEST",
                    "target_id": "CHEMBL_TARGET",
                    "disease_id": "MONDO_TEST",
                },
                max_cost=0.1,
            ),
        ),
        max_steps=1,
        max_total_cost=0.1,
        success_confidence=0.9,
        failure_confidence=0.95,
        next_stage=Stage.CLINICAL_STRATEGY,
    )


def program_step(
    *,
    plan_id: str,
    stage: Stage,
    next_stage: Stage | None,
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


class PinnedEvidenceAdapterTests(unittest.TestCase):
    def test_independent_and_shared_source_runs_form_a_matched_pair(self) -> None:
        context = PromotionContext(
            observed_at=date(2024, 1, 1),
            available_at=date(2024, 1, 2),
            subject="test disease",
            object_value="MONDO_TEST",
            confidence=0.9,
        )
        success_run = runner(PinnedEvidenceAdapter(manifest())).run_stage(
            run_id="matched-pinned-success",
            state=state(
                Stage.DISEASE_CONTEXT,
                program_id="matched-pinned-success-program",
            ),
            stage_plan=disease_plan(),
            promotion_contexts={"unmet-need": context},
        )
        failure_run = runner(
            PinnedEvidenceAdapter(manifest(shared_disease_source=True))
        ).run_stage(
            run_id="matched-pinned-failure",
            state=state(
                Stage.DISEASE_CONTEXT,
                program_id="matched-pinned-failure-program",
            ),
            stage_plan=disease_plan(),
            promotion_contexts={"unmet-need": context},
        )
        key = EpisodeMatchKey(
            disease="test disease",
            stage=Stage.DISEASE_CONTEXT,
            modality="not yet selected",
            population="illustrative population",
            endpoint_family="unmet need",
            target_or_mechanism="unmet-need",
            decision_time_bin="2025",
        )
        pair = MatchedEpisodePair(
            pair_id="pinned-source-independence-pair",
            success=evaluation_episode_from_stage_run(
                success_run,
                episode_id="pinned-source-success",
                pair_id="pinned-source-independence-pair",
                arm=EpisodeArm.SUCCESS,
                match_key=key,
                asset_or_candidate_id="MONDO_TEST",
                target_or_mechanism_id="unmet-need",
                condition_or_context_id="MONDO_TEST",
                available_evidence_packet_id="pinned-profile-success",
                evaluator_label_id="pinned-label-success",
                gold_decision=Decision.ADVANCE,
            ),
            failure=evaluation_episode_from_stage_run(
                failure_run,
                episode_id="pinned-source-failure",
                pair_id="pinned-source-independence-pair",
                arm=EpisodeArm.FAILURE,
                match_key=key,
                asset_or_candidate_id="MONDO_TEST",
                target_or_mechanism_id="unmet-need",
                condition_or_context_id="MONDO_TEST",
                available_evidence_packet_id="pinned-profile-failure",
                evaluator_label_id="pinned-label-failure",
                gold_decision=Decision.DEFER,
                failure_causes=(FailureCause.EVIDENCE_QUALITY,),
            ),
        )

        score = evaluate_matched_pair(pair)

        self.assertTrue(score.both_correct)
        self.assertEqual(score.balanced_accuracy, 1.0)

    def test_matched_assay_target_link_success_and_failure_pair(self) -> None:
        mismatch = manifest()
        target_function = next(
            item
            for item in mismatch["records"]
            if item["predicate"] == "candidate_target_functional_activity_supported"
        )
        target_function["biological_context"]["target_record_id"] = "ENSG_OTHER"
        context = PromotionContext(
            observed_at=date(2024, 1, 1),
            available_at=date(2024, 1, 2),
            subject="Test Drug",
            object_value="CHEMBL_TARGET",
            confidence=0.9,
            candidate_id="CHEMBL_TEST",
            candidate_name="Test Drug",
            modality="small molecule",
            biological_context={"disease_id": "MONDO_TEST"},
        )
        success_run = runner(PinnedEvidenceAdapter(manifest())).run_stage(
            run_id="matched-assay-link-success",
            state=state(
                Stage.PRECLINICAL_VALIDATION,
                program_id="matched-assay-link-success-program",
            ),
            stage_plan=function_plan(),
            promotion_contexts={"functional-effect": context},
        )
        failure_run = runner(PinnedEvidenceAdapter(mismatch)).run_stage(
            run_id="matched-assay-link-failure",
            state=state(
                Stage.PRECLINICAL_VALIDATION,
                program_id="matched-assay-link-failure-program",
            ),
            stage_plan=function_plan(),
            promotion_contexts={"functional-effect": context},
        )
        key = EpisodeMatchKey(
            disease="test disease",
            stage=Stage.PRECLINICAL_VALIDATION,
            modality="small molecule",
            population="preclinical fixture",
            endpoint_family="functional effect",
            target_or_mechanism="CHEMBL_TARGET",
            decision_time_bin="2025",
        )
        pair_id = "assay-target-link-pair"
        pair = MatchedEpisodePair(
            pair_id=pair_id,
            success=evaluation_episode_from_stage_run(
                success_run,
                episode_id="assay-target-link-success",
                pair_id=pair_id,
                arm=EpisodeArm.SUCCESS,
                match_key=key,
                asset_or_candidate_id="CHEMBL_TEST",
                target_or_mechanism_id="CHEMBL_TARGET",
                condition_or_context_id="MONDO_TEST",
                available_evidence_packet_id="assay-target-link-success-packet",
                evaluator_label_id="assay-target-link-success-label",
                gold_decision=Decision.ADVANCE,
            ),
            failure=evaluation_episode_from_stage_run(
                failure_run,
                episode_id="assay-target-link-failure",
                pair_id=pair_id,
                arm=EpisodeArm.FAILURE,
                match_key=key,
                asset_or_candidate_id="CHEMBL_TEST",
                target_or_mechanism_id="CHEMBL_TARGET",
                condition_or_context_id="MONDO_TEST",
                available_evidence_packet_id="assay-target-link-failure-packet",
                evaluator_label_id="assay-target-link-failure-label",
                gold_decision=Decision.DEFER,
                failure_causes=(FailureCause.MECHANISM_OR_CONTEXT,),
            ),
        )

        score = evaluate_matched_pair(pair)

        self.assertEqual(
            failure_run.promotions[0].code,
            "pinned_functional_effect_record_mismatch",
        )
        self.assertTrue(score.both_correct)
        self.assertEqual(score.balanced_accuracy, 1.0)

    def test_public_example_manifest_is_adapter_readable(self) -> None:
        path = (
            Path(__file__).resolve().parents[1]
            / "rl_env/specs/pinned_evidence_manifest.example.json"
        )
        adapter = PinnedEvidenceAdapter.from_json(path)

        self.assertEqual(adapter.stats()["record_count"], 4)
        self.assertEqual(
            adapter.disease_unmet_need("MONDO_EXAMPLE")["status"],
            "resolved",
        )
        self.assertEqual(
            adapter.candidate_functional_effect(
                "CHEMBL_EXAMPLE",
                "CHEMBL_TARGET_EXAMPLE",
                "MONDO_EXAMPLE",
            )["status"],
            "resolved",
        )

    def test_eight_stage_provider_backed_program_completes_and_replays(
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
                    "type": "small molecule",
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

        class FakeEMA:
            def lookup(self, query):
                return {
                    "found": True,
                    "asset": query,
                    "inn": "Test Drug",
                    "status": "Authorised",
                    "url": "https://www.ema.europa.eu/en/medicines/human/EPAR/test-drug",
                    "ma_date": "2024-10-01",
                }

        clock = TickClock()
        registry = register_existing_adapters(
            ToolRegistry(clock=clock),
            opentargets=FakeOpenTargets(),
            chembl=FakeChembl(),
            pinned_evidence=PinnedEvidenceAdapter(full_chain_manifest()),
            molprops=FakeMolProps(),
            ema=FakeEMA(),
        )
        candidate_context = PromotionContext(
            observed_at=date(2024, 1, 1),
            available_at=date(2024, 1, 2),
            subject="Test Drug",
            object_value="CHEMBL_TARGET",
            confidence=0.9,
            candidate_id="CHEMBL_TEST",
            candidate_name="Test Drug",
            modality="small molecule",
        )
        steps = (
            program_step(
                plan_id="e2e-disease",
                stage=Stage.DISEASE_CONTEXT,
                next_stage=Stage.TARGET_NOMINATION,
                call_id="unmet-need",
                tool_id="pinned_evidence",
                operation="disease_unmet_need",
                action_type=ActionType.QUERY_DATABASE,
                purpose="Resolve source-pinned burden and treatment gap.",
                arguments={"disease_id": "MONDO_TEST"},
                max_cost=0.05,
                context=PromotionContext(
                    observed_at=date(2024, 1, 1),
                    available_at=date(2024, 1, 2),
                    subject="test disease",
                    object_value="MONDO_TEST",
                    confidence=0.9,
                ),
            ),
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
                    observed_at=date(2024, 1, 1),
                    available_at=date(2024, 1, 2),
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
                call_id="functional-effect",
                tool_id="pinned_evidence",
                operation="candidate_functional_effect",
                action_type=ActionType.QUERY_DATABASE,
                purpose="Require target function and disease-model effect.",
                arguments={
                    "candidate_id": "CHEMBL_TEST",
                    "target_id": "CHEMBL_TARGET",
                    "disease_id": "MONDO_TEST",
                },
                max_cost=0.1,
                context=PromotionContext(
                    observed_at=candidate_context.observed_at,
                    available_at=candidate_context.available_at,
                    subject=candidate_context.subject,
                    object_value=candidate_context.object_value,
                    confidence=candidate_context.confidence,
                    candidate_id=candidate_context.candidate_id,
                    candidate_name=candidate_context.candidate_name,
                    modality=candidate_context.modality,
                    biological_context={"disease_id": "MONDO_TEST"},
                ),
            ),
            program_step(
                plan_id="e2e-clinical",
                stage=Stage.CLINICAL_STRATEGY,
                next_stage=Stage.REGULATORY_POSTMARKET,
                call_id="clinical-design",
                tool_id="pinned_evidence",
                operation="clinical_trial_design",
                action_type=ActionType.QUERY_DATABASE,
                purpose="Resolve one exact source-pinned trial design.",
                arguments={
                    "candidate_id": "CHEMBL_TEST",
                    "disease_id": "MONDO_TEST",
                    "trial_id": "NCT00000001",
                },
                max_cost=0.1,
                context=PromotionContext(
                    observed_at=date(2024, 6, 1),
                    available_at=date(2024, 9, 15),
                    subject="Test Drug",
                    object_value="test disease",
                    confidence=0.9,
                    candidate_id="CHEMBL_TEST",
                    candidate_name="Test Drug",
                    modality="small molecule",
                    biological_context={
                        "disease_id": "MONDO_TEST",
                        "intervention_id": "CHEMBL_TEST",
                    },
                ),
            ),
            program_step(
                plan_id="e2e-regulatory",
                stage=Stage.REGULATORY_POSTMARKET,
                next_stage=None,
                call_id="regulatory-status",
                tool_id="ema",
                operation="lookup",
                action_type=ActionType.QUERY_DATABASE,
                purpose="Resolve the accepted intervention's regulatory status.",
                arguments={"query": "Test Drug"},
                max_cost=0.1,
                context=PromotionContext(
                    observed_at=date(2024, 10, 1),
                    available_at=date(2024, 10, 1),
                    subject="Test Drug",
                    object_value="Authorised",
                    confidence=0.9,
                    candidate_id="CHEMBL_TEST",
                    candidate_name="Test Drug",
                    modality="small molecule",
                    biological_context={
                        "disease_id": "MONDO_TEST",
                        "intervention_id": "CHEMBL_TEST",
                    },
                ),
            ),
        )
        program_runner = BoundedProgramRunner(
            stage_runner=BoundedStageRunner(
                tool_registry=registry,
                mapper_registry=build_default_semantic_mapper_registry(
                    target_association_minimum_score=0.5
                ),
                planner=BoundedPlanner(clock=clock),
                clock=clock,
            )
        )

        run = program_runner.run_program(
            run_id="eight-stage-provider-backed-chain",
            state=state(Stage.DISEASE_CONTEXT),
            steps=steps,
        )

        self.assertEqual(run.status, ProgramRunStatus.COMPLETED)
        self.assertEqual(
            run.final_state.current_stage, Stage.REGULATORY_POSTMARKET
        )
        self.assertEqual(run.final_state.status, ProgramStatus.COMPLETED)
        self.assertEqual(run.final_state.version, 8)
        self.assertEqual(len(run.execution_ledger.outcomes), 8)
        self.assertEqual(len(run.final_state.evidence), 19)
        self.assertEqual(len(run.final_state.claims), 9)
        self.assertEqual(len(run.final_state.targets), 1)
        self.assertEqual(len(run.final_state.diseases), 1)
        self.assertEqual(len(run.final_state.assays), 1)
        self.assertEqual(len(run.final_state.model_systems), 1)
        self.assertEqual(len(run.final_state.interventions), 1)
        self.assertEqual(len(run.final_state.trials), 1)
        self.assertEqual(len(run.final_state.trial_designs), 1)
        self.assertEqual(len(run.final_state.trial_designs[0].arms), 2)
        self.assertEqual(len(run.final_state.trial_designs[0].populations), 1)
        self.assertEqual(len(run.final_state.trial_designs[0].endpoints), 1)
        self.assertEqual(len(run.final_state.trial_designs[0].safety_records), 1)
        self.assertEqual(
            len(run.final_state.trial_designs[0].safety_records[0].arm_summaries),
            2,
        )
        self.assertIn(
            "clinical_safety_assessed",
            {item.predicate for item in run.final_state.evidence},
        )
        self.assertEqual(
            run.stage_runs[-2].promotions[0].code,
            "pinned_clinical_trial_design_promoted",
        )
        self.assertEqual(
            run.stage_runs[-1].promotions[0].code,
            "ema_regulatory_status_promoted",
        )
        self.assertEqual(
            run.stage_runs[-3].promotions[0].code,
            "pinned_functional_effect_promoted",
        )
        self.assertEqual(replay_program_run(run).final_state, run.final_state)

    def test_disease_profile_advances_only_with_two_pinned_sources(self) -> None:
        current_state = state(Stage.DISEASE_CONTEXT)
        run = runner(PinnedEvidenceAdapter(manifest())).run_stage(
            run_id="pinned-disease-success",
            state=current_state,
            stage_plan=disease_plan(),
            promotion_contexts={
                "unmet-need": PromotionContext(
                    observed_at=date(2024, 1, 1),
                    available_at=date(2024, 1, 2),
                    subject="test disease",
                    object_value="MONDO_TEST",
                    confidence=0.9,
                )
            },
        )

        self.assertEqual(run.accepted_packets[0].decision, Decision.ADVANCE)
        self.assertEqual(run.final_state.current_stage, Stage.TARGET_NOMINATION)
        self.assertEqual(
            {
                item.predicate
                for item in run.final_state.evidence
                if item.stage is Stage.DISEASE_CONTEXT
            },
            {"disease_burden_supported", "treatment_gap_supported"},
        )
        self.assertEqual(
            {item.source.source_id for item in run.final_state.evidence},
            {"burden-source", "gap-source"},
        )
        self.assertTrue(
            all(
                item.available_at == date(2024, 10, 15)
                for item in run.final_state.evidence
            )
        )
        self.assertEqual(run.final_state.claims[0].predicate, "unmet_need_defined")
        self.assertEqual(
            run.final_state.diseases[0].attributes["evidence_context_id"],
            "test-population-context",
        )

    def test_preclinical_profile_advances_with_function_and_disease_model(self) -> None:
        current_state = state(Stage.PRECLINICAL_VALIDATION)
        run = runner(PinnedEvidenceAdapter(manifest())).run_stage(
            run_id="pinned-function-success",
            state=current_state,
            stage_plan=function_plan(),
            promotion_contexts={
                "functional-effect": PromotionContext(
                    observed_at=date(2024, 1, 1),
                    available_at=date(2024, 1, 2),
                    subject="Test Drug",
                    object_value="CHEMBL_TARGET",
                    confidence=0.9,
                    candidate_id="CHEMBL_TEST",
                    candidate_name="Test Drug",
                    modality="small molecule",
                    biological_context={"disease_id": "MONDO_TEST"},
                )
            },
        )

        self.assertEqual(run.accepted_packets[0].decision, Decision.ADVANCE)
        self.assertEqual(run.final_state.current_stage, Stage.CLINICAL_STRATEGY)
        self.assertEqual(
            {
                item.predicate
                for item in run.final_state.evidence
                if item.stage is Stage.PRECLINICAL_VALIDATION
            },
            {
                "candidate_target_functional_activity_supported",
                "disease_model_effect_supported",
            },
        )
        self.assertEqual(
            run.final_state.claims[0].predicate,
            "functional_effect_supported",
        )
        self.assertEqual(run.final_state.assays[0].assay_id, "ASSAY_TEST1_FUNCTION")
        self.assertEqual(
            run.final_state.model_systems[0].model_system_id,
            "MODEL_TEST_DISEASE",
        )

    def test_same_publication_lineage_defers_despite_distinct_source_ids(self) -> None:
        same_lineage = manifest()
        disease_model = next(
            item
            for item in same_lineage["records"]
            if item["predicate"] == "disease_model_effect_supported"
        )
        disease_model["metadata"]["source_lineage_ids"] = [
            "doi:10.1000/synthetic-functional"
        ]
        run = runner(PinnedEvidenceAdapter(same_lineage)).run_stage(
            run_id="pinned-function-shared-lineage",
            state=state(Stage.PRECLINICAL_VALIDATION),
            stage_plan=function_plan(),
            promotion_contexts={
                "functional-effect": PromotionContext(
                    observed_at=date(2024, 1, 1),
                    available_at=date(2024, 1, 2),
                    subject="Test Drug",
                    object_value="CHEMBL_TARGET",
                    confidence=0.9,
                    candidate_id="CHEMBL_TEST",
                    candidate_name="Test Drug",
                    modality="small molecule",
                    biological_context={"disease_id": "MONDO_TEST"},
                )
            },
        )

        self.assertEqual(run.accepted_packets[0].decision, Decision.DEFER)
        self.assertEqual(
            run.promotions[0].code,
            "pinned_functional_effect_lineage_not_independent",
        )
        self.assertEqual(
            run.promotions[0].details["overlapping_source_lineage_ids"],
            ("doi:10.1000/synthetic-functional",),
        )

    def test_disease_model_candidate_must_resolve_to_functional_aliases(self) -> None:
        alias_mismatch = manifest()
        disease_model = next(
            item
            for item in alias_mismatch["records"]
            if item["predicate"] == "disease_model_effect_supported"
        )
        disease_model["metadata"]["source_candidate_name"] = "OTHER-CANDIDATE"
        current_state = state(Stage.PRECLINICAL_VALIDATION)
        run = runner(PinnedEvidenceAdapter(alias_mismatch)).run_stage(
            run_id="pinned-function-alias-mismatch",
            state=current_state,
            stage_plan=function_plan(),
            promotion_contexts={
                "functional-effect": PromotionContext(
                    observed_at=date(2024, 1, 1),
                    available_at=date(2024, 1, 2),
                    subject="Test Drug",
                    object_value="CHEMBL_TARGET",
                    confidence=0.9,
                    candidate_id="CHEMBL_TEST",
                    candidate_name="Test Drug",
                    modality="small molecule",
                    biological_context={"disease_id": "MONDO_TEST"},
                )
            },
        )

        self.assertEqual(run.accepted_packets[0].decision, Decision.DEFER)
        self.assertEqual(
            run.promotions[0].code,
            "pinned_functional_effect_candidate_alias_mismatch",
        )
        self.assertEqual(run.final_state.evidence, current_state.evidence)
        self.assertEqual(run.final_state.assays, ())
        self.assertEqual(run.final_state.model_systems, ())

    def test_same_source_pair_defers_instead_of_laundering_independence(self) -> None:
        current_state = state(Stage.DISEASE_CONTEXT)
        run = runner(
            PinnedEvidenceAdapter(manifest(shared_disease_source=True))
        ).run_stage(
            run_id="pinned-disease-shared-source",
            state=current_state,
            stage_plan=disease_plan(),
            promotion_contexts={
                "unmet-need": PromotionContext(
                    observed_at=date(2024, 1, 1),
                    available_at=date(2024, 1, 2),
                    subject="test disease",
                    object_value="MONDO_TEST",
                    confidence=0.9,
                )
            },
        )

        self.assertEqual(run.accepted_packets[0].decision, Decision.DEFER)
        self.assertEqual(run.final_state.status, ProgramStatus.DEFERRED)
        self.assertEqual(
            run.promotions[0].code,
            "pinned_unmet_need_sources_not_independent",
        )
        self.assertEqual(run.final_state.evidence, ())

    def test_cross_population_profile_defers_without_context_laundering(self) -> None:
        mismatched = manifest()
        mismatched["records"][1]["metadata"]["population"] = "different population"
        run = runner(PinnedEvidenceAdapter(mismatched)).run_stage(
            run_id="pinned-disease-cross-population",
            state=state(Stage.DISEASE_CONTEXT),
            stage_plan=disease_plan(),
            promotion_contexts={
                "unmet-need": PromotionContext(
                    observed_at=date(2024, 1, 1),
                    available_at=date(2024, 1, 2),
                    subject="test disease",
                    object_value="MONDO_TEST",
                    confidence=0.9,
                )
            },
        )

        self.assertEqual(run.accepted_packets[0].decision, Decision.DEFER)
        self.assertEqual(
            run.promotions[0].code,
            "pinned_unmet_need_context_mismatch",
        )
        self.assertEqual(
            run.promotions[0].details["mismatched_fields"],
            ("population",),
        )
        self.assertEqual(run.final_state.evidence, ())

    def test_manifest_dates_enforce_historical_cutoff(self) -> None:
        current_state = state(
            Stage.DISEASE_CONTEXT,
            as_of_date=date(2024, 10, 10),
        )
        run = runner(PinnedEvidenceAdapter(manifest())).run_stage(
            run_id="pinned-disease-future-source",
            state=current_state,
            stage_plan=disease_plan(),
            promotion_contexts={
                "unmet-need": PromotionContext(
                    observed_at=date(2024, 1, 1),
                    available_at=date(2024, 1, 2),
                    subject="test disease",
                    object_value="MONDO_TEST",
                    confidence=0.9,
                )
            },
        )

        self.assertEqual(run.accepted_packets[0].decision, Decision.DEFER)
        self.assertEqual(run.promotions[0].code, "pinned_unmet_need_after_cutoff")
        self.assertEqual(run.final_state.evidence, ())

    def test_incomplete_profile_is_tool_unavailable(self) -> None:
        incomplete = manifest()
        incomplete["records"] = [
            item
            for item in incomplete["records"]
            if item["predicate"] != "treatment_gap_supported"
        ]
        adapter = PinnedEvidenceAdapter(incomplete)
        current_state = state(Stage.DISEASE_CONTEXT)
        registry = register_existing_adapters(
            ToolRegistry(clock=lambda: COMPLETED_AT),
            pinned_evidence=adapter,
        )
        request = ToolRequest(
            request_id="pinned-incomplete-request",
            program_id=current_state.program_id,
            expected_state_version=current_state.version,
            stage=current_state.current_stage,
            tool_id="pinned_evidence",
            operation="disease_unmet_need",
            action_type=ActionType.QUERY_DATABASE,
            purpose="Resolve a complete unmet-need profile.",
            arguments={"disease_id": "MONDO_TEST"},
            max_cost=0.05,
            created_at=REQUEST_AT,
        )

        outcome = registry.execute(current_state, request)

        self.assertEqual(outcome.status, ToolStatus.UNAVAILABLE)
        self.assertEqual(outcome.error_code, "pinned_unmet_need_incomplete")
        self.assertEqual(
            outcome.payload["missing_predicates"], ("treatment_gap_supported",)
        )

    def test_manifest_rejects_unpinned_source_hash(self) -> None:
        invalid = manifest()
        invalid["records"][0]["source"]["content_hash"] = "not-a-hash"

        with self.assertRaisesRegex(ValueError, "SHA-256"):
            PinnedEvidenceAdapter(invalid)

    def test_manifest_rejects_mutable_source_version_markers(self) -> None:
        invalid = manifest()
        invalid["records"][0]["source"]["source_version"] = "latest"

        with self.assertRaisesRegex(ValueError, "immutable revision"):
            PinnedEvidenceAdapter(invalid)


if __name__ == "__main__":
    unittest.main()
