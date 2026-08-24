"""Strict upstream perturbation handoffs with contextual-only compilation."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping, Sequence
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .execution import EvidenceDraft
from .models import EvidenceRelation


TRANSLATIONAL_HANDOFF_SCHEMA_VERSION = "adds.translational-handoff.v1"
TRANSLATIONAL_HANDOFF_ALLOWED_USE = "contextual_evidence_only"
TRANSLATIONAL_HANDOFF_RELATION = EvidenceRelation.CONTEXTUALIZES

_TOP_LEVEL_FIELDS = {
    "schema_version",
    "handoff_id",
    "payload_class",
    "handoff_status",
    "created_on",
    "program",
    "perturbation",
    "biological_context",
    "sources",
    "observations",
    "review",
    "decision_boundary",
    "integrity_sha256",
}
_PROGRAM_FIELDS = {
    "program_id",
    "hypothesis_id",
    "disease_id",
    "disease_name",
    "target_id",
    "target_name",
}
_PERTURBATION_FIELDS = {
    "perturbation_id",
    "perturbation_type",
    "entity_id",
    "entity_namespace",
    "entity_name",
    "direction",
    "modality",
    "dose",
    "duration",
}
_QUANTITY_FIELDS = {"value", "unit"}
_BIOLOGICAL_CONTEXT_FIELDS = {
    "species_taxon_id",
    "species_name",
    "disease_context_id",
    "tissue_id",
    "tissue_name",
    "cell_type_id",
    "cell_type_name",
    "model_system_id",
    "model_system_name",
    "model_system_type",
}
_SOURCE_FIELDS = {
    "source_id",
    "source_version",
    "locator",
    "content_sha256",
    "observed_on",
    "available_on",
    "lineage_ids",
}
_OBSERVATION_FIELDS = {
    "observation_id",
    "source_id",
    "assay",
    "comparator",
    "result",
    "sampling",
    "quality_control",
    "interpretation_confidence",
}
_ASSAY_FIELDS = {
    "assay_id",
    "assay_name",
    "assay_type",
    "platform",
    "endpoint_id",
    "endpoint_name",
    "endpoint_unit",
}
_COMPARATOR_FIELDS = {"comparator_id", "description"}
_RESULT_FIELDS = {
    "effect_scale",
    "estimate",
    "lower_bound",
    "upper_bound",
    "confidence_level",
    "p_value",
    "effect_direction",
}
_SAMPLING_FIELDS = {
    "observation_count",
    "biological_replicates",
    "technical_replicates",
    "donor_count",
}
_QC_FIELDS = {"status", "checks", "limitations"}
_REVIEW_FIELDS = {
    "review_status",
    "reviewed_on",
    "reviewer_role",
    "interpretation",
    "uncertainty_statement",
    "limitations",
    "conflicts",
    "independent_replication_source_ids",
}
_DECISION_BOUNDARY_FIELDS = {
    "allowed_use",
    "requires_human_review_before_scientific_gate",
    "no_autonomous_wet_lab_execution",
    "no_treatment_recommendation",
    "no_affiliation_or_integration_claim",
    "prohibited_inferences",
}
_PAYLOAD_CLASSES = {"synthetic_fixture", "approved_nonsensitive"}
_PERTURBATION_TYPES = {"genetic", "chemical", "biologic", "physical", "other"}
_PERTURBATION_DIRECTIONS = {
    "activate",
    "increase",
    "inhibit",
    "decrease",
    "knockout",
    "knockdown",
    "replace",
    "other",
}
_EFFECT_SCALES = {
    "difference",
    "standardized_difference",
    "log2_fold_change",
    "fold_change",
    "odds_ratio",
    "hazard_ratio",
    "correlation",
    "other",
}
_POSITIVE_EFFECT_SCALES = {"fold_change", "odds_ratio", "hazard_ratio"}
_EFFECT_DIRECTIONS = {"increase", "decrease", "no_change", "uncertain"}
_QC_STATUSES = {"pass", "partial", "fail", "not_assessed"}
_REQUIRED_PROHIBITED_INFERENCES = {
    "clinical_readiness",
    "mechanism_established",
    "safety_established",
    "therapeutic_efficacy",
    "treatment_recommendation",
}
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,191}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_TAXON_ID = re.compile(r"^[1-9][0-9]*$")


class TranslationalHandoffError(ValueError):
    """Raised when an upstream translational handoff violates its contract."""


def _reject_constant(value: str) -> None:
    raise TranslationalHandoffError(f"non-finite JSON constant is not allowed: {value}")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise TranslationalHandoffError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _load_json(text: str) -> dict[str, Any]:
    try:
        value = json.loads(
            text,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except TranslationalHandoffError:
        raise
    except (TypeError, ValueError) as exc:
        raise TranslationalHandoffError(f"invalid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise TranslationalHandoffError("handoff must be a JSON object")
    return value


def _record(value: Any, path: str, fields: set[str]) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise TranslationalHandoffError(f"{path} must be an object")
    keys = set(value)
    missing = fields - keys
    extra = keys - fields
    if missing:
        raise TranslationalHandoffError(
            f"{path} missing fields: {', '.join(sorted(missing))}"
        )
    if extra:
        raise TranslationalHandoffError(
            f"{path} has unknown fields: {', '.join(sorted(extra))}"
        )
    return dict(value)


def _sequence(value: Any, path: str, *, allow_empty: bool = False) -> list[Any]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise TranslationalHandoffError(f"{path} must be an array")
    items = list(value)
    if not allow_empty and not items:
        raise TranslationalHandoffError(f"{path} must not be empty")
    return items


def _text(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise TranslationalHandoffError(f"{path} must be a trimmed non-empty string")
    return value


def _safe_id(value: Any, path: str) -> str:
    text = _text(value, path)
    if _SAFE_ID.fullmatch(text) is None:
        raise TranslationalHandoffError(f"{path} must be a safe identifier")
    return text


def _text_list(value: Any, path: str, *, allow_empty: bool = False) -> list[str]:
    result = [
        _text(item, f"{path}[{index}]")
        for index, item in enumerate(_sequence(value, path, allow_empty=allow_empty))
    ]
    normalized = [item.casefold() for item in result]
    if len(normalized) != len(set(normalized)):
        raise TranslationalHandoffError(f"{path} must contain unique values")
    return result


def _number(value: Any, path: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise TranslationalHandoffError(f"{path} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise TranslationalHandoffError(f"{path} must be finite")
    return result


def _probability(value: Any, path: str, *, open_interval: bool = False) -> float:
    result = _number(value, path)
    valid = 0 < result < 1 if open_interval else 0 <= result <= 1
    if not valid:
        interval = "strictly between zero and one" if open_interval else "between zero and one"
        raise TranslationalHandoffError(f"{path} must be {interval}")
    return result


def _positive_integer(value: Any, path: str, *, nullable: bool = False) -> int | None:
    if nullable and value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise TranslationalHandoffError(f"{path} must be a positive integer")
    return value


def _iso_date(value: Any, path: str) -> date:
    text = _text(value, path)
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise TranslationalHandoffError(f"{path} must be an ISO date") from exc


def _sha256(value: Any, path: str) -> str:
    text = _text(value, path)
    if _SHA256.fullmatch(text) is None:
        raise TranslationalHandoffError(f"{path} must be a lowercase SHA-256 digest")
    return text


def _bind_identity(
    registry: dict[str, tuple[str, ...]],
    identifier: str,
    signature: tuple[str, ...],
    path: str,
) -> None:
    existing = registry.setdefault(identifier, signature)
    if existing != signature:
        raise TranslationalHandoffError(f"{path} rebinds identifier {identifier}")


def _validate_effect_direction(
    *,
    effect_scale: str,
    estimate: float,
    effect_direction: str,
    path: str,
) -> None:
    if effect_scale == "other" or effect_direction == "uncertain":
        return
    null_value = 1.0 if effect_scale in _POSITIVE_EFFECT_SCALES else 0.0
    expected = (
        "increase"
        if estimate > null_value
        else "decrease"
        if estimate < null_value
        else "no_change"
    )
    if effect_direction != expected:
        raise TranslationalHandoffError(
            f"{path} contradicts the estimate on {effect_scale} scale"
        )


def _validate_quantity(value: Any, path: str) -> None:
    data = _record(value, path, _QUANTITY_FIELDS)
    quantity = data["value"]
    unit = data["unit"]
    if quantity is None and unit is None:
        return
    if quantity is None or unit is None:
        raise TranslationalHandoffError(f"{path}.value and {path}.unit must be set together")
    if _number(quantity, f"{path}.value") < 0:
        raise TranslationalHandoffError(f"{path}.value must be non-negative")
    _text(unit, f"{path}.unit")


def _validate_locator(value: Any, path: str) -> str:
    locator = _text(value, path)
    parsed = urlparse(locator)
    if parsed.scheme == "https" and parsed.hostname:
        return locator
    if parsed.scheme in {"doi", "hf"} and parsed.path:
        return locator
    raise TranslationalHandoffError(
        f"{path} must be an HTTPS, DOI, or Hugging Face locator"
    )


def translational_handoff_integrity_sha256(value: Mapping[str, Any]) -> str:
    """Return the canonical handoff hash excluding the integrity field."""

    payload = {key: item for key, item in value.items() if key != "integrity_sha256"}
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def validate_translational_handoff(value: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a handoff and return a compact machine-readable summary."""

    handoff = _record(value, "handoff", _TOP_LEVEL_FIELDS)
    if handoff["schema_version"] != TRANSLATIONAL_HANDOFF_SCHEMA_VERSION:
        raise TranslationalHandoffError("unsupported schema_version")
    handoff_id = _safe_id(handoff["handoff_id"], "handoff.handoff_id")
    if handoff["payload_class"] not in _PAYLOAD_CLASSES:
        raise TranslationalHandoffError("handoff.payload_class is unsupported")
    if handoff["handoff_status"] != "reviewed_contextual_input":
        raise TranslationalHandoffError(
            "handoff.handoff_status must be reviewed_contextual_input"
        )
    created_on = _iso_date(handoff["created_on"], "handoff.created_on")

    program = _record(handoff["program"], "handoff.program", _PROGRAM_FIELDS)
    for field in ("program_id", "hypothesis_id", "disease_id", "target_id"):
        _safe_id(program[field], f"handoff.program.{field}")
    for field in ("disease_name", "target_name"):
        _text(program[field], f"handoff.program.{field}")

    perturbation = _record(
        handoff["perturbation"], "handoff.perturbation", _PERTURBATION_FIELDS
    )
    for field in ("perturbation_id", "entity_id"):
        _safe_id(perturbation[field], f"handoff.perturbation.{field}")
    for field in ("entity_namespace", "entity_name", "modality"):
        _text(perturbation[field], f"handoff.perturbation.{field}")
    if perturbation["perturbation_type"] not in _PERTURBATION_TYPES:
        raise TranslationalHandoffError("handoff.perturbation.perturbation_type is unsupported")
    if perturbation["direction"] not in _PERTURBATION_DIRECTIONS:
        raise TranslationalHandoffError("handoff.perturbation.direction is unsupported")
    _validate_quantity(perturbation["dose"], "handoff.perturbation.dose")
    _validate_quantity(perturbation["duration"], "handoff.perturbation.duration")

    biological = _record(
        handoff["biological_context"],
        "handoff.biological_context",
        _BIOLOGICAL_CONTEXT_FIELDS,
    )
    if _TAXON_ID.fullmatch(
        _text(biological["species_taxon_id"], "handoff.biological_context.species_taxon_id")
    ) is None:
        raise TranslationalHandoffError(
            "handoff.biological_context.species_taxon_id must be a positive NCBI taxonomy id"
        )
    for field in (
        "disease_context_id",
        "tissue_id",
        "cell_type_id",
        "model_system_id",
    ):
        _safe_id(biological[field], f"handoff.biological_context.{field}")
    for field in (
        "species_name",
        "tissue_name",
        "cell_type_name",
        "model_system_name",
        "model_system_type",
    ):
        _text(biological[field], f"handoff.biological_context.{field}")
    if biological["disease_context_id"] != program["disease_id"]:
        raise TranslationalHandoffError(
            "handoff biological disease context must match program disease_id"
        )

    sources: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(_sequence(handoff["sources"], "handoff.sources")):
        source = _record(item, f"handoff.sources[{index}]", _SOURCE_FIELDS)
        source_id = _safe_id(source["source_id"], f"handoff.sources[{index}].source_id")
        if source_id in sources:
            raise TranslationalHandoffError(f"duplicate source_id: {source_id}")
        _text(source["source_version"], f"source {source_id}.source_version")
        _validate_locator(source["locator"], f"source {source_id}.locator")
        _sha256(source["content_sha256"], f"source {source_id}.content_sha256")
        observed_on = _iso_date(source["observed_on"], f"source {source_id}.observed_on")
        available_on = _iso_date(source["available_on"], f"source {source_id}.available_on")
        if available_on < observed_on:
            raise TranslationalHandoffError(
                f"source {source_id}.available_on cannot precede observed_on"
            )
        if available_on > created_on:
            raise TranslationalHandoffError(
                f"source {source_id}.available_on cannot follow handoff.created_on"
            )
        lineage_ids = _text_list(source["lineage_ids"], f"source {source_id}.lineage_ids")
        sources[source_id] = {**source, "lineage_ids": lineage_ids}

    observations: list[dict[str, Any]] = []
    observation_ids: set[str] = set()
    observation_source_ids: set[str] = set()
    endpoint_ids_by_source: dict[str, set[str]] = {
        source_id: set() for source_id in sources
    }
    qc_counts = {status: 0 for status in sorted(_QC_STATUSES)}
    assay_ids: set[str] = set()
    assay_identities: dict[str, tuple[str, ...]] = {}
    endpoint_identities: dict[str, tuple[str, ...]] = {}
    comparator_identities: dict[str, tuple[str, ...]] = {}
    for index, item in enumerate(
        _sequence(handoff["observations"], "handoff.observations")
    ):
        if index >= 256:
            raise TranslationalHandoffError("handoff.observations cannot exceed 256 entries")
        observation = _record(
            item, f"handoff.observations[{index}]", _OBSERVATION_FIELDS
        )
        observation_id = _safe_id(
            observation["observation_id"],
            f"handoff.observations[{index}].observation_id",
        )
        if observation_id in observation_ids:
            raise TranslationalHandoffError(f"duplicate observation_id: {observation_id}")
        observation_ids.add(observation_id)
        source_id = _safe_id(observation["source_id"], f"observation {observation_id}.source_id")
        if source_id not in sources:
            raise TranslationalHandoffError(
                f"observation {observation_id} references unknown source_id"
            )
        observation_source_ids.add(source_id)

        assay = _record(observation["assay"], f"observation {observation_id}.assay", _ASSAY_FIELDS)
        assay_id = _safe_id(
            assay["assay_id"], f"observation {observation_id}.assay.assay_id"
        )
        endpoint_id = _safe_id(
            assay["endpoint_id"], f"observation {observation_id}.assay.endpoint_id"
        )
        for field in ("assay_name", "assay_type", "platform", "endpoint_name", "endpoint_unit"):
            _text(assay[field], f"observation {observation_id}.assay.{field}")
        _bind_identity(
            assay_identities,
            assay_id,
            (assay["assay_name"], assay["assay_type"], assay["platform"], endpoint_id),
            "assay_id",
        )
        _bind_identity(
            endpoint_identities,
            endpoint_id,
            (assay["endpoint_name"], assay["endpoint_unit"]),
            "endpoint_id",
        )
        assay_ids.add(assay_id)
        endpoint_ids_by_source[source_id].add(endpoint_id)

        comparator = _record(
            observation["comparator"],
            f"observation {observation_id}.comparator",
            _COMPARATOR_FIELDS,
        )
        comparator_id = _safe_id(
            comparator["comparator_id"],
            f"observation {observation_id}.comparator.comparator_id",
        )
        _text(comparator["description"], f"observation {observation_id}.comparator.description")
        _bind_identity(
            comparator_identities,
            comparator_id,
            (comparator["description"],),
            "comparator_id",
        )

        result = _record(
            observation["result"], f"observation {observation_id}.result", _RESULT_FIELDS
        )
        if result["effect_scale"] not in _EFFECT_SCALES:
            raise TranslationalHandoffError(
                f"observation {observation_id}.result.effect_scale is unsupported"
            )
        estimate = _number(result["estimate"], f"observation {observation_id}.result.estimate")
        lower = _number(result["lower_bound"], f"observation {observation_id}.result.lower_bound")
        upper = _number(result["upper_bound"], f"observation {observation_id}.result.upper_bound")
        if not lower <= estimate <= upper:
            raise TranslationalHandoffError(
                f"observation {observation_id} interval must contain its estimate"
            )
        if result["effect_scale"] in _POSITIVE_EFFECT_SCALES and lower <= 0:
            raise TranslationalHandoffError(
                f"observation {observation_id} ratio-scale interval must be positive"
            )
        _probability(
            result["confidence_level"],
            f"observation {observation_id}.result.confidence_level",
            open_interval=True,
        )
        if result["p_value"] is not None:
            _probability(result["p_value"], f"observation {observation_id}.result.p_value")
        if result["effect_direction"] not in _EFFECT_DIRECTIONS:
            raise TranslationalHandoffError(
                f"observation {observation_id}.result.effect_direction is unsupported"
            )
        _validate_effect_direction(
            effect_scale=result["effect_scale"],
            estimate=estimate,
            effect_direction=result["effect_direction"],
            path=f"observation {observation_id}.result.effect_direction",
        )

        sampling = _record(
            observation["sampling"],
            f"observation {observation_id}.sampling",
            _SAMPLING_FIELDS,
        )
        for field in ("observation_count", "biological_replicates", "technical_replicates"):
            _positive_integer(sampling[field], f"observation {observation_id}.sampling.{field}")
        _positive_integer(
            sampling["donor_count"],
            f"observation {observation_id}.sampling.donor_count",
            nullable=True,
        )

        quality = _record(
            observation["quality_control"],
            f"observation {observation_id}.quality_control",
            _QC_FIELDS,
        )
        if quality["status"] not in _QC_STATUSES:
            raise TranslationalHandoffError(
                f"observation {observation_id}.quality_control.status is unsupported"
            )
        _text_list(quality["checks"], f"observation {observation_id}.quality_control.checks")
        _text_list(
            quality["limitations"],
            f"observation {observation_id}.quality_control.limitations",
            allow_empty=True,
        )
        qc_counts[quality["status"]] += 1
        _probability(
            observation["interpretation_confidence"],
            f"observation {observation_id}.interpretation_confidence",
        )
        observations.append(observation)
    if observation_source_ids != set(sources):
        unused = set(sources) - observation_source_ids
        raise TranslationalHandoffError(
            "handoff sources without observations: " + ", ".join(sorted(unused))
        )

    review = _record(handoff["review"], "handoff.review", _REVIEW_FIELDS)
    if review["review_status"] != "approved_contextual_use":
        raise TranslationalHandoffError(
            "handoff.review.review_status must be approved_contextual_use"
        )
    reviewed_on = _iso_date(review["reviewed_on"], "handoff.review.reviewed_on")
    if reviewed_on < created_on:
        raise TranslationalHandoffError("handoff.review.reviewed_on cannot precede created_on")
    _text(review["reviewer_role"], "handoff.review.reviewer_role")
    _text(review["interpretation"], "handoff.review.interpretation")
    _text(review["uncertainty_statement"], "handoff.review.uncertainty_statement")
    _text_list(review["limitations"], "handoff.review.limitations")
    _text_list(review["conflicts"], "handoff.review.conflicts", allow_empty=True)
    replication_ids = set(
        _text_list(
            review["independent_replication_source_ids"],
            "handoff.review.independent_replication_source_ids",
            allow_empty=True,
        )
    )
    if replication_ids - set(sources):
        raise TranslationalHandoffError(
            "handoff.review.independent_replication_source_ids references unknown sources"
        )
    if len(replication_ids) == 1:
        raise TranslationalHandoffError(
            "independent replication requires zero or at least two source ids"
        )
    replication_lineages: set[str] = set()
    for source_id in sorted(replication_ids):
        lineage = set(sources[source_id]["lineage_ids"])
        overlap = replication_lineages & lineage
        if overlap:
            raise TranslationalHandoffError(
                "independent replication sources share lineage: "
                + ", ".join(sorted(overlap))
            )
        replication_lineages.update(lineage)
    if replication_ids:
        common_endpoints = set.intersection(
            *(endpoint_ids_by_source[source_id] for source_id in replication_ids)
        )
        if not common_endpoints:
            raise TranslationalHandoffError(
                "independent replication sources must share at least one endpoint_id"
            )

    boundary = _record(
        handoff["decision_boundary"],
        "handoff.decision_boundary",
        _DECISION_BOUNDARY_FIELDS,
    )
    if boundary["allowed_use"] != TRANSLATIONAL_HANDOFF_ALLOWED_USE:
        raise TranslationalHandoffError(
            "handoff.decision_boundary.allowed_use must remain contextual_evidence_only"
        )
    for field in (
        "requires_human_review_before_scientific_gate",
        "no_autonomous_wet_lab_execution",
        "no_treatment_recommendation",
        "no_affiliation_or_integration_claim",
    ):
        if boundary[field] is not True:
            raise TranslationalHandoffError(f"handoff.decision_boundary.{field} must be true")
    prohibited = set(
        _text_list(
            boundary["prohibited_inferences"],
            "handoff.decision_boundary.prohibited_inferences",
        )
    )
    if prohibited != _REQUIRED_PROHIBITED_INFERENCES:
        raise TranslationalHandoffError(
            "handoff.decision_boundary.prohibited_inferences must preserve the reviewed set"
        )

    expected_hash = _sha256(handoff["integrity_sha256"], "handoff.integrity_sha256")
    actual_hash = translational_handoff_integrity_sha256(handoff)
    if expected_hash != actual_hash:
        raise TranslationalHandoffError(
            f"handoff integrity mismatch: expected {expected_hash}, got {actual_hash}"
        )

    return {
        "schema_version": TRANSLATIONAL_HANDOFF_SCHEMA_VERSION,
        "handoff_id": handoff_id,
        "payload_class": handoff["payload_class"],
        "handoff_status": handoff["handoff_status"],
        "program_id": program["program_id"],
        "disease_id": program["disease_id"],
        "target_id": program["target_id"],
        "source_count": len(sources),
        "observation_count": len(observations),
        "assay_count": len(assay_ids),
        "independent_replication_source_count": len(replication_ids),
        "quality_control_counts": qc_counts,
        "allowed_use": TRANSLATIONAL_HANDOFF_ALLOWED_USE,
        "compiled_relation": TRANSLATIONAL_HANDOFF_RELATION.value,
        "integrity_sha256": actual_hash,
    }


