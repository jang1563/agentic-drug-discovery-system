"""Multi-endpoint benefit-risk portfolios with explicit provenance reuse."""

from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass, field, fields
from typing import Any

from .clinical_effects import effect_benefit_direction, validate_effect_scale_interval
from .clinical_synthesis import validate_benefit_risk_synthesis
from .models import (
    BenefitRiskSynthesisRecord,
    ProgramState,
    SerializableRecord,
    StudyBenefitRiskRecord,
    _freeze_mapping,
    _require_instance,
    _require_sha256,
    _require_text,
    to_primitive,
)


CLINICAL_BENEFIT_RISK_PORTFOLIO_SPEC_SCHEMA_VERSION = (
    "adds.clinical-benefit-risk-portfolio-spec.v1"
)
CLINICAL_BENEFIT_RISK_PORTFOLIO_REPORT_SCHEMA_VERSION = (
    "adds.clinical-benefit-risk-portfolio-report.v1"
)
CLINICAL_BENEFIT_RISK_PORTFOLIO_POLICY_ID = (
    "adds.provenance-preserving-multi-endpoint-benefit-risk.v1"
)

_REQUIRED_LIMITATIONS = (
    (
        "Endpoint domains remain separate descriptive syntheses; no cross-endpoint "
        "pooling or scalar benefit-risk score is computed."
    ),
    (
        "Repeated trial, endpoint, safety, and source references are counted as reuse "
        "and never treated as independent evidence."
    ),
    (
        "Distinct endpoint-family labels do not establish distinct endpoint records, "
        "clinical importance, ontology validity, or population comparability."
    ),
    (
        "Source hashes establish artifact identity, not source truth, causal validity, "
        "absence of bias, or scientific independence."
    ),
    (
        "The report does not infer clinical acceptability, treatment choice, utility, "
        "transportability, or regulatory sufficiency."
    ),
)


class ClinicalBenefitRiskPortfolioError(ValueError):
    """Raised when a multi-endpoint portfolio cannot be compiled safely."""


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


def _tuple(value: Any, field_name: str) -> tuple[Any, ...]:
    if isinstance(value, (str, bytes)):
        raise TypeError(f"{field_name} must be an array")
    try:
        return tuple(value)
    except TypeError as exc:
        raise TypeError(f"{field_name} must be an array") from exc


def _sorted_unique_text(value: Any, field_name: str) -> tuple[str, ...]:
    result = _tuple(value, field_name)
    for item in result:
        _require_text(item, field_name)
    if len(result) != len(set(result)):
        raise ValueError(f"{field_name} must contain unique values")
    if result != tuple(sorted(result)):
        raise ValueError(f"{field_name} must use canonical sorted order")
    return result


def _require_bool(value: Any, field_name: str) -> None:
    if not isinstance(value, bool):
        raise TypeError(f"{field_name} must be boolean")


