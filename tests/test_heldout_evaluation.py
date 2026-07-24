from __future__ import annotations

import hashlib
import json
import unittest
from dataclasses import replace
from datetime import date
from pathlib import Path

from jsonschema import Draft202012Validator

from agentic_drug_discovery import (
    BudgetState,
    CuratorDeclaration,
    CuratorRole,
    Decision,
    EpisodeArm,
    EpisodeCurationRecord,
    EpisodeMatchKey,
    EvaluationEpisode,
    FailureCause,
    HeldoutCurationManifest,
    HeldoutEvaluationProtocol,
    HeldoutLabelPolicy,
    HeldoutLabelVote,
    HeldoutMetricPolicy,
    LabelConsensusRule,
    MatchedEpisodePair,
    ProgramState,
    RecordParseError,
    Stage,
    StageEvaluationRequirement,
    constant_policy_submission,
    curator_roster_commitment,
    evaluate_stage_stratified_submissions,
    heldout_curation_manifest_envelope,
    heldout_curation_manifest_from_dict,
    heldout_curation_manifest_from_json,
    heldout_evaluation_protocol_envelope,
    heldout_evaluation_protocol_from_dict,
    heldout_evaluation_protocol_from_json,
    policy_submission_from_matched_pairs,
    seal_heldout_evaluation_board,
    stage_stratified_evaluation_report_envelope,
    stage_stratified_evaluation_report_from_dict,
    stage_stratified_evaluation_report_from_json,
    validate_heldout_curation,
    validate_heldout_protocol_board,
)

ROOT = Path(__file__).resolve().parents[1]
SECRET = "heldout-evaluation-test-secret-32-bytes-minimum"
SCHEMAS = {
    "protocol": ROOT / "rl_env/specs/heldout_evaluation_protocol.schema.json",
    "curation": ROOT / "rl_env/specs/heldout_curation_manifest.schema.json",
    "report": (
        ROOT / "rl_env/specs/stage_stratified_evaluation_report.schema.json"
    ),
}
EXAMPLES = {
    "protocol": ROOT / "rl_env/specs/heldout_evaluation_protocol.example.json",
    "report": (
        ROOT / "rl_env/specs/stage_stratified_evaluation_report.example.json"
    ),
}


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _declarations(
    consensus_rule: LabelConsensusRule,
) -> tuple[CuratorDeclaration, ...]:
    declarations = [
        CuratorDeclaration(
            curator_id=f"cur-{index:016x}",
            role=CuratorRole.CURATOR,
            affiliation_commitment=_digest(f"affiliation-{index}"),
            independence_attestation_sha256=_digest(f"attestation-{index}"),
            declared_on=date(2024, 11, 1),
        )
        for index in range(1, 4)
    ]
    if consensus_rule is LabelConsensusRule.ADJUDICATED:
        declarations.append(
            CuratorDeclaration(
                curator_id="cur-0000000000000004",
                role=CuratorRole.ADJUDICATOR,
                affiliation_commitment=_digest("affiliation-4"),
                independence_attestation_sha256=_digest("attestation-4"),
                declared_on=date(2024, 11, 1),
            )
        )
    return tuple(declarations)