def translational_handoff_from_json(text: str) -> dict[str, Any]:
    """Parse duplicate-safe JSON and return a validated handoff."""

    handoff = _load_json(text)
    validate_translational_handoff(handoff)
    return handoff


def load_translational_handoff(path: str | Path) -> dict[str, Any]:
    """Load and validate one translational handoff from disk."""

    source = Path(path)
    try:
        text = source.read_text(encoding="utf-8")
    except OSError as exc:
        raise TranslationalHandoffError(f"cannot read handoff {source}: {exc}") from exc
    return translational_handoff_from_json(text)


def translational_handoff_summary(value: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a handoff and return its compact summary."""

    return validate_translational_handoff(value)


def compile_translational_handoff_evidence(
    value: Mapping[str, Any],
    *,
    request_id: str,
) -> tuple[EvidenceDraft, ...]:
    """Compile observations into contextual evidence drafts without scientific claims."""

    validate_translational_handoff(value)
    request = _safe_id(request_id, "request_id")
    program = value["program"]
    perturbation = value["perturbation"]
    biological = value["biological_context"]
    sources = {item["source_id"]: item for item in value["sources"]}
    drafts: list[EvidenceDraft] = []
    for observation in value["observations"]:
        source = sources[observation["source_id"]]
        result = observation["result"]
        assay = observation["assay"]
        drafts.append(
            EvidenceDraft(
                evidence_id=(
                    f"{request}:evidence:translational-handoff:"
                    f"{observation['observation_id']}"
                ),
                request_id=request,
                subject=program["target_id"],
                predicate="upstream_perturbation_observation",
                object_value=(
                    f"{assay['endpoint_id']}|{result['effect_scale']}|"
                    f"{result['estimate']}"
                ),
                observed_at=date.fromisoformat(source["observed_on"]),
                available_at=date.fromisoformat(source["available_on"]),
                source_id=source["source_id"],
                relation=TRANSLATIONAL_HANDOFF_RELATION,
                direction=result["effect_direction"],
                confidence=float(observation["interpretation_confidence"]),
                biological_context={
                    "program_id": program["program_id"],
                    "hypothesis_id": program["hypothesis_id"],
                    "disease_id": program["disease_id"],
                    "target_id": program["target_id"],
                    "perturbation_id": perturbation["perturbation_id"],
                    "perturbation_type": perturbation["perturbation_type"],
                    "perturbation_direction": perturbation["direction"],
                    "species_taxon_id": biological["species_taxon_id"],
                    "tissue_id": biological["tissue_id"],
                    "cell_type_id": biological["cell_type_id"],
                    "model_system_id": biological["model_system_id"],
                    "assay_id": assay["assay_id"],
                    "endpoint_id": assay["endpoint_id"],
                    "comparator_id": observation["comparator"]["comparator_id"],
                },
                metadata={
                    "handoff_schema_version": value["schema_version"],
                    "handoff_id": value["handoff_id"],
                    "handoff_integrity_sha256": value["integrity_sha256"],
                    "payload_class": value["payload_class"],
                    "allowed_use": TRANSLATIONAL_HANDOFF_ALLOWED_USE,
                    "source_content_sha256": source["content_sha256"],
                    "source_lineage_ids": source["lineage_ids"],
                    "effect_scale": result["effect_scale"],
                    "estimate": result["estimate"],
                    "lower_bound": result["lower_bound"],
                    "upper_bound": result["upper_bound"],
                    "confidence_level": result["confidence_level"],
                    "p_value": result["p_value"],
                    "endpoint_name": assay["endpoint_name"],
                    "endpoint_unit": assay["endpoint_unit"],
                    "sampling": observation["sampling"],
                    "quality_control": observation["quality_control"],
                    "review_status": value["review"]["review_status"],
                    "requires_human_review_before_scientific_gate": True,
                    "prohibited_inferences": sorted(_REQUIRED_PROHIBITED_INFERENCES),
                },
            )
        )
    return tuple(drafts)
