"""Tokenizer-aware five-arm placebo controls for ADDS-Frontier."""

from __future__ import annotations

import copy
import hashlib
import importlib.metadata
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import tiktoken
from tiktoken.core import Encoding

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
from .frontier_calibration import (
    frontier_calibration_task_sha256,
    validate_frontier_calibration_oracle_set,
    validate_frontier_calibration_progress,
    validate_frontier_calibration_task_set,
)
from .frontier_coupled_placebo import (
    _added_node,
    _canonical_sha256,
    _structural_fingerprint,
    validate_frontier_coupled_placebo_private_opening,
    validate_frontier_coupled_placebo_summary,
)
from .frontier_semantic_review import (
    _delta_certificate,
    _validate_materialized_task,
    frontier_semantic_review_view,
)


FRONTIER_TOKENIZER_PLACEBO_PACKET_SCHEMA_VERSION = (
    "adds.frontier-private-tokenizer-placebo-packet-set.v1"
)
FRONTIER_TOKENIZER_PLACEBO_KEY_SCHEMA_VERSION = (
    "adds.frontier-private-tokenizer-placebo-key-set.v1"
)
FRONTIER_TOKENIZER_PLACEBO_SUMMARY_SCHEMA_VERSION = (
    "adds.frontier-tokenizer-placebo-summary.v1"
)
FRONTIER_TOKENIZER_PLACEBO_SET_ID = "adds-frontier-tokenizer-placebo-v1"
FRONTIER_TOKENIZER_PLACEBO_DESIGN_RULE = (
    "blind_canonical_targeted_reveal_and_three_content_null_reveals_"
    "with_equal_structure_whitespace_and_cl100k_o200k_token_counts"
)
TIKTOKEN_PACKAGE_VERSION = "0.14.0"
TOKENIZER_ENCODING_NAMES = ("cl100k_base", "o200k_base")
EVALUATION_ONLY_ENCODING_NAMES = ("r50k_base", "p50k_base")
PROFILE_SEARCH_TRIALS_PER_PLACEBO = 512
_ARM_IDS = ("arm_a", "arm_b", "arm_c", "arm_d", "arm_e")
_ROLE_IDS = (
    "canonical",
    "candidate",
    "placebo_transport",
    "placebo_schema",
    "placebo_audit",
)
_PLACEBO_ROLE_IDS = _ROLE_IDS[2:]
_REVIEW_DIMENSIONS = (
    "disposition",
    "next_action",
    "risk_flags",
    "witness",
    "blockers",
)
_EXPECTED_ENCODING_PROFILES = (
    {
        "encoding_name": "cl100k_base",
        "source_asset_url": (
            "https://openaipublic.blob.core.windows.net/encodings/cl100k_base.tiktoken"
        ),
        "source_asset_sha256": (
            "223921b76ee99bde995b7ff738513eef100fb51d18c93597a113bcffe865b2a7"
        ),
        "n_vocab": 100277,
        "mergeable_rank_count": 100256,
        "special_token_count": 5,
        "vocabulary_sha256": (
            "c45339dd52b71083191b9547250f3447e45ed4d67d0560a28fe541700001acba"
        ),
    },
    {
        "encoding_name": "o200k_base",
        "source_asset_url": (
            "https://openaipublic.blob.core.windows.net/encodings/o200k_base.tiktoken"
        ),
        "source_asset_sha256": (
            "446a9538cb6c348e3516120d7c08b09f57c36495e2acfffe59a5bf8b0cfb1a2d"
        ),
        "n_vocab": 200019,
        "mergeable_rank_count": 199998,
        "special_token_count": 2,
        "vocabulary_sha256": (
            "9eff60a5f9a550b06572a296a42915e5c7b9c5393ad7e5584abb614d6d95d172"
        ),
    },
)
_EXPECTED_EVALUATION_ENCODING_PROFILES = (
    {
        "encoding_name": "r50k_base",
        "source_asset_url": (
            "https://openaipublic.blob.core.windows.net/encodings/r50k_base.tiktoken"
        ),
        "source_asset_sha256": (
            "306cd27f03c1a714eca7108e03d66b7dc042abe8c258b44c199a7ed9838dd930"
        ),
        "n_vocab": 50257,
        "mergeable_rank_count": 50256,
        "special_token_count": 1,
        "vocabulary_sha256": (
            "fc1756df0d0abea2568bfef979a26c563381b7144f6bac10aac4a20e8f29e674"
        ),
    },
    {
        "encoding_name": "p50k_base",
        "source_asset_url": (
            "https://openaipublic.blob.core.windows.net/encodings/p50k_base.tiktoken"
        ),
        "source_asset_sha256": (
            "94b5ca7dff4d00767bc256fdd1b27e5b17361d7b8a5f968547f9f23eb70d2069"
        ),
        "n_vocab": 50281,
        "mergeable_rank_count": 50280,
        "special_token_count": 1,
        "vocabulary_sha256": (
            "514697bc24623b6a2fdbba7f0ca3e170cf2530092ad251a0050b1333097ac765"
        ),
    },
)
_PLACEBO_FAMILIES = {
    "placebo_transport": {
        "anchor": "interoperability",
        "anchor_continuation_counts": (2, 1),
        "simple": (
            "packet",
            "transport",
            "format",
            "parser",
            "record",
            "control",
            "checksum",
            "schema",
            "header",
            "footer",
            "buffer",
            "stream",
            "queue",
            "cache",
            "mirror",
            "snapshot",
        ),
        "complex": (
            "record-layout",
            "parser-state",
            "buffer-index",
            "payload-format",
            "schema-version",
            "checksum-value",
            "transport-envelope",
            "archive-entry",
            "metadata-field",
            "serialization-rule",
            "delimiter-token",
            "encoding-table",
        ),
    },
    "placebo_schema": {
        "anchor": "portability",
        "anchor_continuation_counts": (2, 1),
        "simple": (
            "metadata",
            "payload",
            "validation",
            "serialization",
            "delimiter",
            "encoding",
            "version",
            "registry",
            "field",
            "table",
            "column",
            "row",
            "archive",
            "copy",
            "namespace",
            "protocol",
        ),
        "complex": (
            "namespace-prefix",
            "protocol-header",
            "container-footer",
            "queue-position",
            "cache-marker",
            "mirror-record",
            "snapshot-index",
            "registry-key",
            "version-tag",
            "packet-frame",
            "field-table",
            "row-index",
        ),
    },
    "placebo_audit": {
        "anchor": "reproducibility",
        "anchor_continuation_counts": (3, 2),
        "simple": (
            "audit",
            "log",
            "receipt",
            "trace",
            "state",
            "event",
            "ledger",
            "review",
            "result",
            "commit",
            "hash",
            "key",
            "bundle",
            "manifest",
            "archive",
            "record",
        ),
        "complex": (
            "replay-log",
            "receipt-index",
            "state-check",
            "event-stream",
            "ledger-entry",
            "review-record",
            "result-cache",
            "key-table",
            "bundle-format",
            "manifest-row",
            "trace-header",
            "audit-record",
        ),
    },
}
_PACKET_NONCLAIMS = {
    "Five-arm packet compilation is an experiment design, not a semantic label.",
    "Exact token-count matching does not match token identities or distributions.",
    "Neutral-vocabulary families do not prove scientific irrelevance.",
    "Profile optimization is deterministic lexical control, not semantic validation.",
    "Optimization is in-sample over fixed lexical candidates, not external validation.",
    "Lower proxy-histogram distance does not establish distributional equivalence.",
    "Arm roles and author expectations are absent from reviewer packets.",
    "Synthetic vocabulary may make placebo families inferable despite order blinding.",
    "No reviewer response, consensus label, oracle edit, admission, or model result is claimed.",
}
_PUBLIC_NONCLAIMS = {
    "Ten five-arm packets are machine-compiled experiment drafts, not independently reviewed labels.",
    "Exact cl100k_base and o200k_base token counts do not match token identities or distributions.",
    "Search and acceptance use only the two frozen design encodings; evaluation-only diagnostics do not make the optimizer tokenizer-general.",
    "Deterministic profile search does not establish syntax, readability, or lexical familiarity equivalence.",
    "Distribution optimization is in-sample over fixed lexical candidates, not external validation.",
    "Lower proxy-histogram distance does not establish token-distribution equivalence.",
    "The r50k_base and p50k_base post-selection audit is not preregistered, held-out model evaluation, or external validation.",
    "The two evaluation encodings share a 50k tokenizer family and do not establish broad tokenizer independence.",
    "Aggregate evaluation-only improvement coexists with four regressing placebos, so robust generalization remains false.",
    "Three neutral-vocabulary families do not establish scientific irrelevance or placebo invariance.",
    "Author-expected candidate changes and placebo intent are sealed selection metadata, not observations.",
    "No arm role, task, oracle, evidence text, identity, nonce, or reviewer payload is public.",
    "No reviewer was assigned and no coupling, invariance, contrast, consensus, or adjudication label exists.",
    "No oracle revision, challenge assignment, board admission, model run, or benchmark result is authorized.",
}


def frontier_tokenizer_placebo_packet_set_integrity_sha256(
    packet_set: Mapping[str, Any],
) -> str:
    return _canonical_sha256(packet_set, exclude=frozenset({"integrity_sha256"}))


def frontier_tokenizer_placebo_key_set_integrity_sha256(
    key_set: Mapping[str, Any],
) -> str:
    return _canonical_sha256(key_set, exclude=frozenset({"integrity_sha256"}))


def frontier_tokenizer_placebo_summary_integrity_sha256(
    summary: Mapping[str, Any],
) -> str:
    return _canonical_sha256(summary, exclude=frozenset({"integrity_sha256"}))


def _encoding_vocabulary_sha256(encoding: Encoding) -> str:
    digest = hashlib.sha256()
    for token, rank in sorted(
        encoding._mergeable_ranks.items(), key=lambda item: (item[1], item[0])
    ):
        digest.update(len(token).to_bytes(4, "big"))
        digest.update(token)
        digest.update(rank.to_bytes(8, "big"))
    for token, rank in sorted(encoding._special_tokens.items()):
        encoded = token.encode("utf-8")
        digest.update(len(encoded).to_bytes(4, "big"))
        digest.update(encoded)
        digest.update(rank.to_bytes(8, "big"))
    pattern = encoding._pat_str.encode("utf-8")
    digest.update(len(pattern).to_bytes(4, "big"))
    digest.update(pattern)
    return digest.hexdigest()