def _protocol(
    *,
    consensus_rule: LabelConsensusRule = LabelConsensusRule.STRICT_MAJORITY,
    minimum_pairs: int = 2,
) -> tuple[HeldoutEvaluationProtocol, tuple[CuratorDeclaration, ...]]:
    declarations = _declarations(consensus_rule)
    decisions = tuple(sorted(Decision, key=lambda item: item.value))
    protocol = HeldoutEvaluationProtocol(
        protocol_id="synthetic-heldout-protocol",
        version="1",
        registered_on=date(2024, 12, 1),
        board_id="synthetic-heldout-board",
        board_version="1",
        label_policy=HeldoutLabelPolicy(
            policy_id="synthetic-label-policy",
            version="1",
            allowed_decisions=decisions,
            decision_definitions={
                decision.value: f"Synthetic definition for {decision.value}."
                for decision in decisions
            },
            consensus_rule=consensus_rule,
            minimum_independent_curators=3,
            outcome_window_days=30,
            label_guidance_sha256=_digest("public label guidance"),
            exclusion_rules_sha256=_digest("public exclusion rules"),
        ),
        metric_policy=HeldoutMetricPolicy(
            confidence_level=0.95,
            stage_requirements=(
                StageEvaluationRequirement(
                    stage=Stage.TARGET_NOMINATION,
                    minimum_pairs=minimum_pairs,
                    minimum_action_covered_episodes=2,
                ),
                StageEvaluationRequirement(
                    stage=Stage.CLINICAL_STRATEGY,
                    minimum_pairs=minimum_pairs,
                    minimum_action_covered_episodes=2,
                ),
            ),
        ),
        cohort_specification_sha256=_digest("synthetic cohort specification"),
        curator_roster_commitment=curator_roster_commitment(declarations),
        metadata={
            "payload_class": "synthetic",
            "policy_outputs_visible_to_curators": False,
        },
    )
    return protocol, declarations


def _state(program_id: str, stage: Stage) -> ProgramState:
    return ProgramState(
        program_id=program_id,
        disease=f"synthetic {stage.value} disease",
        therapeutic_hypothesis="Test held-out evaluation contracts.",
        as_of_date=date(2025, 1, 1),
        current_stage=stage,
        budget=BudgetState(limit=1.0),
    )


def _episode(
    *,
    stage: Stage,
    pair_index: int,
    arm: EpisodeArm,
    predicted: Decision,
    gold: Decision,
) -> EvaluationEpisode:
    pair_id = f"source-{stage.value}-{pair_index}"
    arm_name = arm.value
    episode_id = f"{stage.value}-{pair_index}-{arm_name}"
    target = f"SYNTHETIC_TARGET_{stage.value}"
    return EvaluationEpisode(
        episode_id=episode_id,
        pair_id=pair_id,
        arm=arm,
        match_key=EpisodeMatchKey(
            disease=f"synthetic {stage.value} disease",
            stage=stage,
            modality="synthetic modality",
            population="synthetic population",
            endpoint_family="synthetic endpoint",
            target_or_mechanism=target,
            decision_time_bin="synthetic-2025",
        ),
        decision_cutoff=date(2025, 1, 1),
        visible_state=_state(f"program-{episode_id}", stage),
        asset_or_candidate_id=f"SYNTHETIC_ASSET_{pair_index}",
        target_or_mechanism_id=target,
        condition_or_context_id=f"SYNTHETIC_CONTEXT_{stage.value}",
        available_evidence_packet_id=f"packet-{episode_id}",
        evaluator_label_id=f"label-{episode_id}",
        predicted_decision=predicted,
        gold_decision=gold,
        failure_causes=(
            ()
            if arm is EpisodeArm.SUCCESS
            else (FailureCause.EVIDENCE_QUALITY,)
        ),
        evaluator_metadata={"payload_class": "synthetic"},
    )


def _pairs() -> tuple[MatchedEpisodePair, ...]:
    pairs: list[MatchedEpisodePair] = []
    for stage in (Stage.TARGET_NOMINATION, Stage.CLINICAL_STRATEGY):
        for pair_index in (1, 2):
            success_gold = (
                Decision.ADVANCE if pair_index == 1 else Decision.HOLD
            )
            failure_gold = Decision.DEFER if pair_index == 1 else Decision.KILL
            pair_id = f"source-{stage.value}-{pair_index}"
            pairs.append(
                MatchedEpisodePair(
                    pair_id=pair_id,
                    success=_episode(
                        stage=stage,
                        pair_index=pair_index,
                        arm=EpisodeArm.SUCCESS,
                        predicted=success_gold,
                        gold=success_gold,
                    ),
                    failure=_episode(
                        stage=stage,
                        pair_index=pair_index,
                        arm=EpisodeArm.FAILURE,
                        predicted=failure_gold,
                        gold=failure_gold,
                    ),
                )
            )
    return tuple(pairs)


