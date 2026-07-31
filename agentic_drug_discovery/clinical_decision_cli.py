"""Command-line compiler and validator for clinical evidence packages."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence, TextIO

from .clinical_decision import (
    ClinicalDecisionError,
    clinical_decision_package_envelope,
    clinical_decision_package_from_json,
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


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Compile, validate, and summarize provenance-preserving clinical "
            "evidence decision packages."
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
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        return args.handler(args)
    except (
        ClinicalDecisionError,
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
