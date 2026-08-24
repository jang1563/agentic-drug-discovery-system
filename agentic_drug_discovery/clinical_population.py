"""Phase-bound clinical endpoint and safety population validation."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


TREATMENT_PHASES = frozenset({"induction", "maintenance", "not_applicable"})
POPULATION_ALIGNMENT_FIELDS = frozenset(
    {
        "treatment_phase",
        "study_enrollment_count",
        "endpoint_analysis_participant_count",
        "safety_at_risk_participant_count",
        "rolewise_counts_match",
        "same_participants_inferred",
    }
)


class ClinicalPopulationAlignmentError(ValueError):
    """Raised when endpoint, population, and safety phase identities diverge."""


def _attributes(value: Any, label: str) -> Mapping[str, Any]:
    attributes = getattr(value, "attributes", None)
    if not isinstance(attributes, Mapping):
        raise ClinicalPopulationAlignmentError(f"{label} attributes are invalid")
    return attributes


def _positive_int(value: Any, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ClinicalPopulationAlignmentError(f"{label} must be a positive integer")
    return value


def validate_phase_bound_population_alignment(
    design: Any,
    endpoint: Any,
    safety: Any,
) -> dict[str, Any] | None:
    """Recompute one provider-derived phase/population alignment contract.

    Legacy records without any phase metadata remain valid. Once any phase is
    declared, every linked design layer must carry the same exact alignment.
    """

    design_attributes = _attributes(design, "design")
    endpoint_attributes = _attributes(endpoint, "endpoint")
    safety_attributes = _attributes(safety, "safety")
    population_matches = tuple(
        item
        for item in getattr(design, "populations", ())
        if getattr(item, "population_id", None)
        == getattr(endpoint, "population_id", None)
    )
    if len(population_matches) != 1:
        raise ClinicalPopulationAlignmentError(
            "endpoint population identity is missing or ambiguous"
        )
    population = population_matches[0]
    population_attributes = _attributes(population, "population")

    phase_values = (
        design_attributes.get("treatment_phase"),
        population_attributes.get("treatment_phase"),
        endpoint_attributes.get("treatment_phase"),
        safety_attributes.get("treatment_phase"),
    )
    alignment_values = (
        design_attributes.get("population_alignment"),
        population_attributes.get("population_alignment"),
        endpoint_attributes.get("population_alignment"),
        safety_attributes.get("population_alignment"),
    )
    if all(value is None for value in (*phase_values, *alignment_values)):
        return None
    if any(value is None for value in (*phase_values, *alignment_values)):
        raise ClinicalPopulationAlignmentError(
            "phase-bound design layers must all carry population alignment"
        )

    phase = phase_values[0]
    if phase not in TREATMENT_PHASES or any(value != phase for value in phase_values):
        raise ClinicalPopulationAlignmentError(
            "design, population, endpoint, and safety treatment phases must match"
        )
    if any(not isinstance(value, Mapping) for value in alignment_values):
        raise ClinicalPopulationAlignmentError("population alignment must be an object")
    alignment = dict(alignment_values[0])
    if any(dict(value) != alignment for value in alignment_values[1:]):
        raise ClinicalPopulationAlignmentError(
            "design layers carry different population alignments"
        )
    if set(alignment) != POPULATION_ALIGNMENT_FIELDS:
        raise ClinicalPopulationAlignmentError(
            "population alignment has unsupported fields"
        )

    endpoint_counts: dict[str, int] = {}
    endpoint_arm_ids = set(getattr(endpoint, "arm_ids", ()))
    for arm in getattr(design, "arms", ()):
        if getattr(arm, "arm_id", None) not in endpoint_arm_ids:
            continue
        role = getattr(getattr(arm, "role", None), "value", None)
        measurement = _attributes(arm, "arm").get("measurement")
        if role not in {"candidate", "comparator"} or not isinstance(
            measurement, Mapping
        ):
            raise ClinicalPopulationAlignmentError(
                "endpoint arm role or measurement is invalid"
            )
        endpoint_counts[role] = _positive_int(
            measurement.get("denominator"), f"{role} endpoint denominator"
        )
    safety_counts = {
        getattr(getattr(item, "role", None), "value", None): _positive_int(
            getattr(item, "serious_num_at_risk", None),
            "safety at-risk count",
        )
        for item in getattr(safety, "arm_summaries", ())
    }
    if set(endpoint_counts) != {"candidate", "comparator"} or set(safety_counts) != {
        "candidate",
        "comparator",
    }:
        raise ClinicalPopulationAlignmentError(
            "population alignment requires candidate and comparator counts"
        )
    expected = {
        "treatment_phase": phase,
        "study_enrollment_count": _positive_int(
            getattr(population, "enrollment_count", None), "study enrollment count"
        ),
        "endpoint_analysis_participant_count": sum(endpoint_counts.values()),
        "safety_at_risk_participant_count": sum(safety_counts.values()),
        "rolewise_counts_match": endpoint_counts == safety_counts,
        "same_participants_inferred": False,
    }
    if alignment != expected:
        raise ClinicalPopulationAlignmentError(
            "population alignment does not match committed endpoint and safety counts"
        )
    return alignment
