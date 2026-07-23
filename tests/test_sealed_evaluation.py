from __future__ import annotations

import json
import unittest
from dataclasses import replace
from datetime import date
from pathlib import Path

from jsonschema import Draft202012Validator

from agentic_drug_discovery import (
    BudgetState,
    Decision,
    EpisodeArm,
    EpisodeMatchKey,
    EvaluationBoardSplit,
    EvaluationEpisode,
    FailureCause,
    MatchedEpisodePair,
    PolicyEvaluationSubmission,
    ProgramState,
    RecordParseError,
    Stage,
    compare_policy_submissions,
    constant_policy_submission,
    evaluate_policy_submission,
    policy_evaluation_report_envelope,
    policy_evaluation_report_from_dict,
    policy_evaluation_report_from_json,
    policy_evaluation_submission_envelope,
    policy_evaluation_submission_from_dict,
    policy_evaluation_submission_from_json,
    policy_submission_from_matched_pairs,
    seal_matched_evaluation_board,
    sealed_evaluation_board_envelope,
    sealed_evaluation_board_from_dict,
    sealed_evaluation_board_from_json,
    sealed_evaluation_vault_envelope,
    sealed_evaluation_vault_from_dict,
    sealed_evaluation_vault_from_json,
    validate_evaluation_vault,
)


SECRET = "sealed-evaluation-test-secret-32-bytes-minimum"
ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = {
    "board": ROOT / "rl_env/specs/sealed_evaluation_board.schema.json",
    "vault": ROOT / "rl_env/specs/sealed_evaluation_vault.schema.json",
    "submission": ROOT / "rl_env/specs/policy_evaluation_submission.schema.json",
    "report": ROOT / "rl_env/specs/policy_evaluation_report.schema.json",
}


def _state(program_id: str) -> ProgramState:
    return ProgramState(
        program_id=program_id,
        disease="test disease",
        therapeutic_hypothesis="Evaluate policy behavior without label leakage.",
        as_of_date=date(2025, 1, 1),
        current_stage=Stage.CLINICAL_STRATEGY,
        budget=BudgetState(limit=1.0),
    )


def _match_key() -> EpisodeMatchKey:
    return EpisodeMatchKey(
        disease="test disease",
        stage=Stage.CLINICAL_STRATEGY,
        modality="small molecule",
        population="adult",
        endpoint_family="clinical benefit",
        target_or_mechanism="TEST1",
        decision_time_bin="2020-2025",
    )


def _episode(
    *,
    pair_id: str,
    episode_id: str,
    arm: EpisodeArm,
    predicted: Decision | None,
    gold: Decision,
    failure_causes: tuple[FailureCause, ...] = (),
) -> EvaluationEpisode:
    return EvaluationEpisode(
        episode_id=episode_id,
        pair_id=pair_id,
        arm=arm,
        match_key=_match_key(),
        decision_cutoff=date(2025, 1, 1),
        visible_state=_state(f"program-{episode_id}"),
        asset_or_candidate_id="CHEMBL_TEST",
        target_or_mechanism_id="TEST1",
        condition_or_context_id="MONDO:TEST",
        available_evidence_packet_id=f"packet-{episode_id}",
        evaluator_label_id=f"label-{episode_id}",
        predicted_decision=predicted,
        gold_decision=gold,
        failure_causes=failure_causes,
        evaluator_metadata={
            "label_basis": "synthetic_contract_test",
            "review_status": "locked",
        },
    )


def _pairs() -> tuple[MatchedEpisodePair, ...]:
    return (
        MatchedEpisodePair(
            pair_id="source-pair-one",
            success=_episode(
                pair_id="source-pair-one",
                episode_id="success-one",
                arm=EpisodeArm.SUCCESS,
                predicted=Decision.ADVANCE,
                gold=Decision.ADVANCE,
            ),
            failure=_episode(
                pair_id="source-pair-one",
                episode_id="failure-one",
                arm=EpisodeArm.FAILURE,
                predicted=Decision.DEFER,
                gold=Decision.DEFER,
                failure_causes=(FailureCause.EVIDENCE_QUALITY,),
            ),
        ),
        MatchedEpisodePair(
            pair_id="source-pair-two",
            success=_episode(
                pair_id="source-pair-two",
                episode_id="success-two",
                arm=EpisodeArm.SUCCESS,
                predicted=Decision.HOLD,
                gold=Decision.HOLD,
            ),
            failure=_episode(
                pair_id="source-pair-two",
                episode_id="failure-two",
                arm=EpisodeArm.FAILURE,
                predicted=Decision.KILL,
                gold=Decision.KILL,
                failure_causes=(FailureCause.EFFICACY,),
            ),
        ),
    )


