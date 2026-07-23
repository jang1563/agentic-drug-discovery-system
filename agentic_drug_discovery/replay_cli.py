"""Command-line entry point for strict decision-bundle replay."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

from .serialization import RecordParseError, replay_bundle_from_json, replay_program


def _summary(report, *, full_state: bool) -> dict[str, Any]:
    final_state: dict[str, Any]
    if full_state:
        final_state = report.final_state.to_dict()
    else:
        state = report.final_state
        final_state = {
            "program_id": state.program_id,
            "version": state.version,
            "stage": state.current_stage.value,
            "status": state.status.value,
            "evidence_count": len(state.evidence),
            "claim_count": len(state.claims),
            "candidate_count": len(state.candidates),
            "action_count": len(state.action_history),
            "budget_spent": state.budget.spent,
            "budget_remaining": state.budget.remaining,
        }
    return {
        "schema_version": 1,
        "accepted_count": report.accepted_count,
        "blocked_count": report.blocked_count,
        "attempted_packet_count": len(report.attempted_packets),
        "stopped_on_block": report.stopped_on_block,
        "final_state": final_state,
        "transitions": [
            {
                "packet_id": result.packet.packet_id,
                "stage": result.packet.stage.value,
                "decision": result.packet.decision.value,
                "applied": result.applied,
                "reason": result.reason,
                "blocking_codes": [item.code for item in result.blocking_results],
                "state_version_after": result.state.version,
                "stage_after": result.state.current_stage.value,
                "status_after": result.state.status.value,
            }
            for result in report.results
        ],
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Replay a version-1 Agentic Drug Discovery decision bundle."
    )
    parser.add_argument(
        "bundle",
        nargs="?",
        default="-",
        help="Replay bundle JSON path, or '-' to read stdin (default).",
    )
    parser.add_argument(
        "--continue-after-block",
        action="store_true",
        help="Attempt later packets after a blocking transition.",
    )
    parser.add_argument(
        "--full-state",
        action="store_true",
        help="Include the full final ProgramState instead of a compact summary.",
    )
    args = parser.parse_args(argv)

    try:
        text = (
            sys.stdin.read()
            if args.bundle == "-"
            else Path(args.bundle).read_text("utf-8")
        )
        bundle = replay_bundle_from_json(text)
        report = replay_program(
            bundle,
            stop_on_block=not args.continue_after_block,
        )
    except (OSError, RecordParseError, TypeError, ValueError) as exc:
        error = {
            "error": {
                "code": "invalid_replay_bundle",
                "message": str(exc),
            }
        }
        print(json.dumps(error, sort_keys=True), file=sys.stderr)
        return 2

    print(
        json.dumps(
            _summary(report, full_state=args.full_state), indent=2, sort_keys=True
        )
    )
    return 0 if report.blocked_count == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
