"""Independent-family tokenizer diagnostics for ADDS-Frontier placebos."""

from __future__ import annotations

import hashlib
import importlib.metadata
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from .frontier import (
    FrontierContractError,
    _boolean,
    _date,
    _integer,
    _load_json,
    _record,
    _sha256,
    _text_list,
)
from .frontier_coupled_placebo import _added_node, _canonical_sha256
from .frontier_tokenizer_placebo import (
    _PLACEBO_ROLE_IDS,
    _load_frozen_encodings,
    _tokenizer_placebo_trial_zero_summary,
    frontier_tokenizer_placebo_key_set_integrity_sha256,
    frontier_tokenizer_placebo_packet_set_integrity_sha256,
    frontier_tokenizer_placebo_summary_integrity_sha256,
)


PROTOCOL_SCHEMA_VERSION = "adds.frontier-tokenizer-independent-evaluation-protocol.v1"
PRIVATE_REPORT_SCHEMA_VERSION = (
    "adds.frontier-private-tokenizer-independent-evaluation-report.v1"
)
SUMMARY_SCHEMA_VERSION = "adds.frontier-tokenizer-independent-evaluation-summary.v1"
PROTOCOL_ID = "adds-frontier-tokenizer-independent-family-evaluation-v1"
PARENT_SET_ID = "adds-frontier-tokenizer-placebo-v1"
TOKENIZER_IMPLEMENTATIONS = (
    {
        "evaluation_id": "bert_wordpiece_uncased",
        "algorithm_family": "wordpiece",
        "package": "tokenizers",
        "package_version": "0.23.1",
        "model_repository": "google-bert/bert-base-uncased",
        "model_revision": "86b5e0934494bd15c9632b12f734a8a67f723594",
        "license": "apache-2.0",
        "asset_path": "vocab.txt",
        "source_asset_url": (
            "https://huggingface.co/google-bert/bert-base-uncased/resolve/"
            "86b5e0934494bd15c9632b12f734a8a67f723594/vocab.txt"
        ),
        "source_asset_sha256": (
            "07eced375cec144d27c900241f3e339478dec958f92fddbc551f295c992038a3"
        ),
        "source_asset_size_bytes": 231508,
        "normalization_policy": (
            "bert_clean_lowercase_handle_chinese_strip_accents_default"
        ),
        "special_token_policy": "no_cls_sep_or_padding",
        "continuation_prefix": "##",
    },
    {
        "evaluation_id": "t5_sentencepiece_unigram",
        "algorithm_family": "sentencepiece_unigram",
        "package": "sentencepiece",
        "package_version": "0.2.2",
        "model_repository": "google-t5/t5-base",
        "model_revision": "a9723ea7f1b39c1eae772870f3b547bf6ef7e6c1",
        "license": "apache-2.0",
        "asset_path": "spiece.model",
        "source_asset_url": (
            "https://huggingface.co/google-t5/t5-base/resolve/"
            "a9723ea7f1b39c1eae772870f3b547bf6ef7e6c1/spiece.model"
        ),
        "source_asset_sha256": (
            "d60acb128cf7b7f2536e8f38a5b18a05535c9e14c7a355904270e15b0945ea86"
        ),
        "source_asset_size_bytes": 791656,
        "normalization_policy": "sentencepiece_model_embedded",
        "special_token_policy": "no_bos_eos_or_padding",
        "word_start_marker": "\u2581",
    },
)
PROFILE_DEFINITION = {
    "piece_byte_length_bins": list(range(1, 9)),
    "piece_byte_length_overflow_bin": 8,
    "boundary_class_order": ["word_start", "continuation", "unknown"],
    "wordpiece_surface_rule": ("remove_continuation_prefix_before_utf8_byte_count"),
    "sentencepiece_surface_rule": (
        "replace_word_start_marker_with_one_ascii_space_before_utf8_byte_count"
    ),
    "profile_l1_distance_rule": (
        "piece_byte_length_histogram_l1_plus_boundary_class_histogram_l1"
    ),
    "token_count_absolute_gap_rule": ("absolute_candidate_minus_placebo_token_count"),
}
EVALUATION_UNITS = {
    "placebo_count": 30,
    "tokenizer_comparison_count": 60,
    "profile_component_comparison_count": 120,
    "token_count_gap_comparison_count": 60,
    "vocabulary_family_count": 3,
}
GATES = {
    "profile_encoding_nonregression_required": 60,
    "profile_component_nonregression_required": 120,
    "all_profile_nonregression_placebo_required": 30,
    "any_profile_strict_improvement_placebo_required": 30,
    "token_count_gap_nonregression_required": 60,
    "tokenizer_aggregate_strict_improvement_required": 2,
    "vocabulary_family_aggregate_strict_improvement_required": 3,
    "exact_token_count_match_required_for_confound_control": 60,
}
GATE_EVALUATION_ORDER = (
    "asset_and_implementation_provenance",
    "upstream_selection_noninterference",
    "profile_component_nonregression",
    "profile_encoding_nonregression",
    "placebo_level_nonregression_and_strict_improvement",
    "token_count_gap_nonregression",
    "tokenizer_and_vocabulary_family_aggregate_improvement",
    "exact_token_count_confound_control",
)
_PUBLIC_NONCLAIMS = {
    "The protocol was locally sealed before evaluation but was not publicly preregistered or externally timestamped.",
    "WordPiece and SentencePiece results do not establish universal tokenizer generalization.",
    "Profile-distance improvement does not establish token-distribution equivalence.",
    "Tokenizer controls do not establish semantic placebo invariance or scientific irrelevance.",
    "No evaluation result may retune the upstream cl100k_base/o200k_base selection.",
    "No model behavior, benchmark performance, board admission, or treatment claim is evaluated.",
    "Private text, per-placebo diagnostics, task identity, and failure locations are not published.",
}
_PRIVATE_NONCLAIMS = {
    "Per-placebo diagnostics are evaluator-only and must not enter a public release.",
    "The report evaluates frozen selected text and does not alter upstream selection.",
    "Distance and token-count diagnostics are lexical controls, not semantic labels.",
    "Protocol failure must remain visible and must not trigger threshold revision.",
}


