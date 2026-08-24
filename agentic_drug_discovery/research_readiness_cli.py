"""Command-line validation for collaborator-facing research-readiness profiles."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from .research_readiness import (
    ResearchReadinessError,
    load_research_readiness_profile,
    research_readiness_summary,
)


DEFAULT_PROFILE = "docs/biohub_research_readiness.json"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate or summarize a strict Biohub-context research profile."
    )
    parser.add_argument("command", choices=("validate", "summarize"))
    parser.add_argument("--profile", default=DEFAULT_PROFILE)
    parser.add_argument("--root", default=".")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    profile_path = Path(args.profile)
    if not profile_path.is_absolute():
        profile_path = root / profile_path
    try:
        profile = load_research_readiness_profile(profile_path, root=root)
        summary = research_readiness_summary(profile, root=root)
    except (OSError, ResearchReadinessError, TypeError, ValueError) as exc:
        print(
            json.dumps(
                {"error": {"code": "invalid_research_readiness_profile", "message": str(exc)}},
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2

    if args.command == "validate":
        output = {"valid": True, **summary}
    else:
        output = summary
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
