"""Strict research-context profiles for collaborator and presentation review."""

from __future__ import annotations

import hashlib
import json
import math
from datetime import date
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence
from urllib.parse import urlparse


RESEARCH_READINESS_SCHEMA_VERSION = "adds.biohub-research-readiness.v1"
RESEARCH_READINESS_PROFILE_ID = "biohub-translational-evidence-bridge-v1"
RESEARCH_READINESS_SYSTEM_ROLE = "translational_evidence_governance_layer"

_TOP_LEVEL_FIELDS = {
    "schema_version",
    "profile_id",
    "profile_status",
    "assessment_date",
    "organization_context",
    "positioning",
    "evidence_anchors",
    "maturity_ledger",
    "fit_matrix",
    "pilot",
    "presentation",
    "known_gaps",
    "decision",
    "integrity_sha256",
}
_MATURITY_LEVELS = {"implemented_public", "synthetic_validated", "proposed_pilot"}
_FIT_LEVELS = {"direct", "complementary", "proposed"}
_ANCHOR_KINDS = {"implementation", "test", "document", "synthetic_summary"}
_OFFICIAL_HOSTS = {"czbiohub.org", "www.czbiohub.org"}
_REQUIRED_NON_ROLES = {
    "biohub_endorsed_project",
    "clinical_decision_maker",
    "therapeutic_design_engine",
    "virtual_cell_model",
}
_REQUIRED_GATES = {
    "provenance_coverage": ("==", 1.0, "stop"),
    "replay_success": ("==", 1.0, "stop"),
    "silent_advance_count": ("==", 0, "stop"),
    "independent_review_agreement": (">=", 0.8, "hold_and_review"),
    "median_packet_time_reduction": (">=", 0.25, "hold_and_review"),
}
_REQUIRED_PROHIBITED_CLAIMS = {
    "Biohub endorsement or affiliation",
    "a validated virtual-cell model",
    "autonomous therapeutic design or treatment recommendation",
    "external transportability of synthetic cluster templates",
    "real-world clinical calibration or policy superiority",
}
_REQUIRED_GAP_IDS = {
    "gap-biohub-integration",
    "gap-cell-state-contract",
    "gap-disease-breadth",
    "gap-external-transport",
    "gap-public-candidate",
    "gap-real-heldout-evaluation",
}


class ResearchReadinessError(ValueError):
    """Raised when a research-readiness profile violates its contract."""