def _sealed():
    pairs = _pairs()
    episodes = tuple(
        episode
        for pair in pairs
        for episode in (pair.success, pair.failure)
    )
    return seal_matched_evaluation_board(
        board_id="synthetic-sealed-board",
        version="1",
        split=EvaluationBoardSplit.DEVELOPMENT,
        created_on=date(2026, 7, 23),
        pairs=pairs,
        sealing_secret=SECRET,
        visible_packets_by_episode_id={
            episode.episode_id: {
                "tool_id": "synthetic_cached_tool",
                "operation": "evaluate_contract",
                "arguments": {
                    "slot": index,
                    "condition_id": "MONDO:TEST",
                },
            }
            for index, episode in enumerate(episodes)
        },
        packet_available_at_by_episode_id={
            episode.episode_id: date(2025, 1, 1) for episode in episodes
        },
        metadata={
            "scope": "synthetic contract tests",
            "labels_released": False,
        },
    )


class SealedEvaluationTests(unittest.TestCase):
    def test_sealing_is_deterministic_role_neutral_and_label_separated(
        self,
    ) -> None:
        board, vault = _sealed()
        repeated_board, repeated_vault = _sealed()

        self.assertEqual(board.fingerprint, repeated_board.fingerprint)
        self.assertEqual(vault.fingerprint, repeated_vault.fingerprint)
        self.assertEqual(len(board.observations), 4)
        self.assertEqual(len(board.pairs), 2)
        self.assertEqual(set(validate_evaluation_vault(board, vault)), {
            item.episode_id for item in board.observations
        })
        self.assertTrue(
            all(
                pair.episode_ids == tuple(sorted(pair.episode_ids))
                for pair in board.pairs
            )
        )
        self.assertTrue(
            all(
                item.visible_state.program_id.startswith("sealed-program-")
                for item in board.observations
            )
        )
        self.assertTrue(
            all(
                item.available_evidence_packet["tool_id"]
                == "synthetic_cached_tool"
                for item in board.observations
            )
        )
        serialized_board = json.dumps(board.to_dict(), sort_keys=True)
        for forbidden in (
            '"arm"',
            '"gold_decision"',
            '"failure_causes"',
            "success-one",
            "failure-one",
            "source-pair-one",
        ):
            self.assertNotIn(forbidden, serialized_board)
        serialized_vault = json.dumps(vault.to_dict(), sort_keys=True)
        self.assertIn('"gold_decision"', serialized_vault)
        self.assertIn('"failure_causes"', serialized_vault)

    def test_commitment_and_observation_fingerprints_fail_closed(self) -> None:
        board, vault = _sealed()
        original = vault.labels[0]
        tampered = replace(
            original,
            gold_decision=(
                Decision.KILL
                if original.gold_decision is not Decision.KILL
                else Decision.HOLD
            ),
        )
        tampered_vault = replace(
            vault,
            labels=(tampered, *vault.labels[1:]),
        )
        with self.assertRaisesRegex(ValueError, "label commitment"):
            validate_evaluation_vault(board, tampered_vault)

        submission = policy_submission_from_matched_pairs(
            board=board,
            pairs=_pairs(),
            sealing_secret=SECRET,
            submission_id="governed-submission",
            policy_id="governed-stage-output",
            policy_version="1",
            created_on=date(2026, 7, 23),
            confidence_by_episode_id={
                item.episode_id: 0.9
                for pair in _pairs()
                for item in (pair.success, pair.failure)
            },
        )
        stale_prediction = replace(
            submission.predictions[0],
            observation_fingerprint="0" * 64,
        )
        stale_submission = replace(
            submission,
            predictions=(stale_prediction, *submission.predictions[1:]),
        )
        with self.assertRaisesRegex(ValueError, "another observation"):
            evaluate_policy_submission(board, vault, stale_submission)

    def test_policy_comparison_scores_arms_risk_and_top_label_calibration(
        self,
    ) -> None:
        board, vault = _sealed()
        confidence = {
            item.episode_id: 0.9
            for pair in _pairs()
            for item in (pair.success, pair.failure)
        }
        governed = policy_submission_from_matched_pairs(
            board=board,
            pairs=_pairs(),
            sealing_secret=SECRET,
            submission_id="governed-submission",
            policy_id="governed-stage-output",
            policy_version="1",
            created_on=date(2026, 7, 23),
            confidence_by_episode_id=confidence,
        )
        always_advance = constant_policy_submission(
            board=board,
            submission_id="always-advance-submission",
            policy_id="always-advance",
            policy_version="1",
            created_on=date(2026, 7, 23),
            decision=Decision.ADVANCE,
            confidence=1.0,
        )
        defer_safe = constant_policy_submission(
            board=board,
            submission_id="defer-safe-submission",
            policy_id="defer-safe",
            policy_version="1",
            created_on=date(2026, 7, 23),
            decision=Decision.DEFER,
            confidence=1.0,
        )

        governed_result = evaluate_policy_submission(board, vault, governed)
        advance_result = evaluate_policy_submission(board, vault, always_advance)
        defer_result = evaluate_policy_submission(board, vault, defer_safe)
        report = compare_policy_submissions(
            evaluation_id="synthetic-policy-comparison",
            board=board,
            vault=vault,
            submissions=(governed, always_advance, defer_safe),
            limitations=(
                "Synthetic contract coverage is not discovery performance.",
                "Four episodes cannot establish confidence calibration.",
            ),
        )

        self.assertEqual(governed_result.summary.exact_accuracy, 1.0)
        self.assertEqual(governed_result.summary.both_correct_rate, 1.0)
        self.assertAlmostEqual(
            governed_result.summary.top_label_brier or 0.0,
            0.01,
        )
        self.assertAlmostEqual(
            governed_result.summary.top_label_ece or 0.0,
            0.1,
        )
        self.assertEqual(advance_result.summary.exact_accuracy, 0.25)
        self.assertEqual(advance_result.summary.success_arm_accuracy, 0.5)
        self.assertEqual(advance_result.summary.failure_arm_accuracy, 0.0)
        self.assertEqual(advance_result.summary.unsafe_advance_rate, 1.0)
        self.assertEqual(advance_result.summary.top_label_brier, 0.75)
        self.assertEqual(defer_result.summary.exact_accuracy, 0.25)
        self.assertEqual(defer_result.summary.unsafe_advance_rate, 0.0)
        self.assertEqual(len(report.summaries), 3)

    def test_incomplete_submission_and_label_metadata_leakage_are_rejected(
        self,
    ) -> None:
        board, vault = _sealed()
        with self.assertRaisesRegex(ValueError, "explicit episode confidence"):
            policy_submission_from_matched_pairs(
                board=board,
                pairs=_pairs(),
                sealing_secret=SECRET,
                submission_id="missing-confidence",
                policy_id="governed-stage-output",
                policy_version="1",
                created_on=date(2026, 7, 23),
            )
        complete = constant_policy_submission(
            board=board,
            submission_id="complete",
            policy_id="constant",
            policy_version="1",
            created_on=date(2026, 7, 23),
            decision=Decision.DEFER,
            confidence=1.0,
        )
        incomplete = replace(
            complete,
            predictions=complete.predictions[:-1],
        )
        with self.assertRaisesRegex(ValueError, "cover every observation"):
            evaluate_policy_submission(board, vault, incomplete)

        with self.assertRaisesRegex(ValueError, "evaluator-only"):
            replace(board, metadata={"gold_decision": "advance"})

        with self.assertRaisesRegex(ValueError, "evaluator-only"):
            PolicyEvaluationSubmission(
                submission_id="leaky",
                board_id=board.board_id,
                board_fingerprint=board.fingerprint,
                policy_id="leaky-policy",
                policy_version="1",
                created_on=date(2026, 7, 23),
                predictions=complete.predictions,
                metadata={"outcome_label": "hidden"},
            )

    def test_identity_order_chronology_and_camelcase_leaks_fail_closed(
        self,
    ) -> None:
        board, vault = _sealed()
        observation = board.observations[0]

        with self.assertRaisesRegex(ValueError, "opaque sealed identifier"):
            replace(
                observation,
                available_evidence_packet_id="raw-source-packet",
            )
        with self.assertRaisesRegex(ValueError, "opaque sealed identifier"):
            replace(
                observation,
                visible_state=replace(
                    observation.visible_state,
                    program_id="raw-source-program",
                ),
            )
        with self.assertRaisesRegex(ValueError, "after the decision cutoff"):
            replace(
                observation,
                available_evidence_packet_available_at=date(2025, 1, 2),
            )
        with self.assertRaisesRegex(ValueError, "hash does not match"):
            replace(
                observation,
                available_evidence_packet_sha256="0" * 64,
            )
        with self.assertRaisesRegex(ValueError, "evaluator-only"):
            replace(
                observation,
                available_evidence_packet={
                    "nested": {"goldDecision": "advance"},
                },
            )
        with self.assertRaisesRegex(ValueError, "evaluator-only"):
            replace(board, metadata={"evaluatorLabelId": "hidden"})
        with self.assertRaisesRegex(ValueError, "sorted by episode id"):
            replace(board, observations=tuple(reversed(board.observations)))
        with self.assertRaisesRegex(ValueError, "episode cutoff"):
            replace(board, created_on=date(2024, 12, 31))
        with self.assertRaisesRegex(ValueError, "sorted by episode id"):
            replace(vault, labels=tuple(reversed(vault.labels)))

        submission = constant_policy_submission(
            board=board,
            submission_id="chronology-check",
            policy_id="defer-safe",
            policy_version="1",
            created_on=date(2026, 7, 23),
            decision=Decision.DEFER,
            confidence=1.0,
        )
        with self.assertRaisesRegex(ValueError, "sorted by episode id"):
            replace(
                submission,
                predictions=tuple(reversed(submission.predictions)),
            )
        with self.assertRaisesRegex(ValueError, "cannot predate"):
            evaluate_policy_submission(
                board,
                vault,
                replace(submission, created_on=date(2026, 7, 22)),
            )
        with self.assertRaisesRegex(ValueError, "explicit limitations"):
            compare_policy_submissions(
                evaluation_id="missing-limitations",
                board=board,
                vault=vault,
                submissions=(submission,),
                limitations=(),
            )

    def test_machine_envelopes_bind_schema_versions_and_integrity_hashes(
        self,
    ) -> None:
        board, vault = _sealed()
        submission = constant_policy_submission(
            board=board,
            submission_id="defer-safe",
            policy_id="defer-safe",
            policy_version="1",
            created_on=date(2026, 7, 23),
            decision=Decision.DEFER,
            confidence=1.0,
        )
        report = compare_policy_submissions(
            evaluation_id="envelope-check",
            board=board,
            vault=vault,
            submissions=(submission,),
            limitations=("Synthetic envelope test only.",),
        )
        envelopes = (
            (
                "board",
                sealed_evaluation_board_envelope(board),
                board.fingerprint,
                board,
                sealed_evaluation_board_from_dict,
                sealed_evaluation_board_from_json,
            ),
            (
                "vault",
                sealed_evaluation_vault_envelope(vault),
                vault.fingerprint,
                vault,
                sealed_evaluation_vault_from_dict,
                sealed_evaluation_vault_from_json,
            ),
            (
                "submission",
                policy_evaluation_submission_envelope(submission),
                submission.fingerprint,
                submission,
                policy_evaluation_submission_from_dict,
                policy_evaluation_submission_from_json,
            ),
            (
                "report",
                policy_evaluation_report_envelope(report),
                report.fingerprint,
                report,
                policy_evaluation_report_from_dict,
                policy_evaluation_report_from_json,
            ),
        )
        for (
            schema_name,
            envelope,
            expected_hash,
            expected_record,
            dict_parser,
            json_parser,
        ) in envelopes:
            schema = json.loads(SCHEMAS[schema_name].read_text(encoding="utf-8"))
            Draft202012Validator.check_schema(schema)
            Draft202012Validator(schema).validate(envelope)
            self.assertEqual(envelope["integrity_sha256"], expected_hash)
            self.assertTrue(envelope["schema_version"].startswith("adds."))
            self.assertEqual(dict_parser(envelope), expected_record)
            self.assertEqual(
                json_parser(json.dumps(envelope, sort_keys=True)),
                expected_record,
            )

        tampered = json.loads(
            json.dumps(sealed_evaluation_board_envelope(board))
        )
        tampered["board"]["version"] = "tampered"
        with self.assertRaisesRegex(RecordParseError, "integrity hash"):
            sealed_evaluation_board_from_dict(tampered)

        unknown = json.loads(
            json.dumps(sealed_evaluation_board_envelope(board))
        )
        unknown["unexpected"] = True
        with self.assertRaisesRegex(RecordParseError, "unknown fields"):
            sealed_evaluation_board_from_dict(unknown)

        with self.assertRaisesRegex(RecordParseError, "duplicates key"):
            sealed_evaluation_board_from_json(
                '{"schema_version":"one","schema_version":"two"}'
            )
        with self.assertRaisesRegex(RecordParseError, "contains NaN"):
            sealed_evaluation_board_from_json('{"schema_version":NaN}')


if __name__ == "__main__":
    unittest.main()
