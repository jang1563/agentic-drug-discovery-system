"""Strict extraction of one posted ClinicalTrials.gov endpoint and safety summary."""

from __future__ import annotations

import hashlib
import json
import math
import re
import urllib.parse
from collections.abc import Mapping, Sequence
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from .ingestion import (
    INGESTION_JOB_SCHEMA_VERSION,
    SourceBundle,
    normalize_pinned_ingestion_job,
    verify_source_payload,
)


CLINICALTRIALS_GOV_JOB_SCHEMA_VERSION = (
    "adds.clinicaltrials-gov-ingestion-job.v2"
)
CLINICALTRIALS_GOV_PROVIDER_ID = "clinicaltrials_gov"

_JOB_FIELDS = frozenset(
    {"schema_version", "job_id", "source_receipt_id", "trial", "record"}
)
_TRIAL_FIELDS = frozenset(
    {
        "nct_id",
        "registry_version",
        "candidate_id",
        "candidate_name",
        "candidate_aliases",
        "intervention_id",
        "disease_id",
        "disease_name",
        "condition",
        "study_type",
        "phase",
        "overall_status",
        "arms",
        "population",
        "endpoint",
        "safety",
    }
)
_ARM_FIELDS = frozenset(
    {
        "arm_id",
        "role",
        "protocol_arm_label",
        "protocol_arm_type",
        "source_group_id",
        "source_group_title",
        "intervention_id",
        "intervention_names",
        "measurement",
    }
)
_MEASUREMENT_FIELDS = frozenset({"value", "denominator"})
_POPULATION_FIELDS = frozenset(
    {
        "population_id",
        "description",
        "enrollment_count",
        "enrollment_type",
        "sex",
        "minimum_age",
        "maximum_age",
        "healthy_volunteers",
    }
)
_ENDPOINT_FIELDS = frozenset(
    {
        "endpoint_id",
        "outcome_index",
        "analysis_index",
        "name",
        "outcome_type",
        "time_frame",
        "parameter_type",
        "unit",
        "reporting_status",
        "favorable_direction",
        "analysis",
    }
)
_ANALYSIS_FIELDS = frozenset(
    {
        "source_group_ids",
        "p_value_relation",
        "p_value",
        "statistical_method",
        "parameter_type",
        "parameter_value",
        "confidence_interval_percent",
        "confidence_interval_lower",
        "confidence_interval_upper",
    }
)
_SAFETY_FIELDS = frozenset(
    {
        "safety_id",
        "event_category",
        "reporting_status",
        "time_frame",
        "description",
        "event_term_count",
        "arms",
    }
)
_SAFETY_ARM_FIELDS = frozenset(
    {
        "safety_arm_id",
        "arm_id",
        "role",
        "source_group_id",
        "source_group_title",
        "serious_num_affected",
        "serious_num_at_risk",
    }
)
_RECORD_FIELDS = frozenset(
    {
        "record_id",
        "observed_at",
        "available_at",
        "confidence",
    }
)
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,191}$")
_NCT_ID = re.compile(r"^NCT[0-9]{8}$")
_RESULT_GROUP_ID = re.compile(r"^OG[0-9]{3,}$")
_ADVERSE_EVENT_GROUP_ID = re.compile(r"^EG[0-9]{3,}$")
_P_VALUE = re.compile(
    r"^\s*(?P<relation><=|>=|<|>|=)?\s*(?P<value>[0-9]+(?:\.[0-9]+)?)\s*$"
)
_RELATION = {"<": "lt", "<=": "le", "=": "eq", ">=": "ge", ">": "gt"}


def _mapping(value: Any, field_name: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field_name} must be an object")
    return dict(value)


def _sequence(value: Any, field_name: str) -> list[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"{field_name} must be an array")
    return list(value)


def _text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


def _safe_id(value: Any, field_name: str) -> str:
    result = _text(value, field_name)
    if _SAFE_ID.fullmatch(result) is None:
        raise ValueError(f"{field_name} contains unsupported characters")
    return result


def _positive_int(value: Any, field_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"{field_name} must be a positive integer")
    return value


def _non_negative_int(value: Any, field_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")
    return value


def _probability(value: Any, field_name: str) -> float:
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(float(value))
        or not 0 <= float(value) <= 1
    ):
        raise ValueError(f"{field_name} must be between zero and one")
    return float(value)