def _require_non_negative_int(value: Any, field_name: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")


def _require_positive_int(value: Any, field_name: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ValueError(f"{field_name} must be a positive integer")


def _require_finite(value: Any, field_name: str) -> None:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise TypeError(f"{field_name} must be numeric")
    if not math.isfinite(float(value)):
        raise ValueError(f"{field_name} must be finite")


def _record(value: Any, path: str, fields: set[str]) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ClinicalBenefitRiskPortfolioError(f"{path} must be an object")
    keys = set(value)
    if keys != fields:
        raise ClinicalBenefitRiskPortfolioError(
            f"{path} must contain exactly {sorted(fields)}"
        )
    return dict(value)


def _field_names(record_type: type[Any]) -> set[str]:
    return {item.name for item in fields(record_type)}


def _reject_constant(value: str) -> None:
    raise ClinicalBenefitRiskPortfolioError(
        f"non-finite JSON constant is not allowed: {value}"
    )


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ClinicalBenefitRiskPortfolioError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _load_json(text: str, artifact_name: str) -> dict[str, Any]:
    try:
        value = json.loads(
            text,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except ClinicalBenefitRiskPortfolioError:
        raise
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ClinicalBenefitRiskPortfolioError(f"invalid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise ClinicalBenefitRiskPortfolioError(
            f"{artifact_name} must be a JSON object"
        )
    return value


@dataclass(frozen=True, slots=True)
class ClinicalBenefitRiskPortfolioSpec(SerializableRecord):
    """Exact committed syntheses selected for one endpoint portfolio."""

    portfolio_id: str
    candidate_id: str
    intervention_id: str
    disease_id: str
    synthesis_ids: tuple[str, ...]
    require_distinct_endpoint_records: bool = True
    require_full_state_replay: bool = True
    policy_id: str = CLINICAL_BENEFIT_RISK_PORTFOLIO_POLICY_ID
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for field_name in (
            "portfolio_id",
            "candidate_id",
            "intervention_id",
            "disease_id",
            "policy_id",
        ):
            _require_text(getattr(self, field_name), field_name)
        synthesis_ids = _sorted_unique_text(self.synthesis_ids, "synthesis_ids")
        object.__setattr__(self, "synthesis_ids", synthesis_ids)
        if len(synthesis_ids) < 2:
            raise ValueError("portfolio requires at least two synthesis records")
        _require_bool(
            self.require_distinct_endpoint_records,
            "require_distinct_endpoint_records",
        )
        _require_bool(self.require_full_state_replay, "require_full_state_replay")
        if not self.require_full_state_replay:
            raise ValueError("portfolio compilation requires full state replay")
        if self.policy_id != CLINICAL_BENEFIT_RISK_PORTFOLIO_POLICY_ID:
            raise ValueError("unsupported portfolio policy_id")
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata, "metadata"))

    @property
    def fingerprint(self) -> str:
        return _sha256(self)


@dataclass(frozen=True, slots=True)
class ClinicalBenefitRiskEndpointCell(SerializableRecord):
    """One endpoint result linked to a separately deduplicated safety unit."""

    study_record_id: str
    trial_id: str
    design_id: str
    endpoint_id: str
    endpoint_fingerprint_sha256: str
    safety_unit_id: str
    effect_estimate: float
    confidence_interval_percent: float
    confidence_interval_lower: float
    confidence_interval_upper: float
    measurement_unit: str
    endpoint_time_frame: str
    benefit_direction: str
    source_content_hashes: tuple[str, ...]

    def __post_init__(self) -> None:
        for field_name in (
            "study_record_id",
            "trial_id",
            "design_id",
            "endpoint_id",
            "measurement_unit",
            "endpoint_time_frame",
        ):
            _require_text(getattr(self, field_name), field_name)
        _require_sha256(
            self.endpoint_fingerprint_sha256,
            "endpoint_fingerprint_sha256",
        )
        _require_sha256(self.safety_unit_id, "safety_unit_id")
        for field_name in (
            "effect_estimate",
            "confidence_interval_percent",
            "confidence_interval_lower",
            "confidence_interval_upper",
        ):
            _require_finite(getattr(self, field_name), field_name)
        if not 0 < self.confidence_interval_percent <= 100:
            raise ValueError("confidence_interval_percent must be in (0, 100]")
        if not (
            self.confidence_interval_lower
            <= self.effect_estimate
            <= self.confidence_interval_upper
        ):
            raise ValueError("effect estimate must lie inside its confidence interval")
        if self.benefit_direction not in {
            "benefit",
            "harm",
            "null_or_uncertain",
        }:
            raise ValueError("benefit_direction is not recognized")
        object.__setattr__(
            self,
            "source_content_hashes",
            _sorted_unique_text(
                self.source_content_hashes,
                "source_content_hashes",
            ),
        )
        if not self.source_content_hashes:
            raise ValueError("source_content_hashes must not be empty")
        for index, digest in enumerate(self.source_content_hashes):
            _require_sha256(digest, f"source_content_hashes[{index}]")


@dataclass(frozen=True, slots=True)
class ClinicalBenefitRiskEndpointDomain(SerializableRecord):
    """One non-pooled endpoint-family synthesis inside the portfolio."""

    synthesis_id: str
    synthesis_sha256: str
    endpoint_mapping_id: str
    endpoint_family: str
    effect_measure: str
    favorable_direction: str
    safety_measure: str
    harmonization_policy_id: str
    cells: tuple[ClinicalBenefitRiskEndpointCell, ...]
    benefit_direction_consistent: bool
    safety_direction_consistent: bool
    source_disjoint_within_domain: bool
    pooling_performed: bool = False

    def __post_init__(self) -> None:
        for field_name in (
            "synthesis_id",
            "endpoint_mapping_id",
            "endpoint_family",
            "effect_measure",
            "favorable_direction",
            "safety_measure",
            "harmonization_policy_id",
        ):
            _require_text(getattr(self, field_name), field_name)
        _require_sha256(self.synthesis_sha256, "synthesis_sha256")
        cells = _tuple(self.cells, "cells")
        object.__setattr__(self, "cells", cells)
        if len(cells) < 2:
            raise ValueError("endpoint domain requires at least two trial cells")
        for cell in cells:
            _require_instance(cell, ClinicalBenefitRiskEndpointCell, "cells item")
        if cells != tuple(sorted(cells, key=lambda item: item.trial_id)):
            raise ValueError("endpoint cells must use canonical trial order")
        if len({item.trial_id for item in cells}) != len(cells):
            raise ValueError("endpoint domain trial ids must be unique")
        for cell in cells:
            validate_effect_scale_interval(
                cell.effect_estimate,
                cell.confidence_interval_lower,
                cell.confidence_interval_upper,
                self.effect_measure,
                cell.measurement_unit,
            )
            expected_direction = effect_benefit_direction(
                cell.confidence_interval_lower,
                cell.confidence_interval_upper,
                self.effect_measure,
                self.favorable_direction,
            )
            if cell.benefit_direction != expected_direction:
                raise ValueError("cell benefit direction does not match effect interval")
        _require_bool(
            self.benefit_direction_consistent,
            "benefit_direction_consistent",
        )
        expected_consistency = len({item.benefit_direction for item in cells}) == 1
        if self.benefit_direction_consistent != expected_consistency:
            raise ValueError("benefit direction consistency does not match cells")
        _require_bool(
            self.safety_direction_consistent,
            "safety_direction_consistent",
        )
        _require_bool(
            self.source_disjoint_within_domain,
            "source_disjoint_within_domain",
        )
        if not self.source_disjoint_within_domain:
            raise ValueError("each endpoint domain must remain source-disjoint")
        _require_bool(self.pooling_performed, "pooling_performed")
        if self.pooling_performed:
            raise ValueError("cross-trial pooling is not permitted")


@dataclass(frozen=True, slots=True)
class ClinicalBenefitRiskSafetyUnit(SerializableRecord):
    """One exact safety record, deduplicated across endpoint domains."""

    safety_unit_id: str
    trial_id: str
    design_id: str
    safety_id: str
    safety_fingerprint_sha256: str
    safety_time_frame: str
    candidate_serious_num_affected: int
    candidate_serious_num_at_risk: int
    comparator_serious_num_affected: int
    comparator_serious_num_at_risk: int
    candidate_serious_event_risk: float
    comparator_serious_event_risk: float
    serious_event_risk_difference: float
    safety_direction: str
    source_content_hashes: tuple[str, ...]
    referenced_by_synthesis_ids: tuple[str, ...]
    referenced_by_endpoint_families: tuple[str, ...]
    reference_count: int

    def __post_init__(self) -> None:
        _require_sha256(self.safety_unit_id, "safety_unit_id")
        _require_sha256(
            self.safety_fingerprint_sha256,
            "safety_fingerprint_sha256",
        )
        for field_name in (
            "trial_id",
            "design_id",
            "safety_id",
            "safety_time_frame",
        ):
            _require_text(getattr(self, field_name), field_name)
        expected_safety_unit_id = _sha256(
            {
                "trial_id": self.trial_id,
                "design_id": self.design_id,
                "safety_id": self.safety_id,
                "safety_fingerprint_sha256": self.safety_fingerprint_sha256,
            }
        )
        if self.safety_unit_id != expected_safety_unit_id:
            raise ValueError("safety_unit_id does not match its bound identity")
        for field_name in (
            "candidate_serious_num_affected",
            "candidate_serious_num_at_risk",
            "comparator_serious_num_affected",
            "comparator_serious_num_at_risk",
        ):
            _require_non_negative_int(getattr(self, field_name), field_name)
        if self.candidate_serious_num_at_risk < 1:
            raise ValueError("candidate serious-event denominator must be positive")
        if self.comparator_serious_num_at_risk < 1:
            raise ValueError("comparator serious-event denominator must be positive")
        if self.candidate_serious_num_affected > self.candidate_serious_num_at_risk:
            raise ValueError("candidate serious-event numerator exceeds denominator")
        if self.comparator_serious_num_affected > self.comparator_serious_num_at_risk:
            raise ValueError("comparator serious-event numerator exceeds denominator")
        expected_candidate = (
            self.candidate_serious_num_affected / self.candidate_serious_num_at_risk
        )
        expected_comparator = (
            self.comparator_serious_num_affected / self.comparator_serious_num_at_risk
        )
        expected_difference = expected_candidate - expected_comparator
        for field_name, observed, expected in (
            (
                "candidate_serious_event_risk",
                self.candidate_serious_event_risk,
                expected_candidate,
            ),
            (
                "comparator_serious_event_risk",
                self.comparator_serious_event_risk,
                expected_comparator,
            ),
            (
                "serious_event_risk_difference",
                self.serious_event_risk_difference,
                expected_difference,
            ),
        ):
            _require_finite(observed, field_name)
            if not math.isclose(observed, expected, rel_tol=0.0, abs_tol=1e-12):
                raise ValueError(f"{field_name} does not match raw counts")
        if self.safety_direction not in {
            "lower_observed_serious_event_risk",
            "higher_observed_serious_event_risk",
            "equal_observed_serious_event_risk",
        }:
            raise ValueError("safety_direction is not recognized")
        if math.isclose(expected_difference, 0.0, rel_tol=0.0, abs_tol=1e-12):
            expected_direction = "equal_observed_serious_event_risk"
        elif expected_difference < 0:
            expected_direction = "lower_observed_serious_event_risk"
        else:
            expected_direction = "higher_observed_serious_event_risk"
        if self.safety_direction != expected_direction:
            raise ValueError("safety_direction does not match raw counts")
        for field_name in (
            "source_content_hashes",
            "referenced_by_synthesis_ids",
            "referenced_by_endpoint_families",
        ):
            values = _sorted_unique_text(getattr(self, field_name), field_name)
            object.__setattr__(self, field_name, values)
            if not values:
                raise ValueError(f"{field_name} must not be empty")
        for index, digest in enumerate(self.source_content_hashes):
            _require_sha256(digest, f"source_content_hashes[{index}]")
        _require_positive_int(self.reference_count, "reference_count")
        if self.reference_count != len(self.referenced_by_synthesis_ids):
            raise ValueError("safety reference_count does not match synthesis references")


@dataclass(frozen=True, slots=True)
class ClinicalBenefitRiskSourceUnit(SerializableRecord):
    """One source hash and every endpoint domain that reuses it."""

    source_content_hash: str
    trial_id: str
    synthesis_ids: tuple[str, ...]
    endpoint_families: tuple[str, ...]
    safety_unit_ids: tuple[str, ...]
    reference_count: int

    def __post_init__(self) -> None:
        _require_sha256(self.source_content_hash, "source_content_hash")
        _require_text(self.trial_id, "trial_id")
        for field_name in (
            "synthesis_ids",
            "endpoint_families",
            "safety_unit_ids",
        ):
            values = _sorted_unique_text(getattr(self, field_name), field_name)
            object.__setattr__(self, field_name, values)
            if not values:
                raise ValueError(f"{field_name} must not be empty")
        for index, digest in enumerate(self.safety_unit_ids):
            _require_sha256(digest, f"safety_unit_ids[{index}]")
        _require_positive_int(self.reference_count, "reference_count")
        if self.reference_count != len(self.synthesis_ids):
            raise ValueError("source reference_count does not match synthesis references")


@dataclass(frozen=True, slots=True)
class ClinicalBenefitRiskPortfolioReport(SerializableRecord):
    """Replay-bound multi-endpoint report without a combined clinical score."""

    portfolio_id: str
    program_id: str
    candidate_id: str
    intervention_id: str
    disease_id: str
    policy_id: str
    spec_sha256: str
    state_sha256: str
    endpoint_domains: tuple[ClinicalBenefitRiskEndpointDomain, ...]
    safety_units: tuple[ClinicalBenefitRiskSafetyUnit, ...]
    source_units: tuple[ClinicalBenefitRiskSourceUnit, ...]
    synthesis_count: int
    endpoint_family_count: int
    endpoint_reference_count: int
    unique_endpoint_count: int
    endpoint_reuse_count: int
    trial_reference_count: int
    unique_trial_count: int
    trial_reuse_count: int
    safety_reference_count: int
    unique_safety_unit_count: int
    safety_reuse_count: int
    source_reference_count: int
    unique_source_count: int
    source_reuse_count: int
    distinct_endpoint_records_across_domains: bool
    full_state_replay_performed: bool
    pooling_performed: bool
    benefit_risk_score_computed: bool
    cross_endpoint_comparability_inferred: bool
    safety_independence_inferred: bool
    clinical_acceptability_inferred: bool
    limitations: tuple[str, ...]
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for field_name in (
            "portfolio_id",
            "program_id",
            "candidate_id",
            "intervention_id",
            "disease_id",
            "policy_id",
        ):
            _require_text(getattr(self, field_name), field_name)
        if self.policy_id != CLINICAL_BENEFIT_RISK_PORTFOLIO_POLICY_ID:
            raise ValueError("unsupported portfolio policy_id")
        _require_sha256(self.spec_sha256, "spec_sha256")
        _require_sha256(self.state_sha256, "state_sha256")
        domains = _tuple(self.endpoint_domains, "endpoint_domains")
        safety_units = _tuple(self.safety_units, "safety_units")
        source_units = _tuple(self.source_units, "source_units")
        object.__setattr__(self, "endpoint_domains", domains)
        object.__setattr__(self, "safety_units", safety_units)
        object.__setattr__(self, "source_units", source_units)
        for item in domains:
            _require_instance(item, ClinicalBenefitRiskEndpointDomain, "domain item")
        for item in safety_units:
            _require_instance(item, ClinicalBenefitRiskSafetyUnit, "safety unit item")
        for item in source_units:
            _require_instance(item, ClinicalBenefitRiskSourceUnit, "source unit item")
        if len(domains) < 2:
            raise ValueError("portfolio report requires at least two endpoint domains")
        if domains != tuple(
            sorted(domains, key=lambda item: (item.endpoint_family, item.synthesis_id))
        ):
            raise ValueError("endpoint domains must use canonical family order")
        if safety_units != tuple(
            sorted(
                safety_units,
                key=lambda item: (
                    item.trial_id,
                    item.design_id,
                    item.safety_id,
                    item.safety_unit_id,
                ),
            )
        ):
            raise ValueError("safety units must use canonical trial order")
        if source_units != tuple(
            sorted(source_units, key=lambda item: item.source_content_hash)
        ):
            raise ValueError("source units must use canonical hash order")
        synthesis_ids = tuple(item.synthesis_id for item in domains)
        endpoint_families = tuple(item.endpoint_family for item in domains)
        if len(synthesis_ids) != len(set(synthesis_ids)):
            raise ValueError("endpoint domain synthesis ids must be unique")
        if len(endpoint_families) != len(set(endpoint_families)):
            raise ValueError("endpoint domain families must be unique")
        count_fields = (
            "synthesis_count",
            "endpoint_family_count",
            "endpoint_reference_count",
            "unique_endpoint_count",
            "endpoint_reuse_count",
            "trial_reference_count",
            "unique_trial_count",
            "trial_reuse_count",
            "safety_reference_count",
            "unique_safety_unit_count",
            "safety_reuse_count",
            "source_reference_count",
            "unique_source_count",
            "source_reuse_count",
        )
        for field_name in count_fields:
            _require_non_negative_int(getattr(self, field_name), field_name)
        cells = tuple(cell for domain in domains for cell in domain.cells)
        safety_by_id = {item.safety_unit_id: item for item in safety_units}
        if len(safety_by_id) != len(safety_units):
            raise ValueError("safety unit ids must be unique")
        if {item.safety_unit_id for item in cells} != set(safety_by_id):
            raise ValueError("endpoint cells do not cover the exact safety units")
        for safety_unit_id, safety_unit in safety_by_id.items():
            references = tuple(
                (domain, cell)
                for domain in domains
                for cell in domain.cells
                if cell.safety_unit_id == safety_unit_id
            )
            if any(
                cell.trial_id != safety_unit.trial_id
                or cell.design_id != safety_unit.design_id
                or cell.source_content_hashes
                != safety_unit.source_content_hashes
                for _, cell in references
            ):
                raise ValueError("endpoint-to-safety identity is rebound")
            if tuple(sorted(domain.synthesis_id for domain, _ in references)) != (
                safety_unit.referenced_by_synthesis_ids
            ):
                raise ValueError("safety synthesis references do not match endpoint cells")
            if tuple(
                sorted(domain.endpoint_family for domain, _ in references)
            ) != safety_unit.referenced_by_endpoint_families:
                raise ValueError("safety endpoint-family references do not match cells")
            if len(references) != safety_unit.reference_count:
                raise ValueError("safety reference_count does not match endpoint cells")
        for domain in domains:
            expected_safety_consistency = len(
                {
                    safety_by_id[cell.safety_unit_id].safety_direction
                    for cell in domain.cells
                }
            ) == 1
            if domain.safety_direction_consistent != expected_safety_consistency:
                raise ValueError(
                    "safety direction consistency does not match linked safety units"
                )
        source_by_hash = {item.source_content_hash: item for item in source_units}
        if len(source_by_hash) != len(source_units):
            raise ValueError("source content hashes must be unique")
        cell_source_hashes = {
            digest for cell in cells for digest in cell.source_content_hashes
        }
        if cell_source_hashes != set(source_by_hash):
            raise ValueError("endpoint cells do not cover the exact source units")
        for digest, source_unit in source_by_hash.items():
            references = tuple(
                (domain, cell)
                for domain in domains
                for cell in domain.cells
                if digest in cell.source_content_hashes
            )
            if {cell.trial_id for _, cell in references} != {source_unit.trial_id}:
                raise ValueError("source content hash is rebound across trial ids")
            if tuple(sorted(domain.synthesis_id for domain, _ in references)) != (
                source_unit.synthesis_ids
            ):
                raise ValueError("source synthesis references do not match endpoint cells")
            if tuple(
                sorted(domain.endpoint_family for domain, _ in references)
            ) != source_unit.endpoint_families:
                raise ValueError("source endpoint-family references do not match cells")
            if tuple(sorted({cell.safety_unit_id for _, cell in references})) != (
                source_unit.safety_unit_ids
            ):
                raise ValueError("source safety references do not match endpoint cells")
            if len(references) != source_unit.reference_count:
                raise ValueError("source reference_count does not match endpoint cells")
        endpoint_keys = {(item.trial_id, item.endpoint_id) for item in cells}
        trial_ids = {item.trial_id for item in cells}
        source_reference_count = sum(
            len(item.source_content_hashes) for item in cells
        )
        expected_counts = {
            "synthesis_count": len(domains),
            "endpoint_family_count": len({item.endpoint_family for item in domains}),
            "endpoint_reference_count": len(cells),
            "unique_endpoint_count": len(endpoint_keys),
            "endpoint_reuse_count": len(cells) - len(endpoint_keys),
            "trial_reference_count": len(cells),
            "unique_trial_count": len(trial_ids),
            "trial_reuse_count": len(cells) - len(trial_ids),
            "safety_reference_count": sum(
                item.reference_count for item in safety_units
            ),
            "unique_safety_unit_count": len(safety_units),
            "safety_reuse_count": sum(
                item.reference_count for item in safety_units
            )
            - len(safety_units),
            "source_reference_count": source_reference_count,
            "unique_source_count": len(source_units),
            "source_reuse_count": source_reference_count - len(source_units),
        }
        for field_name, expected in expected_counts.items():
            if getattr(self, field_name) != expected:
                raise ValueError(f"{field_name} does not match report contents")
        bool_fields = (
            "distinct_endpoint_records_across_domains",
            "full_state_replay_performed",
            "pooling_performed",
            "benefit_risk_score_computed",
            "cross_endpoint_comparability_inferred",
            "safety_independence_inferred",
            "clinical_acceptability_inferred",
        )
        for field_name in bool_fields:
            _require_bool(getattr(self, field_name), field_name)
        if self.distinct_endpoint_records_across_domains != (
            self.endpoint_reuse_count == 0
        ):
            raise ValueError("endpoint distinctness does not match endpoint reuse")
        if not self.full_state_replay_performed:
            raise ValueError("portfolio report requires full state replay")
        for field_name in (
            "pooling_performed",
            "benefit_risk_score_computed",
            "cross_endpoint_comparability_inferred",
            "safety_independence_inferred",
            "clinical_acceptability_inferred",
        ):
            if getattr(self, field_name):
                raise ValueError(f"{field_name} must remain false")
        limitations = _tuple(self.limitations, "limitations")
        object.__setattr__(self, "limitations", limitations)
        if limitations != _REQUIRED_LIMITATIONS:
            raise ValueError("portfolio limitations changed")
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata, "metadata"))

    @property
    def fingerprint(self) -> str:
        return _sha256(self)