def _sealed(
    protocol: HeldoutEvaluationProtocol,
):
    pairs = _pairs()
    episodes = tuple(
        episode
        for pair in pairs
        for episode in (pair.success, pair.failure)
    )
    return seal_heldout_evaluation_board(
        protocol=protocol,
        created_on=date(2026, 7, 23),
        pairs=pairs,
        sealing_secret=SECRET,
        visible_packets_by_episode_id={
            episode.episode_id: {
                "tool_id": "synthetic_cached_tool",
                "operation": "evaluate_contract",
                "arguments": {"synthetic_slot": index},
            }
            for index, episode in enumerate(episodes)
        },
        packet_available_at_by_episode_id={
            episode.episode_id: date(2025, 1, 1) for episode in episodes
        },
        metadata={"payload_class": "synthetic"},
    )


def _manifest(
    protocol: HeldoutEvaluationProtocol,
    declarations: tuple[CuratorDeclaration, ...],
    board,
    vault,
) -> HeldoutCurationManifest:
    records: list[EpisodeCurationRecord] = []
    for label in vault.labels:
        alternative = (
            Decision.DEFER
            if label.gold_decision is Decision.ADVANCE
            else Decision.ADVANCE
        )
        if (
            protocol.label_policy.consensus_rule
            is LabelConsensusRule.ADJUDICATED
        ):
            decisions = (label.gold_decision, alternative, alternative)
            adjudicator_id = "cur-0000000000000004"
            adjudicated_on = date(2025, 3, 2)
            adjudication_hash = _digest(f"adjudication-{label.episode_id}")
        elif (
            protocol.label_policy.consensus_rule
            is LabelConsensusRule.UNANIMOUS
        ):
            decisions = (label.gold_decision,) * 3
            adjudicator_id = None
            adjudicated_on = None
            adjudication_hash = None
        else:
            decisions = (label.gold_decision, label.gold_decision, alternative)
            adjudicator_id = None
            adjudicated_on = None
            adjudication_hash = None
        votes = tuple(
            HeldoutLabelVote(
                curator_id=declaration.curator_id,
                decision=decision,
                labeled_on=date(2025, 3, 1),
                evidence_snapshot_sha256=_digest(
                    f"evidence-{label.episode_id}-{declaration.curator_id}"
                ),
                rationale_sha256=_digest(
                    f"rationale-{label.episode_id}-{declaration.curator_id}"
                ),
            )
            for declaration, decision in zip(
                declarations[:3],
                decisions,
                strict=True,
            )
        )
        records.append(
            EpisodeCurationRecord(
                episode_id=label.episode_id,
                votes=votes,
                final_decision=label.gold_decision,
                adjudicator_id=adjudicator_id,
                adjudicated_on=adjudicated_on,
                adjudication_rationale_sha256=adjudication_hash,
            )
        )
    return HeldoutCurationManifest(
        manifest_id="synthetic-curation-manifest",
        version="1",
        protocol_id=protocol.protocol_id,
        protocol_fingerprint=protocol.fingerprint,
        board_id=board.board_id,
        board_fingerprint=board.fingerprint,
        vault_fingerprint=vault.fingerprint,
        created_on=date(2026, 7, 23),
        curator_declarations=declarations,
        episode_records=tuple(sorted(records, key=lambda item: item.episode_id)),
    )


def _bundle(
    consensus_rule: LabelConsensusRule = LabelConsensusRule.STRICT_MAJORITY,
):
    protocol, declarations = _protocol(consensus_rule=consensus_rule)
    board, vault = _sealed(protocol)
    manifest = _manifest(protocol, declarations, board, vault)
    return protocol, declarations, board, vault, manifest