def protocol_integrity_sha256(protocol: Mapping[str, Any]) -> str:
    return _canonical_sha256(protocol, exclude=frozenset({"integrity_sha256"}))


def private_report_integrity_sha256(report: Mapping[str, Any]) -> str:
    return _canonical_sha256(report, exclude=frozenset({"integrity_sha256"}))


def summary_integrity_sha256(summary: Mapping[str, Any]) -> str:
    return _canonical_sha256(summary, exclude=frozenset({"integrity_sha256"}))


def validate_protocol(
    protocol: Mapping[str, Any], *, parent_summary: Mapping[str, Any]
) -> dict[str, Any]:
    fields = {
        "schema_version",
        "protocol_id",
        "parent_tokenizer_placebo_set_id",
        "parent_summary_integrity_sha256",
        "sealed_on",
        "status",
        "evaluation_stage",
        "evaluation_used_for_upstream_selection",
        "public_preregistration_established",
        "evaluation_text_accessed_before_seal",
        "tokenizer_implementations",
        "profile_definition",
        "evaluation_units",
        "gates",
        "gate_evaluation_order",
        "retuning_policy",
        "failure_policy",
        "payload_policy",
        "nonclaims",
        "integrity_sha256",
    }
    data = _record(protocol, "independent tokenizer protocol", fields)
    if (
        data["schema_version"] != PROTOCOL_SCHEMA_VERSION
        or data["protocol_id"] != PROTOCOL_ID
        or data["parent_tokenizer_placebo_set_id"] != PARENT_SET_ID
        or parent_summary.get("set_id") != PARENT_SET_ID
    ):
        raise FrontierContractError("independent tokenizer protocol rebound identity")
    if parent_summary.get("integrity_sha256") != (
        frontier_tokenizer_placebo_summary_integrity_sha256(parent_summary)
    ):
        raise FrontierContractError("independent tokenizer parent integrity mismatch")
    if (
        _sha256(
            data["parent_summary_integrity_sha256"],
            "independent tokenizer parent summary",
        )
        != parent_summary["integrity_sha256"]
    ):
        raise FrontierContractError("independent tokenizer protocol rebound parent")
    _date(data["sealed_on"], "independent tokenizer sealed_on")
    if (
        data["status"] != "local_pre_evaluation_seal_no_results"
        or data["evaluation_stage"] != "post_selection_second_stage"
    ):
        raise FrontierContractError("independent tokenizer protocol overstates seal")
    for field_name in (
        "evaluation_used_for_upstream_selection",
        "public_preregistration_established",
        "evaluation_text_accessed_before_seal",
    ):
        if _boolean(data[field_name], f"independent tokenizer {field_name}"):
            raise FrontierContractError(
                f"independent tokenizer {field_name} must remain false"
            )
    if data["tokenizer_implementations"] != list(TOKENIZER_IMPLEMENTATIONS):
        raise FrontierContractError("independent tokenizer implementation drift")
    if data["profile_definition"] != PROFILE_DEFINITION:
        raise FrontierContractError("independent tokenizer profile drift")
    if data["evaluation_units"] != EVALUATION_UNITS or data["gates"] != GATES:
        raise FrontierContractError("independent tokenizer gate drift")
    if data["gate_evaluation_order"] != list(GATE_EVALUATION_ORDER):
        raise FrontierContractError("independent tokenizer gate order drift")
    if data["retuning_policy"] != (
        "evaluation_results_must_not_change_upstream_search_selection_or_this_protocol"
    ):
        raise FrontierContractError("independent tokenizer retuning policy drift")
    if data["failure_policy"] != (
        "retain_all_failures_and_keep_readiness_false_without_threshold_revision"
    ):
        raise FrontierContractError("independent tokenizer failure policy drift")
    if data["payload_policy"] != (
        "publish_only_aggregate_results_and_commit_private_per_placebo_diagnostics"
    ):
        raise FrontierContractError("independent tokenizer payload policy drift")
    _text_list(data["nonclaims"], "independent tokenizer protocol nonclaims")
    if data["integrity_sha256"] != protocol_integrity_sha256(data):
        raise FrontierContractError("independent tokenizer protocol integrity mismatch")
    return data


def _verify_asset(path: Path, implementation: Mapping[str, Any]) -> None:
    if not path.is_file():
        raise FrontierContractError(
            f"independent tokenizer asset missing for {implementation['evaluation_id']}"
        )
    payload = path.read_bytes()
    if len(payload) != implementation["source_asset_size_bytes"]:
        raise FrontierContractError("independent tokenizer asset size mismatch")
    if hashlib.sha256(payload).hexdigest() != implementation["source_asset_sha256"]:
        raise FrontierContractError("independent tokenizer asset hash mismatch")


