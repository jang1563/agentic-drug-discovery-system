"""Strict normalization for payload-free, source-pinned evidence manifests."""

from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping, Sequence
from datetime import date
from typing import Any


PINNED_EVIDENCE_SCHEMA_VERSION = "adds.pinned-evidence.v1"
DISEASE_BURDEN = "disease_burden_supported"
TREATMENT_GAP = "treatment_gap_supported"
CANDIDATE_TARGET_FUNCTION = "candidate_target_functional_activity_supported"
DISEASE_MODEL_EFFECT = "disease_model_effect_supported"
CLINICAL_TRIAL_DESIGN = "clinical_trial_design_supported"
PINNED_EVIDENCE_PREDICATES = frozenset(
    {
        DISEASE_BURDEN,
        TREATMENT_GAP,
        CANDIDATE_TARGET_FUNCTION,
        DISEASE_MODEL_EFFECT,
        CLINICAL_TRIAL_DESIGN,
    }
)

_RECORD_FIELDS = frozenset(
    {
        "record_id",
        "predicate",
        "subject",
        "object_value",
        "observed_at",
        "available_at",
        "confidence",
        "source",
        "biological_context",
        "metadata",
    }
)
_SOURCE_FIELDS = frozenset({"source_id", "source_version", "locator", "content_hash"})
_FORBIDDEN_SUMMARY_KEYS = frozenset(
    {
        "body",
        "document_text",
        "full_text",
        "html",
        "payload",
        "raw_payload",
        "response_body",
        "source_payload",
        "xml",
    }
)
_FORBIDDEN_SOURCE_VERSION_TERMS = ("latest", "current", "unknown", "unpinned")
_EFFECT_RELATIONS = frozenset({"lt", "le", "eq", "ge", "gt"})
_LINEAGE_ID = re.compile(r"^[a-z][a-z0-9._-]*:[^\s:][^\s]*$")
_LOCAL_PATH = re.compile(
    r"(?:^|[\s=:'\"(])(?:file://|/(?:Users|home|tmp|private/tmp|scratch|lustre|gpfs|nfs)/|"
    r"[A-Za-z]:\\Users\\)",
    re.IGNORECASE,
)


def _text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


def _mapping(value: Any, field_name: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field_name} must be an object")
    return dict(value)


def _iso_date(value: Any, field_name: str) -> date:
    text = _text(value, field_name)
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be an ISO 8601 calendar date") from exc


def _sha256(value: Any, field_name: str) -> str:
    text = _text(value, field_name)
    if len(text) != 64 or text != text.lower():
        raise ValueError(f"{field_name} must be a lowercase SHA-256 digest")
    try:
        int(text, 16)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be a lowercase SHA-256 digest") from exc
    return text


def _normalized(value: str) -> str:
    return " ".join(value.casefold().split())


def _require_keys(value: Mapping[str, Any], keys: tuple[str, ...], label: str) -> None:
    missing = [key for key in keys if key not in value]
    if missing:
        raise ValueError(f"{label} is missing required keys: {', '.join(missing)}")
    for key in keys:
        if value[key] is None or value[key] == "":
            raise ValueError(f"{label}.{key} must not be empty")


def _require_text_values(
    value: Mapping[str, Any],
    keys: tuple[str, ...],
    label: str,
) -> None:
    _require_keys(value, keys, label)
    for key in keys:
        _text(value[key], f"{label}.{key}")


def _require_finite_number(value: Any, field_name: str) -> None:
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(float(value))
    ):
        raise ValueError(f"{field_name} must be a finite number")


def _text_sequence(value: Any, field_name: str) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"{field_name} must be an array of strings")
    items = [_text(item, f"{field_name}[{index}]") for index, item in enumerate(value)]
    if not items or len(items) > 32:
        raise ValueError(f"{field_name} must contain 1-32 strings")
    normalized = [_normalized(item) for item in items]
    if len(normalized) != len(set(normalized)):
        raise ValueError(f"{field_name} must not contain duplicate values")
    return items