def _decimal(value: Any, field_name: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise ValueError(f"{field_name} must be a finite decimal")
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError(f"{field_name} must be a finite decimal") from exc
    if not result.is_finite():
        raise ValueError(f"{field_name} must be a finite decimal")
    return result


def _iso_date(value: Any, field_name: str) -> date:
    text = _text(value, field_name)
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be an ISO 8601 calendar date") from exc


def _normalized(value: str) -> str:
    return " ".join(value.casefold().split())


def _text_list(value: Any, field_name: str) -> list[str]:
    result = [
        _text(item, f"{field_name}[{index}]")
        for index, item in enumerate(_sequence(value, field_name))
    ]
    if not result or len(result) > 32:
        raise ValueError(f"{field_name} must contain 1-32 strings")
    normalized = [_normalized(item) for item in result]
    if len(normalized) != len(set(normalized)):
        raise ValueError(f"{field_name} must not contain duplicate values")
    return result


def _exact_fields(value: Mapping[str, Any], expected: frozenset[str], label: str) -> None:
    if set(value) != expected:
        raise ValueError(f"{label} must contain exactly {sorted(expected)}")


def _normalize_measurement(value: Any, field_name: str) -> dict[str, Any]:
    measurement = _mapping(value, field_name)
    _exact_fields(measurement, _MEASUREMENT_FIELDS, field_name)
    return {
        "value": _text(measurement["value"], f"{field_name}.value"),
        "denominator": _positive_int(
            measurement["denominator"], f"{field_name}.denominator"
        ),
    }


def _normalize_arm(value: Any, index: int) -> dict[str, Any]:
    label = f"job.trial.arms[{index}]"
    arm = _mapping(value, label)
    _exact_fields(arm, _ARM_FIELDS, label)
    role = _text(arm["role"], f"{label}.role").casefold()
    if role not in {"candidate", "comparator"}:
        raise ValueError(f"{label}.role must be candidate or comparator")
    intervention_id = arm["intervention_id"]
    if role == "candidate":
        intervention_id = _safe_id(intervention_id, f"{label}.intervention_id")
    elif intervention_id is not None:
        raise ValueError(f"{label}.intervention_id must be null for comparator")
    source_group_id = _text(arm["source_group_id"], f"{label}.source_group_id")
    if _RESULT_GROUP_ID.fullmatch(source_group_id) is None:
        raise ValueError(f"{label}.source_group_id is not a result group id")
    return {
        "arm_id": _safe_id(arm["arm_id"], f"{label}.arm_id"),
        "role": role,
        "protocol_arm_label": _text(
            arm["protocol_arm_label"], f"{label}.protocol_arm_label"
        ),
        "protocol_arm_type": _text(
            arm["protocol_arm_type"], f"{label}.protocol_arm_type"
        ),
        "source_group_id": source_group_id,
        "source_group_title": _text(
            arm["source_group_title"], f"{label}.source_group_title"
        ),
        "intervention_id": intervention_id,
        "intervention_names": _text_list(
            arm["intervention_names"], f"{label}.intervention_names"
        ),
        "measurement": _normalize_measurement(
            arm["measurement"], f"{label}.measurement"
        ),
    }


def _normalize_population(value: Any) -> dict[str, Any]:
    population = _mapping(value, "job.trial.population")
    _exact_fields(population, _POPULATION_FIELDS, "job.trial.population")
    maximum_age = population["maximum_age"]
    if maximum_age is not None:
        maximum_age = _text(maximum_age, "job.trial.population.maximum_age")
    healthy = population["healthy_volunteers"]
    if not isinstance(healthy, bool):
        raise ValueError("job.trial.population.healthy_volunteers must be boolean")
    return {
        "population_id": _safe_id(
            population["population_id"], "job.trial.population.population_id"
        ),
        "description": _text(
            population["description"], "job.trial.population.description"
        ),
        "enrollment_count": _positive_int(
            population["enrollment_count"],
            "job.trial.population.enrollment_count",
        ),
        "enrollment_type": _text(
            population["enrollment_type"],
            "job.trial.population.enrollment_type",
        ),
        "sex": _text(population["sex"], "job.trial.population.sex"),
        "minimum_age": _text(
            population["minimum_age"], "job.trial.population.minimum_age"
        ),
        "maximum_age": maximum_age,
        "healthy_volunteers": healthy,
    }


def _normalize_analysis(value: Any) -> dict[str, Any]:
    analysis = _mapping(value, "job.trial.endpoint.analysis")
    _exact_fields(analysis, _ANALYSIS_FIELDS, "job.trial.endpoint.analysis")
    relation = _text(
        analysis["p_value_relation"],
        "job.trial.endpoint.analysis.p_value_relation",
    ).casefold()
    if relation not in {"lt", "le", "eq", "ge", "gt"}:
        raise ValueError("job.trial.endpoint.analysis p-value relation is unsupported")
    return {
        "source_group_ids": _text_list(
            analysis["source_group_ids"],
            "job.trial.endpoint.analysis.source_group_ids",
        ),
        "p_value_relation": relation,
        "p_value": float(
            _decimal(analysis["p_value"], "job.trial.endpoint.analysis.p_value")
        ),
        "statistical_method": _text(
            analysis["statistical_method"],
            "job.trial.endpoint.analysis.statistical_method",
        ),
        "parameter_type": _text(
            analysis["parameter_type"],
            "job.trial.endpoint.analysis.parameter_type",
        ),
        "parameter_value": float(
            _decimal(
                analysis["parameter_value"],
                "job.trial.endpoint.analysis.parameter_value",
            )
        ),
        "confidence_interval_percent": float(
            _decimal(
                analysis["confidence_interval_percent"],
                "job.trial.endpoint.analysis.confidence_interval_percent",
            )
        ),
        "confidence_interval_lower": float(
            _decimal(
                analysis["confidence_interval_lower"],
                "job.trial.endpoint.analysis.confidence_interval_lower",
            )
        ),
        "confidence_interval_upper": float(
            _decimal(
                analysis["confidence_interval_upper"],
                "job.trial.endpoint.analysis.confidence_interval_upper",
            )
        ),
    }


def _normalize_endpoint(value: Any) -> dict[str, Any]:
    endpoint = _mapping(value, "job.trial.endpoint")
    _exact_fields(endpoint, _ENDPOINT_FIELDS, "job.trial.endpoint")
    favorable = _text(
        endpoint["favorable_direction"],
        "job.trial.endpoint.favorable_direction",
    ).casefold()
    if favorable != "higher_is_better":
        raise ValueError("v1 supports only higher_is_better posted endpoints")
    return {
        "endpoint_id": _safe_id(
            endpoint["endpoint_id"], "job.trial.endpoint.endpoint_id"
        ),
        "outcome_index": _non_negative_int(
            endpoint["outcome_index"], "job.trial.endpoint.outcome_index"
        ),
        "analysis_index": _non_negative_int(
            endpoint["analysis_index"], "job.trial.endpoint.analysis_index"
        ),
        "name": _text(endpoint["name"], "job.trial.endpoint.name"),
        "outcome_type": _text(
            endpoint["outcome_type"], "job.trial.endpoint.outcome_type"
        ),
        "time_frame": _text(
            endpoint["time_frame"], "job.trial.endpoint.time_frame"
        ),
        "parameter_type": _text(
            endpoint["parameter_type"], "job.trial.endpoint.parameter_type"
        ),
        "unit": _text(endpoint["unit"], "job.trial.endpoint.unit"),
        "reporting_status": _text(
            endpoint["reporting_status"], "job.trial.endpoint.reporting_status"
        ),
        "favorable_direction": favorable,
        "analysis": _normalize_analysis(endpoint["analysis"]),
    }


def _normalize_safety_arm(value: Any, index: int) -> dict[str, Any]:
    label = f"job.trial.safety.arms[{index}]"
    arm = _mapping(value, label)
    _exact_fields(arm, _SAFETY_ARM_FIELDS, label)
    role = _text(arm["role"], f"{label}.role").casefold()
    if role not in {"candidate", "comparator"}:
        raise ValueError(f"{label}.role must be candidate or comparator")
    source_group_id = _text(arm["source_group_id"], f"{label}.source_group_id")
    if _ADVERSE_EVENT_GROUP_ID.fullmatch(source_group_id) is None:
        raise ValueError(f"{label}.source_group_id is not an adverse-event group id")
    affected = _non_negative_int(
        arm["serious_num_affected"], f"{label}.serious_num_affected"
    )
    at_risk = _positive_int(
        arm["serious_num_at_risk"], f"{label}.serious_num_at_risk"
    )
    if affected > at_risk:
        raise ValueError(f"{label} affected count cannot exceed at-risk count")
    return {
        "safety_arm_id": _safe_id(arm["safety_arm_id"], f"{label}.safety_arm_id"),
        "arm_id": _safe_id(arm["arm_id"], f"{label}.arm_id"),
        "role": role,
        "source_group_id": source_group_id,
        "source_group_title": _text(
            arm["source_group_title"], f"{label}.source_group_title"
        ),
        "serious_num_affected": affected,
        "serious_num_at_risk": at_risk,
    }


def _normalize_safety(value: Any, arms: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    safety = _mapping(value, "job.trial.safety")
    _exact_fields(safety, _SAFETY_FIELDS, "job.trial.safety")
    safety_id = _safe_id(safety["safety_id"], "job.trial.safety.safety_id")
    event_category = _text(
        safety["event_category"], "job.trial.safety.event_category"
    ).upper()
    if event_category != "SERIOUS":
        raise ValueError("job.trial.safety.event_category must be SERIOUS")
    reporting_status = _text(
        safety["reporting_status"], "job.trial.safety.reporting_status"
    ).upper()
    if reporting_status != "POSTED":
        raise ValueError("job.trial.safety.reporting_status must be POSTED")
    description = safety["description"]
    if description is not None:
        description = _text(description, "job.trial.safety.description")
    safety_arms = [
        _normalize_safety_arm(item, index)
        for index, item in enumerate(
            _sequence(safety["arms"], "job.trial.safety.arms")
        )
    ]
    if len(safety_arms) != 2:
        raise ValueError("job.trial.safety.arms must contain exactly two selected arms")
    if {item["role"] for item in safety_arms} != {"candidate", "comparator"}:
        raise ValueError(
            "job.trial.safety.arms must contain candidate and comparator roles"
        )
    for field_name in ("safety_arm_id", "arm_id", "source_group_id"):
        if len({item[field_name] for item in safety_arms}) != 2:
            raise ValueError(f"job.trial.safety.arms {field_name} values must be unique")
    canonical_arms = {item["arm_id"]: item for item in arms}
    if [item["arm_id"] for item in safety_arms] != [item["arm_id"] for item in arms]:
        raise ValueError("safety arm order must match the selected endpoint arms")
    for item in safety_arms:
        canonical = canonical_arms.get(item["arm_id"])
        if (
            canonical is None
            or canonical["role"] != item["role"]
            or item["safety_arm_id"]
            != f"{safety_id}:arm:{item['source_group_id']}"
            or _normalized(canonical["source_group_title"])
            != _normalized(item["source_group_title"])
        ):
            raise ValueError("safety arm mapping conflicts with the selected design arm")
    return {
        "safety_id": safety_id,
        "event_category": event_category,
        "reporting_status": reporting_status,
        "time_frame": _text(safety["time_frame"], "job.trial.safety.time_frame"),
        "description": description,
        "event_term_count": _non_negative_int(
            safety["event_term_count"], "job.trial.safety.event_term_count"
        ),
        "arms": safety_arms,
    }


def _normalize_trial(value: Any) -> dict[str, Any]:
    trial = _mapping(value, "job.trial")
    _exact_fields(trial, _TRIAL_FIELDS, "job.trial")
    nct_id = _text(trial["nct_id"], "job.trial.nct_id").upper()
    if _NCT_ID.fullmatch(nct_id) is None:
        raise ValueError("job.trial.nct_id must be a canonical NCT identifier")
    registry_version = _iso_date(
        trial["registry_version"], "job.trial.registry_version"
    ).isoformat()
    arms = [_normalize_arm(item, index) for index, item in enumerate(_sequence(trial["arms"], "job.trial.arms"))]
    if len(arms) != 2:
        raise ValueError("job.trial.arms must contain exactly two selected arms")
    if {item["role"] for item in arms} != {"candidate", "comparator"}:
        raise ValueError("job.trial.arms must contain candidate and comparator roles")
    if len({item["arm_id"] for item in arms}) != 2 or len(
        {item["source_group_id"] for item in arms}
    ) != 2:
        raise ValueError("job.trial.arms identifiers must be unique")
    candidate_id = _safe_id(trial["candidate_id"], "job.trial.candidate_id")
    intervention_id = _safe_id(
        trial["intervention_id"], "job.trial.intervention_id"
    )
    candidate_arm = next(item for item in arms if item["role"] == "candidate")
    if candidate_arm["intervention_id"] != intervention_id:
        raise ValueError("candidate arm must link job.trial.intervention_id")
    population = _normalize_population(trial["population"])
    endpoint = _normalize_endpoint(trial["endpoint"])
    if endpoint["analysis"]["source_group_ids"] != [
        item["source_group_id"] for item in arms
    ]:
        raise ValueError("endpoint analysis group order must match selected arms")
    aliases = _text_list(trial["candidate_aliases"], "job.trial.candidate_aliases")
    candidate_name = _text(trial["candidate_name"], "job.trial.candidate_name")
    if _normalized(candidate_name) not in {_normalized(item) for item in aliases}:
        raise ValueError("candidate_aliases must include candidate_name")
    safety = _normalize_safety(trial["safety"], arms)
    expected_safety_id = f"{nct_id}:safety:serious-adverse-events"
    if safety["safety_id"] != expected_safety_id:
        raise ValueError("job.trial.safety.safety_id is not canonical")
    return {
        "nct_id": nct_id,
        "registry_version": registry_version,
        "candidate_id": candidate_id,
        "candidate_name": candidate_name,
        "candidate_aliases": aliases,
        "intervention_id": intervention_id,
        "disease_id": _safe_id(trial["disease_id"], "job.trial.disease_id"),
        "disease_name": _text(trial["disease_name"], "job.trial.disease_name"),
        "condition": _text(trial["condition"], "job.trial.condition"),
        "study_type": _text(trial["study_type"], "job.trial.study_type"),
        "phase": _text(trial["phase"], "job.trial.phase"),
        "overall_status": _text(
            trial["overall_status"], "job.trial.overall_status"
        ),
        "arms": arms,
        "population": population,
        "endpoint": endpoint,
        "safety": safety,
    }


def normalize_clinicaltrials_gov_ingestion_job(value: Any) -> dict[str, Any]:
    """Validate one reviewer-authored ClinicalTrials.gov extraction job."""

    job = _mapping(value, "job")
    _exact_fields(job, _JOB_FIELDS, "job")
    if job["schema_version"] != CLINICALTRIALS_GOV_JOB_SCHEMA_VERSION:
        raise ValueError(
            f"schema_version must be {CLINICALTRIALS_GOV_JOB_SCHEMA_VERSION}"
        )
    trial = _normalize_trial(job["trial"])
    record = _mapping(job["record"], "job.record")
    _exact_fields(record, _RECORD_FIELDS, "job.record")
    observed_at = _iso_date(record["observed_at"], "job.record.observed_at")
    available_at = _iso_date(record["available_at"], "job.record.available_at")
    if available_at < observed_at:
        raise ValueError("job.record.available_at cannot precede observed_at")
    normalized = {
        "schema_version": CLINICALTRIALS_GOV_JOB_SCHEMA_VERSION,
        "job_id": _safe_id(job["job_id"], "job.job_id"),
        "source_receipt_id": _safe_id(
            job["source_receipt_id"], "job.source_receipt_id"
        ),
        "trial": trial,
        "record": {
            "record_id": _safe_id(record["record_id"], "job.record.record_id"),
            "observed_at": observed_at.isoformat(),
            "available_at": available_at.isoformat(),
            "confidence": _probability(record["confidence"], "job.record.confidence"),
        },
    }
    _generic_job(normalized, linked_receipt=None)
    return normalized


def _generic_job(
    job: Mapping[str, Any],
    *,
    linked_receipt: Mapping[str, Any] | None,
) -> dict[str, Any]:
    trial = job["trial"]
    endpoint = trial["endpoint"]
    safety = trial["safety"]
    arms = [
        {
            "arm_id": item["arm_id"],
            "source_group_id": item["source_group_id"],
            "label": item["source_group_title"],
            "arm_type": item["protocol_arm_type"],
            "role": item["role"],
            "intervention_id": item["intervention_id"],
            "intervention_names": item["intervention_names"],
            "measurement": item["measurement"],
        }
        for item in trial["arms"]
    ]
    population = dict(trial["population"])
    population["description_sha256"] = hashlib.sha256(
        population["description"].encode("utf-8")
    ).hexdigest()
    metadata = {
        "provider_id": CLINICALTRIALS_GOV_PROVIDER_ID,
        "registry": "ClinicalTrials.gov",
        "registry_version": trial["registry_version"],
        "study_type": trial["study_type"],
        "overall_status": trial["overall_status"],
        "phase": trial["phase"],
        "effect_direction": "benefit",
        "candidate_aliases": trial["candidate_aliases"],
        "source_interventions": sorted(
            {
                name
                for arm in trial["arms"]
                for name in arm["intervention_names"]
            }
        ),
        "source_conditions": [trial["condition"]],
        "source_lineage_ids": [f"clinicaltrials-gov:{trial['nct_id']}"],
        "arms": arms,
        "population": population,
        "endpoint": {
            "endpoint_id": endpoint["endpoint_id"],
            "outcome_index": endpoint["outcome_index"],
            "analysis_index": endpoint["analysis_index"],
            "population_id": population["population_id"],
            "name": endpoint["name"],
            "outcome_type": endpoint["outcome_type"],
            "time_frame": endpoint["time_frame"],
            "parameter_type": endpoint["parameter_type"],
            "unit": endpoint["unit"],
            "reporting_status": endpoint["reporting_status"],
            "favorable_direction": endpoint["favorable_direction"],
            "arm_ids": [item["arm_id"] for item in trial["arms"]],
            "analysis": endpoint["analysis"],
        },
        "safety": {
            "safety_id": safety["safety_id"],
            "event_category": safety["event_category"],
            "reporting_status": safety["reporting_status"],
            "time_frame": safety["time_frame"],
            "description": safety["description"],
            "event_term_count": safety["event_term_count"],
            "arms": [dict(item) for item in safety["arms"]],
        },
    }
    if linked_receipt is not None:
        metadata["linked_source_receipt"] = dict(linked_receipt)
    return normalize_pinned_ingestion_job(
        {
            "schema_version": INGESTION_JOB_SCHEMA_VERSION,
            "job_id": job["job_id"],
            "records": [
                {
                    "source_receipt_id": job["source_receipt_id"],
                    "record_id": job["record"]["record_id"],
                    "predicate": "clinical_trial_design_supported",
                    "subject": trial["candidate_name"],
                    "object_value": trial["disease_name"],
                    "observed_at": job["record"]["observed_at"],
                    "available_at": job["record"]["available_at"],
                    "confidence": job["record"]["confidence"],
                    "biological_context": {
                        "candidate_id": trial["candidate_id"],
                        "intervention_id": trial["intervention_id"],
                        "disease_id": trial["disease_id"],
                        "trial_id": trial["nct_id"],
                        "design_id": f"{trial['nct_id']}:design",
                    },
                    "metadata": metadata,
                }
            ],
        }
    )


def _json_object(payload: bytes) -> dict[str, Any]:
    try:
        source = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("ClinicalTrials.gov source must be UTF-8 JSON") from exc

    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, item in pairs:
            if key in result:
                raise ValueError(f"ClinicalTrials.gov JSON duplicates key {key}")
            result[key] = item
        return result

    try:
        value = json.loads(
            source,
            object_pairs_hook=unique_object,
            parse_constant=lambda item: (_ for _ in ()).throw(
                ValueError(f"ClinicalTrials.gov JSON contains {item}")
            ),
        )
    except json.JSONDecodeError as exc:
        raise ValueError("ClinicalTrials.gov source is not valid JSON") from exc
    return _mapping(value, "ClinicalTrials.gov source")


def _module(value: Mapping[str, Any], key: str, label: str) -> dict[str, Any]:
    return _mapping(value.get(key), f"ClinicalTrials.gov {label}")


def _source_text(value: Mapping[str, Any], key: str, label: str) -> str:
    return _text(value.get(key), f"ClinicalTrials.gov {label}.{key}")


def _parse_source_p_value(value: Any) -> tuple[str, Decimal]:
    text = _text(value, "ClinicalTrials.gov analysis.pValue")
    match = _P_VALUE.fullmatch(text)
    if match is None:
        raise ValueError("ClinicalTrials.gov pValue is not a bounded decimal")
    relation = _RELATION.get(match.group("relation") or "=", "eq")
    return relation, _decimal(match.group("value"), "ClinicalTrials.gov pValue")


def _validate_receipt(bundle: SourceBundle, job: Mapping[str, Any]) -> None:
    verify_source_payload(bundle.receipt, bundle.payload)
    receipt = bundle.receipt
    trial = job["trial"]
    if receipt.receipt_id != job["source_receipt_id"]:
        raise ValueError("ClinicalTrials.gov receipt_id does not match the job")
    if receipt.media_type.casefold() not in {"application/json", "application/json; charset=utf-8"}:
        raise ValueError("ClinicalTrials.gov source must use application/json")
    parsed = urllib.parse.urlsplit(receipt.locator)
    expected_path = f"/api/v2/studies/{trial['nct_id']}"
    if (
        parsed.scheme.casefold() != "https"
        or (parsed.hostname or "").casefold() != "clinicaltrials.gov"
        or parsed.port not in {None, 443}
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path != expected_path
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("ClinicalTrials.gov locator must be the exact study API URL")
    expected_version = (
        f"clinicaltrials-gov-{trial['nct_id']}-version-{trial['registry_version']}"
    )
    if receipt.source_version != expected_version:
        raise ValueError("ClinicalTrials.gov source_version does not bind versionHolder")
    if receipt.source_id != f"clinicaltrials-gov-{trial['nct_id']}":
        raise ValueError("ClinicalTrials.gov source_id is not canonical")
    if receipt.retrieved_at.date() < date.fromisoformat(trial["registry_version"]):
        raise ValueError("ClinicalTrials.gov snapshot predates its versionHolder")


def _validate_source(source: Mapping[str, Any], job: Mapping[str, Any]) -> None:
    trial = job["trial"]
    protocol = _module(source, "protocolSection", "protocolSection")
    derived = _module(source, "derivedSection", "derivedSection")
    results = _module(source, "resultsSection", "resultsSection")
    identification = _module(protocol, "identificationModule", "identificationModule")
    status = _module(protocol, "statusModule", "statusModule")
    conditions = _module(protocol, "conditionsModule", "conditionsModule")
    design = _module(protocol, "designModule", "designModule")
    arms_interventions = _module(
        protocol, "armsInterventionsModule", "armsInterventionsModule"
    )
    outcomes = _module(protocol, "outcomesModule", "outcomesModule")
    eligibility = _module(protocol, "eligibilityModule", "eligibilityModule")
    misc = _module(derived, "miscInfoModule", "miscInfoModule")
    outcome_measures = _module(
        results, "outcomeMeasuresModule", "outcomeMeasuresModule"
    )
    adverse_events = _module(
        results, "adverseEventsModule", "adverseEventsModule"
    )
    if (
        _source_text(identification, "nctId", "identificationModule")
        != trial["nct_id"]
        or _source_text(misc, "versionHolder", "miscInfoModule")
        != trial["registry_version"]
        or source.get("hasResults") is not True
        or _source_text(status, "overallStatus", "statusModule")
        != trial["overall_status"]
        or _source_text(design, "studyType", "designModule") != trial["study_type"]
    ):
        raise ValueError("ClinicalTrials.gov core trial identity mismatch")
    phases = _text_list(design.get("phases"), "ClinicalTrials.gov design.phases")
    if phases != [trial["phase"]]:
        raise ValueError("ClinicalTrials.gov phase mismatch")
    source_conditions = _text_list(
        conditions.get("conditions"), "ClinicalTrials.gov conditions"
    )
    if _normalized(trial["condition"]) not in {
        _normalized(item) for item in source_conditions
    }:
        raise ValueError("ClinicalTrials.gov condition mismatch")
    primary_completion = _mapping(
        status.get("primaryCompletionDateStruct"),
        "ClinicalTrials.gov primaryCompletionDateStruct",
    )
    results_post = _mapping(
        status.get("resultsFirstPostDateStruct"),
        "ClinicalTrials.gov resultsFirstPostDateStruct",
    )
    if (
        _source_text(primary_completion, "date", "primaryCompletionDateStruct")
        != job["record"]["observed_at"]
        or _source_text(results_post, "date", "resultsFirstPostDateStruct")
        != job["record"]["available_at"]
    ):
        raise ValueError("ClinicalTrials.gov evidence chronology mismatch")

    source_interventions = _sequence(
        arms_interventions.get("interventions"),
        "ClinicalTrials.gov interventions",
    )
    source_aliases: set[str] = set()
    for index, raw in enumerate(source_interventions):
        intervention = _mapping(raw, f"ClinicalTrials.gov interventions[{index}]")
        source_aliases.add(_normalized(_source_text(intervention, "name", "intervention")))
        for alias in intervention.get("otherNames", ()):
            source_aliases.add(_normalized(_text(alias, "intervention.otherNames")))
    missing_aliases = sorted(
        alias
        for alias in trial["candidate_aliases"]
        if _normalized(alias) not in source_aliases
    )
    if missing_aliases:
        raise ValueError(f"ClinicalTrials.gov is missing aliases: {missing_aliases}")

    protocol_arms = [
        _mapping(item, "ClinicalTrials.gov armGroup")
        for item in _sequence(
            arms_interventions.get("armGroups"), "ClinicalTrials.gov armGroups"
        )
    ]
    source_primary = _sequence(
        outcomes.get("primaryOutcomes"), "ClinicalTrials.gov primaryOutcomes"
    )
    outcome_list = [
        _mapping(item, "ClinicalTrials.gov outcomeMeasure")
        for item in _sequence(
            outcome_measures.get("outcomeMeasures"),
            "ClinicalTrials.gov outcomeMeasures",
        )
    ]
    endpoint = trial["endpoint"]
    if endpoint["outcome_index"] >= len(outcome_list):
        raise ValueError("ClinicalTrials.gov outcome_index is out of range")
    source_outcome = outcome_list[endpoint["outcome_index"]]
    if endpoint["outcome_index"] >= len(source_primary):
        raise ValueError("ClinicalTrials.gov primary outcome index is out of range")
    protocol_outcome = _mapping(
        source_primary[endpoint["outcome_index"]],
        "ClinicalTrials.gov protocol primary outcome",
    )
    outcome_checks = {
        "outcome type": (_source_text(source_outcome, "type", "outcome"), endpoint["outcome_type"]),
        "outcome name": (_source_text(source_outcome, "title", "outcome"), endpoint["name"]),
        "protocol outcome name": (_source_text(protocol_outcome, "measure", "primary outcome"), endpoint["name"]),
        "outcome time frame": (_source_text(source_outcome, "timeFrame", "outcome"), endpoint["time_frame"]),
        "protocol time frame": (_source_text(protocol_outcome, "timeFrame", "primary outcome"), endpoint["time_frame"]),
        "parameter type": (_source_text(source_outcome, "paramType", "outcome"), endpoint["parameter_type"]),
        "unit": (_source_text(source_outcome, "unitOfMeasure", "outcome"), endpoint["unit"]),
        "reporting status": (_source_text(source_outcome, "reportingStatus", "outcome"), endpoint["reporting_status"]),
        "population": (_source_text(source_outcome, "populationDescription", "outcome"), trial["population"]["description"]),
    }
    mismatches = sorted(
        label for label, (source_value, expected) in outcome_checks.items() if source_value != expected
    )
    if mismatches:
        raise ValueError(f"ClinicalTrials.gov endpoint mismatch: {mismatches}")

    enrollment = _mapping(design.get("enrollmentInfo"), "ClinicalTrials.gov enrollmentInfo")
    population = trial["population"]
    population_checks = {
        "enrollment count": (enrollment.get("count"), population["enrollment_count"]),
        "enrollment type": (enrollment.get("type"), population["enrollment_type"]),
        "sex": (eligibility.get("sex"), population["sex"]),
        "minimum age": (eligibility.get("minimumAge"), population["minimum_age"]),
        "maximum age": (eligibility.get("maximumAge"), population["maximum_age"]),
        "healthy volunteers": (eligibility.get("healthyVolunteers"), population["healthy_volunteers"]),
    }
    mismatches = sorted(
        label for label, (source_value, expected) in population_checks.items() if source_value != expected
    )
    if mismatches:
        raise ValueError(f"ClinicalTrials.gov population mismatch: {mismatches}")

    outcome_groups = {
        _source_text(item, "id", "outcome group"): item
        for item in _sequence(source_outcome.get("groups"), "outcome.groups")
        if isinstance(item, Mapping)
    }
    denoms = _sequence(source_outcome.get("denoms"), "outcome.denoms")
    participant_denoms = [
        _mapping(item, "outcome denom")
        for item in denoms
        if isinstance(item, Mapping) and item.get("units") == "Participants"
    ]
    if len(participant_denoms) != 1:
        raise ValueError("ClinicalTrials.gov outcome needs one participant denominator")
    denominator_by_group = {
        _source_text(item, "groupId", "denominator count"): _positive_int(
            int(_source_text(item, "value", "denominator count")),
            "ClinicalTrials.gov denominator",
        )
        for item in _sequence(participant_denoms[0].get("counts"), "denom.counts")
        if isinstance(item, Mapping)
    }
    measurements: dict[str, str] = {}
    for source_class in _sequence(source_outcome.get("classes"), "outcome.classes"):
        class_value = _mapping(source_class, "outcome class")
        for category in _sequence(class_value.get("categories"), "outcome.categories"):
            category_value = _mapping(category, "outcome category")
            for measurement in _sequence(
                category_value.get("measurements"), "outcome.measurements"
            ):
                value = _mapping(measurement, "outcome measurement")
                group_id = _source_text(value, "groupId", "outcome measurement")
                if group_id in measurements:
                    raise ValueError("ClinicalTrials.gov group has duplicate measurements")
                measurements[group_id] = _source_text(value, "value", "outcome measurement")

    for arm in trial["arms"]:
        matching_protocol = [
            item for item in protocol_arms if item.get("label") == arm["protocol_arm_label"]
        ]
        if len(matching_protocol) != 1:
            raise ValueError("ClinicalTrials.gov selected arm identity is ambiguous")
        protocol_arm = matching_protocol[0]
        outcome_group = outcome_groups.get(arm["source_group_id"])
        if (
            protocol_arm.get("type") != arm["protocol_arm_type"]
            or protocol_arm.get("interventionNames") != arm["intervention_names"]
            or not isinstance(outcome_group, Mapping)
            or outcome_group.get("title") != arm["source_group_title"]
            or measurements.get(arm["source_group_id"])
            != arm["measurement"]["value"]
            or denominator_by_group.get(arm["source_group_id"])
            != arm["measurement"]["denominator"]
        ):
            raise ValueError("ClinicalTrials.gov arm/result measurement mismatch")

    analyses = _sequence(source_outcome.get("analyses"), "outcome.analyses")
    if endpoint["analysis_index"] >= len(analyses):
        raise ValueError("ClinicalTrials.gov analysis_index is out of range")
    source_analysis = _mapping(
        analyses[endpoint["analysis_index"]], "ClinicalTrials.gov analysis"
    )
    expected_analysis = endpoint["analysis"]
    relation, p_value = _parse_source_p_value(source_analysis.get("pValue"))
    source_analysis_values = {
        "source_group_ids": source_analysis.get("groupIds"),
        "p_value_relation": relation,
        "p_value": float(p_value),
        "statistical_method": source_analysis.get("statisticalMethod"),
        "parameter_type": source_analysis.get("paramType"),
        "parameter_value": float(_decimal(source_analysis.get("paramValue"), "analysis.paramValue")),
        "confidence_interval_percent": float(_decimal(source_analysis.get("ciPctValue"), "analysis.ciPctValue")),
        "confidence_interval_lower": float(_decimal(source_analysis.get("ciLowerLimit"), "analysis.ciLowerLimit")),
        "confidence_interval_upper": float(_decimal(source_analysis.get("ciUpperLimit"), "analysis.ciUpperLimit")),
    }
    if source_analysis_values != expected_analysis:
        raise ValueError("ClinicalTrials.gov statistical analysis mismatch")
    candidate, comparator = trial["arms"]
    candidate_value = _decimal(candidate["measurement"]["value"], "candidate measurement")
    comparator_value = _decimal(comparator["measurement"]["value"], "comparator measurement")
    parameter = Decimal(str(expected_analysis["parameter_value"]))
    ci_upper = Decimal(str(expected_analysis["confidence_interval_upper"]))
    if (
        candidate["role"] != "candidate"
        or comparator["role"] != "comparator"
        or _normalized(endpoint["outcome_type"]) != "primary"
        or _normalized(endpoint["reporting_status"]) != "posted"
        or _normalized(expected_analysis["parameter_type"])
        not in {"hazard ratio", "hazard ratio (hr)"}
        or expected_analysis["p_value_relation"] not in {"lt", "le"}
        or not 0 < Decimal(str(expected_analysis["p_value"])) <= Decimal("0.05")
        or not 0 < parameter < 1
        or not ci_upper < 1
        or not candidate_value > comparator_value
    ):
        raise ValueError("ClinicalTrials.gov endpoint fails the bounded benefit rule")

    safety = trial["safety"]
    source_description = adverse_events.get("description")
    if source_description is not None:
        source_description = _text(
            source_description, "ClinicalTrials.gov adverseEventsModule.description"
        )
    source_serious_events = _sequence(
        adverse_events.get("seriousEvents", ()),
        "ClinicalTrials.gov adverseEventsModule.seriousEvents",
    )
    if (
        safety["event_category"] != "SERIOUS"
        or safety["reporting_status"] != "POSTED"
        or _source_text(adverse_events, "timeFrame", "adverseEventsModule")
        != safety["time_frame"]
        or source_description != safety["description"]
        or len(source_serious_events) != safety["event_term_count"]
    ):
        raise ValueError("ClinicalTrials.gov serious-adverse-event module mismatch")
    for event_index, raw_event in enumerate(source_serious_events):
        source_event = _mapping(
            raw_event,
            f"ClinicalTrials.gov seriousEvents[{event_index}]",
        )
        _source_text(source_event, "term", f"seriousEvents[{event_index}]")
        source_stats = _sequence(
            source_event.get("stats"),
            f"ClinicalTrials.gov seriousEvents[{event_index}].stats",
        )
        if not source_stats:
            raise ValueError("ClinicalTrials.gov serious event has no arm statistics")
        event_group_ids: set[str] = set()
        for stat_index, raw_stat in enumerate(source_stats):
            source_stat = _mapping(
                raw_stat,
                (
                    "ClinicalTrials.gov "
                    f"seriousEvents[{event_index}].stats[{stat_index}]"
                ),
            )
            group_id = _source_text(
                source_stat,
                "groupId",
                f"seriousEvents[{event_index}].stats[{stat_index}]",
            )
            if (
                _ADVERSE_EVENT_GROUP_ID.fullmatch(group_id) is None
                or group_id in event_group_ids
            ):
                raise ValueError(
                    "ClinicalTrials.gov serious-event arm statistics are ambiguous"
                )
            event_group_ids.add(group_id)
            _non_negative_int(
                source_stat.get("numAffected"),
                "ClinicalTrials.gov serious-event numAffected",
            )
            _positive_int(
                source_stat.get("numAtRisk"),
                "ClinicalTrials.gov serious-event numAtRisk",
            )
    source_event_groups: dict[str, Mapping[str, Any]] = {}
    for raw_group in _sequence(
        adverse_events.get("eventGroups"),
        "ClinicalTrials.gov adverseEventsModule.eventGroups",
    ):
        source_group = _mapping(raw_group, "ClinicalTrials.gov adverse-event group")
        source_group_id = _source_text(
            source_group, "id", "adverse-event group"
        )
        if (
            _ADVERSE_EVENT_GROUP_ID.fullmatch(source_group_id) is None
            or source_group_id in source_event_groups
        ):
            raise ValueError("ClinicalTrials.gov adverse-event group ids are duplicated")
        source_event_groups[source_group_id] = source_group
    canonical_arms = {item["arm_id"]: item for item in trial["arms"]}
    for safety_arm in safety["arms"]:
        canonical_arm = canonical_arms.get(safety_arm["arm_id"])
        source_group = source_event_groups.get(safety_arm["source_group_id"])
        if not isinstance(source_group, Mapping):
            raise ValueError(
                "ClinicalTrials.gov serious-adverse-event arm summary mismatch"
            )
        source_affected = _non_negative_int(
            source_group.get("seriousNumAffected"),
            "ClinicalTrials.gov adverse-event group seriousNumAffected",
        )
        source_at_risk = _positive_int(
            source_group.get("seriousNumAtRisk"),
            "ClinicalTrials.gov adverse-event group seriousNumAtRisk",
        )
        if (
            canonical_arm is None
            or canonical_arm["role"] != safety_arm["role"]
            or source_group.get("title") != safety_arm["source_group_title"]
            or source_affected != safety_arm["serious_num_affected"]
            or source_at_risk != safety_arm["serious_num_at_risk"]
        ):
            raise ValueError(
                "ClinicalTrials.gov serious-adverse-event arm summary mismatch"
            )


def extract_clinicaltrials_gov_ingestion_job(
    value: Any,
    bundle: SourceBundle,
) -> dict[str, Any]:
    """Verify one exact study snapshot and emit one payload-free generic record."""

    job = normalize_clinicaltrials_gov_ingestion_job(value)
    if not isinstance(bundle, SourceBundle):
        raise TypeError("bundle must be a SourceBundle")
    _validate_receipt(bundle, job)
    source = _json_object(bundle.payload)
    _validate_source(source, job)
    return _generic_job(
        job,
        linked_receipt={
            "receipt_id": bundle.receipt.receipt_id,
            "source_id": bundle.receipt.source_id,
            "source_version": bundle.receipt.source_version,
            "content_hash": bundle.receipt.content_hash,
        },
    )
