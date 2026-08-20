from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from agentic_drug_discovery.models import EvidenceRelation
from agentic_drug_discovery.translational_handoff import (
    TRANSLATIONAL_HANDOFF_ALLOWED_USE,
    TRANSLATIONAL_HANDOFF_SCHEMA_VERSION,
    TranslationalHandoffError,
    compile_translational_handoff_evidence,
    load_translational_handoff,
    translational_handoff_from_json,
    translational_handoff_integrity_sha256,
    translational_handoff_summary,
    validate_translational_handoff,
)


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "rl_env" / "specs" / "translational_handoff.example.json"
SCHEMA = ROOT / "rl_env" / "specs" / "translational_handoff.schema.json"


def _handoff() -> dict:
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


def _rehash(handoff: dict) -> dict:
    handoff["integrity_sha256"] = translational_handoff_integrity_sha256(handoff)
    return handoff


class TranslationalHandoffTests(unittest.TestCase):
    def test_synthetic_handoff_validates_with_expected_summary(self) -> None:
        handoff = load_translational_handoff(EXAMPLE)
        summary = translational_handoff_summary(handoff)

        self.assertEqual(summary["schema_version"], TRANSLATIONAL_HANDOFF_SCHEMA_VERSION)
        self.assertEqual(summary["payload_class"], "synthetic_fixture")
        self.assertEqual(summary["source_count"], 2)
        self.assertEqual(summary["observation_count"], 2)
        self.assertEqual(summary["assay_count"], 2)
        self.assertEqual(summary["independent_replication_source_count"], 2)
        self.assertEqual(summary["allowed_use"], TRANSLATIONAL_HANDOFF_ALLOWED_USE)
        self.assertEqual(summary["compiled_relation"], "contextualizes")
        self.assertEqual(
            summary["quality_control_counts"],
            {"fail": 0, "not_assessed": 0, "partial": 1, "pass": 1},
        )

    def test_synthetic_handoff_matches_strict_json_schema(self) -> None:
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema, format_checker=FormatChecker()).validate(_handoff())

    def test_duplicate_json_key_is_rejected(self) -> None:
        text = EXAMPLE.read_text(encoding="utf-8")
        duplicate = text.replace(
            '  "schema_version":',
            '  "handoff_id": "duplicate",\n  "schema_version":',
            1,
        )
        with self.assertRaisesRegex(TranslationalHandoffError, "duplicate JSON key"):
            translational_handoff_from_json(duplicate)

    def test_rehashed_source_identity_tampering_is_rejected(self) -> None:
        handoff = copy.deepcopy(_handoff())
        handoff["observations"][0]["source_id"] = "unknown-source"
        _rehash(handoff)
        with self.assertRaisesRegex(TranslationalHandoffError, "unknown source_id"):
            validate_translational_handoff(handoff)

    def test_rehashed_disease_context_rebinding_is_rejected(self) -> None:
        handoff = copy.deepcopy(_handoff())
        handoff["biological_context"]["disease_context_id"] = (
            "SYNTHETIC:DISEASE-OTHER"
        )
        _rehash(handoff)
        with self.assertRaisesRegex(TranslationalHandoffError, "must match program"):
            validate_translational_handoff(handoff)

    def test_rehashed_invalid_effect_interval_is_rejected(self) -> None:
        handoff = copy.deepcopy(_handoff())
        handoff["observations"][0]["result"]["lower_bound"] = -1.0
        _rehash(handoff)
        with self.assertRaisesRegex(TranslationalHandoffError, "must contain its estimate"):
            validate_translational_handoff(handoff)

    def test_rehashed_post_creation_source_is_rejected(self) -> None:
        handoff = copy.deepcopy(_handoff())
        handoff["sources"][0]["available_on"] = "2026-07-12"
        _rehash(handoff)
        with self.assertRaisesRegex(TranslationalHandoffError, "cannot follow"):
            validate_translational_handoff(handoff)

    def test_rehashed_shared_replication_lineage_is_rejected(self) -> None:
        handoff = copy.deepcopy(_handoff())
        handoff["sources"][1]["lineage_ids"][0] = handoff["sources"][0][
            "lineage_ids"
        ][0]
        _rehash(handoff)
        with self.assertRaisesRegex(TranslationalHandoffError, "share lineage"):
            validate_translational_handoff(handoff)

    def test_rehashed_replication_source_without_observation_is_rejected(self) -> None:
        handoff = copy.deepcopy(_handoff())
        handoff["observations"][1]["source_id"] = handoff["observations"][0][
            "source_id"
        ]
        _rehash(handoff)
        with self.assertRaisesRegex(TranslationalHandoffError, "without observations"):
            validate_translational_handoff(handoff)

    def test_rehashed_replication_endpoint_mismatch_is_rejected(self) -> None:
        handoff = copy.deepcopy(_handoff())
        handoff["observations"][1]["assay"]["endpoint_id"] = (
            "SYNTHETIC:ENDPOINT-DIFFERENT"
        )
        _rehash(handoff)
        with self.assertRaisesRegex(TranslationalHandoffError, "share at least one endpoint"):
            validate_translational_handoff(handoff)

    def test_rehashed_endpoint_identity_rebinding_is_rejected(self) -> None:
        handoff = copy.deepcopy(_handoff())
        handoff["observations"][1]["assay"]["endpoint_name"] = "Conflicting endpoint"
        _rehash(handoff)
        with self.assertRaisesRegex(TranslationalHandoffError, "endpoint_id rebinds"):
            validate_translational_handoff(handoff)

    def test_rehashed_assay_identity_rebinding_is_rejected(self) -> None:
        handoff = copy.deepcopy(_handoff())
        handoff["observations"][1]["assay"]["assay_id"] = handoff["observations"][
            0
        ]["assay"]["assay_id"]
        _rehash(handoff)
        with self.assertRaisesRegex(TranslationalHandoffError, "assay_id rebinds"):
            validate_translational_handoff(handoff)

    def test_rehashed_comparator_identity_rebinding_is_rejected(self) -> None:
        handoff = copy.deepcopy(_handoff())
        handoff["observations"][1]["comparator"]["comparator_id"] = handoff[
            "observations"
        ][0]["comparator"]["comparator_id"]
        _rehash(handoff)
        with self.assertRaisesRegex(TranslationalHandoffError, "comparator_id rebinds"):
            validate_translational_handoff(handoff)

    def test_rehashed_effect_direction_contradiction_is_rejected(self) -> None:
        handoff = copy.deepcopy(_handoff())
        handoff["observations"][0]["result"]["effect_direction"] = "increase"
        _rehash(handoff)
        with self.assertRaisesRegex(TranslationalHandoffError, "contradicts the estimate"):
            validate_translational_handoff(handoff)

    def test_rehashed_boundary_relaxation_is_rejected(self) -> None:
        handoff = copy.deepcopy(_handoff())
        handoff["decision_boundary"]["requires_human_review_before_scientific_gate"] = False
        _rehash(handoff)
        with self.assertRaisesRegex(TranslationalHandoffError, "must be true"):
            validate_translational_handoff(handoff)

    def test_rehashed_integrity_mismatch_is_rejected(self) -> None:
        handoff = copy.deepcopy(_handoff())
        handoff["review"]["interpretation"] = "Changed without rehashing."
        with self.assertRaisesRegex(TranslationalHandoffError, "integrity mismatch"):
            validate_translational_handoff(handoff)

    def test_compiler_emits_contextual_evidence_only(self) -> None:
        drafts = compile_translational_handoff_evidence(
            _handoff(), request_id="synthetic-request-001"
        )

        self.assertEqual(len(drafts), 2)
        self.assertEqual({item.relation for item in drafts}, {EvidenceRelation.CONTEXTUALIZES})
        self.assertEqual(
            {item.predicate for item in drafts}, {"upstream_perturbation_observation"}
        )
        self.assertEqual(
            {item.metadata["allowed_use"] for item in drafts},
            {TRANSLATIONAL_HANDOFF_ALLOWED_USE},
        )
        self.assertTrue(
            all(
                item.metadata["requires_human_review_before_scientific_gate"]
                for item in drafts
            )
        )
        self.assertNotIn("mechanism", {item.predicate for item in drafts})
        self.assertNotIn("efficacy", {item.predicate for item in drafts})

    def test_cli_validate_summarize_and_compile(self) -> None:
        for command in ("validate", "summarize", "compile"):
            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "agentic_drug_discovery.translational_handoff_cli",
                    command,
                    "--handoff",
                    str(EXAMPLE),
                    "--root",
                    str(ROOT),
                    "--request-id",
                    "synthetic-cli-request",
                ],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            output = json.loads(completed.stdout)
            if command == "compile":
                self.assertEqual(len(output["evidence_drafts"]), 2)
                self.assertEqual(
                    {item["relation"] for item in output["evidence_drafts"]},
                    {"contextualizes"},
                )
            else:
                self.assertEqual(output["handoff_id"], _handoff()["handoff_id"])

    def test_cli_rejects_modified_handoff(self) -> None:
        handoff = copy.deepcopy(_handoff())
        handoff["decision_boundary"]["allowed_use"] = "scientific_gate"
        _rehash(handoff)
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "handoff.json"
            path.write_text(json.dumps(handoff), encoding="utf-8")
            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "agentic_drug_discovery.translational_handoff_cli",
                    "validate",
                    "--handoff",
                    str(path),
                ],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
        self.assertEqual(completed.returncode, 2)
        error = json.loads(completed.stderr)
        self.assertEqual(error["error"]["code"], "invalid_translational_handoff")


if __name__ == "__main__":
    unittest.main()
