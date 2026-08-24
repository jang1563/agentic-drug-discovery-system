"""Command-line validation for ADDS-Frontier research contracts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from .frontier import (
    FrontierContractError,
    frontier_protocol_summary,
    frontier_seed_manifest_summary,
    load_frontier_protocol,
    load_frontier_seed_manifest,
)
from .frontier_tasks import (
    frontier_development_summary,
    load_frontier_curation_tranche,
    load_frontier_oracle_set,
    load_frontier_task_set,
)
from .frontier_board import (
    frontier_board_summary,
    load_frontier_board_protocol,
    load_frontier_board_slot_manifest,
)
from .frontier_calibration import (
    frontier_calibration_progress_summary,
    load_frontier_calibration_oracle_set,
    load_frontier_calibration_progress,
    load_frontier_calibration_task_set,
    validate_frontier_calibration_private_opening,
)
from .frontier_preflight import (
    frontier_preflight_summary,
    load_frontier_private_preflight_report,
    load_frontier_public_preflight_summary,
    validate_frontier_preflight_private_opening,
)
from .frontier_oracle_challenge import (
    load_frontier_oracle_challenge_key_set,
    load_frontier_oracle_challenge_ledger,
    load_frontier_oracle_challenge_packet_set,
    load_frontier_oracle_challenge_summary,
    oracle_challenge_summary,
    validate_frontier_oracle_challenge_private_opening,
)
from .frontier_oracle_fragility import (
    load_frontier_oracle_fragility_report,
    load_frontier_oracle_fragility_summary,
    oracle_fragility_summary,
    validate_frontier_oracle_fragility_private_opening,
)
from .frontier_oracle_support_curation import (
    load_frontier_support_curation_packet_set,
    load_frontier_support_curation_summary,
    support_curation_summary,
    validate_frontier_support_curation_private_opening,
)
from .frontier_oracle_transition_audit import (
    load_frontier_transition_audit_report,
    load_frontier_transition_audit_summary,
    transition_audit_summary,
    validate_frontier_transition_audit_private_opening,
)
from .frontier_coupled_augmentation import (
    coupled_augmentation_summary,
    load_frontier_coupled_augmentation_packet_set,
    load_frontier_coupled_augmentation_summary,
    validate_frontier_coupled_augmentation_private_opening,
)
from .frontier_coupled_placebo import (
    coupled_placebo_summary,
    load_frontier_coupled_placebo_key_set,
    load_frontier_coupled_placebo_packet_set,
    load_frontier_coupled_placebo_summary,
    validate_frontier_coupled_placebo_private_opening,
)
from .frontier_semantic_review import (
    load_frontier_semantic_review_key_set,
    load_frontier_semantic_review_packet_set,
    load_frontier_semantic_review_summary,
    semantic_review_summary,
    validate_frontier_semantic_review_private_opening,
)
from .frontier_semantic_resolution import (
    load_frontier_semantic_resolution_ledger,
    load_frontier_semantic_resolution_summary,
    semantic_resolution_summary,
    validate_frontier_semantic_resolution_private_opening,
)
from .frontier_semantic_workflow import (
    load_frontier_semantic_workflow_ledger,
    load_frontier_semantic_workflow_summary,
    semantic_workflow_summary,
    validate_frontier_semantic_workflow_private_opening,
)


DEFAULT_PROTOCOL = "docs/adds_frontier_research_protocol.json"
DEFAULT_SEED_MANIFEST = "rl_env/specs/frontier_pilot_seed_manifest.example.json"
DEFAULT_TASK_SET = "rl_env/specs/frontier_development_task_set.example.json"
DEFAULT_ORACLE_SET = "rl_env/specs/frontier_development_oracle_set.example.json"
DEFAULT_CURATION = "rl_env/specs/frontier_development_curation_tranche.example.json"
DEFAULT_BOARD_PROTOCOL = "docs/adds_frontier_board_protocol.json"
DEFAULT_BOARD_SLOTS = "rl_env/specs/frontier_private_board_slots.example.json"
DEFAULT_CALIBRATION_PROGRESS = (
    "rl_env/specs/frontier_calibration_authoring_progress.json"
)
DEFAULT_PRIVATE_CALIBRATION_TASKS = (
    "case_banks/frontier_private/calibration/frontier_calibration_tasks.private.json"
)
DEFAULT_PRIVATE_CALIBRATION_ORACLES = (
    "case_banks/frontier_private/calibration/frontier_calibration_oracles.private.json"
)
DEFAULT_PREFLIGHT_SUMMARY = "rl_env/specs/frontier_calibration_preflight_summary.json"
DEFAULT_PRIVATE_PREFLIGHT_REPORT = (
    "case_banks/frontier_private/calibration/"
    "frontier_calibration_preflight.private.json"
)
DEFAULT_SEMANTIC_REVIEW_SUMMARY = (
    "rl_env/specs/frontier_semantic_review_readiness_summary.json"
)
DEFAULT_PRIVATE_SEMANTIC_PACKETS = (
    "case_banks/frontier_private/calibration/"
    "frontier_semantic_review_packets.private.json"
)
DEFAULT_PRIVATE_SEMANTIC_KEYS = (
    "case_banks/frontier_private/calibration/frontier_semantic_review_keys.private.json"
)
DEFAULT_SEMANTIC_WORKFLOW_SUMMARY = (
    "rl_env/specs/frontier_semantic_review_workflow_summary.json"
)
DEFAULT_PRIVATE_SEMANTIC_WORKFLOW_LEDGER = (
    "case_banks/frontier_private/calibration/"
    "frontier_semantic_review_workflow_ledger.private.json"
)
DEFAULT_SEMANTIC_RESOLUTION_SUMMARY = (
    "rl_env/specs/frontier_semantic_review_resolution_summary.json"
)
DEFAULT_PRIVATE_SEMANTIC_RESOLUTION_LEDGER = (
    "case_banks/frontier_private/calibration/"
    "frontier_semantic_review_resolution_ledger.private.json"
)
DEFAULT_ORACLE_CHALLENGE_SUMMARY = (
    "rl_env/specs/frontier_oracle_challenge_readiness_summary.json"
)
DEFAULT_PRIVATE_ORACLE_CHALLENGE_PACKETS = (
    "case_banks/frontier_private/calibration/"
    "frontier_oracle_challenge_packets.private.json"
)
DEFAULT_PRIVATE_ORACLE_CHALLENGE_KEYS = (
    "case_banks/frontier_private/calibration/"
    "frontier_oracle_challenge_keys.private.json"
)
DEFAULT_PRIVATE_ORACLE_CHALLENGE_LEDGER = (
    "case_banks/frontier_private/calibration/"
    "frontier_oracle_challenge_ledger.private.json"
)
DEFAULT_ORACLE_FRAGILITY_SUMMARY = "rl_env/specs/frontier_oracle_fragility_summary.json"
DEFAULT_PRIVATE_ORACLE_FRAGILITY_REPORT = (
    "case_banks/frontier_private/calibration/"
    "frontier_oracle_fragility_report.private.json"
)
DEFAULT_SUPPORT_CURATION_SUMMARY = (
    "rl_env/specs/frontier_oracle_support_curation_summary.json"
)
DEFAULT_PRIVATE_SUPPORT_CURATION_PACKETS = (
    "case_banks/frontier_private/calibration/"
    "frontier_oracle_support_curation_packets.private.json"
)
DEFAULT_TRANSITION_AUDIT_SUMMARY = (
    "rl_env/specs/frontier_oracle_transition_audit_summary.json"
)
DEFAULT_PRIVATE_TRANSITION_AUDIT_REPORT = (
    "case_banks/frontier_private/calibration/"
    "frontier_oracle_transition_audit_report.private.json"
)
DEFAULT_COUPLED_AUGMENTATION_SUMMARY = (
    "rl_env/specs/frontier_coupled_augmentation_summary.json"
)
DEFAULT_PRIVATE_COUPLED_AUGMENTATION_PACKETS = (
    "case_banks/frontier_private/calibration/"
    "frontier_coupled_augmentation_packets.private.json"
)
DEFAULT_COUPLED_PLACEBO_SUMMARY = "rl_env/specs/frontier_coupled_placebo_summary.json"
DEFAULT_PRIVATE_COUPLED_PLACEBO_PACKETS = (
    "case_banks/frontier_private/calibration/"
    "frontier_coupled_placebo_packets.private.json"
)
DEFAULT_PRIVATE_COUPLED_PLACEBO_KEYS = (
    "case_banks/frontier_private/calibration/frontier_coupled_placebo_keys.private.json"
)
DEFAULT_TOKENIZER_PLACEBO_SUMMARY = (
    "rl_env/specs/frontier_tokenizer_placebo_summary.json"
)
DEFAULT_PRIVATE_TOKENIZER_PLACEBO_PACKETS = (
    "case_banks/frontier_private/calibration/"
    "frontier_tokenizer_placebo_packets.private.json"
)
DEFAULT_PRIVATE_TOKENIZER_PLACEBO_KEYS = (
    "case_banks/frontier_private/calibration/"
    "frontier_tokenizer_placebo_keys.private.json"
)
DEFAULT_TOKENIZER_INDEPENDENT_PROTOCOL = (
    "rl_env/specs/frontier_tokenizer_independent_evaluation_protocol.json"
)
DEFAULT_TOKENIZER_INDEPENDENT_SUMMARY = (
    "rl_env/specs/frontier_tokenizer_independent_evaluation_summary.json"
)
DEFAULT_PRIVATE_TOKENIZER_INDEPENDENT_REPORT = (
    "case_banks/frontier_private/calibration/"
    "frontier_tokenizer_independent_evaluation.private.json"
)
DEFAULT_TOKENIZER_INDEPENDENT_ASSET_ROOT = (
    "case_banks/frontier_private/tokenizer_assets"
)


def _resolve(path: str, *, root: Path) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else root / candidate


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate or summarize strict ADDS-Frontier research contracts."
    )
    parser.add_argument(
        "command",
        choices=(
            "validate-protocol",
            "summarize-protocol",
            "validate-seeds",
            "summarize-seeds",
            "validate-development",
            "summarize-development",
            "validate-board",
            "summarize-board",
            "validate-calibration",
            "summarize-calibration",
            "validate-private-calibration",
            "validate-preflight",
            "summarize-preflight",
            "validate-private-preflight",
            "validate-semantic-review",
            "summarize-semantic-review",
            "validate-private-semantic-review",
            "validate-semantic-workflow",
            "summarize-semantic-workflow",
            "validate-private-semantic-workflow",
            "validate-semantic-resolution",
            "summarize-semantic-resolution",
            "validate-private-semantic-resolution",
            "validate-oracle-challenge",
            "summarize-oracle-challenge",
            "validate-private-oracle-challenge",
            "validate-oracle-fragility",
            "summarize-oracle-fragility",
            "validate-private-oracle-fragility",
            "validate-support-curation",
            "summarize-support-curation",
            "validate-private-support-curation",
            "validate-transition-audit",
            "summarize-transition-audit",
            "validate-private-transition-audit",
            "validate-coupled-augmentation",
            "summarize-coupled-augmentation",
            "validate-private-coupled-augmentation",
            "validate-coupled-placebo",
            "summarize-coupled-placebo",
            "validate-private-coupled-placebo",
            "validate-tokenizer-placebo",
            "summarize-tokenizer-placebo",
            "validate-private-tokenizer-placebo",
            "validate-tokenizer-independent-evaluation",
            "summarize-tokenizer-independent-evaluation",
            "validate-private-tokenizer-independent-evaluation",
        ),
    )
    parser.add_argument("--protocol", default=DEFAULT_PROTOCOL)
    parser.add_argument("--seeds", default=DEFAULT_SEED_MANIFEST)
    parser.add_argument("--tasks", default=DEFAULT_TASK_SET)
    parser.add_argument("--oracles", default=DEFAULT_ORACLE_SET)
    parser.add_argument("--curation", default=DEFAULT_CURATION)
    parser.add_argument("--board-protocol", default=DEFAULT_BOARD_PROTOCOL)
    parser.add_argument("--board-slots", default=DEFAULT_BOARD_SLOTS)
    parser.add_argument("--calibration-progress", default=DEFAULT_CALIBRATION_PROGRESS)
    parser.add_argument(
        "--private-calibration-tasks", default=DEFAULT_PRIVATE_CALIBRATION_TASKS
    )
    parser.add_argument(
        "--private-calibration-oracles", default=DEFAULT_PRIVATE_CALIBRATION_ORACLES
    )
    parser.add_argument("--preflight-summary", default=DEFAULT_PREFLIGHT_SUMMARY)
    parser.add_argument(
        "--private-preflight-report", default=DEFAULT_PRIVATE_PREFLIGHT_REPORT
    )
    parser.add_argument(
        "--semantic-review-summary", default=DEFAULT_SEMANTIC_REVIEW_SUMMARY
    )
    parser.add_argument(
        "--private-semantic-packets", default=DEFAULT_PRIVATE_SEMANTIC_PACKETS
    )
    parser.add_argument(
        "--private-semantic-keys", default=DEFAULT_PRIVATE_SEMANTIC_KEYS
    )
    parser.add_argument(
        "--semantic-workflow-summary", default=DEFAULT_SEMANTIC_WORKFLOW_SUMMARY
    )
    parser.add_argument(
        "--private-semantic-workflow-ledger",
        default=DEFAULT_PRIVATE_SEMANTIC_WORKFLOW_LEDGER,
    )
    parser.add_argument(
        "--semantic-resolution-summary",
        default=DEFAULT_SEMANTIC_RESOLUTION_SUMMARY,
    )
    parser.add_argument(
        "--private-semantic-resolution-ledger",
        default=DEFAULT_PRIVATE_SEMANTIC_RESOLUTION_LEDGER,
    )
    parser.add_argument(
        "--oracle-challenge-summary", default=DEFAULT_ORACLE_CHALLENGE_SUMMARY
    )
    parser.add_argument(
        "--private-oracle-challenge-packets",
        default=DEFAULT_PRIVATE_ORACLE_CHALLENGE_PACKETS,
    )
    parser.add_argument(
        "--private-oracle-challenge-keys",
        default=DEFAULT_PRIVATE_ORACLE_CHALLENGE_KEYS,
    )
    parser.add_argument(
        "--private-oracle-challenge-ledger",
        default=DEFAULT_PRIVATE_ORACLE_CHALLENGE_LEDGER,
    )
    parser.add_argument(
        "--oracle-fragility-summary", default=DEFAULT_ORACLE_FRAGILITY_SUMMARY
    )
    parser.add_argument(
        "--private-oracle-fragility-report",
        default=DEFAULT_PRIVATE_ORACLE_FRAGILITY_REPORT,
    )
    parser.add_argument(
        "--support-curation-summary", default=DEFAULT_SUPPORT_CURATION_SUMMARY
    )
    parser.add_argument(
        "--private-support-curation-packets",
        default=DEFAULT_PRIVATE_SUPPORT_CURATION_PACKETS,
    )
    parser.add_argument(
        "--transition-audit-summary", default=DEFAULT_TRANSITION_AUDIT_SUMMARY
    )
    parser.add_argument(
        "--private-transition-audit-report",
        default=DEFAULT_PRIVATE_TRANSITION_AUDIT_REPORT,
    )
    parser.add_argument(
        "--coupled-augmentation-summary",
        default=DEFAULT_COUPLED_AUGMENTATION_SUMMARY,
    )
    parser.add_argument(
        "--private-coupled-augmentation-packets",
        default=DEFAULT_PRIVATE_COUPLED_AUGMENTATION_PACKETS,
    )
    parser.add_argument(
        "--coupled-placebo-summary",
        default=DEFAULT_COUPLED_PLACEBO_SUMMARY,
    )
    parser.add_argument(
        "--private-coupled-placebo-packets",
        default=DEFAULT_PRIVATE_COUPLED_PLACEBO_PACKETS,
    )
    parser.add_argument(
        "--private-coupled-placebo-keys",
        default=DEFAULT_PRIVATE_COUPLED_PLACEBO_KEYS,
    )
    parser.add_argument(
        "--tokenizer-placebo-summary",
        default=DEFAULT_TOKENIZER_PLACEBO_SUMMARY,
    )
    parser.add_argument(
        "--private-tokenizer-placebo-packets",
        default=DEFAULT_PRIVATE_TOKENIZER_PLACEBO_PACKETS,
    )
    parser.add_argument(
        "--private-tokenizer-placebo-keys",
        default=DEFAULT_PRIVATE_TOKENIZER_PLACEBO_KEYS,
    )
    parser.add_argument(
        "--tokenizer-independent-protocol",
        default=DEFAULT_TOKENIZER_INDEPENDENT_PROTOCOL,
    )
    parser.add_argument(
        "--tokenizer-independent-summary",
        default=DEFAULT_TOKENIZER_INDEPENDENT_SUMMARY,
    )
    parser.add_argument(
        "--private-tokenizer-independent-report",
        default=DEFAULT_PRIVATE_TOKENIZER_INDEPENDENT_REPORT,
    )
    parser.add_argument(
        "--tokenizer-independent-asset-root",
        default=DEFAULT_TOKENIZER_INDEPENDENT_ASSET_ROOT,
    )
    parser.add_argument("--root", default=".")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    try:
        protocol = load_frontier_protocol(
            _resolve(args.protocol, root=root),
            root=root,
        )
        if args.command.endswith("protocol"):
            summary = frontier_protocol_summary(protocol, root=root)
        elif args.command.endswith("seeds"):
            seeds = load_frontier_seed_manifest(
                _resolve(args.seeds, root=root),
                root=root,
                protocol=protocol,
            )
            summary = frontier_seed_manifest_summary(
                seeds,
                root=root,
                protocol=protocol,
            )
        elif args.command.endswith("board"):
            board_protocol = load_frontier_board_protocol(
                _resolve(args.board_protocol, root=root),
                root=root,
                frontier_protocol=protocol,
            )
            board_slots = load_frontier_board_slot_manifest(
                _resolve(args.board_slots, root=root),
                root=root,
                frontier_protocol=protocol,
                board_protocol=board_protocol,
            )
            summary = frontier_board_summary(
                board_slots,
                root=root,
                frontier_protocol=protocol,
                board_protocol=board_protocol,
            )
        elif args.command.endswith(
            (
                "coupled-augmentation",
                "coupled-placebo",
                "tokenizer-placebo",
                "tokenizer-independent-evaluation",
            )
        ):
            board_protocol = load_frontier_board_protocol(
                _resolve(args.board_protocol, root=root),
                root=root,
                frontier_protocol=protocol,
            )
            board_slots = load_frontier_board_slot_manifest(
                _resolve(args.board_slots, root=root),
                root=root,
                frontier_protocol=protocol,
                board_protocol=board_protocol,
            )
            augmentation_kwargs = {
                "root": root,
                "frontier_protocol": protocol,
                "board_protocol": board_protocol,
                "board_slots": board_slots,
            }
            progress = load_frontier_calibration_progress(
                _resolve(args.calibration_progress, root=root),
                **augmentation_kwargs,
            )
            public_preflight = load_frontier_public_preflight_summary(
                _resolve(args.preflight_summary, root=root),
                progress=progress,
                **augmentation_kwargs,
            )
            public_semantic = load_frontier_semantic_review_summary(
                _resolve(args.semantic_review_summary, root=root),
                public_preflight=public_preflight,
                progress=progress,
                **augmentation_kwargs,
            )
            public_fragility = load_frontier_oracle_fragility_summary(
                _resolve(args.oracle_fragility_summary, root=root),
                public_preflight=public_preflight,
                progress=progress,
                **augmentation_kwargs,
            )
            public_curation = load_frontier_support_curation_summary(
                _resolve(args.support_curation_summary, root=root),
                public_fragility_summary=public_fragility,
                public_preflight=public_preflight,
                progress=progress,
                **augmentation_kwargs,
            )
            public_transition = load_frontier_transition_audit_summary(
                _resolve(args.transition_audit_summary, root=root),
                public_support_curation_summary=public_curation,
                public_fragility_summary=public_fragility,
                public_preflight=public_preflight,
                progress=progress,
                **augmentation_kwargs,
            )
            public_augmentation = load_frontier_coupled_augmentation_summary(
                _resolve(args.coupled_augmentation_summary, root=root),
                public_semantic_summary=public_semantic,
                public_transition_summary=public_transition,
                public_support_curation_summary=public_curation,
                public_fragility_summary=public_fragility,
                public_preflight=public_preflight,
                progress=progress,
                **augmentation_kwargs,
            )
            if args.command.endswith(
                (
                    "coupled-placebo",
                    "tokenizer-placebo",
                    "tokenizer-independent-evaluation",
                )
            ):
                public_placebo = load_frontier_coupled_placebo_summary(
                    _resolve(args.coupled_placebo_summary, root=root),
                    public_coupled_summary=public_augmentation,
                    public_semantic_summary=public_semantic,
                    public_transition_summary=public_transition,
                    public_support_curation_summary=public_curation,
                    public_fragility_summary=public_fragility,
                    public_preflight=public_preflight,
                    progress=progress,
                    **augmentation_kwargs,
                )
                if args.command.endswith(
                    ("tokenizer-placebo", "tokenizer-independent-evaluation")
                ):
                    from .frontier_tokenizer_placebo import (
                        load_frontier_tokenizer_placebo_key_set,
                        load_frontier_tokenizer_placebo_packet_set,
                        load_frontier_tokenizer_placebo_summary,
                        tokenizer_placebo_summary,
                        validate_frontier_tokenizer_placebo_private_opening,
                    )

                    public_tokenizer_placebo = load_frontier_tokenizer_placebo_summary(
                        _resolve(args.tokenizer_placebo_summary, root=root)
                    )
                    if args.command.endswith("tokenizer-independent-evaluation"):
                        from .frontier_tokenizer_independent_evaluation import (
                            load_private_report,
                            load_protocol,
                            load_summary,
                            summary_view,
                            validate_private_opening,
                        )

                        tokenizer_placebo_summary(
                            public_tokenizer_placebo,
                            public_coupled_placebo_summary=public_placebo,
                            public_coupled_summary=public_augmentation,
                            public_semantic_summary=public_semantic,
                            public_transition_summary=public_transition,
                            public_support_curation_summary=public_curation,
                            public_fragility_summary=public_fragility,
                            public_preflight=public_preflight,
                            progress=progress,
                            **augmentation_kwargs,
                        )
                        independent_protocol = load_protocol(
                            _resolve(args.tokenizer_independent_protocol, root=root)
                        )
                        independent_summary = load_summary(
                            _resolve(args.tokenizer_independent_summary, root=root)
                        )
                        if args.command == (
                            "validate-private-tokenizer-independent-evaluation"
                        ):
                            private_tokenizer_packets = (
                                load_frontier_tokenizer_placebo_packet_set(
                                    _resolve(
                                        args.private_tokenizer_placebo_packets,
                                        root=root,
                                    )
                                )
                            )
                            private_tokenizer_keys = (
                                load_frontier_tokenizer_placebo_key_set(
                                    _resolve(
                                        args.private_tokenizer_placebo_keys,
                                        root=root,
                                    )
                                )
                            )
                            summary = validate_private_opening(
                                private_report=load_private_report(
                                    _resolve(
                                        args.private_tokenizer_independent_report,
                                        root=root,
                                    )
                                ),
                                summary=independent_summary,
                                protocol=independent_protocol,
                                private_packet_set=private_tokenizer_packets,
                                private_key_set=private_tokenizer_keys,
                                parent_summary=public_tokenizer_placebo,
                                asset_root=_resolve(
                                    args.tokenizer_independent_asset_root,
                                    root=root,
                                ),
                            )
                        else:
                            summary = summary_view(
                                independent_summary,
                                protocol=independent_protocol,
                                parent_summary=public_tokenizer_placebo,
                            )
                    elif args.command == "validate-private-tokenizer-placebo":
                        private_tasks = load_frontier_calibration_task_set(
                            _resolve(args.private_calibration_tasks, root=root),
                            **augmentation_kwargs,
                        )
                        private_oracles = load_frontier_calibration_oracle_set(
                            _resolve(args.private_calibration_oracles, root=root),
                            task_set=private_tasks,
                            **augmentation_kwargs,
                        )
                        private_preflight = load_frontier_private_preflight_report(
                            _resolve(args.private_preflight_report, root=root),
                            task_set=private_tasks,
                            oracle_set=private_oracles,
                            progress=progress,
                            **augmentation_kwargs,
                        )
                        private_semantic_packets = (
                            load_frontier_semantic_review_packet_set(
                                _resolve(args.private_semantic_packets, root=root)
                            )
                        )
                        private_semantic_keys = load_frontier_semantic_review_key_set(
                            _resolve(args.private_semantic_keys, root=root)
                        )
                        private_fragility = load_frontier_oracle_fragility_report(
                            _resolve(args.private_oracle_fragility_report, root=root)
                        )
                        private_curation = load_frontier_support_curation_packet_set(
                            _resolve(
                                args.private_support_curation_packets,
                                root=root,
                            )
                        )
                        private_transition = load_frontier_transition_audit_report(
                            _resolve(
                                args.private_transition_audit_report,
                                root=root,
                            )
                        )
                        private_augmentation = (
                            load_frontier_coupled_augmentation_packet_set(
                                _resolve(
                                    args.private_coupled_augmentation_packets,
                                    root=root,
                                )
                            )
                        )
                        private_placebo_packets = (
                            load_frontier_coupled_placebo_packet_set(
                                _resolve(
                                    args.private_coupled_placebo_packets,
                                    root=root,
                                )
                            )
                        )
                        private_placebo_keys = load_frontier_coupled_placebo_key_set(
                            _resolve(
                                args.private_coupled_placebo_keys,
                                root=root,
                            )
                        )
                        private_tokenizer_packets = (
                            load_frontier_tokenizer_placebo_packet_set(
                                _resolve(
                                    args.private_tokenizer_placebo_packets,
                                    root=root,
                                )
                            )
                        )
                        private_tokenizer_keys = (
                            load_frontier_tokenizer_placebo_key_set(
                                _resolve(
                                    args.private_tokenizer_placebo_keys,
                                    root=root,
                                )
                            )
                        )
                        summary = validate_frontier_tokenizer_placebo_private_opening(
                            private_packet_set=private_tokenizer_packets,
                            private_key_set=private_tokenizer_keys,
                            public_summary=public_tokenizer_placebo,
                            private_coupled_placebo_packets=(private_placebo_packets),
                            private_coupled_placebo_keys=private_placebo_keys,
                            public_coupled_placebo_summary=public_placebo,
                            private_coupled_packet_set=private_augmentation,
                            public_coupled_summary=public_augmentation,
                            task_set=private_tasks,
                            oracle_set=private_oracles,
                            private_preflight=private_preflight,
                            public_preflight=public_preflight,
                            private_semantic_packets=private_semantic_packets,
                            private_semantic_keys=private_semantic_keys,
                            public_semantic_summary=public_semantic,
                            private_transition_report=private_transition,
                            public_transition_summary=public_transition,
                            private_fragility_report=private_fragility,
                            public_fragility_summary=public_fragility,
                            private_support_curation_packets=private_curation,
                            public_support_curation_summary=public_curation,
                            progress=progress,
                            **augmentation_kwargs,
                        )
                    else:
                        summary = tokenizer_placebo_summary(
                            public_tokenizer_placebo,
                            public_coupled_placebo_summary=public_placebo,
                            public_coupled_summary=public_augmentation,
                            public_semantic_summary=public_semantic,
                            public_transition_summary=public_transition,
                            public_support_curation_summary=public_curation,
                            public_fragility_summary=public_fragility,
                            public_preflight=public_preflight,
                            progress=progress,
                            **augmentation_kwargs,
                        )
                elif args.command == "validate-private-coupled-placebo":
                    private_tasks = load_frontier_calibration_task_set(
                        _resolve(args.private_calibration_tasks, root=root),
                        **augmentation_kwargs,
                    )
                    private_oracles = load_frontier_calibration_oracle_set(
                        _resolve(args.private_calibration_oracles, root=root),
                        task_set=private_tasks,
                        **augmentation_kwargs,
                    )
                    private_preflight = load_frontier_private_preflight_report(
                        _resolve(args.private_preflight_report, root=root),
                        task_set=private_tasks,
                        oracle_set=private_oracles,
                        progress=progress,
                        **augmentation_kwargs,
                    )
                    private_semantic_packets = load_frontier_semantic_review_packet_set(
                        _resolve(args.private_semantic_packets, root=root)
                    )
                    private_semantic_keys = load_frontier_semantic_review_key_set(
                        _resolve(args.private_semantic_keys, root=root)
                    )
                    private_fragility = load_frontier_oracle_fragility_report(
                        _resolve(args.private_oracle_fragility_report, root=root)
                    )
                    private_curation = load_frontier_support_curation_packet_set(
                        _resolve(args.private_support_curation_packets, root=root)
                    )
                    private_transition = load_frontier_transition_audit_report(
                        _resolve(args.private_transition_audit_report, root=root)
                    )
                    private_augmentation = (
                        load_frontier_coupled_augmentation_packet_set(
                            _resolve(
                                args.private_coupled_augmentation_packets,
                                root=root,
                            )
                        )
                    )
                    private_placebo_packets = load_frontier_coupled_placebo_packet_set(
                        _resolve(args.private_coupled_placebo_packets, root=root)
                    )
                    private_placebo_keys = load_frontier_coupled_placebo_key_set(
                        _resolve(args.private_coupled_placebo_keys, root=root)
                    )
                    summary = validate_frontier_coupled_placebo_private_opening(
                        private_packet_set=private_placebo_packets,
                        private_key_set=private_placebo_keys,
                        public_summary=public_placebo,
                        private_coupled_packet_set=private_augmentation,
                        public_coupled_summary=public_augmentation,
                        task_set=private_tasks,
                        oracle_set=private_oracles,
                        private_preflight=private_preflight,
                        public_preflight=public_preflight,
                        private_semantic_packets=private_semantic_packets,
                        private_semantic_keys=private_semantic_keys,
                        public_semantic_summary=public_semantic,
                        private_transition_report=private_transition,
                        public_transition_summary=public_transition,
                        private_fragility_report=private_fragility,
                        public_fragility_summary=public_fragility,
                        private_support_curation_packets=private_curation,
                        public_support_curation_summary=public_curation,
                        progress=progress,
                        **augmentation_kwargs,
                    )
                else:
                    summary = coupled_placebo_summary(
                        public_placebo,
                        public_coupled_summary=public_augmentation,
                        public_semantic_summary=public_semantic,
                        public_transition_summary=public_transition,
                        public_support_curation_summary=public_curation,
                        public_fragility_summary=public_fragility,
                        public_preflight=public_preflight,
                        progress=progress,
                        **augmentation_kwargs,
                    )
            elif args.command == "validate-private-coupled-augmentation":
                private_tasks = load_frontier_calibration_task_set(
                    _resolve(args.private_calibration_tasks, root=root),
                    **augmentation_kwargs,
                )
                private_oracles = load_frontier_calibration_oracle_set(
                    _resolve(args.private_calibration_oracles, root=root),
                    task_set=private_tasks,
                    **augmentation_kwargs,
                )
                private_preflight = load_frontier_private_preflight_report(
                    _resolve(args.private_preflight_report, root=root),
                    task_set=private_tasks,
                    oracle_set=private_oracles,
                    progress=progress,
                    **augmentation_kwargs,
                )
                private_semantic_packets = load_frontier_semantic_review_packet_set(
                    _resolve(args.private_semantic_packets, root=root)
                )
                private_semantic_keys = load_frontier_semantic_review_key_set(
                    _resolve(args.private_semantic_keys, root=root)
                )
                private_fragility = load_frontier_oracle_fragility_report(
                    _resolve(args.private_oracle_fragility_report, root=root)
                )
                private_curation = load_frontier_support_curation_packet_set(
                    _resolve(args.private_support_curation_packets, root=root)
                )
                private_transition = load_frontier_transition_audit_report(
                    _resolve(args.private_transition_audit_report, root=root)
                )
                private_augmentation = load_frontier_coupled_augmentation_packet_set(
                    _resolve(args.private_coupled_augmentation_packets, root=root)
                )
                summary = validate_frontier_coupled_augmentation_private_opening(
                    private_packet_set=private_augmentation,
                    public_summary=public_augmentation,
                    task_set=private_tasks,
                    oracle_set=private_oracles,
                    private_preflight=private_preflight,
                    public_preflight=public_preflight,
                    private_semantic_packets=private_semantic_packets,
                    private_semantic_keys=private_semantic_keys,
                    public_semantic_summary=public_semantic,
                    private_transition_report=private_transition,
                    public_transition_summary=public_transition,
                    private_fragility_report=private_fragility,
                    public_fragility_summary=public_fragility,
                    private_support_curation_packets=private_curation,
                    public_support_curation_summary=public_curation,
                    progress=progress,
                    **augmentation_kwargs,
                )
            else:
                summary = coupled_augmentation_summary(
                    public_augmentation,
                    public_semantic_summary=public_semantic,
                    public_transition_summary=public_transition,
                    public_support_curation_summary=public_curation,
                    public_fragility_summary=public_fragility,
                    public_preflight=public_preflight,
                    progress=progress,
                    **augmentation_kwargs,
                )
        elif args.command.endswith("transition-audit"):
            board_protocol = load_frontier_board_protocol(
                _resolve(args.board_protocol, root=root),
                root=root,
                frontier_protocol=protocol,
            )
            board_slots = load_frontier_board_slot_manifest(
                _resolve(args.board_slots, root=root),
                root=root,
                frontier_protocol=protocol,
                board_protocol=board_protocol,
            )
            transition_kwargs = {
                "root": root,
                "frontier_protocol": protocol,
                "board_protocol": board_protocol,
                "board_slots": board_slots,
            }
            progress = load_frontier_calibration_progress(
                _resolve(args.calibration_progress, root=root),
                **transition_kwargs,
            )
            public_preflight = load_frontier_public_preflight_summary(
                _resolve(args.preflight_summary, root=root),
                progress=progress,
                **transition_kwargs,
            )
            public_fragility = load_frontier_oracle_fragility_summary(
                _resolve(args.oracle_fragility_summary, root=root),
                public_preflight=public_preflight,
                progress=progress,
                **transition_kwargs,
            )
            public_curation = load_frontier_support_curation_summary(
                _resolve(args.support_curation_summary, root=root),
                public_fragility_summary=public_fragility,
                public_preflight=public_preflight,
                progress=progress,
                **transition_kwargs,
            )
            public_transition = load_frontier_transition_audit_summary(
                _resolve(args.transition_audit_summary, root=root),
                public_support_curation_summary=public_curation,
                public_fragility_summary=public_fragility,
                public_preflight=public_preflight,
                progress=progress,
                **transition_kwargs,
            )
            if args.command == "validate-private-transition-audit":
                private_tasks = load_frontier_calibration_task_set(
                    _resolve(args.private_calibration_tasks, root=root),
                    **transition_kwargs,
                )
                private_oracles = load_frontier_calibration_oracle_set(
                    _resolve(args.private_calibration_oracles, root=root),
                    task_set=private_tasks,
                    **transition_kwargs,
                )
                private_preflight = load_frontier_private_preflight_report(
                    _resolve(args.private_preflight_report, root=root),
                    task_set=private_tasks,
                    oracle_set=private_oracles,
                    progress=progress,
                    **transition_kwargs,
                )
                private_fragility = load_frontier_oracle_fragility_report(
                    _resolve(args.private_oracle_fragility_report, root=root)
                )
                private_curation = load_frontier_support_curation_packet_set(
                    _resolve(args.private_support_curation_packets, root=root)
                )
                private_transition = load_frontier_transition_audit_report(
                    _resolve(args.private_transition_audit_report, root=root)
                )
                summary = validate_frontier_transition_audit_private_opening(
                    private_report=private_transition,
                    public_summary=public_transition,
                    task_set=private_tasks,
                    oracle_set=private_oracles,
                    private_preflight=private_preflight,
                    public_preflight=public_preflight,
                    private_fragility_report=private_fragility,
                    public_fragility_summary=public_fragility,
                    private_support_curation_packets=private_curation,
                    public_support_curation_summary=public_curation,
                    progress=progress,
                    **transition_kwargs,
                )
            else:
                summary = transition_audit_summary(
                    public_transition,
                    public_support_curation_summary=public_curation,
                    public_fragility_summary=public_fragility,
                    public_preflight=public_preflight,
                    progress=progress,
                    **transition_kwargs,
                )
        elif args.command.endswith("support-curation"):
            board_protocol = load_frontier_board_protocol(
                _resolve(args.board_protocol, root=root),
                root=root,
                frontier_protocol=protocol,
            )
            board_slots = load_frontier_board_slot_manifest(
                _resolve(args.board_slots, root=root),
                root=root,
                frontier_protocol=protocol,
                board_protocol=board_protocol,
            )
            curation_kwargs = {
                "root": root,
                "frontier_protocol": protocol,
                "board_protocol": board_protocol,
                "board_slots": board_slots,
            }
            progress = load_frontier_calibration_progress(
                _resolve(args.calibration_progress, root=root),
                **curation_kwargs,
            )
            public_preflight = load_frontier_public_preflight_summary(
                _resolve(args.preflight_summary, root=root),
                progress=progress,
                **curation_kwargs,
            )
            public_fragility = load_frontier_oracle_fragility_summary(
                _resolve(args.oracle_fragility_summary, root=root),
                public_preflight=public_preflight,
                progress=progress,
                **curation_kwargs,
            )
            public_curation = load_frontier_support_curation_summary(
                _resolve(args.support_curation_summary, root=root),
                public_fragility_summary=public_fragility,
                public_preflight=public_preflight,
                progress=progress,
                **curation_kwargs,
            )
            if args.command == "validate-private-support-curation":
                private_tasks = load_frontier_calibration_task_set(
                    _resolve(args.private_calibration_tasks, root=root),
                    **curation_kwargs,
                )
                private_oracles = load_frontier_calibration_oracle_set(
                    _resolve(args.private_calibration_oracles, root=root),
                    task_set=private_tasks,
                    **curation_kwargs,
                )
                private_preflight = load_frontier_private_preflight_report(
                    _resolve(args.private_preflight_report, root=root),
                    task_set=private_tasks,
                    oracle_set=private_oracles,
                    progress=progress,
                    **curation_kwargs,
                )
                private_fragility = load_frontier_oracle_fragility_report(
                    _resolve(args.private_oracle_fragility_report, root=root)
                )
                private_curation = load_frontier_support_curation_packet_set(
                    _resolve(args.private_support_curation_packets, root=root)
                )
                summary = validate_frontier_support_curation_private_opening(
                    private_packet_set=private_curation,
                    public_summary=public_curation,
                    task_set=private_tasks,
                    oracle_set=private_oracles,
                    private_preflight=private_preflight,
                    public_preflight=public_preflight,
                    private_fragility_report=private_fragility,
                    public_fragility_summary=public_fragility,
                    progress=progress,
                    **curation_kwargs,
                )
            else:
                summary = support_curation_summary(
                    public_curation,
                    public_fragility_summary=public_fragility,
                    public_preflight=public_preflight,
                    progress=progress,
                    **curation_kwargs,
                )
        elif args.command.endswith("oracle-fragility"):
            board_protocol = load_frontier_board_protocol(
                _resolve(args.board_protocol, root=root),
                root=root,
                frontier_protocol=protocol,
            )
            board_slots = load_frontier_board_slot_manifest(
                _resolve(args.board_slots, root=root),
                root=root,
                frontier_protocol=protocol,
                board_protocol=board_protocol,
            )
            fragility_kwargs = {
                "root": root,
                "frontier_protocol": protocol,
                "board_protocol": board_protocol,
                "board_slots": board_slots,
            }
            progress = load_frontier_calibration_progress(
                _resolve(args.calibration_progress, root=root),
                **fragility_kwargs,
            )
            public_preflight = load_frontier_public_preflight_summary(
                _resolve(args.preflight_summary, root=root),
                progress=progress,
                **fragility_kwargs,
            )
            public_fragility = load_frontier_oracle_fragility_summary(
                _resolve(args.oracle_fragility_summary, root=root),
                public_preflight=public_preflight,
                progress=progress,
                **fragility_kwargs,
            )
            if args.command == "validate-private-oracle-fragility":
                private_tasks = load_frontier_calibration_task_set(
                    _resolve(args.private_calibration_tasks, root=root),
                    **fragility_kwargs,
                )
                private_oracles = load_frontier_calibration_oracle_set(
                    _resolve(args.private_calibration_oracles, root=root),
                    task_set=private_tasks,
                    **fragility_kwargs,
                )
                private_preflight = load_frontier_private_preflight_report(
                    _resolve(args.private_preflight_report, root=root),
                    task_set=private_tasks,
                    oracle_set=private_oracles,
                    progress=progress,
                    **fragility_kwargs,
                )
                private_fragility = load_frontier_oracle_fragility_report(
                    _resolve(args.private_oracle_fragility_report, root=root)
                )
                summary = validate_frontier_oracle_fragility_private_opening(
                    private_report=private_fragility,
                    public_summary=public_fragility,
                    task_set=private_tasks,
                    oracle_set=private_oracles,
                    private_preflight=private_preflight,
                    public_preflight=public_preflight,
                    progress=progress,
                    **fragility_kwargs,
                )
            else:
                summary = oracle_fragility_summary(
                    public_fragility,
                    public_preflight=public_preflight,
                    progress=progress,
                    **fragility_kwargs,
                )
        elif args.command.endswith("oracle-challenge"):
            board_protocol = load_frontier_board_protocol(
                _resolve(args.board_protocol, root=root),
                root=root,
                frontier_protocol=protocol,
            )
            board_slots = load_frontier_board_slot_manifest(
                _resolve(args.board_slots, root=root),
                root=root,
                frontier_protocol=protocol,
                board_protocol=board_protocol,
            )
            challenge_kwargs = {
                "root": root,
                "frontier_protocol": protocol,
                "board_protocol": board_protocol,
                "board_slots": board_slots,
            }
            progress = load_frontier_calibration_progress(
                _resolve(args.calibration_progress, root=root),
                **challenge_kwargs,
            )
            public_preflight = load_frontier_public_preflight_summary(
                _resolve(args.preflight_summary, root=root),
                progress=progress,
                **challenge_kwargs,
            )
            public_challenge = load_frontier_oracle_challenge_summary(
                _resolve(args.oracle_challenge_summary, root=root),
                public_preflight=public_preflight,
                progress=progress,
                **challenge_kwargs,
            )
            if args.command == "validate-private-oracle-challenge":
                private_tasks = load_frontier_calibration_task_set(
                    _resolve(args.private_calibration_tasks, root=root),
                    **challenge_kwargs,
                )
                private_oracles = load_frontier_calibration_oracle_set(
                    _resolve(args.private_calibration_oracles, root=root),
                    task_set=private_tasks,
                    **challenge_kwargs,
                )
                private_preflight = load_frontier_private_preflight_report(
                    _resolve(args.private_preflight_report, root=root),
                    task_set=private_tasks,
                    oracle_set=private_oracles,
                    progress=progress,
                    **challenge_kwargs,
                )
                packets = load_frontier_oracle_challenge_packet_set(
                    _resolve(args.private_oracle_challenge_packets, root=root)
                )
                keys = load_frontier_oracle_challenge_key_set(
                    _resolve(args.private_oracle_challenge_keys, root=root)
                )
                ledger = load_frontier_oracle_challenge_ledger(
                    _resolve(args.private_oracle_challenge_ledger, root=root)
                )
                summary = validate_frontier_oracle_challenge_private_opening(
                    packet_set=packets,
                    key_set=keys,
                    ledger=ledger,
                    public_summary=public_challenge,
                    task_set=private_tasks,
                    oracle_set=private_oracles,
                    private_preflight=private_preflight,
                    public_preflight=public_preflight,
                    progress=progress,
                    **challenge_kwargs,
                )
            else:
                summary = oracle_challenge_summary(
                    public_challenge,
                    public_preflight=public_preflight,
                    progress=progress,
                    **challenge_kwargs,
                )
        elif args.command.endswith("semantic-resolution"):
            board_protocol = load_frontier_board_protocol(
                _resolve(args.board_protocol, root=root),
                root=root,
                frontier_protocol=protocol,
            )
            board_slots = load_frontier_board_slot_manifest(
                _resolve(args.board_slots, root=root),
                root=root,
                frontier_protocol=protocol,
                board_protocol=board_protocol,
            )
            resolution_kwargs = {
                "root": root,
                "frontier_protocol": protocol,
                "board_protocol": board_protocol,
                "board_slots": board_slots,
            }
            progress = load_frontier_calibration_progress(
                _resolve(args.calibration_progress, root=root),
                **resolution_kwargs,
            )
            public_preflight = load_frontier_public_preflight_summary(
                _resolve(args.preflight_summary, root=root),
                progress=progress,
                **resolution_kwargs,
            )
            public_semantic = load_frontier_semantic_review_summary(
                _resolve(args.semantic_review_summary, root=root),
                public_preflight=public_preflight,
                progress=progress,
                **resolution_kwargs,
            )
            public_workflow = load_frontier_semantic_workflow_summary(
                _resolve(args.semantic_workflow_summary, root=root),
                semantic_summary=public_semantic,
                public_preflight=public_preflight,
                progress=progress,
                **resolution_kwargs,
            )
            public_resolution = load_frontier_semantic_resolution_summary(
                _resolve(args.semantic_resolution_summary, root=root),
                workflow_summary=public_workflow,
                semantic_summary=public_semantic,
                public_preflight=public_preflight,
                progress=progress,
                **resolution_kwargs,
            )
            if args.command == "validate-private-semantic-resolution":
                packets = load_frontier_semantic_review_packet_set(
                    _resolve(args.private_semantic_packets, root=root)
                )
                keys = load_frontier_semantic_review_key_set(
                    _resolve(args.private_semantic_keys, root=root)
                )
                workflow_ledger = load_frontier_semantic_workflow_ledger(
                    _resolve(args.private_semantic_workflow_ledger, root=root)
                )
                resolution_ledger = load_frontier_semantic_resolution_ledger(
                    _resolve(args.private_semantic_resolution_ledger, root=root)
                )
                summary = validate_frontier_semantic_resolution_private_opening(
                    ledger=resolution_ledger,
                    public_summary=public_resolution,
                    workflow_ledger=workflow_ledger,
                    workflow_summary=public_workflow,
                    packet_set=packets,
                    key_set=keys,
                    semantic_summary=public_semantic,
                    public_preflight=public_preflight,
                    progress=progress,
                    **resolution_kwargs,
                )
            else:
                summary = semantic_resolution_summary(
                    public_resolution,
                    workflow_summary=public_workflow,
                    semantic_summary=public_semantic,
                    public_preflight=public_preflight,
                    progress=progress,
                    **resolution_kwargs,
                )
        elif args.command.endswith("semantic-workflow"):
            board_protocol = load_frontier_board_protocol(
                _resolve(args.board_protocol, root=root),
                root=root,
                frontier_protocol=protocol,
            )
            board_slots = load_frontier_board_slot_manifest(
                _resolve(args.board_slots, root=root),
                root=root,
                frontier_protocol=protocol,
                board_protocol=board_protocol,
            )
            workflow_kwargs = {
                "root": root,
                "frontier_protocol": protocol,
                "board_protocol": board_protocol,
                "board_slots": board_slots,
            }
            progress = load_frontier_calibration_progress(
                _resolve(args.calibration_progress, root=root),
                **workflow_kwargs,
            )
            public_preflight = load_frontier_public_preflight_summary(
                _resolve(args.preflight_summary, root=root),
                progress=progress,
                **workflow_kwargs,
            )
            public_semantic = load_frontier_semantic_review_summary(
                _resolve(args.semantic_review_summary, root=root),
                public_preflight=public_preflight,
                progress=progress,
                **workflow_kwargs,
            )
            public_workflow = load_frontier_semantic_workflow_summary(
                _resolve(args.semantic_workflow_summary, root=root),
                semantic_summary=public_semantic,
                public_preflight=public_preflight,
                progress=progress,
                **workflow_kwargs,
            )
            if args.command == "validate-private-semantic-workflow":
                packets = load_frontier_semantic_review_packet_set(
                    _resolve(args.private_semantic_packets, root=root)
                )
                keys = load_frontier_semantic_review_key_set(
                    _resolve(args.private_semantic_keys, root=root)
                )
                ledger = load_frontier_semantic_workflow_ledger(
                    _resolve(args.private_semantic_workflow_ledger, root=root)
                )
                summary = validate_frontier_semantic_workflow_private_opening(
                    ledger=ledger,
                    public_summary=public_workflow,
                    packet_set=packets,
                    key_set=keys,
                    semantic_summary=public_semantic,
                    public_preflight=public_preflight,
                    progress=progress,
                    **workflow_kwargs,
                )
            else:
                summary = semantic_workflow_summary(
                    public_workflow,
                    semantic_summary=public_semantic,
                    public_preflight=public_preflight,
                    progress=progress,
                    **workflow_kwargs,
                )
        elif args.command.endswith("semantic-review"):
            board_protocol = load_frontier_board_protocol(
                _resolve(args.board_protocol, root=root),
                root=root,
                frontier_protocol=protocol,
            )
            board_slots = load_frontier_board_slot_manifest(
                _resolve(args.board_slots, root=root),
                root=root,
                frontier_protocol=protocol,
                board_protocol=board_protocol,
            )
            semantic_kwargs = {
                "root": root,
                "frontier_protocol": protocol,
                "board_protocol": board_protocol,
                "board_slots": board_slots,
            }
            progress = load_frontier_calibration_progress(
                _resolve(args.calibration_progress, root=root),
                **semantic_kwargs,
            )
            public_preflight = load_frontier_public_preflight_summary(
                _resolve(args.preflight_summary, root=root),
                progress=progress,
                **semantic_kwargs,
            )
            public_semantic = load_frontier_semantic_review_summary(
                _resolve(args.semantic_review_summary, root=root),
                public_preflight=public_preflight,
                progress=progress,
                **semantic_kwargs,
            )
            if args.command == "validate-private-semantic-review":
                private_tasks = load_frontier_calibration_task_set(
                    _resolve(args.private_calibration_tasks, root=root),
                    **semantic_kwargs,
                )
                private_oracles = load_frontier_calibration_oracle_set(
                    _resolve(args.private_calibration_oracles, root=root),
                    task_set=private_tasks,
                    **semantic_kwargs,
                )
                private_preflight = load_frontier_private_preflight_report(
                    _resolve(args.private_preflight_report, root=root),
                    task_set=private_tasks,
                    oracle_set=private_oracles,
                    progress=progress,
                    **semantic_kwargs,
                )
                packets = load_frontier_semantic_review_packet_set(
                    _resolve(args.private_semantic_packets, root=root)
                )
                keys = load_frontier_semantic_review_key_set(
                    _resolve(args.private_semantic_keys, root=root)
                )
                summary = validate_frontier_semantic_review_private_opening(
                    packet_set=packets,
                    key_set=keys,
                    public_summary=public_semantic,
                    task_set=private_tasks,
                    oracle_set=private_oracles,
                    private_preflight=private_preflight,
                    public_preflight=public_preflight,
                    progress=progress,
                    **semantic_kwargs,
                )
            else:
                summary = semantic_review_summary(
                    public_semantic,
                    public_preflight=public_preflight,
                    progress=progress,
                    **semantic_kwargs,
                )
        elif args.command.endswith("preflight"):
            board_protocol = load_frontier_board_protocol(
                _resolve(args.board_protocol, root=root),
                root=root,
                frontier_protocol=protocol,
            )
            board_slots = load_frontier_board_slot_manifest(
                _resolve(args.board_slots, root=root),
                root=root,
                frontier_protocol=protocol,
                board_protocol=board_protocol,
            )
            preflight_kwargs = {
                "root": root,
                "frontier_protocol": protocol,
                "board_protocol": board_protocol,
                "board_slots": board_slots,
            }
            progress = load_frontier_calibration_progress(
                _resolve(args.calibration_progress, root=root),
                **preflight_kwargs,
            )
            public_summary = load_frontier_public_preflight_summary(
                _resolve(args.preflight_summary, root=root),
                progress=progress,
                **preflight_kwargs,
            )
            if args.command == "validate-private-preflight":
                private_tasks = load_frontier_calibration_task_set(
                    _resolve(args.private_calibration_tasks, root=root),
                    **preflight_kwargs,
                )
                private_oracles = load_frontier_calibration_oracle_set(
                    _resolve(args.private_calibration_oracles, root=root),
                    task_set=private_tasks,
                    **preflight_kwargs,
                )
                private_report = load_frontier_private_preflight_report(
                    _resolve(args.private_preflight_report, root=root),
                    task_set=private_tasks,
                    oracle_set=private_oracles,
                    progress=progress,
                    **preflight_kwargs,
                )
                summary = validate_frontier_preflight_private_opening(
                    private_report=private_report,
                    public_summary=public_summary,
                    task_set=private_tasks,
                    oracle_set=private_oracles,
                    progress=progress,
                    **preflight_kwargs,
                )
            else:
                summary = frontier_preflight_summary(
                    public_summary,
                    progress=progress,
                    **preflight_kwargs,
                )
        elif args.command.endswith("calibration"):
            board_protocol = load_frontier_board_protocol(
                _resolve(args.board_protocol, root=root),
                root=root,
                frontier_protocol=protocol,
            )
            board_slots = load_frontier_board_slot_manifest(
                _resolve(args.board_slots, root=root),
                root=root,
                frontier_protocol=protocol,
                board_protocol=board_protocol,
            )
            progress = load_frontier_calibration_progress(
                _resolve(args.calibration_progress, root=root),
                root=root,
                frontier_protocol=protocol,
                board_protocol=board_protocol,
                board_slots=board_slots,
            )
            if args.command == "validate-private-calibration":
                private_tasks = load_frontier_calibration_task_set(
                    _resolve(args.private_calibration_tasks, root=root),
                    root=root,
                    frontier_protocol=protocol,
                    board_protocol=board_protocol,
                    board_slots=board_slots,
                )
                private_oracles = load_frontier_calibration_oracle_set(
                    _resolve(args.private_calibration_oracles, root=root),
                    root=root,
                    frontier_protocol=protocol,
                    board_protocol=board_protocol,
                    board_slots=board_slots,
                    task_set=private_tasks,
                )
                summary = validate_frontier_calibration_private_opening(
                    progress=progress,
                    task_set=private_tasks,
                    oracle_set=private_oracles,
                    root=root,
                    frontier_protocol=protocol,
                    board_protocol=board_protocol,
                    board_slots=board_slots,
                )
            else:
                summary = frontier_calibration_progress_summary(
                    progress,
                    root=root,
                    frontier_protocol=protocol,
                    board_protocol=board_protocol,
                    board_slots=board_slots,
                )
        else:
            seeds = load_frontier_seed_manifest(
                _resolve(args.seeds, root=root),
                root=root,
                protocol=protocol,
            )
            tasks = load_frontier_task_set(
                _resolve(args.tasks, root=root),
                root=root,
                protocol=protocol,
                seed_manifest=seeds,
            )
            oracles = load_frontier_oracle_set(
                _resolve(args.oracles, root=root),
                root=root,
                protocol=protocol,
                seed_manifest=seeds,
                task_set=tasks,
            )
            curation = load_frontier_curation_tranche(
                _resolve(args.curation, root=root),
                root=root,
                protocol=protocol,
                seed_manifest=seeds,
                task_set=tasks,
                oracle_set=oracles,
            )
            summary = frontier_development_summary(
                curation,
                root=root,
                protocol=protocol,
                seed_manifest=seeds,
                task_set=tasks,
                oracle_set=oracles,
            )
    except (OSError, FrontierContractError, TypeError, ValueError) as exc:
        print(
            json.dumps(
                {"error": {"code": "invalid_frontier_contract", "message": str(exc)}},
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2

    output = (
        {"valid": True, **summary} if args.command.startswith("validate") else summary
    )
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