def _lineage_ids(value: Any, field_name: str) -> list[str]:
    items = _text_sequence(value, field_name)
    if any(_LINEAGE_ID.fullmatch(item) is None for item in items):
        raise ValueError(
            f"{field_name} values must use a canonical namespace:identifier form"
        )
    return items


def _effect_relation(value: Any, field_name: str) -> str:
    relation = _text(value, field_name).casefold()
    if relation not in _EFFECT_RELATIONS:
        raise ValueError(f"{field_name} must be one of {sorted(_EFFECT_RELATIONS)}")
    return relation


def _clinical_trial_design_metadata(
    metadata: dict[str, Any],
    *,
    index: int,
) -> None:
    label = f"records[{index}].metadata"
    _require_text_values(
        metadata,
        (
            "provider_id",
            "registry",
            "registry_version",
            "study_type",
            "overall_status",
            "phase",
            "effect_direction",
        ),
        label,
    )
    if _normalized(str(metadata["provider_id"])) != "clinicaltrials_gov":
        raise ValueError(f"{label}.provider_id must be clinicaltrials_gov")
    if _normalized(str(metadata["registry"])) != "clinicaltrials.gov":
        raise ValueError(f"{label}.registry must be ClinicalTrials.gov")
    if _normalized(str(metadata["study_type"])) != "interventional":
        raise ValueError(f"{label}.study_type must be INTERVENTIONAL")
    if _normalized(str(metadata["effect_direction"])) not in {
        "benefit",
        "harm",
        "unresolved",
    }:
        raise ValueError(f"{label}.effect_direction is unsupported")
    metadata["candidate_aliases"] = _text_sequence(
        metadata.get("candidate_aliases"), f"{label}.candidate_aliases"
    )
    metadata["source_interventions"] = _text_sequence(
        metadata.get("source_interventions"), f"{label}.source_interventions"
    )
    metadata["source_conditions"] = _text_sequence(
        metadata.get("source_conditions"), f"{label}.source_conditions"
    )
    metadata["source_lineage_ids"] = _lineage_ids(
        metadata.get("source_lineage_ids"), f"{label}.source_lineage_ids"
    )

    arms_raw = metadata.get("arms")
    if not isinstance(arms_raw, Sequence) or isinstance(arms_raw, (str, bytes)):
        raise ValueError(f"{label}.arms must be an array")
    if len(arms_raw) != 2:
        raise ValueError(f"{label}.arms must contain exactly two selected arms")
    arm_ids: list[str] = []
    source_group_ids: list[str] = []
    roles: list[str] = []
    for arm_index, raw_arm in enumerate(arms_raw):
        arm = _mapping(raw_arm, f"{label}.arms[{arm_index}]")
        _require_text_values(
            arm,
            (
                "arm_id",
                "source_group_id",
                "label",
                "arm_type",
                "role",
            ),
            f"{label}.arms[{arm_index}]",
        )
        role = _normalized(str(arm["role"]))
        if role not in {"candidate", "comparator"}:
            raise ValueError(f"{label}.arms[{arm_index}].role is unsupported")
        intervention_id = arm.get("intervention_id")
        if role == "candidate":
            _text(intervention_id, f"{label}.arms[{arm_index}].intervention_id")
        elif intervention_id is not None:
            raise ValueError(
                f"{label}.arms[{arm_index}].intervention_id must be null"
            )
        arm["intervention_names"] = _text_sequence(
            arm.get("intervention_names"),
            f"{label}.arms[{arm_index}].intervention_names",
        )
        measurements = _mapping(
            arm.get("measurement"), f"{label}.arms[{arm_index}].measurement"
        )
        _require_text_values(
            measurements,
            ("value",),
            f"{label}.arms[{arm_index}].measurement",
        )
        denominator = measurements.get("denominator")
        if not isinstance(denominator, int) or isinstance(denominator, bool) or denominator <= 0:
            raise ValueError(
                f"{label}.arms[{arm_index}].measurement.denominator must be positive"
            )
        arm_ids.append(str(arm["arm_id"]))
        source_group_ids.append(str(arm["source_group_id"]))
        roles.append(role)
    if len(set(arm_ids)) != 2 or len(set(source_group_ids)) != 2:
        raise ValueError(f"{label}.arms must have unique arm and source group ids")
    if set(roles) != {"candidate", "comparator"}:
        raise ValueError(f"{label}.arms must contain candidate and comparator roles")

    population = _mapping(metadata.get("population"), f"{label}.population")
    _require_text_values(
        population,
        (
            "population_id",
            "description",
            "enrollment_type",
            "sex",
            "minimum_age",
        ),
        f"{label}.population",
    )
    maximum_age = population.get("maximum_age")
    if maximum_age is not None:
        _text(maximum_age, f"{label}.population.maximum_age")
    enrollment_count = population.get("enrollment_count")
    if (
        not isinstance(enrollment_count, int)
        or isinstance(enrollment_count, bool)
        or enrollment_count <= 0
    ):
        raise ValueError(f"{label}.population.enrollment_count must be positive")
    if not isinstance(population.get("healthy_volunteers"), bool):
        raise ValueError(f"{label}.population.healthy_volunteers must be boolean")

    endpoint = _mapping(metadata.get("endpoint"), f"{label}.endpoint")
    _require_text_values(
        endpoint,
        (
            "endpoint_id",
            "population_id",
            "name",
            "outcome_type",
            "time_frame",
            "parameter_type",
            "unit",
            "reporting_status",
            "favorable_direction",
        ),
        f"{label}.endpoint",
    )
    endpoint_arm_ids = _text_sequence(
        endpoint.get("arm_ids"), f"{label}.endpoint.arm_ids"
    )
    if endpoint_arm_ids != arm_ids:
        raise ValueError(f"{label}.endpoint.arm_ids must preserve selected arm order")
    if endpoint["population_id"] != population["population_id"]:
        raise ValueError(f"{label}.endpoint population identity mismatch")
    analysis = _mapping(endpoint.get("analysis"), f"{label}.endpoint.analysis")
    _require_text_values(
        analysis,
        (
            "p_value_relation",
            "statistical_method",
            "parameter_type",
        ),
        f"{label}.endpoint.analysis",
    )
    if analysis["p_value_relation"] not in {"lt", "le", "eq", "ge", "gt"}:
        raise ValueError(f"{label}.endpoint.analysis p-value relation is unsupported")
    for field_name in (
        "p_value",
        "parameter_value",
        "confidence_interval_percent",
        "confidence_interval_lower",
        "confidence_interval_upper",
    ):
        _require_finite_number(
            analysis.get(field_name), f"{label}.endpoint.analysis.{field_name}"
        )
    analysis_group_ids = _text_sequence(
        analysis.get("source_group_ids"),
        f"{label}.endpoint.analysis.source_group_ids",
    )
    if analysis_group_ids != source_group_ids:
        raise ValueError(
            f"{label}.endpoint analysis group ids must preserve selected arm order"
        )


