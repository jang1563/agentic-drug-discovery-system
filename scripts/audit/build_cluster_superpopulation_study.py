#!/usr/bin/env python3
"""Build the public empirical-template cluster-superpopulation study."""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from agentic_drug_discovery.clinical_outcome_cluster_superpopulation import (
    ClinicalOutcomeClusterCountRule,
    ClinicalOutcomeClusterSuperpopulationProtocol,
    ClinicalOutcomeClusterSuperpopulationSamplingModel,
    analyze_clinical_outcome_cluster_superpopulation,
    clinical_outcome_cluster_superpopulation_protocol_envelope,
    clinical_outcome_cluster_superpopulation_report_envelope,
    clinical_outcome_cluster_superpopulation_summary,
)
from agentic_drug_discovery.clinical_outcome_design_simulation import (
    ClinicalOutcomeDesignMetric,
)
from agentic_drug_discovery.clinical_outcome_informative_cluster_size import (
    ClinicalOutcomeClusterInfluenceBasis,
    ClinicalOutcomeClusterSizeEstimand,
    ClinicalOutcomeClusterSizeMethod,
    ClinicalOutcomeClusterSizeStatus,
    ClinicalOutcomeThresholdDirection,
    analyze_clinical_outcome_informative_cluster_size,
)
from agentic_drug_discovery.ingestion import write_json_artifact
from agentic_drug_discovery.models import Stage
from scripts.audit.build_informative_cluster_size_study import (
    _stress_protocol,
    _study_protocol,
)


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIRECTORY = ROOT / "rl_env" / "specs"
SCHEMA_BASE = (
    "https://github.com/jang1563/agentic-drug-discovery-system/rl_env/specs"
)