def _profile_from_pieces(
    pieces: Sequence[str],
    *,
    continuation_prefix: str | None = None,
    word_start_marker: str | None = None,
    unknown_piece: str,
) -> dict[str, Any]:
    byte_histogram = [0] * 8
    boundary_histogram = [0] * 3
    for piece in pieces:
        if piece == unknown_piece:
            boundary_index = 2
            surface = piece
        elif continuation_prefix is not None and piece.startswith(continuation_prefix):
            boundary_index = 1
            surface = piece[len(continuation_prefix) :]
        elif word_start_marker is not None and piece.startswith(word_start_marker):
            boundary_index = 0
            surface = " " + piece[len(word_start_marker) :]
        elif continuation_prefix is not None:
            boundary_index = 0
            surface = piece
        else:
            boundary_index = 1
            surface = piece
        byte_length = max(1, len(surface.encode("utf-8")))
        byte_histogram[min(byte_length, 8) - 1] += 1
        boundary_histogram[boundary_index] += 1
    return {
        "token_count": len(pieces),
        "piece_byte_length_histogram": byte_histogram,
        "boundary_class_histogram": boundary_histogram,
        "unknown_token_count": boundary_histogram[2],
    }


def _load_tokenizers(
    protocol: Mapping[str, Any], *, asset_root: Path
) -> dict[str, Callable[[str], dict[str, Any]]]:
    implementations = protocol["tokenizer_implementations"]
    for implementation in implementations:
        package = implementation["package"]
        if importlib.metadata.version(package) != implementation["package_version"]:
            raise FrontierContractError(
                f"independent tokenizer requires {package}=={implementation['package_version']}"
            )
    try:
        import sentencepiece as spm
        from tokenizers import BertWordPieceTokenizer
    except ImportError as exc:
        raise FrontierContractError(
            "install the frontier-tokenizer-eval extra before private evaluation"
        ) from exc

    wordpiece_spec, sentencepiece_spec = implementations
    wordpiece_path = (
        asset_root / wordpiece_spec["evaluation_id"] / wordpiece_spec["asset_path"]
    )
    sentencepiece_path = (
        asset_root
        / sentencepiece_spec["evaluation_id"]
        / sentencepiece_spec["asset_path"]
    )
    _verify_asset(wordpiece_path, wordpiece_spec)
    _verify_asset(sentencepiece_path, sentencepiece_spec)
    wordpiece = BertWordPieceTokenizer(
        str(wordpiece_path),
        clean_text=True,
        handle_chinese_chars=True,
        strip_accents=None,
        lowercase=True,
    )
    sentencepiece = spm.SentencePieceProcessor(model_file=str(sentencepiece_path))

    def wordpiece_profile(text: str) -> dict[str, Any]:
        pieces = wordpiece.encode(text, add_special_tokens=False).tokens
        return _profile_from_pieces(
            pieces,
            continuation_prefix="##",
            unknown_piece="[UNK]",
        )

    def sentencepiece_profile(text: str) -> dict[str, Any]:
        pieces = sentencepiece.encode(text, out_type=str)
        return _profile_from_pieces(
            pieces,
            word_start_marker="\u2581",
            unknown_piece="<unk>",
        )

    return {
        wordpiece_spec["evaluation_id"]: wordpiece_profile,
        sentencepiece_spec["evaluation_id"]: sentencepiece_profile,
    }


def _component_distances(
    candidate: Mapping[str, Any], placebo: Mapping[str, Any]
) -> dict[str, int]:
    byte_distance = sum(
        abs(left - right)
        for left, right in zip(
            candidate["piece_byte_length_histogram"],
            placebo["piece_byte_length_histogram"],
            strict=True,
        )
    )
    boundary_distance = sum(
        abs(left - right)
        for left, right in zip(
            candidate["boundary_class_histogram"],
            placebo["boundary_class_histogram"],
            strict=True,
        )
    )
    return {
        "piece_byte_length_l1_distance": byte_distance,
        "boundary_class_l1_distance": boundary_distance,
        "combined_l1_distance": byte_distance + boundary_distance,
    }