def validate_pinned_public_summary(value: Any, *, label: str) -> None:
    """Reject raw-payload fields, machine paths, and oversized public summaries."""

    def visit(item: Any, path: str) -> None:
        if isinstance(item, Mapping):
            for key, nested in item.items():
                if not isinstance(key, str):
                    raise ValueError(f"{path} keys must be strings")
                normalized_key = re.sub(r"[^a-z0-9]+", "_", key.casefold()).strip("_")
                if normalized_key in _FORBIDDEN_SUMMARY_KEYS:
                    raise ValueError(f"{path}.{key} is a forbidden raw-payload field")
                visit(nested, f"{path}.{key}")
        elif isinstance(item, Sequence) and not isinstance(item, (str, bytes)):
            for index, nested in enumerate(item):
                visit(nested, f"{path}[{index}]")
        elif isinstance(item, str):
            if len(item) > 4096:
                raise ValueError(f"{path} exceeds the public summary text limit")
            if _LOCAL_PATH.search(item):
                raise ValueError(f"{path} contains a machine-local path")
        elif isinstance(item, float) and not math.isfinite(item):
            raise ValueError(f"{path} must contain finite numeric values")
        elif item is not None and not isinstance(item, (bool, int, float)):
            raise ValueError(f"{path} must contain JSON-compatible summary values")

    visit(value, label)
    encoded = json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    if len(encoded) > 64 * 1024:
        raise ValueError(f"{label} exceeds the public summary size limit")


