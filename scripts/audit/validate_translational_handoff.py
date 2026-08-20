#!/usr/bin/env python3
"""Validate the public synthetic upstream translational handoff."""

from __future__ import annotations

import json
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
from agentic_drug_discovery.clinical_endpoint_mapping import (  # noqa: E402
    clinical_endpoint_mapping_spec_from_dict,
)
from agentic_drug_discovery.clinical_synthesis import (  # noqa: E402
    clinical_synthesis_spec_from_dict,
)


HANDOFFS = (
    ROOT / "rl_env" / "specs" / "translational_handoff.example.json",
    ROOT / "rl_env" / "specs" / "translational_handoff.uc.synthetic.example.json",
)
UC_MAPPING = (
    ROOT
    / "rl_env"
    / "specs"
    / "clinical_endpoint_mapping.uc.synthetic.example.json"
)
UC_SYNTHESIS = (
    ROOT
    / "rl_env"
    / "specs"
    / "clinical_benefit_risk_synthesis.uc.synthetic.example.json"
)


def main() -> int:
    try:
        handoffs = tuple(load_translational_handoff(path) for path in HANDOFFS)
        summaries = tuple(translational_handoff_summary(item) for item in handoffs)
        drafts = tuple(
            draft
            for index, handoff in enumerate(handoffs)
            for draft in compile_translational_handoff_evidence(
                handoff,
                request_id=f"release-audit-translational-handoff-{index}",
            )
        )
        mapping = clinical_endpoint_mapping_spec_from_dict(
            json.loads(UC_MAPPING.read_text(encoding="utf-8"))
        )
        synthesis = clinical_synthesis_spec_from_dict(
            json.loads(UC_SYNTHESIS.read_text(encoding="utf-8"))
        )
    except (OSError, TranslationalHandoffError, TypeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    if any(item.relation.value != "contextualizes" for item in drafts):
        print("ERROR: translational handoff emitted non-contextual evidence", file=sys.stderr)
        return 1
    uc_handoff = handoffs[1]
    if {
        uc_handoff["program"]["disease_id"],
        mapping.disease_id,
        synthesis.disease_id,
    } != {"MONDO:0005101"}:
        print("ERROR: UC conformance disease identity is not continuous", file=sys.stderr)
        return 1
    if (
        mapping.mapping_id != synthesis.endpoint_mapping_id
        or mapping.endpoint_family_id != synthesis.endpoint_family
        or mapping.effect_measure != synthesis.effect_measure
        or mapping.favorable_direction != synthesis.effect_measure_favorable_direction
    ):
        print("ERROR: UC clinical conformance dimensions are not continuous", file=sys.stderr)
        return 1
    print(
        "PASS: translational handoffs and UC clinical conformance validated "
        f"({len(handoffs)} diseases, "
        f"{sum(item['source_count'] for item in summaries)} sources, "
        f"{sum(item['observation_count'] for item in summaries)} observations, "
        "contextual-only upstream)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
