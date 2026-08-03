#!/usr/bin/env python3
"""Build and audit the public unequal-cluster pattern-mixture study."""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from agentic_drug_discovery import (
    ClinicalOutcomeDesignGate,
    ClinicalOutcomeDesignMetric,
    ClinicalOutcomePatternMixtureInfluenceProtocol,
    ClinicalOutcomePatternMixtureIntervalMethod,
    ClinicalOutcomePatternMixtureProtocol,
    ClinicalOutcomeStressAnalysisMode,
    ClinicalOutcomeStressEstimandTarget,
    ClinicalOutcomeStressScenario,
    ClinicalOutcomeStressSimulationProtocol,
    Stage,
    analyze_clinical_outcome_pattern_mixture,
    analyze_clinical_outcome_pattern_mixture_influence_calibration,
    clinical_outcome_pattern_mixture_influence_calibration_summary,
    clinical_outcome_pattern_mixture_influence_protocol_envelope,
    clinical_outcome_pattern_mixture_influence_report_envelope,
    clinical_outcome_pattern_mixture_protocol_envelope,
    clinical_outcome_pattern_mixture_report_envelope,
    clinical_outcome_stress_protocol_envelope,
)
from agentic_drug_discovery.ingestion import write_json_artifact


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIRECTORY = ROOT / "rl_env" / "specs"


def _scenario(
    scenario_id: str,
    nominal_cluster_sizes: tuple[int, ...],
) -> ClinicalOutcomeStressScenario:
    return ClinicalOutcomeStressScenario(
        scenario_id=scenario_id,
        stage=Stage.CLINICAL_STRATEGY,
        endpoint_family="composite_benefit_risk",
        nominal_cluster_sizes=nominal_cluster_sizes,
        dependence_blocks=tuple(
            (index,) for index in range(len(nominal_cluster_sizes))
        ),
        favorable_prevalence=0.42,
        dependence_block_intraclass_correlation=0.15,
        favorable_evaluable_probability=0.9,
        unfavorable_evaluable_probability=0.55,
        classification_threshold=0.5,
        policy_a_probability_pattern=(0.2, 0.4, 0.6, 0.8),
        policy_b_probability_pattern=(0.3, 0.5, 0.7, 0.9),
    )


def _stress_protocol() -> ClinicalOutcomeStressSimulationProtocol:
    return ClinicalOutcomeStressSimulationProtocol(
        protocol_id="synthetic-unequal-cluster-influence-stress",
        version="1.0.0",
        registered_on=date(2026, 8, 3),
        confidence_level=0.95,
        monte_carlo_confidence_level=0.95,
        replicates=500,
        random_seed=20260803,
        coverage_tolerance=0.08,
        minimum_interval_yield=0.95,
        analysis_modes=tuple(ClinicalOutcomeStressAnalysisMode),
        estimand_targets=tuple(ClinicalOutcomeStressEstimandTarget),
        gates=(
            ClinicalOutcomeDesignGate(
                gate_id="production-g08-share15",
                minimum_evaluable_clusters=8,
                maximum_evaluable_cluster_fraction=0.15,
            ),
        ),
        scenarios=(
            _scenario("balanced-few-8", (16,) * 8),
            _scenario("balanced-reference-12", (16,) * 12),
            _scenario("dominant-cluster-12", (64,) + (16,) * 11),
            _scenario(
                "unequal-clusters-12",
                (24, 20, 20, 20, 16, 16, 16, 12, 12, 12, 8, 8),
            ),
        ),
        metadata={
            "design_scope": "synthetic unequal-cluster influence calibration",
            "public_example": True,
            "real_clinical_outcomes_included": False,
        },
    )


def _pattern_protocol(
    stress_protocol: ClinicalOutcomeStressSimulationProtocol,
) -> ClinicalOutcomePatternMixtureProtocol:
    return ClinicalOutcomePatternMixtureProtocol(
        protocol_id="synthetic-unequal-cluster-pattern-mixture",
        version="1.0.0",
        registered_on=date(2026, 8, 3),
        stress_protocol_fingerprint=stress_protocol.fingerprint,
        log_imor_grid=(-2.0, -1.0, 0.0, 1.0, 2.0),
        monte_carlo_confidence_level=0.95,
        minimum_analyzable_rate=0.95,
        maximum_mean_identification_width=0.5,
        maximum_absolute_bias=0.02,
        metadata={
            "design_scope": "binary log-IMOR influence-calibration anchor",
            "public_example": True,
        },
    )


def _influence_protocol(
    stress_protocol: ClinicalOutcomeStressSimulationProtocol,
    pattern_protocol: ClinicalOutcomePatternMixtureProtocol,
    pattern_report_fingerprint: str,
) -> ClinicalOutcomePatternMixtureInfluenceProtocol:
    return ClinicalOutcomePatternMixtureInfluenceProtocol(
        protocol_id="synthetic-unequal-cluster-influence-calibration",
        version="1.0.0",
        registered_on=date(2026, 8, 3),
        stress_protocol_fingerprint=stress_protocol.fingerprint,
        pattern_mixture_protocol_fingerprint=pattern_protocol.fingerprint,
        pattern_mixture_report_fingerprint=pattern_report_fingerprint,
        methods=tuple(ClinicalOutcomePatternMixtureIntervalMethod),
        confidence_level=0.95,
        monte_carlo_confidence_level=0.95,
        coverage_tolerance=0.08,
        minimum_interval_yield=0.95,
        minimum_production_clusters=8,
        maximum_production_cluster_unit_fraction=0.15,
        maximum_standard_error_calibration_deviation=0.2,
        multiplier_draws=99,
        multiplier_seed=20260803,
        primary_metric=ClinicalOutcomeDesignMetric.OBSERVED_FAVORABLE_RATE,
        metadata={
            "design_scope": "unequal and influential dependence-block calibration",
            "public_example": True,
            "webb_method_operational": False,
        },
    )


def build(output_directory: Path, *, force: bool) -> dict[str, object]:
    output_directory.mkdir(parents=True, exist_ok=True)
    stress_protocol = _stress_protocol()
    pattern_protocol = _pattern_protocol(stress_protocol)
    pattern_report = analyze_clinical_outcome_pattern_mixture(
        pattern_protocol,
        stress_protocol,
    )
    influence_protocol = _influence_protocol(
        stress_protocol,
        pattern_protocol,
        pattern_report.fingerprint,
    )
    influence_report = analyze_clinical_outcome_pattern_mixture_influence_calibration(
        influence_protocol,
        pattern_protocol,
        stress_protocol,
    )
    summary = clinical_outcome_pattern_mixture_influence_calibration_summary(
        influence_report
    )
    artifacts = {
        "clinical_outcome_pattern_mixture_influence_stress_protocol.example.json": (
            clinical_outcome_stress_protocol_envelope(stress_protocol)
        ),
        "clinical_outcome_pattern_mixture_influence_pattern_protocol.example.json": (
            clinical_outcome_pattern_mixture_protocol_envelope(pattern_protocol)
        ),
        "clinical_outcome_pattern_mixture_influence_pattern_report.example.json": (
            clinical_outcome_pattern_mixture_report_envelope(pattern_report)
        ),
        "clinical_outcome_pattern_mixture_influence_protocol.example.json": (
            clinical_outcome_pattern_mixture_influence_protocol_envelope(
                influence_protocol
            )
        ),
        "clinical_outcome_pattern_mixture_influence_report.example.json": (
            clinical_outcome_pattern_mixture_influence_report_envelope(influence_report)
        ),
        "clinical_outcome_pattern_mixture_influence_summary.example.json": summary,
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
