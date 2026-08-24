from __future__ import annotations

import copy
import hashlib
import json
import unittest
from dataclasses import replace
from pathlib import Path

from jsonschema import Draft202012Validator

from agentic_drug_discovery.clinical_endpoint_review_candidates import (
    ClinicalEndpointReviewCandidateError,
    ClinicalEndpointReviewCandidateSpec,
    clinical_endpoint_review_candidate_packet_envelope,
    clinical_endpoint_review_candidate_packet_from_dict,
    clinical_endpoint_review_candidate_packet_from_json,
    clinical_endpoint_review_candidate_packet_summary,
    clinical_endpoint_review_candidate_spec_from_dict,
    clinical_endpoint_review_candidate_spec_from_json,
    clinical_endpoint_review_candidate_spec_to_dict,
    compile_clinical_endpoint_review_candidate_packet,
    validate_clinical_endpoint_review_candidate_packet,
)
from tests.test_clinical_benefit_risk_portfolio import _unmapped_state
from tests.test_clinical_benefit_risk_portfolio_stress import (
    _phase_bound_multi_endpoint_design,
)


ROOT = Path(__file__).resolve().parents[1]
SPEC_SCHEMA = ROOT / "rl_env/specs/clinical_endpoint_review_candidate_spec.schema.json"
PACKET_SCHEMA = (
    ROOT / "rl_env/specs/clinical_endpoint_review_candidate_packet.schema.json"
)


def _state(*, population_mismatch: bool = False, timeframe_mismatch: bool = False):
    state = _unmapped_state(("NCT00000001", "NCT00000002"))
    transformed = tuple(
        _phase_bound_multi_endpoint_design(
            design,
            state.evidence_by_id,
            population_mismatch=population_mismatch,
            timeframe_mismatch=timeframe_mismatch,
        )
        for design in state.trial_designs
    )
    return replace(
        state,
        evidence=(
            *state.evidence,
            *(event for _, events in transformed for event in events),
        ),
        trial_designs=tuple(design for design, _ in transformed),
    )


def _spec(state) -> ClinicalEndpointReviewCandidateSpec:
    return ClinicalEndpointReviewCandidateSpec(
        packet_id="CHEMBL_TEST:MONDO_TEST:endpoint-review-candidates:v1",
        candidate_id="CHEMBL_TEST",
        intervention_id="CHEMBL_TEST",
        disease_id="MONDO_TEST",
        design_ids=tuple(sorted(item.design_id for item in state.trial_designs)),
    )