def _safety_identity(study: StudyBenefitRiskRecord) -> tuple[str, str]:
    fingerprint = study.identifiers.get("safety_fingerprint_sha256")
    if not isinstance(fingerprint, str):
        raise ClinicalBenefitRiskPortfolioError(
            "study safety fingerprint is missing"
        )
    _require_sha256(fingerprint, "safety_fingerprint_sha256")
    safety_unit_id = _sha256(
        {
            "trial_id": study.trial_id,
            "design_id": study.design_id,
            "safety_id": study.safety_id,
            "safety_fingerprint_sha256": fingerprint,
        }
    )
    return safety_unit_id, fingerprint


def _endpoint_cell(
    study: StudyBenefitRiskRecord,
    *,
    safety_unit_id: str,
) -> ClinicalBenefitRiskEndpointCell:
    endpoint_fingerprint = study.identifiers.get("endpoint_fingerprint_sha256")
    if not isinstance(endpoint_fingerprint, str):
        raise ClinicalBenefitRiskPortfolioError(
            "study endpoint fingerprint is missing"
        )
    return ClinicalBenefitRiskEndpointCell(
        study_record_id=study.study_record_id,
        trial_id=study.trial_id,
        design_id=study.design_id,
        endpoint_id=study.endpoint_id,
        endpoint_fingerprint_sha256=endpoint_fingerprint,
        safety_unit_id=safety_unit_id,
        effect_estimate=study.effect_estimate,
        confidence_interval_percent=study.confidence_interval_percent,
        confidence_interval_lower=study.confidence_interval_lower,
        confidence_interval_upper=study.confidence_interval_upper,
        measurement_unit=study.measurement_unit,
        endpoint_time_frame=study.endpoint_time_frame,
        benefit_direction=study.benefit_direction,
        source_content_hashes=study.source_content_hashes,
    )


