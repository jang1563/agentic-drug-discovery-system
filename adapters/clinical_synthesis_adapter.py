"""Local adapter for reviewed endpoint mappings and cross-trial synthesis."""

from __future__ import annotations

from typing import Any

from agentic_drug_discovery.clinical_endpoint_mapping import (
    clinical_endpoint_mapping_spec_from_dict,
    clinical_endpoint_mapping_spec_to_dict,
)
from agentic_drug_discovery.clinical_synthesis import (
    clinical_synthesis_spec_from_dict,
    clinical_synthesis_spec_to_dict,
)


class ClinicalSynthesisAdapter:
    """Normalize reviewed mapping and synthesis specs without retrieving data."""

    def register_endpoint_mapping(self, spec: Any) -> dict[str, Any]:
        parsed = clinical_endpoint_mapping_spec_from_dict(spec)
        return clinical_endpoint_mapping_spec_to_dict(parsed)

    def harmonize_benefit_risk(self, spec: Any) -> dict[str, Any]:
        parsed = clinical_synthesis_spec_from_dict(spec)
        return clinical_synthesis_spec_to_dict(parsed)