def normalize_pinned_evidence_record(raw: Any, index: int = 0) -> dict[str, Any]:
    """Validate and JSON-normalize one public pinned-evidence record."""

    record = _mapping(raw, f"records[{index}]")
    unknown = sorted(set(record) - _RECORD_FIELDS)
    missing = sorted(_RECORD_FIELDS - set(record))
    if unknown or missing:
        raise ValueError(
            f"records[{index}] fields are invalid; missing={missing}, unknown={unknown}"
        )

    record_id = _text(record["record_id"], f"records[{index}].record_id")
    predicate = _text(record["predicate"], f"records[{index}].predicate")
    if predicate not in PINNED_EVIDENCE_PREDICATES:
        raise ValueError(f"records[{index}].predicate is not supported")
    subject = _text(record["subject"], f"records[{index}].subject")
    object_value = _text(record["object_value"], f"records[{index}].object_value")
    observed_at = _iso_date(record["observed_at"], f"records[{index}].observed_at")
    available_at = _iso_date(record["available_at"], f"records[{index}].available_at")
    if available_at < observed_at:
        raise ValueError(f"records[{index}].available_at cannot precede observed_at")
    confidence = record["confidence"]
    if (
        not isinstance(confidence, (int, float))
        or isinstance(confidence, bool)
        or not 0.0 <= float(confidence) <= 1.0
    ):
        raise ValueError(f"records[{index}].confidence must be between zero and one")

    source = _mapping(record["source"], f"records[{index}].source")
    if set(source) != _SOURCE_FIELDS:
        raise ValueError(
            f"records[{index}].source must contain exactly {sorted(_SOURCE_FIELDS)}"
        )
    source_id = _text(source["source_id"], f"records[{index}].source.source_id")
    source_version = _text(
        source["source_version"], f"records[{index}].source.source_version"
    )
    if any(
        term in source_version.casefold() for term in _FORBIDDEN_SOURCE_VERSION_TERMS
    ):
        raise ValueError(
            f"records[{index}].source.source_version must identify an immutable revision"
        )
    locator = _text(source["locator"], f"records[{index}].source.locator")
    content_hash = _sha256(
        source["content_hash"], f"records[{index}].source.content_hash"
    )

    biological_context = _mapping(
        record["biological_context"], f"records[{index}].biological_context"
    )
    metadata = _mapping(record["metadata"], f"records[{index}].metadata")
    if predicate == DISEASE_BURDEN:
        _require_text_values(
            biological_context,
            ("disease_id", "evidence_context_id"),
            "biological_context",
        )
        _require_text_values(
            metadata,
            (
                "measure_type",
                "measure_unit",
                "population",
                "geography",
                "reference_period",
            ),
            "metadata",
        )
        _require_finite_number(metadata.get("measure_value"), "metadata.measure_value")
    elif predicate == TREATMENT_GAP:
        _require_text_values(
            biological_context,
            ("disease_id", "evidence_context_id"),
            "biological_context",
        )
        _require_text_values(
            metadata,
            (
                "treatment_context",
                "gap_summary",
                "population",
                "geography",
                "reference_period",
            ),
            "metadata",
        )
    elif predicate == CANDIDATE_TARGET_FUNCTION:
        _require_text_values(
            biological_context,
            (
                "candidate_id",
                "target_id",
                "target_record_id",
                "disease_id",
                "organism",
                "assay_id",
            ),
            "biological_context",
        )
        _require_text_values(
            metadata,
            (
                "assay_name",
                "assay_type",
                "source_assay_type",
                "source_assay_type_description",
                "endpoint",
                "endpoint_unit",
                "effect_direction",
            ),
            "metadata",
        )
        if _normalized(str(metadata["assay_type"])) != "functional":
            raise ValueError(f"records[{index}].metadata.assay_type must be functional")
        if metadata.get("functional_readout") is not True:
            raise ValueError(
                f"records[{index}].metadata.functional_readout must be true"
            )
        metadata["endpoint_relation"] = _effect_relation(
            metadata.get("endpoint_relation"), "metadata.endpoint_relation"
        )
        _require_finite_number(
            metadata.get("endpoint_value"), "metadata.endpoint_value"
        )
        metadata["candidate_aliases"] = _text_sequence(
            metadata.get("candidate_aliases"), "metadata.candidate_aliases"
        )
        metadata["source_lineage_ids"] = _lineage_ids(
            metadata.get("source_lineage_ids"), "metadata.source_lineage_ids"
        )
    elif predicate == DISEASE_MODEL_EFFECT:
        _require_text_values(
            biological_context,
            ("candidate_id", "disease_id", "organism", "model_system_id"),
            "biological_context",
        )
        _require_text_values(
            metadata,
            (
                "model_system",
                "model_type",
                "endpoint",
                "endpoint_unit",
                "effect_direction",
                "disease_relevance",
                "source_candidate_name",
            ),
            "metadata",
        )
        metadata["endpoint_relation"] = _effect_relation(
            metadata.get("endpoint_relation"), "metadata.endpoint_relation"
        )
        _require_finite_number(
            metadata.get("endpoint_value"), "metadata.endpoint_value"
        )
        metadata["source_lineage_ids"] = _lineage_ids(
            metadata.get("source_lineage_ids"), "metadata.source_lineage_ids"
        )
    else:
        _require_text_values(
            biological_context,
            ("candidate_id", "intervention_id", "disease_id", "trial_id", "design_id"),
            "biological_context",
        )
        _clinical_trial_design_metadata(metadata, index=index)

    normalized = {
        "record_id": record_id,
        "predicate": predicate,
        "subject": subject,
        "object_value": object_value,
        "observed_at": observed_at.isoformat(),
        "available_at": available_at.isoformat(),
        "confidence": float(confidence),
        "source": {
            "source_id": source_id,
            "source_version": source_version,
            "locator": locator,
            "content_hash": content_hash,
        },
        "biological_context": biological_context,
        "metadata": metadata,
    }
    validate_pinned_public_summary(normalized, label=f"records[{index}]")
    try:
        return json.loads(json.dumps(normalized, sort_keys=True, allow_nan=False))
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"records[{index}] must contain JSON-compatible values"
        ) from exc


def normalize_pinned_evidence_manifest(manifest: Any) -> dict[str, Any]:
    """Validate and normalize a complete version-1 pinned-evidence manifest."""

    value = _mapping(manifest, "manifest")
    if set(value) != {"schema_version", "records"}:
        raise ValueError("manifest must contain exactly schema_version and records")
    if value["schema_version"] != PINNED_EVIDENCE_SCHEMA_VERSION:
        raise ValueError(f"schema_version must be {PINNED_EVIDENCE_SCHEMA_VERSION}")
    records = value["records"]
    if not isinstance(records, Sequence) or isinstance(records, (str, bytes)):
        raise ValueError("records must be an array")
    normalized = tuple(
        normalize_pinned_evidence_record(record, index)
        for index, record in enumerate(records)
    )
    record_ids = tuple(record["record_id"] for record in normalized)
    if len(record_ids) != len(set(record_ids)):
        raise ValueError("record_id values must be unique")
    return {
        "schema_version": PINNED_EVIDENCE_SCHEMA_VERSION,
        "records": list(normalized),
    }
