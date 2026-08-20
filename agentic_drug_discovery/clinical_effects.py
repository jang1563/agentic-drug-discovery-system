"""Shared effect semantics for clinical ingestion and synthesis."""

from __future__ import annotations

import math


RATIO_EFFECT_FAVORABLE_DIRECTIONS = {
    "hazard_ratio": "lower_is_better",
    "odds_ratio": "higher_is_better",
    "risk_ratio": "higher_is_better",
}

EFFECT_MEASURE_NULL_VALUES = {
    **{effect_measure: 1.0 for effect_measure in RATIO_EFFECT_FAVORABLE_DIRECTIONS},
    "risk_difference": 0.0,
}

_PARAMETER_TYPE_ALIASES = {
    "hazard_ratio": {
        "cox proportional hazard",
        "hazard ratio",
        "hazard ratio (hr)",
        "hazard ratio, log",
    },
    "odds_ratio": {
        "odds ratio",
        "odds ratio (or)",
    },
    "risk_ratio": {
        "relative risk",
        "relative risk (rr)",
        "risk ratio",
        "risk ratio (rr)",
    },
    "risk_difference": {
        "adjusted risk difference (%)",
        "difference in percentage",
        "risk difference",
        "risk difference (rd)",
    },
}

_PERCENTAGE_POINT_MEASUREMENT_UNITS = {
    "%",
    "percent",
    "percentage",
    "percent of participants",
    "percentage of participants",
    "percent of patients",
    "percentage of patients",
    "percent of subjects",
    "percentage of subjects",
}


