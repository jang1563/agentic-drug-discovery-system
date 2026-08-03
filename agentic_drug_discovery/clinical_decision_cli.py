"""Command-line compiler and validator for clinical evidence packages."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence, TextIO

from .clinical_cohort import (
    ClinicalCohortError,
    clinical_cohort_manifest_from_json,
    clinical_cohort_report_envelope,
    clinical_cohort_report_from_json,
    clinical_cohort_report_summary,
    clinical_cohort_validation_report,
    compile_clinical_cohort_report,
    validate_clinical_cohort_report,
)
from .clinical_decision import (
    ClinicalDecisionError,
    clinical_decision_package_envelope,
    clinical_decision_package_from_json,
)
from .clinical_outcome_evaluation import (
    ClinicalOutcomeEvaluationError,
    clinical_outcome_evaluation_summary,
    clinical_outcome_manifest_from_json,
    clinical_outcome_protocol_from_json,
    clinical_outcome_report_envelope,
    clinical_outcome_report_from_json,
    clinical_outcome_validation_summary,
    clinical_prediction_submission_from_json,
    evaluate_clinical_outcomes,
    validate_clinical_outcome_evaluation_report,
)
from .clinical_outcome_design_simulation import (
    ClinicalOutcomeDesignSimulationError,
    clinical_outcome_design_protocol_from_json,
    clinical_outcome_design_report_envelope,
    clinical_outcome_design_report_from_json,
    clinical_outcome_design_simulation_summary,
    clinical_outcome_design_simulation_validation_summary,
    simulate_clinical_outcome_uncertainty_design,
    validate_clinical_outcome_design_simulation_report,
)
from .clinical_outcome_stress_simulation import (
    ClinicalOutcomeStressSimulationError,
    clinical_outcome_stress_protocol_from_json,
    clinical_outcome_stress_report_envelope,
    clinical_outcome_stress_report_from_json,
    clinical_outcome_stress_simulation_summary,
    clinical_outcome_stress_simulation_validation_summary,
    simulate_clinical_outcome_stress,
    validate_clinical_outcome_stress_simulation_report,
)
from .clinical_outcome_pattern_mixture import (
    ClinicalOutcomePatternMixtureError,
    analyze_clinical_outcome_pattern_mixture,
    clinical_outcome_pattern_mixture_protocol_from_json,
    clinical_outcome_pattern_mixture_report_envelope,
    clinical_outcome_pattern_mixture_report_from_json,
    clinical_outcome_pattern_mixture_summary,
    clinical_outcome_pattern_mixture_validation_summary,
    validate_clinical_outcome_pattern_mixture_report,
)
from .clinical_outcome_pattern_mixture_uncertainty import (
    ClinicalOutcomePatternMixtureUncertaintyError,
    analyze_clinical_outcome_pattern_mixture_uncertainty,
    clinical_outcome_pattern_mixture_uncertainty_protocol_from_json,
    clinical_outcome_pattern_mixture_uncertainty_report_envelope,
    clinical_outcome_pattern_mixture_uncertainty_report_from_json,
    clinical_outcome_pattern_mixture_uncertainty_summary,
    clinical_outcome_pattern_mixture_uncertainty_validation_summary,
    validate_clinical_outcome_pattern_mixture_uncertainty_report,
)
from .clinical_outcome_pattern_mixture_influence_calibration import (
    ClinicalOutcomePatternMixtureInfluenceError,
    analyze_clinical_outcome_pattern_mixture_influence_calibration,
    clinical_outcome_pattern_mixture_influence_calibration_summary,
    clinical_outcome_pattern_mixture_influence_calibration_validation_summary,
    clinical_outcome_pattern_mixture_influence_protocol_from_json,
    clinical_outcome_pattern_mixture_influence_report_envelope,
    clinical_outcome_pattern_mixture_influence_report_from_json,
    validate_clinical_outcome_pattern_mixture_influence_calibration_report,
)
from .clinical_outcome_informative_cluster_size import (
    ClinicalOutcomeInformativeClusterSizeError,
    analyze_clinical_outcome_informative_cluster_size,
    clinical_outcome_informative_cluster_size_protocol_from_json,
    clinical_outcome_informative_cluster_size_report_envelope,
    clinical_outcome_informative_cluster_size_report_from_json,
    clinical_outcome_informative_cluster_size_summary,
    clinical_outcome_informative_cluster_size_validation_summary,
    validate_clinical_outcome_informative_cluster_size_report,
)
from .clinical_outcome_uncertainty import (
    ClinicalOutcomeUncertaintyError,
    clinical_outcome_dependence_manifest_from_json,
    clinical_outcome_uncertainty_protocol_from_json,
    clinical_outcome_uncertainty_report_envelope,
    clinical_outcome_uncertainty_report_from_json,
    clinical_outcome_uncertainty_summary,
    clinical_outcome_uncertainty_validation_summary,
    evaluate_clinical_outcome_uncertainty,
    validate_clinical_outcome_uncertainty_report,
)
from .clinical_workflow import (
    ClinicalEvidenceWorkflowError,
    clinical_decision_config_from_json,
    clinical_decision_package_summary,
    clinical_decision_validation_report,
    compile_clinical_decision_from_config,
)
from .ingestion import write_json_artifact
from .serialization import RecordParseError, program_state_from_dict


def _read_text(path: str, label: str) -> str:
    try:
        return sys.stdin.read() if path == "-" else Path(path).read_text("utf-8")
    except OSError as exc:
        raise ValueError(f"{label} is not readable") from exc


def _strict_json(payload: str, label: str) -> Any:
    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise RecordParseError(f"{label} duplicates key {key}")
            result[key] = value
        return result

    def reject_constant(value: str) -> Any:
        raise RecordParseError(f"{label} contains {value}")

    try:
        return json.loads(
            payload,
            object_pairs_hook=unique_object,
            parse_constant=reject_constant,
        )
    except json.JSONDecodeError as exc:
        raise RecordParseError(f"{label} is not valid JSON") from exc


def _state(path: str):
    return program_state_from_dict(
        _strict_json(_read_text(path, "program state"), "program state")
    )


def _package(path: str):
    return clinical_decision_package_from_json(
        _read_text(path, "clinical decision package")
    )


def _cohort_manifest(path: str):
    return clinical_cohort_manifest_from_json(
        _read_text(path, "clinical cohort manifest")
    )


def _cohort_report(path: str):
    return clinical_cohort_report_from_json(
        _read_text(path, "clinical cohort report")
    )


def _outcome_protocol(path: str):
    return clinical_outcome_protocol_from_json(
        _read_text(path, "clinical outcome protocol")
    )


def _prediction_submission(path: str):
    return clinical_prediction_submission_from_json(
        _read_text(path, "clinical prediction submission")
    )


def _outcome_manifest(path: str):
    return clinical_outcome_manifest_from_json(
        _read_text(path, "clinical outcome manifest")
    )


def _outcome_report(path: str):
    return clinical_outcome_report_from_json(
        _read_text(path, "clinical outcome evaluation report")
    )


def _dependence_manifest(path: str):
    return clinical_outcome_dependence_manifest_from_json(
        _read_text(path, "clinical outcome dependence manifest")
    )


def _uncertainty_protocol(path: str):
    return clinical_outcome_uncertainty_protocol_from_json(
        _read_text(path, "clinical outcome uncertainty protocol")
    )


def _uncertainty_report(path: str):
    return clinical_outcome_uncertainty_report_from_json(
        _read_text(path, "clinical outcome uncertainty report")
    )


def _design_protocol(path: str):
    return clinical_outcome_design_protocol_from_json(
        _read_text(path, "clinical outcome design simulation protocol")
    )


def _design_report(path: str):
    return clinical_outcome_design_report_from_json(
        _read_text(path, "clinical outcome design simulation report")
    )


def _stress_protocol(path: str):
    return clinical_outcome_stress_protocol_from_json(
        _read_text(path, "clinical outcome stress simulation protocol")
    )


def _stress_report(path: str):
    return clinical_outcome_stress_report_from_json(
        _read_text(path, "clinical outcome stress simulation report")
    )


def _pattern_mixture_protocol(path: str):
    return clinical_outcome_pattern_mixture_protocol_from_json(
        _read_text(path, "clinical outcome pattern-mixture protocol")
    )


def _pattern_mixture_report(path: str):
    return clinical_outcome_pattern_mixture_report_from_json(
        _read_text(path, "clinical outcome pattern-mixture report")
    )


def _pattern_mixture_uncertainty_protocol(path: str):
    return clinical_outcome_pattern_mixture_uncertainty_protocol_from_json(
        _read_text(path, "clinical outcome pattern-mixture uncertainty protocol")
    )


def _pattern_mixture_uncertainty_report(path: str):
    return clinical_outcome_pattern_mixture_uncertainty_report_from_json(
        _read_text(path, "clinical outcome pattern-mixture uncertainty report")
    )


def _pattern_mixture_influence_protocol(path: str):
    return clinical_outcome_pattern_mixture_influence_protocol_from_json(
        _read_text(path, "clinical outcome pattern-mixture influence protocol")
    )


def _pattern_mixture_influence_report(path: str):
    return clinical_outcome_pattern_mixture_influence_report_from_json(
        _read_text(path, "clinical outcome pattern-mixture influence report")
    )


def _informative_cluster_size_protocol(path: str):
    return clinical_outcome_informative_cluster_size_protocol_from_json(
        _read_text(path, "clinical outcome informative-cluster-size protocol")
    )


def _informative_cluster_size_report(path: str):
    return clinical_outcome_informative_cluster_size_report_from_json(
        _read_text(path, "clinical outcome informative-cluster-size report")
    )


def _require_single_stdin(paths: Sequence[str | None]) -> None:
    if sum(path == "-" for path in paths) > 1:
        raise ValueError("only one input may read from stdin")


def _print_json(value: Any, stream: TextIO = sys.stdout) -> None:
    print(json.dumps(value, indent=2, sort_keys=True), file=stream)


def _compile(args: argparse.Namespace) -> int:
    if args.state == "-" and args.config == "-":
        raise ValueError("--state and --config cannot both read from stdin")
    state = _state(args.state)
    config = clinical_decision_config_from_json(
        _read_text(args.config, "clinical decision config")
    )
    package = compile_clinical_decision_from_config(state, config)
    envelope = clinical_decision_package_envelope(package)
    if args.output == "-":
        _print_json(envelope)
        return 0
    output = write_json_artifact(args.output, envelope, force=args.force)
    report = clinical_decision_validation_report(package, state=state)
    if not output.is_file():
        raise OSError("clinical decision package output was not created")
    _print_json(report)
    return 0


def _validate(args: argparse.Namespace) -> int:
    if args.package == "-" and args.state == "-":
        raise ValueError("--package and --state cannot both read from stdin")
    package = _package(args.package)
    state = None if args.state is None else _state(args.state)
    report = clinical_decision_validation_report(package, state=state)
    _print_json(report)
    return 0 if report["validation"]["status"] == "valid" else 1


def _summarize(args: argparse.Namespace) -> int:
    _print_json(clinical_decision_package_summary(_package(args.package)))
    return 0


def _compile_cohort(args: argparse.Namespace) -> int:
    _require_single_stdin((args.manifest, *args.package, *args.state))
    manifest = _cohort_manifest(args.manifest)
    packages = tuple(_package(path) for path in args.package)
    states = tuple(_state(path) for path in args.state)
    report = compile_clinical_cohort_report(
        manifest,
        packages,
        states=states,
    )
    envelope = clinical_cohort_report_envelope(report)
    if args.output == "-":
        _print_json(envelope)
        return 0
    output = write_json_artifact(args.output, envelope, force=args.force)
    if not output.is_file():
        raise OSError("clinical cohort report output was not created")
    _print_json(
        clinical_cohort_validation_report(
            report,
            scope=(
                "integrity_aggregate_manifest_package_and_state_replay"
                if states
                else "integrity_aggregate_and_manifest_package_binding"
            ),
        )
    )
    return 0


def _validate_cohort(args: argparse.Namespace) -> int:
    if args.manifest is None and (args.package or args.state):
        raise ValueError("--package and --state require --manifest")
    if args.manifest is not None and not args.package:
        raise ValueError("--manifest validation requires at least one --package")
    paths = (args.report, args.manifest, *args.package, *args.state)
    _require_single_stdin(paths)
    report = _cohort_report(args.report)
    failures: tuple[str, ...] = ()
    scope = "integrity_and_aggregate_consistency"
    if args.manifest is not None:
        manifest = _cohort_manifest(args.manifest)
        packages = tuple(_package(path) for path in args.package)
        states = tuple(_state(path) for path in args.state)
        failures = validate_clinical_cohort_report(
            report,
            manifest,
            packages,
            states=states,
        )
        scope = (
            "integrity_aggregate_manifest_package_and_state_replay"
            if states
            else "integrity_aggregate_and_manifest_package_binding"
        )
    validation = clinical_cohort_validation_report(
        report,
        failures=failures,
        scope=scope,
    )
    _print_json(validation)
    return 0 if not failures else 1


def _summarize_cohort(args: argparse.Namespace) -> int:
    _print_json(clinical_cohort_report_summary(_cohort_report(args.report)))
    return 0


def _evaluate_outcomes(args: argparse.Namespace) -> int:
    _require_single_stdin(
        (
            args.protocol,
            args.cohort_report,
            *args.submission,
            args.outcomes,
        )
    )
    protocol = _outcome_protocol(args.protocol)
    cohort_report = _cohort_report(args.cohort_report)
    submissions = tuple(_prediction_submission(path) for path in args.submission)
    outcome_manifest = _outcome_manifest(args.outcomes)
    report = evaluate_clinical_outcomes(
        protocol,
        cohort_report,
        submissions,
        outcome_manifest,
    )
    envelope = clinical_outcome_report_envelope(report)
    if args.output == "-":
        _print_json(envelope)
        return 0
    output = write_json_artifact(args.output, envelope, force=args.force)
    if not output.is_file():
        raise OSError("clinical outcome report output was not created")
    _print_json(
        clinical_outcome_validation_summary(
            report,
            scope="full_protocol_cohort_submission_and_outcome_replay",
        )
    )
    return 0


def _validate_outcomes(args: argparse.Namespace) -> int:
    replay_paths = (
        args.protocol,
        args.cohort_report,
        args.outcomes,
    )
    replay_requested = any(path is not None for path in replay_paths) or bool(
        args.submission
    )
    if replay_requested and (
        any(path is None for path in replay_paths) or not args.submission
    ):
        raise ValueError(
            "full outcome replay requires --protocol, --cohort-report, "
            "--submission, and --outcomes"
        )
    _require_single_stdin(
        (
            args.report,
            args.protocol,
            args.cohort_report,
            *args.submission,
            args.outcomes,
        )
    )
    report = _outcome_report(args.report)
    failures: tuple[str, ...] = ()
    scope = "integrity_and_aggregate_consistency"
    if replay_requested:
        assert args.protocol is not None
        assert args.cohort_report is not None
        assert args.outcomes is not None
        failures = validate_clinical_outcome_evaluation_report(
            report,
            _outcome_protocol(args.protocol),
            _cohort_report(args.cohort_report),
            tuple(_prediction_submission(path) for path in args.submission),
            _outcome_manifest(args.outcomes),
        )
        scope = "full_protocol_cohort_submission_and_outcome_replay"
    validation = clinical_outcome_validation_summary(
        report,
        failures=failures,
        scope=scope,
    )
    _print_json(validation)
    return 0 if not failures else 1


def _summarize_outcomes(args: argparse.Namespace) -> int:
    _print_json(clinical_outcome_evaluation_summary(_outcome_report(args.report)))
    return 0


def _evaluate_uncertainty(args: argparse.Namespace) -> int:
    _require_single_stdin(
        (
            args.uncertainty_protocol,
            args.dependence_manifest,
            args.outcome_protocol,
            args.cohort_report,
            *args.submission,
            args.outcomes,
            args.outcome_report,
        )
    )
    report = evaluate_clinical_outcome_uncertainty(
        _uncertainty_protocol(args.uncertainty_protocol),
        _dependence_manifest(args.dependence_manifest),
        _outcome_protocol(args.outcome_protocol),
        _cohort_report(args.cohort_report),
        tuple(_prediction_submission(path) for path in args.submission),
        _outcome_manifest(args.outcomes),
        _outcome_report(args.outcome_report),
    )
    envelope = clinical_outcome_uncertainty_report_envelope(report)
    if args.output == "-":
        _print_json(envelope)
        return 0
    output = write_json_artifact(args.output, envelope, force=args.force)
    if not output.is_file():
        raise OSError("clinical outcome uncertainty report output was not created")
    _print_json(
        clinical_outcome_uncertainty_validation_summary(
            report,
            scope="full_dependence_and_private_outcome_replay",
        )
    )
    return 0


def _validate_uncertainty(args: argparse.Namespace) -> int:
    replay_paths = (
        args.uncertainty_protocol,
        args.dependence_manifest,
        args.outcome_protocol,
        args.cohort_report,
        args.outcomes,
        args.outcome_report,
    )
    replay_requested = any(path is not None for path in replay_paths) or bool(
        args.submission
    )
    if replay_requested and (
        any(path is None for path in replay_paths) or not args.submission
    ):
        raise ValueError(
            "full uncertainty replay requires --uncertainty-protocol, "
            "--dependence-manifest, --outcome-protocol, --cohort-report, "
            "--submission, --outcomes, and --outcome-report"
        )
    _require_single_stdin(
        (
            args.report,
            args.uncertainty_protocol,
            args.dependence_manifest,
            args.outcome_protocol,
            args.cohort_report,
            *args.submission,
            args.outcomes,
            args.outcome_report,
        )
    )
    report = _uncertainty_report(args.report)
    failures: tuple[str, ...] = ()
    scope = "integrity_and_aggregate_consistency"
    if replay_requested:
        assert args.uncertainty_protocol is not None
        assert args.dependence_manifest is not None
        assert args.outcome_protocol is not None
        assert args.cohort_report is not None
        assert args.outcomes is not None
        assert args.outcome_report is not None
        failures = validate_clinical_outcome_uncertainty_report(
            report,
            _uncertainty_protocol(args.uncertainty_protocol),
            _dependence_manifest(args.dependence_manifest),
            _outcome_protocol(args.outcome_protocol),
            _cohort_report(args.cohort_report),
            tuple(_prediction_submission(path) for path in args.submission),
            _outcome_manifest(args.outcomes),
            _outcome_report(args.outcome_report),
        )
        scope = "full_dependence_and_private_outcome_replay"
    _print_json(
        clinical_outcome_uncertainty_validation_summary(
            report,
            failures=failures,
            scope=scope,
        )
    )
    return 0 if not failures else 1


def _summarize_uncertainty(args: argparse.Namespace) -> int:
    _print_json(clinical_outcome_uncertainty_summary(_uncertainty_report(args.report)))
    return 0


def _simulate_uncertainty_design(args: argparse.Namespace) -> int:
    report = simulate_clinical_outcome_uncertainty_design(
        _design_protocol(args.protocol)
    )
    envelope = clinical_outcome_design_report_envelope(report)
    if args.output == "-":
        _print_json(envelope)
        return 0
    output = write_json_artifact(args.output, envelope, force=args.force)
    if not output.is_file():
        raise OSError("clinical outcome design simulation output was not created")
    _print_json(
        clinical_outcome_design_simulation_validation_summary(
            report,
            scope="full_protocol_and_seeded_simulation_replay",
        )
    )
    return 0


def _validate_uncertainty_design(args: argparse.Namespace) -> int:
    _require_single_stdin((args.report, args.protocol))
    report = _design_report(args.report)
    failures: tuple[str, ...] = ()
    scope = "integrity_and_aggregate_consistency"
    if args.protocol is not None:
        failures = validate_clinical_outcome_design_simulation_report(
            report,
            _design_protocol(args.protocol),
        )
        scope = "full_protocol_and_seeded_simulation_replay"
    _print_json(
        clinical_outcome_design_simulation_validation_summary(
            report,
            failures=failures,
            scope=scope,
        )
    )
    return 0 if not failures else 1


def _summarize_uncertainty_design(args: argparse.Namespace) -> int:
    _print_json(clinical_outcome_design_simulation_summary(_design_report(args.report)))
    return 0


def _simulate_uncertainty_stress(args: argparse.Namespace) -> int:
    report = simulate_clinical_outcome_stress(_stress_protocol(args.protocol))
    envelope = clinical_outcome_stress_report_envelope(report)
    if args.output == "-":
        _print_json(envelope)
        return 0
    output = write_json_artifact(args.output, envelope, force=args.force)
    if not output.is_file():
        raise OSError("clinical outcome stress simulation output was not created")
    _print_json(
        clinical_outcome_stress_simulation_validation_summary(
            report,
            scope="full_protocol_and_seeded_simulation_replay",
        )
    )
    return 0


def _validate_uncertainty_stress(args: argparse.Namespace) -> int:
    _require_single_stdin((args.report, args.protocol))
    report = _stress_report(args.report)
    failures: tuple[str, ...] = ()
    scope = "integrity_and_aggregate_consistency"
    if args.protocol is not None:
        failures = validate_clinical_outcome_stress_simulation_report(
            report,
            _stress_protocol(args.protocol),
        )
        scope = "full_protocol_and_seeded_simulation_replay"
    _print_json(
        clinical_outcome_stress_simulation_validation_summary(
            report,
            failures=failures,
            scope=scope,
        )
    )
    return 0 if not failures else 1


def _summarize_uncertainty_stress(args: argparse.Namespace) -> int:
    _print_json(clinical_outcome_stress_simulation_summary(_stress_report(args.report)))
    return 0


def _analyze_pattern_mixture(args: argparse.Namespace) -> int:
    _require_single_stdin((args.protocol, args.stress_protocol))
    report = analyze_clinical_outcome_pattern_mixture(
        _pattern_mixture_protocol(args.protocol),
        _stress_protocol(args.stress_protocol),
    )
    envelope = clinical_outcome_pattern_mixture_report_envelope(report)
    if args.output == "-":
        _print_json(envelope)
        return 0
    output = write_json_artifact(args.output, envelope, force=args.force)
    if not output.is_file():
        raise OSError("clinical outcome pattern-mixture output was not created")
    _print_json(
        clinical_outcome_pattern_mixture_validation_summary(
            report,
            scope="full_protocol_and_seeded_stress_replay",
        )
    )
    return 0


def _validate_pattern_mixture(args: argparse.Namespace) -> int:
    if (args.protocol is None) != (args.stress_protocol is None):
        raise ValueError(
            "full pattern-mixture replay requires both --protocol and --stress-protocol"
        )
    _require_single_stdin((args.report, args.protocol, args.stress_protocol))
    report = _pattern_mixture_report(args.report)
    failures: tuple[str, ...] = ()
    scope = "integrity_and_aggregate_consistency"
    if args.protocol is not None:
        assert args.stress_protocol is not None
        failures = validate_clinical_outcome_pattern_mixture_report(
            report,
            _pattern_mixture_protocol(args.protocol),
            _stress_protocol(args.stress_protocol),
        )
        scope = "full_protocol_and_seeded_stress_replay"
    _print_json(
        clinical_outcome_pattern_mixture_validation_summary(
            report,
            failures=failures,
            scope=scope,
        )
    )
    return 0 if not failures else 1


def _summarize_pattern_mixture(args: argparse.Namespace) -> int:
    _print_json(
        clinical_outcome_pattern_mixture_summary(
            _pattern_mixture_report(args.report)
        )
    )
    return 0


def _analyze_pattern_mixture_uncertainty(args: argparse.Namespace) -> int:
    _require_single_stdin(
        (args.protocol, args.pattern_mixture_protocol, args.stress_protocol)
    )
    report = analyze_clinical_outcome_pattern_mixture_uncertainty(
        _pattern_mixture_uncertainty_protocol(args.protocol),
        _pattern_mixture_protocol(args.pattern_mixture_protocol),
        _stress_protocol(args.stress_protocol),
    )
    envelope = clinical_outcome_pattern_mixture_uncertainty_report_envelope(report)
    if args.output == "-":
        _print_json(envelope)
        return 0
    output = write_json_artifact(args.output, envelope, force=args.force)
    if not output.is_file():
        raise OSError(
            "clinical outcome pattern-mixture uncertainty output was not created"
        )
    _print_json(
        clinical_outcome_pattern_mixture_uncertainty_validation_summary(
            report,
            scope="full_protocol_and_seeded_stress_replay",
        )
    )
    return 0


def _validate_pattern_mixture_uncertainty(args: argparse.Namespace) -> int:
    replay_inputs = (
        args.protocol,
        args.pattern_mixture_protocol,
        args.stress_protocol,
    )
    if any(item is not None for item in replay_inputs) and not all(
        item is not None for item in replay_inputs
    ):
        raise ValueError(
            "full pattern-mixture uncertainty replay requires --protocol, "
            "--pattern-mixture-protocol, and --stress-protocol"
        )
    _require_single_stdin((args.report, *replay_inputs))
    report = _pattern_mixture_uncertainty_report(args.report)
    failures: tuple[str, ...] = ()
    scope = "integrity_and_aggregate_consistency"
    if args.protocol is not None:
        assert args.pattern_mixture_protocol is not None
        assert args.stress_protocol is not None
        failures = validate_clinical_outcome_pattern_mixture_uncertainty_report(
            report,
            _pattern_mixture_uncertainty_protocol(args.protocol),
            _pattern_mixture_protocol(args.pattern_mixture_protocol),
            _stress_protocol(args.stress_protocol),
        )
        scope = "full_protocol_and_seeded_stress_replay"
    _print_json(
        clinical_outcome_pattern_mixture_uncertainty_validation_summary(
            report,
            failures=failures,
            scope=scope,
        )
    )
    return 0 if not failures else 1


def _summarize_pattern_mixture_uncertainty(args: argparse.Namespace) -> int:
    _print_json(
        clinical_outcome_pattern_mixture_uncertainty_summary(
            _pattern_mixture_uncertainty_report(args.report)
        )
    )
    return 0


def _calibrate_pattern_mixture_influence(args: argparse.Namespace) -> int:
    _require_single_stdin(
        (args.protocol, args.pattern_mixture_protocol, args.stress_protocol)
    )
    report = analyze_clinical_outcome_pattern_mixture_influence_calibration(
        _pattern_mixture_influence_protocol(args.protocol),
        _pattern_mixture_protocol(args.pattern_mixture_protocol),
        _stress_protocol(args.stress_protocol),
    )
    envelope = clinical_outcome_pattern_mixture_influence_report_envelope(report)
    if args.output == "-":
        _print_json(envelope)
        return 0
    output = write_json_artifact(args.output, envelope, force=args.force)
    if not output.is_file():
        raise OSError(
            "clinical outcome pattern-mixture influence output was not created"
        )
    _print_json(
        clinical_outcome_pattern_mixture_influence_calibration_validation_summary(
            report,
            scope="full_protocol_and_seeded_stress_replay",
        )
    )
    return 0


def _validate_pattern_mixture_influence(args: argparse.Namespace) -> int:
    replay_inputs = (
        args.protocol,
        args.pattern_mixture_protocol,
        args.stress_protocol,
    )
    if any(item is not None for item in replay_inputs) and not all(
        item is not None for item in replay_inputs
    ):
        raise ValueError(
            "full pattern-mixture influence replay requires --protocol, "
            "--pattern-mixture-protocol, and --stress-protocol"
        )
    _require_single_stdin((args.report, *replay_inputs))
    report = _pattern_mixture_influence_report(args.report)
    failures: tuple[str, ...] = ()
    scope = "integrity_and_aggregate_consistency"
    if args.protocol is not None:
        assert args.pattern_mixture_protocol is not None
        assert args.stress_protocol is not None
        failures = (
            validate_clinical_outcome_pattern_mixture_influence_calibration_report(
                report,
                _pattern_mixture_influence_protocol(args.protocol),
                _pattern_mixture_protocol(args.pattern_mixture_protocol),
                _stress_protocol(args.stress_protocol),
            )
        )
        scope = "full_protocol_and_seeded_stress_replay"
    _print_json(
        clinical_outcome_pattern_mixture_influence_calibration_validation_summary(
            report,
            failures=failures,
            scope=scope,
        )
    )
    return 0 if not failures else 1


def _summarize_pattern_mixture_influence(args: argparse.Namespace) -> int:
    _print_json(
        clinical_outcome_pattern_mixture_influence_calibration_summary(
            _pattern_mixture_influence_report(args.report)
        )
    )
    return 0


def _analyze_informative_cluster_size(args: argparse.Namespace) -> int:
    _require_single_stdin((args.protocol, args.stress_protocol))
    report = analyze_clinical_outcome_informative_cluster_size(
        _informative_cluster_size_protocol(args.protocol),
        _stress_protocol(args.stress_protocol),
    )
    envelope = clinical_outcome_informative_cluster_size_report_envelope(report)
    if args.output == "-":
        _print_json(envelope)
        return 0
    output = write_json_artifact(args.output, envelope, force=args.force)
    if not output.is_file():
        raise OSError("informative-cluster-size report output was not created")
    _print_json(
        clinical_outcome_informative_cluster_size_validation_summary(
            report,
            scope="full_protocol_and_seeded_stress_replay",
        )
    )
    return 0


def _validate_informative_cluster_size(args: argparse.Namespace) -> int:
    replay_inputs = (args.protocol, args.stress_protocol)
    if any(item is not None for item in replay_inputs) and not all(
        item is not None for item in replay_inputs
    ):
        raise ValueError(
            "full informative-cluster-size replay requires --protocol and "
            "--stress-protocol"
        )
    _require_single_stdin((args.report, *replay_inputs))
    report = _informative_cluster_size_report(args.report)
    failures: tuple[str, ...] = ()
    scope = "integrity_and_aggregate_consistency"
    if args.protocol is not None:
        assert args.stress_protocol is not None
        failures = validate_clinical_outcome_informative_cluster_size_report(
            report,
            _informative_cluster_size_protocol(args.protocol),
            _stress_protocol(args.stress_protocol),
        )
        scope = "full_protocol_and_seeded_stress_replay"
    _print_json(
        clinical_outcome_informative_cluster_size_validation_summary(
            report,
            failures=failures,
            scope=scope,
        )
    )
    return 0 if not failures else 1


def _summarize_informative_cluster_size(args: argparse.Namespace) -> int:
    _print_json(
        clinical_outcome_informative_cluster_size_summary(
            _informative_cluster_size_report(args.report)
        )
    )
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Compile, validate, and summarize provenance-preserving clinical "
            "evidence packages, outcome-free cohort diagnostics, and "
            "preregistered aggregate outcome, cluster-aware uncertainty, and "
            "prospective uncertainty-design and missingness-sensitivity simulations."
        )
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    compile_parser = subparsers.add_parser(
        "compile",
        help="Compile a decision package from a committed ProgramState and config.",
    )
    compile_parser.add_argument(
        "--state",
        required=True,
        help="ProgramState JSON path, or '-' for stdin.",
    )
    compile_parser.add_argument(
        "--config",
        required=True,
        help="Clinical decision config JSON path, or '-' for stdin.",
    )
    compile_parser.add_argument(
        "--output",
        required=True,
        help="Package JSON path, or '-' for stdout.",
    )
    compile_parser.add_argument(
        "--force",
        action="store_true",
        help="Atomically replace an existing package file.",
    )
    compile_parser.set_defaults(handler=_compile)

    validate_parser = subparsers.add_parser(
        "validate",
        help="Validate package integrity, with optional full state replay.",
    )
    validate_parser.add_argument(
        "--package",
        required=True,
        help="Decision package JSON path, or '-' for stdin.",
    )
    validate_parser.add_argument(
        "--state",
        help="Optional ProgramState JSON for committed-ledger replay.",
    )
    validate_parser.set_defaults(handler=_validate)

    summarize_parser = subparsers.add_parser(
        "summarize",
        help="Emit a compact human- and machine-readable package summary.",
    )
    summarize_parser.add_argument(
        "--package",
        required=True,
        help="Decision package JSON path, or '-' for stdin.",
    )
    summarize_parser.set_defaults(handler=_summarize)

    cohort_parser = subparsers.add_parser(
        "cohort",
        help=(
            "Compile outcome-free cohort diagnostics and matched policy "
            "sensitivity from an exact package roster."
        ),
    )
    cohort_parser.add_argument(
        "--manifest",
        required=True,
        help="Integrity-bound cohort manifest JSON path, or '-' for stdin.",
    )
    cohort_parser.add_argument(
        "--package",
        action="append",
        required=True,
        help="Decision package JSON path; repeat once per manifest binding.",
    )
    cohort_parser.add_argument(
        "--state",
        action="append",
        default=[],
        help=(
            "Accepted ProgramState JSON path; repeat once per program when "
            "state_sha256 is declared in the manifest."
        ),
    )
    cohort_parser.add_argument(
        "--output",
        required=True,
        help="Cohort report JSON path, or '-' for stdout.",
    )
    cohort_parser.add_argument(
        "--force",
        action="store_true",
        help="Atomically replace an existing cohort report file.",
    )
    cohort_parser.set_defaults(handler=_compile_cohort)

    validate_cohort_parser = subparsers.add_parser(
        "validate-cohort",
        help=(
            "Validate report integrity and aggregates, with optional exact "
            "manifest/package/state replay."
        ),
    )
    validate_cohort_parser.add_argument(
        "--report",
        required=True,
        help="Cohort report JSON path, or '-' for stdin.",
    )
    validate_cohort_parser.add_argument(
        "--manifest",
        help="Optional integrity-bound cohort manifest JSON path.",
    )
    validate_cohort_parser.add_argument(
        "--package",
        action="append",
        default=[],
        help="Decision package JSON path; repeat for exact manifest replay.",
    )
    validate_cohort_parser.add_argument(
        "--state",
        action="append",
        default=[],
        help="Accepted ProgramState JSON path; repeat for state-bound replay.",
    )
    validate_cohort_parser.set_defaults(handler=_validate_cohort)

    summarize_cohort_parser = subparsers.add_parser(
        "summarize-cohort",
        help="Emit a compact human- and machine-readable cohort summary.",
    )
    summarize_cohort_parser.add_argument(
        "--report",
        required=True,
        help="Cohort report JSON path, or '-' for stdin.",
    )
    summarize_cohort_parser.set_defaults(handler=_summarize_cohort)

    outcome_parser = subparsers.add_parser(
        "evaluate-outcomes",
        help=(
            "Evaluate package-bound probability forecasts against frozen, "
            "post-deadline clinical outcomes."
        ),
    )
    outcome_parser.add_argument(
        "--protocol",
        required=True,
        help="Preregistered clinical outcome protocol JSON path, or '-' for stdin.",
    )
    outcome_parser.add_argument(
        "--cohort-report",
        required=True,
        help="Outcome-free clinical cohort report JSON path.",
    )
    outcome_parser.add_argument(
        "--submission",
        action="append",
        required=True,
        help="Frozen policy prediction submission; repeat once per cohort policy.",
    )
    outcome_parser.add_argument(
        "--outcomes",
        required=True,
        help="Evaluator-only clinical outcome manifest JSON path.",
    )
    outcome_parser.add_argument(
        "--output",
        required=True,
        help="Aggregate clinical outcome report JSON path, or '-' for stdout.",
    )
    outcome_parser.add_argument(
        "--force",
        action="store_true",
        help="Atomically replace an existing aggregate report file.",
    )
    outcome_parser.set_defaults(handler=_evaluate_outcomes)

    validate_outcome_parser = subparsers.add_parser(
        "validate-outcomes",
        help=(
            "Validate aggregate outcome report integrity, with optional full "
            "private-input replay."
        ),
    )
    validate_outcome_parser.add_argument(
        "--report",
        required=True,
        help="Aggregate clinical outcome report JSON path, or '-' for stdin.",
    )
    validate_outcome_parser.add_argument(
        "--protocol",
        help="Preregistered protocol JSON for full replay.",
    )
    validate_outcome_parser.add_argument(
        "--cohort-report",
        help="Outcome-free clinical cohort report JSON for full replay.",
    )
    validate_outcome_parser.add_argument(
        "--submission",
        action="append",
        default=[],
        help="Prediction submission JSON; repeat once per policy for full replay.",
    )
    validate_outcome_parser.add_argument(
        "--outcomes",
        help="Evaluator-only outcome manifest JSON for full replay.",
    )
    validate_outcome_parser.set_defaults(handler=_validate_outcomes)

    summarize_outcome_parser = subparsers.add_parser(
        "summarize-outcomes",
        help="Emit compact aggregate calibration and paired-policy metrics.",
    )
    summarize_outcome_parser.add_argument(
        "--report",
        required=True,
        help="Aggregate clinical outcome report JSON path, or '-' for stdin.",
    )
    summarize_outcome_parser.set_defaults(handler=_summarize_outcomes)

    uncertainty_parser = subparsers.add_parser(
        "evaluate-uncertainty",
        help=(
            "Evaluate cluster-robust uncertainty over a frozen aggregate "
            "clinical outcome report."
        ),
    )
    uncertainty_parser.add_argument(
        "--uncertainty-protocol",
        required=True,
        help="Preregistered uncertainty protocol JSON path, or '-' for stdin.",
    )
    uncertainty_parser.add_argument(
        "--dependence-manifest",
        required=True,
        help="Evaluator-only dependence manifest JSON path.",
    )
    uncertainty_parser.add_argument(
        "--outcome-protocol",
        required=True,
        help="Bound clinical outcome protocol JSON path.",
    )
    uncertainty_parser.add_argument(
        "--cohort-report",
        required=True,
        help="Bound outcome-free clinical cohort report JSON path.",
    )
    uncertainty_parser.add_argument(
        "--submission",
        action="append",
        required=True,
        help="Frozen prediction submission; repeat once per cohort policy.",
    )
    uncertainty_parser.add_argument(
        "--outcomes",
        required=True,
        help="Evaluator-only clinical outcome manifest JSON path.",
    )
    uncertainty_parser.add_argument(
        "--outcome-report",
        required=True,
        help="Reproducible aggregate clinical outcome report JSON path.",
    )
    uncertainty_parser.add_argument(
        "--output",
        required=True,
        help="Aggregate uncertainty report JSON path, or '-' for stdout.",
    )
    uncertainty_parser.add_argument(
        "--force",
        action="store_true",
        help="Atomically replace an existing aggregate uncertainty report.",
    )
    uncertainty_parser.set_defaults(handler=_evaluate_uncertainty)

    validate_uncertainty_parser = subparsers.add_parser(
        "validate-uncertainty",
        help=(
            "Validate uncertainty-report integrity, with optional full "
            "dependence and private-outcome replay."
        ),
    )
    validate_uncertainty_parser.add_argument(
        "--report",
        required=True,
        help="Aggregate uncertainty report JSON path, or '-' for stdin.",
    )
    validate_uncertainty_parser.add_argument("--uncertainty-protocol")
    validate_uncertainty_parser.add_argument("--dependence-manifest")
    validate_uncertainty_parser.add_argument("--outcome-protocol")
    validate_uncertainty_parser.add_argument("--cohort-report")
    validate_uncertainty_parser.add_argument(
        "--submission",
        action="append",
        default=[],
        help="Prediction submission JSON; repeat once per policy for full replay.",
    )
    validate_uncertainty_parser.add_argument("--outcomes")
    validate_uncertainty_parser.add_argument("--outcome-report")
    validate_uncertainty_parser.set_defaults(handler=_validate_uncertainty)

    summarize_uncertainty_parser = subparsers.add_parser(
        "summarize-uncertainty",
        help="Emit compact cluster diagnostics and aggregate uncertainty metrics.",
    )
    summarize_uncertainty_parser.add_argument(
        "--report",
        required=True,
        help="Aggregate uncertainty report JSON path, or '-' for stdin.",
    )
    summarize_uncertainty_parser.set_defaults(handler=_summarize_uncertainty)

    simulate_design_parser = subparsers.add_parser(
        "simulate-uncertainty-design",
        help=(
            "Run deterministic prospective coverage and interval-yield simulations "
            "for candidate cluster gates."
        ),
    )
    simulate_design_parser.add_argument(
        "--protocol",
        required=True,
        help="Prospective design simulation protocol JSON path, or '-' for stdin.",
    )
    simulate_design_parser.add_argument(
        "--output",
        required=True,
        help="Aggregate design simulation report JSON path, or '-' for stdout.",
    )
    simulate_design_parser.add_argument(
        "--force",
        action="store_true",
        help="Atomically replace an existing design simulation report.",
    )
    simulate_design_parser.set_defaults(handler=_simulate_uncertainty_design)

    validate_design_parser = subparsers.add_parser(
        "validate-uncertainty-design",
        help=(
            "Validate aggregate design-report integrity, with optional full "
            "protocol and seeded simulation replay."
        ),
    )
    validate_design_parser.add_argument(
        "--report",
        required=True,
        help="Aggregate design simulation report JSON path, or '-' for stdin.",
    )
    validate_design_parser.add_argument(
        "--protocol",
        help="Design simulation protocol JSON for full deterministic replay.",
    )
    validate_design_parser.set_defaults(handler=_validate_uncertainty_design)

    summarize_design_parser = subparsers.add_parser(
        "summarize-uncertainty-design",
        help="Emit compact coverage, width, attrition, and candidate-gate results.",
    )
    summarize_design_parser.add_argument(
        "--report",
        required=True,
        help="Aggregate design simulation report JSON path, or '-' for stdin.",
    )
    summarize_design_parser.set_defaults(handler=_summarize_uncertainty_design)

    simulate_stress_parser = subparsers.add_parser(
        "simulate-uncertainty-stress",
        help=(
            "Run deterministic informative-evaluability and dependence-closure "
            "stress simulations."
        ),
    )
    simulate_stress_parser.add_argument(
        "--protocol",
        required=True,
        help="Prospective stress simulation protocol JSON path, or '-' for stdin.",
    )
    simulate_stress_parser.add_argument(
        "--output",
        required=True,
        help="Aggregate stress simulation report JSON path, or '-' for stdout.",
    )
    simulate_stress_parser.add_argument(
        "--force",
        action="store_true",
        help="Atomically replace an existing stress simulation report.",
    )
    simulate_stress_parser.set_defaults(handler=_simulate_uncertainty_stress)

    validate_stress_parser = subparsers.add_parser(
        "validate-uncertainty-stress",
        help=(
            "Validate aggregate stress-report integrity, with optional full "
            "protocol and seeded simulation replay."
        ),
    )
    validate_stress_parser.add_argument(
        "--report",
        required=True,
        help="Aggregate stress simulation report JSON path, or '-' for stdin.",
    )
    validate_stress_parser.add_argument(
        "--protocol",
        help="Stress simulation protocol JSON for full deterministic replay.",
    )
    validate_stress_parser.set_defaults(handler=_validate_uncertainty_stress)

    summarize_stress_parser = subparsers.add_parser(
        "summarize-uncertainty-stress",
        help=(
            "Emit compact estimand-shift and dependence-closure stress comparisons."
        ),
    )
    summarize_stress_parser.add_argument(
        "--report",
        required=True,
        help="Aggregate stress simulation report JSON path, or '-' for stdin.",
    )
    summarize_stress_parser.set_defaults(handler=_summarize_uncertainty_stress)

    pattern_mixture_parser = subparsers.add_parser(
        "analyze-pattern-mixture",
        help=(
            "Run a preregistered prediction-stratified binary log-IMOR "
            "sensitivity analysis."
        ),
    )
    pattern_mixture_parser.add_argument(
        "--protocol",
        required=True,
        help="Pattern-mixture protocol JSON path, or '-' for stdin.",
    )
    pattern_mixture_parser.add_argument(
        "--stress-protocol",
        required=True,
        help="Bound stress simulation protocol JSON path, or '-' for stdin.",
    )
    pattern_mixture_parser.add_argument(
        "--output",
        required=True,
        help="Aggregate pattern-mixture report JSON path, or '-' for stdout.",
    )
    pattern_mixture_parser.add_argument(
        "--force",
        action="store_true",
        help="Atomically replace an existing pattern-mixture report.",
    )
    pattern_mixture_parser.set_defaults(handler=_analyze_pattern_mixture)

    validate_pattern_mixture_parser = subparsers.add_parser(
        "validate-pattern-mixture",
        help=(
            "Validate pattern-mixture report integrity, with optional exact "
            "protocol and seeded stress replay."
        ),
    )
    validate_pattern_mixture_parser.add_argument(
        "--report",
        required=True,
        help="Aggregate pattern-mixture report JSON path, or '-' for stdin.",
    )
    validate_pattern_mixture_parser.add_argument(
        "--protocol",
        help="Pattern-mixture protocol JSON for full deterministic replay.",
    )
    validate_pattern_mixture_parser.add_argument(
        "--stress-protocol",
        help="Bound stress simulation protocol JSON for full deterministic replay.",
    )
    validate_pattern_mixture_parser.set_defaults(
        handler=_validate_pattern_mixture
    )

    summarize_pattern_mixture_parser = subparsers.add_parser(
        "summarize-pattern-mixture",
        help="Emit compact missingness identification and recovery diagnostics.",
    )
    summarize_pattern_mixture_parser.add_argument(
        "--report",
        required=True,
        help="Aggregate pattern-mixture report JSON path, or '-' for stdin.",
    )
    summarize_pattern_mixture_parser.set_defaults(
        handler=_summarize_pattern_mixture
    )

    pattern_uncertainty_parser = subparsers.add_parser(
        "analyze-pattern-mixture-uncertainty",
        help=(
            "Add nominal and dependence-closed delete-one-cluster jackknife "
            "intervals to a bound pattern-mixture sensitivity study."
        ),
    )
    pattern_uncertainty_parser.add_argument(
        "--protocol",
        required=True,
        help="Pattern-mixture uncertainty protocol JSON path, or '-' for stdin.",
    )
    pattern_uncertainty_parser.add_argument(
        "--pattern-mixture-protocol",
        required=True,
        help="Bound pattern-mixture protocol JSON path, or '-' for stdin.",
    )
    pattern_uncertainty_parser.add_argument(
        "--stress-protocol",
        required=True,
        help="Bound stress simulation protocol JSON path, or '-' for stdin.",
    )
    pattern_uncertainty_parser.add_argument(
        "--output",
        required=True,
        help="Aggregate pattern-mixture uncertainty report path, or '-' for stdout.",
    )
    pattern_uncertainty_parser.add_argument(
        "--force",
        action="store_true",
        help="Atomically replace an existing pattern-mixture uncertainty report.",
    )
    pattern_uncertainty_parser.set_defaults(
        handler=_analyze_pattern_mixture_uncertainty
    )

    validate_pattern_uncertainty_parser = subparsers.add_parser(
        "validate-pattern-mixture-uncertainty",
        help=(
            "Validate pattern-mixture uncertainty integrity, with optional "
            "complete seeded replay."
        ),
    )
    validate_pattern_uncertainty_parser.add_argument(
        "--report",
        required=True,
        help="Aggregate pattern-mixture uncertainty report path, or '-' for stdin.",
    )
    validate_pattern_uncertainty_parser.add_argument(
        "--protocol",
        help="Pattern-mixture uncertainty protocol for complete replay.",
    )
    validate_pattern_uncertainty_parser.add_argument(
        "--pattern-mixture-protocol",
        help="Bound pattern-mixture protocol for complete replay.",
    )
    validate_pattern_uncertainty_parser.add_argument(
        "--stress-protocol",
        help="Bound stress simulation protocol for complete replay.",
    )
    validate_pattern_uncertainty_parser.set_defaults(
        handler=_validate_pattern_mixture_uncertainty
    )

    summarize_pattern_uncertainty_parser = subparsers.add_parser(
        "summarize-pattern-mixture-uncertainty",
        help="Emit compact jackknife calibration and dependence-closure comparisons.",
    )
    summarize_pattern_uncertainty_parser.add_argument(
        "--report",
        required=True,
        help="Aggregate pattern-mixture uncertainty report path, or '-' for stdin.",
    )
    summarize_pattern_uncertainty_parser.set_defaults(
        handler=_summarize_pattern_mixture_uncertainty
    )

    pattern_influence_parser = subparsers.add_parser(
        "calibrate-pattern-mixture-influence",
        help=(
            "Compare normal, Student-t, unequal delete-mj, and experimental "
            "Webb multiplier intervals on a bound pattern-mixture study."
        ),
    )
    pattern_influence_parser.add_argument(
        "--protocol",
        required=True,
        help="Pattern-mixture influence protocol JSON path, or '-' for stdin.",
    )
    pattern_influence_parser.add_argument(
        "--pattern-mixture-protocol",
        required=True,
        help="Bound pattern-mixture protocol JSON path, or '-' for stdin.",
    )
    pattern_influence_parser.add_argument(
        "--stress-protocol",
        required=True,
        help="Bound stress simulation protocol JSON path, or '-' for stdin.",
    )
    pattern_influence_parser.add_argument(
        "--output",
        required=True,
        help="Aggregate pattern-mixture influence report path, or '-' for stdout.",
    )
    pattern_influence_parser.add_argument(
        "--force",
        action="store_true",
        help="Atomically replace an existing pattern-mixture influence report.",
    )
    pattern_influence_parser.set_defaults(handler=_calibrate_pattern_mixture_influence)

    validate_pattern_influence_parser = subparsers.add_parser(
        "validate-pattern-mixture-influence",
        help=(
            "Validate pattern-mixture influence integrity, with optional "
            "complete seeded replay."
        ),
    )
    validate_pattern_influence_parser.add_argument(
        "--report",
        required=True,
        help="Aggregate pattern-mixture influence report path, or '-' for stdin.",
    )
    validate_pattern_influence_parser.add_argument(
        "--protocol",
        help="Pattern-mixture influence protocol for complete replay.",
    )
    validate_pattern_influence_parser.add_argument(
        "--pattern-mixture-protocol",
        help="Bound pattern-mixture protocol for complete replay.",
    )
    validate_pattern_influence_parser.add_argument(
        "--stress-protocol",
        help="Bound stress simulation protocol for complete replay.",
    )
    validate_pattern_influence_parser.set_defaults(
        handler=_validate_pattern_mixture_influence
    )

    summarize_pattern_influence_parser = subparsers.add_parser(
        "summarize-pattern-mixture-influence",
        help="Emit compact unequal-cluster interval calibration comparisons.",
    )
    summarize_pattern_influence_parser.add_argument(
        "--report",
        required=True,
        help="Aggregate pattern-mixture influence report path, or '-' for stdin.",
    )
    summarize_pattern_influence_parser.set_defaults(
        handler=_summarize_pattern_mixture_influence
    )

    informative_cluster_size_parser = subparsers.add_parser(
        "analyze-informative-cluster-size",
        help=(
            "Compare unit-weighted and cluster-balanced pattern-mixture "
            "functionals under informative cluster size."
        ),
    )
    informative_cluster_size_parser.add_argument(
        "--protocol",
        required=True,
        help="Informative-cluster-size protocol JSON path, or '-' for stdin.",
    )
    informative_cluster_size_parser.add_argument(
        "--stress-protocol",
        required=True,
        help="Bound stress simulation protocol JSON path, or '-' for stdin.",
    )
    informative_cluster_size_parser.add_argument(
        "--output",
        required=True,
        help="Aggregate informative-cluster-size report path, or '-' for stdout.",
    )
    informative_cluster_size_parser.add_argument(
        "--force",
        action="store_true",
        help="Atomically replace an existing informative-cluster-size report.",
    )
    informative_cluster_size_parser.set_defaults(
        handler=_analyze_informative_cluster_size
    )

    validate_informative_cluster_size_parser = subparsers.add_parser(
        "validate-informative-cluster-size",
        help=(
            "Validate informative-cluster-size integrity, with optional complete "
            "seeded replay."
        ),
    )
    validate_informative_cluster_size_parser.add_argument(
        "--report",
        required=True,
        help="Aggregate informative-cluster-size report path, or '-' for stdin.",
    )
    validate_informative_cluster_size_parser.add_argument(
        "--protocol",
        help="Informative-cluster-size protocol for complete replay.",
    )
    validate_informative_cluster_size_parser.add_argument(
        "--stress-protocol",
        help="Bound stress simulation protocol for complete replay.",
    )
    validate_informative_cluster_size_parser.set_defaults(
        handler=_validate_informative_cluster_size
    )

    summarize_informative_cluster_size_parser = subparsers.add_parser(
        "summarize-informative-cluster-size",
        help="Emit compact estimand-drift and influence-concentration comparisons.",
    )
    summarize_informative_cluster_size_parser.add_argument(
        "--report",
        required=True,
        help="Aggregate informative-cluster-size report path, or '-' for stdin.",
    )
    summarize_informative_cluster_size_parser.set_defaults(
        handler=_summarize_informative_cluster_size
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        return args.handler(args)
    except (
        ClinicalDecisionError,
        ClinicalCohortError,
        ClinicalOutcomeEvaluationError,
        ClinicalOutcomeDesignSimulationError,
        ClinicalOutcomeStressSimulationError,
        ClinicalOutcomePatternMixtureError,
        ClinicalOutcomePatternMixtureUncertaintyError,
        ClinicalOutcomePatternMixtureInfluenceError,
        ClinicalOutcomeInformativeClusterSizeError,
        ClinicalOutcomeUncertaintyError,
        ClinicalEvidenceWorkflowError,
        OSError,
        RecordParseError,
        TypeError,
        ValueError,
    ) as exc:
        _print_json(
            {
                "error": {
                    "code": "clinical_evidence_workflow_failed",
                    "message": str(exc),
                }
            },
            stream=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
