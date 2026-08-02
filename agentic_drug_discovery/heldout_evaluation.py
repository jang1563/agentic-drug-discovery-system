"""Independently curated held-out evaluation with stage-level uncertainty."""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from enum import Enum
from statistics import NormalDist
from typing import Any

from .matched_evaluation import (
    EpisodeArm,
    MatchedEpisodePair,
    _contains_evaluator_key,
)
from .models import (
    Decision,
    SerializableRecord,
    Stage,
    _freeze_mapping,
    _freeze_text_tuple,
    _require_date,
    _require_instance,
    _require_probability,
    _require_sha256,
    _require_text,
)
from .sealed_evaluation import (
    EpisodePolicyEvaluation,
    EvaluationBoardSplit,
    PolicyEvaluationSubmission,
    SealedEvaluationBoard,
    SealedEvaluationVault,
    _parse_date,
    _parse_enum,
    _parse_envelope_json,
    _parse_integrity_envelope,
    _parse_mapping,
    _parse_record,
    _parse_sequence,
    _sha256,
    evaluate_policy_submission,
    seal_matched_evaluation_board,
    validate_evaluation_vault,
)
from .serialization import RecordParseError

HELDOUT_EVALUATION_PROTOCOL_SCHEMA_VERSION = (
    "adds.heldout-evaluation-protocol.v1"
)
HELDOUT_CURATION_MANIFEST_SCHEMA_VERSION = (
    "adds.heldout-curation-manifest.v1"
)
STAGE_STRATIFIED_EVALUATION_REPORT_SCHEMA_VERSION = (
    "adds.stage-stratified-evaluation-report.v1"
)

_CURATOR_ID_PATTERN = re.compile(r"^cur-[0-9a-f]{16}$")
_EPISODE_ID_PATTERN = re.compile(r"^ep-[0-9a-f]{24}$")
_HELDOUT_PROTOCOL_ID_KEY = "heldout_protocol_id"
_HELDOUT_PROTOCOL_FINGERPRINT_KEY = "heldout_protocol_fingerprint"
_STAGE_ORDER = {stage: index for index, stage in enumerate(Stage)}
_REQUIRED_REPORT_LIMITATIONS = (
    "Wilson intervals quantify finite-board sampling uncertainty only.",
    (
        "Episode-level Wilson intervals do not adjust for within-pair "
        "dependence or curator-label uncertainty."
    ),
    "Action coverage excludes missing and explicit defer decisions.",
    "Held-out policy scores do not establish prospective clinical utility.",
)


class LabelConsensusRule(str, Enum):
    UNANIMOUS = "unanimous"
    STRICT_MAJORITY = "strict_majority"
    ADJUDICATED = "adjudicated"


class CuratorRole(str, Enum):
    CURATOR = "curator"
    ADJUDICATOR = "adjudicator"


class IntervalMethod(str, Enum):
    WILSON_SCORE = "wilson_score"


class MissingPredictionRule(str, Enum):
    COUNT_AS_INCORRECT = "count_as_incorrect"


class ActionCoverageRule(str, Enum):
    NON_MISSING_NON_DEFER = "non_missing_non_defer"