def compile_clinical_benefit_risk_portfolio(
    state: ProgramState,
    spec: ClinicalBenefitRiskPortfolioSpec,
) -> ClinicalBenefitRiskPortfolioReport:
    """Compile replayed endpoint domains and deduplicate shared provenance."""

    _require_instance(state, ProgramState, "state")
    _require_instance(spec, ClinicalBenefitRiskPortfolioSpec, "spec")
    try:
        state.validate_committed_history()
    except (TypeError, ValueError) as exc:
        raise ClinicalBenefitRiskPortfolioError(
            "program state failed committed-history replay"
        ) from exc
    candidate = state.candidates_by_id.get(spec.candidate_id)
    intervention = state.interventions_by_id.get(spec.intervention_id)
    disease = state.diseases_by_id.get(spec.disease_id)
    if candidate is None or intervention is None or disease is None:
        raise ClinicalBenefitRiskPortfolioError(
            "portfolio candidate, intervention, or disease is absent"
        )
    if (
        intervention.candidate_id != spec.candidate_id
        or intervention.disease_id != spec.disease_id
    ):
        raise ClinicalBenefitRiskPortfolioError(
            "portfolio candidate/intervention/disease identity is rebound"
        )

    syntheses: list[BenefitRiskSynthesisRecord] = []
    for synthesis_id in spec.synthesis_ids:
        synthesis = state.benefit_risk_syntheses_by_id.get(synthesis_id)
        if synthesis is None:
            raise ClinicalBenefitRiskPortfolioError(
                f"portfolio synthesis is absent from state: {synthesis_id}"
            )
        if (
            synthesis.candidate_id != spec.candidate_id
            or synthesis.intervention_id != spec.intervention_id
            or synthesis.disease_id != spec.disease_id
        ):
            raise ClinicalBenefitRiskPortfolioError(
                f"portfolio synthesis identity is rebound: {synthesis_id}"
            )
        failures = validate_benefit_risk_synthesis(state, synthesis)
        if failures:
            raise ClinicalBenefitRiskPortfolioError(
                f"portfolio synthesis failed ledger replay: {synthesis_id}: "
                f"{', '.join(failures)}"
            )
        syntheses.append(synthesis)
    endpoint_families = {item.endpoint_family for item in syntheses}
    if len(endpoint_families) != len(syntheses):
        raise ClinicalBenefitRiskPortfolioError(
            "portfolio synthesis endpoint families must be distinct"
        )

    endpoint_owners: defaultdict[tuple[str, str], set[str]] = defaultdict(set)
    trial_owners: defaultdict[str, set[str]] = defaultdict(set)
    safety_records: dict[tuple[str, str, str], StudyBenefitRiskRecord] = {}
    safety_owners: defaultdict[tuple[str, str, str], set[tuple[str, str]]] = (
        defaultdict(set)
    )
    source_trials: defaultdict[str, set[str]] = defaultdict(set)
    source_owners: defaultdict[str, set[tuple[str, str, str]]] = defaultdict(set)
    domains: list[ClinicalBenefitRiskEndpointDomain] = []

    for synthesis in syntheses:
        cells: list[ClinicalBenefitRiskEndpointCell] = []
        favorable_direction = synthesis.attributes.get(
            "effect_measure_favorable_direction"
        )
        if not isinstance(favorable_direction, str):
            raise ClinicalBenefitRiskPortfolioError(
                "synthesis favorable direction is missing"
            )
        for study in synthesis.studies:
            safety_unit_id, safety_fingerprint = _safety_identity(study)
            safety_key = (study.trial_id, study.design_id, study.safety_id)
            existing = safety_records.setdefault(safety_key, study)
            existing_unit_id, existing_fingerprint = _safety_identity(existing)
            if (
                existing_unit_id != safety_unit_id
                or existing_fingerprint != safety_fingerprint
                or (
                    existing.candidate_serious_num_affected,
                    existing.candidate_serious_num_at_risk,
                    existing.comparator_serious_num_affected,
                    existing.comparator_serious_num_at_risk,
                    existing.safety_time_frame,
                    existing.source_content_hashes,
                )
                != (
                    study.candidate_serious_num_affected,
                    study.candidate_serious_num_at_risk,
                    study.comparator_serious_num_affected,
                    study.comparator_serious_num_at_risk,
                    study.safety_time_frame,
                    study.source_content_hashes,
                )
            ):
                raise ClinicalBenefitRiskPortfolioError(
                    "one safety identity is rebound across endpoint domains"
                )
            endpoint_key = (study.trial_id, study.endpoint_id)
            endpoint_owners[endpoint_key].add(synthesis.synthesis_id)
            trial_owners[study.trial_id].add(synthesis.synthesis_id)
            safety_owners[safety_key].add(
                (synthesis.synthesis_id, synthesis.endpoint_family)
            )
            for digest in study.source_content_hashes:
                source_trials[digest].add(study.trial_id)
                source_owners[digest].add(
                    (
                        synthesis.synthesis_id,
                        synthesis.endpoint_family,
                        safety_unit_id,
                    )
                )
            cells.append(_endpoint_cell(study, safety_unit_id=safety_unit_id))
        domains.append(
            ClinicalBenefitRiskEndpointDomain(
                synthesis_id=synthesis.synthesis_id,
                synthesis_sha256=_sha256(synthesis),
                endpoint_mapping_id=synthesis.endpoint_mapping_id,
                endpoint_family=synthesis.endpoint_family,
                effect_measure=synthesis.effect_measure,
                favorable_direction=favorable_direction,
                safety_measure=synthesis.safety_measure,
                harmonization_policy_id=synthesis.harmonization_policy_id,
                cells=tuple(sorted(cells, key=lambda item: item.trial_id)),
                benefit_direction_consistent=(
                    synthesis.benefit_direction_consistent
                ),
                safety_direction_consistent=synthesis.safety_direction_consistent,
                source_disjoint_within_domain=synthesis.source_disjoint,
                pooling_performed=synthesis.pooling_performed,
            )
        )

    repeated_endpoints = {
        key: owners for key, owners in endpoint_owners.items() if len(owners) > 1
    }
    if spec.require_distinct_endpoint_records and repeated_endpoints:
        raise ClinicalBenefitRiskPortfolioError(
            "strict multi-endpoint portfolio reuses endpoint records across domains"
        )
    cross_trial_source_reuse = {
        digest: trials for digest, trials in source_trials.items() if len(trials) > 1
    }
    if cross_trial_source_reuse:
        raise ClinicalBenefitRiskPortfolioError(
            "one source content hash is rebound across different trial ids"
        )

    safety_units: list[ClinicalBenefitRiskSafetyUnit] = []
    for safety_key, study in safety_records.items():
        safety_unit_id, safety_fingerprint = _safety_identity(study)
        owners = safety_owners[safety_key]
        synthesis_ids = tuple(sorted(item[0] for item in owners))
        endpoint_families_for_unit = tuple(sorted(item[1] for item in owners))
        safety_units.append(
            ClinicalBenefitRiskSafetyUnit(
                safety_unit_id=safety_unit_id,
                trial_id=study.trial_id,
                design_id=study.design_id,
                safety_id=study.safety_id,
                safety_fingerprint_sha256=safety_fingerprint,
                safety_time_frame=study.safety_time_frame,
                candidate_serious_num_affected=(
                    study.candidate_serious_num_affected
                ),
                candidate_serious_num_at_risk=study.candidate_serious_num_at_risk,
                comparator_serious_num_affected=(
                    study.comparator_serious_num_affected
                ),
                comparator_serious_num_at_risk=(
                    study.comparator_serious_num_at_risk
                ),
                candidate_serious_event_risk=study.candidate_serious_event_risk,
                comparator_serious_event_risk=study.comparator_serious_event_risk,
                serious_event_risk_difference=study.serious_event_risk_difference,
                safety_direction=study.safety_direction,
                source_content_hashes=study.source_content_hashes,
                referenced_by_synthesis_ids=synthesis_ids,
                referenced_by_endpoint_families=endpoint_families_for_unit,
                reference_count=len(synthesis_ids),
            )
        )

    source_units: list[ClinicalBenefitRiskSourceUnit] = []
    for digest, owners in source_owners.items():
        synthesis_ids = tuple(sorted(item[0] for item in owners))
        source_units.append(
            ClinicalBenefitRiskSourceUnit(
                source_content_hash=digest,
                trial_id=next(iter(source_trials[digest])),
                synthesis_ids=synthesis_ids,
                endpoint_families=tuple(sorted({item[1] for item in owners})),
                safety_unit_ids=tuple(sorted({item[2] for item in owners})),
                reference_count=len(synthesis_ids),
            )
        )

    ordered_domains = tuple(
        sorted(domains, key=lambda item: (item.endpoint_family, item.synthesis_id))
    )
    ordered_safety = tuple(
        sorted(
            safety_units,
            key=lambda item: (
                item.trial_id,
                item.design_id,
                item.safety_id,
                item.safety_unit_id,
            ),
        )
    )
    ordered_sources = tuple(
        sorted(source_units, key=lambda item: item.source_content_hash)
    )
    cells = tuple(cell for domain in ordered_domains for cell in domain.cells)
    endpoint_keys = {(item.trial_id, item.endpoint_id) for item in cells}
    trial_ids = {item.trial_id for item in cells}
    source_reference_count = sum(len(item.source_content_hashes) for item in cells)
    return ClinicalBenefitRiskPortfolioReport(
        portfolio_id=spec.portfolio_id,
        program_id=state.program_id,
        candidate_id=spec.candidate_id,
        intervention_id=spec.intervention_id,
        disease_id=spec.disease_id,
        policy_id=spec.policy_id,
        spec_sha256=spec.fingerprint,
        state_sha256=_sha256(state),
        endpoint_domains=ordered_domains,
        safety_units=ordered_safety,
        source_units=ordered_sources,
        synthesis_count=len(ordered_domains),
        endpoint_family_count=len(endpoint_families),
        endpoint_reference_count=len(cells),
        unique_endpoint_count=len(endpoint_keys),
        endpoint_reuse_count=len(cells) - len(endpoint_keys),
        trial_reference_count=len(cells),
        unique_trial_count=len(trial_ids),
        trial_reuse_count=len(cells) - len(trial_ids),
        safety_reference_count=sum(item.reference_count for item in ordered_safety),
        unique_safety_unit_count=len(ordered_safety),
        safety_reuse_count=(
            sum(item.reference_count for item in ordered_safety) - len(ordered_safety)
        ),
        source_reference_count=source_reference_count,
        unique_source_count=len(ordered_sources),
        source_reuse_count=source_reference_count - len(ordered_sources),
        distinct_endpoint_records_across_domains=not repeated_endpoints,
        full_state_replay_performed=True,
        pooling_performed=False,
        benefit_risk_score_computed=False,
        cross_endpoint_comparability_inferred=False,
        safety_independence_inferred=False,
        clinical_acceptability_inferred=False,
        limitations=_REQUIRED_LIMITATIONS,
        metadata={
            "require_distinct_endpoint_records": (
                spec.require_distinct_endpoint_records
            ),
            "cross_domain_trial_overlap_count": sum(
                1 for owners in trial_owners.values() if len(owners) > 1
            ),
            "spec_metadata": dict(spec.metadata),
        },
    )