def _reject_constant(value: str) -> None:
    raise ResearchReadinessError(f"non-finite JSON constant is not allowed: {value}")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ResearchReadinessError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _load_json(text: str) -> dict[str, Any]:
    try:
        value = json.loads(
            text,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except ResearchReadinessError:
        raise
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ResearchReadinessError(f"invalid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise ResearchReadinessError("profile must be a JSON object")
    return value


def _record(
    value: Any,
    path: str,
    *,
    required: set[str],
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ResearchReadinessError(f"{path} must be an object")
    keys = set(value)
    missing = required - keys
    extra = keys - required
    if missing:
        raise ResearchReadinessError(
            f"{path} missing fields: {', '.join(sorted(missing))}"
        )
    if extra:
        raise ResearchReadinessError(
            f"{path} has unknown fields: {', '.join(sorted(extra))}"
        )
    return dict(value)


def _sequence(value: Any, path: str) -> list[Any]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ResearchReadinessError(f"{path} must be an array")
    return list(value)


def _text(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ResearchReadinessError(f"{path} must be a non-empty string")
    return value


def _text_list(value: Any, path: str, *, nonempty: bool = True) -> list[str]:
    items = _sequence(value, path)
    if nonempty and not items:
        raise ResearchReadinessError(f"{path} must not be empty")
    result = [_text(item, f"{path}[{index}]") for index, item in enumerate(items)]
    if len(result) != len(set(result)):
        raise ResearchReadinessError(f"{path} must contain unique values")
    return result


def _integer(value: Any, path: str, *, minimum: int | None = None) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ResearchReadinessError(f"{path} must be an integer")
    if minimum is not None and value < minimum:
        raise ResearchReadinessError(f"{path} must be at least {minimum}")
    return value


def _number(value: Any, path: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ResearchReadinessError(f"{path} must be numeric")
    if not math.isfinite(float(value)):
        raise ResearchReadinessError(f"{path} must be finite")
    return float(value)


def _iso_date(value: Any, path: str) -> date:
    text = _text(value, path)
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise ResearchReadinessError(f"{path} must be an ISO date") from exc


def _sha256(value: Any, path: str) -> str:
    text = _text(value, path)
    if len(text) != 64 or text.lower() != text:
        raise ResearchReadinessError(f"{path} must be a lowercase SHA-256 digest")
    try:
        int(text, 16)
    except ValueError as exc:
        raise ResearchReadinessError(
            f"{path} must be a lowercase SHA-256 digest"
        ) from exc
    return text


def _relative_path(value: Any, path: str) -> str:
    text = _text(value, path)
    pure = PurePosixPath(text)
    if pure.is_absolute() or ".." in pure.parts or text != pure.as_posix():
        raise ResearchReadinessError(f"{path} must be a normalized relative POSIX path")
    return text


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def research_readiness_integrity_sha256(profile: Mapping[str, Any]) -> str:
    """Return the canonical integrity hash, excluding the hash field itself."""

    payload = {key: value for key, value in profile.items() if key != "integrity_sha256"}
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _validate_organization(
    value: Any,
    *,
    assessment_date: date,
) -> set[str]:
    data = _record(
        value,
        "organization_context",
        required={
            "name",
            "affiliation_claimed",
            "context_scope",
            "official_sources",
            "alignment_observations",
        },
    )
    if data["name"] != "Chan Zuckerberg Biohub Network":
        raise ResearchReadinessError("organization_context.name is not the reviewed organization")
    if data["affiliation_claimed"] is not False:
        raise ResearchReadinessError("organization_context must not claim affiliation")
    _text(data["context_scope"], "organization_context.context_scope")

    observations: dict[str, set[str]] = {}
    for index, item in enumerate(
        _sequence(data["alignment_observations"], "organization_context.alignment_observations")
    ):
        entry = _record(
            item,
            f"organization_context.alignment_observations[{index}]",
            required={"observation_id", "statement", "source_ids"},
        )
        observation_id = _text(
            entry["observation_id"],
            f"organization_context.alignment_observations[{index}].observation_id",
        )
        if observation_id in observations:
            raise ResearchReadinessError(f"duplicate observation_id: {observation_id}")
        _text(entry["statement"], f"alignment observation {observation_id}.statement")
        observations[observation_id] = set(
            _text_list(entry["source_ids"], f"alignment observation {observation_id}.source_ids")
        )
    if not observations:
        raise ResearchReadinessError("organization_context.alignment_observations must not be empty")

    sources: dict[str, set[str]] = {}
    for index, item in enumerate(
        _sequence(data["official_sources"], "organization_context.official_sources")
    ):
        entry = _record(
            item,
            f"organization_context.official_sources[{index}]",
            required={"source_id", "url", "accessed_on", "supports"},
        )
        source_id = _text(entry["source_id"], f"official source {index}.source_id")
        if source_id in sources:
            raise ResearchReadinessError(f"duplicate official source_id: {source_id}")
        url = _text(entry["url"], f"official source {source_id}.url")
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.hostname not in _OFFICIAL_HOSTS:
            raise ResearchReadinessError(
                f"official source {source_id} must use an official czbiohub.org HTTPS URL"
            )
        if _iso_date(entry["accessed_on"], f"official source {source_id}.accessed_on") > assessment_date:
            raise ResearchReadinessError(
                f"official source {source_id} cannot be accessed after assessment_date"
            )
        sources[source_id] = set(
            _text_list(entry["supports"], f"official source {source_id}.supports")
        )
    if not sources:
        raise ResearchReadinessError("organization_context.official_sources must not be empty")

    for observation_id, source_ids in observations.items():
        missing = source_ids - set(sources)
        if missing:
            raise ResearchReadinessError(
                f"observation {observation_id} references unknown sources: {', '.join(sorted(missing))}"
            )
        for source_id in source_ids:
            if observation_id not in sources[source_id]:
                raise ResearchReadinessError(
                    f"source {source_id} does not reciprocally support {observation_id}"
                )
    for source_id, observation_ids in sources.items():
        missing = observation_ids - set(observations)
        if missing:
            raise ResearchReadinessError(
                f"source {source_id} references unknown observations: {', '.join(sorted(missing))}"
            )
    return set(observations)


def _validate_positioning(value: Any) -> None:
    data = _record(
        value,
        "positioning",
        required={
            "one_line",
            "system_role",
            "upstream_inputs",
            "outputs",
            "explicit_non_roles",
        },
    )
    _text(data["one_line"], "positioning.one_line")
    if data["system_role"] != RESEARCH_READINESS_SYSTEM_ROLE:
        raise ResearchReadinessError("positioning.system_role overstates or changes the reviewed role")
    _text_list(data["upstream_inputs"], "positioning.upstream_inputs")
    _text_list(data["outputs"], "positioning.outputs")
    non_roles = set(_text_list(data["explicit_non_roles"], "positioning.explicit_non_roles"))
    missing = _REQUIRED_NON_ROLES - non_roles
    if missing:
        raise ResearchReadinessError(
            f"positioning missing explicit non-roles: {', '.join(sorted(missing))}"
        )


def _validate_anchors(value: Any, *, root: Path) -> dict[str, str]:
    anchors: dict[str, str] = {}
    paths: set[str] = set()
    for index, item in enumerate(_sequence(value, "evidence_anchors")):
        entry = _record(
            item,
            f"evidence_anchors[{index}]",
            required={"anchor_id", "path", "sha256", "kind"},
        )
        anchor_id = _text(entry["anchor_id"], f"evidence_anchors[{index}].anchor_id")
        if anchor_id in anchors:
            raise ResearchReadinessError(f"duplicate anchor_id: {anchor_id}")
        relative = _relative_path(entry["path"], f"evidence anchor {anchor_id}.path")
        if relative in paths:
            raise ResearchReadinessError(f"duplicate evidence anchor path: {relative}")
        kind = entry["kind"]
        if kind not in _ANCHOR_KINDS:
            raise ResearchReadinessError(f"evidence anchor {anchor_id} has unsupported kind")
        expected = _sha256(entry["sha256"], f"evidence anchor {anchor_id}.sha256")
        resolved = (root / relative).resolve()
        try:
            resolved.relative_to(root.resolve())
        except ValueError as exc:
            raise ResearchReadinessError(
                f"evidence anchor {anchor_id} escapes the repository"
            ) from exc
        if not resolved.is_file():
            raise ResearchReadinessError(f"evidence anchor {anchor_id} is missing: {relative}")
        actual = _file_sha256(resolved)
        if actual != expected:
            raise ResearchReadinessError(
                f"evidence anchor {anchor_id} hash mismatch: expected {expected}, got {actual}"
            )
        anchors[anchor_id] = kind
        paths.add(relative)
    if not anchors:
        raise ResearchReadinessError("evidence_anchors must not be empty")
    return anchors


def _validate_maturity(value: Any, *, anchors: Mapping[str, str]) -> dict[str, str]:
    capabilities: dict[str, str] = {}
    for index, item in enumerate(_sequence(value, "maturity_ledger")):
        entry = _record(
            item,
            f"maturity_ledger[{index}]",
            required={
                "capability_id",
                "label",
                "maturity",
                "claim",
                "evidence_anchor_ids",
                "limitations",
            },
        )
        capability_id = _text(entry["capability_id"], f"maturity item {index}.capability_id")
        if capability_id in capabilities:
            raise ResearchReadinessError(f"duplicate capability_id: {capability_id}")
        _text(entry["label"], f"capability {capability_id}.label")
        _text(entry["claim"], f"capability {capability_id}.claim")
        maturity = entry["maturity"]
        if maturity not in _MATURITY_LEVELS:
            raise ResearchReadinessError(f"capability {capability_id} has unsupported maturity")
        anchor_ids = _text_list(
            entry["evidence_anchor_ids"],
            f"capability {capability_id}.evidence_anchor_ids",
            nonempty=False,
        )
        missing = set(anchor_ids) - set(anchors)
        if missing:
            raise ResearchReadinessError(
                f"capability {capability_id} references unknown anchors: {', '.join(sorted(missing))}"
            )
        kinds = {anchors[anchor_id] for anchor_id in anchor_ids}
        if maturity == "implemented_public" and not {"implementation", "test"} <= kinds:
            raise ResearchReadinessError(
                f"implemented capability {capability_id} requires implementation and test anchors"
            )
        if maturity == "synthetic_validated" and not {
            "implementation",
            "test",
            "document",
            "synthetic_summary",
        } <= kinds:
            raise ResearchReadinessError(
                f"synthetic capability {capability_id} requires implementation, test, document, and synthetic-summary anchors"
            )
        _text_list(entry["limitations"], f"capability {capability_id}.limitations")
        capabilities[capability_id] = maturity
    if not capabilities:
        raise ResearchReadinessError("maturity_ledger must not be empty")
    return capabilities


def _validate_pilot(value: Any) -> tuple[set[str], set[str]]:
    data = _record(
        value,
        "pilot",
        required={
            "pilot_id",
            "status",
            "duration_days",
            "research_question",
            "unit_of_analysis",
            "target_programs",
            "input_contract",
            "output_contract",
            "work_packages",
            "phases",
            "evaluation_design",
            "acceptance_gates",
            "governance",
        },
    )
    _text(data["pilot_id"], "pilot.pilot_id")
    if data["status"] != "proposed_not_executed":
        raise ResearchReadinessError("pilot.status must remain proposed_not_executed")
    if _integer(data["duration_days"], "pilot.duration_days", minimum=1) != 90:
        raise ResearchReadinessError("pilot.duration_days must be 90")
    _text(data["research_question"], "pilot.research_question")
    _text(data["unit_of_analysis"], "pilot.unit_of_analysis")
    targets = _record(
        data["target_programs"],
        "pilot.target_programs",
        required={"minimum", "target"},
    )
    minimum = _integer(targets["minimum"], "pilot.target_programs.minimum", minimum=1)
    target = _integer(targets["target"], "pilot.target_programs.target", minimum=minimum)
    if (minimum, target) != (12, 20):
        raise ResearchReadinessError("pilot target_programs must preserve the preregistered 12/20 scope")
    _text_list(data["input_contract"], "pilot.input_contract")
    _text_list(data["output_contract"], "pilot.output_contract")

    work_package_ids: set[str] = set()
    for index, item in enumerate(_sequence(data["work_packages"], "pilot.work_packages")):
        entry = _record(
            item,
            f"pilot.work_packages[{index}]",
            required={"work_package_id", "title", "objective", "deliverables"},
        )
        work_package_id = _text(
            entry["work_package_id"], f"pilot.work_packages[{index}].work_package_id"
        )
        if work_package_id in work_package_ids:
            raise ResearchReadinessError(f"duplicate work_package_id: {work_package_id}")
        _text(entry["title"], f"work package {work_package_id}.title")
        _text(entry["objective"], f"work package {work_package_id}.objective")
        _text_list(entry["deliverables"], f"work package {work_package_id}.deliverables")
        work_package_ids.add(work_package_id)

    expected_start = 1
    phase_ids: set[str] = set()
    assigned_work_package_ids: set[str] = set()
    for index, item in enumerate(_sequence(data["phases"], "pilot.phases")):
        entry = _record(
            item,
            f"pilot.phases[{index}]",
            required={
                "phase_id",
                "name",
                "day_start",
                "day_end",
                "work_package_ids",
                "exit_criteria",
            },
        )
        phase_id = _text(entry["phase_id"], f"pilot.phases[{index}].phase_id")
        if phase_id in phase_ids:
            raise ResearchReadinessError(f"duplicate pilot phase_id: {phase_id}")
        phase_ids.add(phase_id)
        _text(entry["name"], f"pilot phase {phase_id}.name")
        start = _integer(entry["day_start"], f"pilot phase {phase_id}.day_start", minimum=1)
        end = _integer(entry["day_end"], f"pilot phase {phase_id}.day_end", minimum=start)
        if start != expected_start:
            raise ResearchReadinessError("pilot phases must be contiguous and start on day 1")
        expected_start = end + 1
        phase_work_packages = set(
            _text_list(entry["work_package_ids"], f"pilot phase {phase_id}.work_package_ids")
        )
        missing = phase_work_packages - work_package_ids
        if missing:
            raise ResearchReadinessError(
                f"pilot phase {phase_id} references unknown work packages: {', '.join(sorted(missing))}"
            )
        assigned_work_package_ids.update(phase_work_packages)
        _text_list(entry["exit_criteria"], f"pilot phase {phase_id}.exit_criteria")
    if expected_start != 91:
        raise ResearchReadinessError("pilot phases must cover days 1 through 90 exactly")
    if assigned_work_package_ids != work_package_ids:
        missing = work_package_ids - assigned_work_package_ids
        raise ResearchReadinessError(
            f"pilot phases do not assign work packages: {', '.join(sorted(missing))}"
        )

    evaluation = _record(
        data["evaluation_design"],
        "pilot.evaluation_design",
        required={
            "design",
            "comparator",
            "primary_endpoint",
            "secondary_endpoints",
            "analysis_boundary",
        },
    )
    if evaluation["design"] != "prospective_preregistered_workflow_evaluation":
        raise ResearchReadinessError("pilot evaluation must remain prospectively preregistered")
    _text(evaluation["comparator"], "pilot.evaluation_design.comparator")
    _text(evaluation["primary_endpoint"], "pilot.evaluation_design.primary_endpoint")
    _text_list(evaluation["secondary_endpoints"], "pilot.evaluation_design.secondary_endpoints")
    _text(evaluation["analysis_boundary"], "pilot.evaluation_design.analysis_boundary")

    gate_ids: set[str] = set()
    for index, item in enumerate(
        _sequence(data["acceptance_gates"], "pilot.acceptance_gates")
    ):
        entry = _record(
            item,
            f"pilot.acceptance_gates[{index}]",
            required={
                "gate_id",
                "metric",
                "operator",
                "threshold",
                "denominator",
                "failure_action",
            },
        )
        gate_id = _text(entry["gate_id"], f"pilot gate {index}.gate_id")
        if gate_id in gate_ids:
            raise ResearchReadinessError(f"duplicate pilot gate_id: {gate_id}")
        if gate_id not in _REQUIRED_GATES:
            raise ResearchReadinessError(f"unsupported pilot gate: {gate_id}")
        _text(entry["metric"], f"pilot gate {gate_id}.metric")
        operator, threshold, failure_action = _REQUIRED_GATES[gate_id]
        if entry["operator"] != operator:
            raise ResearchReadinessError(f"pilot gate {gate_id} operator changed")
        if _number(entry["threshold"], f"pilot gate {gate_id}.threshold") != float(threshold):
            raise ResearchReadinessError(f"pilot gate {gate_id} threshold changed")
        _text(entry["denominator"], f"pilot gate {gate_id}.denominator")
        if entry["failure_action"] != failure_action:
            raise ResearchReadinessError(f"pilot gate {gate_id} failure_action changed")
        gate_ids.add(gate_id)
    if gate_ids != set(_REQUIRED_GATES):
        missing = set(_REQUIRED_GATES) - gate_ids
        raise ResearchReadinessError(
            f"pilot acceptance gates missing: {', '.join(sorted(missing))}"
        )

    governance = _record(
        data["governance"],
        "pilot.governance",
        required={
            "human_approval_required",
            "no_autonomous_wet_lab_execution",
            "no_treatment_recommendation",
            "real_data_release_review_required",
            "stopping_rule",
        },
    )
    for field in (
        "human_approval_required",
        "no_autonomous_wet_lab_execution",
        "no_treatment_recommendation",
        "real_data_release_review_required",
    ):
        if governance[field] is not True:
            raise ResearchReadinessError(f"pilot.governance.{field} must be true")
    _text(governance["stopping_rule"], "pilot.governance.stopping_rule")
    return work_package_ids, gate_ids


def _validate_fit_matrix(
    value: Any,
    *,
    capabilities: Mapping[str, str],
    observations: set[str],
    work_package_ids: set[str],
) -> dict[str, str]:
    priorities: dict[str, str] = {}
    for index, item in enumerate(_sequence(value, "fit_matrix")):
        entry = _record(
            item,
            f"fit_matrix[{index}]",
            required={
                "priority_id",
                "biohub_priority",
                "fit",
                "contribution",
                "current_gap",
                "capability_ids",
                "pilot_work_package_ids",
                "source_observation_ids",
            },
        )
        priority_id = _text(entry["priority_id"], f"fit_matrix[{index}].priority_id")
        if priority_id in priorities:
            raise ResearchReadinessError(f"duplicate priority_id: {priority_id}")
        _text(entry["biohub_priority"], f"fit {priority_id}.biohub_priority")
        fit = entry["fit"]
        if fit not in _FIT_LEVELS:
            raise ResearchReadinessError(f"fit {priority_id} has unsupported fit level")
        _text(entry["contribution"], f"fit {priority_id}.contribution")
        _text(entry["current_gap"], f"fit {priority_id}.current_gap")
        referenced_capabilities = set(
            _text_list(entry["capability_ids"], f"fit {priority_id}.capability_ids")
        )
        if referenced_capabilities - set(capabilities):
            raise ResearchReadinessError(f"fit {priority_id} references unknown capabilities")
        referenced_work = set(
            _text_list(
                entry["pilot_work_package_ids"],
                f"fit {priority_id}.pilot_work_package_ids",
                nonempty=False,
            )
        )
        if referenced_work - work_package_ids:
            raise ResearchReadinessError(f"fit {priority_id} references unknown work packages")
        referenced_observations = set(
            _text_list(
                entry["source_observation_ids"],
                f"fit {priority_id}.source_observation_ids",
            )
        )
        if referenced_observations - observations:
            raise ResearchReadinessError(f"fit {priority_id} references unknown observations")
        priorities[priority_id] = fit
    if not priorities:
        raise ResearchReadinessError("fit_matrix must not be empty")
    return priorities


def _validate_presentation(
    value: Any,
    *,
    root: Path,
    anchors: Mapping[str, str],
    capabilities: Mapping[str, str],
) -> int:
    data = _record(
        value,
        "presentation",
        required={
            "audience",
            "headline_claim",
            "claims",
            "slide_sequence",
            "prohibited_claims",
            "demo_commands",
        },
    )
    _text(data["audience"], "presentation.audience")
    _text(data["headline_claim"], "presentation.headline_claim")
    claims: dict[str, str] = {}
    for index, item in enumerate(_sequence(data["claims"], "presentation.claims")):
        entry = _record(
            item,
            f"presentation.claims[{index}]",
            required={
                "claim_id",
                "text",
                "maturity",
                "evidence_anchor_ids",
                "capability_ids",
            },
        )
        claim_id = _text(entry["claim_id"], f"presentation claim {index}.claim_id")
        if claim_id in claims:
            raise ResearchReadinessError(f"duplicate presentation claim_id: {claim_id}")
        _text(entry["text"], f"presentation claim {claim_id}.text")
        maturity = entry["maturity"]
        if maturity not in _MATURITY_LEVELS:
            raise ResearchReadinessError(f"presentation claim {claim_id} has unsupported maturity")
        anchor_ids = set(
            _text_list(
                entry["evidence_anchor_ids"],
                f"presentation claim {claim_id}.evidence_anchor_ids",
                nonempty=maturity != "proposed_pilot",
            )
        )
        if anchor_ids - set(anchors):
            raise ResearchReadinessError(f"presentation claim {claim_id} references unknown anchors")
        capability_ids = set(
            _text_list(entry["capability_ids"], f"presentation claim {claim_id}.capability_ids")
        )
        if capability_ids - set(capabilities):
            raise ResearchReadinessError(
                f"presentation claim {claim_id} references unknown capabilities"
            )
        capability_maturities = {capabilities[item] for item in capability_ids}
        if capability_maturities != {maturity}:
            raise ResearchReadinessError(
                f"presentation claim {claim_id} maturity does not match its capabilities"
            )
        claims[claim_id] = maturity

    slides = _sequence(data["slide_sequence"], "presentation.slide_sequence")
    used_claim_ids: set[str] = set()
    for index, item in enumerate(slides, start=1):
        entry = _record(
            item,
            f"presentation.slide_sequence[{index - 1}]",
            required={
                "slide",
                "title",
                "purpose",
                "claim_ids",
                "artifact_paths",
                "speaker_boundary",
            },
        )
        if _integer(entry["slide"], f"presentation slide {index}.slide", minimum=1) != index:
            raise ResearchReadinessError("presentation slides must be numbered contiguously from 1")
        _text(entry["title"], f"presentation slide {index}.title")
        _text(entry["purpose"], f"presentation slide {index}.purpose")
        claim_ids = set(
            _text_list(entry["claim_ids"], f"presentation slide {index}.claim_ids", nonempty=False)
        )
        if claim_ids - set(claims):
            raise ResearchReadinessError(f"presentation slide {index} references unknown claims")
        used_claim_ids.update(claim_ids)
        for artifact_index, artifact in enumerate(
            _text_list(entry["artifact_paths"], f"presentation slide {index}.artifact_paths")
        ):
            relative = _relative_path(
                artifact, f"presentation slide {index}.artifact_paths[{artifact_index}]"
            )
            resolved = (root / relative).resolve()
            try:
                resolved.relative_to(root.resolve())
            except ValueError as exc:
                raise ResearchReadinessError(
                    f"presentation slide {index} artifact escapes the repository: {relative}"
                ) from exc
            if not resolved.is_file():
                raise ResearchReadinessError(
                    f"presentation slide {index} artifact is missing: {relative}"
                )
        _text(entry["speaker_boundary"], f"presentation slide {index}.speaker_boundary")
    if len(slides) != 10:
        raise ResearchReadinessError("presentation must retain the reviewed 10-slide sequence")
    if used_claim_ids != set(claims):
        missing = set(claims) - used_claim_ids
        raise ResearchReadinessError(
            f"presentation slides omit claims: {', '.join(sorted(missing))}"
        )

    prohibited = set(
        _text_list(data["prohibited_claims"], "presentation.prohibited_claims")
    )
    missing = _REQUIRED_PROHIBITED_CLAIMS - prohibited
    if missing:
        raise ResearchReadinessError(
            f"presentation missing prohibited claims: {', '.join(sorted(missing))}"
        )
    commands = _text_list(data["demo_commands"], "presentation.demo_commands")
    if not any("adds-research-readiness validate" in command for command in commands):
        raise ResearchReadinessError("presentation demo must include readiness validation")
    if not any("adds-clinical-evidence" in command for command in commands):
        raise ResearchReadinessError("presentation demo must include an executable clinical path")
    return len(slides)


def _validate_known_gaps(value: Any) -> int:
    gap_ids: set[str] = set()
    for index, item in enumerate(_sequence(value, "known_gaps")):
        entry = _record(
            item,
            f"known_gaps[{index}]",
            required={"gap_id", "gap", "status", "closure_evidence_required"},
        )
        gap_id = _text(entry["gap_id"], f"known gap {index}.gap_id")
        if gap_id in gap_ids:
            raise ResearchReadinessError(f"duplicate known gap_id: {gap_id}")
        _text(entry["gap"], f"known gap {gap_id}.gap")
        if entry["status"] != "open":
            raise ResearchReadinessError(f"known gap {gap_id} must remain open")
        _text_list(
            entry["closure_evidence_required"],
            f"known gap {gap_id}.closure_evidence_required",
        )
        gap_ids.add(gap_id)
    if not gap_ids:
        raise ResearchReadinessError("known_gaps must not be empty")
    if gap_ids != _REQUIRED_GAP_IDS:
        missing = _REQUIRED_GAP_IDS - gap_ids
        extra = gap_ids - _REQUIRED_GAP_IDS
        details = []
        if missing:
            details.append(f"missing {', '.join(sorted(missing))}")
        if extra:
            details.append(f"unknown {', '.join(sorted(extra))}")
        raise ResearchReadinessError(
            f"known_gaps must preserve the reviewed gap set ({'; '.join(details)})"
        )
    return len(gap_ids)


def _validate_decision(value: Any) -> dict[str, str]:
    data = _record(
        value,
        "decision",
        required={
            "presentation_readiness",
            "pilot_readiness",
            "public_release_status",
            "next_decision",
        },
    )
    expected = {
        "presentation_readiness": "ready_with_boundaries",
        "pilot_readiness": "ready_for_joint_scoping_not_execution",
        "public_release_status": "candidate_not_merged_or_uploaded",
    }
    for key, value_expected in expected.items():
        if data[key] != value_expected:
            raise ResearchReadinessError(f"decision.{key} must be {value_expected}")
    _text(data["next_decision"], "decision.next_decision")
    return {key: str(data[key]) for key in data}


def validate_research_readiness_profile(
    value: Mapping[str, Any],
    *,
    root: str | Path,
) -> dict[str, Any]:
    """Validate one profile and return a compact, machine-readable summary."""

    profile = _record(value, "profile", required=_TOP_LEVEL_FIELDS)
    if profile["schema_version"] != RESEARCH_READINESS_SCHEMA_VERSION:
        raise ResearchReadinessError("unsupported research-readiness schema_version")
    if profile["profile_id"] != RESEARCH_READINESS_PROFILE_ID:
        raise ResearchReadinessError("unsupported research-readiness profile_id")
    if profile["profile_status"] != "presentation_candidate_not_endorsed":
        raise ResearchReadinessError("profile_status must remain presentation_candidate_not_endorsed")
    assessment_date = _iso_date(profile["assessment_date"], "assessment_date")
    repository_root = Path(root).resolve()
    if not repository_root.is_dir():
        raise ResearchReadinessError("root must be an existing repository directory")

    observations = _validate_organization(
        profile["organization_context"], assessment_date=assessment_date
    )
    _validate_positioning(profile["positioning"])
    anchors = _validate_anchors(profile["evidence_anchors"], root=repository_root)
    capabilities = _validate_maturity(profile["maturity_ledger"], anchors=anchors)
    work_package_ids, gate_ids = _validate_pilot(profile["pilot"])
    priorities = _validate_fit_matrix(
        profile["fit_matrix"],
        capabilities=capabilities,
        observations=observations,
        work_package_ids=work_package_ids,
    )
    slide_count = _validate_presentation(
        profile["presentation"],
        root=repository_root,
        anchors=anchors,
        capabilities=capabilities,
    )
    gap_count = _validate_known_gaps(profile["known_gaps"])
    decision = _validate_decision(profile["decision"])

    expected_integrity = _sha256(profile["integrity_sha256"], "integrity_sha256")
    actual_integrity = research_readiness_integrity_sha256(profile)
    if expected_integrity != actual_integrity:
        raise ResearchReadinessError(
            f"profile integrity mismatch: expected {expected_integrity}, got {actual_integrity}"
        )

    maturity_counts = {
        level: sum(value == level for value in capabilities.values())
        for level in sorted(_MATURITY_LEVELS)
    }
    fit_counts = {
        level: sum(value == level for value in priorities.values())
        for level in sorted(_FIT_LEVELS)
    }
    return {
        "schema_version": RESEARCH_READINESS_SCHEMA_VERSION,
        "profile_id": RESEARCH_READINESS_PROFILE_ID,
        "profile_integrity_sha256": actual_integrity,
        "system_role": RESEARCH_READINESS_SYSTEM_ROLE,
        "official_source_count": len(
            profile["organization_context"]["official_sources"]
        ),
        "evidence_anchor_count": len(anchors),
        "maturity_counts": maturity_counts,
        "fit_counts": fit_counts,
        "pilot_id": profile["pilot"]["pilot_id"],
        "pilot_status": profile["pilot"]["status"],
        "acceptance_gate_count": len(gate_ids),
        "presentation_slide_count": slide_count,
        "known_gap_count": gap_count,
        "presentation_readiness": decision["presentation_readiness"],
        "pilot_readiness": decision["pilot_readiness"],
        "affiliation_claimed": False,
    }


def research_readiness_profile_from_json(
    text: str,
    *,
    root: str | Path,
) -> dict[str, Any]:
    """Parse duplicate-safe JSON, validate it, and return the profile."""

    profile = _load_json(text)
    validate_research_readiness_profile(profile, root=root)
    return profile


def load_research_readiness_profile(
    path: str | Path,
    *,
    root: str | Path,
) -> dict[str, Any]:
    """Load and validate a research-readiness profile from disk."""

    source = Path(path)
    try:
        text = source.read_text(encoding="utf-8")
    except OSError as exc:
        raise ResearchReadinessError(f"cannot read profile {source}: {exc}") from exc
    return research_readiness_profile_from_json(text, root=root)


def research_readiness_summary(
    profile: Mapping[str, Any],
    *,
    root: str | Path,
) -> dict[str, Any]:
    """Validate a profile and return its compact summary."""

    return validate_research_readiness_profile(profile, root=root)