def _load_expected_encodings(
    expected_profiles: Sequence[Mapping[str, Any]],
) -> dict[str, Encoding]:
    package_version = importlib.metadata.version("tiktoken")
    if package_version != TIKTOKEN_PACKAGE_VERSION:
        raise FrontierContractError("tokenizer placebo requires frozen tiktoken 0.14.0")
    encodings = {
        str(profile["encoding_name"]): tiktoken.get_encoding(
            str(profile["encoding_name"])
        )
        for profile in expected_profiles
    }
    actual_profiles = tuple(
        {
            **{
                key: value
                for key, value in expected.items()
                if key in {"encoding_name", "source_asset_url", "source_asset_sha256"}
            },
            "n_vocab": encoding.n_vocab,
            "mergeable_rank_count": len(encoding._mergeable_ranks),
            "special_token_count": len(encoding._special_tokens),
            "vocabulary_sha256": _encoding_vocabulary_sha256(encoding),
        }
        for encoding, expected in zip(
            encodings.values(), expected_profiles, strict=True
        )
    )
    if actual_profiles != tuple(expected_profiles):
        raise FrontierContractError("tokenizer vocabulary fingerprint mismatch")
    return encodings


def _load_frozen_encodings() -> dict[str, Encoding]:
    return _load_expected_encodings(_EXPECTED_ENCODING_PROFILES)


def _load_evaluation_only_encodings() -> dict[str, Encoding]:
    return _load_expected_encodings(_EXPECTED_EVALUATION_ENCODING_PROFILES)