def validate_clinical_benefit_risk_portfolio(
    state: ProgramState,
    spec: ClinicalBenefitRiskPortfolioSpec,
    report: ClinicalBenefitRiskPortfolioReport,
) -> tuple[str, ...]:
    """Recompile the exact portfolio and return deterministic failure codes."""

    try:
        rebuilt = compile_clinical_benefit_risk_portfolio(state, spec)
    except (ClinicalBenefitRiskPortfolioError, TypeError, ValueError):
        return ("portfolio_recompile_failed",)
    if rebuilt != report:
        return ("portfolio_recompiled_report_mismatch",)
    return ()


def clinical_benefit_risk_portfolio_spec_envelope(
    spec: ClinicalBenefitRiskPortfolioSpec,
) -> dict[str, Any]:
    """Return a strict integrity envelope for a portfolio specification."""

    _require_instance(spec, ClinicalBenefitRiskPortfolioSpec, "spec")
    return {
        "schema_version": CLINICAL_BENEFIT_RISK_PORTFOLIO_SPEC_SCHEMA_VERSION,
        "integrity_sha256": spec.fingerprint,
        "spec": to_primitive(spec),
    }


def clinical_benefit_risk_portfolio_report_envelope(
    report: ClinicalBenefitRiskPortfolioReport,
) -> dict[str, Any]:
    """Return a strict integrity envelope for a portfolio report."""

    _require_instance(report, ClinicalBenefitRiskPortfolioReport, "report")
    return {
        "schema_version": CLINICAL_BENEFIT_RISK_PORTFOLIO_REPORT_SCHEMA_VERSION,
        "integrity_sha256": report.fingerprint,
        "report": to_primitive(report),
    }