def _schema_key(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _merge_schemas(schemas: list[dict[str, object]]) -> dict[str, object]:
    unique = {_schema_key(item): item for item in schemas}
    values = list(unique.values())
    if len(values) == 1:
        return values[0]
    types = {item.get("type") for item in values}
    if types <= {"integer", "number"}:
        return {"type": "number"}
    if types == {"object"}:
        keys = set.intersection(
            *(set(item["properties"]) for item in values)  # type: ignore[arg-type]
        )
        if all(set(item["properties"]) == keys for item in values):  # type: ignore[arg-type]
            return {
                "type": "object",
                "additionalProperties": False,
                "required": sorted(keys),
                "properties": {
                    key: _merge_schemas(
                        [item["properties"][key] for item in values]  # type: ignore[index]
                    )
                    for key in sorted(keys)
                },
            }
    if types == {"array"}:
        item_schemas = [item.get("items", {}) for item in values]
        return {
            "type": "array",
            "items": _merge_schemas(item_schemas),  # type: ignore[arg-type]
        }
    alternatives: list[dict[str, object]] = []
    for item in values:
        if set(item) == {"anyOf"}:
            alternatives.extend(item["anyOf"])  # type: ignore[arg-type]
        else:
            alternatives.append(item)
    deduplicated = {
        _schema_key(item): item for item in alternatives
    }
    return {"anyOf": list(deduplicated.values())}


def _infer_schema(value: object, *, key: str | None = None) -> dict[str, object]:
    if key == "metadata":
        return {"type": "object"}
    if value is None:
        return {"type": "null"}
    if isinstance(value, bool):
        return {"type": "boolean"}
    if isinstance(value, int):
        return {"type": "integer"}
    if isinstance(value, float):
        return {"type": "number"}
    if isinstance(value, str):
        return {"type": "string"}
    if isinstance(value, list):
        schema: dict[str, object] = {"type": "array"}
        if value:
            schema["items"] = _merge_schemas(
                [_infer_schema(item, key=key) for item in value]
            )
        return schema
    if isinstance(value, dict):
        return {
            "type": "object",
            "additionalProperties": False,
            "required": sorted(value),
            "properties": {
                item_key: _infer_schema(item, key=item_key)
                for item_key, item in sorted(value.items())
            },
        }
    raise TypeError(f"unsupported schema example value: {type(value).__name__}")


_ENUMS = {
    "sampling_model": [item.value for item in ClinicalOutcomeClusterSuperpopulationSamplingModel],
    "cluster_count_rule": [item.value for item in ClinicalOutcomeClusterCountRule],
    "method": [item.value for item in ClinicalOutcomeClusterSizeMethod],
    "target_estimand": [item.value for item in ClinicalOutcomeClusterSizeEstimand],
    "metric": [item.value for item in ClinicalOutcomeDesignMetric],
    "primary_metric": [item.value for item in ClinicalOutcomeDesignMetric],
    "status": [item.value for item in ClinicalOutcomeClusterSizeStatus],
    "basis": [item.value for item in ClinicalOutcomeClusterInfluenceBasis],
    "stage": [item.value for item in Stage],
    "unit_weighted_reference_direction": [
        item.value for item in ClinicalOutcomeThresholdDirection
    ],
    "cluster_balanced_reference_direction": [
        item.value for item in ClinicalOutcomeThresholdDirection
    ],
}
_NULLABLE_NUMERIC_KEYS = {
    "rate",
    "lower",
    "upper",
    "mean_estimate",
    "target_bias",
    "alternate_estimand_bias",
    "empirical_standard_deviation",
    "monte_carlo_bias_lower",
    "monte_carlo_bias_upper",
    "monte_carlo_absolute_bias_upper",
    "root_mean_squared_reported_standard_error",
    "mean_reported_standard_error",
    "mean_interval_width",
    "interval_width_empirical_standard_deviation",
    "mean_interval_width_monte_carlo_lower",
    "mean_interval_width_monte_carlo_upper",
    "standard_error_to_empirical_sd_ratio",
    "size_outcome_correlation",
    "mean_maximum_absolute_influence",
    "p95_maximum_absolute_influence",
    "mean_maximum_absolute_influence_share",
    "fixed_profile_target_bias",
    "superpopulation_target_bias",
    "target_bias_change",
    "coverage_rate_change",
    "fixed_profile_standard_error_to_empirical_sd_ratio",
    "superpopulation_standard_error_to_empirical_sd_ratio",
    "standard_error_ratio_change",
}
_PROBABILITY_KEYS = {
    "confidence_level",
    "monte_carlo_confidence_level",
    "coverage_tolerance",
    "minimum_interval_yield",
    "maximum_absolute_bias",
    "maximum_production_cluster_unit_fraction",
    "direction_threshold",
    "coverage_target",
    "mean_maximum_cluster_fraction",
    "p95_maximum_cluster_fraction",
    "superpopulation_unit_weighted_favorable_prevalence",
    "superpopulation_cluster_balanced_favorable_prevalence",
    "rate",
    "lower",
    "upper",
}


def _ensure_nullable_number(schema: dict[str, object]) -> dict[str, object]:
    alternatives = schema.get("anyOf")
    if alternatives is not None:
        values = list(alternatives)  # type: ignore[arg-type]
        if not any(item.get("type") == "null" for item in values):
            values.append({"type": "null"})
        if not any(item.get("type") in {"integer", "number"} for item in values):
            values.append({"type": "number"})
        return {"anyOf": values}
    if schema.get("type") == "null":
        return {"anyOf": [{"type": "number"}, {"type": "null"}]}
    return {"anyOf": [dict(schema), {"type": "null"}]}


def _annotate_schema(schema: dict[str, object], *, key: str | None = None) -> None:
    if key in _ENUMS:
        schema.clear()
        schema.update({"type": "string", "enum": _ENUMS[key]})
        return
    if key in _NULLABLE_NUMERIC_KEYS:
        replacement = _ensure_nullable_number(schema)
        schema.clear()
        schema.update(replacement)
    if key == "registered_on":
        schema.update({"format": "date"})
    if key and (
        key == "integrity_sha256"
        or key.endswith("_fingerprint")
        or key.endswith("_sha256")
    ):
        schema.update({"pattern": "^[0-9a-f]{64}$"})
    if key and (key.endswith("_id") or key in {"version", "endpoint_family"}):
        schema.update({"minLength": 1})
    if key in _PROBABILITY_KEYS:
        schema.update({"minimum": 0.0, "maximum": 1.0})
    if key and (key == "count" or key.endswith("_count")):
        schema.update({"minimum": 0})
    if key in {"replicates", "replicate_count", "sampled_cluster_count", "template_type_count"}:
        schema.update({"minimum": 1})
    if key == "random_seed":
        schema.update({"minimum": 0, "maximum": 2**63 - 1})
    if key in {"methods", "status_counts"}:
        schema.update({"minItems": len(ClinicalOutcomeClusterSizeMethod) if key == "methods" else len(ClinicalOutcomeClusterSizeStatus), "maxItems": len(ClinicalOutcomeClusterSizeMethod) if key == "methods" else len(ClinicalOutcomeClusterSizeStatus)})
    if key == "methods":
        schema["uniqueItems"] = True
    if key == "methods" and isinstance(schema.get("items"), dict) and schema[
        "items"
    ].get("type") == "string":
        schema["items"] = {
            "type": "string",
            "enum": [item.value for item in ClinicalOutcomeClusterSizeMethod],
        }
        return
    if key in {
        "log_imor_grid",
        "scenario_results",
        "method_results",
        "metric_inference",
        "grid_inference",
        "conditional_comparisons",
        "influence_diagnostics",
        "template_cluster_sizes",
        "template_favorable_prevalences",
        "scenarios",
    }:
        schema.update({"minItems": 1})
    if key in {"method_results", "influence_diagnostics"}:
        schema["maxItems"] = len(ClinicalOutcomeClusterSizeMethod)
    if key == "metric_inference":
        schema["maxItems"] = len(ClinicalOutcomeDesignMetric)
    if key == "template_cluster_sizes":
        schema["items"] = {"type": "integer", "minimum": 1}
    if key == "template_favorable_prevalences":
        schema["items"] = {
            "type": "number",
            "exclusiveMinimum": 0.0,
            "exclusiveMaximum": 1.0,
        }
    if key == "log_imor_grid":
        schema.update({"uniqueItems": True})
    properties = schema.get("properties")
    if isinstance(properties, dict):
        for child_key, child_schema in properties.items():
            _annotate_schema(child_schema, key=child_key)
    items = schema.get("items")
    if isinstance(items, dict):
        _annotate_schema(items, key=None)
    alternatives = schema.get("anyOf")
    if isinstance(alternatives, list):
        for item in alternatives:
            _annotate_schema(item, key=None)


def _artifact_schema(
    artifact: dict[str, object],
    *,
    filename: str,
    title: str,
    description: str,
) -> dict[str, object]:
    schema = _infer_schema(artifact)
    schema.update(
        {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": f"{SCHEMA_BASE}/{filename}",
            "title": title,
            "description": description,
        }
    )
    _annotate_schema(schema)
    properties = schema["properties"]
    properties["schema_version"] = {  # type: ignore[index]
        "const": artifact["schema_version"]
    }
    payload = artifact.get("protocol") or artifact.get("report")
    if isinstance(payload, dict):
        payload_name = "protocol" if "protocol" in artifact else "report"
        payload_properties = properties[payload_name]["properties"]  # type: ignore[index]
        for field_name in ("method_id", "rng_method_id"):
            if field_name in payload:
                payload_properties[field_name] = {"const": payload[field_name]}
        if "limitations" in payload:
            payload_properties["limitations"] = {"const": payload["limitations"]}
        for field_name, value in payload.items():
            if isinstance(value, bool) and field_name not in {"metadata"}:
                payload_properties[field_name] = {"const": value}
    return schema


def _superpopulation_protocol(
    *,
    stress_protocol,
    fixed_profile_protocol,
    fixed_profile_report,
) -> ClinicalOutcomeClusterSuperpopulationProtocol:
    return ClinicalOutcomeClusterSuperpopulationProtocol(
        protocol_id="synthetic-cluster-superpopulation-calibration",
        version="1.0.0",
        registered_on=date(2026, 8, 3),
        stress_protocol_fingerprint=stress_protocol.fingerprint,
        fixed_profile_protocol_fingerprint=fixed_profile_protocol.fingerprint,
        fixed_profile_report_fingerprint=fixed_profile_report.fingerprint,
        sampling_model=(
            ClinicalOutcomeClusterSuperpopulationSamplingModel.UNIFORM_EMPIRICAL_TEMPLATE_WITH_REPLACEMENT
        ),
        cluster_count_rule=ClinicalOutcomeClusterCountRule.MATCH_TEMPLATE_COUNT,
        replicates=fixed_profile_report.replicates,
        random_seed=20260804,
        methods=fixed_profile_protocol.methods,
        log_imor_grid=fixed_profile_protocol.log_imor_grid,
        reference_log_imor=fixed_profile_protocol.reference_log_imor,
        confidence_level=fixed_profile_protocol.confidence_level,
        monte_carlo_confidence_level=(
            fixed_profile_protocol.monte_carlo_confidence_level
        ),
        coverage_tolerance=fixed_profile_protocol.coverage_tolerance,
        minimum_interval_yield=fixed_profile_protocol.minimum_interval_yield,
        maximum_absolute_bias=fixed_profile_protocol.maximum_absolute_bias,
        minimum_production_clusters=(
            fixed_profile_protocol.minimum_production_clusters
        ),
        maximum_production_cluster_unit_fraction=(
            fixed_profile_protocol.maximum_production_cluster_unit_fraction
        ),
        maximum_standard_error_calibration_deviation=(
            fixed_profile_protocol.maximum_standard_error_calibration_deviation
        ),
        primary_metric=fixed_profile_protocol.primary_metric,
        direction_threshold=fixed_profile_protocol.direction_threshold,
        metadata={
            "design_scope": (
                "conditional versus empirical-template cluster-superpopulation "
                "interval calibration"
            ),
            "public_example": True,
            "sampling_frame": "finite empirical template support",
            "post_hoc_design_filtering": False,
        },
    )


def build(output_directory: Path, *, force: bool) -> dict[str, object]:
    output_directory.mkdir(parents=True, exist_ok=True)
    stress_protocol = _stress_protocol()
    fixed_profile_protocol = _study_protocol(stress_protocol)
    fixed_profile_report = analyze_clinical_outcome_informative_cluster_size(
        fixed_profile_protocol,
        stress_protocol,
    )
    protocol = _superpopulation_protocol(
        stress_protocol=stress_protocol,
        fixed_profile_protocol=fixed_profile_protocol,
        fixed_profile_report=fixed_profile_report,
    )
    report = analyze_clinical_outcome_cluster_superpopulation(
        protocol,
        stress_protocol,
        fixed_profile_protocol,
        fixed_profile_report,
    )
    summary = clinical_outcome_cluster_superpopulation_summary(report)
    protocol_artifact = clinical_outcome_cluster_superpopulation_protocol_envelope(
        protocol
    )
    report_artifact = clinical_outcome_cluster_superpopulation_report_envelope(
        report
    )
    artifacts = {
        "clinical_outcome_cluster_superpopulation_protocol.schema.json": (
            _artifact_schema(
                protocol_artifact,
                filename=(
                    "clinical_outcome_cluster_superpopulation_protocol.schema.json"
                ),
                title="Clinical outcome cluster-superpopulation protocol",
                description=(
                    "Strict preregistration contract for empirical-template cluster "
                    "superpopulation calibration."
                ),
            )
        ),
        "clinical_outcome_cluster_superpopulation_protocol.example.json": (
            protocol_artifact
        ),
        "clinical_outcome_cluster_superpopulation_report.schema.json": (
            _artifact_schema(
                report_artifact,
                filename=(
                    "clinical_outcome_cluster_superpopulation_report.schema.json"
                ),
                title="Clinical outcome cluster-superpopulation report",
                description=(
                    "Aggregate conditional-versus-superpopulation calibration, "
                    "realized-design, and influence report."
                ),
            )
        ),
        "clinical_outcome_cluster_superpopulation_report.example.json": (
            report_artifact
        ),
        "clinical_outcome_cluster_superpopulation_summary.schema.json": (
            _artifact_schema(
                summary,
                filename=(
                    "clinical_outcome_cluster_superpopulation_summary.schema.json"
                ),
                title="Clinical outcome cluster-superpopulation summary",
                description=(
                    "Compact human- and machine-readable projection of the public "
                    "cluster-superpopulation calibration report."
                ),
            )
        ),
        "clinical_outcome_cluster_superpopulation_summary.example.json": summary,
    }
    for filename, artifact in artifacts.items():
        write_json_artifact(
            output_directory / filename,
            artifact,
            force=force,
        )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-directory",
        type=Path,
        default=DEFAULT_OUTPUT_DIRECTORY,
    )
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    summary = build(args.output_directory, force=args.force)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
