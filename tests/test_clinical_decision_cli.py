from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
import tomllib
import unittest
from dataclasses import replace
from pathlib import Path

from jsonschema import Draft202012Validator

import agentic_drug_discovery
from agentic_drug_discovery import (
    ClinicalEvidenceWorkflowError,
    RecordParseError,
    clinical_decision_config_from_dict,
    clinical_decision_config_from_json,
    clinical_decision_config_to_dict,
    clinical_decision_package_envelope,
    clinical_decision_package_from_dict,
    clinical_decision_package_summary,
    clinical_decision_validation_report,
    compile_clinical_decision_from_config,
    validate_clinical_decision_against_state,
)
from tests.test_clinical_benefit_risk_synthesis import (
    _combined_state,
    _mapping_spec,
    _run_mapping,
    _run_synthesis,
    _spec,
)


ROOT = Path(__file__).resolve().parents[1]
CONFIG_SCHEMA = (
    ROOT / "rl_env/specs/clinical_evidence_decision_config.schema.json"
)
CONFIG_EXAMPLE = (
    ROOT / "rl_env/specs/clinical_evidence_decision_config.example.json"
)
PACKAGE_SCHEMA = (
    ROOT / "rl_env/specs/clinical_evidence_decision_package.schema.json"
)
SUMMARY_SCHEMA = (
    ROOT / "rl_env/specs/clinical_evidence_decision_summary.schema.json"
)
PACKAGE_EXAMPLE = (
    ROOT / "rl_env/specs/clinical_evidence_decision_package.example.json"
)


class ClinicalDecisionWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        mapping_run, _ = _run_mapping(_combined_state(), _mapping_spec())
        synthesis_run, _ = _run_synthesis(mapping_run.final_state, _spec())
        cls.state = synthesis_run.final_state
        cls.config_raw = json.loads(CONFIG_EXAMPLE.read_text(encoding="utf-8"))
        cls.config = clinical_decision_config_from_dict(cls.config_raw)
        cls.expected_envelope = json.loads(
            PACKAGE_EXAMPLE.read_text(encoding="utf-8")
        )

    def test_config_schema_example_and_runtime_version_are_synchronized(self) -> None:
        config_schema = json.loads(CONFIG_SCHEMA.read_text(encoding="utf-8"))
        package_schema = json.loads(PACKAGE_SCHEMA.read_text(encoding="utf-8"))
        summary_schema = json.loads(SUMMARY_SCHEMA.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(config_schema)
        Draft202012Validator.check_schema(summary_schema)
        Draft202012Validator(config_schema).validate(self.config_raw)
        self.assertEqual(
            config_schema["$defs"]["policy"],
            package_schema["$defs"]["policy"],
        )
        self.assertEqual(
            config_schema["$defs"]["actionOption"],
            package_schema["$defs"]["actionOption"],
        )
        self.assertEqual(
            clinical_decision_config_to_dict(self.config),
            self.config_raw,
        )
        project = tomllib.loads((ROOT / "pyproject.toml").read_text("utf-8"))
        self.assertEqual(
            agentic_drug_discovery.__version__,
            project["project"]["version"],
        )

    def test_compiler_reproduces_public_package_and_compact_summary(self) -> None:
        package = compile_clinical_decision_from_config(self.state, self.config)
        self.assertEqual(
            clinical_decision_package_envelope(package),
            self.expected_envelope,
        )
        self.assertEqual(
            validate_clinical_decision_against_state(self.state, package),
            (),
        )
        summary = clinical_decision_package_summary(package)
        Draft202012Validator(
            json.loads(SUMMARY_SCHEMA.read_text(encoding="utf-8"))
        ).validate(summary)
        self.assertEqual(summary["evidence"]["trial_count"], 2)
        self.assertEqual(
            summary["evidence"]["dimension_status_counts"],
            {"satisfied": 8, "gap": 2, "blocking_signal": 0},
        )
        self.assertEqual(summary["plan"]["decision"], "hold")
        self.assertEqual(
            summary["plan"]["selected_actions"][0]["action_id"],
            "retrieve-safety-followup",
        )
        self.assertFalse(summary["guardrails"]["pooling_performed"])
        self.assertFalse(summary["guardrails"]["terminal_decision_issued"])

    def test_compiler_requires_exact_accepted_packet_provenance(self) -> None:
        last_packet = self.state.packet_history[-1]
        tampered_packet = replace(
            last_packet,
            benefit_risk_synthesis_updates=(),
        )
        uncommitted = replace(
            self.state,
            packet_history=(*self.state.packet_history[:-1], tampered_packet),
        )
        package = clinical_decision_package_from_dict(self.expected_envelope)
        self.assertEqual(
            validate_clinical_decision_against_state(uncommitted, package),
            ("synthesis_packet_provenance_missing",),
        )
        with self.assertRaisesRegex(
            ClinicalEvidenceWorkflowError,
            "synthesis_packet_provenance_missing",
        ):
            compile_clinical_decision_from_config(uncommitted, self.config)

    def test_config_parser_rejects_ambiguous_or_non_finite_json(self) -> None:
        encoded = CONFIG_EXAMPLE.read_text(encoding="utf-8")
        duplicate = encoded.replace(
            "{",
            '{"schema_version":"adds.clinical-evidence-decision-config.v1",',
            1,
        )
        with self.assertRaisesRegex(RecordParseError, "duplicates key"):
            clinical_decision_config_from_json(duplicate)

        non_finite = encoded.replace('"max_planned_cost": 0.25', '"max_planned_cost": NaN')
        with self.assertRaisesRegex(RecordParseError, "contains NaN"):
            clinical_decision_config_from_json(non_finite)

        duplicate_action = copy.deepcopy(self.config_raw)
        duplicate_action["action_catalog"][1]["action_id"] = (
            duplicate_action["action_catalog"][0]["action_id"]
        )
        with self.assertRaisesRegex(RecordParseError, "action ids must be unique"):
            clinical_decision_config_from_dict(duplicate_action)

    def test_cli_compile_validate_and_summarize_are_atomic(self) -> None:
        with tempfile.TemporaryDirectory(prefix="adds-clinical-decision-cli-") as tmp:
            root = Path(tmp)
            state_path = root / "state.json"
            config_path = root / "config.json"
            package_path = root / "package.json"
            state_path.write_text(
                json.dumps(self.state.to_dict(), indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            config_path.write_text(
                json.dumps(self.config_raw, indent=2) + "\n",
                encoding="utf-8",
            )
            compile_command = [
                sys.executable,
                "-m",
                "agentic_drug_discovery.clinical_decision_cli",
                "compile",
                "--state",
                str(state_path),
                "--config",
                str(config_path),
                "--output",
                str(package_path),
            ]
            compiled = subprocess.run(
                compile_command,
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
                timeout=30,
            )
            self.assertEqual(compiled.returncode, 0, compiled.stderr)
            self.assertEqual(
                json.loads(package_path.read_text(encoding="utf-8")),
                self.expected_envelope,
            )
            compile_report = json.loads(compiled.stdout)
            self.assertEqual(compile_report["validation"]["status"], "valid")

            validated = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "agentic_drug_discovery.clinical_decision_cli",
                    "validate",
                    "--package",
                    str(package_path),
                    "--state",
                    str(state_path),
                ],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
                timeout=30,
            )
            self.assertEqual(validated.returncode, 0, validated.stderr)
            validation_report = json.loads(validated.stdout)
            self.assertEqual(
                validation_report["validation"]["scope"],
                "integrity_structure_and_state_replay",
            )

            summarized = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "agentic_drug_discovery.clinical_decision_cli",
                    "summarize",
                    "--package",
                    str(package_path),
                ],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
                timeout=30,
            )
            self.assertEqual(summarized.returncode, 0, summarized.stderr)
            self.assertEqual(json.loads(summarized.stdout)["plan"]["decision"], "hold")

            unchanged = package_path.read_bytes()
            duplicate_write = subprocess.run(
                compile_command,
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
                timeout=30,
            )
            self.assertEqual(duplicate_write.returncode, 2)
            self.assertEqual(package_path.read_bytes(), unchanged)

    def test_validation_report_marks_state_replay_mismatch(self) -> None:
        package = clinical_decision_package_from_dict(self.expected_envelope)
        mismatched = replace(
            self.state,
            benefit_risk_syntheses=(),
        )
        report = clinical_decision_validation_report(package, state=mismatched)
        Draft202012Validator(
            json.loads(SUMMARY_SCHEMA.read_text(encoding="utf-8"))
        ).validate(report)
        self.assertEqual(report["validation"]["status"], "invalid")
        self.assertEqual(
            report["validation"]["failure_codes"],
            ["program_committed_history_invalid"],
        )


if __name__ == "__main__":
    unittest.main()
