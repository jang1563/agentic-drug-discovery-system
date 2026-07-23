from __future__ import annotations

import unittest
from datetime import date

from agentic_drug_discovery import (
    BudgetState,
    Decision,
    EpisodeArm,
    EpisodeMatchKey,
    EvaluationEpisode,
    FailureCause,
    MatchedEpisodePair,
    PlanningStatus,
    PlanResult,
    ProgramState,
    Stage,
    StageRun,
    StageRunStatus,
    ToolExecutionLedger,
    evaluate_matched_pair,
    evaluation_episode_from_stage_run,
    summarize_matched_pairs,
)


def visible_state(program_id: str, *, metadata=None) -> ProgramState:
    return ProgramState(
        program_id=program_id,
        disease="test disease",
        therapeutic_hypothesis="Matched cases prevent success-only evaluation.",
        as_of_date=date(2025, 1, 1),
        current_stage=Stage.CLINICAL_STRATEGY,
        budget=BudgetState(limit=1.0),
        target_product_profile=metadata or {},
    )


def match_key(*, population: str = "adult") -> EpisodeMatchKey:
    return EpisodeMatchKey(
        disease="test disease",
        stage=Stage.CLINICAL_STRATEGY,
        modality="small molecule",
        population=population,
        endpoint_family="clinical benefit",
        target_or_mechanism="TEST1",
        decision_time_bin="2020-2025",
    )


def episode(
    *,
    episode_id: str,
    program_id: str,
    arm: EpisodeArm,
    predicted: Decision | None,
    gold: Decision,
    failure_causes=(),
    key=None,
    pair_id="pair-1",
    condition_or_context_id="MONDO_TEST",
    evaluator_label_id=None,
) -> EvaluationEpisode:
    return EvaluationEpisode(
        episode_id=episode_id,
        pair_id=pair_id,
        arm=arm,
        match_key=key or match_key(),
        decision_cutoff=date(2025, 1, 1),
        visible_state=visible_state(program_id),
        asset_or_candidate_id=f"asset-{episode_id}",
        target_or_mechanism_id="TEST1",
        condition_or_context_id=condition_or_context_id,
        available_evidence_packet_id=f"visible-{episode_id}",
        evaluator_label_id=evaluator_label_id or f"label-{episode_id}",
        predicted_decision=predicted,
        gold_decision=gold,
        failure_causes=failure_causes,
        evaluator_metadata={"source": "locked_outcome_table"},
    )


