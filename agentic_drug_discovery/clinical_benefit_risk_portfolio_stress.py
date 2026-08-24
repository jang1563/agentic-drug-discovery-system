"""Pairwise structural stress diagnostics for multi-endpoint portfolios."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass, fields
from itertools import combinations
from typing import Any

from .clinical_benefit_risk_portfolio import (
    ClinicalBenefitRiskEndpointCell,
    ClinicalBenefitRiskEndpointDomain,
    ClinicalBenefitRiskPortfolioReport,
    ClinicalBenefitRiskPortfolioSpec,
    validate_clinical_benefit_risk_portfolio,
)
from .clinical_population import (
    ClinicalPopulationAlignmentError,
    TREATMENT_PHASES,
    validate_phase_bound_population_alignment,
)
from .models import (
    ProgramState,
    SerializableRecord,
    _require_instance,
    _require_sha256,
    _require_text,
    to_primitive,
)


CLINICAL_BENEFIT_RISK_PORTFOLIO_STRESS_REPORT_SCHEMA_VERSION = (
    "adds.clinical-benefit-risk-portfolio-stress-report.v1"
)
CLINICAL_BENEFIT_RISK_PORTFOLIO_STRESS_POLICY_ID = (
    "adds.same-trial-multi-endpoint-structural-stress.v1"
)

MATCHED_STRUCTURE = "matched_structure"
PHASE_UNDECLARED = "phase_undeclared"
HETEROGENEOUS_STRUCTURE = "heterogeneous_structure"

EXACT_SOURCE_OVERLAP = "exact"
PARTIAL_SOURCE_OVERLAP = "partial"
DISJOINT_SOURCE_OVERLAP = "disjoint"

ENDPOINT_RECORD_REUSED = "endpoint_record_reused"
POPULATION_IDENTITY_MISMATCH = "analysis_population_identity_mismatch"
POPULATION_RECORD_MISMATCH = "analysis_population_record_mismatch"
POPULATION_ALIGNMENT_MISMATCH = "population_alignment_record_mismatch"
ENDPOINT_TIMEFRAME_MISMATCH = "endpoint_timeframe_mismatch"
TREATMENT_PHASE_NOT_DECLARED = "treatment_phase_not_declared"
TREATMENT_PHASE_PARTIAL_DECLARATION = "treatment_phase_partial_declaration"
TREATMENT_PHASE_MISMATCH = "treatment_phase_mismatch"
SAFETY_RECORD_IDENTITY_MISMATCH = "safety_record_identity_mismatch"
SAFETY_TIMEFRAME_MISMATCH = "safety_timeframe_mismatch"

_DIAGNOSTIC_CODES = frozenset(
    {
        ENDPOINT_RECORD_REUSED,
        POPULATION_IDENTITY_MISMATCH,
        POPULATION_RECORD_MISMATCH,
        POPULATION_ALIGNMENT_MISMATCH,
        ENDPOINT_TIMEFRAME_MISMATCH,
        TREATMENT_PHASE_NOT_DECLARED,
        TREATMENT_PHASE_PARTIAL_DECLARATION,
        TREATMENT_PHASE_MISMATCH,
        SAFETY_RECORD_IDENTITY_MISMATCH,
        SAFETY_TIMEFRAME_MISMATCH,
    }
)
_HETEROGENEITY_CODES = frozenset(
    {
        ENDPOINT_RECORD_REUSED,
        POPULATION_IDENTITY_MISMATCH,
        POPULATION_RECORD_MISMATCH,
        POPULATION_ALIGNMENT_MISMATCH,
        ENDPOINT_TIMEFRAME_MISMATCH,
        TREATMENT_PHASE_PARTIAL_DECLARATION,
        TREATMENT_PHASE_MISMATCH,
        SAFETY_RECORD_IDENTITY_MISMATCH,
        SAFETY_TIMEFRAME_MISMATCH,
    }
)

_REQUIRED_LIMITATIONS = (
    (
        "Pairwise structural matches do not establish endpoint exchangeability, "
        "clinical comparability, or a shared estimand."
    ),
    (
        "Shared safety units and source artifacts are provenance reuse, not new "
        "independent evidence."
    ),
    (
        "Exact population identifiers and hashes do not establish that endpoint "
        "analysis sets contain the same participants."
    ),
    (
        "Time-frame text equality does not establish equal follow-up, censoring, "
        "assessment schedules, or risk windows."
    ),
    (
        "The diagnostic performs no pooling, utility weighting, clinical "
        "acceptability judgment, treatment choice, or regulatory inference."
    ),
)


class ClinicalBenefitRiskPortfolioStressError(ValueError):
    """Raised when a structural stress report cannot be replayed safely."""


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
    values = _tuple(value, field_name)
    for item in values:
        _require_text(item, field_name)
    if values != tuple(sorted(values)) or len(values) != len(set(values)):
        raise ValueError(f"{field_name} must use canonical unique sorted order")
    return values


def _require_bool(value: Any, field_name: str) -> None:
    if not isinstance(value, bool):
        raise TypeError(f"{field_name} must be boolean")


def _require_non_negative_int(value: Any, field_name: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")


def _field_names(record_type: type[Any]) -> set[str]:
    return {item.name for item in fields(record_type)}


def _record(value: Any, path: str, expected_fields: set[str]) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ClinicalBenefitRiskPortfolioStressError(f"{path} must be an object")
    if set(value) != expected_fields:
        raise ClinicalBenefitRiskPortfolioStressError(
            f"{path} must contain exactly {sorted(expected_fields)}"
        )
    return dict(value)


def _reject_constant(value: str) -> None:
    raise ClinicalBenefitRiskPortfolioStressError(
        f"non-finite JSON constant is not allowed: {value}"
    )


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ClinicalBenefitRiskPortfolioStressError(
                f"duplicate JSON key: {key}"
            )
        result[key] = value
    return result


def _load_json(text: str) -> dict[str, Any]:
    try:
        value = json.loads(
            text,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except ClinicalBenefitRiskPortfolioStressError:
        raise
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ClinicalBenefitRiskPortfolioStressError(f"invalid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise ClinicalBenefitRiskPortfolioStressError(
            "portfolio stress report envelope must be a JSON object"
        )
    return value


@dataclass(frozen=True, slots=True)
class ClinicalBenefitRiskEndpointStressContext(SerializableRecord):
    """One state-replayed endpoint, population, and safety context."""

    synthesis_id: str
    endpoint_family: str
    trial_id: str
    design_id: str
    endpoint_id: str
    endpoint_fingerprint_sha256: str
    population_id: str
    population_record_sha256: str
    endpoint_time_frame: str
    treatment_phase: str | None
    population_alignment_sha256: str | None
    safety_unit_id: str
    safety_id: str
    safety_fingerprint_sha256: str
    safety_time_frame: str
    source_content_hashes: tuple[str, ...]

    def __post_init__(self) -> None:
        for field_name in (
            "synthesis_id",
            "endpoint_family",
            "trial_id",
            "design_id",
            "endpoint_id",
            "population_id",
            "endpoint_time_frame",
            "safety_id",
            "safety_time_frame",
        ):
            _require_text(getattr(self, field_name), field_name)
        for field_name in (
            "endpoint_fingerprint_sha256",
            "population_record_sha256",
            "safety_unit_id",
            "safety_fingerprint_sha256",
        ):
            _require_sha256(getattr(self, field_name), field_name)
        if self.treatment_phase is None:
            if self.population_alignment_sha256 is not None:
                raise ValueError(
                    "population alignment hash requires a declared treatment phase"
                )
        else:
            if self.treatment_phase not in TREATMENT_PHASES:
                raise ValueError("treatment_phase is not recognized")
            if self.population_alignment_sha256 is None:
                raise ValueError(
                    "declared treatment phase requires a population alignment hash"
                )
            _require_sha256(
                self.population_alignment_sha256,
                "population_alignment_sha256",
            )
        source_hashes = _sorted_unique_text(
            self.source_content_hashes,
            "source_content_hashes",
        )
        if not source_hashes:
            raise ValueError("source_content_hashes must not be empty")
        for index, digest in enumerate(source_hashes):
            _require_sha256(digest, f"source_content_hashes[{index}]")
        object.__setattr__(self, "source_content_hashes", source_hashes)


def _pair_id(
    left: ClinicalBenefitRiskEndpointStressContext,
    right: ClinicalBenefitRiskEndpointStressContext,
) -> str:
    return _sha256(
        {
            "trial_id": left.trial_id,
            "left_synthesis_id": left.synthesis_id,
            "right_synthesis_id": right.synthesis_id,
        }
    )


def _pair_facts(
    left: ClinicalBenefitRiskEndpointStressContext,
    right: ClinicalBenefitRiskEndpointStressContext,
) -> dict[str, Any]:
    diagnostic_codes: list[str] = []
    if left.endpoint_id == right.endpoint_id:
        diagnostic_codes.append(ENDPOINT_RECORD_REUSED)
    if left.population_id != right.population_id:
        diagnostic_codes.append(POPULATION_IDENTITY_MISMATCH)
    elif left.population_record_sha256 != right.population_record_sha256:
        diagnostic_codes.append(POPULATION_RECORD_MISMATCH)
    if (
        left.population_alignment_sha256 is not None
        and right.population_alignment_sha256 is not None
        and left.population_alignment_sha256 != right.population_alignment_sha256
    ):
        diagnostic_codes.append(POPULATION_ALIGNMENT_MISMATCH)
    if left.endpoint_time_frame != right.endpoint_time_frame:
        diagnostic_codes.append(ENDPOINT_TIMEFRAME_MISMATCH)
    if left.treatment_phase is None and right.treatment_phase is None:
        diagnostic_codes.append(TREATMENT_PHASE_NOT_DECLARED)
    elif left.treatment_phase is None or right.treatment_phase is None:
        diagnostic_codes.append(TREATMENT_PHASE_PARTIAL_DECLARATION)
    elif left.treatment_phase != right.treatment_phase:
        diagnostic_codes.append(TREATMENT_PHASE_MISMATCH)
    if left.safety_unit_id != right.safety_unit_id:
        diagnostic_codes.append(SAFETY_RECORD_IDENTITY_MISMATCH)
    if left.safety_time_frame != right.safety_time_frame:
        diagnostic_codes.append(SAFETY_TIMEFRAME_MISMATCH)

    left_sources = set(left.source_content_hashes)
    right_sources = set(right.source_content_hashes)
    shared_sources = tuple(sorted(left_sources & right_sources))
    if left_sources == right_sources:
        source_overlap_status = EXACT_SOURCE_OVERLAP
    elif shared_sources:
        source_overlap_status = PARTIAL_SOURCE_OVERLAP
    else:
        source_overlap_status = DISJOINT_SOURCE_OVERLAP

    code_set = set(diagnostic_codes)
    if code_set & _HETEROGENEITY_CODES:
        structural_status = HETEROGENEOUS_STRUCTURE
    elif TREATMENT_PHASE_NOT_DECLARED in code_set:
        structural_status = PHASE_UNDECLARED
    else:
        structural_status = MATCHED_STRUCTURE
    return {
        "shared_endpoint_record": left.endpoint_id == right.endpoint_id,
        "shared_population_identity": left.population_id == right.population_id,
        "shared_population_record": (
            left.population_id == right.population_id
            and left.population_record_sha256 == right.population_record_sha256
        ),
        "shared_population_alignment": (
            left.population_alignment_sha256 is not None
            and left.population_alignment_sha256
            == right.population_alignment_sha256
        ),
        "endpoint_time_frames_equal": (
            left.endpoint_time_frame == right.endpoint_time_frame
        ),
        "treatment_phases_equal": (
            left.treatment_phase is not None
            and left.treatment_phase == right.treatment_phase
        ),
        "shared_safety_unit": left.safety_unit_id == right.safety_unit_id,
        "safety_time_frames_equal": (
            left.safety_time_frame == right.safety_time_frame
        ),
        "shared_source_content_hashes": shared_sources,
        "source_overlap_status": source_overlap_status,
        "diagnostic_codes": tuple(sorted(diagnostic_codes)),
        "structural_status": structural_status,
    }


@dataclass(frozen=True, slots=True)
class ClinicalBenefitRiskPairwiseStressCell(SerializableRecord):
    """One unordered pair of endpoint domains observed in the same trial."""

    pair_id: str
    trial_id: str
    left: ClinicalBenefitRiskEndpointStressContext
    right: ClinicalBenefitRiskEndpointStressContext
    shared_endpoint_record: bool
    shared_population_identity: bool
    shared_population_record: bool
    shared_population_alignment: bool
    endpoint_time_frames_equal: bool
    treatment_phases_equal: bool
    shared_safety_unit: bool
    safety_time_frames_equal: bool
    shared_source_content_hashes: tuple[str, ...]
    source_overlap_status: str
    diagnostic_codes: tuple[str, ...]
    structural_status: str
    clinical_comparability_inferred: bool = False
    safety_independence_inferred: bool = False

    def __post_init__(self) -> None:
        _require_sha256(self.pair_id, "pair_id")
        _require_text(self.trial_id, "trial_id")
        _require_instance(
            self.left,
            ClinicalBenefitRiskEndpointStressContext,
            "left",
        )
        _require_instance(
            self.right,
            ClinicalBenefitRiskEndpointStressContext,
            "right",
        )
        if self.left.trial_id != self.trial_id or self.right.trial_id != self.trial_id:
            raise ValueError("pair contexts must match the pair trial")
        left_key = (self.left.endpoint_family, self.left.synthesis_id)
        right_key = (self.right.endpoint_family, self.right.synthesis_id)
        if left_key >= right_key:
            raise ValueError("pair contexts must use canonical endpoint-domain order")
        if self.pair_id != _pair_id(self.left, self.right):
            raise ValueError("pair_id does not match endpoint-domain identities")
        shared_sources = _sorted_unique_text(
            self.shared_source_content_hashes,
            "shared_source_content_hashes",
        )
        for index, digest in enumerate(shared_sources):
            _require_sha256(digest, f"shared_source_content_hashes[{index}]")
        object.__setattr__(
            self,
            "shared_source_content_hashes",
            shared_sources,
        )
        diagnostic_codes = _sorted_unique_text(
            self.diagnostic_codes,
            "diagnostic_codes",
        )
        if any(code not in _DIAGNOSTIC_CODES for code in diagnostic_codes):
            raise ValueError("diagnostic_codes contains an unsupported value")
        object.__setattr__(self, "diagnostic_codes", diagnostic_codes)
        _require_text(self.source_overlap_status, "source_overlap_status")
        _require_text(self.structural_status, "structural_status")
        facts = _pair_facts(self.left, self.right)
        for field_name in (
            "shared_endpoint_record",
            "shared_population_identity",
            "shared_population_record",
            "shared_population_alignment",
            "endpoint_time_frames_equal",
            "treatment_phases_equal",
            "shared_safety_unit",
            "safety_time_frames_equal",
            "clinical_comparability_inferred",
            "safety_independence_inferred",
        ):
            _require_bool(getattr(self, field_name), field_name)
        for field_name, expected in facts.items():
            if getattr(self, field_name) != expected:
                raise ValueError(f"{field_name} does not match pair contexts")
        if self.clinical_comparability_inferred:
            raise ValueError("clinical comparability cannot be inferred")
        if self.safety_independence_inferred:
            raise ValueError("safety independence cannot be inferred")


@dataclass(frozen=True, slots=True)
class ClinicalBenefitRiskPortfolioStressReport(SerializableRecord):
    """Aggregate same-trial pairwise stress report with fixed nonclaims."""

    stress_report_id: str
    portfolio_id: str
    program_id: str
    candidate_id: str
    intervention_id: str
    disease_id: str
    policy_id: str
    portfolio_spec_sha256: str
    portfolio_report_sha256: str
    state_sha256: str
    pairwise_cells: tuple[ClinicalBenefitRiskPairwiseStressCell, ...]
    same_trial_pair_count: int
    matched_structure_pair_count: int
    phase_undeclared_pair_count: int
    heterogeneous_structure_pair_count: int
    endpoint_record_reuse_pair_count: int
    population_identity_mismatch_pair_count: int
    population_record_mismatch_pair_count: int
    population_alignment_mismatch_pair_count: int
    endpoint_timeframe_mismatch_pair_count: int
    treatment_phase_partial_pair_count: int
    treatment_phase_mismatch_pair_count: int
    safety_unit_reuse_pair_count: int
    safety_identity_mismatch_pair_count: int
    safety_timeframe_mismatch_pair_count: int
    exact_source_overlap_pair_count: int
    partial_source_overlap_pair_count: int
    disjoint_source_pair_count: int
    full_state_replay_performed: bool
    shared_safety_counted_as_independent: bool
    clinical_comparability_inferred: bool
    endpoint_exchangeability_inferred: bool
    safety_independence_inferred: bool
    treatment_choice_inferred: bool
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        for field_name in (
            "stress_report_id",
            "portfolio_id",
            "program_id",
            "candidate_id",
            "intervention_id",
            "disease_id",
            "policy_id",
        ):
            _require_text(getattr(self, field_name), field_name)
        if self.policy_id != CLINICAL_BENEFIT_RISK_PORTFOLIO_STRESS_POLICY_ID:
            raise ValueError("unsupported portfolio stress policy_id")
        for field_name in (
            "portfolio_spec_sha256",
            "portfolio_report_sha256",
            "state_sha256",
        ):
            _require_sha256(getattr(self, field_name), field_name)
        cells = _tuple(self.pairwise_cells, "pairwise_cells")
        object.__setattr__(self, "pairwise_cells", cells)
        if not cells:
            raise ValueError("stress report requires at least one same-trial pair")
        for cell in cells:
            _require_instance(
                cell,
                ClinicalBenefitRiskPairwiseStressCell,
                "pairwise_cells item",
            )
        expected_order = tuple(
            sorted(
                cells,
                key=lambda item: (
                    item.trial_id,
                    item.left.endpoint_family,
                    item.left.synthesis_id,
                    item.right.endpoint_family,
                    item.right.synthesis_id,
                ),
            )
        )
        if cells != expected_order:
            raise ValueError("pairwise_cells must use canonical order")
        if len({item.pair_id for item in cells}) != len(cells):
            raise ValueError("pairwise pair ids must be unique")
        count_fields = (
            "same_trial_pair_count",
            "matched_structure_pair_count",
            "phase_undeclared_pair_count",
            "heterogeneous_structure_pair_count",
            "endpoint_record_reuse_pair_count",
            "population_identity_mismatch_pair_count",
            "population_record_mismatch_pair_count",
            "population_alignment_mismatch_pair_count",
            "endpoint_timeframe_mismatch_pair_count",
            "treatment_phase_partial_pair_count",
            "treatment_phase_mismatch_pair_count",
            "safety_unit_reuse_pair_count",
            "safety_identity_mismatch_pair_count",
            "safety_timeframe_mismatch_pair_count",
            "exact_source_overlap_pair_count",
            "partial_source_overlap_pair_count",
            "disjoint_source_pair_count",
        )
        for field_name in count_fields:
            _require_non_negative_int(getattr(self, field_name), field_name)
        expected_counts = _stress_counts(cells)
        for field_name, expected in expected_counts.items():
            if getattr(self, field_name) != expected:
                raise ValueError(f"{field_name} does not match pairwise cells")
        for field_name in (
            "full_state_replay_performed",
            "shared_safety_counted_as_independent",
            "clinical_comparability_inferred",
            "endpoint_exchangeability_inferred",
            "safety_independence_inferred",
            "treatment_choice_inferred",
        ):
            _require_bool(getattr(self, field_name), field_name)
        if not self.full_state_replay_performed:
            raise ValueError("stress report requires full state replay")
        for field_name in (
            "shared_safety_counted_as_independent",
            "clinical_comparability_inferred",
            "endpoint_exchangeability_inferred",
            "safety_independence_inferred",
            "treatment_choice_inferred",
        ):
            if getattr(self, field_name):
                raise ValueError(f"{field_name} must remain false")
        limitations = _tuple(self.limitations, "limitations")
        object.__setattr__(self, "limitations", limitations)
        if limitations != _REQUIRED_LIMITATIONS:
            raise ValueError("portfolio stress limitations changed")

    @property
    def fingerprint(self) -> str:
        return _sha256(self)


def _stress_counts(
    cells: tuple[ClinicalBenefitRiskPairwiseStressCell, ...],
) -> dict[str, int]:
    def count_code(code: str) -> int:
        return sum(code in item.diagnostic_codes for item in cells)

    def count_status(status: str) -> int:
        return sum(item.structural_status == status for item in cells)

    def count_source(status: str) -> int:
        return sum(item.source_overlap_status == status for item in cells)

    return {
        "same_trial_pair_count": len(cells),
        "matched_structure_pair_count": count_status(MATCHED_STRUCTURE),
        "phase_undeclared_pair_count": count_status(PHASE_UNDECLARED),
        "heterogeneous_structure_pair_count": count_status(
            HETEROGENEOUS_STRUCTURE
        ),
        "endpoint_record_reuse_pair_count": count_code(ENDPOINT_RECORD_REUSED),
        "population_identity_mismatch_pair_count": count_code(
            POPULATION_IDENTITY_MISMATCH
        ),
        "population_record_mismatch_pair_count": count_code(
            POPULATION_RECORD_MISMATCH
        ),
        "population_alignment_mismatch_pair_count": count_code(
            POPULATION_ALIGNMENT_MISMATCH
        ),
        "endpoint_timeframe_mismatch_pair_count": count_code(
            ENDPOINT_TIMEFRAME_MISMATCH
        ),
        "treatment_phase_partial_pair_count": count_code(
            TREATMENT_PHASE_PARTIAL_DECLARATION
        ),
        "treatment_phase_mismatch_pair_count": count_code(
            TREATMENT_PHASE_MISMATCH
        ),
        "safety_unit_reuse_pair_count": sum(
            item.shared_safety_unit for item in cells
        ),
        "safety_identity_mismatch_pair_count": count_code(
            SAFETY_RECORD_IDENTITY_MISMATCH
        ),
        "safety_timeframe_mismatch_pair_count": count_code(
            SAFETY_TIMEFRAME_MISMATCH
        ),
        "exact_source_overlap_pair_count": count_source(EXACT_SOURCE_OVERLAP),
        "partial_source_overlap_pair_count": count_source(PARTIAL_SOURCE_OVERLAP),
        "disjoint_source_pair_count": count_source(DISJOINT_SOURCE_OVERLAP),
    }


def _endpoint_context(
    state: ProgramState,
    portfolio_report: ClinicalBenefitRiskPortfolioReport,
    domain: ClinicalBenefitRiskEndpointDomain,
    cell: ClinicalBenefitRiskEndpointCell,
) -> ClinicalBenefitRiskEndpointStressContext:
    design = state.trial_designs_by_id.get(cell.design_id)
    if design is None or design.trial_id != cell.trial_id:
        raise ClinicalBenefitRiskPortfolioStressError(
            "portfolio endpoint design is absent or rebound"
        )
    endpoints = tuple(
        item for item in design.endpoints if item.endpoint_id == cell.endpoint_id
    )
    if len(endpoints) != 1:
        raise ClinicalBenefitRiskPortfolioStressError(
            "portfolio endpoint record is missing or ambiguous"
        )
    endpoint = endpoints[0]
    populations = tuple(
        item
        for item in design.populations
        if item.population_id == endpoint.population_id
    )
    if len(populations) != 1:
        raise ClinicalBenefitRiskPortfolioStressError(
            "portfolio analysis population is missing or ambiguous"
        )
    population = populations[0]
    safety_by_id = {
        item.safety_unit_id: item for item in portfolio_report.safety_units
    }
    safety_unit = safety_by_id.get(cell.safety_unit_id)
    if safety_unit is None:
        raise ClinicalBenefitRiskPortfolioStressError(
            "portfolio safety unit is missing"
        )
    safety_records = tuple(
        item
        for item in design.safety_records
        if item.safety_id == safety_unit.safety_id
    )
    if len(safety_records) != 1:
        raise ClinicalBenefitRiskPortfolioStressError(
            "portfolio safety record is missing or ambiguous"
        )
    safety = safety_records[0]
    if endpoint.time_frame != cell.endpoint_time_frame:
        raise ClinicalBenefitRiskPortfolioStressError(
            "portfolio endpoint time frame is rebound"
        )
    if safety.time_frame != safety_unit.safety_time_frame:
        raise ClinicalBenefitRiskPortfolioStressError(
            "portfolio safety time frame is rebound"
        )
    try:
        alignment = validate_phase_bound_population_alignment(
            design,
            endpoint,
            safety,
        )
    except ClinicalPopulationAlignmentError as exc:
        raise ClinicalBenefitRiskPortfolioStressError(
            "portfolio population alignment failed replay"
        ) from exc
    return ClinicalBenefitRiskEndpointStressContext(
        synthesis_id=domain.synthesis_id,
        endpoint_family=domain.endpoint_family,
        trial_id=cell.trial_id,
        design_id=cell.design_id,
        endpoint_id=cell.endpoint_id,
        endpoint_fingerprint_sha256=cell.endpoint_fingerprint_sha256,
        population_id=population.population_id,
        population_record_sha256=_sha256(population),
        endpoint_time_frame=cell.endpoint_time_frame,
        treatment_phase=(
            alignment["treatment_phase"] if alignment is not None else None
        ),
        population_alignment_sha256=(
            _sha256(alignment) if alignment is not None else None
        ),
        safety_unit_id=safety_unit.safety_unit_id,
        safety_id=safety_unit.safety_id,
        safety_fingerprint_sha256=safety_unit.safety_fingerprint_sha256,
        safety_time_frame=safety_unit.safety_time_frame,
        source_content_hashes=cell.source_content_hashes,
    )


def _pair_cell(
    left: ClinicalBenefitRiskEndpointStressContext,
    right: ClinicalBenefitRiskEndpointStressContext,
) -> ClinicalBenefitRiskPairwiseStressCell:
    facts = _pair_facts(left, right)
    return ClinicalBenefitRiskPairwiseStressCell(
        pair_id=_pair_id(left, right),
        trial_id=left.trial_id,
        left=left,
        right=right,
        **facts,
        clinical_comparability_inferred=False,
        safety_independence_inferred=False,
    )


def compile_clinical_benefit_risk_portfolio_stress_report(
    state: ProgramState,
    portfolio_spec: ClinicalBenefitRiskPortfolioSpec,
    portfolio_report: ClinicalBenefitRiskPortfolioReport,
) -> ClinicalBenefitRiskPortfolioStressReport:
    """Replay every same-trial endpoint-domain pair and expose heterogeneity."""

    _require_instance(state, ProgramState, "state")
    _require_instance(
        portfolio_spec,
        ClinicalBenefitRiskPortfolioSpec,
        "portfolio_spec",
    )
    _require_instance(
        portfolio_report,
        ClinicalBenefitRiskPortfolioReport,
        "portfolio_report",
    )
    failures = validate_clinical_benefit_risk_portfolio(
        state,
        portfolio_spec,
        portfolio_report,
    )
    if failures:
        raise ClinicalBenefitRiskPortfolioStressError(
            "portfolio failed full-state recompilation"
        )
    contexts_by_trial: defaultdict[
        str, list[ClinicalBenefitRiskEndpointStressContext]
    ] = defaultdict(list)
    for domain in portfolio_report.endpoint_domains:
        for cell in domain.cells:
            contexts_by_trial[cell.trial_id].append(
                _endpoint_context(state, portfolio_report, domain, cell)
            )
    pairs: list[ClinicalBenefitRiskPairwiseStressCell] = []
    for trial_id, contexts in sorted(contexts_by_trial.items()):
        if len(contexts) < 2:
            continue
        ordered_contexts = sorted(
            contexts,
            key=lambda item: (item.endpoint_family, item.synthesis_id),
        )
        for left, right in combinations(ordered_contexts, 2):
            if left.trial_id != trial_id or right.trial_id != trial_id:
                raise ClinicalBenefitRiskPortfolioStressError(
                    "same-trial context grouping failed"
                )
            pairs.append(_pair_cell(left, right))
    ordered_pairs = tuple(
        sorted(
            pairs,
            key=lambda item: (
                item.trial_id,
                item.left.endpoint_family,
                item.left.synthesis_id,
                item.right.endpoint_family,
                item.right.synthesis_id,
            ),
        )
    )
    if not ordered_pairs:
        raise ClinicalBenefitRiskPortfolioStressError(
            "portfolio has no same-trial endpoint-domain pairs"
        )
    counts = _stress_counts(ordered_pairs)
    return ClinicalBenefitRiskPortfolioStressReport(
        stress_report_id=f"{portfolio_report.portfolio_id}:structural-stress:v1",
        portfolio_id=portfolio_report.portfolio_id,
        program_id=portfolio_report.program_id,
        candidate_id=portfolio_report.candidate_id,
        intervention_id=portfolio_report.intervention_id,
        disease_id=portfolio_report.disease_id,
        policy_id=CLINICAL_BENEFIT_RISK_PORTFOLIO_STRESS_POLICY_ID,
        portfolio_spec_sha256=portfolio_spec.fingerprint,
        portfolio_report_sha256=portfolio_report.fingerprint,
        state_sha256=portfolio_report.state_sha256,
        pairwise_cells=ordered_pairs,
        **counts,
        full_state_replay_performed=True,
        shared_safety_counted_as_independent=False,
        clinical_comparability_inferred=False,
        endpoint_exchangeability_inferred=False,
        safety_independence_inferred=False,
        treatment_choice_inferred=False,
        limitations=_REQUIRED_LIMITATIONS,
    )


def validate_clinical_benefit_risk_portfolio_stress_report(
    state: ProgramState,
    portfolio_spec: ClinicalBenefitRiskPortfolioSpec,
    portfolio_report: ClinicalBenefitRiskPortfolioReport,
    stress_report: ClinicalBenefitRiskPortfolioStressReport,
) -> tuple[str, ...]:
    """Recompile a structural stress report and return deterministic failures."""

    try:
        rebuilt = compile_clinical_benefit_risk_portfolio_stress_report(
            state,
            portfolio_spec,
            portfolio_report,
        )
    except (ClinicalBenefitRiskPortfolioStressError, TypeError, ValueError):
        return ("portfolio_stress_recompile_failed",)
    if rebuilt != stress_report:
        return ("portfolio_stress_recompiled_report_mismatch",)
    return ()


def clinical_benefit_risk_portfolio_stress_report_envelope(
    report: ClinicalBenefitRiskPortfolioStressReport,
) -> dict[str, Any]:
    """Return a strict integrity envelope for one stress report."""

    _require_instance(
        report,
        ClinicalBenefitRiskPortfolioStressReport,
        "report",
    )
    return {
        "schema_version": (
            CLINICAL_BENEFIT_RISK_PORTFOLIO_STRESS_REPORT_SCHEMA_VERSION
        ),
        "integrity_sha256": report.fingerprint,
        "report": to_primitive(report),
    }


def _context_from_dict(
    value: Any,
    path: str,
) -> ClinicalBenefitRiskEndpointStressContext:
    data = _record(
        value,
        path,
        _field_names(ClinicalBenefitRiskEndpointStressContext),
    )
    return ClinicalBenefitRiskEndpointStressContext(**data)


def _pair_from_dict(
    value: Any,
    path: str,
) -> ClinicalBenefitRiskPairwiseStressCell:
    data = _record(
        value,
        path,
        _field_names(ClinicalBenefitRiskPairwiseStressCell),
    )
    data["left"] = _context_from_dict(data["left"], f"{path}.left")
    data["right"] = _context_from_dict(data["right"], f"{path}.right")
    return ClinicalBenefitRiskPairwiseStressCell(**data)


def clinical_benefit_risk_portfolio_stress_report_from_dict(
    value: Any,
) -> ClinicalBenefitRiskPortfolioStressReport:
    """Parse and integrity-check one portfolio stress report envelope."""

    envelope = _record(
        value,
        "portfolio_stress_report_envelope",
        {"schema_version", "integrity_sha256", "report"},
    )
    if envelope["schema_version"] != (
        CLINICAL_BENEFIT_RISK_PORTFOLIO_STRESS_REPORT_SCHEMA_VERSION
    ):
        raise ClinicalBenefitRiskPortfolioStressError(
            "unsupported portfolio stress report schema"
        )
    _require_sha256(envelope["integrity_sha256"], "integrity_sha256")
    data = _record(
        envelope["report"],
        "portfolio_stress_report",
        _field_names(ClinicalBenefitRiskPortfolioStressReport),
    )
    data["pairwise_cells"] = tuple(
        _pair_from_dict(item, f"portfolio_stress_report.pairwise_cells[{index}]")
        for index, item in enumerate(
            _tuple(
                data["pairwise_cells"],
                "portfolio_stress_report.pairwise_cells",
            )
        )
    )
    report = ClinicalBenefitRiskPortfolioStressReport(**data)
    if report.fingerprint != envelope["integrity_sha256"]:
        raise ClinicalBenefitRiskPortfolioStressError(
            "portfolio stress report integrity mismatch"
        )
    return report


def clinical_benefit_risk_portfolio_stress_report_from_json(
    text: str,
) -> ClinicalBenefitRiskPortfolioStressReport:
    return clinical_benefit_risk_portfolio_stress_report_from_dict(
        _load_json(text)
    )


def clinical_benefit_risk_portfolio_stress_report_summary(
    report: ClinicalBenefitRiskPortfolioStressReport,
) -> dict[str, Any]:
    """Return a compact human- and machine-facing stress summary."""

    _require_instance(
        report,
        ClinicalBenefitRiskPortfolioStressReport,
        "report",
    )
    return {
        "stress_report_id": report.stress_report_id,
        "portfolio_id": report.portfolio_id,
        "same_trial_pair_count": report.same_trial_pair_count,
        "matched_structure_pair_count": report.matched_structure_pair_count,
        "phase_undeclared_pair_count": report.phase_undeclared_pair_count,
        "heterogeneous_structure_pair_count": (
            report.heterogeneous_structure_pair_count
        ),
        "endpoint_record_reuse_pair_count": (
            report.endpoint_record_reuse_pair_count
        ),
        "population_identity_mismatch_pair_count": (
            report.population_identity_mismatch_pair_count
        ),
        "population_alignment_mismatch_pair_count": (
            report.population_alignment_mismatch_pair_count
        ),
        "endpoint_timeframe_mismatch_pair_count": (
            report.endpoint_timeframe_mismatch_pair_count
        ),
        "safety_unit_reuse_pair_count": report.safety_unit_reuse_pair_count,
        "clinical_comparability_inferred": (
            report.clinical_comparability_inferred
        ),
        "safety_independence_inferred": report.safety_independence_inferred,
        "integrity_sha256": report.fingerprint,
    }
