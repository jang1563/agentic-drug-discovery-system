"""Command-line validation and compilation for translational handoffs."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from .translational_handoff import (
    TranslationalHandoffError,
    compile_translational_handoff_evidence,
    load_translational_handoff,
    translational_handoff_summary,
)


DEFAULT_HANDOFF = "rl_env/specs/translational_handoff.example.json"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate, summarize, or compile a contextual translational handoff."
    )
    parser.add_argument("command", choices=("validate", "summarize", "compile"))
    parser.add_argument("--handoff", default=DEFAULT_HANDOFF)
    parser.add_argument("--root", default=".")
    parser.add_argument("--request-id", default="translational-handoff-request")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    handoff_path = Path(args.handoff)
    if not handoff_path.is_absolute():
        handoff_path = root / handoff_path
    try:
        handoff = load_translational_handoff(handoff_path)
        summary = translational_handoff_summary(handoff)
        if args.command == "compile":
            drafts = compile_translational_handoff_evidence(
                handoff, request_id=args.request_id
            )
            output = {
                "summary": summary,
                "evidence_drafts": [draft.to_dict() for draft in drafts],
            }
        elif args.command == "validate":
            output = {"valid": True, **summary}
        else:
            output = summary
    except (OSError, TranslationalHandoffError, TypeError, ValueError) as exc:
        print(
            json.dumps(
                {"error": {"code": "invalid_translational_handoff", "message": str(exc)}},
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2

    print(json.dumps(output, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