def _normalized(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("effect text must be a non-empty string")
    return " ".join(value.casefold().split())


def canonical_ratio_effect_measure(parameter_type: str) -> str | None:
    """Resolve one supported registry parameter label to its canonical ratio measure."""

    normalized = _normalized(parameter_type)
    for effect_measure, aliases in _PARAMETER_TYPE_ALIASES.items():
        if effect_measure not in RATIO_EFFECT_FAVORABLE_DIRECTIONS:
            continue
        if normalized in aliases:
            return effect_measure
    return None


def canonical_effect_measure(parameter_type: str) -> str | None:
    """Resolve a bounded registry label to one canonical effect measure."""

    normalized = _normalized(parameter_type)
    for effect_measure, aliases in _PARAMETER_TYPE_ALIASES.items():
        if normalized in aliases:
            return effect_measure
    return None


def ratio_effect_favorable_direction(effect_measure: str) -> str:
    """Return the only supported favorable direction for a canonical ratio measure."""

    normalized = _normalized(effect_measure).replace(" ", "_")
    try:
        return RATIO_EFFECT_FAVORABLE_DIRECTIONS[normalized]
    except KeyError as exc:
        raise ValueError(f"unsupported ratio effect measure: {effect_measure}") from exc


def effect_favorable_direction(
    effect_measure: str,
    endpoint_favorable_direction: str | None = None,
) -> str:
    """Resolve effect direction, using endpoint direction only for differences."""

    normalized = _normalized(effect_measure).replace(" ", "_")
    if normalized in RATIO_EFFECT_FAVORABLE_DIRECTIONS:
        return ratio_effect_favorable_direction(normalized)
    if normalized == "risk_difference":
        if endpoint_favorable_direction not in {
            "higher_is_better",
            "lower_is_better",
        }:
            raise ValueError(
                "risk_difference requires a declared endpoint favorable direction"
            )
        return endpoint_favorable_direction
    raise ValueError(f"unsupported effect measure: {effect_measure}")


def validate_ratio_effect_contract(
    effect_measure: str,
    favorable_direction: str,
) -> None:
    """Reject unsupported measures and direction reversals."""

    expected = ratio_effect_favorable_direction(effect_measure)
    if favorable_direction != expected:
        raise ValueError(
            f"{effect_measure} requires {expected} favorable direction"
        )


def validate_effect_contract(
    effect_measure: str,
    favorable_direction: str,
) -> None:
    """Reject unsupported measures and incompatible endpoint directions."""

    normalized = _normalized(effect_measure).replace(" ", "_")
    if normalized in RATIO_EFFECT_FAVORABLE_DIRECTIONS:
        validate_ratio_effect_contract(normalized, favorable_direction)
        return
    if normalized == "risk_difference":
        if favorable_direction not in {"higher_is_better", "lower_is_better"}:
            raise ValueError(
                "risk_difference requires higher_is_better or lower_is_better "
                "favorable direction"
            )
        return
    raise ValueError(f"unsupported effect measure: {effect_measure}")


def validate_effect_interval(
    estimate: float,
    lower: float,
    upper: float,
    effect_measure: str,
) -> None:
    """Validate an estimate and interval on its declared effect scale."""

    _validate_effect_interval_bounds(lower, upper, effect_measure)
    if (
        not isinstance(estimate, (int, float))
        or isinstance(estimate, bool)
        or not math.isfinite(float(estimate))
    ):
        raise ValueError("effect estimate and confidence interval must be finite")
    if not lower <= estimate <= upper:
        raise ValueError("confidence interval must contain the effect estimate")


def _validate_effect_interval_bounds(
    lower: float,
    upper: float,
    effect_measure: str,
) -> None:
    """Validate ordered finite confidence bounds on the declared effect scale."""

    values = (lower, upper)
    if any(
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(float(value))
        for value in values
    ):
        raise ValueError("effect estimate and confidence interval must be finite")
    if lower > upper:
        raise ValueError("confidence interval bounds must be ordered")
    normalized = _normalized(effect_measure).replace(" ", "_")
    if normalized in RATIO_EFFECT_FAVORABLE_DIRECTIONS:
        if lower <= 0:
            raise ValueError("ratio confidence interval must be positive")
        return
    if normalized != "risk_difference":
        raise ValueError(f"unsupported effect measure: {effect_measure}")


def validate_effect_measure_unit(
    effect_measure: str,
    measurement_unit: str,
) -> None:
    """Require an explicit percentage scale for supported risk differences."""

    normalized = _normalized(effect_measure).replace(" ", "_")
    if normalized not in EFFECT_MEASURE_NULL_VALUES:
        raise ValueError(f"unsupported effect measure: {effect_measure}")
    if (
        normalized == "risk_difference"
        and _normalized(measurement_unit) not in _PERCENTAGE_POINT_MEASUREMENT_UNITS
    ):
        raise ValueError(
            "risk_difference requires a bounded percentage-of-participants "
            "measurement unit"
        )


def effect_benefit_direction(
    lower: float,
    upper: float,
    effect_measure: str,
    favorable_direction: str,
) -> str:
    """Classify an interval against the measure-specific null value."""

    validate_effect_contract(effect_measure, favorable_direction)
    _validate_effect_interval_bounds(lower, upper, effect_measure)
    normalized = _normalized(effect_measure).replace(" ", "_")
    null_value = EFFECT_MEASURE_NULL_VALUES[normalized]
    if favorable_direction == "lower_is_better":
        if upper < null_value:
            return "benefit"
        if lower > null_value:
            return "harm"
    else:
        if lower > null_value:
            return "benefit"
        if upper < null_value:
            return "harm"
    return "null_or_uncertain"


def ratio_benefit_direction(
    lower: float,
    upper: float,
    favorable_direction: str,
) -> str:
    """Classify a positive ratio interval without pooling or acceptability inference."""

    if favorable_direction not in {"higher_is_better", "lower_is_better"}:
        raise ValueError(f"unsupported favorable direction: {favorable_direction}")
    return effect_benefit_direction(
        lower,
        upper,
        "hazard_ratio" if favorable_direction == "lower_is_better" else "odds_ratio",
        favorable_direction,
    )