def clinical_benefit_risk_portfolio_spec_from_dict(
    value: Any,
) -> ClinicalBenefitRiskPortfolioSpec:
    """Parse and integrity-check one portfolio specification envelope."""

    envelope = _record(
        value,
        "portfolio_spec_envelope",
        {"schema_version", "integrity_sha256", "spec"},
    )
    if envelope["schema_version"] != (
        CLINICAL_BENEFIT_RISK_PORTFOLIO_SPEC_SCHEMA_VERSION
    ):
        raise ClinicalBenefitRiskPortfolioError("unsupported portfolio spec schema")
    _require_sha256(envelope["integrity_sha256"], "integrity_sha256")
    data = _record(
        envelope["spec"],
        "portfolio_spec",
        {
            "portfolio_id",
            "candidate_id",
            "intervention_id",
            "disease_id",
            "synthesis_ids",
            "require_distinct_endpoint_records",
            "require_full_state_replay",
            "policy_id",
            "metadata",
        },
    )
    spec = ClinicalBenefitRiskPortfolioSpec(
        portfolio_id=data["portfolio_id"],
        candidate_id=data["candidate_id"],
        intervention_id=data["intervention_id"],
        disease_id=data["disease_id"],
        synthesis_ids=_tuple(data["synthesis_ids"], "synthesis_ids"),
        require_distinct_endpoint_records=data[
            "require_distinct_endpoint_records"
        ],
        require_full_state_replay=data["require_full_state_replay"],
        policy_id=data["policy_id"],
        metadata=_record_mapping(data["metadata"], "metadata"),
    )
    if spec.fingerprint != envelope["integrity_sha256"]:
        raise ClinicalBenefitRiskPortfolioError(
            "portfolio spec integrity mismatch"
        )
    return spec