def _token_profile(text: str, encoding: Encoding) -> dict[str, Any]:
    token_ids = encoding.encode(text, disallowed_special=())
    byte_histogram = [0] * 8
    rank_histogram = [0] * 10
    for token_id in token_ids:
        byte_length = len(encoding.decode_single_token_bytes(token_id))
        byte_histogram[min(byte_length, 8) - 1] += 1
        rank_histogram[min(token_id * 10 // encoding.n_vocab, 9)] += 1
    return {
        "token_count": len(token_ids),
        "token_byte_length_histogram": byte_histogram,
        "token_rank_decile_histogram": rank_histogram,
    }


def _profiles(text: str, encodings: Mapping[str, Encoding]) -> dict[str, Any]:
    return {
        name: _token_profile(text, encoding) for name, encoding in encodings.items()
    }


def _profile_l1_distance(
    candidate_profiles: Mapping[str, Any], placebo_profiles: Mapping[str, Any]
) -> int:
    return sum(
        record["combined_l1_distance"]
        for record in _profile_component_distances(
            candidate_profiles, placebo_profiles
        ).values()
    )


def _profile_component_distances(
    candidate_profiles: Mapping[str, Any],
    placebo_profiles: Mapping[str, Any],
    *,
    encoding_names: Sequence[str] = TOKENIZER_ENCODING_NAMES,
) -> dict[str, dict[str, int]]:
    distances: dict[str, dict[str, int]] = {}
    for encoding_name in encoding_names:
        candidate = candidate_profiles[encoding_name]
        placebo = placebo_profiles[encoding_name]
        byte_distance = sum(
            abs(left - right)
            for left, right in zip(
                candidate["token_byte_length_histogram"],
                placebo["token_byte_length_histogram"],
                strict=True,
            )
        )
        rank_distance = sum(
            abs(left - right)
            for left, right in zip(
                candidate["token_rank_decile_histogram"],
                placebo["token_rank_decile_histogram"],
                strict=True,
            )
        )
        distances[encoding_name] = {
            "token_byte_length_l1_distance": byte_distance,
            "token_rank_decile_l1_distance": rank_distance,
            "combined_l1_distance": byte_distance + rank_distance,
        }
    return distances


def _ranked_terms(terms: Sequence[str], *, seed: str) -> list[str]:
    return sorted(
        terms,
        key=lambda term: (
            hashlib.sha256(f"{seed}|{term}".encode("utf-8")).hexdigest(),
            term,
        ),
    )


def _placebo_trial_summary(
    *,
    slot_id: str,
    family_id: str,
    family: Mapping[str, Any],
    simple_count: int,
    complex_count: int,
    trial: int,
) -> str:
    seed = f"{slot_id}|{family_id}|{trial}"
    simple_terms = _ranked_terms(family["simple"], seed=f"{seed}|simple")[:simple_count]
    complex_terms = _ranked_terms(family["complex"], seed=f"{seed}|complex")[
        :complex_count
    ]
    first = simple_terms[0]
    remaining = _ranked_terms(
        [*simple_terms[1:], *complex_terms, family["anchor"]],
        seed=f"{seed}|order",
    )
    return " ".join([first, *remaining]) + "."


def _heldout_generalization_record(
    *,
    candidate_summary: str,
    trial_zero_summary: str,
    optimized_summary: str,
    encodings: Mapping[str, Encoding],
) -> dict[str, Any]:
    candidate_profiles = _profiles(candidate_summary, encodings)
    baseline_profiles = _profiles(trial_zero_summary, encodings)
    optimized_profiles = _profiles(optimized_summary, encodings)
    baseline_components = _profile_component_distances(
        candidate_profiles,
        baseline_profiles,
        encoding_names=EVALUATION_ONLY_ENCODING_NAMES,
    )
    optimized_components = _profile_component_distances(
        candidate_profiles,
        optimized_profiles,
        encoding_names=EVALUATION_ONLY_ENCODING_NAMES,
    )
    baseline_gaps = {
        name: abs(
            candidate_profiles[name]["token_count"]
            - baseline_profiles[name]["token_count"]
        )
        for name in EVALUATION_ONLY_ENCODING_NAMES
    }
    optimized_gaps = {
        name: abs(
            candidate_profiles[name]["token_count"]
            - optimized_profiles[name]["token_count"]
        )
        for name in EVALUATION_ONLY_ENCODING_NAMES
    }
    profile_comparisons = [
        (
            baseline_components[name]["combined_l1_distance"],
            optimized_components[name]["combined_l1_distance"],
        )
        for name in EVALUATION_ONLY_ENCODING_NAMES
    ]
    component_comparisons = [
        (
            baseline_components[name][field],
            optimized_components[name][field],
        )
        for name in EVALUATION_ONLY_ENCODING_NAMES
        for field in (
            "token_byte_length_l1_distance",
            "token_rank_decile_l1_distance",
        )
    ]
    gap_comparisons = [
        (baseline_gaps[name], optimized_gaps[name])
        for name in EVALUATION_ONLY_ENCODING_NAMES
    ]
    baseline_distance = sum(left for left, _ in profile_comparisons)
    optimized_distance = sum(right for _, right in profile_comparisons)
    profile_nonregression_count = sum(
        optimized <= baseline for baseline, optimized in profile_comparisons
    )
    profile_strict_improvement_count = sum(
        optimized < baseline for baseline, optimized in profile_comparisons
    )
    return {
        "heldout_trial_zero_summary_commitment": hashlib.sha256(
            trial_zero_summary.encode("utf-8")
        ).hexdigest(),
        "heldout_token_count_absolute_gaps": {
            "baseline": baseline_gaps,
            "optimized": optimized_gaps,
        },
        "heldout_exact_token_count_match_count_baseline": sum(
            gap == 0 for gap in baseline_gaps.values()
        ),
        "heldout_exact_token_count_match_count_optimized": sum(
            gap == 0 for gap in optimized_gaps.values()
        ),
        "heldout_token_byte_length_histogram_match_count_baseline": sum(
            candidate_profiles[name]["token_byte_length_histogram"]
            == baseline_profiles[name]["token_byte_length_histogram"]
            for name in EVALUATION_ONLY_ENCODING_NAMES
        ),
        "heldout_token_byte_length_histogram_match_count_optimized": sum(
            candidate_profiles[name]["token_byte_length_histogram"]
            == optimized_profiles[name]["token_byte_length_histogram"]
            for name in EVALUATION_ONLY_ENCODING_NAMES
        ),
        "heldout_token_rank_decile_histogram_match_count_baseline": sum(
            candidate_profiles[name]["token_rank_decile_histogram"]
            == baseline_profiles[name]["token_rank_decile_histogram"]
            for name in EVALUATION_ONLY_ENCODING_NAMES
        ),
        "heldout_token_rank_decile_histogram_match_count_optimized": sum(
            candidate_profiles[name]["token_rank_decile_histogram"]
            == optimized_profiles[name]["token_rank_decile_histogram"]
            for name in EVALUATION_ONLY_ENCODING_NAMES
        ),
        "heldout_profile_l1_distance_baseline": baseline_distance,
        "heldout_profile_l1_distance_optimized": optimized_distance,
        "heldout_profile_l1_distance_reduction": (
            baseline_distance - optimized_distance
        ),
        "heldout_profile_component_distances": {
            "baseline": baseline_components,
            "optimized": optimized_components,
        },
        "heldout_profile_encoding_comparison_count": len(profile_comparisons),
        "heldout_profile_encoding_nonregression_count": (profile_nonregression_count),
        "heldout_profile_encoding_strict_improvement_count": (
            profile_strict_improvement_count
        ),
        "heldout_profile_component_comparison_count": len(component_comparisons),
        "heldout_profile_component_nonregression_count": sum(
            optimized <= baseline for baseline, optimized in component_comparisons
        ),
        "heldout_profile_component_strict_improvement_count": sum(
            optimized < baseline for baseline, optimized in component_comparisons
        ),
        "heldout_token_count_gap_comparison_count": len(gap_comparisons),
        "heldout_token_count_gap_nonregression_count": sum(
            optimized <= baseline for baseline, optimized in gap_comparisons
        ),
        "heldout_token_count_gap_strict_improvement_count": sum(
            optimized < baseline for baseline, optimized in gap_comparisons
        ),
        "heldout_all_profile_nonregression_passed": (
            profile_nonregression_count == len(profile_comparisons)
        ),
        "heldout_all_profile_strict_improvement_passed": (
            profile_strict_improvement_count == len(profile_comparisons)
        ),
    }


def _validate_family_lexicons(encodings: Mapping[str, Encoding]) -> None:
    for family_id, family in _PLACEBO_FAMILIES.items():
        for term in family["simple"]:
            counts = tuple(
                len(encoding.encode(prefix + term, disallowed_special=()))
                for encoding in encodings.values()
                for prefix in ("", " ")
            )
            if counts != (1, 1, 1, 1):
                raise FrontierContractError(
                    f"tokenizer placebo simple lexicon drifted for {family_id}"
                )
        for term in family["complex"]:
            counts = tuple(
                len(encoding.encode(" " + term, disallowed_special=()))
                for encoding in encodings.values()
            )
            if counts != (2, 2):
                raise FrontierContractError(
                    f"tokenizer placebo complex lexicon drifted for {family_id}"
                )
        anchor_counts = tuple(
            len(encoding.encode(" " + family["anchor"], disallowed_special=()))
            for encoding in encodings.values()
        )
        if anchor_counts != family["anchor_continuation_counts"]:
            raise FrontierContractError(
                f"tokenizer placebo anchor lexicon drifted for {family_id}"
            )


def _tokenizer_placebo_search_context(
    *,
    candidate_summary: str,
    slot_id: str,
    family_id: str,
    encodings: Mapping[str, Encoding],
) -> tuple[Mapping[str, Any], int, int]:
    family = _PLACEBO_FAMILIES[family_id]
    candidate_profiles = _profiles(candidate_summary, encodings)
    whitespace_count = len(candidate_summary.split())
    cl_count = candidate_profiles["cl100k_base"]["token_count"]
    o_count = candidate_profiles["o200k_base"]["token_count"]
    anchor_cl, anchor_o = family["anchor_continuation_counts"]
    if cl_count - o_count != anchor_cl - anchor_o:
        raise FrontierContractError(
            f"tokenizer placebo candidate profile is infeasible for {slot_id}"
        )
    complex_count = o_count - whitespace_count - 1 - (anchor_o - 1)
    simple_count = whitespace_count - complex_count - 1
    if not (
        1 <= simple_count <= len(family["simple"])
        and 0 <= complex_count <= len(family["complex"])
    ):
        raise FrontierContractError(
            f"tokenizer placebo lexical budget is infeasible for {slot_id}"
        )
    return family, simple_count, complex_count


def _tokenizer_placebo_trial_zero_summary(
    *,
    candidate_summary: str,
    slot_id: str,
    family_id: str,
    encodings: Mapping[str, Encoding],
) -> str:
    family, simple_count, complex_count = _tokenizer_placebo_search_context(
        candidate_summary=candidate_summary,
        slot_id=slot_id,
        family_id=family_id,
        encodings=encodings,
    )
    return _placebo_trial_summary(
        slot_id=slot_id,
        family_id=family_id,
        family=family,
        simple_count=simple_count,
        complex_count=complex_count,
        trial=0,
    )


def _tokenizer_matched_summary(
    *,
    candidate_summary: str,
    slot_id: str,
    family_id: str,
    encodings: Mapping[str, Encoding],
) -> tuple[str, str, dict[str, Any]]:
    family, simple_count, complex_count = _tokenizer_placebo_search_context(
        candidate_summary=candidate_summary,
        slot_id=slot_id,
        family_id=family_id,
        encodings=encodings,
    )
    candidate_profiles = _profiles(candidate_summary, encodings)
    whitespace_count = len(candidate_summary.split())

    baseline: tuple[int, str, dict[str, Any], dict[str, dict[str, int]]] | None = None
    best: tuple[int, str, dict[str, Any], dict[str, dict[str, int]]] | None = None
    for trial in range(PROFILE_SEARCH_TRIALS_PER_PLACEBO):
        summary = _placebo_trial_summary(
            slot_id=slot_id,
            family_id=family_id,
            family=family,
            simple_count=simple_count,
            complex_count=complex_count,
            trial=trial,
        )
        placebo_profiles = _profiles(summary, encodings)
        if any(
            placebo_profiles[name]["token_count"]
            != candidate_profiles[name]["token_count"]
            for name in TOKENIZER_ENCODING_NAMES
        ):
            continue
        distance = _profile_l1_distance(candidate_profiles, placebo_profiles)
        component_distances = _profile_component_distances(
            candidate_profiles, placebo_profiles
        )
        proposal = (distance, summary, placebo_profiles, component_distances)
        if trial == 0:
            baseline = proposal
        if baseline is None:
            continue
        baseline_components = baseline[3]
        if any(
            component_distances[encoding_name][field_name]
            > baseline_components[encoding_name][field_name]
            for encoding_name in TOKENIZER_ENCODING_NAMES
            for field_name in (
                "token_byte_length_l1_distance",
                "token_rank_decile_l1_distance",
            )
        ):
            continue
        if best is None or proposal[:2] < best[:2]:
            best = proposal
    if baseline is None or best is None:
        raise FrontierContractError(
            f"tokenizer placebo search produced no exact match for {slot_id}"
        )

    baseline_distance, _, _, baseline_components = baseline
    distance, summary, placebo_profiles, optimized_components = best
    component_comparisons = [
        (
            baseline_components[encoding_name][field_name],
            optimized_components[encoding_name][field_name],
        )
        for encoding_name in TOKENIZER_ENCODING_NAMES
        for field_name in (
            "token_byte_length_l1_distance",
            "token_rank_decile_l1_distance",
        )
    ]
    component_nonregression_count = sum(
        optimized <= baseline_value
        for baseline_value, optimized in component_comparisons
    )
    component_strict_improvement_count = sum(
        optimized < baseline_value
        for baseline_value, optimized in component_comparisons
    )
    encoding_nonregression_count = sum(
        optimized_components[name]["combined_l1_distance"]
        <= baseline_components[name]["combined_l1_distance"]
        for name in TOKENIZER_ENCODING_NAMES
    )
    strict_improvement = distance < baseline_distance
    optimization_accepted = (
        component_nonregression_count == len(component_comparisons)
        and encoding_nonregression_count == len(TOKENIZER_ENCODING_NAMES)
        and strict_improvement
    )
    vocabulary = {
        *family["simple"],
        *family["complex"],
        family["anchor"],
    }
    vocabulary_passed = {token.rstrip(".") for token in summary.split()}.issubset(
        vocabulary
    )
    byte_match_count = sum(
        candidate_profiles[name]["token_byte_length_histogram"]
        == placebo_profiles[name]["token_byte_length_histogram"]
        for name in TOKENIZER_ENCODING_NAMES
    )
    rank_match_count = sum(
        candidate_profiles[name]["token_rank_decile_histogram"]
        == placebo_profiles[name]["token_rank_decile_histogram"]
        for name in TOKENIZER_ENCODING_NAMES
    )
    match_record = {
        "family_id": family_id,
        "whitespace_token_count_matched": (len(summary.split()) == whitespace_count),
        "candidate_token_counts": {
            name: candidate_profiles[name]["token_count"]
            for name in TOKENIZER_ENCODING_NAMES
        },
        "placebo_token_counts": {
            name: placebo_profiles[name]["token_count"]
            for name in TOKENIZER_ENCODING_NAMES
        },
        "exact_token_count_match_count": sum(
            candidate_profiles[name]["token_count"]
            == placebo_profiles[name]["token_count"]
            for name in TOKENIZER_ENCODING_NAMES
        ),
        "token_byte_length_histogram_match_count": byte_match_count,
        "token_rank_decile_histogram_match_count": rank_match_count,
        "baseline_profile_l1_distance": baseline_distance,
        "optimized_profile_l1_distance": distance,
        "profile_l1_distance_reduction": baseline_distance - distance,
        "profile_component_distances": {
            "baseline": baseline_components,
            "optimized": optimized_components,
        },
        "profile_component_comparison_count": len(component_comparisons),
        "profile_component_nonregression_count": component_nonregression_count,
        "profile_component_strict_improvement_count": (
            component_strict_improvement_count
        ),
        "profile_encoding_comparison_count": len(TOKENIZER_ENCODING_NAMES),
        "profile_encoding_nonregression_count": encoding_nonregression_count,
        "strict_profile_improvement_passed": strict_improvement,
        "distribution_optimization_acceptance_passed": optimization_accepted,
        "profile_search_trials": PROFILE_SEARCH_TRIALS_PER_PLACEBO,
        "vocabulary_family_policy_passed": vocabulary_passed,
    }
    if not (
        match_record["whitespace_token_count_matched"]
        and match_record["exact_token_count_match_count"]
        == len(TOKENIZER_ENCODING_NAMES)
        and vocabulary_passed
        and optimization_accepted
    ):
        raise FrontierContractError(
            f"tokenizer placebo matching failed for {slot_id} {family_id}"
        )
    return summary, baseline[1], match_record


def _materialize_tokenizer_placebo(
    task: Mapping[str, Any], *, summary: str, family_id: str
) -> dict[str, Any]:
    mutated = copy.deepcopy(task)
    token = hashlib.sha256(
        f"{task['slot_id']}|tokenizer-placebo|{family_id}".encode("utf-8")
    ).hexdigest()[:16]
    evidence_id = f"ev-tokenizer-placebo-{token}"
    mutated["evidence_nodes"].append(
        {
            "evidence_id": evidence_id,
            "available_on": mutated["stages"][3]["as_of_date"],
            "lineage_id": f"lineage-tokenizer-placebo-{token}",
            "evidence_role": "source",
            "evidence_summary": summary,
        }
    )
    for stage in mutated["stages"][3:]:
        stage["accessible_evidence_ids"].append(evidence_id)
    return mutated


def _arm_mapping(*, task_index: int) -> dict[str, str]:
    shift = task_index % len(_ARM_IDS)
    return {
        role: _ARM_IDS[(role_index + shift) % len(_ARM_IDS)]
        for role_index, role in enumerate(_ROLE_IDS)
    }


def compile_frontier_tokenizer_placebo_artifacts(
    *,
    private_coupled_placebo_packets: Mapping[str, Any],
    private_coupled_placebo_keys: Mapping[str, Any],
    public_coupled_placebo_summary: Mapping[str, Any],
    private_coupled_packet_set: Mapping[str, Any],
    public_coupled_summary: Mapping[str, Any],
    task_set: Mapping[str, Any],
    oracle_set: Mapping[str, Any],
    private_preflight: Mapping[str, Any],
    public_preflight: Mapping[str, Any],
    private_semantic_packets: Mapping[str, Any],
    private_semantic_keys: Mapping[str, Any],
    public_semantic_summary: Mapping[str, Any],
    private_transition_report: Mapping[str, Any],
    public_transition_summary: Mapping[str, Any],
    private_fragility_report: Mapping[str, Any],
    public_fragility_summary: Mapping[str, Any],
    private_support_curation_packets: Mapping[str, Any],
    public_support_curation_summary: Mapping[str, Any],
    progress: Mapping[str, Any],
    root: Path,
    frontier_protocol: Mapping[str, Any],
    board_protocol: Mapping[str, Any],
    board_slots: Mapping[str, Any],
    compiled_on: str,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Compile five-arm packets with three tokenizer-count-matched placebos."""

    validation_kwargs = {
        "root": root,
        "frontier_protocol": frontier_protocol,
        "board_protocol": board_protocol,
        "board_slots": board_slots,
    }
    tasks_data = validate_frontier_calibration_task_set(task_set, **validation_kwargs)
    oracles_data = validate_frontier_calibration_oracle_set(
        oracle_set, task_set=tasks_data, **validation_kwargs
    )
    progress_data = validate_frontier_calibration_progress(
        progress, **validation_kwargs
    )
    source_summary = validate_frontier_coupled_placebo_summary(
        public_coupled_placebo_summary,
        public_coupled_summary=public_coupled_summary,
        public_semantic_summary=public_semantic_summary,
        public_transition_summary=public_transition_summary,
        public_support_curation_summary=public_support_curation_summary,
        public_fragility_summary=public_fragility_summary,
        public_preflight=public_preflight,
        progress=progress_data,
        **validation_kwargs,
    )
    validate_frontier_coupled_placebo_private_opening(
        private_packet_set=private_coupled_placebo_packets,
        private_key_set=private_coupled_placebo_keys,
        public_summary=source_summary,
        private_coupled_packet_set=private_coupled_packet_set,
        public_coupled_summary=public_coupled_summary,
        task_set=tasks_data,
        oracle_set=oracles_data,
        private_preflight=private_preflight,
        public_preflight=public_preflight,
        private_semantic_packets=private_semantic_packets,
        private_semantic_keys=private_semantic_keys,
        public_semantic_summary=public_semantic_summary,
        private_transition_report=private_transition_report,
        public_transition_summary=public_transition_summary,
        private_fragility_report=private_fragility_report,
        public_fragility_summary=public_fragility_summary,
        private_support_curation_packets=private_support_curation_packets,
        public_support_curation_summary=public_support_curation_summary,
        progress=progress_data,
        **validation_kwargs,
    )
    _date(compiled_on, "tokenizer placebo compiled_on")
    encodings = _load_frozen_encodings()
    _validate_family_lexicons(encodings)
    evaluation_encodings = _load_evaluation_only_encodings()

    source_packets = {
        packet["packet_id"]: packet
        for packet in private_coupled_placebo_packets["packets"]
    }
    source_keys = {key["slot_id"]: key for key in private_coupled_placebo_keys["keys"]}
    packets: list[dict[str, Any]] = []
    keys: list[dict[str, Any]] = []
    for task_index, (task, oracle) in enumerate(
        zip(tasks_data["tasks"], oracles_data["oracles"], strict=True)
    ):
        slot_id = task["slot_id"]
        source_key = source_keys.get(slot_id)
        if source_key is None:
            raise FrontierContractError(
                f"tokenizer placebo source key missing for {slot_id}"
            )
        source_packet = source_packets.get(source_key["packet_id"])
        if source_packet is None:
            raise FrontierContractError(
                f"tokenizer placebo source packet missing for {slot_id}"
            )
        canonical_view = source_packet[source_key["canonical_arm"]]
        candidate_view = source_packet[source_key["candidate_arm"]]
        candidate_node = _added_node(canonical_view, candidate_view)
        candidate_certificate = source_key["candidate_structural_delta_certificate"]
        candidate_fingerprint = _structural_fingerprint(canonical_view, candidate_view)
        placebo_views: dict[str, dict[str, Any]] = {}
        placebo_records: list[dict[str, Any]] = []
        profile_bundle: dict[str, Any] = {
            "tokenizer_profiles": list(_EXPECTED_ENCODING_PROFILES),
            "evaluation_only_tokenizer_profiles": list(
                _EXPECTED_EVALUATION_ENCODING_PROFILES
            ),
            "placebos": [],
        }
        for family_id in _PLACEBO_ROLE_IDS:
            summary, trial_zero_summary, lexical_record = _tokenizer_matched_summary(
                candidate_summary=candidate_node["evidence_summary"],
                slot_id=slot_id,
                family_id=family_id,
                encodings=encodings,
            )
            heldout_record = _heldout_generalization_record(
                candidate_summary=candidate_node["evidence_summary"],
                trial_zero_summary=trial_zero_summary,
                optimized_summary=summary,
                encodings=evaluation_encodings,
            )
            placebo_task = _materialize_tokenizer_placebo(
                task, summary=summary, family_id=family_id
            )
            _validate_materialized_task(
                task_set=tasks_data,
                oracle_set=oracles_data,
                task_index=task_index,
                mutated_task=placebo_task,
                validation_kwargs=validation_kwargs,
            )
            placebo_view = frontier_semantic_review_view(placebo_task)
            placebo_certificate = _delta_certificate(
                task, placebo_task, probe_kind="bounded_evidence_reveal"
            )
            placebo_fingerprint = _structural_fingerprint(canonical_view, placebo_view)
            structural_match = (
                candidate_certificate == placebo_certificate
                and candidate_fingerprint == placebo_fingerprint
            )
            if not (
                candidate_certificate["exact_delta_passed"]
                and placebo_certificate["exact_delta_passed"]
                and structural_match
            ):
                raise FrontierContractError(
                    f"tokenizer placebo structure failed for {slot_id} {family_id}"
                )
            placebo_views[family_id] = placebo_view
            record = {
                "family_id": family_id,
                "placebo_task_commitment": frontier_calibration_task_sha256(
                    placebo_task
                ),
                "placebo_intended_changed_components": [],
                "placebo_structural_delta_certificate": placebo_certificate,
                "placebo_structural_fingerprint": placebo_fingerprint,
                "candidate_placebo_structural_match_passed": structural_match,
                **lexical_record,
                **heldout_record,
                "tokenizer_count_match_established": True,
                "tokenizer_distribution_match_established": (
                    lexical_record["token_byte_length_histogram_match_count"]
                    == len(TOKENIZER_ENCODING_NAMES)
                    and lexical_record["token_rank_decile_histogram_match_count"]
                    == len(TOKENIZER_ENCODING_NAMES)
                ),
                "placebo_scientific_invariance_established": False,
            }
            placebo_records.append(record)
            profile_bundle["placebos"].append(
                {
                    key: value
                    for key, value in (lexical_record | heldout_record).items()
                    if key != "candidate_token_counts"
                }
            )

        mapping = _arm_mapping(task_index=task_index)
        role_payloads = {
            "canonical": canonical_view,
            "candidate": candidate_view,
            **placebo_views,
        }
        arm_payloads = {mapping[role]: role_payloads[role] for role in _ROLE_IDS}
        blind_digest = hashlib.sha256(
            (
                f"{oracle['oracle_commitment_nonce']}|{slot_id}|"
                "tokenizer-placebo-five-arm"
            ).encode("utf-8")
        ).hexdigest()
        packet_id = f"tokenizer-placebo-{blind_digest[:20]}"
        packet = {
            "packet_id": packet_id,
            "review_dimensions": list(_REVIEW_DIMENSIONS),
            **{arm_id: arm_payloads[arm_id] for arm_id in _ARM_IDS},
            **{
                f"{arm_id}_commitment": _canonical_sha256(arm_payloads[arm_id])
                for arm_id in _ARM_IDS
            },
            "matched_tokenizer_profile_commitment": _canonical_sha256(profile_bundle),
        }
        packets.append(packet)
        keys.append(
            {
                "packet_id": packet_id,
                "slot_id": slot_id,
                "source_coupled_placebo_packet_id": source_packet["packet_id"],
                **{f"{role}_arm": mapping[role] for role in _ROLE_IDS},
                "canonical_task_commitment": frontier_calibration_task_sha256(task),
                "candidate_task_commitment": source_key["candidate_task_commitment"],
                "candidate_expected_changed_components": list(
                    source_key["candidate_expected_changed_components"]
                ),
                "candidate_structural_delta_certificate": candidate_certificate,
                "candidate_structural_fingerprint": candidate_fingerprint,
                "placebos": placebo_records,
                "candidate_scientific_coupling_established": False,
                "contrast_identifiability_established": False,
            }
        )

    packets.sort(key=lambda packet: packet["packet_id"])
    keys.sort(key=lambda key: key["packet_id"])
    arm_role_counts = {
        role: dict(Counter(key[f"{role}_arm"] for key in keys)) for role in _ROLE_IDS
    }
    for counts in arm_role_counts.values():
        for arm_id in _ARM_IDS:
            counts.setdefault(arm_id, 0)
    max_imbalance = max(
        max(counts.values()) - min(counts.values())
        for counts in arm_role_counts.values()
    )
    all_placebo_records = [placebo for key in keys for placebo in key["placebos"]]
    packet_set: dict[str, Any] = {
        "schema_version": FRONTIER_TOKENIZER_PLACEBO_PACKET_SCHEMA_VERSION,
        "set_id": FRONTIER_TOKENIZER_PLACEBO_SET_ID,
        "protocol_id": tasks_data["protocol_id"],
        "board_id": tasks_data["board_id"],
        "compiled_on": compiled_on,
        "private_coupled_placebo_packet_set_integrity_sha256": (
            private_coupled_placebo_packets["integrity_sha256"]
        ),
        "arm_role_mapping_included": False,
        "author_expectations_included": False,
        "minimum_independent_curators_per_packet": 3,
        "review_instructions": [
            "Solve all five arms independently before comparing them.",
            "Return all six stage actions, witnesses, and blockers for every arm.",
            "One arm is canonical and four add one synthetic source from stage 4 onward.",
            "Do not infer scientific relevance from token counts, vocabulary, source presence, or arm order.",
            "Assess candidate/placebo contrasts only after completing independent arm solves.",
        ],
        "packets": packets,
        "nonclaims": sorted(_PACKET_NONCLAIMS),
        "integrity_sha256": "0" * 64,
    }
    packet_set["integrity_sha256"] = (
        frontier_tokenizer_placebo_packet_set_integrity_sha256(packet_set)
    )
    key_set: dict[str, Any] = {
        "schema_version": FRONTIER_TOKENIZER_PLACEBO_KEY_SCHEMA_VERSION,
        "set_id": FRONTIER_TOKENIZER_PLACEBO_SET_ID,
        "protocol_id": tasks_data["protocol_id"],
        "board_id": tasks_data["board_id"],
        "compiled_on": compiled_on,
        "packet_set_integrity_sha256": packet_set["integrity_sha256"],
        "tokenizer_package": "tiktoken",
        "tokenizer_package_version": TIKTOKEN_PACKAGE_VERSION,
        "tokenizer_profiles": list(_EXPECTED_ENCODING_PROFILES),
        "evaluation_only_tokenizer_profiles": list(
            _EXPECTED_EVALUATION_ENCODING_PROFILES
        ),
        "keys": keys,
        "arm_role_counts": arm_role_counts,
        "arm_role_balance_max_imbalance": max_imbalance,
        "reviewer_assignment_count": 0,
        "reviewer_response_count": 0,
        "candidate_coupling_label_count": 0,
        "placebo_invariance_label_count": 0,
        "contrast_label_count": 0,
        "consensus_label_count": 0,
        "independent_review_complete": False,
        "integrity_sha256": "0" * 64,
    }
    key_set["integrity_sha256"] = frontier_tokenizer_placebo_key_set_integrity_sha256(
        key_set
    )
    tokenizer_comparison_count = len(all_placebo_records) * len(
        TOKENIZER_ENCODING_NAMES
    )
    byte_match_count = sum(
        record["token_byte_length_histogram_match_count"]
        for record in all_placebo_records
    )
    rank_match_count = sum(
        record["token_rank_decile_histogram_match_count"]
        for record in all_placebo_records
    )
    baseline_profile_distance_total = sum(
        record["baseline_profile_l1_distance"] for record in all_placebo_records
    )
    optimized_profile_distance_total = sum(
        record["optimized_profile_l1_distance"] for record in all_placebo_records
    )
    component_comparison_count = sum(
        record["profile_component_comparison_count"] for record in all_placebo_records
    )
    component_nonregression_count = sum(
        record["profile_component_nonregression_count"]
        for record in all_placebo_records
    )
    component_strict_improvement_count = sum(
        record["profile_component_strict_improvement_count"]
        for record in all_placebo_records
    )
    encoding_comparison_count = sum(
        record["profile_encoding_comparison_count"] for record in all_placebo_records
    )
    encoding_nonregression_count = sum(
        record["profile_encoding_nonregression_count"] for record in all_placebo_records
    )
    optimization_acceptance_count = sum(
        record["distribution_optimization_acceptance_passed"]
        for record in all_placebo_records
    )
    heldout_tokenizer_comparison_count = len(all_placebo_records) * len(
        EVALUATION_ONLY_ENCODING_NAMES
    )
    heldout_profile_distance_baseline = sum(
        record["heldout_profile_l1_distance_baseline"] for record in all_placebo_records
    )
    heldout_profile_distance_optimized = sum(
        record["heldout_profile_l1_distance_optimized"]
        for record in all_placebo_records
    )
    heldout_profile_nonregression_count = sum(
        record["heldout_profile_encoding_nonregression_count"]
        for record in all_placebo_records
    )
    heldout_profile_strict_improvement_count = sum(
        record["heldout_profile_encoding_strict_improvement_count"]
        for record in all_placebo_records
    )
    heldout_component_comparison_count = sum(
        record["heldout_profile_component_comparison_count"]
        for record in all_placebo_records
    )
    heldout_component_nonregression_count = sum(
        record["heldout_profile_component_nonregression_count"]
        for record in all_placebo_records
    )
    heldout_component_strict_improvement_count = sum(
        record["heldout_profile_component_strict_improvement_count"]
        for record in all_placebo_records
    )
    heldout_count_gap_baseline_total = sum(
        sum(record["heldout_token_count_absolute_gaps"]["baseline"].values())
        for record in all_placebo_records
    )
    heldout_count_gap_optimized_total = sum(
        sum(record["heldout_token_count_absolute_gaps"]["optimized"].values())
        for record in all_placebo_records
    )
    heldout_count_gap_nonregression_count = sum(
        record["heldout_token_count_gap_nonregression_count"]
        for record in all_placebo_records
    )
    heldout_count_gap_strict_improvement_count = sum(
        record["heldout_token_count_gap_strict_improvement_count"]
        for record in all_placebo_records
    )
    heldout_tokenizer_results = [
        {
            "encoding_name": encoding_name,
            "comparison_count": len(all_placebo_records),
            "baseline_profile_l1_distance_total": sum(
                record["heldout_profile_component_distances"]["baseline"][
                    encoding_name
                ]["combined_l1_distance"]
                for record in all_placebo_records
            ),
            "optimized_profile_l1_distance_total": sum(
                record["heldout_profile_component_distances"]["optimized"][
                    encoding_name
                ]["combined_l1_distance"]
                for record in all_placebo_records
            ),
        }
        for encoding_name in EVALUATION_ONLY_ENCODING_NAMES
    ]
    for result in heldout_tokenizer_results:
        result["profile_l1_distance_reduction_total"] = (
            result["baseline_profile_l1_distance_total"]
            - result["optimized_profile_l1_distance_total"]
        )
    heldout_family_results = []
    for family_id in _PLACEBO_ROLE_IDS:
        family_records = [
            record for record in all_placebo_records if record["family_id"] == family_id
        ]
        family_baseline = sum(
            record["heldout_profile_l1_distance_baseline"] for record in family_records
        )
        family_optimized = sum(
            record["heldout_profile_l1_distance_optimized"] for record in family_records
        )
        family_comparison_count = sum(
            record["heldout_profile_encoding_comparison_count"]
            for record in family_records
        )
        family_nonregression_count = sum(
            record["heldout_profile_encoding_nonregression_count"]
            for record in family_records
        )
        family_strict_improvement_count = sum(
            record["heldout_profile_encoding_strict_improvement_count"]
            for record in family_records
        )
        heldout_family_results.append(
            {
                "family_id": family_id,
                "comparison_count": family_comparison_count,
                "baseline_profile_l1_distance_total": family_baseline,
                "optimized_profile_l1_distance_total": family_optimized,
                "profile_l1_distance_reduction_total": (
                    family_baseline - family_optimized
                ),
                "profile_nonregression_count": family_nonregression_count,
                "profile_strict_improvement_count": (family_strict_improvement_count),
                "profile_regression_count": (
                    family_comparison_count - family_nonregression_count
                ),
            }
        )
    summary: dict[str, Any] = {
        "schema_version": FRONTIER_TOKENIZER_PLACEBO_SUMMARY_SCHEMA_VERSION,
        "set_id": FRONTIER_TOKENIZER_PLACEBO_SET_ID,
        "protocol_id": tasks_data["protocol_id"],
        "board_id": tasks_data["board_id"],
        "status": "five_arm_tokenizer_placebo_packets_compiled_review_not_started",
        "compiled_on": compiled_on,
        "public_coupled_placebo_summary_integrity_sha256": source_summary[
            "integrity_sha256"
        ],
        "private_packet_set_commitment": packet_set["integrity_sha256"],
        "private_key_set_commitment": key_set["integrity_sha256"],
        "design_rule": FRONTIER_TOKENIZER_PLACEBO_DESIGN_RULE,
        "tokenizer_package": "tiktoken",
        "tokenizer_package_version": TIKTOKEN_PACKAGE_VERSION,
        "tokenizer_profiles": list(_EXPECTED_ENCODING_PROFILES),
        "evaluation_only_tokenizer_profiles": list(
            _EXPECTED_EVALUATION_ENCODING_PROFILES
        ),
        "heldout_evaluation_status": "post_selection_diagnostic",
        "heldout_evaluation_used_for_selection": False,
        "heldout_evaluation_preregistered": False,
        "heldout_evaluation_external_validation": False,
        "profile_search_trials_per_placebo": (PROFILE_SEARCH_TRIALS_PER_PLACEBO),
        "five_arm_packet_count": len(packets),
        "canonical_arm_count": len(packets),
        "candidate_reveal_arm_count": len(packets),
        "placebo_variant_count": len(_PLACEBO_ROLE_IDS),
        "placebo_reveal_arm_count": len(all_placebo_records),
        "candidate_exact_structural_delta_count": sum(
            key["candidate_structural_delta_certificate"]["exact_delta_passed"]
            for key in keys
        ),
        "placebo_exact_structural_delta_count": sum(
            record["placebo_structural_delta_certificate"]["exact_delta_passed"]
            for record in all_placebo_records
        ),
        "candidate_placebo_structural_match_count": sum(
            record["candidate_placebo_structural_match_passed"]
            for record in all_placebo_records
        ),
        "whitespace_token_count_match_count": sum(
            record["whitespace_token_count_matched"] for record in all_placebo_records
        ),
        "placebo_vocabulary_family_pass_count": sum(
            record["vocabulary_family_policy_passed"] for record in all_placebo_records
        ),
        "tokenizer_comparison_count": tokenizer_comparison_count,
        "tokenizer_exact_token_count_match_count": sum(
            record["exact_token_count_match_count"] for record in all_placebo_records
        ),
        "all_tokenizer_count_match_placebo_count": sum(
            record["tokenizer_count_match_established"]
            for record in all_placebo_records
        ),
        "token_byte_length_histogram_match_count": byte_match_count,
        "token_rank_decile_histogram_match_count": rank_match_count,
        "deterministic_profile_search_replay_count": len(all_placebo_records),
        "baseline_profile_l1_distance_total": baseline_profile_distance_total,
        "optimized_profile_l1_distance_total": optimized_profile_distance_total,
        "profile_l1_distance_reduction_total": (
            baseline_profile_distance_total - optimized_profile_distance_total
        ),
        "strict_profile_improvement_placebo_count": sum(
            record["strict_profile_improvement_passed"]
            for record in all_placebo_records
        ),
        "profile_component_comparison_count": component_comparison_count,
        "profile_component_nonregression_count": component_nonregression_count,
        "profile_component_strict_improvement_count": (
            component_strict_improvement_count
        ),
        "profile_encoding_comparison_count": encoding_comparison_count,
        "profile_encoding_nonregression_count": encoding_nonregression_count,
        "distribution_optimization_acceptance_count": (optimization_acceptance_count),
        "heldout_tokenizer_comparison_count": (heldout_tokenizer_comparison_count),
        "heldout_exact_token_count_match_count_baseline": sum(
            record["heldout_exact_token_count_match_count_baseline"]
            for record in all_placebo_records
        ),
        "heldout_exact_token_count_match_count_optimized": sum(
            record["heldout_exact_token_count_match_count_optimized"]
            for record in all_placebo_records
        ),
        "heldout_token_byte_length_histogram_match_count_baseline": sum(
            record["heldout_token_byte_length_histogram_match_count_baseline"]
            for record in all_placebo_records
        ),
        "heldout_token_byte_length_histogram_match_count_optimized": sum(
            record["heldout_token_byte_length_histogram_match_count_optimized"]
            for record in all_placebo_records
        ),
        "heldout_token_rank_decile_histogram_match_count_baseline": sum(
            record["heldout_token_rank_decile_histogram_match_count_baseline"]
            for record in all_placebo_records
        ),
        "heldout_token_rank_decile_histogram_match_count_optimized": sum(
            record["heldout_token_rank_decile_histogram_match_count_optimized"]
            for record in all_placebo_records
        ),
        "heldout_profile_l1_distance_baseline_total": (
            heldout_profile_distance_baseline
        ),
        "heldout_profile_l1_distance_optimized_total": (
            heldout_profile_distance_optimized
        ),
        "heldout_profile_l1_distance_reduction_total": (
            heldout_profile_distance_baseline - heldout_profile_distance_optimized
        ),
        "heldout_profile_encoding_nonregression_count": (
            heldout_profile_nonregression_count
        ),
        "heldout_profile_encoding_strict_improvement_count": (
            heldout_profile_strict_improvement_count
        ),
        "heldout_profile_encoding_regression_count": (
            heldout_tokenizer_comparison_count - heldout_profile_nonregression_count
        ),
        "heldout_profile_component_comparison_count": (
            heldout_component_comparison_count
        ),
        "heldout_profile_component_nonregression_count": (
            heldout_component_nonregression_count
        ),
        "heldout_profile_component_strict_improvement_count": (
            heldout_component_strict_improvement_count
        ),
        "heldout_profile_component_regression_count": (
            heldout_component_comparison_count - heldout_component_nonregression_count
        ),
        "heldout_all_profile_nonregression_placebo_count": sum(
            record["heldout_all_profile_nonregression_passed"]
            for record in all_placebo_records
        ),
        "heldout_all_profile_strict_improvement_placebo_count": sum(
            record["heldout_all_profile_strict_improvement_passed"]
            for record in all_placebo_records
        ),
        "heldout_profile_regression_placebo_count": sum(
            not record["heldout_all_profile_nonregression_passed"]
            for record in all_placebo_records
        ),
        "heldout_token_count_absolute_gap_baseline_total": (
            heldout_count_gap_baseline_total
        ),
        "heldout_token_count_absolute_gap_optimized_total": (
            heldout_count_gap_optimized_total
        ),
        "heldout_token_count_absolute_gap_reduction_total": (
            heldout_count_gap_baseline_total - heldout_count_gap_optimized_total
        ),
        "heldout_token_count_gap_nonregression_count": (
            heldout_count_gap_nonregression_count
        ),
        "heldout_token_count_gap_strict_improvement_count": (
            heldout_count_gap_strict_improvement_count
        ),
        "heldout_token_count_gap_regression_count": (
            heldout_tokenizer_comparison_count - heldout_count_gap_nonregression_count
        ),
        "heldout_tokenizer_results": heldout_tokenizer_results,
        "heldout_family_results": heldout_family_results,
        "heldout_tokenizer_aggregate_improvement_count": sum(
            result["profile_l1_distance_reduction_total"] > 0
            for result in heldout_tokenizer_results
        ),
        "heldout_family_aggregate_improvement_count": sum(
            result["profile_l1_distance_reduction_total"] > 0
            for result in heldout_family_results
        ),
        "heldout_aggregate_profile_improvement_observed": (
            heldout_profile_distance_optimized < heldout_profile_distance_baseline
        ),
        "heldout_robust_placebo_generalization_ready": False,
        "heldout_token_count_confound_control_ready": False,
        "heldout_tokenizer_family_independence_established": False,
        "arm_role_balance_max_imbalance": max_imbalance,
        "arm_role_balance_passed": max_imbalance == 0,
        "five_arm_design_ready": len(packets) == 10,
        "structural_confound_control_ready": True,
        "tokenizer_count_confound_control_ready": (
            tokenizer_comparison_count
            == sum(
                record["exact_token_count_match_count"]
                for record in all_placebo_records
            )
        ),
        "deterministic_distribution_optimization_ready": (
            optimization_acceptance_count == len(all_placebo_records)
            and component_nonregression_count == component_comparison_count
            and encoding_nonregression_count == encoding_comparison_count
            and optimized_profile_distance_total < baseline_profile_distance_total
        ),
        "tokenizer_distribution_confound_control_ready": (
            byte_match_count == tokenizer_comparison_count
            and rank_match_count == tokenizer_comparison_count
        ),
        "lexical_confound_control_ready": False,
        "human_semantic_review_required": True,
        "reviewer_assignment_count": 0,
        "reviewer_response_count": 0,
        "candidate_coupling_label_count": 0,
        "placebo_invariance_label_count": 0,
        "contrast_label_count": 0,
        "consensus_label_count": 0,
        "placebo_scientific_invariance_established": False,
        "candidate_scientific_coupling_established": False,
        "contrast_identifiability_established": False,
        "canonical_transition_coupling_coverage_ready": source_summary[
            "canonical_transition_coupling_coverage_ready"
        ],
        "oracle_revision_applied": False,
        "challenge_assignment_authorized": False,
        "expert_solve_gate_changed": False,
        "admission_gate_changed": False,
        "board_admitted_count": 0,
        "baseline_model_runs_started": False,
        "benchmark_evidence_claimed": False,
        "private_payload_published": False,
        "nonclaims": sorted(_PUBLIC_NONCLAIMS),
        "integrity_sha256": "0" * 64,
    }
    summary["integrity_sha256"] = frontier_tokenizer_placebo_summary_integrity_sha256(
        summary
    )
    return packet_set, key_set, summary


def validate_frontier_tokenizer_placebo_summary(
    summary: Mapping[str, Any],
    *,
    public_coupled_placebo_summary: Mapping[str, Any],
    public_coupled_summary: Mapping[str, Any],
    public_semantic_summary: Mapping[str, Any],
    public_transition_summary: Mapping[str, Any],
    public_support_curation_summary: Mapping[str, Any],
    public_fragility_summary: Mapping[str, Any],
    public_preflight: Mapping[str, Any],
    progress: Mapping[str, Any],
    root: Path,
    frontier_protocol: Mapping[str, Any],
    board_protocol: Mapping[str, Any],
    board_slots: Mapping[str, Any],
) -> dict[str, Any]:
    validation_kwargs = {
        "root": root,
        "frontier_protocol": frontier_protocol,
        "board_protocol": board_protocol,
        "board_slots": board_slots,
    }
    progress_data = validate_frontier_calibration_progress(
        progress, **validation_kwargs
    )
    source_summary = validate_frontier_coupled_placebo_summary(
        public_coupled_placebo_summary,
        public_coupled_summary=public_coupled_summary,
        public_semantic_summary=public_semantic_summary,
        public_transition_summary=public_transition_summary,
        public_support_curation_summary=public_support_curation_summary,
        public_fragility_summary=public_fragility_summary,
        public_preflight=public_preflight,
        progress=progress_data,
        **validation_kwargs,
    )
    fields = {
        "schema_version",
        "set_id",
        "protocol_id",
        "board_id",
        "status",
        "compiled_on",
        "public_coupled_placebo_summary_integrity_sha256",
        "private_packet_set_commitment",
        "private_key_set_commitment",
        "design_rule",
        "tokenizer_package",
        "tokenizer_package_version",
        "tokenizer_profiles",
        "evaluation_only_tokenizer_profiles",
        "heldout_evaluation_status",
        "heldout_evaluation_used_for_selection",
        "heldout_evaluation_preregistered",
        "heldout_evaluation_external_validation",
        "profile_search_trials_per_placebo",
        "five_arm_packet_count",
        "canonical_arm_count",
        "candidate_reveal_arm_count",
        "placebo_variant_count",
        "placebo_reveal_arm_count",
        "candidate_exact_structural_delta_count",
        "placebo_exact_structural_delta_count",
        "candidate_placebo_structural_match_count",
        "whitespace_token_count_match_count",
        "placebo_vocabulary_family_pass_count",
        "tokenizer_comparison_count",
        "tokenizer_exact_token_count_match_count",
        "all_tokenizer_count_match_placebo_count",
        "token_byte_length_histogram_match_count",
        "token_rank_decile_histogram_match_count",
        "deterministic_profile_search_replay_count",
        "baseline_profile_l1_distance_total",
        "optimized_profile_l1_distance_total",
        "profile_l1_distance_reduction_total",
        "strict_profile_improvement_placebo_count",
        "profile_component_comparison_count",
        "profile_component_nonregression_count",
        "profile_component_strict_improvement_count",
        "profile_encoding_comparison_count",
        "profile_encoding_nonregression_count",
        "distribution_optimization_acceptance_count",
        "heldout_tokenizer_comparison_count",
        "heldout_exact_token_count_match_count_baseline",
        "heldout_exact_token_count_match_count_optimized",
        "heldout_token_byte_length_histogram_match_count_baseline",
        "heldout_token_byte_length_histogram_match_count_optimized",
        "heldout_token_rank_decile_histogram_match_count_baseline",
        "heldout_token_rank_decile_histogram_match_count_optimized",
        "heldout_profile_l1_distance_baseline_total",
        "heldout_profile_l1_distance_optimized_total",
        "heldout_profile_l1_distance_reduction_total",
        "heldout_profile_encoding_nonregression_count",
        "heldout_profile_encoding_strict_improvement_count",
        "heldout_profile_encoding_regression_count",
        "heldout_profile_component_comparison_count",
        "heldout_profile_component_nonregression_count",
        "heldout_profile_component_strict_improvement_count",
        "heldout_profile_component_regression_count",
        "heldout_all_profile_nonregression_placebo_count",
        "heldout_all_profile_strict_improvement_placebo_count",
        "heldout_profile_regression_placebo_count",
        "heldout_token_count_absolute_gap_baseline_total",
        "heldout_token_count_absolute_gap_optimized_total",
        "heldout_token_count_absolute_gap_reduction_total",
        "heldout_token_count_gap_nonregression_count",
        "heldout_token_count_gap_strict_improvement_count",
        "heldout_token_count_gap_regression_count",
        "heldout_tokenizer_results",
        "heldout_family_results",
        "heldout_tokenizer_aggregate_improvement_count",
        "heldout_family_aggregate_improvement_count",
        "heldout_aggregate_profile_improvement_observed",
        "heldout_robust_placebo_generalization_ready",
        "heldout_token_count_confound_control_ready",
        "heldout_tokenizer_family_independence_established",
        "arm_role_balance_max_imbalance",
        "arm_role_balance_passed",
        "five_arm_design_ready",
        "structural_confound_control_ready",
        "tokenizer_count_confound_control_ready",
        "deterministic_distribution_optimization_ready",
        "tokenizer_distribution_confound_control_ready",
        "lexical_confound_control_ready",
        "human_semantic_review_required",
        "reviewer_assignment_count",
        "reviewer_response_count",
        "candidate_coupling_label_count",
        "placebo_invariance_label_count",
        "contrast_label_count",
        "consensus_label_count",
        "placebo_scientific_invariance_established",
        "candidate_scientific_coupling_established",
        "contrast_identifiability_established",
        "canonical_transition_coupling_coverage_ready",
        "oracle_revision_applied",
        "challenge_assignment_authorized",
        "expert_solve_gate_changed",
        "admission_gate_changed",
        "board_admitted_count",
        "baseline_model_runs_started",
        "benchmark_evidence_claimed",
        "private_payload_published",
        "nonclaims",
        "integrity_sha256",
    }
    data = _record(summary, "tokenizer_placebo_summary", fields)
    if (
        data["schema_version"] != FRONTIER_TOKENIZER_PLACEBO_SUMMARY_SCHEMA_VERSION
        or data["set_id"] != FRONTIER_TOKENIZER_PLACEBO_SET_ID
        or data["protocol_id"] != source_summary["protocol_id"]
        or data["board_id"] != source_summary["board_id"]
    ):
        raise FrontierContractError("tokenizer placebo summary rebound provenance")
    if (
        data["status"]
        != "five_arm_tokenizer_placebo_packets_compiled_review_not_started"
    ):
        raise FrontierContractError("tokenizer placebo summary overstates maturity")
    _date(data["compiled_on"], "tokenizer placebo compiled_on")
    if (
        _sha256(
            data["public_coupled_placebo_summary_integrity_sha256"],
            "tokenizer placebo upstream summary",
        )
        != source_summary["integrity_sha256"]
    ):
        raise FrontierContractError("tokenizer placebo does not bind source summary")
    for field_name in (
        "private_packet_set_commitment",
        "private_key_set_commitment",
        "integrity_sha256",
    ):
        _sha256(data[field_name], f"tokenizer placebo {field_name}")
    if data["design_rule"] != FRONTIER_TOKENIZER_PLACEBO_DESIGN_RULE:
        raise FrontierContractError("tokenizer placebo changed the design rule")
    if (
        data["tokenizer_package"] != "tiktoken"
        or data["tokenizer_package_version"] != TIKTOKEN_PACKAGE_VERSION
        or data["tokenizer_profiles"] != list(_EXPECTED_ENCODING_PROFILES)
        or data["evaluation_only_tokenizer_profiles"]
        != list(_EXPECTED_EVALUATION_ENCODING_PROFILES)
    ):
        raise FrontierContractError("tokenizer placebo changed tokenizer provenance")
    if data["heldout_evaluation_status"] != "post_selection_diagnostic":
        raise FrontierContractError(
            "tokenizer placebo heldout evaluation changed maturity"
        )
    _load_frozen_encodings()
    _load_evaluation_only_encodings()
    exact_counts = {
        "profile_search_trials_per_placebo": PROFILE_SEARCH_TRIALS_PER_PLACEBO,
        "five_arm_packet_count": 10,
        "canonical_arm_count": 10,
        "candidate_reveal_arm_count": 10,
        "placebo_variant_count": 3,
        "placebo_reveal_arm_count": 30,
        "candidate_exact_structural_delta_count": 10,
        "placebo_exact_structural_delta_count": 30,
        "candidate_placebo_structural_match_count": 30,
        "whitespace_token_count_match_count": 30,
        "placebo_vocabulary_family_pass_count": 30,
        "tokenizer_comparison_count": 60,
        "tokenizer_exact_token_count_match_count": 60,
        "all_tokenizer_count_match_placebo_count": 30,
        "token_byte_length_histogram_match_count": 0,
        "token_rank_decile_histogram_match_count": 0,
        "deterministic_profile_search_replay_count": 30,
        "baseline_profile_l1_distance_total": 1908,
        "optimized_profile_l1_distance_total": 1454,
        "profile_l1_distance_reduction_total": 454,
        "strict_profile_improvement_placebo_count": 30,
        "profile_component_comparison_count": 120,
        "profile_component_nonregression_count": 120,
        "profile_component_strict_improvement_count": 102,
        "profile_encoding_comparison_count": 60,
        "profile_encoding_nonregression_count": 60,
        "distribution_optimization_acceptance_count": 30,
        "heldout_tokenizer_comparison_count": 60,
        "heldout_exact_token_count_match_count_baseline": 2,
        "heldout_exact_token_count_match_count_optimized": 4,
        "heldout_token_byte_length_histogram_match_count_baseline": 0,
        "heldout_token_byte_length_histogram_match_count_optimized": 0,
        "heldout_token_rank_decile_histogram_match_count_baseline": 0,
        "heldout_token_rank_decile_histogram_match_count_optimized": 0,
        "heldout_profile_l1_distance_baseline_total": 2166,
        "heldout_profile_l1_distance_optimized_total": 1940,
        "heldout_profile_l1_distance_reduction_total": 226,
        "heldout_profile_encoding_nonregression_count": 52,
        "heldout_profile_encoding_strict_improvement_count": 44,
        "heldout_profile_encoding_regression_count": 8,
        "heldout_profile_component_comparison_count": 120,
        "heldout_profile_component_nonregression_count": 98,
        "heldout_profile_component_strict_improvement_count": 74,
        "heldout_profile_component_regression_count": 22,
        "heldout_all_profile_nonregression_placebo_count": 26,
        "heldout_all_profile_strict_improvement_placebo_count": 22,
        "heldout_profile_regression_placebo_count": 4,
        "heldout_token_count_absolute_gap_baseline_total": 344,
        "heldout_token_count_absolute_gap_optimized_total": 342,
        "heldout_token_count_absolute_gap_reduction_total": 2,
        "heldout_token_count_gap_nonregression_count": 48,
        "heldout_token_count_gap_strict_improvement_count": 16,
        "heldout_token_count_gap_regression_count": 12,
        "heldout_tokenizer_aggregate_improvement_count": 2,
        "heldout_family_aggregate_improvement_count": 3,
        "arm_role_balance_max_imbalance": 0,
        "reviewer_assignment_count": 0,
        "reviewer_response_count": 0,
        "candidate_coupling_label_count": 0,
        "placebo_invariance_label_count": 0,
        "contrast_label_count": 0,
        "consensus_label_count": 0,
        "board_admitted_count": 0,
    }
    for field_name, expected in exact_counts.items():
        if _integer(data[field_name], f"tokenizer placebo {field_name}") != expected:
            raise FrontierContractError(
                f"tokenizer placebo {field_name} must remain {expected}"
            )
    expected_tokenizer_results = [
        {
            "encoding_name": "r50k_base",
            "comparison_count": 30,
            "baseline_profile_l1_distance_total": 1084,
            "optimized_profile_l1_distance_total": 970,
            "profile_l1_distance_reduction_total": 114,
        },
        {
            "encoding_name": "p50k_base",
            "comparison_count": 30,
            "baseline_profile_l1_distance_total": 1082,
            "optimized_profile_l1_distance_total": 970,
            "profile_l1_distance_reduction_total": 112,
        },
    ]
    expected_family_results = [
        {
            "family_id": "placebo_transport",
            "comparison_count": 20,
            "baseline_profile_l1_distance_total": 838,
            "optimized_profile_l1_distance_total": 700,
            "profile_l1_distance_reduction_total": 138,
            "profile_nonregression_count": 20,
            "profile_strict_improvement_count": 16,
            "profile_regression_count": 0,
        },
        {
            "family_id": "placebo_schema",
            "comparison_count": 20,
            "baseline_profile_l1_distance_total": 596,
            "optimized_profile_l1_distance_total": 592,
            "profile_l1_distance_reduction_total": 4,
            "profile_nonregression_count": 14,
            "profile_strict_improvement_count": 12,
            "profile_regression_count": 6,
        },
        {
            "family_id": "placebo_audit",
            "comparison_count": 20,
            "baseline_profile_l1_distance_total": 732,
            "optimized_profile_l1_distance_total": 648,
            "profile_l1_distance_reduction_total": 84,
            "profile_nonregression_count": 18,
            "profile_strict_improvement_count": 16,
            "profile_regression_count": 2,
        },
    ]
    if data["heldout_tokenizer_results"] != expected_tokenizer_results:
        raise FrontierContractError(
            "tokenizer placebo heldout tokenizer results changed"
        )
    if data["heldout_family_results"] != expected_family_results:
        raise FrontierContractError("tokenizer placebo heldout family results changed")
    for field_name in (
        "arm_role_balance_passed",
        "five_arm_design_ready",
        "structural_confound_control_ready",
        "tokenizer_count_confound_control_ready",
        "deterministic_distribution_optimization_ready",
        "heldout_aggregate_profile_improvement_observed",
        "human_semantic_review_required",
    ):
        if not _boolean(data[field_name], f"tokenizer placebo {field_name}"):
            raise FrontierContractError(
                f"tokenizer placebo {field_name} must remain true"
            )
    if (
        _boolean(
            data["canonical_transition_coupling_coverage_ready"],
            "tokenizer placebo canonical coverage",
        )
        != source_summary["canonical_transition_coupling_coverage_ready"]
    ):
        raise FrontierContractError("tokenizer placebo changed canonical coverage")
    for field_name in (
        "heldout_evaluation_used_for_selection",
        "heldout_evaluation_preregistered",
        "heldout_evaluation_external_validation",
        "heldout_robust_placebo_generalization_ready",
        "heldout_token_count_confound_control_ready",
        "heldout_tokenizer_family_independence_established",
        "tokenizer_distribution_confound_control_ready",
        "lexical_confound_control_ready",
        "placebo_scientific_invariance_established",
        "candidate_scientific_coupling_established",
        "contrast_identifiability_established",
        "oracle_revision_applied",
        "challenge_assignment_authorized",
        "expert_solve_gate_changed",
        "admission_gate_changed",
        "baseline_model_runs_started",
        "benchmark_evidence_claimed",
        "private_payload_published",
    ):
        if _boolean(data[field_name], f"tokenizer placebo {field_name}"):
            raise FrontierContractError(
                f"tokenizer placebo {field_name} must remain false"
            )
    if not _PUBLIC_NONCLAIMS.issubset(
        set(_text_list(data["nonclaims"], "tokenizer placebo nonclaims"))
    ):
        raise FrontierContractError("tokenizer placebo removed a public nonclaim")
    if data["integrity_sha256"] != (
        frontier_tokenizer_placebo_summary_integrity_sha256(data)
    ):
        raise FrontierContractError("tokenizer placebo summary integrity mismatch")
    return data


def validate_frontier_tokenizer_placebo_private_opening(
    *,
    private_packet_set: Mapping[str, Any],
    private_key_set: Mapping[str, Any],
    public_summary: Mapping[str, Any],
    private_coupled_placebo_packets: Mapping[str, Any],
    private_coupled_placebo_keys: Mapping[str, Any],
    public_coupled_placebo_summary: Mapping[str, Any],
    private_coupled_packet_set: Mapping[str, Any],
    public_coupled_summary: Mapping[str, Any],
    task_set: Mapping[str, Any],
    oracle_set: Mapping[str, Any],
    private_preflight: Mapping[str, Any],
    public_preflight: Mapping[str, Any],
    private_semantic_packets: Mapping[str, Any],
    private_semantic_keys: Mapping[str, Any],
    public_semantic_summary: Mapping[str, Any],
    private_transition_report: Mapping[str, Any],
    public_transition_summary: Mapping[str, Any],
    private_fragility_report: Mapping[str, Any],
    public_fragility_summary: Mapping[str, Any],
    private_support_curation_packets: Mapping[str, Any],
    public_support_curation_summary: Mapping[str, Any],
    progress: Mapping[str, Any],
    root: Path,
    frontier_protocol: Mapping[str, Any],
    board_protocol: Mapping[str, Any],
    board_slots: Mapping[str, Any],
) -> dict[str, Any]:
    validation_kwargs = {
        "root": root,
        "frontier_protocol": frontier_protocol,
        "board_protocol": board_protocol,
        "board_slots": board_slots,
    }
    data = validate_frontier_tokenizer_placebo_summary(
        public_summary,
        public_coupled_placebo_summary=public_coupled_placebo_summary,
        public_coupled_summary=public_coupled_summary,
        public_semantic_summary=public_semantic_summary,
        public_transition_summary=public_transition_summary,
        public_support_curation_summary=public_support_curation_summary,
        public_fragility_summary=public_fragility_summary,
        public_preflight=public_preflight,
        progress=progress,
        **validation_kwargs,
    )
    if private_packet_set.get("integrity_sha256") != (
        frontier_tokenizer_placebo_packet_set_integrity_sha256(private_packet_set)
    ):
        raise FrontierContractError("tokenizer placebo packet-set integrity mismatch")
    if private_key_set.get("integrity_sha256") != (
        frontier_tokenizer_placebo_key_set_integrity_sha256(private_key_set)
    ):
        raise FrontierContractError("tokenizer placebo key-set integrity mismatch")
    expected_packets, expected_keys, expected_summary = (
        compile_frontier_tokenizer_placebo_artifacts(
            private_coupled_placebo_packets=private_coupled_placebo_packets,
            private_coupled_placebo_keys=private_coupled_placebo_keys,
            public_coupled_placebo_summary=public_coupled_placebo_summary,
            private_coupled_packet_set=private_coupled_packet_set,
            public_coupled_summary=public_coupled_summary,
            task_set=task_set,
            oracle_set=oracle_set,
            private_preflight=private_preflight,
            public_preflight=public_preflight,
            private_semantic_packets=private_semantic_packets,
            private_semantic_keys=private_semantic_keys,
            public_semantic_summary=public_semantic_summary,
            private_transition_report=private_transition_report,
            public_transition_summary=public_transition_summary,
            private_fragility_report=private_fragility_report,
            public_fragility_summary=public_fragility_summary,
            private_support_curation_packets=private_support_curation_packets,
            public_support_curation_summary=public_support_curation_summary,
            progress=progress,
            compiled_on=data["compiled_on"],
            **validation_kwargs,
        )
    )
    if (
        private_packet_set != expected_packets
        or private_key_set != expected_keys
        or public_summary != expected_summary
    ):
        raise FrontierContractError(
            "tokenizer placebo artifacts do not replay from committed inputs"
        )
    return tokenizer_placebo_summary(
        public_summary,
        public_coupled_placebo_summary=public_coupled_placebo_summary,
        public_coupled_summary=public_coupled_summary,
        public_semantic_summary=public_semantic_summary,
        public_transition_summary=public_transition_summary,
        public_support_curation_summary=public_support_curation_summary,
        public_fragility_summary=public_fragility_summary,
        public_preflight=public_preflight,
        progress=progress,
        **validation_kwargs,
    ) | {"private_tokenizer_placebo_commitments_opened": True}


def load_frontier_tokenizer_placebo_packet_set(path: Path) -> dict[str, Any]:
    return _load_json(path.read_text(encoding="utf-8"), "tokenizer placebo packets")


def load_frontier_tokenizer_placebo_key_set(path: Path) -> dict[str, Any]:
    return _load_json(path.read_text(encoding="utf-8"), "tokenizer placebo keys")


def load_frontier_tokenizer_placebo_summary(path: Path) -> dict[str, Any]:
    return _load_json(path.read_text(encoding="utf-8"), "tokenizer placebo summary")


def tokenizer_placebo_summary(
    summary: Mapping[str, Any], **validation_kwargs: Any
) -> dict[str, Any]:
    data = validate_frontier_tokenizer_placebo_summary(summary, **validation_kwargs)
    return {
        "protocol_id": data["protocol_id"],
        "board_id": data["board_id"],
        "status": data["status"],
        "five_arm_packet_count": data["five_arm_packet_count"],
        "placebo_reveal_arm_count": data["placebo_reveal_arm_count"],
        "tokenizer_package_version": data["tokenizer_package_version"],
        "tokenizer_encoding_names": [
            profile["encoding_name"] for profile in data["tokenizer_profiles"]
        ],
        "evaluation_only_tokenizer_encoding_names": [
            profile["encoding_name"]
            for profile in data["evaluation_only_tokenizer_profiles"]
        ],
        "heldout_evaluation_status": data["heldout_evaluation_status"],
        "heldout_evaluation_used_for_selection": data[
            "heldout_evaluation_used_for_selection"
        ],
        "tokenizer_exact_token_count_match_count": data[
            "tokenizer_exact_token_count_match_count"
        ],
        "tokenizer_comparison_count": data["tokenizer_comparison_count"],
        "token_byte_length_histogram_match_count": data[
            "token_byte_length_histogram_match_count"
        ],
        "token_rank_decile_histogram_match_count": data[
            "token_rank_decile_histogram_match_count"
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
        "strict_profile_improvement_placebo_count": data[
            "strict_profile_improvement_placebo_count"
        ],
        "profile_component_nonregression_count": data[
            "profile_component_nonregression_count"
        ],
        "profile_component_comparison_count": data[
            "profile_component_comparison_count"
        ],
        "heldout_profile_l1_distance_baseline_total": data[
            "heldout_profile_l1_distance_baseline_total"
        ],
        "heldout_profile_l1_distance_optimized_total": data[
            "heldout_profile_l1_distance_optimized_total"
        ],
        "heldout_profile_l1_distance_reduction_total": data[
            "heldout_profile_l1_distance_reduction_total"
        ],
        "heldout_profile_encoding_nonregression_count": data[
            "heldout_profile_encoding_nonregression_count"
        ],
        "heldout_tokenizer_comparison_count": data[
            "heldout_tokenizer_comparison_count"
        ],
        "heldout_profile_regression_placebo_count": data[
            "heldout_profile_regression_placebo_count"
        ],
        "heldout_aggregate_profile_improvement_observed": data[
            "heldout_aggregate_profile_improvement_observed"
        ],
        "heldout_robust_placebo_generalization_ready": data[
            "heldout_robust_placebo_generalization_ready"
        ],
        "heldout_token_count_confound_control_ready": data[
            "heldout_token_count_confound_control_ready"
        ],
        "arm_role_balance_max_imbalance": data["arm_role_balance_max_imbalance"],
        "five_arm_design_ready": data["five_arm_design_ready"],
        "tokenizer_count_confound_control_ready": data[
            "tokenizer_count_confound_control_ready"
        ],
        "deterministic_distribution_optimization_ready": data[
            "deterministic_distribution_optimization_ready"
        ],
        "tokenizer_distribution_confound_control_ready": data[
            "tokenizer_distribution_confound_control_ready"
        ],
        "lexical_confound_control_ready": data["lexical_confound_control_ready"],
        "human_semantic_review_required": data["human_semantic_review_required"],
        "reviewer_response_count": data["reviewer_response_count"],
        "placebo_scientific_invariance_established": data[
            "placebo_scientific_invariance_established"
        ],
        "candidate_scientific_coupling_established": data[
            "candidate_scientific_coupling_established"
        ],
        "contrast_identifiability_established": data[
            "contrast_identifiability_established"
        ],
    }
