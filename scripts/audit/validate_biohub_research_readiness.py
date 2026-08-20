#!/usr/bin/env python3
"""Validate the collaborator-facing Biohub research-readiness packet."""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agentic_drug_discovery.research_readiness import (  # noqa: E402
    ResearchReadinessError,
    load_research_readiness_profile,
    research_readiness_summary,
)


PROFILE = ROOT / "docs" / "biohub_research_readiness.json"


def main() -> int:
    try:
        profile = load_research_readiness_profile(PROFILE, root=ROOT)
        summary = research_readiness_summary(profile, root=ROOT)
    except (OSError, ResearchReadinessError, TypeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(
        "PASS: Biohub research-readiness profile validated "
        f"({summary['evidence_anchor_count']} anchors, "
        f"{summary['presentation_slide_count']} slides, "
        f"{summary['acceptance_gate_count']} pilot gates)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
