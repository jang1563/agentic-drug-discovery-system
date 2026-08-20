#!/usr/bin/env python3
"""Validate the public synthetic upstream translational handoff."""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agentic_drug_discovery.translational_handoff import (  # noqa: E402
    TranslationalHandoffError,
    compile_translational_handoff_evidence,
    load_translational_handoff,
    translational_handoff_summary,
)


HANDOFF = ROOT / "rl_env" / "specs" / "translational_handoff.example.json"


def main() -> int:
    try:
        handoff = load_translational_handoff(HANDOFF)
        summary = translational_handoff_summary(handoff)
        drafts = compile_translational_handoff_evidence(
            handoff, request_id="release-audit-translational-handoff"
        )
    except (OSError, TranslationalHandoffError, TypeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    if any(item.relation.value != "contextualizes" for item in drafts):
        print("ERROR: translational handoff emitted non-contextual evidence", file=sys.stderr)
        return 1
    print(
        "PASS: translational handoff validated "
        f"({summary['source_count']} sources, "
        f"{summary['observation_count']} observations, contextual-only)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
