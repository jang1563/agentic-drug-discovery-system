from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from agentic_drug_discovery.research_readiness import (
    RESEARCH_READINESS_PROFILE_ID,
    ResearchReadinessError,
    load_research_readiness_profile,
    research_readiness_integrity_sha256,
    research_readiness_profile_from_json,
    research_readiness_summary,
    validate_research_readiness_profile,
)


ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / "docs" / "biohub_research_readiness.json"
SCHEMA = ROOT / "rl_env" / "specs" / "biohub_research_readiness.schema.json"


def _profile() -> dict:
    return json.loads(PROFILE.read_text(encoding="utf-8"))


def _rehash(profile: dict) -> dict:
    profile["integrity_sha256"] = research_readiness_integrity_sha256(profile)
    return profile


class ResearchReadinessTests(unittest.TestCase):
    def test_public_profile_validates_and_has_expected_summary(self) -> None:
        profile = load_research_readiness_profile(PROFILE, root=ROOT)
        summary = research_readiness_summary(profile, root=ROOT)

        self.assertEqual(summary["profile_id"], RESEARCH_READINESS_PROFILE_ID)
        self.assertEqual(summary["official_source_count"], 4)
        self.assertEqual(summary["evidence_anchor_count"], 41)
        self.assertEqual(
            summary["maturity_counts"],
            {
                "implemented_public": 8,
                "proposed_pilot": 1,
                "synthetic_validated": 3,
            },
        )
        self.assertEqual(
            summary["fit_counts"],
            {"complementary": 1, "direct": 1, "proposed": 2},
        )
        self.assertEqual(summary["presentation_slide_count"], 10)
        self.assertEqual(summary["acceptance_gate_count"], 5)
        self.assertEqual(summary["known_gap_count"], 6)
        self.assertFalse(summary["affiliation_claimed"])
        self.assertIn(
            "uc-public-registry-contract-validation",
            {item["capability_id"] for item in profile["maturity_ledger"]},
        )
        self.assertIn(
            "claim-uc-public-registry-validation",
            {item["claim_id"] for item in profile["presentation"]["claims"]},
        )
        self.assertIn(
            "ra-public-registry-contract-validation",
            {item["capability_id"] for item in profile["maturity_ledger"]},
        )
        self.assertIn(
            "claim-ra-public-registry-hold",
            {item["claim_id"] for item in profile["presentation"]["claims"]},
        )
        self.assertIn(
            "claim-ra-source-disjoint-additive-tensor",
            {item["claim_id"] for item in profile["presentation"]["claims"]},
        )
        self.assertIn(
            "estimable transport model",
            profile["decision"]["next_decision"],
        )

    def test_public_profile_matches_strict_json_schema(self) -> None:
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        profile = _profile()
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(
            schema,
            format_checker=FormatChecker(),
        ).validate(profile)

    def test_duplicate_json_key_is_rejected(self) -> None:
        text = PROFILE.read_text(encoding="utf-8")
        duplicate = text.replace(
            '  "schema_version":',
            '  "profile_id": "duplicate",\n  "schema_version":',
            1,
        )
        with self.assertRaisesRegex(ResearchReadinessError, "duplicate JSON key"):
            research_readiness_profile_from_json(duplicate, root=ROOT)

    def test_rehashed_evidence_anchor_tampering_is_rejected(self) -> None:
        profile = copy.deepcopy(_profile())
        profile["evidence_anchors"][0]["sha256"] = "0" * 64
        _rehash(profile)
        with self.assertRaisesRegex(ResearchReadinessError, "hash mismatch"):
            validate_research_readiness_profile(profile, root=ROOT)

    def test_rehashed_maturity_promotion_is_rejected(self) -> None:
        profile = copy.deepcopy(_profile())
        item = next(
            entry
            for entry in profile["maturity_ledger"]
            if entry["capability_id"] == "biohub-data-integration"
        )
        item["maturity"] = "implemented_public"
        _rehash(profile)
        with self.assertRaisesRegex(
            ResearchReadinessError, "requires implementation and test anchors"
        ):
            validate_research_readiness_profile(profile, root=ROOT)

    def test_rehashed_pilot_gate_relaxation_is_rejected(self) -> None:
        profile = copy.deepcopy(_profile())
        gate = next(
            entry
            for entry in profile["pilot"]["acceptance_gates"]
            if entry["gate_id"] == "replay_success"
        )
        gate["threshold"] = 0.95
        _rehash(profile)
        with self.assertRaisesRegex(ResearchReadinessError, "threshold changed"):
            validate_research_readiness_profile(profile, root=ROOT)

    def test_rehashed_presentation_maturity_promotion_is_rejected(self) -> None:
        profile = copy.deepcopy(_profile())
        claim = next(
            entry
            for entry in profile["presentation"]["claims"]
            if entry["claim_id"] == "claim-calibration-boundary"
        )
        claim["maturity"] = "implemented_public"
        _rehash(profile)
        with self.assertRaisesRegex(ResearchReadinessError, "maturity does not match"):
            validate_research_readiness_profile(profile, root=ROOT)

    def test_rehashed_affiliation_claim_is_rejected(self) -> None:
        profile = copy.deepcopy(_profile())
        profile["organization_context"]["affiliation_claimed"] = True
        _rehash(profile)
        with self.assertRaisesRegex(
            ResearchReadinessError, "must not claim affiliation"
        ):
            validate_research_readiness_profile(profile, root=ROOT)

    def test_rehashed_empty_official_sources_are_rejected(self) -> None:
        profile = copy.deepcopy(_profile())
        profile["organization_context"]["official_sources"] = []
        _rehash(profile)
        with self.assertRaisesRegex(
            ResearchReadinessError, "official_sources must not be empty"
        ):
            validate_research_readiness_profile(profile, root=ROOT)

    def test_rehashed_duplicate_pilot_phase_is_rejected(self) -> None:
        profile = copy.deepcopy(_profile())
        profile["pilot"]["phases"][1]["phase_id"] = profile["pilot"]["phases"][0][
            "phase_id"
        ]
        _rehash(profile)
        with self.assertRaisesRegex(ResearchReadinessError, "duplicate pilot phase_id"):
            validate_research_readiness_profile(profile, root=ROOT)

    def test_rehashed_required_gap_removal_is_rejected(self) -> None:
        profile = copy.deepcopy(_profile())
        profile["known_gaps"].pop()
        _rehash(profile)
        with self.assertRaisesRegex(
            ResearchReadinessError, "preserve the reviewed gap set"
        ):
            validate_research_readiness_profile(profile, root=ROOT)

    def test_cli_validate_and_summarize(self) -> None:
        for command in ("validate", "summarize"):
            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "agentic_drug_discovery.research_readiness_cli",
                    command,
                    "--profile",
                    str(PROFILE),
                    "--root",
                    str(ROOT),
                ],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["profile_id"], RESEARCH_READINESS_PROFILE_ID)
            if command == "validate":
                self.assertTrue(payload["valid"])

    def test_cli_rejects_modified_profile(self) -> None:
        profile = copy.deepcopy(_profile())
        profile["decision"]["pilot_readiness"] = "ready_for_execution"
        _rehash(profile)
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "profile.json"
            path.write_text(json.dumps(profile), encoding="utf-8")
            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "agentic_drug_discovery.research_readiness_cli",
                    "validate",
                    "--profile",
                    str(path),
                    "--root",
                    str(ROOT),
                ],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
        self.assertEqual(completed.returncode, 2)
        error = json.loads(completed.stderr)
        self.assertEqual(error["error"]["code"], "invalid_research_readiness_profile")


if __name__ == "__main__":
    unittest.main()