def _require_positive_int(value: int, field_name: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ValueError(f"{field_name} must be a positive integer")


def _require_bool(value: bool, field_name: str) -> None:
    if not isinstance(value, bool):
        raise TypeError(f"{field_name} must be boolean")


def _require_opaque_curator_id(value: str, field_name: str) -> None:
    _require_text(value, field_name)
    if _CURATOR_ID_PATTERN.fullmatch(value) is None:
        raise ValueError(f"{field_name} must be an opaque curator identifier")


@dataclass(frozen=True, slots=True)
class StageEvaluationRequirement(SerializableRecord):
    stage: Stage
    minimum_pairs: int
    minimum_action_covered_episodes: int

    def __post_init__(self) -> None:
        _require_instance(self.stage, Stage, "stage")
        _require_positive_int(self.minimum_pairs, "minimum_pairs")
        _require_positive_int(
            self.minimum_action_covered_episodes,
            "minimum_action_covered_episodes",
        )
        if self.minimum_action_covered_episodes > self.minimum_pairs * 2:
            raise ValueError(
                "minimum action-covered episodes cannot exceed the minimum "
                "episode count"
            )


@dataclass(frozen=True, slots=True)
class HeldoutLabelPolicy(SerializableRecord):
    policy_id: str
    version: str
    allowed_decisions: tuple[Decision, ...]
    decision_definitions: Mapping[str, str]
    consensus_rule: LabelConsensusRule
    minimum_independent_curators: int
    outcome_window_days: int
    label_guidance_sha256: str
    exclusion_rules_sha256: str
    policy_blinding_required: bool = True
    conflict_free_required: bool = True
    adjudicator_independence_required: bool = True

    def __post_init__(self) -> None:
        for field_name in ("policy_id", "version"):
            _require_text(getattr(self, field_name), field_name)
        decisions = tuple(self.allowed_decisions)
        object.__setattr__(self, "allowed_decisions", decisions)
        if len(decisions) < 2 or len(decisions) != len(set(decisions)):
            raise ValueError(
                "allowed_decisions must contain at least two unique decisions"
            )
        for decision in decisions:
            _require_instance(decision, Decision, "allowed_decisions item")
        if decisions != tuple(sorted(decisions, key=lambda item: item.value)):
            raise ValueError("allowed_decisions must be sorted by decision value")
        if Decision.ADVANCE not in decisions:
            raise ValueError("allowed_decisions must include advance")
        if not any(decision is not Decision.ADVANCE for decision in decisions):
            raise ValueError("allowed_decisions require a non-advance label")
        definitions = dict(self.decision_definitions)
        expected_definition_keys = {decision.value for decision in decisions}
        if set(definitions) != expected_definition_keys:
            raise ValueError(
                "decision_definitions must exactly cover allowed_decisions"
            )
        for key, value in definitions.items():
            _require_text(key, "decision_definitions key")
            _require_text(value, f"decision_definitions[{key}]")
        object.__setattr__(
            self,
            "decision_definitions",
            _freeze_mapping(definitions, "decision_definitions"),
        )
        _require_instance(
            self.consensus_rule,
            LabelConsensusRule,
            "consensus_rule",
        )
        _require_positive_int(
            self.minimum_independent_curators,
            "minimum_independent_curators",
        )
        if self.minimum_independent_curators < 2:
            raise ValueError("held-out labeling requires at least two curators")
        if (
            self.consensus_rule is LabelConsensusRule.STRICT_MAJORITY
            and self.minimum_independent_curators < 3
        ):
            raise ValueError("strict-majority labeling requires three curators")
        _require_positive_int(self.outcome_window_days, "outcome_window_days")
        _require_sha256(self.label_guidance_sha256, "label_guidance_sha256")
        _require_sha256(self.exclusion_rules_sha256, "exclusion_rules_sha256")
        for field_name in (
            "policy_blinding_required",
            "conflict_free_required",
            "adjudicator_independence_required",
        ):
            value = getattr(self, field_name)
            _require_bool(value, field_name)
            if not value:
                raise ValueError(f"{field_name} must be true")


@dataclass(frozen=True, slots=True)
class HeldoutMetricPolicy(SerializableRecord):
    confidence_level: float
    stage_requirements: tuple[StageEvaluationRequirement, ...]
    interval_method: IntervalMethod = IntervalMethod.WILSON_SCORE
    missing_prediction_rule: MissingPredictionRule = (
        MissingPredictionRule.COUNT_AS_INCORRECT
    )
    action_coverage_rule: ActionCoverageRule = (
        ActionCoverageRule.NON_MISSING_NON_DEFER
    )

    def __post_init__(self) -> None:
        _require_probability(self.confidence_level, "confidence_level")
        if not 0.5 < float(self.confidence_level) < 1.0:
            raise ValueError("confidence_level must be between 0.5 and 1")
        requirements = tuple(self.stage_requirements)
        object.__setattr__(self, "stage_requirements", requirements)
        if not requirements:
            raise ValueError("stage_requirements must not be empty")
        for requirement in requirements:
            _require_instance(
                requirement,
                StageEvaluationRequirement,
                "stage_requirements item",
            )
        stages = tuple(item.stage for item in requirements)
        if len(stages) != len(set(stages)):
            raise ValueError("stage_requirements stages must be unique")
        if stages != tuple(sorted(stages, key=_STAGE_ORDER.__getitem__)):
            raise ValueError("stage_requirements must follow canonical stage order")
        _require_instance(
            self.interval_method,
            IntervalMethod,
            "interval_method",
        )
        _require_instance(
            self.missing_prediction_rule,
            MissingPredictionRule,
            "missing_prediction_rule",
        )
        _require_instance(
            self.action_coverage_rule,
            ActionCoverageRule,
            "action_coverage_rule",
        )


@dataclass(frozen=True, slots=True)
class HeldoutEvaluationProtocol(SerializableRecord):
    protocol_id: str
    version: str
    registered_on: date
    board_id: str
    board_version: str
    label_policy: HeldoutLabelPolicy
    metric_policy: HeldoutMetricPolicy
    cohort_specification_sha256: str
    curator_roster_commitment: str
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for field_name in (
            "protocol_id",
            "version",
            "board_id",
            "board_version",
        ):
            _require_text(getattr(self, field_name), field_name)
        _require_date(self.registered_on, "registered_on")
        _require_instance(
            self.label_policy,
            HeldoutLabelPolicy,
            "label_policy",
        )
        _require_instance(
            self.metric_policy,
            HeldoutMetricPolicy,
            "metric_policy",
        )
        _require_sha256(
            self.cohort_specification_sha256,
            "cohort_specification_sha256",
        )
        _require_sha256(
            self.curator_roster_commitment,
            "curator_roster_commitment",
        )
        metadata = _freeze_mapping(self.metadata, "metadata")
        if _contains_evaluator_key(metadata):
            raise ValueError(
                "held-out protocol metadata cannot contain evaluator labels"
            )
        object.__setattr__(self, "metadata", metadata)

    @property
    def fingerprint(self) -> str:
        return _sha256(self)


@dataclass(frozen=True, slots=True)
class CuratorDeclaration(SerializableRecord):
    curator_id: str
    role: CuratorRole
    affiliation_commitment: str
    independence_attestation_sha256: str
    declared_on: date
    policy_blinded: bool = True
    conflict_free: bool = True

    def __post_init__(self) -> None:
        _require_opaque_curator_id(self.curator_id, "curator_id")
        _require_instance(self.role, CuratorRole, "role")
        _require_sha256(
            self.affiliation_commitment,
            "affiliation_commitment",
        )
        _require_sha256(
            self.independence_attestation_sha256,
            "independence_attestation_sha256",
        )
        _require_date(self.declared_on, "declared_on")
        for field_name in ("policy_blinded", "conflict_free"):
            value = getattr(self, field_name)
            _require_bool(value, field_name)
            if not value:
                raise ValueError(f"{field_name} must be true")


def curator_roster_commitment(
    declarations: Sequence[CuratorDeclaration],
) -> str:
    """Commit to an opaque, predeclared curator roster."""

    if isinstance(declarations, (str, bytes)):
        raise TypeError("declarations must be a sequence")
    resolved = tuple(declarations)
    if not resolved:
        raise ValueError("curator roster must not be empty")
    for declaration in resolved:
        _require_instance(
            declaration,
            CuratorDeclaration,
            "declarations item",
        )
    curator_ids = tuple(item.curator_id for item in resolved)
    if len(curator_ids) != len(set(curator_ids)):
        raise ValueError("curator roster ids must be unique")
    if curator_ids != tuple(sorted(curator_ids)):
        raise ValueError("curator roster must be sorted by curator id")
    return _sha256(resolved)


@dataclass(frozen=True, slots=True)
class HeldoutLabelVote(SerializableRecord):
    curator_id: str
    decision: Decision
    labeled_on: date
    evidence_snapshot_sha256: str
    rationale_sha256: str

    def __post_init__(self) -> None:
        _require_opaque_curator_id(self.curator_id, "curator_id")
        _require_instance(self.decision, Decision, "decision")
        _require_date(self.labeled_on, "labeled_on")
        _require_sha256(
            self.evidence_snapshot_sha256,
            "evidence_snapshot_sha256",
        )
        _require_sha256(self.rationale_sha256, "rationale_sha256")


@dataclass(frozen=True, slots=True)
class EpisodeCurationRecord(SerializableRecord):
    episode_id: str
    votes: tuple[HeldoutLabelVote, ...]
    final_decision: Decision
    adjudicator_id: str | None = None
    adjudicated_on: date | None = None
    adjudication_rationale_sha256: str | None = None

    def __post_init__(self) -> None:
        _require_text(self.episode_id, "episode_id")
        if _EPISODE_ID_PATTERN.fullmatch(self.episode_id) is None:
            raise ValueError("episode_id must be an opaque sealed identifier")
        votes = tuple(self.votes)
        object.__setattr__(self, "votes", votes)
        if not votes:
            raise ValueError("episode curation requires votes")
        for vote in votes:
            _require_instance(vote, HeldoutLabelVote, "votes item")
        curator_ids = tuple(item.curator_id for item in votes)
        if len(curator_ids) != len(set(curator_ids)):
            raise ValueError("episode curator ids must be unique")
        if curator_ids != tuple(sorted(curator_ids)):
            raise ValueError("episode votes must be sorted by curator id")
        _require_instance(self.final_decision, Decision, "final_decision")
        adjudication_fields = (
            self.adjudicator_id,
            self.adjudicated_on,
            self.adjudication_rationale_sha256,
        )
        if all(item is None for item in adjudication_fields):
            return
        if any(item is None for item in adjudication_fields):
            raise ValueError("adjudication fields must be supplied together")
        assert self.adjudicator_id is not None
        assert self.adjudicated_on is not None
        assert self.adjudication_rationale_sha256 is not None
        _require_opaque_curator_id(self.adjudicator_id, "adjudicator_id")
        if self.adjudicator_id in curator_ids:
            raise ValueError("adjudicator cannot vote on the same episode")
        _require_date(self.adjudicated_on, "adjudicated_on")
        _require_sha256(
            self.adjudication_rationale_sha256,
            "adjudication_rationale_sha256",
        )


@dataclass(frozen=True, slots=True)
class HeldoutCurationManifest(SerializableRecord):
    manifest_id: str
    version: str
    protocol_id: str
    protocol_fingerprint: str
    board_id: str
    board_fingerprint: str
    vault_fingerprint: str
    created_on: date
    curator_declarations: tuple[CuratorDeclaration, ...]
    episode_records: tuple[EpisodeCurationRecord, ...]

    def __post_init__(self) -> None:
        for field_name in (
            "manifest_id",
            "version",
            "protocol_id",
            "board_id",
        ):
            _require_text(getattr(self, field_name), field_name)
        for field_name in (
            "protocol_fingerprint",
            "board_fingerprint",
            "vault_fingerprint",
        ):
            _require_sha256(getattr(self, field_name), field_name)
        _require_date(self.created_on, "created_on")
        declarations = tuple(self.curator_declarations)
        records = tuple(self.episode_records)
        object.__setattr__(self, "curator_declarations", declarations)
        object.__setattr__(self, "episode_records", records)
        curator_roster_commitment(declarations)
        if not records:
            raise ValueError("curation manifest requires episode records")
        for record in records:
            _require_instance(
                record,
                EpisodeCurationRecord,
                "episode_records item",
            )
        episode_ids = tuple(item.episode_id for item in records)
        if len(episode_ids) != len(set(episode_ids)):
            raise ValueError("curation episode ids must be unique")
        if episode_ids != tuple(sorted(episode_ids)):
            raise ValueError("curation records must be sorted by episode id")

    @property
    def fingerprint(self) -> str:
        return _sha256(self)


def validate_heldout_protocol_board(
    protocol: HeldoutEvaluationProtocol,
    board: SealedEvaluationBoard,
) -> Mapping[Stage, int]:
    """Validate preregistration, board binding, and stage sample minima."""

    _require_instance(
        protocol,
        HeldoutEvaluationProtocol,
        "protocol",
    )
    _require_instance(board, SealedEvaluationBoard, "board")
    if board.split is not EvaluationBoardSplit.SEALED_EXTERNAL:
        raise ValueError("held-out boards must use the sealed_external split")
    if board.board_id != protocol.board_id or board.version != protocol.board_version:
        raise ValueError("held-out board identity does not match the protocol")
    if board.created_on < protocol.registered_on:
        raise ValueError("held-out board cannot predate protocol registration")
    if board.metadata.get(_HELDOUT_PROTOCOL_ID_KEY) != protocol.protocol_id:
        raise ValueError("held-out board is missing its protocol id binding")
    if (
        board.metadata.get(_HELDOUT_PROTOCOL_FINGERPRINT_KEY)
        != protocol.fingerprint
    ):
        raise ValueError(
            "held-out board is missing its protocol fingerprint binding"
        )
    observations = {item.episode_id: item for item in board.observations}
    counts: Counter[Stage] = Counter()
    for pair in board.pairs:
        pair_observations = tuple(
            observations[episode_id] for episode_id in pair.episode_ids
        )
        match_keys = {item.match_key for item in pair_observations}
        if len(match_keys) != 1:
            raise ValueError("held-out pairs must share one exact match key")
        counts[pair_observations[0].match_key.stage] += 1
    requirements = {
        item.stage: item for item in protocol.metric_policy.stage_requirements
    }
    if set(counts) != set(requirements):
        raise ValueError(
            "held-out board stages must exactly match preregistered stages"
        )
    for stage, requirement in requirements.items():
        if counts[stage] < requirement.minimum_pairs:
            raise ValueError(
                f"held-out board does not meet the {stage.value} pair minimum"
            )
    return {stage: counts[stage] for stage in requirements}


def seal_heldout_evaluation_board(
    *,
    protocol: HeldoutEvaluationProtocol,
    created_on: date,
    pairs: Sequence[MatchedEpisodePair],
    sealing_secret: str,
    visible_packets_by_episode_id: Mapping[str, Mapping[str, Any]],
    packet_available_at_by_episode_id: Mapping[str, date],
    metadata: Mapping[str, Any] | None = None,
) -> tuple[SealedEvaluationBoard, SealedEvaluationVault]:
    """Seal a board and bind it to a preregistered held-out protocol."""

    _require_instance(
        protocol,
        HeldoutEvaluationProtocol,
        "protocol",
    )
    resolved_metadata = dict(metadata or {})
    reserved = {
        _HELDOUT_PROTOCOL_ID_KEY,
        _HELDOUT_PROTOCOL_FINGERPRINT_KEY,
    }
    if reserved.intersection(resolved_metadata):
        raise ValueError("held-out protocol metadata keys are reserved")
    resolved_metadata.update(
        {
            _HELDOUT_PROTOCOL_ID_KEY: protocol.protocol_id,
            _HELDOUT_PROTOCOL_FINGERPRINT_KEY: protocol.fingerprint,
        }
    )
    board, vault = seal_matched_evaluation_board(
        board_id=protocol.board_id,
        version=protocol.board_version,
        split=EvaluationBoardSplit.SEALED_EXTERNAL,
        created_on=created_on,
        pairs=pairs,
        sealing_secret=sealing_secret,
        visible_packets_by_episode_id=visible_packets_by_episode_id,
        packet_available_at_by_episode_id=packet_available_at_by_episode_id,
        metadata=resolved_metadata,
    )
    validate_heldout_protocol_board(protocol, board)
    return board, vault


def validate_heldout_curation(
    protocol: HeldoutEvaluationProtocol,
    board: SealedEvaluationBoard,
    vault: SealedEvaluationVault,
    manifest: HeldoutCurationManifest,
) -> Mapping[str, EpisodeCurationRecord]:
    """Validate curator independence, consensus, chronology, and gold labels."""

    validate_heldout_protocol_board(protocol, board)
    labels = validate_evaluation_vault(board, vault)
    _require_instance(
        manifest,
        HeldoutCurationManifest,
        "manifest",
    )
    if (
        manifest.protocol_id != protocol.protocol_id
        or manifest.protocol_fingerprint != protocol.fingerprint
    ):
        raise ValueError("curation manifest is bound to another protocol")
    if (
        manifest.board_id != board.board_id
        or manifest.board_fingerprint != board.fingerprint
        or manifest.vault_fingerprint != vault.fingerprint
    ):
        raise ValueError("curation manifest is bound to another board or vault")
    if manifest.created_on < board.created_on:
        raise ValueError("curation manifest cannot predate the held-out board")
    declarations = {
        item.curator_id: item for item in manifest.curator_declarations
    }
    if (
        curator_roster_commitment(manifest.curator_declarations)
        != protocol.curator_roster_commitment
    ):
        raise ValueError("curator roster does not open the protocol commitment")
    if any(
        item.declared_on > protocol.registered_on
        for item in manifest.curator_declarations
    ):
        raise ValueError("curator declarations must predate registration")
    curator_count = sum(
        item.role is CuratorRole.CURATOR
        for item in manifest.curator_declarations
    )
    if curator_count < protocol.label_policy.minimum_independent_curators:
        raise ValueError("curator roster is smaller than the label policy")
    if (
        protocol.label_policy.consensus_rule
        is LabelConsensusRule.ADJUDICATED
        and not any(
            item.role is CuratorRole.ADJUDICATOR
            for item in manifest.curator_declarations
        )
    ):
        raise ValueError("adjudicated policy requires a declared adjudicator")
    records = {item.episode_id: item for item in manifest.episode_records}
    if set(records) != set(labels):
        raise ValueError(
            "curation manifest must cover every board observation exactly"
        )
    observations = {item.episode_id: item for item in board.observations}
    allowed_decisions = set(protocol.label_policy.allowed_decisions)
    for episode_id, record in records.items():
        observation = observations[episode_id]
        label = labels[episode_id]
        if record.final_decision not in allowed_decisions:
            raise ValueError("final decision is outside the label policy")
        if record.final_decision is not label.gold_decision:
            raise ValueError("curation decision does not match the label vault")
        if (
            len(record.votes)
            < protocol.label_policy.minimum_independent_curators
        ):
            raise ValueError("episode has too few independent curator votes")
        earliest_label_date = observation.decision_cutoff + timedelta(
            days=protocol.label_policy.outcome_window_days
        )
        affiliations: list[str] = []
        vote_counts: Counter[Decision] = Counter()
        for vote in record.votes:
            declaration = declarations.get(vote.curator_id)
            if declaration is None:
                raise ValueError("episode vote uses an undeclared curator")
            if declaration.role is not CuratorRole.CURATOR:
                raise ValueError("adjudicators cannot submit curator votes")
            if vote.decision not in allowed_decisions:
                raise ValueError("curator vote is outside the label policy")
            if vote.labeled_on < earliest_label_date:
                raise ValueError("curator vote predates the outcome window")
            if vote.labeled_on > manifest.created_on:
                raise ValueError("curator vote postdates the curation manifest")
            affiliations.append(declaration.affiliation_commitment)
            vote_counts[vote.decision] += 1
        if len(affiliations) != len(set(affiliations)):
            raise ValueError(
                "episode votes must come from independent affiliations"
            )
        rule = protocol.label_policy.consensus_rule
        disagreement = len(vote_counts) > 1
        if rule is LabelConsensusRule.UNANIMOUS:
            if disagreement or record.final_decision not in vote_counts:
                raise ValueError("unanimous policy requires unanimous final label")
            if record.adjudicator_id is not None:
                raise ValueError("unanimous labels cannot use adjudication")
        elif rule is LabelConsensusRule.STRICT_MAJORITY:
            if vote_counts[record.final_decision] <= len(record.votes) / 2:
                raise ValueError(
                    "strict-majority policy requires a majority final label"
                )
            if record.adjudicator_id is not None:
                raise ValueError("strict-majority labels cannot use adjudication")
        elif not disagreement:
            if record.final_decision not in vote_counts:
                raise ValueError("unanimous votes must determine the final label")
            if record.adjudicator_id is not None:
                raise ValueError(
                    "adjudication is not allowed without curator disagreement"
                )
        else:
            assert rule is LabelConsensusRule.ADJUDICATED
            if record.adjudicator_id is None:
                raise ValueError("disagreement requires independent adjudication")
            declaration = declarations.get(record.adjudicator_id)
            if declaration is None:
                raise ValueError("episode uses an undeclared adjudicator")
            if declaration.role is not CuratorRole.ADJUDICATOR:
                raise ValueError("episode adjudicator lacks adjudicator role")
            if declaration.affiliation_commitment in affiliations:
                raise ValueError(
                    "adjudicator affiliation must be independent of voters"
                )
            assert record.adjudicated_on is not None
            if record.adjudicated_on < max(
                vote.labeled_on for vote in record.votes
            ):
                raise ValueError("adjudication cannot predate curator votes")
            if record.adjudicated_on > manifest.created_on:
                raise ValueError("adjudication postdates the curation manifest")
    return records


def _wilson_interval(
    event_count: int,
    total: int,
    confidence_level: float,
) -> tuple[float, float]:
    estimate = event_count / total
    z = NormalDist().inv_cdf(0.5 + confidence_level / 2)
    z_squared = z * z
    denominator = 1 + z_squared / total
    center = (estimate + z_squared / (2 * total)) / denominator
    margin = (
        z
        * math.sqrt(
            estimate * (1 - estimate) / total
            + z_squared / (4 * total * total)
        )
        / denominator
    )
    return (
        round(max(0.0, center - margin), 12),
        round(min(1.0, center + margin), 12),
    )


@dataclass(frozen=True, slots=True)
class BinomialEstimate(SerializableRecord):
    event_count: int
    total: int
    estimate: float | None
    lower: float | None
    upper: float | None
    confidence_level: float
    method: IntervalMethod = IntervalMethod.WILSON_SCORE

    def __post_init__(self) -> None:
        if (
            not isinstance(self.event_count, int)
            or isinstance(self.event_count, bool)
            or self.event_count < 0
        ):
            raise ValueError("event_count must be a non-negative integer")
        if (
            not isinstance(self.total, int)
            or isinstance(self.total, bool)
            or self.total < 0
        ):
            raise ValueError("total must be a non-negative integer")
        if self.event_count > self.total:
            raise ValueError("event_count cannot exceed total")
        _require_probability(self.confidence_level, "confidence_level")
        if not 0.5 < float(self.confidence_level) < 1.0:
            raise ValueError("confidence_level must be between 0.5 and 1")
        _require_instance(self.method, IntervalMethod, "method")
        values = (self.estimate, self.lower, self.upper)
        if self.total == 0:
            if any(value is not None for value in values):
                raise ValueError("zero-denominator estimates must be null")
            return
        if any(value is None for value in values):
            raise ValueError("non-empty estimates require estimate and bounds")
        assert self.estimate is not None
        assert self.lower is not None
        assert self.upper is not None
        for value, field_name in zip(
            values,
            ("estimate", "lower", "upper"),
            strict=True,
        ):
            assert value is not None
            _require_probability(value, field_name)
        expected_estimate = self.event_count / self.total
        expected_lower, expected_upper = _wilson_interval(
            self.event_count,
            self.total,
            self.confidence_level,
        )
        for actual, expected, field_name in (
            (self.estimate, expected_estimate, "estimate"),
            (self.lower, expected_lower, "lower"),
            (self.upper, expected_upper, "upper"),
        ):
            if not math.isclose(actual, expected, rel_tol=0.0, abs_tol=1e-12):
                raise ValueError(f"{field_name} does not match Wilson scoring")
        if not self.lower <= self.estimate <= self.upper:
            raise ValueError("binomial interval must contain its estimate")


def _binomial_estimate(
    event_count: int,
    total: int,
    policy: HeldoutMetricPolicy,
) -> BinomialEstimate:
    if total == 0:
        estimate = lower = upper = None
    else:
        estimate = event_count / total
        lower, upper = _wilson_interval(
            event_count,
            total,
            policy.confidence_level,
        )
    return BinomialEstimate(
        event_count=event_count,
        total=total,
        estimate=estimate,
        lower=lower,
        upper=upper,
        confidence_level=policy.confidence_level,
        method=policy.interval_method,
    )


@dataclass(frozen=True, slots=True)
class StageStratumMetrics(SerializableRecord):
    stage: Stage | None
    pair_count: int
    episode_count: int
    minimum_pairs: int
    minimum_action_covered_episodes: int
    board_requirement_met: bool
    action_requirement_met: bool
    exact_accuracy: BinomialEstimate
    success_arm_accuracy: BinomialEstimate
    failure_arm_accuracy: BinomialEstimate
    both_correct_rate: BinomialEstimate
    action_coverage: BinomialEstimate
    selective_risk: BinomialEstimate
    defer_rate: BinomialEstimate
    unsafe_advance_rate: BinomialEstimate

    def __post_init__(self) -> None:
        if self.stage is not None:
            _require_instance(self.stage, Stage, "stage")
        _require_positive_int(self.pair_count, "pair_count")
        _require_positive_int(self.episode_count, "episode_count")
        if self.episode_count != self.pair_count * 2:
            raise ValueError("episode_count must equal twice pair_count")
        _require_positive_int(self.minimum_pairs, "minimum_pairs")
        _require_positive_int(
            self.minimum_action_covered_episodes,
            "minimum_action_covered_episodes",
        )
        _require_bool(self.board_requirement_met, "board_requirement_met")
        _require_bool(self.action_requirement_met, "action_requirement_met")
        estimates = (
            self.exact_accuracy,
            self.success_arm_accuracy,
            self.failure_arm_accuracy,
            self.both_correct_rate,
            self.action_coverage,
            self.selective_risk,
            self.defer_rate,
            self.unsafe_advance_rate,
        )
        for estimate in estimates:
            _require_instance(estimate, BinomialEstimate, "metric estimate")
        if len({item.confidence_level for item in estimates}) != 1:
            raise ValueError("metric confidence levels must be consistent")
        if len({item.method for item in estimates}) != 1:
            raise ValueError("metric interval methods must be consistent")
        expected_totals = (
            (self.exact_accuracy, self.episode_count, "exact_accuracy"),
            (self.success_arm_accuracy, self.pair_count, "success_arm_accuracy"),
            (self.failure_arm_accuracy, self.pair_count, "failure_arm_accuracy"),
            (self.both_correct_rate, self.pair_count, "both_correct_rate"),
            (self.action_coverage, self.episode_count, "action_coverage"),
            (
                self.selective_risk,
                self.action_coverage.event_count,
                "selective_risk",
            ),
            (self.defer_rate, self.episode_count, "defer_rate"),
        )
        for estimate, expected_total, field_name in expected_totals:
            if estimate.total != expected_total:
                raise ValueError(f"{field_name} denominator is inconsistent")
        if self.unsafe_advance_rate.total > self.episode_count:
            raise ValueError("unsafe advance denominator exceeds episode count")
        if (
            self.exact_accuracy.event_count
            != self.success_arm_accuracy.event_count
            + self.failure_arm_accuracy.event_count
        ):
            raise ValueError("arm accuracy counts do not sum to exact accuracy")
        minimum_both_correct = max(
            0,
            self.exact_accuracy.event_count - self.pair_count,
        )
        maximum_both_correct = min(
            self.success_arm_accuracy.event_count,
            self.failure_arm_accuracy.event_count,
        )
        if not (
            minimum_both_correct
            <= self.both_correct_rate.event_count
            <= maximum_both_correct
        ):
            raise ValueError("pair correctness counts are not jointly feasible")
        if (
            self.action_coverage.event_count + self.defer_rate.event_count
            > self.episode_count
        ):
            raise ValueError("action coverage and defer counts overlap")
        if (
            self.selective_risk.event_count
            > self.episode_count - self.exact_accuracy.event_count
        ):
            raise ValueError("selective errors exceed all prediction errors")
        if (
            self.unsafe_advance_rate.event_count
            > self.selective_risk.event_count
        ):
            raise ValueError("unsafe advances must be action-covered errors")
        if (
            self.board_requirement_met
            != (self.pair_count >= self.minimum_pairs)
        ):
            raise ValueError("board_requirement_met is inconsistent")
        if (
            self.action_requirement_met
            != (
                self.action_coverage.event_count
                >= self.minimum_action_covered_episodes
            )
        ):
            raise ValueError("action_requirement_met is inconsistent")


@dataclass(frozen=True, slots=True)
class StageStratifiedPolicySummary(SerializableRecord):
    submission_id: str
    submission_fingerprint: str
    policy_id: str
    policy_version: str
    overall: StageStratumMetrics
    by_stage: tuple[StageStratumMetrics, ...]
    all_stage_requirements_met: bool
    all_action_requirements_met: bool

    def __post_init__(self) -> None:
        for field_name in ("submission_id", "policy_id", "policy_version"):
            _require_text(getattr(self, field_name), field_name)
        _require_sha256(
            self.submission_fingerprint,
            "submission_fingerprint",
        )
        _require_instance(self.overall, StageStratumMetrics, "overall")
        if self.overall.stage is not None:
            raise ValueError("overall metrics cannot carry a stage")
        by_stage = tuple(self.by_stage)
        object.__setattr__(self, "by_stage", by_stage)
        if not by_stage:
            raise ValueError("by_stage metrics must not be empty")
        for metrics in by_stage:
            _require_instance(metrics, StageStratumMetrics, "by_stage item")
            if metrics.stage is None:
                raise ValueError("stage strata require a stage")
        stages = tuple(item.stage for item in by_stage)
        if len(stages) != len(set(stages)):
            raise ValueError("stage strata must be unique")
        if stages != tuple(
            sorted(stages, key=lambda item: _STAGE_ORDER[item])
        ):
            raise ValueError("stage strata must follow canonical stage order")
        _require_bool(
            self.all_stage_requirements_met,
            "all_stage_requirements_met",
        )
        _require_bool(
            self.all_action_requirements_met,
            "all_action_requirements_met",
        )
        if self.all_stage_requirements_met != all(
            item.board_requirement_met for item in by_stage
        ):
            raise ValueError("all_stage_requirements_met is inconsistent")
        if self.all_action_requirements_met != all(
            item.action_requirement_met for item in by_stage
        ):
            raise ValueError("all_action_requirements_met is inconsistent")
        if self.overall.pair_count != sum(item.pair_count for item in by_stage):
            raise ValueError("stage pair counts do not sum to overall")
        if self.overall.episode_count != sum(
            item.episode_count for item in by_stage
        ):
            raise ValueError("stage episode counts do not sum to overall")
        if self.overall.minimum_pairs != sum(
            item.minimum_pairs for item in by_stage
        ):
            raise ValueError("stage pair minima do not sum to overall")
        if self.overall.minimum_action_covered_episodes != sum(
            item.minimum_action_covered_episodes for item in by_stage
        ):
            raise ValueError("stage action minima do not sum to overall")
        all_strata = (self.overall, *by_stage)
        if len(
            {
                item.exact_accuracy.confidence_level
                for item in all_strata
            }
        ) != 1:
            raise ValueError("stratum confidence levels must be consistent")
        if len({item.exact_accuracy.method for item in all_strata}) != 1:
            raise ValueError("stratum interval methods must be consistent")
        for field_name in (
            "exact_accuracy",
            "success_arm_accuracy",
            "failure_arm_accuracy",
            "both_correct_rate",
            "action_coverage",
            "selective_risk",
            "defer_rate",
            "unsafe_advance_rate",
        ):
            overall_estimate = getattr(self.overall, field_name)
            stage_estimates = tuple(
                getattr(item, field_name) for item in by_stage
            )
            if overall_estimate.event_count != sum(
                item.event_count for item in stage_estimates
            ) or overall_estimate.total != sum(
                item.total for item in stage_estimates
            ):
                raise ValueError(
                    f"stage {field_name} counts do not sum to overall"
                )


@dataclass(frozen=True, slots=True)
class StageStratifiedEvaluationReport(SerializableRecord):
    evaluation_id: str
    protocol_id: str
    protocol_fingerprint: str
    board_id: str
    board_fingerprint: str
    vault_fingerprint: str
    curation_manifest_fingerprint: str
    created_on: date
    summaries: tuple[StageStratifiedPolicySummary, ...]
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        for field_name in ("evaluation_id", "protocol_id", "board_id"):
            _require_text(getattr(self, field_name), field_name)
        for field_name in (
            "protocol_fingerprint",
            "board_fingerprint",
            "vault_fingerprint",
            "curation_manifest_fingerprint",
        ):
            _require_sha256(getattr(self, field_name), field_name)
        _require_date(self.created_on, "created_on")
        summaries = tuple(self.summaries)
        object.__setattr__(self, "summaries", summaries)
        if not summaries:
            raise ValueError("stage-stratified report requires summaries")
        for summary in summaries:
            _require_instance(
                summary,
                StageStratifiedPolicySummary,
                "summaries item",
            )
        identities = tuple(
            (item.policy_id, item.policy_version, item.submission_id)
            for item in summaries
        )
        if len(identities) != len(set(identities)):
            raise ValueError("stage-stratified policy identities must be unique")
        if identities != tuple(sorted(identities)):
            raise ValueError("policy summaries must use canonical identity order")
        policy_identities = tuple(
            (item.policy_id, item.policy_version) for item in summaries
        )
        if len(policy_identities) != len(set(policy_identities)):
            raise ValueError(
                "one submission is allowed per policy identity"
            )
        distributions = {
            tuple(
                (item.stage, item.pair_count, item.episode_count)
                for item in summary.by_stage
            )
            for summary in summaries
        }
        if len(distributions) != 1:
            raise ValueError("policy summaries must use one stage distribution")
        requirement_distributions = {
            tuple(
                (
                    item.stage,
                    item.minimum_pairs,
                    item.minimum_action_covered_episodes,
                )
                for item in summary.by_stage
            )
            for summary in summaries
        }
        if len(requirement_distributions) != 1:
            raise ValueError("policy summaries must use one requirement set")
        unsafe_denominators = {
            (
                summary.overall.unsafe_advance_rate.total,
                tuple(
                    (
                        item.stage,
                        item.unsafe_advance_rate.total,
                    )
                    for item in summary.by_stage
                ),
            )
            for summary in summaries
        }
        if len(unsafe_denominators) != 1:
            raise ValueError("policy summaries must use one gold distribution")
        if len(
            {
                summary.overall.exact_accuracy.confidence_level
                for summary in summaries
            }
        ) != 1:
            raise ValueError("policy confidence levels must be consistent")
        limitations = _freeze_text_tuple(self.limitations, "limitations")
        if not limitations:
            raise ValueError("stage-stratified report requires limitations")
        if not set(_REQUIRED_REPORT_LIMITATIONS).issubset(limitations):
            raise ValueError(
                "stage-stratified report is missing required limitations"
            )
        object.__setattr__(self, "limitations", limitations)

    @property
    def fingerprint(self) -> str:
        return _sha256(self)


def _stratum_metrics(
    *,
    stage: Stage | None,
    episodes: Sequence[EpisodePolicyEvaluation],
    pair_episode_ids: Sequence[tuple[str, str]],
    minimum_pairs: int,
    minimum_action_covered_episodes: int,
    policy: HeldoutMetricPolicy,
) -> StageStratumMetrics:
    resolved = tuple(episodes)
    pairs = tuple(pair_episode_ids)
    if not resolved or not pairs:
        raise ValueError("evaluation strata require episodes and pairs")
    results_by_id = {item.episode_id: item for item in resolved}
    success = tuple(item for item in resolved if item.arm is EpisodeArm.SUCCESS)
    failure = tuple(item for item in resolved if item.arm is EpisodeArm.FAILURE)
    both_correct = sum(
        all(results_by_id[episode_id].exact_match for episode_id in episode_ids)
        for episode_ids in pairs
    )
    action_covered = tuple(
        item
        for item in resolved
        if item.predicted_decision is not None
        and item.predicted_decision is not Decision.DEFER
    )
    unsafe_denominator = tuple(
        item for item in resolved if item.gold_decision is not Decision.ADVANCE
    )
    pair_count = len(pairs)
    episode_count = len(resolved)
    return StageStratumMetrics(
        stage=stage,
        pair_count=pair_count,
        episode_count=episode_count,
        minimum_pairs=minimum_pairs,
        minimum_action_covered_episodes=minimum_action_covered_episodes,
        board_requirement_met=pair_count >= minimum_pairs,
        action_requirement_met=(
            len(action_covered) >= minimum_action_covered_episodes
        ),
        exact_accuracy=_binomial_estimate(
            sum(item.exact_match for item in resolved),
            episode_count,
            policy,
        ),
        success_arm_accuracy=_binomial_estimate(
            sum(item.exact_match for item in success),
            len(success),
            policy,
        ),
        failure_arm_accuracy=_binomial_estimate(
            sum(item.exact_match for item in failure),
            len(failure),
            policy,
        ),
        both_correct_rate=_binomial_estimate(
            both_correct,
            pair_count,
            policy,
        ),
        action_coverage=_binomial_estimate(
            len(action_covered),
            episode_count,
            policy,
        ),
        selective_risk=_binomial_estimate(
            sum(not item.exact_match for item in action_covered),
            len(action_covered),
            policy,
        ),
        defer_rate=_binomial_estimate(
            sum(item.predicted_decision is Decision.DEFER for item in resolved),
            episode_count,
            policy,
        ),
        unsafe_advance_rate=_binomial_estimate(
            sum(item.unsafe_advance for item in unsafe_denominator),
            len(unsafe_denominator),
            policy,
        ),
    )


def evaluate_stage_stratified_submissions(
    *,
    evaluation_id: str,
    protocol: HeldoutEvaluationProtocol,
    board: SealedEvaluationBoard,
    vault: SealedEvaluationVault,
    curation_manifest: HeldoutCurationManifest,
    submissions: Sequence[PolicyEvaluationSubmission],
    created_on: date,
    limitations: Sequence[str] = (),
) -> StageStratifiedEvaluationReport:
    """Evaluate frozen submissions without post-hoc strata or winner selection."""

    validate_heldout_curation(protocol, board, vault, curation_manifest)
    _require_text(evaluation_id, "evaluation_id")
    _require_date(created_on, "created_on")
    if created_on < curation_manifest.created_on:
        raise ValueError("evaluation report cannot predate curation")
    resolved_submissions = tuple(submissions)
    if not resolved_submissions:
        raise ValueError("stage-stratified evaluation requires submissions")
    submission_ids = tuple(item.submission_id for item in resolved_submissions)
    if len(submission_ids) != len(set(submission_ids)):
        raise ValueError("stage-stratified submission ids must be unique")
    policy_identities = tuple(
        (item.policy_id, item.policy_version) for item in resolved_submissions
    )
    if len(policy_identities) != len(set(policy_identities)):
        raise ValueError(
            "stage-stratified policy identities must be unique"
        )
    if any(
        item.created_on > curation_manifest.created_on
        for item in resolved_submissions
    ):
        raise ValueError(
            "policy submissions must not postdate the curation freeze"
        )
    if any(item.created_on > created_on for item in resolved_submissions):
        raise ValueError("evaluation report cannot predate a submission")
    observations = {item.episode_id: item for item in board.observations}
    requirement_by_stage = {
        item.stage: item for item in protocol.metric_policy.stage_requirements
    }
    pairs_by_stage: dict[Stage, list[tuple[str, str]]] = {
        stage: [] for stage in requirement_by_stage
    }
    for pair in board.pairs:
        stage = observations[pair.episode_ids[0]].match_key.stage
        pairs_by_stage[stage].append(pair.episode_ids)
    summaries: list[StageStratifiedPolicySummary] = []
    for submission in resolved_submissions:
        result = evaluate_policy_submission(board, vault, submission)
        results_by_id = {item.episode_id: item for item in result.episodes}
        stage_metrics: list[StageStratumMetrics] = []
        for requirement in protocol.metric_policy.stage_requirements:
            pair_ids = tuple(pairs_by_stage[requirement.stage])
            episode_ids = {
                episode_id
                for pair_episode_ids in pair_ids
                for episode_id in pair_episode_ids
            }
            stage_metrics.append(
                _stratum_metrics(
                    stage=requirement.stage,
                    episodes=tuple(
                        results_by_id[episode_id]
                        for episode_id in sorted(episode_ids)
                    ),
                    pair_episode_ids=pair_ids,
                    minimum_pairs=requirement.minimum_pairs,
                    minimum_action_covered_episodes=(
                        requirement.minimum_action_covered_episodes
                    ),
                    policy=protocol.metric_policy,
                )
            )
        all_pair_ids = tuple(pair.episode_ids for pair in board.pairs)
        overall = _stratum_metrics(
            stage=None,
            episodes=result.episodes,
            pair_episode_ids=all_pair_ids,
            minimum_pairs=sum(
                item.minimum_pairs
                for item in protocol.metric_policy.stage_requirements
            ),
            minimum_action_covered_episodes=sum(
                item.minimum_action_covered_episodes
                for item in protocol.metric_policy.stage_requirements
            ),
            policy=protocol.metric_policy,
        )
        summaries.append(
            StageStratifiedPolicySummary(
                submission_id=submission.submission_id,
                submission_fingerprint=submission.fingerprint,
                policy_id=submission.policy_id,
                policy_version=submission.policy_version,
                overall=overall,
                by_stage=tuple(stage_metrics),
                all_stage_requirements_met=all(
                    item.board_requirement_met for item in stage_metrics
                ),
                all_action_requirements_met=all(
                    item.action_requirement_met for item in stage_metrics
                ),
            )
        )
    resolved_limitations = tuple(
        dict.fromkeys((*_REQUIRED_REPORT_LIMITATIONS, *tuple(limitations)))
    )
    return StageStratifiedEvaluationReport(
        evaluation_id=evaluation_id,
        protocol_id=protocol.protocol_id,
        protocol_fingerprint=protocol.fingerprint,
        board_id=board.board_id,
        board_fingerprint=board.fingerprint,
        vault_fingerprint=vault.fingerprint,
        curation_manifest_fingerprint=curation_manifest.fingerprint,
        created_on=created_on,
        summaries=tuple(
            sorted(
                summaries,
                key=lambda item: (
                    item.policy_id,
                    item.policy_version,
                    item.submission_id,
                ),
            )
        ),
        limitations=resolved_limitations,
    )


def heldout_evaluation_protocol_envelope(
    protocol: HeldoutEvaluationProtocol,
) -> dict[str, Any]:
    _require_instance(
        protocol,
        HeldoutEvaluationProtocol,
        "protocol",
    )
    return {
        "schema_version": HELDOUT_EVALUATION_PROTOCOL_SCHEMA_VERSION,
        "integrity_sha256": protocol.fingerprint,
        "protocol": protocol.to_dict(),
    }


def heldout_curation_manifest_envelope(
    manifest: HeldoutCurationManifest,
) -> dict[str, Any]:
    _require_instance(
        manifest,
        HeldoutCurationManifest,
        "manifest",
    )
    return {
        "schema_version": HELDOUT_CURATION_MANIFEST_SCHEMA_VERSION,
        "integrity_sha256": manifest.fingerprint,
        "manifest": manifest.to_dict(),
    }


def stage_stratified_evaluation_report_envelope(
    report: StageStratifiedEvaluationReport,
) -> dict[str, Any]:
    _require_instance(
        report,
        StageStratifiedEvaluationReport,
        "report",
    )
    return {
        "schema_version": STAGE_STRATIFIED_EVALUATION_REPORT_SCHEMA_VERSION,
        "integrity_sha256": report.fingerprint,
        "report": report.to_dict(),
    }


def _parse_stage_requirement(
    value: Any,
    path: str,
) -> StageEvaluationRequirement:
    data = _parse_record(
        value,
        path,
        {
            "stage",
            "minimum_pairs",
            "minimum_action_covered_episodes",
        },
    )
    return StageEvaluationRequirement(
        stage=_parse_enum(Stage, data["stage"], f"{path}.stage"),
        minimum_pairs=data["minimum_pairs"],
        minimum_action_covered_episodes=data[
            "minimum_action_covered_episodes"
        ],
    )


def _parse_label_policy(value: Any, path: str) -> HeldoutLabelPolicy:
    data = _parse_record(
        value,
        path,
        {
            "policy_id",
            "version",
            "allowed_decisions",
            "decision_definitions",
            "consensus_rule",
            "minimum_independent_curators",
            "outcome_window_days",
            "label_guidance_sha256",
            "exclusion_rules_sha256",
            "policy_blinding_required",
            "conflict_free_required",
            "adjudicator_independence_required",
        },
    )
    return HeldoutLabelPolicy(
        policy_id=data["policy_id"],
        version=data["version"],
        allowed_decisions=tuple(
            _parse_enum(Decision, item, f"{path}.allowed_decisions[{index}]")
            for index, item in enumerate(
                _parse_sequence(
                    data["allowed_decisions"],
                    f"{path}.allowed_decisions",
                )
            )
        ),
        decision_definitions=_parse_mapping(
            data["decision_definitions"],
            f"{path}.decision_definitions",
        ),
        consensus_rule=_parse_enum(
            LabelConsensusRule,
            data["consensus_rule"],
            f"{path}.consensus_rule",
        ),
        minimum_independent_curators=data["minimum_independent_curators"],
        outcome_window_days=data["outcome_window_days"],
        label_guidance_sha256=data["label_guidance_sha256"],
        exclusion_rules_sha256=data["exclusion_rules_sha256"],
        policy_blinding_required=data["policy_blinding_required"],
        conflict_free_required=data["conflict_free_required"],
        adjudicator_independence_required=data[
            "adjudicator_independence_required"
        ],
    )


def _parse_metric_policy(value: Any, path: str) -> HeldoutMetricPolicy:
    data = _parse_record(
        value,
        path,
        {
            "confidence_level",
            "stage_requirements",
            "interval_method",
            "missing_prediction_rule",
            "action_coverage_rule",
        },
    )
    return HeldoutMetricPolicy(
        confidence_level=data["confidence_level"],
        stage_requirements=tuple(
            _parse_stage_requirement(
                item,
                f"{path}.stage_requirements[{index}]",
            )
            for index, item in enumerate(
                _parse_sequence(
                    data["stage_requirements"],
                    f"{path}.stage_requirements",
                )
            )
        ),
        interval_method=_parse_enum(
            IntervalMethod,
            data["interval_method"],
            f"{path}.interval_method",
        ),
        missing_prediction_rule=_parse_enum(
            MissingPredictionRule,
            data["missing_prediction_rule"],
            f"{path}.missing_prediction_rule",
        ),
        action_coverage_rule=_parse_enum(
            ActionCoverageRule,
            data["action_coverage_rule"],
            f"{path}.action_coverage_rule",
        ),
    )


def heldout_evaluation_protocol_from_dict(
    value: Any,
) -> HeldoutEvaluationProtocol:
    raw, expected_hash = _parse_integrity_envelope(
        value,
        path="heldout_evaluation_protocol_envelope",
        schema_version=HELDOUT_EVALUATION_PROTOCOL_SCHEMA_VERSION,
        payload_key="protocol",
    )
    data = _parse_record(
        raw,
        "protocol",
        {
            "protocol_id",
            "version",
            "registered_on",
            "board_id",
            "board_version",
            "label_policy",
            "metric_policy",
            "cohort_specification_sha256",
            "curator_roster_commitment",
            "metadata",
        },
    )
    protocol = HeldoutEvaluationProtocol(
        protocol_id=data["protocol_id"],
        version=data["version"],
        registered_on=_parse_date(data["registered_on"], "protocol.registered_on"),
        board_id=data["board_id"],
        board_version=data["board_version"],
        label_policy=_parse_label_policy(
            data["label_policy"],
            "protocol.label_policy",
        ),
        metric_policy=_parse_metric_policy(
            data["metric_policy"],
            "protocol.metric_policy",
        ),
        cohort_specification_sha256=data["cohort_specification_sha256"],
        curator_roster_commitment=data["curator_roster_commitment"],
        metadata=_parse_mapping(data["metadata"], "protocol.metadata"),
    )
    if protocol.fingerprint != expected_hash:
        raise RecordParseError(
            "parsed held-out protocol changed canonical identity"
        )
    return protocol


def _parse_curator_declaration(
    value: Any,
    path: str,
) -> CuratorDeclaration:
    data = _parse_record(
        value,
        path,
        {
            "curator_id",
            "role",
            "affiliation_commitment",
            "independence_attestation_sha256",
            "declared_on",
            "policy_blinded",
            "conflict_free",
        },
    )
    return CuratorDeclaration(
        curator_id=data["curator_id"],
        role=_parse_enum(CuratorRole, data["role"], f"{path}.role"),
        affiliation_commitment=data["affiliation_commitment"],
        independence_attestation_sha256=data[
            "independence_attestation_sha256"
        ],
        declared_on=_parse_date(data["declared_on"], f"{path}.declared_on"),
        policy_blinded=data["policy_blinded"],
        conflict_free=data["conflict_free"],
    )


def _parse_label_vote(value: Any, path: str) -> HeldoutLabelVote:
    data = _parse_record(
        value,
        path,
        {
            "curator_id",
            "decision",
            "labeled_on",
            "evidence_snapshot_sha256",
            "rationale_sha256",
        },
    )
    return HeldoutLabelVote(
        curator_id=data["curator_id"],
        decision=_parse_enum(Decision, data["decision"], f"{path}.decision"),
        labeled_on=_parse_date(data["labeled_on"], f"{path}.labeled_on"),
        evidence_snapshot_sha256=data["evidence_snapshot_sha256"],
        rationale_sha256=data["rationale_sha256"],
    )


def _parse_episode_curation(
    value: Any,
    path: str,
) -> EpisodeCurationRecord:
    data = _parse_record(
        value,
        path,
        {
            "episode_id",
            "votes",
            "final_decision",
            "adjudicator_id",
            "adjudicated_on",
            "adjudication_rationale_sha256",
        },
    )
    adjudicated_on = data["adjudicated_on"]
    return EpisodeCurationRecord(
        episode_id=data["episode_id"],
        votes=tuple(
            _parse_label_vote(item, f"{path}.votes[{index}]")
            for index, item in enumerate(
                _parse_sequence(data["votes"], f"{path}.votes")
            )
        ),
        final_decision=_parse_enum(
            Decision,
            data["final_decision"],
            f"{path}.final_decision",
        ),
        adjudicator_id=data["adjudicator_id"],
        adjudicated_on=(
            None
            if adjudicated_on is None
            else _parse_date(adjudicated_on, f"{path}.adjudicated_on")
        ),
        adjudication_rationale_sha256=data[
            "adjudication_rationale_sha256"
        ],
    )


def heldout_curation_manifest_from_dict(
    value: Any,
) -> HeldoutCurationManifest:
    raw, expected_hash = _parse_integrity_envelope(
        value,
        path="heldout_curation_manifest_envelope",
        schema_version=HELDOUT_CURATION_MANIFEST_SCHEMA_VERSION,
        payload_key="manifest",
    )
    data = _parse_record(
        raw,
        "manifest",
        {
            "manifest_id",
            "version",
            "protocol_id",
            "protocol_fingerprint",
            "board_id",
            "board_fingerprint",
            "vault_fingerprint",
            "created_on",
            "curator_declarations",
            "episode_records",
        },
    )
    manifest = HeldoutCurationManifest(
        manifest_id=data["manifest_id"],
        version=data["version"],
        protocol_id=data["protocol_id"],
        protocol_fingerprint=data["protocol_fingerprint"],
        board_id=data["board_id"],
        board_fingerprint=data["board_fingerprint"],
        vault_fingerprint=data["vault_fingerprint"],
        created_on=_parse_date(data["created_on"], "manifest.created_on"),
        curator_declarations=tuple(
            _parse_curator_declaration(
                item,
                f"manifest.curator_declarations[{index}]",
            )
            for index, item in enumerate(
                _parse_sequence(
                    data["curator_declarations"],
                    "manifest.curator_declarations",
                )
            )
        ),
        episode_records=tuple(
            _parse_episode_curation(
                item,
                f"manifest.episode_records[{index}]",
            )
            for index, item in enumerate(
                _parse_sequence(
                    data["episode_records"],
                    "manifest.episode_records",
                )
            )
        ),
    )
    if manifest.fingerprint != expected_hash:
        raise RecordParseError(
            "parsed held-out curation manifest changed canonical identity"
        )
    return manifest


def _parse_binomial_estimate(value: Any, path: str) -> BinomialEstimate:
    data = _parse_record(
        value,
        path,
        {
            "event_count",
            "total",
            "estimate",
            "lower",
            "upper",
            "confidence_level",
            "method",
        },
    )
    return BinomialEstimate(
        event_count=data["event_count"],
        total=data["total"],
        estimate=data["estimate"],
        lower=data["lower"],
        upper=data["upper"],
        confidence_level=data["confidence_level"],
        method=_parse_enum(
            IntervalMethod,
            data["method"],
            f"{path}.method",
        ),
    )


def _parse_stratum(value: Any, path: str) -> StageStratumMetrics:
    data = _parse_record(
        value,
        path,
        {
            "stage",
            "pair_count",
            "episode_count",
            "minimum_pairs",
            "minimum_action_covered_episodes",
            "board_requirement_met",
            "action_requirement_met",
            "exact_accuracy",
            "success_arm_accuracy",
            "failure_arm_accuracy",
            "both_correct_rate",
            "action_coverage",
            "selective_risk",
            "defer_rate",
            "unsafe_advance_rate",
        },
    )
    raw_stage = data["stage"]
    return StageStratumMetrics(
        stage=(
            None
            if raw_stage is None
            else _parse_enum(Stage, raw_stage, f"{path}.stage")
        ),
        pair_count=data["pair_count"],
        episode_count=data["episode_count"],
        minimum_pairs=data["minimum_pairs"],
        minimum_action_covered_episodes=data[
            "minimum_action_covered_episodes"
        ],
        board_requirement_met=data["board_requirement_met"],
        action_requirement_met=data["action_requirement_met"],
        exact_accuracy=_parse_binomial_estimate(
            data["exact_accuracy"],
            f"{path}.exact_accuracy",
        ),
        success_arm_accuracy=_parse_binomial_estimate(
            data["success_arm_accuracy"],
            f"{path}.success_arm_accuracy",
        ),
        failure_arm_accuracy=_parse_binomial_estimate(
            data["failure_arm_accuracy"],
            f"{path}.failure_arm_accuracy",
        ),
        both_correct_rate=_parse_binomial_estimate(
            data["both_correct_rate"],
            f"{path}.both_correct_rate",
        ),
        action_coverage=_parse_binomial_estimate(
            data["action_coverage"],
            f"{path}.action_coverage",
        ),
        selective_risk=_parse_binomial_estimate(
            data["selective_risk"],
            f"{path}.selective_risk",
        ),
        defer_rate=_parse_binomial_estimate(
            data["defer_rate"],
            f"{path}.defer_rate",
        ),
        unsafe_advance_rate=_parse_binomial_estimate(
            data["unsafe_advance_rate"],
            f"{path}.unsafe_advance_rate",
        ),
    )


def _parse_stage_summary(
    value: Any,
    path: str,
) -> StageStratifiedPolicySummary:
    data = _parse_record(
        value,
        path,
        {
            "submission_id",
            "submission_fingerprint",
            "policy_id",
            "policy_version",
            "overall",
            "by_stage",
            "all_stage_requirements_met",
            "all_action_requirements_met",
        },
    )
    return StageStratifiedPolicySummary(
        submission_id=data["submission_id"],
        submission_fingerprint=data["submission_fingerprint"],
        policy_id=data["policy_id"],
        policy_version=data["policy_version"],
        overall=_parse_stratum(data["overall"], f"{path}.overall"),
        by_stage=tuple(
            _parse_stratum(item, f"{path}.by_stage[{index}]")
            for index, item in enumerate(
                _parse_sequence(data["by_stage"], f"{path}.by_stage")
            )
        ),
        all_stage_requirements_met=data["all_stage_requirements_met"],
        all_action_requirements_met=data["all_action_requirements_met"],
    )


def stage_stratified_evaluation_report_from_dict(
    value: Any,
) -> StageStratifiedEvaluationReport:
    raw, expected_hash = _parse_integrity_envelope(
        value,
        path="stage_stratified_evaluation_report_envelope",
        schema_version=STAGE_STRATIFIED_EVALUATION_REPORT_SCHEMA_VERSION,
        payload_key="report",
    )
    data = _parse_record(
        raw,
        "report",
        {
            "evaluation_id",
            "protocol_id",
            "protocol_fingerprint",
            "board_id",
            "board_fingerprint",
            "vault_fingerprint",
            "curation_manifest_fingerprint",
            "created_on",
            "summaries",
            "limitations",
        },
    )
    report = StageStratifiedEvaluationReport(
        evaluation_id=data["evaluation_id"],
        protocol_id=data["protocol_id"],
        protocol_fingerprint=data["protocol_fingerprint"],
        board_id=data["board_id"],
        board_fingerprint=data["board_fingerprint"],
        vault_fingerprint=data["vault_fingerprint"],
        curation_manifest_fingerprint=data[
            "curation_manifest_fingerprint"
        ],
        created_on=_parse_date(data["created_on"], "report.created_on"),
        summaries=tuple(
            _parse_stage_summary(item, f"report.summaries[{index}]")
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
            "parsed stage-stratified report changed canonical identity"
        )
    return report


def heldout_evaluation_protocol_from_json(
    payload: str,
) -> HeldoutEvaluationProtocol:
    return heldout_evaluation_protocol_from_dict(
        _parse_envelope_json(payload, "held-out evaluation protocol")
    )


def heldout_curation_manifest_from_json(
    payload: str,
) -> HeldoutCurationManifest:
    return heldout_curation_manifest_from_dict(
        _parse_envelope_json(payload, "held-out curation manifest")
    )


def stage_stratified_evaluation_report_from_json(
    payload: str,
) -> StageStratifiedEvaluationReport:
    return stage_stratified_evaluation_report_from_dict(
        _parse_envelope_json(payload, "stage-stratified evaluation report")
    )