def _record_mapping(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ClinicalBenefitRiskPortfolioError(f"{path} must be an object")
    return dict(value)


def clinical_benefit_risk_portfolio_spec_from_json(
    text: str,
) -> ClinicalBenefitRiskPortfolioSpec:
    return clinical_benefit_risk_portfolio_spec_from_dict(
        _load_json(text, "portfolio spec envelope")
    )


def _endpoint_cell_from_dict(
    value: Any,
    path: str,
) -> ClinicalBenefitRiskEndpointCell:
    data = _record(value, path, _field_names(ClinicalBenefitRiskEndpointCell))
    return ClinicalBenefitRiskEndpointCell(**data)


def _endpoint_domain_from_dict(
    value: Any,
    path: str,
) -> ClinicalBenefitRiskEndpointDomain:
    data = _record(value, path, _field_names(ClinicalBenefitRiskEndpointDomain))
    data["cells"] = tuple(
        _endpoint_cell_from_dict(item, f"{path}.cells[{index}]")
        for index, item in enumerate(_tuple(data["cells"], f"{path}.cells"))
    )
    return ClinicalBenefitRiskEndpointDomain(**data)


def _safety_unit_from_dict(
    value: Any,
    path: str,
) -> ClinicalBenefitRiskSafetyUnit:
    data = _record(value, path, _field_names(ClinicalBenefitRiskSafetyUnit))
    return ClinicalBenefitRiskSafetyUnit(**data)


def _source_unit_from_dict(
    value: Any,
    path: str,
) -> ClinicalBenefitRiskSourceUnit:
    data = _record(value, path, _field_names(ClinicalBenefitRiskSourceUnit))
    return ClinicalBenefitRiskSourceUnit(**data)


def clinical_benefit_risk_portfolio_report_from_dict(
    value: Any,
) -> ClinicalBenefitRiskPortfolioReport:
    """Parse and integrity-check one portfolio report envelope."""

    envelope = _record(
        value,
        "portfolio_report_envelope",
        {"schema_version", "integrity_sha256", "report"},
    )
    if envelope["schema_version"] != (
        CLINICAL_BENEFIT_RISK_PORTFOLIO_REPORT_SCHEMA_VERSION
    ):
        raise ClinicalBenefitRiskPortfolioError("unsupported portfolio report schema")
    _require_sha256(envelope["integrity_sha256"], "integrity_sha256")
    data = _record(
        envelope["report"],
        "portfolio_report",
        _field_names(ClinicalBenefitRiskPortfolioReport),
    )
    data["endpoint_domains"] = tuple(
        _endpoint_domain_from_dict(item, f"portfolio_report.endpoint_domains[{index}]")
        for index, item in enumerate(
            _tuple(data["endpoint_domains"], "portfolio_report.endpoint_domains")
        )
    )
    data["safety_units"] = tuple(
        _safety_unit_from_dict(item, f"portfolio_report.safety_units[{index}]")
        for index, item in enumerate(
            _tuple(data["safety_units"], "portfolio_report.safety_units")
        )
    )
    data["source_units"] = tuple(
        _source_unit_from_dict(item, f"portfolio_report.source_units[{index}]")
        for index, item in enumerate(
            _tuple(data["source_units"], "portfolio_report.source_units")
        )
    )
    report = ClinicalBenefitRiskPortfolioReport(**data)
    if report.fingerprint != envelope["integrity_sha256"]:
        raise ClinicalBenefitRiskPortfolioError(
            "portfolio report integrity mismatch"
        )
    return report


def clinical_benefit_risk_portfolio_report_from_json(
    text: str,
) -> ClinicalBenefitRiskPortfolioReport:
    return clinical_benefit_risk_portfolio_report_from_dict(
        _load_json(text, "portfolio report envelope")
    )


def clinical_benefit_risk_portfolio_report_summary(
    report: ClinicalBenefitRiskPortfolioReport,
) -> dict[str, Any]:
    """Return a compact human- and machine-facing portfolio summary."""

    _require_instance(report, ClinicalBenefitRiskPortfolioReport, "report")
    return {
        "portfolio_id": report.portfolio_id,
        "program_id": report.program_id,
        "endpoint_families": [
            item.endpoint_family for item in report.endpoint_domains
        ],
        "effect_measures": [item.effect_measure for item in report.endpoint_domains],
        "synthesis_count": report.synthesis_count,
        "endpoint_reference_count": report.endpoint_reference_count,
        "unique_endpoint_count": report.unique_endpoint_count,
        "endpoint_reuse_count": report.endpoint_reuse_count,
        "trial_reference_count": report.trial_reference_count,
        "unique_trial_count": report.unique_trial_count,
        "trial_reuse_count": report.trial_reuse_count,
        "safety_reference_count": report.safety_reference_count,
        "unique_safety_unit_count": report.unique_safety_unit_count,
        "safety_reuse_count": report.safety_reuse_count,
        "source_reference_count": report.source_reference_count,
        "unique_source_count": report.unique_source_count,
        "source_reuse_count": report.source_reuse_count,
        "distinct_endpoint_records_across_domains": (
            report.distinct_endpoint_records_across_domains
        ),
        "pooling_performed": report.pooling_performed,
        "benefit_risk_score_computed": report.benefit_risk_score_computed,
        "clinical_acceptability_inferred": report.clinical_acceptability_inferred,
        "integrity_sha256": report.fingerprint,
    }
