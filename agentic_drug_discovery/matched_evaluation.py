"""Matched success/failure evaluation with evaluator-only outcome labels."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Any

from .models import (
    Decision,
    ProgramState,
    SerializableRecord,
    Stage,
    _freeze_mapping,
    _require_date,
    _require_instance,
    _require_probability,
    _require_text,
)
from .orchestration import StageRun


class EpisodeArm(str, Enum):
    SUCCESS = "success"
    FAILURE = "failure"


class FailureCause(str, Enum):
    EFFICACY = "efficacy"
    SAFETY = "safety"
    PK_PD = "pk_pd"
    BIOMARKER = "biomarker"
    ENDPOINT_OR_TRIAL_DESIGN = "endpoint_or_trial_design"
    OPERATIONAL = "operational"
    REGULATORY = "regulatory"
    ADMET_OR_TOXICITY = "admet_or_toxicity"
    MECHANISM_OR_CONTEXT = "mechanism_or_context"
    EVIDENCE_QUALITY = "evidence_quality"
    TOOL_UNAVAILABLE = "tool_unavailable"
    VERIFIER_BLOCK = "verifier_block"
    OTHER = "other"


@dataclass(frozen=True, slots=True)
class EpisodeMatchKey(SerializableRecord):
    disease: str
    stage: Stage
    modality: str
    population: str
    endpoint_family: str
    target_or_mechanism: str
    decision_time_bin: str

    def __post_init__(self) -> None:
        for field_name in (
            "disease",
            "modality",
            "population",
            "endpoint_family",
            "target_or_mechanism",
            "decision_time_bin",
        ):
            _require_text(getattr(self, field_name), field_name)
        _require_instance(self.stage, Stage, "stage")


_EVALUATOR_ONLY_KEYS = {
    "evaluator_only",
    "evaluator_label",
    "evaluator_label_id",
    "failure_causes",
    "failure_mode",
    "failure_mode_labels",
    "gold_decision",
    "outcome_label",
    "reference_label",
    "terminal_outcome",
}


def _normalized_key(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    return "_".join(value.casefold().replace("-", " ").split())


def _contains_evaluator_key(value: Any) -> bool:
    if isinstance(value, Mapping):
        return any(
            _normalized_key(key) in _EVALUATOR_ONLY_KEYS
            or _contains_evaluator_key(item)
            for key, item in value.items()
        )
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return any(_contains_evaluator_key(item) for item in value)
    return False


@dataclass(frozen=True, slots=True)
class EvaluationEpisode(SerializableRecord):
    episode_id: str
    pair_id: str
    arm: EpisodeArm
    match_key: EpisodeMatchKey
    decision_cutoff: date
    visible_state: ProgramState
    asset_or_candidate_id: str
    target_or_mechanism_id: str
    condition_or_context_id: str
    available_evidence_packet_id: str
    evaluator_label_id: str
    predicted_decision: Decision | None
    gold_decision: Decision
    failure_causes: tuple[FailureCause, ...] = ()
    evaluator_metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for field_name in ("episode_id", "pair_id"):
            _require_text(getattr(self, field_name), field_name)
        _require_instance(self.arm, EpisodeArm, "arm")
        _require_instance(self.match_key, EpisodeMatchKey, "match_key")
        _require_date(self.decision_cutoff, "decision_cutoff")
        _require_instance(self.visible_state, ProgramState, "visible_state")
        for field_name in (
            "asset_or_candidate_id",
            "target_or_mechanism_id",
            "condition_or_context_id",
            "available_evidence_packet_id",
            "evaluator_label_id",
        ):
            _require_text(getattr(self, field_name), field_name)
        if " ".join(self.target_or_mechanism_id.casefold().split()) != " ".join(
            self.match_key.target_or_mechanism.casefold().split()
        ):
            raise ValueError("episode target/mechanism must match the match key")
        if self.predicted_decision is not None:
            _require_instance(
                self.predicted_decision,
                Decision,
                "predicted_decision",
            )
        _require_instance(self.gold_decision, Decision, "gold_decision")
        object.__setattr__(self, "failure_causes", tuple(self.failure_causes))
        for cause in self.failure_causes:
            _require_instance(cause, FailureCause, "failure_causes item")
        if len(self.failure_causes) != len(set(self.failure_causes)):
            raise ValueError("failure_causes must be unique")
        if self.arm is EpisodeArm.SUCCESS and self.failure_causes:
            raise ValueError("success episodes cannot carry failure causes")
        if self.arm is EpisodeArm.FAILURE and not self.failure_causes:
            raise ValueError("failure episodes require at least one failure cause")
        if self.visible_state.as_of_date != self.decision_cutoff:
            raise ValueError("visible_state cutoff must equal decision_cutoff")
        if self.visible_state.current_stage is not self.match_key.stage:
            raise ValueError("visible_state stage must match the episode match key")
        if " ".join(self.visible_state.disease.casefold().split()) != " ".join(
            self.match_key.disease.casefold().split()
        ):
            raise ValueError("visible_state disease must match the episode match key")
        future_evidence = [
            item.evidence_id
            for item in self.visible_state.evidence
            if not item.is_visible_at(self.decision_cutoff)
        ]
        if future_evidence:
            raise ValueError(
                "visible_state contains evidence after the decision cutoff"
            )
        if _contains_evaluator_key(self.visible_state.to_dict()):
            raise ValueError("evaluator-only labels cannot appear in visible_state")
        object.__setattr__(
            self,
            "evaluator_metadata",
            _freeze_mapping(self.evaluator_metadata, "evaluator_metadata"),
        )


@dataclass(frozen=True, slots=True)
class MatchedEpisodePair(SerializableRecord):
    pair_id: str
    success: EvaluationEpisode
    failure: EvaluationEpisode

    def __post_init__(self) -> None:
        _require_text(self.pair_id, "pair_id")
        _require_instance(self.success, EvaluationEpisode, "success")
        _require_instance(self.failure, EvaluationEpisode, "failure")
        if self.success.arm is not EpisodeArm.SUCCESS:
            raise ValueError("success must contain the success arm")
        if self.failure.arm is not EpisodeArm.FAILURE:
            raise ValueError("failure must contain the failure arm")
        if self.success.pair_id != self.pair_id or self.failure.pair_id != self.pair_id:
            raise ValueError("episode pair ids must match the pair record")
        if self.success.match_key != self.failure.match_key:
            raise ValueError("success and failure episodes must share the match key")
        if self.success.condition_or_context_id != self.failure.condition_or_context_id:
            raise ValueError(
                "success and failure episodes must share the condition/context id"
            )
        if self.success.episode_id == self.failure.episode_id:
            raise ValueError("matched episodes must have unique episode ids")
        if self.success.evaluator_label_id == self.failure.evaluator_label_id:
            raise ValueError("matched episodes must have unique evaluator label ids")
        if (
            self.success.visible_state.program_id
            == self.failure.visible_state.program_id
        ):
            raise ValueError("matched episodes must use distinct program ids")


@dataclass(frozen=True, slots=True)
class EpisodeEvaluation(SerializableRecord):
    episode_id: str
    arm: EpisodeArm
    predicted_decision: Decision | None
    gold_decision: Decision
    exact_match: bool

    def __post_init__(self) -> None:
        _require_text(self.episode_id, "episode_id")
        _require_instance(self.arm, EpisodeArm, "arm")
        if self.predicted_decision is not None:
            _require_instance(
                self.predicted_decision,
                Decision,
                "predicted_decision",
            )
        _require_instance(self.gold_decision, Decision, "gold_decision")
        if not isinstance(self.exact_match, bool):
            raise TypeError("exact_match must be boolean")


@dataclass(frozen=True, slots=True)
class MatchedPairEvaluation(SerializableRecord):
    pair_id: str
    success: EpisodeEvaluation
    failure: EpisodeEvaluation
    balanced_accuracy: float
    both_correct: bool

    def __post_init__(self) -> None:
        _require_text(self.pair_id, "pair_id")
        _require_instance(self.success, EpisodeEvaluation, "success")
        _require_instance(self.failure, EpisodeEvaluation, "failure")
        if self.success.arm is not EpisodeArm.SUCCESS:
            raise ValueError("success score must describe the success arm")
        if self.failure.arm is not EpisodeArm.FAILURE:
            raise ValueError("failure score must describe the failure arm")
        _require_probability(self.balanced_accuracy, "balanced_accuracy")
        if not isinstance(self.both_correct, bool):
            raise TypeError("both_correct must be boolean")
        if self.both_correct != (self.success.exact_match and self.failure.exact_match):
            raise ValueError("both_correct must match the arm evaluations")


@dataclass(frozen=True, slots=True)
class MatchedEvaluationSummary(SerializableRecord):
    pair_count: int
    episode_count: int
    exact_accuracy: float
    success_arm_accuracy: float
    failure_arm_accuracy: float
    both_correct_rate: float
    decision_counts: Mapping[str, int]

    def __post_init__(self) -> None:
        for field_name in ("pair_count", "episode_count"):
            value = getattr(self, field_name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 1:
                raise ValueError(f"{field_name} must be a positive integer")
        if self.episode_count != self.pair_count * 2:
            raise ValueError("episode_count must be exactly twice pair_count")
        for field_name in (
            "exact_accuracy",
            "success_arm_accuracy",
            "failure_arm_accuracy",
            "both_correct_rate",
        ):
            _require_probability(getattr(self, field_name), field_name)
        if not isinstance(self.decision_counts, Mapping):
            raise TypeError("decision_counts must be a mapping")
        counts = dict(self.decision_counts)
        for key, value in counts.items():
            _require_text(key, "decision_counts key")
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError("decision_counts values must be non-negative integers")
        if sum(counts.values()) != self.episode_count:
            raise ValueError("decision_counts must cover every episode")
        object.__setattr__(
            self,
            "decision_counts",
            _freeze_mapping(counts, "decision_counts"),
        )


def evaluation_episode_from_stage_run(
    run: StageRun,
    *,
    episode_id: str,
    pair_id: str,
    arm: EpisodeArm,
    match_key: EpisodeMatchKey,
    asset_or_candidate_id: str,
    target_or_mechanism_id: str,
    condition_or_context_id: str,
    available_evidence_packet_id: str,
    evaluator_label_id: str,
    gold_decision: Decision,
    failure_causes: tuple[FailureCause, ...] = (),
    evaluator_metadata: Mapping[str, Any] | None = None,
) -> EvaluationEpisode:
    """Separate the policy-visible initial state from evaluator-only outcome labels."""

    _require_instance(run, StageRun, "run")
    accepted = run.accepted_packets
    if accepted:
        predicted = accepted[-1].decision
    elif run.attempted_packets:
        predicted = run.attempted_packets[-1].decision
    else:
        predicted = None
    return EvaluationEpisode(
        episode_id=episode_id,
        pair_id=pair_id,
        arm=arm,
        match_key=match_key,
        decision_cutoff=run.initial_state.as_of_date,
        visible_state=run.initial_state,
        asset_or_candidate_id=asset_or_candidate_id,
        target_or_mechanism_id=target_or_mechanism_id,
        condition_or_context_id=condition_or_context_id,
        available_evidence_packet_id=available_evidence_packet_id,
        evaluator_label_id=evaluator_label_id,
        predicted_decision=predicted,
        gold_decision=gold_decision,
        failure_causes=failure_causes,
        evaluator_metadata=evaluator_metadata or {},
    )


def evaluate_episode(episode: EvaluationEpisode) -> EpisodeEvaluation:
    _require_instance(episode, EvaluationEpisode, "episode")
    return EpisodeEvaluation(
        episode_id=episode.episode_id,
        arm=episode.arm,
        predicted_decision=episode.predicted_decision,
        gold_decision=episode.gold_decision,
        exact_match=episode.predicted_decision is episode.gold_decision,
    )


def evaluate_matched_pair(pair: MatchedEpisodePair) -> MatchedPairEvaluation:
    _require_instance(pair, MatchedEpisodePair, "pair")
    success = evaluate_episode(pair.success)
    failure = evaluate_episode(pair.failure)
    balanced_accuracy = (float(success.exact_match) + float(failure.exact_match)) / 2
    return MatchedPairEvaluation(
        pair_id=pair.pair_id,
        success=success,
        failure=failure,
        balanced_accuracy=balanced_accuracy,
        both_correct=success.exact_match and failure.exact_match,
    )


def summarize_matched_pairs(
    pairs: Sequence[MatchedEpisodePair],
) -> MatchedEvaluationSummary:
    if isinstance(pairs, (str, bytes)):
        raise TypeError("pairs must be a sequence of MatchedEpisodePair records")
    resolved = tuple(pairs)
    if not resolved:
        raise ValueError("at least one matched pair is required")
    for pair in resolved:
        _require_instance(pair, MatchedEpisodePair, "pairs item")
    pair_ids = tuple(pair.pair_id for pair in resolved)
    if len(pair_ids) != len(set(pair_ids)):
        raise ValueError("matched pair ids must be unique")
    episode_ids = tuple(
        episode.episode_id
        for pair in resolved
        for episode in (pair.success, pair.failure)
    )
    if len(episode_ids) != len(set(episode_ids)):
        raise ValueError("episode ids must be unique across matched pairs")
    evaluator_label_ids = tuple(
        episode.evaluator_label_id
        for pair in resolved
        for episode in (pair.success, pair.failure)
    )
    if len(evaluator_label_ids) != len(set(evaluator_label_ids)):
        raise ValueError("evaluator label ids must be unique across matched pairs")
    program_ids = tuple(
        episode.visible_state.program_id
        for pair in resolved
        for episode in (pair.success, pair.failure)
    )
    if len(program_ids) != len(set(program_ids)):
        raise ValueError("program ids must be unique across matched pairs")
    evaluations = tuple(evaluate_matched_pair(pair) for pair in resolved)
    success_correct = sum(item.success.exact_match for item in evaluations)
    failure_correct = sum(item.failure.exact_match for item in evaluations)
    both_correct = sum(item.both_correct for item in evaluations)
    decision_counts: dict[str, int] = {}
    for pair in resolved:
        for episode in (pair.success, pair.failure):
            key = (
                episode.predicted_decision.value
                if episode.predicted_decision is not None
                else "missing"
            )
            decision_counts[key] = decision_counts.get(key, 0) + 1
    pair_count = len(resolved)
    return MatchedEvaluationSummary(
        pair_count=pair_count,
        episode_count=pair_count * 2,
        exact_accuracy=(success_correct + failure_correct) / (pair_count * 2),
        success_arm_accuracy=success_correct / pair_count,
        failure_arm_accuracy=failure_correct / pair_count,
        both_correct_rate=both_correct / pair_count,
        decision_counts=decision_counts,
    )
