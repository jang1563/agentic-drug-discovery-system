from __future__ import annotations

import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from agentic_drug_discovery.clinical_effects import (
    canonical_effect_measure,
    canonical_ratio_effect_measure,
    effect_benefit_direction,
    ratio_benefit_direction,
    ratio_effect_favorable_direction,
    risk_difference_ci_width_percentage_points,
    risk_difference_effect_scale,
    validate_effect_contract,
    validate_effect_interval,
    validate_effect_measure_unit,
    validate_effect_scale_interval,
    validate_ratio_effect_contract,
)
from agentic_drug_discovery.clinical_endpoint_mapping import (
    clinical_endpoint_mapping_spec_from_dict,
    clinical_endpoint_mapping_spec_to_dict,
)
from agentic_drug_discovery.clinical_synthesis import (
    clinical_synthesis_spec_from_dict,
    clinical_synthesis_spec_to_dict,
)
from agentic_drug_discovery.translational_handoff import (
    compile_translational_handoff_evidence,
    load_translational_handoff,
)


ROOT = Path(__file__).resolve().parents[1]
MAPPING_SCHEMA = ROOT / "rl_env/specs/clinical_endpoint_mapping.schema.json"
MAPPING = ROOT / "rl_env/specs/clinical_endpoint_mapping.uc.synthetic.example.json"
SYNTHESIS_SCHEMA = ROOT / "rl_env/specs/clinical_benefit_risk_synthesis.schema.json"
SYNTHESIS = (
    ROOT / "rl_env/specs/clinical_benefit_risk_synthesis.uc.synthetic.example.json"
)
HANDOFF_SCHEMA = ROOT / "rl_env/specs/translational_handoff.schema.json"
HANDOFF = ROOT / "rl_env/specs/translational_handoff.uc.synthetic.example.json"


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class CrossDiseaseClinicalConformanceTests(unittest.TestCase):
    def test_supported_registry_ratio_aliases_are_canonical(self) -> None:
        expected = {
            "Hazard Ratio (HR)": "hazard_ratio",
            "Odds Ratio (OR)": "odds_ratio",
            "Risk Ratio (RR)": "risk_ratio",
            "Relative Risk": "risk_ratio",
        }
        self.assertEqual(
            {label: canonical_ratio_effect_measure(label) for label in expected},
            expected,
        )
        self.assertIsNone(canonical_ratio_effect_measure("Mean Difference"))

    def test_ratio_contracts_and_interval_direction_are_fail_closed(self) -> None:
        self.assertEqual(
            ratio_effect_favorable_direction("hazard_ratio"),
            "lower_is_better",
        )
        self.assertEqual(
            ratio_effect_favorable_direction("odds_ratio"),
            "higher_is_better",
        )
        self.assertEqual(
            ratio_effect_favorable_direction("risk_ratio"),
            "higher_is_better",
        )
        self.assertEqual(
            ratio_benefit_direction(0.5, 0.8, "lower_is_better"),
            "benefit",
        )
        self.assertEqual(
            ratio_benefit_direction(1.2, 2.0, "higher_is_better"),
            "benefit",
        )
        self.assertEqual(
            ratio_benefit_direction(0.8, 1.2, "higher_is_better"),
            "null_or_uncertain",
        )
        with self.assertRaisesRegex(ValueError, "requires higher_is_better"):
            validate_ratio_effect_contract("odds_ratio", "lower_is_better")

    def test_additive_risk_difference_contract_is_direction_and_scale_aware(
        self,
    ) -> None:
        aliases = (
            "Difference in percentage",
            "Risk Difference (RD)",
            "Adjusted risk difference (%)",
        )
        self.assertEqual(
            {canonical_effect_measure(label) for label in aliases},
            {"risk_difference"},
        )
        self.assertIsNone(canonical_ratio_effect_measure(aliases[0]))
        self.assertIsNone(canonical_effect_measure("Adjusted treatment difference"))
        for direction in ("higher_is_better", "lower_is_better"):
            validate_effect_contract("risk_difference", direction)
        self.assertEqual(
            effect_benefit_direction(
                15.3,
                31.2,
                "risk_difference",
                "higher_is_better",
            ),
            "benefit",
        )
        self.assertEqual(
            effect_benefit_direction(
                -12.0,
                -2.0,
                "risk_difference",
                "lower_is_better",
            ),
            "benefit",
        )
        self.assertEqual(
            effect_benefit_direction(
                -1.0,
                2.0,
                "risk_difference",
                "higher_is_better",
            ),
            "null_or_uncertain",
        )
        with self.assertRaisesRegex(ValueError, "finite"):
            validate_effect_interval(
                float("nan"),
                -1.0,
                1.0,
                "risk_difference",
            )
        with self.assertRaisesRegex(ValueError, "contain"):
            validate_effect_interval(2.0, -1.0, 1.0, "risk_difference")
        validate_effect_measure_unit(
            "risk_difference",
            "percentage of participants",
        )
        validate_effect_measure_unit("risk_difference", "participants")
        self.assertEqual(
            risk_difference_effect_scale("Percentage of Participants"),
            "percentage_points",
        )
        self.assertEqual(
            risk_difference_effect_scale("Participants"),
            "proportion",
        )
        validate_effect_scale_interval(
            0.19,
            0.03,
            0.337,
            "risk_difference",
            "Participants",
        )
        self.assertAlmostEqual(
            risk_difference_ci_width_percentage_points(
                0.03,
                0.337,
                "Participants",
            ),
            30.7,
        )
        with self.assertRaisesRegex(ValueError, r"within \[-1, 1\]"):
            validate_effect_scale_interval(
                1.1,
                1.0,
                1.2,
                "risk_difference",
                "Participants",
            )
        with self.assertRaisesRegex(ValueError, "binary-count"):
            validate_effect_measure_unit(
                "risk_difference",
                "percent change from baseline",
            )

    def test_uc_examples_validate_round_trip_and_share_disease_identity(self) -> None:
        mapping_schema = _json(MAPPING_SCHEMA)
        synthesis_schema = _json(SYNTHESIS_SCHEMA)
        handoff_schema = _json(HANDOFF_SCHEMA)
        mapping_data = _json(MAPPING)
        synthesis_data = _json(SYNTHESIS)
        handoff_data = _json(HANDOFF)
        for schema in (mapping_schema, synthesis_schema, handoff_schema):
            Draft202012Validator.check_schema(schema)
        Draft202012Validator(mapping_schema).validate(mapping_data)
        Draft202012Validator(synthesis_schema).validate(synthesis_data)
        Draft202012Validator(
            handoff_schema,
            format_checker=FormatChecker(),
        ).validate(handoff_data)

        mapping = clinical_endpoint_mapping_spec_from_dict(mapping_data)
        synthesis = clinical_synthesis_spec_from_dict(synthesis_data)
        handoff = load_translational_handoff(HANDOFF)
        self.assertEqual(clinical_endpoint_mapping_spec_to_dict(mapping), mapping_data)
        self.assertEqual(clinical_synthesis_spec_to_dict(synthesis), synthesis_data)
        self.assertEqual(
            {mapping.disease_id, synthesis.disease_id, handoff["program"]["disease_id"]},
            {"MONDO:0005101"},
        )
        self.assertEqual(mapping.mapping_id, synthesis.endpoint_mapping_id)
        self.assertEqual(mapping.endpoint_family_id, synthesis.endpoint_family)
        self.assertEqual(mapping.effect_measure, synthesis.effect_measure)
        self.assertEqual(mapping.favorable_direction, "higher_is_better")
        drafts = compile_translational_handoff_evidence(
            handoff,
            request_id="synthetic-uc-conformance",
        )
        self.assertEqual({item.relation.value for item in drafts}, {"contextualizes"})

    def test_uc_schema_rejects_reversed_odds_ratio_direction(self) -> None:
        schema = _json(MAPPING_SCHEMA)
        mapping = _json(MAPPING)
        mapping["favorable_direction"] = "lower_is_better"
        errors = list(Draft202012Validator(schema).iter_errors(mapping))
        self.assertTrue(errors)

    def test_public_schemas_accept_directional_risk_difference(self) -> None:
        mapping = _json(MAPPING)
        mapping["effect_measure"] = "risk_difference"
        mapping["favorable_direction"] = "higher_is_better"
        synthesis = _json(SYNTHESIS)
        synthesis["effect_measure"] = "risk_difference"
        synthesis["effect_measure_favorable_direction"] = "higher_is_better"

        Draft202012Validator(_json(MAPPING_SCHEMA)).validate(mapping)
        Draft202012Validator(_json(SYNTHESIS_SCHEMA)).validate(synthesis)


if __name__ == "__main__":
    unittest.main()