class HeldoutEvaluationTests(unittest.TestCase):
    def test_preregistered_board_and_stage_stratified_policy_metrics(
        self,
    ) -> None:
        protocol, _, board, vault, manifest = _bundle()
        stage_counts = validate_heldout_protocol_board(protocol, board)
        validate_heldout_curation(protocol, board, vault, manifest)
        self.assertEqual(stage_counts[Stage.TARGET_NOMINATION], 2)
        self.assertEqual(stage_counts[Stage.CLINICAL_STRATEGY], 2)

        confidence = {
            episode.episode_id: 0.9
            for pair in _pairs()
            for episode in (pair.success, pair.failure)
        }
        governed = policy_submission_from_matched_pairs(
            board=board,
            pairs=_pairs(),
            sealing_secret=SECRET,
            submission_id="governed-submission",
            policy_id="governed",
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
        report = evaluate_stage_stratified_submissions(
            evaluation_id="synthetic-stage-comparison",
            protocol=protocol,
            board=board,
            vault=vault,
            curation_manifest=manifest,
            submissions=(governed, always_advance, defer_safe),
            created_on=date(2026, 7, 23),
            limitations=("Synthetic labels are not discovery outcomes.",),
        )
        summaries = {item.policy_id: item for item in report.summaries}
        governed_summary = summaries["governed"]
        self.assertEqual(governed_summary.overall.exact_accuracy.estimate, 1.0)
        self.assertEqual(
            governed_summary.overall.action_coverage.event_count,
            6,
        )
        self.assertEqual(
            governed_summary.overall.selective_risk.estimate,
            0.0,
        )
        self.assertTrue(governed_summary.all_stage_requirements_met)
        self.assertTrue(governed_summary.all_action_requirements_met)
        self.assertEqual(len(governed_summary.by_stage), 2)
        self.assertLess(
            governed_summary.overall.exact_accuracy.lower or 0.0,
            1.0,
        )

        defer_summary = summaries["defer-safe"]
        self.assertEqual(defer_summary.overall.action_coverage.event_count, 0)
        self.assertIsNone(defer_summary.overall.selective_risk.estimate)
        self.assertFalse(defer_summary.all_action_requirements_met)
        self.assertEqual(defer_summary.overall.unsafe_advance_rate.estimate, 0.0)

        advance_summary = summaries["always-advance"]
        self.assertEqual(advance_summary.overall.action_coverage.estimate, 1.0)
        self.assertEqual(
            advance_summary.overall.unsafe_advance_rate.estimate,
            1.0,
        )
        self.assertEqual(
            report.curation_manifest_fingerprint,
            manifest.fingerprint,
        )
        self.assertIn(
            (
                "Episode-level Wilson intervals do not adjust for within-pair "
                "dependence or curator-label uncertainty."
            ),
            report.limitations,
        )

    def test_sample_minima_protocol_binding_and_reserved_metadata_fail_closed(
        self,
    ) -> None:
        protocol, _ = _protocol(minimum_pairs=3)
        with self.assertRaisesRegex(ValueError, "pair minimum"):
            _sealed(protocol)

        valid_protocol, _ = _protocol()
        with self.assertRaisesRegex(ValueError, "reserved"):
            pairs = _pairs()
            episodes = tuple(
                episode
                for pair in pairs
                for episode in (pair.success, pair.failure)
            )
            seal_heldout_evaluation_board(
                protocol=valid_protocol,
                created_on=date(2026, 7, 23),
                pairs=pairs,
                sealing_secret=SECRET,
                visible_packets_by_episode_id={
                    item.episode_id: {"synthetic": True} for item in episodes
                },
                packet_available_at_by_episode_id={
                    item.episode_id: date(2025, 1, 1) for item in episodes
                },
                metadata={"heldout_protocol_id": "injected"},
            )

        protocol, _, board, vault, manifest = _bundle()
        late = constant_policy_submission(
            board=board,
            submission_id="late-submission",
            policy_id="late-policy",
            policy_version="1",
            created_on=date(2026, 7, 24),
            decision=Decision.DEFER,
            confidence=1.0,
        )
        with self.assertRaisesRegex(ValueError, "curation freeze"):
            evaluate_stage_stratified_submissions(
                evaluation_id="late-submission-check",
                protocol=protocol,
                board=board,
                vault=vault,
                curation_manifest=manifest,
                submissions=(late,),
                created_on=date(2026, 7, 24),
            )

        first = replace(
            late,
            submission_id="duplicate-policy-one",
            created_on=date(2026, 7, 23),
        )
        second = replace(first, submission_id="duplicate-policy-two")
        with self.assertRaisesRegex(ValueError, "policy identities"):
            evaluate_stage_stratified_submissions(
                evaluation_id="duplicate-policy-check",
                protocol=protocol,
                board=board,
                vault=vault,
                curation_manifest=manifest,
                submissions=(first, second),
                created_on=date(2026, 7, 23),
            )

    def test_aggregate_report_rejects_cross_metric_inconsistency(self) -> None:
        protocol, _, board, vault, manifest = _bundle()
        submission = constant_policy_submission(
            board=board,
            submission_id="defer-safe-submission",
            policy_id="defer-safe",
            policy_version="1",
            created_on=date(2026, 7, 23),
            decision=Decision.DEFER,
            confidence=1.0,
        )
        report = evaluate_stage_stratified_submissions(
            evaluation_id="aggregate-consistency-check",
            protocol=protocol,
            board=board,
            vault=vault,
            curation_manifest=manifest,
            submissions=(submission,),
            created_on=date(2026, 7, 23),
        )
        summary = report.summaries[0]
        with self.assertRaisesRegex(ValueError, "jointly feasible"):
            replace(
                summary.overall,
                both_correct_rate=summary.overall.failure_arm_accuracy,
            )

        different_confidence = replace(
            summary.overall.selective_risk,
            confidence_level=0.9,
        )
        with self.assertRaisesRegex(ValueError, "confidence levels"):
            replace(
                summary.overall,
                selective_risk=different_confidence,
            )

        duplicate_identity = replace(
            summary,
            submission_id="second-submission",
            submission_fingerprint=_digest("second submission"),
        )
        with self.assertRaisesRegex(ValueError, "one submission"):
            replace(
                report,
                summaries=tuple(
                    sorted(
                        (summary, duplicate_identity),
                        key=lambda item: (
                            item.policy_id,
                            item.policy_version,
                            item.submission_id,
                        ),
                    )
                ),
            )

    def test_curation_rejects_uncommitted_roster_majority_and_chronology(
        self,
    ) -> None:
        protocol, _, board, vault, manifest = _bundle()
        changed_declaration = replace(
            manifest.curator_declarations[0],
            affiliation_commitment=_digest("uncommitted-affiliation"),
        )
        uncommitted = replace(
            manifest,
            curator_declarations=(
                changed_declaration,
                *manifest.curator_declarations[1:],
            ),
        )
        with self.assertRaisesRegex(ValueError, "roster"):
            validate_heldout_curation(
                protocol,
                board,
                vault,
                uncommitted,
            )

        record = manifest.episode_records[0]
        alternative = (
            Decision.DEFER
            if record.final_decision is Decision.ADVANCE
            else Decision.ADVANCE
        )
        minority_votes = tuple(
            replace(vote, decision=alternative)
            for vote in record.votes[:2]
        ) + (record.votes[2],)
        no_majority = replace(record, votes=minority_votes)
        majority_tampered = replace(
            manifest,
            episode_records=(
                no_majority,
                *manifest.episode_records[1:],
            ),
        )
        with self.assertRaisesRegex(ValueError, "strict-majority"):
            validate_heldout_curation(
                protocol,
                board,
                vault,
                majority_tampered,
            )

        early_record = replace(
            record,
            votes=tuple(
                replace(vote, labeled_on=date(2025, 1, 15))
                for vote in record.votes
            ),
        )
        chronology_tampered = replace(
            manifest,
            episode_records=(
                early_record,
                *manifest.episode_records[1:],
            ),
        )
        with self.assertRaisesRegex(ValueError, "outcome window"):
            validate_heldout_curation(
                protocol,
                board,
                vault,
                chronology_tampered,
            )

    def test_independent_adjudication_resolves_disagreement(self) -> None:
        unanimous = _bundle(LabelConsensusRule.UNANIMOUS)
        validate_heldout_curation(
            unanimous[0],
            unanimous[2],
            unanimous[3],
            unanimous[4],
        )

        protocol, _, board, vault, manifest = _bundle(
            LabelConsensusRule.ADJUDICATED
        )
        validate_heldout_curation(protocol, board, vault, manifest)

        first = manifest.episode_records[0]
        missing_adjudication = replace(
            first,
            adjudicator_id=None,
            adjudicated_on=None,
            adjudication_rationale_sha256=None,
        )
        tampered = replace(
            manifest,
            episode_records=(
                missing_adjudication,
                *manifest.episode_records[1:],
            ),
        )
        with self.assertRaisesRegex(ValueError, "requires independent"):
            validate_heldout_curation(protocol, board, vault, tampered)

    def test_strict_envelopes_round_trip_and_validate_public_schemas(
        self,
    ) -> None:
        protocol, _, board, vault, manifest = _bundle()
        submission = constant_policy_submission(
            board=board,
            submission_id="defer-safe-submission",
            policy_id="defer-safe",
            policy_version="1",
            created_on=date(2026, 7, 23),
            decision=Decision.DEFER,
            confidence=1.0,
        )
        report = evaluate_stage_stratified_submissions(
            evaluation_id="synthetic-envelope-check",
            protocol=protocol,
            board=board,
            vault=vault,
            curation_manifest=manifest,
            submissions=(submission,),
            created_on=date(2026, 7, 23),
        )
        artifacts = (
            (
                "protocol",
                heldout_evaluation_protocol_envelope(protocol),
                protocol,
                heldout_evaluation_protocol_from_dict,
                heldout_evaluation_protocol_from_json,
            ),
            (
                "curation",
                heldout_curation_manifest_envelope(manifest),
                manifest,
                heldout_curation_manifest_from_dict,
                heldout_curation_manifest_from_json,
            ),
            (
                "report",
                stage_stratified_evaluation_report_envelope(report),
                report,
                stage_stratified_evaluation_report_from_dict,
                stage_stratified_evaluation_report_from_json,
            ),
        )
        for schema_name, envelope, expected, dict_reader, json_reader in artifacts:
            schema = json.loads(SCHEMAS[schema_name].read_text(encoding="utf-8"))
            Draft202012Validator.check_schema(schema)
            Draft202012Validator(schema).validate(envelope)
            self.assertEqual(dict_reader(envelope), expected)
            self.assertEqual(
                json_reader(json.dumps(envelope, sort_keys=True)),
                expected,
            )
            if schema_name in EXAMPLES:
                self.assertEqual(
                    json.loads(
                        EXAMPLES[schema_name].read_text(encoding="utf-8")
                    ),
                    envelope,
                )

        tampered = json.loads(
            json.dumps(heldout_evaluation_protocol_envelope(protocol))
        )
        tampered["protocol"]["version"] = "tampered"
        with self.assertRaisesRegex(RecordParseError, "integrity hash"):
            heldout_evaluation_protocol_from_dict(tampered)
        with self.assertRaisesRegex(RecordParseError, "duplicates key"):
            heldout_evaluation_protocol_from_json(
                '{"schema_version":"one","schema_version":"two"}'
            )


if __name__ == "__main__":
    unittest.main()