def _evaluate_text_triplet(
    *,
    candidate: str,
    baseline: str,
    optimized: str,
    tokenizers: Mapping[str, Callable[[str], dict[str, Any]]],
) -> list[dict[str, Any]]:
    results = []
    for evaluation_id, profile in tokenizers.items():
        candidate_profile = profile(candidate)
        baseline_profile = profile(baseline)
        optimized_profile = profile(optimized)
        baseline_components = _component_distances(candidate_profile, baseline_profile)
        optimized_components = _component_distances(
            candidate_profile, optimized_profile
        )
        baseline_gap = abs(
            candidate_profile["token_count"] - baseline_profile["token_count"]
        )
        optimized_gap = abs(
            candidate_profile["token_count"] - optimized_profile["token_count"]
        )
        results.append(
            {
                "evaluation_id": evaluation_id,
                "candidate_token_count": candidate_profile["token_count"],
                "baseline_token_count": baseline_profile["token_count"],
                "optimized_token_count": optimized_profile["token_count"],
                "baseline_token_count_absolute_gap": baseline_gap,
                "optimized_token_count_absolute_gap": optimized_gap,
                "baseline_profile_component_distances": baseline_components,
                "optimized_profile_component_distances": optimized_components,
                "profile_nonregression_passed": (
                    optimized_components["combined_l1_distance"]
                    <= baseline_components["combined_l1_distance"]
                ),
                "profile_strict_improvement_passed": (
                    optimized_components["combined_l1_distance"]
                    < baseline_components["combined_l1_distance"]
                ),
                "component_nonregression_count": sum(
                    optimized_components[field] <= baseline_components[field]
                    for field in (
                        "piece_byte_length_l1_distance",
                        "boundary_class_l1_distance",
                    )
                ),
                "component_strict_improvement_count": sum(
                    optimized_components[field] < baseline_components[field]
                    for field in (
                        "piece_byte_length_l1_distance",
                        "boundary_class_l1_distance",
                    )
                ),
                "token_count_gap_nonregression_passed": optimized_gap <= baseline_gap,
                "token_count_gap_strict_improvement_passed": optimized_gap
                < baseline_gap,
                "optimized_exact_token_count_match_passed": optimized_gap == 0,
                "candidate_unknown_token_count": candidate_profile[
                    "unknown_token_count"
                ],
                "baseline_unknown_token_count": baseline_profile["unknown_token_count"],
                "optimized_unknown_token_count": optimized_profile[
                    "unknown_token_count"
                ],
            }
        )
    return results


