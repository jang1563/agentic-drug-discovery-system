#!/usr/bin/env python3
"""Build the public informative-cluster-size estimand study."""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from agentic_drug_discovery.clinical_outcome_design_simulation import (
    ClinicalOutcomeDesignGate,
    ClinicalOutcomeDesignMetric,
)
from agentic_drug_discovery.clinical_outcome_informative_cluster_size import (
    ClinicalOutcomeClusterSizeMethod,
    ClinicalOutcomeClusterSizeProfile,
    ClinicalOutcomeInformativeClusterSizeProtocol,
    analyze_clinical_outcome_informative_cluster_size,
    clinical_outcome_informative_cluster_size_protocol_envelope,
    clinical_outcome_informative_cluster_size_report_envelope,
    clinical_outcome_informative_cluster_size_summary,
)
from agentic_drug_discovery.clinical_outcome_stress_simulation import (
    ClinicalOutcomeStressAnalysisMode,
    ClinicalOutcomeStressEstimandTarget,
    ClinicalOutcomeStressScenario,
    ClinicalOutcomeStressSimulationProtocol,
    clinical_outcome_stress_protocol_envelope,
)
from agentic_drug_discovery.ingestion import write_json_artifact
from agentic_drug_discovery.models import Stage


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIRECTORY = ROOT / "rl_env" / "specs"
REFERENCE_LOG_IMOR = -1.996553881874
UNEQUAL_SIZES = (192, 160, 160, 160, 128, 128, 128, 96, 96, 96, 64, 64)


def _scenario(
    scenario_id: str,
    nominal_cluster_sizes: tuple[int, ...],
    favorable_prevalence: float,
) -> ClinicalOutcomeStressScenario:
    return ClinicalOutcomeStressScenario(
        scenario_id=scenario_id,
        stage=Stage.CLINICAL_STRATEGY,
        endpoint_family="composite_benefit_risk",
        nominal_cluster_sizes=nominal_cluster_sizes,
        dependence_blocks=tuple(
            (index,) for index in range(len(nominal_cluster_sizes))
        ),
        favorable_prevalence=favorable_prevalence,
        dependence_block_intraclass_correlation=0.05,
        favorable_evaluable_probability=0.9,
        unfavorable_evaluable_probability=0.55,
        classification_threshold=0.5,
        policy_a_probability_pattern=(0.35,),
        policy_b_probability_pattern=(0.65,),
    )


def _stress_protocol() -> ClinicalOutcomeStressSimulationProtocol:
    return ClinicalOutcomeStressSimulationProtocol(
        protocol_id="synthetic-informative-cluster-size-stress",
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
            _scenario("balanced-null-12", (128,) * 12, 0.5),
            _scenario(
                "dominant-informative-benefit-12",
                (512,) + (128,) * 11,
                0.53,
            ),
            _scenario(
                "unequal-informative-benefit-12",
                UNEQUAL_SIZES,
                0.526086956522,
            ),
            _scenario(
                "unequal-informative-harm-12",
                UNEQUAL_SIZES,
                0.473913043478,
            ),
            _scenario("unequal-null-12", UNEQUAL_SIZES, 0.5),
        ),
        metadata={
            "design_scope": "informative cluster size and estimand drift",
            "public_example": True,
            "real_clinical_outcomes_included": False,
            "prediction_strata": 1,
        },
    )


def _study_protocol(
    stress_protocol: ClinicalOutcomeStressSimulationProtocol,
) -> ClinicalOutcomeInformativeClusterSizeProtocol:
    null_profile = (0.5,) * 12
    benefit_profile = (
        0.74,
        0.62,
        0.62,
        0.62,
        0.5,
        0.5,
        0.5,
        0.38,
        0.38,
        0.38,
        0.26,
        0.26,
    )
    harm_profile = tuple(1.0 - value for value in benefit_profile)
    return ClinicalOutcomeInformativeClusterSizeProtocol(
        protocol_id="synthetic-informative-cluster-size-estimands",
        version="1.0.0",
        registered_on=date(2026, 8, 3),
        stress_protocol_fingerprint=stress_protocol.fingerprint,
        profiles=(
            ClinicalOutcomeClusterSizeProfile(
                scenario_id="balanced-null-12",
                block_favorable_prevalences=null_profile,
            ),
            ClinicalOutcomeClusterSizeProfile(
                scenario_id="dominant-informative-benefit-12",
                block_favorable_prevalences=(0.75,) + (0.45,) * 11,
            ),
            ClinicalOutcomeClusterSizeProfile(
                scenario_id="unequal-informative-benefit-12",
                block_favorable_prevalences=benefit_profile,
            ),
            ClinicalOutcomeClusterSizeProfile(
                scenario_id="unequal-informative-harm-12",
                block_favorable_prevalences=harm_profile,
            ),
            ClinicalOutcomeClusterSizeProfile(
                scenario_id="unequal-null-12",
                block_favorable_prevalences=null_profile,
            ),
        ),
        methods=tuple(ClinicalOutcomeClusterSizeMethod),
        log_imor_grid=(REFERENCE_LOG_IMOR, -1.0, 0.0, 1.0, 2.0),
        reference_log_imor=REFERENCE_LOG_IMOR,
        confidence_level=0.95,
        monte_carlo_confidence_level=0.95,
        coverage_tolerance=0.08,
        minimum_interval_yield=0.95,
        maximum_absolute_bias=0.02,
        minimum_production_clusters=8,
        maximum_production_cluster_unit_fraction=0.15,
        maximum_standard_error_calibration_deviation=0.3,
        primary_metric=ClinicalOutcomeDesignMetric.OBSERVED_FAVORABLE_RATE,
        direction_threshold=0.5,
        metadata={
            "design_scope": "unit-weighted versus cluster-balanced functionals",
            "public_example": True,
            "automatic_estimand_selection": False,
        },
    )


def build(output_directory: Path, *, force: bool) -> dict[str, object]:
    output_directory.mkdir(parents=True, exist_ok=True)
    stress_protocol = _stress_protocol()
    study_protocol = _study_protocol(stress_protocol)
    report = analyze_clinical_outcome_informative_cluster_size(
        study_protocol,
        stress_protocol,
    )
    summary = clinical_outcome_informative_cluster_size_summary(report)
    artifacts = {
        "clinical_outcome_informative_cluster_size_stress_protocol.example.json": (
            clinical_outcome_stress_protocol_envelope(stress_protocol)
        ),
        "clinical_outcome_informative_cluster_size_protocol.example.json": (
            clinical_outcome_informative_cluster_size_protocol_envelope(study_protocol)
        ),
        "clinical_outcome_informative_cluster_size_report.example.json": (
            clinical_outcome_informative_cluster_size_report_envelope(report)
        ),
        "clinical_outcome_informative_cluster_size_summary.example.json": summary,
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