def _rehashed(envelope: dict) -> dict:
    encoded = json.dumps(
        envelope["packet"],
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    envelope["integrity_sha256"] = hashlib.sha256(encoded).hexdigest()
    return envelope


class ClinicalEndpointReviewCandidateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.state = _state()
        cls.spec = _spec(cls.state)
        cls.packet = compile_clinical_endpoint_review_candidate_packet(
            cls.state,
            cls.spec,
        )

    def test_complete_enumeration_retains_secondary_endpoints_and_nonclaims(
        self,
    ) -> None:
        packet = self.packet
        expected_endpoint_ids = {
            endpoint.endpoint_id
            for design in self.state.trial_designs
            for endpoint in design.endpoints
        }
        expected_population_ids = {
            population.population_id
            for design in self.state.trial_designs
            for population in design.populations
        }
        expected_safety_ids = {
            safety.safety_id
            for design in self.state.trial_designs
            for safety in design.safety_records
        }

        self.assertEqual(
            {item.endpoint_id for item in packet.endpoints}, expected_endpoint_ids
        )
        self.assertEqual(
            {item.population_id for item in packet.populations},
            expected_population_ids,
        )
        self.assertEqual(
            {item.safety_id for item in packet.safety_records},
            expected_safety_ids,
        )
        self.assertEqual(packet.design_count, 2)
        self.assertEqual(packet.endpoint_record_count, 4)
        self.assertEqual(packet.endpoint_candidate_count, 4)
        self.assertEqual(packet.endpoint_excluded_count, 0)
        self.assertEqual(packet.population_candidate_count, 2)
        self.assertEqual(packet.safety_candidate_count, 2)
        self.assertEqual(packet.endpoint_pair_count, 2)
        self.assertEqual(packet.endpoint_safety_link_count, 4)
        self.assertTrue(
            all(
                "secondary-0" in item.left_endpoint_id
                or "secondary-0" in item.right_endpoint_id
                for item in packet.endpoint_pairs
            )
        )
        self.assertTrue(packet.full_record_enumeration_performed)
        self.assertTrue(packet.full_state_replay_required)
        self.assertFalse(packet.reviewer_approval_performed)
        self.assertFalse(packet.endpoint_family_assigned)
        self.assertFalse(packet.ontology_mapping_approved)
        self.assertFalse(packet.estimand_equivalence_inferred)
        self.assertFalse(packet.clinical_comparability_inferred)
        self.assertFalse(packet.comparative_safety_inferred)
        self.assertFalse(packet.benefit_risk_synthesis_performed)
        self.assertFalse(packet.treatment_choice_inferred)
        self.assertTrue(
            all(not item.endpoint_family_assigned for item in packet.endpoints)
        )
        self.assertTrue(
            all(
                not item.endpoint_relationship_approved
                for item in packet.safety_records
            )
        )
        source_ids = {item.evidence_id for item in packet.source_evidence}
        self.assertTrue(
            all(
                set(item.source_evidence_ids).issubset(source_ids)
                for item in (
                    *packet.populations,
                    *packet.endpoints,
                    *packet.safety_records,
                )
            )
        )
        self.assertEqual(
            validate_clinical_endpoint_review_candidate_packet(
                self.state,
                self.spec,
                packet,
            ),
            (),
        )

    def test_population_and_timeframe_heterogeneity_remain_diagnostic_only(
        self,
    ) -> None:
        state = _state(population_mismatch=True, timeframe_mismatch=True)
        packet = compile_clinical_endpoint_review_candidate_packet(state, _spec(state))

        self.assertEqual(packet.population_record_count, 4)
        self.assertEqual(packet.population_candidate_count, 4)
        self.assertEqual(packet.endpoint_pair_count, 2)
        self.assertTrue(
            all(
                item.structural_status == "heterogeneous_structure"
                for item in packet.endpoint_pairs
            )
        )
        self.assertTrue(
            all(
                "analysis_population_identity_mismatch" in item.diagnostic_codes
                and "endpoint_timeframe_mismatch" in item.diagnostic_codes
                and not item.endpoint_equivalence_approved
                and not item.clinical_comparability_inferred
                for item in packet.endpoint_pairs
            )
        )

    def test_nonposted_and_nonserious_records_are_retained_in_excluded_partition(
        self,
    ) -> None:
        first = self.state.trial_designs[0]
        altered = replace(
            first,
            endpoints=(
                replace(first.endpoints[0], reporting_status="pending"),
                *first.endpoints[1:],
            ),
            safety_records=(replace(first.safety_records[0], event_category="other"),),
        )
        state = replace(
            self.state,
            trial_designs=(altered, *self.state.trial_designs[1:]),
        )
        packet = compile_clinical_endpoint_review_candidate_packet(state, _spec(state))

        self.assertEqual(packet.endpoint_record_count, 4)
        self.assertEqual(packet.endpoint_candidate_count, 3)
        self.assertEqual(packet.endpoint_excluded_count, 1)
        excluded_endpoint = next(
            item
            for item in packet.endpoints
            if item.eligibility_status == "mechanically_excluded"
        )
        self.assertEqual(
            excluded_endpoint.exclusion_reasons,
            ("reporting_status_not_posted",),
        )
        self.assertEqual(packet.safety_record_count, 2)
        self.assertEqual(packet.safety_candidate_count, 1)
        self.assertEqual(packet.safety_excluded_count, 1)
        excluded_safety = next(
            item
            for item in packet.safety_records
            if item.eligibility_status == "mechanically_excluded"
        )
        self.assertEqual(
            excluded_safety.exclusion_reasons, ("event_category_not_serious",)
        )
        self.assertEqual(packet.endpoint_pair_count, 1)
        self.assertEqual(packet.endpoint_safety_link_count, 2)

    def test_invalid_phase_alignment_is_retained_as_a_review_diagnostic(self) -> None:
        first = self.state.trial_designs[0]
        endpoint = first.endpoints[0]
        altered_endpoint = replace(
            endpoint,
            attributes={
                **dict(endpoint.attributes),
                "treatment_phase": "induction",
            },
        )
        altered = replace(
            first,
            endpoints=(altered_endpoint, *first.endpoints[1:]),
        )
        state = replace(
            self.state,
            trial_designs=(altered, *self.state.trial_designs[1:]),
        )
        packet = compile_clinical_endpoint_review_candidate_packet(state, _spec(state))

        link = next(
            item
            for item in packet.endpoint_safety_links
            if item.endpoint_id == altered_endpoint.endpoint_id
        )
        self.assertEqual(link.alignment_status, "population_alignment_invalid")
        self.assertFalse(link.endpoint_relationship_approved)
        self.assertFalse(link.common_safety_risk_window_inferred)
        self.assertFalse(link.comparative_safety_inferred)

    def test_unreferenced_population_is_retained_and_excluded(self) -> None:
        first = self.state.trial_designs[0]
        altered = replace(
            first,
            endpoints=tuple(
                replace(item, reporting_status="pending") for item in first.endpoints
            ),
        )
        state = replace(
            self.state,
            trial_designs=(altered, *self.state.trial_designs[1:]),
        )
        packet = compile_clinical_endpoint_review_candidate_packet(state, _spec(state))

        population = next(
            item for item in packet.populations if item.design_id == altered.design_id
        )
        self.assertEqual(population.eligibility_status, "mechanically_excluded")
        self.assertEqual(
            population.exclusion_reasons,
            ("not_referenced_by_posted_endpoint",),
        )
        self.assertEqual(population.referenced_endpoint_ids, ())
        self.assertEqual(packet.population_record_count, 2)
        self.assertEqual(packet.population_excluded_count, 1)

    def test_strict_schema_roundtrip_and_summary(self) -> None:
        spec_schema = json.loads(SPEC_SCHEMA.read_text(encoding="utf-8"))
        packet_schema = json.loads(PACKET_SCHEMA.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(spec_schema)
        Draft202012Validator.check_schema(packet_schema)
        spec_payload = clinical_endpoint_review_candidate_spec_to_dict(self.spec)
        envelope = clinical_endpoint_review_candidate_packet_envelope(self.packet)
        Draft202012Validator(spec_schema).validate(spec_payload)
        Draft202012Validator(packet_schema).validate(envelope)
        self.assertEqual(
            clinical_endpoint_review_candidate_spec_from_dict(spec_payload), self.spec
        )
        self.assertEqual(
            clinical_endpoint_review_candidate_spec_from_json(json.dumps(spec_payload)),
            self.spec,
        )
        self.assertEqual(
            clinical_endpoint_review_candidate_packet_from_dict(envelope), self.packet
        )
        self.assertEqual(
            clinical_endpoint_review_candidate_packet_from_json(json.dumps(envelope)),
            self.packet,
        )
        summary = clinical_endpoint_review_candidate_packet_summary(self.packet)
        self.assertEqual(summary["endpoint_record_count"], 4)
        self.assertFalse(summary["reviewer_approval_performed"])
        self.assertEqual(summary["integrity_sha256"], self.packet.fingerprint)

    def test_rehashed_eligibility_and_count_tampering_fail_parser(self) -> None:
        envelope = copy.deepcopy(
            clinical_endpoint_review_candidate_packet_envelope(self.packet)
        )
        envelope["packet"]["endpoints"][0]["eligibility_status"] = (
            "mechanically_excluded"
        )
        with self.assertRaisesRegex(ValueError, "eligibility"):
            clinical_endpoint_review_candidate_packet_from_dict(_rehashed(envelope))

        count_envelope = copy.deepcopy(
            clinical_endpoint_review_candidate_packet_envelope(self.packet)
        )
        count_envelope["packet"]["endpoint_pair_count"] = 99
        with self.assertRaisesRegex(ValueError, "endpoint_pair_count"):
            clinical_endpoint_review_candidate_packet_from_dict(
                _rehashed(count_envelope)
            )

    def test_rehashed_cross_link_pair_omission_and_date_tampering_fail(self) -> None:
        link_envelope = copy.deepcopy(
            clinical_endpoint_review_candidate_packet_envelope(self.packet)
        )
        link_envelope["packet"]["endpoint_safety_links"][0]["endpoint_time_frame"] = (
            "rebound window"
        )
        with self.assertRaisesRegex(ValueError, "endpoint_time_frame is rebound"):
            clinical_endpoint_review_candidate_packet_from_dict(
                _rehashed(link_envelope)
            )

        pair_envelope = copy.deepcopy(
            clinical_endpoint_review_candidate_packet_envelope(self.packet)
        )
        pair_envelope["packet"]["endpoint_pairs"].pop()
        pair_envelope["packet"]["endpoint_pair_count"] -= 1
        with self.assertRaisesRegex(ValueError, "pair enumeration"):
            clinical_endpoint_review_candidate_packet_from_dict(
                _rehashed(pair_envelope)
            )

        date_envelope = copy.deepcopy(
            clinical_endpoint_review_candidate_packet_envelope(self.packet)
        )
        date_envelope["packet"]["source_evidence"][0]["observed_at"] = "not-a-date"
        with self.assertRaisesRegex(ValueError, "ISO day precision"):
            clinical_endpoint_review_candidate_packet_from_dict(
                _rehashed(date_envelope)
            )

    def test_unknown_fields_duplicate_keys_and_nonfinite_values_fail(self) -> None:
        envelope = copy.deepcopy(
            clinical_endpoint_review_candidate_packet_envelope(self.packet)
        )
        envelope["packet"]["unsupported"] = True
        with self.assertRaisesRegex(ValueError, "must contain exactly"):
            clinical_endpoint_review_candidate_packet_from_dict(envelope)
        with self.assertRaisesRegex(ValueError, "duplicate JSON key"):
            clinical_endpoint_review_candidate_packet_from_json(
                '{"schema_version":"x","schema_version":"y"}'
            )
        with self.assertRaisesRegex(ValueError, "non-finite"):
            clinical_endpoint_review_candidate_spec_from_json('{"schema_version":NaN}')

    def test_missing_source_and_full_state_rebinding_fail(self) -> None:
        first = self.state.trial_designs[0]
        rebound_endpoint = replace(
            first.endpoints[0],
            supporting_evidence=("missing:endpoint:evidence",),
        )
        rebound_design = replace(
            first,
            endpoints=(rebound_endpoint, *first.endpoints[1:]),
        )
        rebound_state = replace(
            self.state,
            trial_designs=(rebound_design, *self.state.trial_designs[1:]),
        )
        with self.assertRaisesRegex(
            ClinicalEndpointReviewCandidateError,
            "missing evidence",
        ):
            compile_clinical_endpoint_review_candidate_packet(
                rebound_state,
                _spec(rebound_state),
            )
        self.assertEqual(
            validate_clinical_endpoint_review_candidate_packet(
                self.state,
                self.spec,
                replace(self.packet, state_sha256="0" * 64),
            ),
            ("clinical_endpoint_review_candidate_packet_mismatch",),
        )


if __name__ == "__main__":
    unittest.main()
