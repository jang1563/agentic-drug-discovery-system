"""Shared ratio-effect semantics for clinical ingestion and synthesis."""

from __future__ import annotations


RATIO_EFFECT_FAVORABLE_DIRECTIONS = {
    "hazard_ratio": "lower_is_better",
    "odds_ratio": "higher_is_better",
    "risk_ratio": "higher_is_better",
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
}


def _normalized(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("effect text must be a non-empty string")
    return " ".join(value.casefold().split())


def canonical_ratio_effect_measure(parameter_type: str) -> str | None:
    """Resolve one supported registry parameter label to its canonical ratio measure."""

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


def ratio_benefit_direction(
    lower: float,
    upper: float,
    favorable_direction: str,
) -> str:
    """Classify a positive ratio interval without pooling or acceptability inference."""

    if not 0 < lower <= upper:
        raise ValueError("ratio confidence interval must be positive and ordered")
    if favorable_direction == "lower_is_better":
        if upper < 1.0:
            return "benefit"
        if lower > 1.0:
            return "harm"
    elif favorable_direction == "higher_is_better":
        if lower > 1.0:
            return "benefit"
        if upper < 1.0:
            return "harm"
    else:
        raise ValueError(f"unsupported favorable direction: {favorable_direction}")
    return "null_or_uncertain"