def compile_artifacts(
    *,
    protocol: Mapping[str, Any],
    private_packet_set: Mapping[str, Any],
    private_key_set: Mapping[str, Any],
    parent_summary: Mapping[str, Any],
    asset_root: Path,
    compiled_on: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    protocol_data = validate_protocol(protocol, parent_summary=parent_summary)
    _date(compiled_on, "independent tokenizer compiled_on")
    if private_packet_set.get("integrity_sha256") != (
        frontier_tokenizer_placebo_packet_set_integrity_sha256(private_packet_set)
    ):
        raise FrontierContractError("independent tokenizer packet integrity mismatch")
    if private_key_set.get("integrity_sha256") != (
        frontier_tokenizer_placebo_key_set_integrity_sha256(private_key_set)
    ):
        raise FrontierContractError("independent tokenizer key integrity mismatch")
    if (
        private_packet_set["integrity_sha256"]
        != parent_summary["private_packet_set_commitment"]
        or private_key_set["integrity_sha256"]
        != parent_summary["private_key_set_commitment"]
    ):
        raise FrontierContractError("independent tokenizer private opening mismatch")

    tokenizers = _load_tokenizers(protocol_data, asset_root=asset_root)
    design_encodings = _load_frozen_encodings()
    packets = {packet["packet_id"]: packet for packet in private_packet_set["packets"]}
    records = []
    for key in private_key_set["keys"]:
        packet = packets[key["packet_id"]]
        canonical = packet[key["canonical_arm"]]
        candidate = packet[key["candidate_arm"]]
        candidate_summary = _added_node(canonical, candidate)["evidence_summary"]
        placebo_keys = {item["family_id"]: item for item in key["placebos"]}
        for family_id in _PLACEBO_ROLE_IDS:
            optimized = packet[key[f"{family_id}_arm"]]
            optimized_summary = _added_node(canonical, optimized)["evidence_summary"]
            baseline_summary = _tokenizer_placebo_trial_zero_summary(
                candidate_summary=candidate_summary,
                slot_id=key["slot_id"],
                family_id=family_id,
                encodings=design_encodings,
            )
            baseline_commitment = hashlib.sha256(
                baseline_summary.encode("utf-8")
            ).hexdigest()
            if (
                baseline_commitment
                != placebo_keys[family_id]["heldout_trial_zero_summary_commitment"]
            ):
                raise FrontierContractError(
                    "independent tokenizer trial-zero commitment mismatch"
                )
            tokenizer_results = _evaluate_text_triplet(
                candidate=candidate_summary,
                baseline=baseline_summary,
                optimized=optimized_summary,
                tokenizers=tokenizers,
            )
            records.append(
                {
                    "packet_id": key["packet_id"],
                    "family_id": family_id,
                    "trial_zero_summary_commitment": baseline_commitment,
                    "optimized_placebo_task_commitment": placebo_keys[family_id][
                        "placebo_task_commitment"
                    ],
                    "tokenizer_results": tokenizer_results,
                    "all_profile_nonregression_passed": all(
                        result["profile_nonregression_passed"]
                        for result in tokenizer_results
                    ),
                    "any_profile_strict_improvement_passed": any(
                        result["profile_strict_improvement_passed"]
                        for result in tokenizer_results
                    ),
                    "all_token_count_gap_nonregression_passed": all(
                        result["token_count_gap_nonregression_passed"]
                        for result in tokenizer_results
                    ),
                }
            )
    records.sort(key=lambda item: (item["packet_id"], item["family_id"]))
    report: dict[str, Any] = {
        "schema_version": PRIVATE_REPORT_SCHEMA_VERSION,
        "protocol_id": PROTOCOL_ID,
        "protocol_integrity_sha256": protocol_data["integrity_sha256"],
        "parent_summary_integrity_sha256": parent_summary["integrity_sha256"],
        "private_packet_set_integrity_sha256": private_packet_set["integrity_sha256"],
        "private_key_set_integrity_sha256": private_key_set["integrity_sha256"],
        "compiled_on": compiled_on,
        "tokenizer_implementations": list(TOKENIZER_IMPLEMENTATIONS),
        "records": records,
        "results_used_for_retuning": False,
        "upstream_selection_changed": False,
        "nonclaims": sorted(_PRIVATE_NONCLAIMS),
        "integrity_sha256": "0" * 64,
    }
    report["integrity_sha256"] = private_report_integrity_sha256(report)

    all_results = [
        result for record in records for result in record["tokenizer_results"]
    ]
    baseline_total = sum(
        result["baseline_profile_component_distances"]["combined_l1_distance"]
        for result in all_results
    )
    optimized_total = sum(
        result["optimized_profile_component_distances"]["combined_l1_distance"]
        for result in all_results
    )
    tokenizer_results = []
    for implementation in TOKENIZER_IMPLEMENTATIONS:
        evaluation_id = implementation["evaluation_id"]
        subset = [
            result for result in all_results if result["evaluation_id"] == evaluation_id
        ]
        baseline = sum(
            result["baseline_profile_component_distances"]["combined_l1_distance"]
            for result in subset
        )
        optimized = sum(
            result["optimized_profile_component_distances"]["combined_l1_distance"]
            for result in subset
        )
        tokenizer_results.append(
            {
                "evaluation_id": evaluation_id,
                "algorithm_family": implementation["algorithm_family"],
                "comparison_count": len(subset),
                "baseline_profile_l1_distance_total": baseline,
                "optimized_profile_l1_distance_total": optimized,
                "profile_l1_distance_reduction_total": baseline - optimized,
                "profile_nonregression_count": sum(
                    result["profile_nonregression_passed"] for result in subset
                ),
                "profile_strict_improvement_count": sum(
                    result["profile_strict_improvement_passed"] for result in subset
                ),
                "profile_regression_count": sum(
                    not result["profile_nonregression_passed"] for result in subset
                ),
                "optimized_exact_token_count_match_count": sum(
                    result["optimized_exact_token_count_match_passed"]
                    for result in subset
                ),
            }
        )
    family_results = []
    for family_id in _PLACEBO_ROLE_IDS:
        family_records = [
            record for record in records if record["family_id"] == family_id
        ]
        subset = [
            result
            for record in family_records
            for result in record["tokenizer_results"]
        ]
        baseline = sum(
            result["baseline_profile_component_distances"]["combined_l1_distance"]
            for result in subset
        )
        optimized = sum(
            result["optimized_profile_component_distances"]["combined_l1_distance"]
            for result in subset
        )
        family_results.append(
            {
                "family_id": family_id,
                "comparison_count": len(subset),
                "baseline_profile_l1_distance_total": baseline,
                "optimized_profile_l1_distance_total": optimized,
                "profile_l1_distance_reduction_total": baseline - optimized,
                "profile_nonregression_count": sum(
                    result["profile_nonregression_passed"] for result in subset
                ),
                "profile_strict_improvement_count": sum(
                    result["profile_strict_improvement_passed"] for result in subset
                ),
                "profile_regression_count": sum(
                    not result["profile_nonregression_passed"] for result in subset
                ),
            }
        )

    profile_nonregression_count = sum(
        result["profile_nonregression_passed"] for result in all_results
    )
    component_nonregression_count = sum(
        result["component_nonregression_count"] for result in all_results
    )
    placebo_nonregression_count = sum(
        record["all_profile_nonregression_passed"] for record in records
    )
    placebo_strict_count = sum(
        record["any_profile_strict_improvement_passed"] for record in records
    )
    gap_nonregression_count = sum(
        result["token_count_gap_nonregression_passed"] for result in all_results
    )
    tokenizer_aggregate_improvement_count = sum(
        result["profile_l1_distance_reduction_total"] > 0
        for result in tokenizer_results
    )
    family_aggregate_improvement_count = sum(
        result["profile_l1_distance_reduction_total"] > 0 for result in family_results
    )
    exact_token_count_match_count = sum(
        result["optimized_exact_token_count_match_passed"] for result in all_results
    )
    robust_profile_ready = (
        profile_nonregression_count == GATES["profile_encoding_nonregression_required"]
        and component_nonregression_count
        == GATES["profile_component_nonregression_required"]
        and placebo_nonregression_count
        == GATES["all_profile_nonregression_placebo_required"]
        and placebo_strict_count
        == GATES["any_profile_strict_improvement_placebo_required"]
        and gap_nonregression_count == GATES["token_count_gap_nonregression_required"]
        and tokenizer_aggregate_improvement_count
        == GATES["tokenizer_aggregate_strict_improvement_required"]
        and family_aggregate_improvement_count
        == GATES["vocabulary_family_aggregate_strict_improvement_required"]
    )
    token_count_ready = (
        exact_token_count_match_count
        == GATES["exact_token_count_match_required_for_confound_control"]
    )
    summary: dict[str, Any] = {
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "protocol_id": PROTOCOL_ID,
        "protocol_integrity_sha256": protocol_data["integrity_sha256"],
        "parent_tokenizer_placebo_set_id": PARENT_SET_ID,
        "parent_summary_integrity_sha256": parent_summary["integrity_sha256"],
        "private_report_commitment": report["integrity_sha256"],
        "compiled_on": compiled_on,
        "status": "independent_tokenizer_family_evaluation_completed",
        "evaluation_stage": "post_selection_second_stage",
        "public_preregistration_established": False,
        "evaluation_used_for_upstream_selection": False,
        "results_used_for_retuning": False,
        "upstream_selection_changed": False,
        "tokenizer_implementations": list(TOKENIZER_IMPLEMENTATIONS),
        "profile_definition": PROFILE_DEFINITION,
        "gates": GATES,
        "placebo_count": len(records),
        "tokenizer_comparison_count": len(all_results),
        "profile_component_comparison_count": len(all_results) * 2,
        "token_count_gap_comparison_count": len(all_results),
        "baseline_profile_l1_distance_total": baseline_total,
        "optimized_profile_l1_distance_total": optimized_total,
        "profile_l1_distance_reduction_total": baseline_total - optimized_total,
        "profile_encoding_nonregression_count": profile_nonregression_count,
        "profile_encoding_strict_improvement_count": sum(
            result["profile_strict_improvement_passed"] for result in all_results
        ),
        "profile_encoding_regression_count": len(all_results)
        - profile_nonregression_count,
        "profile_component_nonregression_count": component_nonregression_count,
        "profile_component_strict_improvement_count": sum(
            result["component_strict_improvement_count"] for result in all_results
        ),
        "profile_component_regression_count": len(all_results) * 2
        - component_nonregression_count,
        "all_profile_nonregression_placebo_count": placebo_nonregression_count,
        "any_profile_strict_improvement_placebo_count": placebo_strict_count,
        "profile_regression_placebo_count": len(records) - placebo_nonregression_count,
        "token_count_gap_nonregression_count": gap_nonregression_count,
        "token_count_gap_strict_improvement_count": sum(
            result["token_count_gap_strict_improvement_passed"]
            for result in all_results
        ),
        "token_count_gap_regression_count": len(all_results) - gap_nonregression_count,
        "optimized_exact_token_count_match_count": exact_token_count_match_count,
        "candidate_unknown_token_count_total": sum(
            result["candidate_unknown_token_count"] for result in all_results
        ),
        "baseline_unknown_token_count_total": sum(
            result["baseline_unknown_token_count"] for result in all_results
        ),
        "optimized_unknown_token_count_total": sum(
            result["optimized_unknown_token_count"] for result in all_results
        ),
        "tokenizer_results": tokenizer_results,
        "vocabulary_family_results": family_results,
        "tokenizer_aggregate_strict_improvement_count": (
            tokenizer_aggregate_improvement_count
        ),
        "vocabulary_family_aggregate_strict_improvement_count": (
            family_aggregate_improvement_count
        ),
        "aggregate_profile_improvement_observed": optimized_total < baseline_total,
        "robust_independent_family_profile_generalization_ready": (
            robust_profile_ready
        ),
        "independent_family_token_count_confound_control_ready": (token_count_ready),
        "independent_family_control_ready": robust_profile_ready and token_count_ready,
        "human_semantic_review_required": True,
        "placebo_scientific_invariance_established": False,
        "candidate_scientific_coupling_established": False,
        "benchmark_evidence_claimed": False,
        "private_payload_published": False,
        "nonclaims": sorted(_PUBLIC_NONCLAIMS),
        "integrity_sha256": "0" * 64,
    }
    summary["integrity_sha256"] = summary_integrity_sha256(summary)
    return report, summary


def load_protocol(path: Path) -> dict[str, Any]:
    return _load_json(
        path.read_text(encoding="utf-8"), "independent tokenizer protocol"
    )


def load_private_report(path: Path) -> dict[str, Any]:
    return _load_json(
        path.read_text(encoding="utf-8"), "independent tokenizer private report"
    )


def load_summary(path: Path) -> dict[str, Any]:
    return _load_json(path.read_text(encoding="utf-8"), "independent tokenizer summary")


def validate_summary(
    summary: Mapping[str, Any],
    *,
    protocol: Mapping[str, Any],
    parent_summary: Mapping[str, Any],
) -> dict[str, Any]:
    protocol_data = validate_protocol(protocol, parent_summary=parent_summary)
    fields = {
        "schema_version",
        "protocol_id",
        "protocol_integrity_sha256",
        "parent_tokenizer_placebo_set_id",
        "parent_summary_integrity_sha256",
        "private_report_commitment",
        "compiled_on",
        "status",
        "evaluation_stage",
        "public_preregistration_established",
        "evaluation_used_for_upstream_selection",
        "results_used_for_retuning",
        "upstream_selection_changed",
        "tokenizer_implementations",
        "profile_definition",
        "gates",
        "placebo_count",
        "tokenizer_comparison_count",
        "profile_component_comparison_count",
        "token_count_gap_comparison_count",
        "baseline_profile_l1_distance_total",
        "optimized_profile_l1_distance_total",
        "profile_l1_distance_reduction_total",
        "profile_encoding_nonregression_count",
        "profile_encoding_strict_improvement_count",
        "profile_encoding_regression_count",
        "profile_component_nonregression_count",
        "profile_component_strict_improvement_count",
        "profile_component_regression_count",
        "all_profile_nonregression_placebo_count",
        "any_profile_strict_improvement_placebo_count",
        "profile_regression_placebo_count",
        "token_count_gap_nonregression_count",
        "token_count_gap_strict_improvement_count",
        "token_count_gap_regression_count",
        "optimized_exact_token_count_match_count",
        "candidate_unknown_token_count_total",
        "baseline_unknown_token_count_total",
        "optimized_unknown_token_count_total",
        "tokenizer_results",
        "vocabulary_family_results",
        "tokenizer_aggregate_strict_improvement_count",
        "vocabulary_family_aggregate_strict_improvement_count",
        "aggregate_profile_improvement_observed",
        "robust_independent_family_profile_generalization_ready",
        "independent_family_token_count_confound_control_ready",
        "independent_family_control_ready",
        "human_semantic_review_required",
        "placebo_scientific_invariance_established",
        "candidate_scientific_coupling_established",
        "benchmark_evidence_claimed",
        "private_payload_published",
        "nonclaims",
        "integrity_sha256",
    }
    data = _record(summary, "independent tokenizer summary", fields)
    if (
        data["schema_version"] != SUMMARY_SCHEMA_VERSION
        or data["protocol_id"] != PROTOCOL_ID
        or data["parent_tokenizer_placebo_set_id"] != PARENT_SET_ID
    ):
        raise FrontierContractError("independent tokenizer summary rebound identity")
    for field_name, expected in (
        ("protocol_integrity_sha256", protocol_data["integrity_sha256"]),
        ("parent_summary_integrity_sha256", parent_summary["integrity_sha256"]),
    ):
        if _sha256(data[field_name], f"independent tokenizer {field_name}") != expected:
            raise FrontierContractError(
                f"independent tokenizer {field_name} commitment mismatch"
            )
    _sha256(
        data["private_report_commitment"],
        "independent tokenizer private report commitment",
    )
    _sha256(data["integrity_sha256"], "independent tokenizer summary integrity")
    _date(data["compiled_on"], "independent tokenizer compiled_on")
    if (
        data["status"] != "independent_tokenizer_family_evaluation_completed"
        or data["evaluation_stage"] != "post_selection_second_stage"
    ):
        raise FrontierContractError("independent tokenizer summary changed maturity")
    if data["tokenizer_implementations"] != list(TOKENIZER_IMPLEMENTATIONS):
        raise FrontierContractError("independent tokenizer summary changed provenance")
    if data["profile_definition"] != PROFILE_DEFINITION or data["gates"] != GATES:
        raise FrontierContractError("independent tokenizer summary changed protocol")
    exact_counts = {
        "placebo_count": 30,
        "tokenizer_comparison_count": 60,
        "profile_component_comparison_count": 120,
        "token_count_gap_comparison_count": 60,
        "baseline_profile_l1_distance_total": 1720,
        "optimized_profile_l1_distance_total": 1532,
        "profile_l1_distance_reduction_total": 188,
        "profile_encoding_nonregression_count": 51,
        "profile_encoding_strict_improvement_count": 41,
        "profile_encoding_regression_count": 9,
        "profile_component_nonregression_count": 94,
        "profile_component_strict_improvement_count": 74,
        "profile_component_regression_count": 26,
        "all_profile_nonregression_placebo_count": 23,
        "any_profile_strict_improvement_placebo_count": 26,
        "profile_regression_placebo_count": 7,
        "token_count_gap_nonregression_count": 44,
        "token_count_gap_strict_improvement_count": 32,
        "token_count_gap_regression_count": 16,
        "optimized_exact_token_count_match_count": 1,
        "candidate_unknown_token_count_total": 0,
        "baseline_unknown_token_count_total": 0,
        "optimized_unknown_token_count_total": 0,
        "tokenizer_aggregate_strict_improvement_count": 2,
        "vocabulary_family_aggregate_strict_improvement_count": 3,
    }
    for field_name, expected in exact_counts.items():
        if (
            _integer(data[field_name], f"independent tokenizer {field_name}")
            != expected
        ):
            raise FrontierContractError(
                f"independent tokenizer {field_name} must remain {expected}"
            )
    expected_tokenizer_results = [
        {
            "evaluation_id": "bert_wordpiece_uncased",
            "algorithm_family": "wordpiece",
            "comparison_count": 30,
            "baseline_profile_l1_distance_total": 894,
            "optimized_profile_l1_distance_total": 820,
            "profile_l1_distance_reduction_total": 74,
            "profile_nonregression_count": 28,
            "profile_strict_improvement_count": 19,
            "profile_regression_count": 2,
            "optimized_exact_token_count_match_count": 0,
        },
        {
            "evaluation_id": "t5_sentencepiece_unigram",
            "algorithm_family": "sentencepiece_unigram",
            "comparison_count": 30,
            "baseline_profile_l1_distance_total": 826,
            "optimized_profile_l1_distance_total": 712,
            "profile_l1_distance_reduction_total": 114,
            "profile_nonregression_count": 23,
            "profile_strict_improvement_count": 22,
            "profile_regression_count": 7,
            "optimized_exact_token_count_match_count": 1,
        },
    ]
    expected_family_results = [
        {
            "family_id": "placebo_transport",
            "comparison_count": 20,
            "baseline_profile_l1_distance_total": 750,
            "optimized_profile_l1_distance_total": 640,
            "profile_l1_distance_reduction_total": 110,
            "profile_nonregression_count": 19,
            "profile_strict_improvement_count": 16,
            "profile_regression_count": 1,
        },
        {
            "family_id": "placebo_schema",
            "comparison_count": 20,
            "baseline_profile_l1_distance_total": 516,
            "optimized_profile_l1_distance_total": 468,
            "profile_l1_distance_reduction_total": 48,
            "profile_nonregression_count": 16,
            "profile_strict_improvement_count": 12,
            "profile_regression_count": 4,
        },
        {
            "family_id": "placebo_audit",
            "comparison_count": 20,
            "baseline_profile_l1_distance_total": 454,
            "optimized_profile_l1_distance_total": 424,
            "profile_l1_distance_reduction_total": 30,
            "profile_nonregression_count": 16,
            "profile_strict_improvement_count": 13,
            "profile_regression_count": 4,
        },
    ]
    if data["tokenizer_results"] != expected_tokenizer_results:
        raise FrontierContractError("independent tokenizer result breakdown drift")
    if data["vocabulary_family_results"] != expected_family_results:
        raise FrontierContractError("independent tokenizer family breakdown drift")
    for field_name in (
        "aggregate_profile_improvement_observed",
        "human_semantic_review_required",
    ):
        if not _boolean(data[field_name], f"independent tokenizer {field_name}"):
            raise FrontierContractError(
                f"independent tokenizer {field_name} must remain true"
            )
    for field_name in (
        "public_preregistration_established",
        "evaluation_used_for_upstream_selection",
        "results_used_for_retuning",
        "upstream_selection_changed",
        "robust_independent_family_profile_generalization_ready",
        "independent_family_token_count_confound_control_ready",
        "independent_family_control_ready",
        "placebo_scientific_invariance_established",
        "candidate_scientific_coupling_established",
        "benchmark_evidence_claimed",
        "private_payload_published",
    ):
        if _boolean(data[field_name], f"independent tokenizer {field_name}"):
            raise FrontierContractError(
                f"independent tokenizer {field_name} must remain false"
            )
    if not _PUBLIC_NONCLAIMS.issubset(
        set(_text_list(data["nonclaims"], "independent tokenizer nonclaims"))
    ):
        raise FrontierContractError("independent tokenizer removed a public nonclaim")
    if data["integrity_sha256"] != summary_integrity_sha256(data):
        raise FrontierContractError("independent tokenizer summary integrity mismatch")
    return data


def summary_view(
    summary: Mapping[str, Any],
    *,
    protocol: Mapping[str, Any],
    parent_summary: Mapping[str, Any],
) -> dict[str, Any]:
    data = validate_summary(
        summary,
        protocol=protocol,
        parent_summary=parent_summary,
    )
    return {
        "protocol_id": data["protocol_id"],
        "status": data["status"],
        "evaluation_stage": data["evaluation_stage"],
        "algorithm_families": [
            item["algorithm_family"] for item in data["tokenizer_implementations"]
        ],
        "public_preregistration_established": data[
            "public_preregistration_established"
        ],
        "evaluation_used_for_upstream_selection": data[
            "evaluation_used_for_upstream_selection"
        ],
        "baseline_profile_l1_distance_total": data[
            "baseline_profile_l1_distance_total"
        ],
        "optimized_profile_l1_distance_total": data[
            "optimized_profile_l1_distance_total"
        ],
        "profile_l1_distance_reduction_total": data[
            "profile_l1_distance_reduction_total"
        ],
        "profile_encoding_nonregression_count": data[
            "profile_encoding_nonregression_count"
        ],
        "tokenizer_comparison_count": data["tokenizer_comparison_count"],
        "all_profile_nonregression_placebo_count": data[
            "all_profile_nonregression_placebo_count"
        ],
        "profile_regression_placebo_count": data["profile_regression_placebo_count"],
        "token_count_gap_nonregression_count": data[
            "token_count_gap_nonregression_count"
        ],
        "optimized_exact_token_count_match_count": data[
            "optimized_exact_token_count_match_count"
        ],
        "aggregate_profile_improvement_observed": data[
            "aggregate_profile_improvement_observed"
        ],
        "robust_independent_family_profile_generalization_ready": data[
            "robust_independent_family_profile_generalization_ready"
        ],
        "independent_family_token_count_confound_control_ready": data[
            "independent_family_token_count_confound_control_ready"
        ],
        "independent_family_control_ready": data["independent_family_control_ready"],
    }


def validate_private_opening(
    *,
    private_report: Mapping[str, Any],
    summary: Mapping[str, Any],
    protocol: Mapping[str, Any],
    private_packet_set: Mapping[str, Any],
    private_key_set: Mapping[str, Any],
    parent_summary: Mapping[str, Any],
    asset_root: Path,
) -> dict[str, Any]:
    data = validate_summary(
        summary,
        protocol=protocol,
        parent_summary=parent_summary,
    )
    if private_report.get("integrity_sha256") != (
        private_report_integrity_sha256(private_report)
    ):
        raise FrontierContractError("independent tokenizer private integrity mismatch")
    if private_report["integrity_sha256"] != data["private_report_commitment"]:
        raise FrontierContractError("independent tokenizer private commitment mismatch")
    expected_report, expected_summary = compile_artifacts(
        protocol=protocol,
        private_packet_set=private_packet_set,
        private_key_set=private_key_set,
        parent_summary=parent_summary,
        asset_root=asset_root,
        compiled_on=data["compiled_on"],
    )
    if private_report != expected_report or summary != expected_summary:
        raise FrontierContractError(
            "independent tokenizer artifacts do not replay from sealed inputs"
        )
    return summary_view(
        summary,
        protocol=protocol,
        parent_summary=parent_summary,
    ) | {"private_independent_tokenizer_commitment_opened": True}
