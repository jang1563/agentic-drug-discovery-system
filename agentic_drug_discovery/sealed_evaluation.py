"""Cutoff-safe matched boards with cryptographically separated evaluator labels."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import date
from enum import Enum
from typing import Any

from .matched_evaluation import (
    EpisodeArm,
    EpisodeMatchKey,
    FailureCause,
    MatchedEpisodePair,
    _contains_evaluator_key,
    summarize_matched_pairs,
)
from .models import (
    Decision,
    ProgramState,
    SerializableRecord,
    Stage,
    _freeze_mapping,
    _freeze_text_tuple,
    _require_date,
    _require_instance,
    _require_probability,
    _require_sha256,
    _require_text,
    to_primitive,
)
from .serialization import RecordParseError, program_state_from_dict


SEALED_EVALUATION_BOARD_SCHEMA_VERSION = "adds.sealed-evaluation-board.v1"
SEALED_EVALUATION_VAULT_SCHEMA_VERSION = "adds.sealed-evaluation-vault.v1"
POLICY_EVALUATION_SUBMISSION_SCHEMA_VERSION = (
    "adds.policy-evaluation-submission.v1"
)
POLICY_EVALUATION_REPORT_SCHEMA_VERSION = "adds.policy-evaluation-report.v1"

_EPISODE_ID_PATTERN = re.compile(r"^ep-[0-9a-f]{24}$")
_PAIR_ID_PATTERN = re.compile(r"^pair-[0-9a-f]{16}$")
_LABEL_ID_PATTERN = re.compile(r"^lbl-[0-9a-f]{24}$")
_PROGRAM_ID_PATTERN = re.compile(r"^sealed-program-[0-9a-f]{24}$")
_PACKET_ID_PATTERN = re.compile(r"^packet-[0-9a-f]{24}$")


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        to_primitive(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _require_opaque_id(
    value: str,
    field_name: str,
    pattern: re.Pattern[str],
) -> None:
    _require_text(value, field_name)
    if pattern.fullmatch(value) is None:
        raise ValueError(f"{field_name} must be an opaque sealed identifier")


def _require_non_empty_secret(secret: str) -> bytes:
    _require_text(secret, "sealing_secret")
    encoded = secret.encode("utf-8")
    if len(encoded) < 32:
        raise ValueError("sealing_secret must contain at least 32 UTF-8 bytes")
    return encoded


def _opaque_digest(secret: bytes, board_id: str, purpose: str, value: str) -> str:
    return hmac.new(
        secret,
        f"{board_id}|{purpose}|{value}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _opaque_episode_id(secret: bytes, board_id: str, episode_id: str) -> str:
    return f"ep-{_opaque_digest(secret, board_id, 'episode', episode_id)[:24]}"


def _opaque_pair_id(secret: bytes, board_id: str, pair_id: str) -> str:
    return f"pair-{_opaque_digest(secret, board_id, 'pair', pair_id)[:16]}"


def _opaque_label_id(secret: bytes, board_id: str, label_id: str) -> str:
    return f"lbl-{_opaque_digest(secret, board_id, 'label', label_id)[:24]}"


def _opaque_program_id(secret: bytes, board_id: str, episode_id: str) -> str:
    return f"sealed-program-{_opaque_digest(secret, board_id, 'program', episode_id)[:24]}"


def _opaque_packet_id(secret: bytes, board_id: str, packet_id: str) -> str:
    return f"packet-{_opaque_digest(secret, board_id, 'packet', packet_id)[:24]}"


def _opaque_visible_state(
    state: ProgramState,
    *,
    program_id: str,
) -> ProgramState:
    packet_history = tuple(
        replace(packet, program_id=program_id) for packet in state.packet_history
    )
    opaque = replace(
        state,
        program_id=program_id,
        packet_history=packet_history,
    )
    opaque.validate_committed_history()
    return opaque


class EvaluationBoardSplit(str, Enum):
    DEVELOPMENT = "development"
    SEALED_EXTERNAL = "sealed_external"


@dataclass(frozen=True, slots=True)
class CutoffEpisodeObservation(SerializableRecord):
    """Policy-visible episode state with no arm, outcome, or failure label."""

    episode_id: str
    pair_id: str
    match_key: EpisodeMatchKey
    decision_cutoff: date
    visible_state: ProgramState
    asset_or_candidate_id: str
    target_or_mechanism_id: str
    condition_or_context_id: str
    available_evidence_packet_id: str
    available_evidence_packet_available_at: date
    available_evidence_packet: Mapping[str, Any]
    available_evidence_packet_sha256: str
    label_commitment: str

    def __post_init__(self) -> None:
        _require_opaque_id(
            self.episode_id,
            "episode_id",
            _EPISODE_ID_PATTERN,
        )
        _require_opaque_id(self.pair_id, "pair_id", _PAIR_ID_PATTERN)
        _require_instance(self.match_key, EpisodeMatchKey, "match_key")
        _require_date(self.decision_cutoff, "decision_cutoff")
        _require_instance(self.visible_state, ProgramState, "visible_state")
        for field_name in (
            "asset_or_candidate_id",
            "target_or_mechanism_id",
            "condition_or_context_id",
        ):
            _require_text(getattr(self, field_name), field_name)
        _require_opaque_id(
            self.visible_state.program_id,
            "visible_state.program_id",
            _PROGRAM_ID_PATTERN,
        )
        _require_opaque_id(
            self.available_evidence_packet_id,
            "available_evidence_packet_id",
            _PACKET_ID_PATTERN,
        )
        _require_date(
            self.available_evidence_packet_available_at,
            "available_evidence_packet_available_at",
        )
        if self.available_evidence_packet_available_at > self.decision_cutoff:
            raise ValueError(
                "available evidence packet is after the decision cutoff"
            )
        frozen_packet = _freeze_mapping(
            self.available_evidence_packet,
            "available_evidence_packet",
        )
        if not frozen_packet:
            raise ValueError("available_evidence_packet must not be empty")
        if _contains_evaluator_key(frozen_packet):
            raise ValueError(
                "available evidence packet cannot contain evaluator-only labels"
            )
        object.__setattr__(
            self,
            "available_evidence_packet",
            frozen_packet,
        )
        _require_sha256(
            self.available_evidence_packet_sha256,
            "available_evidence_packet_sha256",
        )
        if self.available_evidence_packet_sha256 != _sha256(frozen_packet):
            raise ValueError("available evidence packet hash does not match")
        _require_sha256(self.label_commitment, "label_commitment")
        if self.visible_state.as_of_date != self.decision_cutoff:
            raise ValueError("visible_state cutoff must equal decision_cutoff")
        if self.visible_state.current_stage is not self.match_key.stage:
            raise ValueError("visible_state stage must match the episode match key")
        if " ".join(self.visible_state.disease.casefold().split()) != " ".join(
            self.match_key.disease.casefold().split()
        ):
            raise ValueError("visible_state disease must match the episode match key")
        if " ".join(self.target_or_mechanism_id.casefold().split()) != " ".join(
            self.match_key.target_or_mechanism.casefold().split()
        ):
            raise ValueError("episode target/mechanism must match the match key")
        if any(
            not item.is_visible_at(self.decision_cutoff)
            for item in self.visible_state.evidence
        ):
            raise ValueError(
                "visible_state contains evidence after the decision cutoff"
            )
        if _contains_evaluator_key(self.visible_state.to_dict()):
            raise ValueError("evaluator-only labels cannot appear in visible_state")

    @property
    def fingerprint(self) -> str:
        return _sha256(self)


@dataclass(frozen=True, slots=True)
class OpaqueMatchedPair(SerializableRecord):
    """A role-neutral pair index; arm assignment remains in the label vault."""

    pair_id: str
    episode_ids: tuple[str, str]

    def __post_init__(self) -> None:
        _require_opaque_id(self.pair_id, "pair_id", _PAIR_ID_PATTERN)
        episode_ids = tuple(self.episode_ids)
        object.__setattr__(self, "episode_ids", episode_ids)
        if len(episode_ids) != 2 or len(set(episode_ids)) != 2:
            raise ValueError("opaque matched pairs require two unique episode ids")
        for episode_id in episode_ids:
            _require_opaque_id(
                episode_id,
                "episode_ids item",
                _EPISODE_ID_PATTERN,
            )
        if episode_ids != tuple(sorted(episode_ids)):
            raise ValueError("opaque matched pair episode ids must be sorted")


@dataclass(frozen=True, slots=True)
class SealedEvaluationBoard(SerializableRecord):
    """Role-neutral policy surface for development or external sealed scoring."""

    board_id: str
    version: str
    split: EvaluationBoardSplit
    created_on: date
    observations: tuple[CutoffEpisodeObservation, ...]
    pairs: tuple[OpaqueMatchedPair, ...]
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for field_name in ("board_id", "version"):
            _require_text(getattr(self, field_name), field_name)
        _require_instance(self.split, EvaluationBoardSplit, "split")
        _require_date(self.created_on, "created_on")
        observations = tuple(self.observations)
        pairs = tuple(self.pairs)
        object.__setattr__(self, "observations", observations)
        object.__setattr__(self, "pairs", pairs)
        if not observations or not pairs:
            raise ValueError("evaluation boards require observations and pairs")
        for observation in observations:
            _require_instance(
                observation,
                CutoffEpisodeObservation,
                "observations item",
            )
        for pair in pairs:
            _require_instance(pair, OpaqueMatchedPair, "pairs item")
        episode_ids = tuple(item.episode_id for item in observations)
        pair_ids = tuple(item.pair_id for item in pairs)
        if len(episode_ids) != len(set(episode_ids)):
            raise ValueError("board episode ids must be unique")
        if len(pair_ids) != len(set(pair_ids)):
            raise ValueError("board pair ids must be unique")
        if episode_ids != tuple(sorted(episode_ids)):
            raise ValueError("board observations must be sorted by episode id")
        if pair_ids != tuple(sorted(pair_ids)):
            raise ValueError("board pairs must be sorted by pair id")
        if any(item.decision_cutoff > self.created_on for item in observations):
            raise ValueError("board creation cannot predate an episode cutoff")
        indexed_episode_ids = tuple(
            episode_id for pair in pairs for episode_id in pair.episode_ids
        )
        if len(indexed_episode_ids) != len(set(indexed_episode_ids)):
            raise ValueError("each observation must belong to exactly one pair")
        if set(indexed_episode_ids) != set(episode_ids):
            raise ValueError("pair index must cover every board observation")
        observations_by_id = {item.episode_id: item for item in observations}
        for pair in pairs:
            if any(
                observations_by_id[episode_id].pair_id != pair.pair_id
                for episode_id in pair.episode_ids
            ):
                raise ValueError("observation pair id does not match pair index")
        commitments = tuple(item.label_commitment for item in observations)
        if len(commitments) != len(set(commitments)):
            raise ValueError("label commitments must be unique")
        frozen_metadata = _freeze_mapping(self.metadata, "metadata")
        if _contains_evaluator_key(frozen_metadata):
            raise ValueError("board metadata cannot contain evaluator-only labels")
        object.__setattr__(self, "metadata", frozen_metadata)

    @property
    def fingerprint(self) -> str:
        return _sha256(self)


@dataclass(frozen=True, slots=True)
class SealedEpisodeLabel(SerializableRecord):
    """Evaluator-only arm, outcome, and failure annotation with a nonce."""

    episode_id: str
    pair_id: str
    evaluator_label_id: str
    arm: EpisodeArm
    gold_decision: Decision
    commitment_nonce: str
    failure_causes: tuple[FailureCause, ...] = ()
    evaluator_metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_opaque_id(
            self.episode_id,
            "episode_id",
            _EPISODE_ID_PATTERN,
        )
        _require_opaque_id(self.pair_id, "pair_id", _PAIR_ID_PATTERN)
        _require_opaque_id(
            self.evaluator_label_id,
            "evaluator_label_id",
            _LABEL_ID_PATTERN,
        )
        _require_instance(self.arm, EpisodeArm, "arm")
        _require_instance(self.gold_decision, Decision, "gold_decision")
        _require_sha256(self.commitment_nonce, "commitment_nonce")
        causes = tuple(self.failure_causes)
        object.__setattr__(self, "failure_causes", causes)
        for cause in causes:
            _require_instance(cause, FailureCause, "failure_causes item")
        if len(causes) != len(set(causes)):
            raise ValueError("failure_causes must be unique")
        if self.arm is EpisodeArm.SUCCESS and causes:
            raise ValueError("success labels cannot carry failure causes")
        if self.arm is EpisodeArm.FAILURE and not causes:
            raise ValueError("failure labels require at least one failure cause")
        object.__setattr__(
            self,
            "evaluator_metadata",
            _freeze_mapping(self.evaluator_metadata, "evaluator_metadata"),
        )

    @property
    def commitment(self) -> str:
        return _sha256(
            {
                "episode_id": self.episode_id,
                "pair_id": self.pair_id,
                "evaluator_label_id": self.evaluator_label_id,
                "arm": self.arm,
                "gold_decision": self.gold_decision,
                "failure_causes": self.failure_causes,
                "evaluator_metadata": self.evaluator_metadata,
                "commitment_nonce": self.commitment_nonce,
            }
        )


@dataclass(frozen=True, slots=True)
class SealedEvaluationVault(SerializableRecord):
    """External label artifact bound to one exact board fingerprint."""

    board_id: str
    board_fingerprint: str
    labels: tuple[SealedEpisodeLabel, ...]

    def __post_init__(self) -> None:
        _require_text(self.board_id, "board_id")
        _require_sha256(self.board_fingerprint, "board_fingerprint")
        labels = tuple(self.labels)
        object.__setattr__(self, "labels", labels)
        if not labels:
            raise ValueError("label vaults require labels")
        for label in labels:
            _require_instance(label, SealedEpisodeLabel, "labels item")
        if tuple(item.episode_id for item in labels) != tuple(
            sorted(item.episode_id for item in labels)
        ):
            raise ValueError("label vault entries must be sorted by episode id")
        for field_name, values in (
            ("label episode ids", tuple(item.episode_id for item in labels)),
            (
                "evaluator label ids",
                tuple(item.evaluator_label_id for item in labels),
            ),
            (
                "commitment nonces",
                tuple(item.commitment_nonce for item in labels),
            ),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"{field_name} must be unique")

    @property
    def fingerprint(self) -> str:
        return _sha256(self)


@dataclass(frozen=True, slots=True)
class PolicyDecisionPrediction(SerializableRecord):
    episode_id: str
    observation_fingerprint: str
    predicted_decision: Decision | None
    confidence: float | None

    def __post_init__(self) -> None:
        _require_opaque_id(
            self.episode_id,
            "episode_id",
            _EPISODE_ID_PATTERN,
        )
        _require_sha256(
            self.observation_fingerprint,
            "observation_fingerprint",
        )
        if self.predicted_decision is None:
            if self.confidence is not None:
                raise ValueError("missing predictions cannot carry confidence")
            return
        _require_instance(
            self.predicted_decision,
            Decision,
            "predicted_decision",
        )
        if self.confidence is None:
            raise ValueError("predicted decisions require confidence")
        _require_probability(self.confidence, "confidence")


@dataclass(frozen=True, slots=True)
class PolicyEvaluationSubmission(SerializableRecord):
    submission_id: str
    board_id: str
    board_fingerprint: str
    policy_id: str
    policy_version: str
    created_on: date
    predictions: tuple[PolicyDecisionPrediction, ...]
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for field_name in (
            "submission_id",
            "board_id",
            "policy_id",
            "policy_version",
        ):
            _require_text(getattr(self, field_name), field_name)
        _require_sha256(self.board_fingerprint, "board_fingerprint")
        _require_date(self.created_on, "created_on")
        predictions = tuple(self.predictions)
        object.__setattr__(self, "predictions", predictions)
        if not predictions:
            raise ValueError("policy submissions require predictions")
        for prediction in predictions:
            _require_instance(
                prediction,
                PolicyDecisionPrediction,
                "predictions item",
            )
        episode_ids = tuple(item.episode_id for item in predictions)
        if len(episode_ids) != len(set(episode_ids)):
            raise ValueError("prediction episode ids must be unique")
        if episode_ids != tuple(sorted(episode_ids)):
            raise ValueError("predictions must be sorted by episode id")
        frozen_metadata = _freeze_mapping(self.metadata, "metadata")
        if _contains_evaluator_key(frozen_metadata):
            raise ValueError(
                "policy submission metadata cannot contain evaluator-only labels"
            )
        object.__setattr__(self, "metadata", frozen_metadata)

    @property
    def fingerprint(self) -> str:
        return _sha256(self)


@dataclass(frozen=True, slots=True)
class EpisodePolicyEvaluation(SerializableRecord):
    episode_id: str
    pair_id: str
    arm: EpisodeArm
    predicted_decision: Decision | None
    gold_decision: Decision
    confidence: float | None
    exact_match: bool
    unsafe_advance: bool

    def __post_init__(self) -> None:
        _require_opaque_id(
            self.episode_id,
            "episode_id",
            _EPISODE_ID_PATTERN,
        )
        _require_opaque_id(self.pair_id, "pair_id", _PAIR_ID_PATTERN)
        _require_instance(self.arm, EpisodeArm, "arm")
        if self.predicted_decision is not None:
            _require_instance(
                self.predicted_decision,
                Decision,
                "predicted_decision",
            )
        _require_instance(self.gold_decision, Decision, "gold_decision")
        if self.confidence is not None:
            _require_probability(self.confidence, "confidence")
        if not isinstance(self.exact_match, bool):
            raise TypeError("exact_match must be boolean")
        if not isinstance(self.unsafe_advance, bool):
            raise TypeError("unsafe_advance must be boolean")
        if self.exact_match != (self.predicted_decision is self.gold_decision):
            raise ValueError("exact_match does not match the decisions")
        expected_unsafe = (
            self.predicted_decision is Decision.ADVANCE
            and self.gold_decision is not Decision.ADVANCE
        )
        if self.unsafe_advance != expected_unsafe:
            raise ValueError("unsafe_advance does not match the decisions")


@dataclass(frozen=True, slots=True)
class PolicyEvaluationSummary(SerializableRecord):
    policy_id: str
    policy_version: str
    pair_count: int
    episode_count: int
    exact_accuracy: float
    success_arm_accuracy: float
    failure_arm_accuracy: float
    both_correct_rate: float
    coverage: float
    defer_rate: float
    unsafe_advance_rate: float
    mean_confidence: float | None
    top_label_brier: float | None
    top_label_ece: float | None
    predicted_decision_counts: Mapping[str, int]
    gold_decision_counts: Mapping[str, int]
    confusion_counts: Mapping[str, int]
    failure_cause_counts: Mapping[str, int]

    def __post_init__(self) -> None:
        for field_name in ("policy_id", "policy_version"):
            _require_text(getattr(self, field_name), field_name)
        for field_name in ("pair_count", "episode_count"):
            value = getattr(self, field_name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 1:
                raise ValueError(f"{field_name} must be a positive integer")
        if self.episode_count != self.pair_count * 2:
            raise ValueError("episode_count must equal twice pair_count")
        for field_name in (
            "exact_accuracy",
            "success_arm_accuracy",
            "failure_arm_accuracy",
            "both_correct_rate",
            "coverage",
            "defer_rate",
            "unsafe_advance_rate",
        ):
            _require_probability(getattr(self, field_name), field_name)
        optional_probabilities = (
            self.mean_confidence,
            self.top_label_brier,
            self.top_label_ece,
        )
        for value, field_name in zip(
            optional_probabilities,
            ("mean_confidence", "top_label_brier", "top_label_ece"),
            strict=True,
        ):
            if value is not None:
                _require_probability(value, field_name)
        for field_name in (
            "predicted_decision_counts",
            "gold_decision_counts",
            "confusion_counts",
            "failure_cause_counts",
        ):
            counts = getattr(self, field_name)
            if not isinstance(counts, Mapping):
                raise TypeError(f"{field_name} must be a mapping")
            normalized = dict(counts)
            for key, value in normalized.items():
                _require_text(key, f"{field_name} key")
                if (
                    not isinstance(value, int)
                    or isinstance(value, bool)
                    or value < 0
                ):
                    raise ValueError(
                        f"{field_name} values must be non-negative integers"
                    )
            object.__setattr__(
                self,
                field_name,
                _freeze_mapping(normalized, field_name),
            )
        if sum(self.predicted_decision_counts.values()) != self.episode_count:
            raise ValueError("predicted decision counts must cover every episode")
        if sum(self.gold_decision_counts.values()) != self.episode_count:
            raise ValueError("gold decision counts must cover every episode")
        if sum(self.confusion_counts.values()) != self.episode_count:
            raise ValueError("confusion counts must cover every episode")


@dataclass(frozen=True, slots=True)
class PolicyEvaluationResult(SerializableRecord):
    submission_id: str
    submission_fingerprint: str
    board_id: str
    board_fingerprint: str
    vault_fingerprint: str
    episodes: tuple[EpisodePolicyEvaluation, ...]
    summary: PolicyEvaluationSummary

    def __post_init__(self) -> None:
        for field_name in ("submission_id", "board_id"):
            _require_text(getattr(self, field_name), field_name)
        for field_name in (
            "submission_fingerprint",
            "board_fingerprint",
            "vault_fingerprint",
        ):
            _require_sha256(getattr(self, field_name), field_name)
        episodes = tuple(self.episodes)
        object.__setattr__(self, "episodes", episodes)
        if not episodes:
            raise ValueError("policy evaluation results require episodes")
        for episode in episodes:
            _require_instance(
                episode,
                EpisodePolicyEvaluation,
                "episodes item",
            )
        _require_instance(self.summary, PolicyEvaluationSummary, "summary")
        if len(episodes) != self.summary.episode_count:
            raise ValueError("episode details do not match summary count")


@dataclass(frozen=True, slots=True)
class PolicyComparisonReport(SerializableRecord):
    evaluation_id: str
    board_id: str
    board_fingerprint: str
    vault_fingerprint: str
    summaries: tuple[PolicyEvaluationSummary, ...]
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        for field_name in ("evaluation_id", "board_id"):
            _require_text(getattr(self, field_name), field_name)
        for field_name in ("board_fingerprint", "vault_fingerprint"):
            _require_sha256(getattr(self, field_name), field_name)
        summaries = tuple(self.summaries)
        object.__setattr__(self, "summaries", summaries)
        if not summaries:
            raise ValueError("policy comparison requires at least one summary")
        for summary in summaries:
            _require_instance(
                summary,
                PolicyEvaluationSummary,
                "summaries item",
            )
        identities = tuple(
            (item.policy_id, item.policy_version) for item in summaries
        )
        if len(identities) != len(set(identities)):
            raise ValueError("policy identities must be unique")
        board_sizes = {
            (item.pair_count, item.episode_count) for item in summaries
        }
        if len(board_sizes) != 1:
            raise ValueError("policy summaries must describe one board size")
        frozen_limitations = _freeze_text_tuple(
            self.limitations,
            "limitations",
        )
        if not frozen_limitations:
            raise ValueError("policy comparison requires explicit limitations")
        object.__setattr__(
            self,
            "limitations",
            frozen_limitations,
        )

    @property
    def fingerprint(self) -> str:
        return _sha256(self)


def seal_matched_evaluation_board(
    *,
    board_id: str,
    version: str,
    split: EvaluationBoardSplit,
    created_on: date,
    pairs: Sequence[MatchedEpisodePair],
    sealing_secret: str,
    visible_packets_by_episode_id: Mapping[str, Mapping[str, Any]],
    packet_available_at_by_episode_id: Mapping[str, date],
    metadata: Mapping[str, Any] | None = None,
) -> tuple[SealedEvaluationBoard, SealedEvaluationVault]:
    """Split complete matched episodes into a role-neutral board and label vault."""

    _require_text(board_id, "board_id")
    secret = _require_non_empty_secret(sealing_secret)
    resolved_pairs = tuple(pairs)
    summarize_matched_pairs(resolved_pairs)
    source_episode_ids = {
        episode.episode_id
        for pair in resolved_pairs
        for episode in (pair.success, pair.failure)
    }
    if set(visible_packets_by_episode_id) != source_episode_ids:
        raise ValueError(
            "visible packet mapping must cover every source episode exactly"
        )
    if set(packet_available_at_by_episode_id) != source_episode_ids:
        raise ValueError(
            "packet availability mapping must cover every source episode exactly"
        )
    observations: list[CutoffEpisodeObservation] = []
    labels: list[SealedEpisodeLabel] = []
    pair_index: list[OpaqueMatchedPair] = []
    for pair in resolved_pairs:
        opaque_pair_id = _opaque_pair_id(secret, board_id, pair.pair_id)
        opaque_episode_ids: list[str] = []
        for source_episode in (pair.success, pair.failure):
            opaque_episode_id = _opaque_episode_id(
                secret,
                board_id,
                source_episode.episode_id,
            )
            opaque_episode_ids.append(opaque_episode_id)
            opaque_program_id = _opaque_program_id(
                secret,
                board_id,
                source_episode.episode_id,
            )
            visible_state = _opaque_visible_state(
                source_episode.visible_state,
                program_id=opaque_program_id,
            )
            opaque_packet_id = _opaque_packet_id(
                secret,
                board_id,
                source_episode.available_evidence_packet_id,
            )
            visible_packet = visible_packets_by_episode_id[
                source_episode.episode_id
            ]
            packet_available_at = packet_available_at_by_episode_id[
                source_episode.episode_id
            ]
            _require_date(
                packet_available_at,
                "packet_available_at_by_episode_id value",
            )
            packet_sha256 = _sha256(visible_packet)
            label = SealedEpisodeLabel(
                episode_id=opaque_episode_id,
                pair_id=opaque_pair_id,
                evaluator_label_id=_opaque_label_id(
                    secret,
                    board_id,
                    source_episode.evaluator_label_id,
                ),
                arm=source_episode.arm,
                gold_decision=source_episode.gold_decision,
                commitment_nonce=_opaque_digest(
                    secret,
                    board_id,
                    "commitment-nonce",
                    source_episode.evaluator_label_id,
                ),
                failure_causes=source_episode.failure_causes,
                evaluator_metadata=source_episode.evaluator_metadata,
            )
            labels.append(label)
            observations.append(
                CutoffEpisodeObservation(
                    episode_id=opaque_episode_id,
                    pair_id=opaque_pair_id,
                    match_key=source_episode.match_key,
                    decision_cutoff=source_episode.decision_cutoff,
                    visible_state=visible_state,
                    asset_or_candidate_id=source_episode.asset_or_candidate_id,
                    target_or_mechanism_id=(
                        source_episode.target_or_mechanism_id
                    ),
                    condition_or_context_id=(
                        source_episode.condition_or_context_id
                    ),
                    available_evidence_packet_id=opaque_packet_id,
                    available_evidence_packet_available_at=(
                        packet_available_at
                    ),
                    available_evidence_packet=visible_packet,
                    available_evidence_packet_sha256=packet_sha256,
                    label_commitment=label.commitment,
                )
            )
        pair_index.append(
            OpaqueMatchedPair(
                pair_id=opaque_pair_id,
                episode_ids=tuple(sorted(opaque_episode_ids)),
            )
        )
    board = SealedEvaluationBoard(
        board_id=board_id,
        version=version,
        split=split,
        created_on=created_on,
        observations=tuple(sorted(observations, key=lambda item: item.episode_id)),
        pairs=tuple(sorted(pair_index, key=lambda item: item.pair_id)),
        metadata=metadata or {},
    )
    vault = SealedEvaluationVault(
        board_id=board.board_id,
        board_fingerprint=board.fingerprint,
        labels=tuple(sorted(labels, key=lambda item: item.episode_id)),
    )
    validate_evaluation_vault(board, vault)
    return board, vault


def policy_submission_from_matched_pairs(
    *,
    board: SealedEvaluationBoard,
    pairs: Sequence[MatchedEpisodePair],
    sealing_secret: str,
    submission_id: str,
    policy_id: str,
    policy_version: str,
    created_on: date,
    confidence_by_episode_id: Mapping[str, float] | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> PolicyEvaluationSubmission:
    """Bind predictions already present in matched episodes to sealed observations."""

    secret = _require_non_empty_secret(sealing_secret)
    resolved_pairs = tuple(pairs)
    summarize_matched_pairs(resolved_pairs)
    observations = {item.episode_id: item for item in board.observations}
    confidence_by_episode_id = confidence_by_episode_id or {}
    source_episode_ids = {
        episode.episode_id
        for pair in resolved_pairs
        for episode in (pair.success, pair.failure)
    }
    unknown_confidence_ids = set(confidence_by_episode_id) - source_episode_ids
    if unknown_confidence_ids:
        raise ValueError("confidence mapping contains unknown episode ids")
    predictions: list[PolicyDecisionPrediction] = []
    for pair in resolved_pairs:
        for episode in (pair.success, pair.failure):
            opaque_episode_id = _opaque_episode_id(
                secret,
                board.board_id,
                episode.episode_id,
            )
            observation = observations.get(opaque_episode_id)
            if observation is None:
                raise ValueError("matched episode is not present in the sealed board")
            if episode.predicted_decision is None:
                confidence = None
            else:
                if episode.episode_id not in confidence_by_episode_id:
                    raise ValueError(
                        "predicted decisions require explicit episode confidence"
                    )
                confidence = confidence_by_episode_id[episode.episode_id]
            predictions.append(
                PolicyDecisionPrediction(
                    episode_id=opaque_episode_id,
                    observation_fingerprint=observation.fingerprint,
                    predicted_decision=episode.predicted_decision,
                    confidence=confidence,
                )
            )
    return PolicyEvaluationSubmission(
        submission_id=submission_id,
        board_id=board.board_id,
        board_fingerprint=board.fingerprint,
        policy_id=policy_id,
        policy_version=policy_version,
        created_on=created_on,
        predictions=tuple(sorted(predictions, key=lambda item: item.episode_id)),
        metadata=metadata or {},
    )


def constant_policy_submission(
    *,
    board: SealedEvaluationBoard,
    submission_id: str,
    policy_id: str,
    policy_version: str,
    created_on: date,
    decision: Decision,
    confidence: float,
    metadata: Mapping[str, Any] | None = None,
) -> PolicyEvaluationSubmission:
    """Create a fingerprint-bound constant-decision baseline."""

    _require_instance(decision, Decision, "decision")
    _require_probability(confidence, "confidence")
    return PolicyEvaluationSubmission(
        submission_id=submission_id,
        board_id=board.board_id,
        board_fingerprint=board.fingerprint,
        policy_id=policy_id,
        policy_version=policy_version,
        created_on=created_on,
        predictions=tuple(
            PolicyDecisionPrediction(
                episode_id=observation.episode_id,
                observation_fingerprint=observation.fingerprint,
                predicted_decision=decision,
                confidence=confidence,
            )
            for observation in board.observations
        ),
        metadata=metadata or {},
    )


def validate_evaluation_vault(
    board: SealedEvaluationBoard,
    vault: SealedEvaluationVault,
) -> Mapping[str, SealedEpisodeLabel]:
    """Open commitments only inside the evaluator boundary."""

    _require_instance(board, SealedEvaluationBoard, "board")
    _require_instance(vault, SealedEvaluationVault, "vault")
    if vault.board_id != board.board_id:
        raise ValueError("label vault belongs to another board")
    if vault.board_fingerprint != board.fingerprint:
        raise ValueError("label vault is bound to another board fingerprint")
    observations = {item.episode_id: item for item in board.observations}
    labels = {item.episode_id: item for item in vault.labels}
    if set(labels) != set(observations):
        raise ValueError("label vault must cover every board observation exactly")
    for episode_id, label in labels.items():
        observation = observations[episode_id]
        if label.pair_id != observation.pair_id:
            raise ValueError("label pair id does not match the observation")
        if label.commitment != observation.label_commitment:
            raise ValueError("label commitment does not match the sealed board")
    for pair in board.pairs:
        arms = {labels[episode_id].arm for episode_id in pair.episode_ids}
        if arms != {EpisodeArm.SUCCESS, EpisodeArm.FAILURE}:
            raise ValueError(
                "each sealed pair must open to one success and one failure arm"
            )
    return labels


def _increment(counts: dict[str, int], key: str) -> None:
    counts[key] = counts.get(key, 0) + 1


def _confidence_metrics(
    episodes: Sequence[EpisodePolicyEvaluation],
    *,
    bin_count: int,
) -> tuple[float | None, float | None, float | None]:
    if not isinstance(bin_count, int) or isinstance(bin_count, bool) or bin_count < 1:
        raise ValueError("bin_count must be a positive integer")
    scored = tuple(item for item in episodes if item.confidence is not None)
    if not scored:
        return None, None, None
    mean_confidence = sum(float(item.confidence) for item in scored) / len(scored)
    brier = sum(
        (float(item.confidence) - float(item.exact_match)) ** 2 for item in scored
    ) / len(scored)
    bins: list[list[EpisodePolicyEvaluation]] = [[] for _ in range(bin_count)]
    for item in scored:
        confidence = float(item.confidence)
        index = min(int(confidence * bin_count), bin_count - 1)
        bins[index].append(item)
    ece = 0.0
    for items in bins:
        if not items:
            continue
        average_confidence = sum(float(item.confidence) for item in items) / len(
            items
        )
        accuracy = sum(item.exact_match for item in items) / len(items)
        ece += len(items) / len(scored) * abs(accuracy - average_confidence)
    return mean_confidence, brier, ece


def evaluate_policy_submission(
    board: SealedEvaluationBoard,
    vault: SealedEvaluationVault,
    submission: PolicyEvaluationSubmission,
    *,
    calibration_bin_count: int = 5,
) -> PolicyEvaluationResult:
    """Score one exact board submission after validating every commitment."""

    labels = validate_evaluation_vault(board, vault)
    _require_instance(
        submission,
        PolicyEvaluationSubmission,
        "submission",
    )
    if (
        submission.board_id != board.board_id
        or submission.board_fingerprint != board.fingerprint
    ):
        raise ValueError("policy submission is bound to another board")
    if submission.created_on < board.created_on:
        raise ValueError("policy submission cannot predate board creation")
    observations = {item.episode_id: item for item in board.observations}
    predictions = {item.episode_id: item for item in submission.predictions}
    if set(predictions) != set(observations):
        raise ValueError("policy submission must cover every observation exactly")
    episode_results: list[EpisodePolicyEvaluation] = []
    predicted_counts: dict[str, int] = {}
    gold_counts: dict[str, int] = {}
    confusion_counts: dict[str, int] = {}
    failure_cause_counts: dict[str, int] = {}
    for episode_id in sorted(observations):
        observation = observations[episode_id]
        prediction = predictions[episode_id]
        label = labels[episode_id]
        if prediction.observation_fingerprint != observation.fingerprint:
            raise ValueError("prediction is bound to another observation")
        predicted_key = (
            prediction.predicted_decision.value
            if prediction.predicted_decision is not None
            else "missing"
        )
        _increment(predicted_counts, predicted_key)
        _increment(gold_counts, label.gold_decision.value)
        _increment(
            confusion_counts,
            f"gold={label.gold_decision.value}|predicted={predicted_key}",
        )
        for cause in label.failure_causes:
            _increment(failure_cause_counts, cause.value)
        exact = prediction.predicted_decision is label.gold_decision
        unsafe = (
            prediction.predicted_decision is Decision.ADVANCE
            and label.gold_decision is not Decision.ADVANCE
        )
        episode_results.append(
            EpisodePolicyEvaluation(
                episode_id=episode_id,
                pair_id=observation.pair_id,
                arm=label.arm,
                predicted_decision=prediction.predicted_decision,
                gold_decision=label.gold_decision,
                confidence=prediction.confidence,
                exact_match=exact,
                unsafe_advance=unsafe,
            )
        )
    results = tuple(episode_results)
    success = tuple(item for item in results if item.arm is EpisodeArm.SUCCESS)
    failure = tuple(item for item in results if item.arm is EpisodeArm.FAILURE)
    both_correct = 0
    results_by_id = {item.episode_id: item for item in results}
    for pair in board.pairs:
        if all(results_by_id[item].exact_match for item in pair.episode_ids):
            both_correct += 1
    unsafe_denominator = tuple(
        item for item in results if item.gold_decision is not Decision.ADVANCE
    )
    mean_confidence, brier, ece = _confidence_metrics(
        results,
        bin_count=calibration_bin_count,
    )
    episode_count = len(results)
    summary = PolicyEvaluationSummary(
        policy_id=submission.policy_id,
        policy_version=submission.policy_version,
        pair_count=len(board.pairs),
        episode_count=episode_count,
        exact_accuracy=sum(item.exact_match for item in results) / episode_count,
        success_arm_accuracy=sum(item.exact_match for item in success)
        / len(success),
        failure_arm_accuracy=sum(item.exact_match for item in failure)
        / len(failure),
        both_correct_rate=both_correct / len(board.pairs),
        coverage=sum(item.predicted_decision is not None for item in results)
        / episode_count,
        defer_rate=sum(
            item.predicted_decision is Decision.DEFER for item in results
        )
        / episode_count,
        unsafe_advance_rate=(
            sum(item.unsafe_advance for item in unsafe_denominator)
            / len(unsafe_denominator)
            if unsafe_denominator
            else 0.0
        ),
        mean_confidence=mean_confidence,
        top_label_brier=brier,
        top_label_ece=ece,
        predicted_decision_counts=predicted_counts,
        gold_decision_counts=gold_counts,
        confusion_counts=confusion_counts,
        failure_cause_counts=failure_cause_counts,
    )
    return PolicyEvaluationResult(
        submission_id=submission.submission_id,
        submission_fingerprint=submission.fingerprint,
        board_id=board.board_id,
        board_fingerprint=board.fingerprint,
        vault_fingerprint=vault.fingerprint,
        episodes=results,
        summary=summary,
    )


def compare_policy_submissions(
    *,
    evaluation_id: str,
    board: SealedEvaluationBoard,
    vault: SealedEvaluationVault,
    submissions: Sequence[PolicyEvaluationSubmission],
    limitations: Sequence[str],
    calibration_bin_count: int = 5,
) -> PolicyComparisonReport:
    """Evaluate multiple policies on one board without selecting a winner."""

    resolved = tuple(submissions)
    if not resolved:
        raise ValueError("policy comparison requires submissions")
    results = tuple(
        evaluate_policy_submission(
            board,
            vault,
            submission,
            calibration_bin_count=calibration_bin_count,
        )
        for submission in resolved
    )
    return PolicyComparisonReport(
        evaluation_id=evaluation_id,
        board_id=board.board_id,
        board_fingerprint=board.fingerprint,
        vault_fingerprint=vault.fingerprint,
        summaries=tuple(item.summary for item in results),
        limitations=tuple(limitations),
    )


def sealed_evaluation_board_envelope(
    board: SealedEvaluationBoard,
) -> dict[str, Any]:
    _require_instance(board, SealedEvaluationBoard, "board")
    return {
        "schema_version": SEALED_EVALUATION_BOARD_SCHEMA_VERSION,
        "integrity_sha256": board.fingerprint,
        "board": board.to_dict(),
    }


def sealed_evaluation_vault_envelope(
    vault: SealedEvaluationVault,
) -> dict[str, Any]:
    _require_instance(vault, SealedEvaluationVault, "vault")
    return {
        "schema_version": SEALED_EVALUATION_VAULT_SCHEMA_VERSION,
        "integrity_sha256": vault.fingerprint,
        "vault": vault.to_dict(),
    }


def policy_evaluation_submission_envelope(
    submission: PolicyEvaluationSubmission,
) -> dict[str, Any]:
    _require_instance(
        submission,
        PolicyEvaluationSubmission,
        "submission",
    )
    return {
        "schema_version": POLICY_EVALUATION_SUBMISSION_SCHEMA_VERSION,
        "integrity_sha256": submission.fingerprint,
        "submission": submission.to_dict(),
    }


def policy_evaluation_report_envelope(
    report: PolicyComparisonReport,
) -> dict[str, Any]:
    _require_instance(report, PolicyComparisonReport, "report")
    return {
        "schema_version": POLICY_EVALUATION_REPORT_SCHEMA_VERSION,
        "integrity_sha256": report.fingerprint,
        "report": report.to_dict(),
    }


def _parse_record(
    value: Any,
    path: str,
    fields: set[str],
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise RecordParseError(f"{path} must be an object")
    data = dict(value)
    missing = fields - set(data)
    extra = set(data) - fields
    if missing:
        raise RecordParseError(
            f"{path} missing fields: {', '.join(sorted(missing))}"
        )
    if extra:
        raise RecordParseError(
            f"{path} has unknown fields: {', '.join(sorted(extra))}"
        )
    return data


def _parse_sequence(value: Any, path: str) -> tuple[Any, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise RecordParseError(f"{path} must be an array")
    return tuple(value)


def _parse_mapping(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise RecordParseError(f"{path} must be an object")
    return dict(value)


def _parse_date(value: Any, path: str) -> date:
    if not isinstance(value, str):
        raise RecordParseError(f"{path} must be an ISO date")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise RecordParseError(f"{path} must be an ISO date") from exc


def _parse_enum(enum_type, value: Any, path: str):
    try:
        return enum_type(value)
    except (TypeError, ValueError) as exc:
        raise RecordParseError(
            f"{path} is not a valid {enum_type.__name__}"
        ) from exc


def _parse_integrity_envelope(
    value: Any,
    *,
    path: str,
    schema_version: str,
    payload_key: str,
) -> tuple[dict[str, Any], str]:
    envelope = _parse_record(
        value,
        path,
        {"schema_version", "integrity_sha256", payload_key},
    )
    if envelope["schema_version"] != schema_version:
        raise RecordParseError(f"{path} schema_version is unsupported")
    expected_hash = envelope["integrity_sha256"]
    if (
        not isinstance(expected_hash, str)
        or re.fullmatch(r"[0-9a-f]{64}", expected_hash) is None
    ):
        raise RecordParseError(
            f"{path}.integrity_sha256 must be a lowercase SHA-256 digest"
        )
    raw = _parse_mapping(envelope[payload_key], f"{path}.{payload_key}")
    if _sha256(raw) != expected_hash:
        raise RecordParseError(f"{path} integrity hash does not match")
    return raw, expected_hash


def _parse_match_key(value: Any, path: str) -> EpisodeMatchKey:
    data = _parse_record(
        value,
        path,
        {
            "disease",
            "stage",
            "modality",
            "population",
            "endpoint_family",
            "target_or_mechanism",
            "decision_time_bin",
        },
    )
    return EpisodeMatchKey(
        disease=data["disease"],
        stage=_parse_enum(Stage, data["stage"], f"{path}.stage"),
        modality=data["modality"],
        population=data["population"],
        endpoint_family=data["endpoint_family"],
        target_or_mechanism=data["target_or_mechanism"],
        decision_time_bin=data["decision_time_bin"],
    )


def _parse_observation(
    value: Any,
    path: str,
) -> CutoffEpisodeObservation:
    data = _parse_record(
        value,
        path,
        {
            "episode_id",
            "pair_id",
            "match_key",
            "decision_cutoff",
            "visible_state",
            "asset_or_candidate_id",
            "target_or_mechanism_id",
            "condition_or_context_id",
            "available_evidence_packet_id",
            "available_evidence_packet_available_at",
            "available_evidence_packet",
            "available_evidence_packet_sha256",
            "label_commitment",
        },
    )
    return CutoffEpisodeObservation(
        episode_id=data["episode_id"],
        pair_id=data["pair_id"],
        match_key=_parse_match_key(data["match_key"], f"{path}.match_key"),
        decision_cutoff=_parse_date(
            data["decision_cutoff"],
            f"{path}.decision_cutoff",
        ),
        visible_state=program_state_from_dict(
            data["visible_state"],
            f"{path}.visible_state",
        ),
        asset_or_candidate_id=data["asset_or_candidate_id"],
        target_or_mechanism_id=data["target_or_mechanism_id"],
        condition_or_context_id=data["condition_or_context_id"],
        available_evidence_packet_id=data["available_evidence_packet_id"],
        available_evidence_packet_available_at=_parse_date(
            data["available_evidence_packet_available_at"],
            f"{path}.available_evidence_packet_available_at",
        ),
        available_evidence_packet=_parse_mapping(
            data["available_evidence_packet"],
            f"{path}.available_evidence_packet",
        ),
        available_evidence_packet_sha256=(
            data["available_evidence_packet_sha256"]
        ),
        label_commitment=data["label_commitment"],
    )


def _parse_pair(value: Any, path: str) -> OpaqueMatchedPair:
    data = _parse_record(value, path, {"pair_id", "episode_ids"})
    return OpaqueMatchedPair(
        pair_id=data["pair_id"],
        episode_ids=tuple(
            _parse_sequence(data["episode_ids"], f"{path}.episode_ids")
        ),
    )


def sealed_evaluation_board_from_dict(value: Any) -> SealedEvaluationBoard:
    """Parse and integrity-check one role-neutral board envelope."""

    raw, expected_hash = _parse_integrity_envelope(
        value,
        path="sealed_evaluation_board_envelope",
        schema_version=SEALED_EVALUATION_BOARD_SCHEMA_VERSION,
        payload_key="board",
    )
    data = _parse_record(
        raw,
        "board",
        {
            "board_id",
            "version",
            "split",
            "created_on",
            "observations",
            "pairs",
            "metadata",
        },
    )
    board = SealedEvaluationBoard(
        board_id=data["board_id"],
        version=data["version"],
        split=_parse_enum(
            EvaluationBoardSplit,
            data["split"],
            "board.split",
        ),
        created_on=_parse_date(data["created_on"], "board.created_on"),
        observations=tuple(
            _parse_observation(item, f"board.observations[{index}]")
            for index, item in enumerate(
                _parse_sequence(data["observations"], "board.observations")
            )
        ),
        pairs=tuple(
            _parse_pair(item, f"board.pairs[{index}]")
            for index, item in enumerate(
                _parse_sequence(data["pairs"], "board.pairs")
            )
        ),
        metadata=_parse_mapping(data["metadata"], "board.metadata"),
    )
    if board.fingerprint != expected_hash:
        raise RecordParseError("parsed sealed board changed canonical identity")
    return board


def _parse_label(value: Any, path: str) -> SealedEpisodeLabel:
    data = _parse_record(
        value,
        path,
        {
            "episode_id",
            "pair_id",
            "evaluator_label_id",
            "arm",
            "gold_decision",
            "commitment_nonce",
            "failure_causes",
            "evaluator_metadata",
        },
    )
    return SealedEpisodeLabel(
        episode_id=data["episode_id"],
        pair_id=data["pair_id"],
        evaluator_label_id=data["evaluator_label_id"],
        arm=_parse_enum(EpisodeArm, data["arm"], f"{path}.arm"),
        gold_decision=_parse_enum(
            Decision,
            data["gold_decision"],
            f"{path}.gold_decision",
        ),
        commitment_nonce=data["commitment_nonce"],
        failure_causes=tuple(
            _parse_enum(
                FailureCause,
                item,
                f"{path}.failure_causes[{index}]",
            )
            for index, item in enumerate(
                _parse_sequence(
                    data["failure_causes"],
                    f"{path}.failure_causes",
                )
            )
        ),
        evaluator_metadata=_parse_mapping(
            data["evaluator_metadata"],
            f"{path}.evaluator_metadata",
        ),
    )


def sealed_evaluation_vault_from_dict(value: Any) -> SealedEvaluationVault:
    """Parse and integrity-check one evaluator-only vault envelope."""

    raw, expected_hash = _parse_integrity_envelope(
        value,
        path="sealed_evaluation_vault_envelope",
        schema_version=SEALED_EVALUATION_VAULT_SCHEMA_VERSION,
        payload_key="vault",
    )
    data = _parse_record(
        raw,
        "vault",
        {"board_id", "board_fingerprint", "labels"},
    )
    vault = SealedEvaluationVault(
        board_id=data["board_id"],
        board_fingerprint=data["board_fingerprint"],
        labels=tuple(
            _parse_label(item, f"vault.labels[{index}]")
            for index, item in enumerate(
                _parse_sequence(data["labels"], "vault.labels")
            )
        ),
    )
    if vault.fingerprint != expected_hash:
        raise RecordParseError("parsed label vault changed canonical identity")
    return vault


def _parse_prediction(
    value: Any,
    path: str,
) -> PolicyDecisionPrediction:
    data = _parse_record(
        value,
        path,
        {
            "episode_id",
            "observation_fingerprint",
            "predicted_decision",
            "confidence",
        },
    )
    predicted = data["predicted_decision"]
    return PolicyDecisionPrediction(
        episode_id=data["episode_id"],
        observation_fingerprint=data["observation_fingerprint"],
        predicted_decision=(
            None
            if predicted is None
            else _parse_enum(
                Decision,
                predicted,
                f"{path}.predicted_decision",
            )
        ),
        confidence=data["confidence"],
    )


def policy_evaluation_submission_from_dict(
    value: Any,
) -> PolicyEvaluationSubmission:
    """Parse and integrity-check one complete policy submission envelope."""

    raw, expected_hash = _parse_integrity_envelope(
        value,
        path="policy_evaluation_submission_envelope",
        schema_version=POLICY_EVALUATION_SUBMISSION_SCHEMA_VERSION,
        payload_key="submission",
    )
    data = _parse_record(
        raw,
        "submission",
        {
            "submission_id",
            "board_id",
            "board_fingerprint",
            "policy_id",
            "policy_version",
            "created_on",
            "predictions",
            "metadata",
        },
    )
    submission = PolicyEvaluationSubmission(
        submission_id=data["submission_id"],
        board_id=data["board_id"],
        board_fingerprint=data["board_fingerprint"],
        policy_id=data["policy_id"],
        policy_version=data["policy_version"],
        created_on=_parse_date(data["created_on"], "submission.created_on"),
        predictions=tuple(
            _parse_prediction(item, f"submission.predictions[{index}]")
            for index, item in enumerate(
                _parse_sequence(
                    data["predictions"],
                    "submission.predictions",
                )
            )
        ),
        metadata=_parse_mapping(data["metadata"], "submission.metadata"),
    )
    if submission.fingerprint != expected_hash:
        raise RecordParseError(
            "parsed policy submission changed canonical identity"
        )
    return submission


def _parse_summary(value: Any, path: str) -> PolicyEvaluationSummary:
    data = _parse_record(
        value,
        path,
        {
            "policy_id",
            "policy_version",
            "pair_count",
            "episode_count",
            "exact_accuracy",
            "success_arm_accuracy",
            "failure_arm_accuracy",
            "both_correct_rate",
            "coverage",
            "defer_rate",
            "unsafe_advance_rate",
            "mean_confidence",
            "top_label_brier",
            "top_label_ece",
            "predicted_decision_counts",
            "gold_decision_counts",
            "confusion_counts",
            "failure_cause_counts",
        },
    )
    return PolicyEvaluationSummary(
        policy_id=data["policy_id"],
        policy_version=data["policy_version"],
        pair_count=data["pair_count"],
        episode_count=data["episode_count"],
        exact_accuracy=data["exact_accuracy"],
        success_arm_accuracy=data["success_arm_accuracy"],
        failure_arm_accuracy=data["failure_arm_accuracy"],
        both_correct_rate=data["both_correct_rate"],
        coverage=data["coverage"],
        defer_rate=data["defer_rate"],
        unsafe_advance_rate=data["unsafe_advance_rate"],
        mean_confidence=data["mean_confidence"],
        top_label_brier=data["top_label_brier"],
        top_label_ece=data["top_label_ece"],
        predicted_decision_counts=_parse_mapping(
            data["predicted_decision_counts"],
            f"{path}.predicted_decision_counts",
        ),
        gold_decision_counts=_parse_mapping(
            data["gold_decision_counts"],
            f"{path}.gold_decision_counts",
        ),
        confusion_counts=_parse_mapping(
            data["confusion_counts"],
            f"{path}.confusion_counts",
        ),
        failure_cause_counts=_parse_mapping(
            data["failure_cause_counts"],
            f"{path}.failure_cause_counts",
        ),
    )


def policy_evaluation_report_from_dict(
    value: Any,
) -> PolicyComparisonReport:
    """Parse and integrity-check one aggregate policy comparison envelope."""

    raw, expected_hash = _parse_integrity_envelope(
        value,
        path="policy_evaluation_report_envelope",
        schema_version=POLICY_EVALUATION_REPORT_SCHEMA_VERSION,
        payload_key="report",
    )
    data = _parse_record(
        raw,
        "report",
        {
            "evaluation_id",
            "board_id",
            "board_fingerprint",
            "vault_fingerprint",
            "summaries",
            "limitations",
        },
    )
    report = PolicyComparisonReport(
        evaluation_id=data["evaluation_id"],
        board_id=data["board_id"],
        board_fingerprint=data["board_fingerprint"],
        vault_fingerprint=data["vault_fingerprint"],
        summaries=tuple(
            _parse_summary(item, f"report.summaries[{index}]")
            for index, item in enumerate(
                _parse_sequence(data["summaries"], "report.summaries")
            )
        ),
        limitations=tuple(
            _parse_sequence(data["limitations"], "report.limitations")
        ),
    )
    if report.fingerprint != expected_hash:
        raise RecordParseError(
            "parsed policy comparison report changed canonical identity"
        )
    return report


def _parse_envelope_json(payload: str, label: str) -> Any:
    if not isinstance(payload, str):
        raise TypeError("payload must be a string")

    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, item in pairs:
            if key in result:
                raise RecordParseError(f"{label} duplicates key {key}")
            result[key] = item
        return result

    try:
        return json.loads(
            payload,
            object_pairs_hook=unique_object,
            parse_constant=lambda item: (_ for _ in ()).throw(
                RecordParseError(f"{label} contains {item}")
            ),
        )
    except json.JSONDecodeError as exc:
        raise RecordParseError(f"{label} is not valid JSON") from exc


def sealed_evaluation_board_from_json(payload: str) -> SealedEvaluationBoard:
    """Parse JSON without accepting duplicate keys or non-finite values."""

    return sealed_evaluation_board_from_dict(
        _parse_envelope_json(payload, "sealed evaluation board")
    )


def sealed_evaluation_vault_from_json(payload: str) -> SealedEvaluationVault:
    """Parse evaluator-vault JSON without duplicate keys or non-finite values."""

    return sealed_evaluation_vault_from_dict(
        _parse_envelope_json(payload, "sealed evaluation vault")
    )


def policy_evaluation_submission_from_json(
    payload: str,
) -> PolicyEvaluationSubmission:
    """Parse submission JSON without duplicate keys or non-finite values."""

    return policy_evaluation_submission_from_dict(
        _parse_envelope_json(payload, "policy evaluation submission")
    )


def policy_evaluation_report_from_json(
    payload: str,
) -> PolicyComparisonReport:
    """Parse report JSON without duplicate keys or non-finite values."""

    return policy_evaluation_report_from_dict(
        _parse_envelope_json(payload, "policy evaluation report")
    )