class MatchedEvaluationTests(unittest.TestCase):
    def test_complete_pair_scores_success_and_failure_arms_separately(self) -> None:
        pair = MatchedEpisodePair(
            pair_id="pair-1",
            success=episode(
                episode_id="success-1",
                program_id="program-success",
                arm=EpisodeArm.SUCCESS,
                predicted=Decision.ADVANCE,
                gold=Decision.ADVANCE,
            ),
            failure=episode(
                episode_id="failure-1",
                program_id="program-failure",
                arm=EpisodeArm.FAILURE,
                predicted=Decision.DEFER,
                gold=Decision.DEFER,
                failure_causes=(FailureCause.EFFICACY,),
            ),
        )

        pair_score = evaluate_matched_pair(pair)
        summary = summarize_matched_pairs((pair,))

        self.assertTrue(pair_score.both_correct)
        self.assertEqual(pair_score.balanced_accuracy, 1.0)
        self.assertEqual(summary.pair_count, 1)
        self.assertEqual(summary.episode_count, 2)
        self.assertEqual(summary.success_arm_accuracy, 1.0)
        self.assertEqual(summary.failure_arm_accuracy, 1.0)
        self.assertEqual(summary.both_correct_rate, 1.0)
        self.assertEqual(summary.decision_counts, {"advance": 1, "defer": 1})

    def test_pair_rejects_context_mismatch_and_missing_failure_causes(self) -> None:
        with self.assertRaisesRegex(ValueError, "failure episodes require"):
            episode(
                episode_id="failure-missing-cause",
                program_id="program-failure",
                arm=EpisodeArm.FAILURE,
                predicted=Decision.DEFER,
                gold=Decision.DEFER,
            )

        success = episode(
            episode_id="success-1",
            program_id="program-success",
            arm=EpisodeArm.SUCCESS,
            predicted=Decision.ADVANCE,
            gold=Decision.ADVANCE,
        )
        failure = episode(
            episode_id="failure-1",
            program_id="program-failure",
            arm=EpisodeArm.FAILURE,
            predicted=Decision.DEFER,
            gold=Decision.DEFER,
            failure_causes=(FailureCause.SAFETY,),
            key=match_key(population="pediatric"),
        )
        with self.assertRaisesRegex(ValueError, "share the match key"):
            MatchedEpisodePair(
                pair_id="pair-1",
                success=success,
                failure=failure,
            )

        failure_wrong_condition = episode(
            episode_id="failure-wrong-condition",
            program_id="program-failure-condition",
            arm=EpisodeArm.FAILURE,
            predicted=Decision.DEFER,
            gold=Decision.DEFER,
            failure_causes=(FailureCause.SAFETY,),
            condition_or_context_id="MONDO_OTHER",
        )
        with self.assertRaisesRegex(ValueError, "condition/context id"):
            MatchedEpisodePair(
                pair_id="pair-1",
                success=success,
                failure=failure_wrong_condition,
            )

    def test_evaluator_labels_are_rejected_from_visible_state(self) -> None:
        with self.assertRaisesRegex(ValueError, "evaluator-only labels"):
            EvaluationEpisode(
                episode_id="leaky-episode",
                pair_id="pair-1",
                arm=EpisodeArm.SUCCESS,
                match_key=match_key(),
                decision_cutoff=date(2025, 1, 1),
                visible_state=visible_state(
                    "program-leaky",
                    metadata={"Evaluator-Label-ID": "hidden-label"},
                ),
                asset_or_candidate_id="asset-leaky",
                target_or_mechanism_id="TEST1",
                condition_or_context_id="MONDO_TEST",
                available_evidence_packet_id="visible-leaky",
                evaluator_label_id="label-leaky",
                predicted_decision=Decision.ADVANCE,
                gold_decision=Decision.ADVANCE,
            )

    def test_planning_block_is_scored_as_missing_prediction(self) -> None:
        state = visible_state("program-planning-block")
        plan_result = PlanResult(
            status=PlanningStatus.BLOCKED,
            plan_id="blocked-plan",
            code="required_tool_contract_missing",
            message="Required tool was not registered.",
        )
        run = StageRun(
            run_id="blocked-run",
            status=StageRunStatus.PLANNING_BLOCKED,
            code=plan_result.code,
            message=plan_result.message,
            initial_state=state,
            final_state=state,
            plan_result=plan_result,
            execution_ledger=ToolExecutionLedger(),
        )

        failure_episode = evaluation_episode_from_stage_run(
            run,
            episode_id="failure-planning-block",
            pair_id="pair-1",
            arm=EpisodeArm.FAILURE,
            match_key=match_key(),
            asset_or_candidate_id="asset-planning-block",
            target_or_mechanism_id="TEST1",
            condition_or_context_id="MONDO_TEST",
            available_evidence_packet_id="visible-planning-block",
            evaluator_label_id="label-planning-block",
            gold_decision=Decision.DEFER,
            failure_causes=(FailureCause.TOOL_UNAVAILABLE,),
        )

        self.assertIsNone(failure_episode.predicted_decision)

    def test_empty_pair_collection_is_not_a_valid_evaluation(self) -> None:
        with self.assertRaisesRegex(ValueError, "at least one matched pair"):
            summarize_matched_pairs(())

    def test_summary_rejects_duplicate_labels_and_programs_across_pairs(self) -> None:
        def pair(
            pair_id: str,
            suffix: str,
            *,
            success_label: str,
            success_program: str,
        ) -> MatchedEpisodePair:
            return MatchedEpisodePair(
                pair_id=pair_id,
                success=episode(
                    episode_id=f"success-{suffix}",
                    program_id=success_program,
                    arm=EpisodeArm.SUCCESS,
                    predicted=Decision.ADVANCE,
                    gold=Decision.ADVANCE,
                    pair_id=pair_id,
                    evaluator_label_id=success_label,
                ),
                failure=episode(
                    episode_id=f"failure-{suffix}",
                    program_id=f"program-failure-{suffix}",
                    arm=EpisodeArm.FAILURE,
                    predicted=Decision.DEFER,
                    gold=Decision.DEFER,
                    failure_causes=(FailureCause.EFFICACY,),
                    pair_id=pair_id,
                ),
            )

        first = pair(
            "pair-1",
            "one",
            success_label="shared-label",
            success_program="program-success-shared",
        )
        duplicate_label = pair(
            "pair-2",
            "two",
            success_label="shared-label",
            success_program="program-success-two",
        )
        with self.assertRaisesRegex(ValueError, "evaluator label ids"):
            summarize_matched_pairs((first, duplicate_label))

        duplicate_program = pair(
            "pair-3",
            "three",
            success_label="label-success-three",
            success_program="program-success-shared",
        )
        with self.assertRaisesRegex(ValueError, "program ids"):
            summarize_matched_pairs((first, duplicate_program))


if __name__ == "__main__":
    unittest.main()
