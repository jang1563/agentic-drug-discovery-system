#!/usr/bin/env python3
"""Read source-pinned evidence records for composite discovery-stage gates.

The adapter stores no scientific source payloads. It validates a compact public
manifest containing source identifiers, versions, locators, content hashes, dates,
and typed summaries that can be independently audited by a caller.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from agentic_drug_discovery.pinned_evidence import (
    CANDIDATE_TARGET_FUNCTION,
    CLINICAL_PRIMARY_ENDPOINT_NOT_MET,
    CLINICAL_TRIAL_DESIGN,
    CLINICAL_TRIAL_TERMINATION,
    DISEASE_BURDEN,
    DISEASE_MODEL_EFFECT,
    PINNED_EVIDENCE_PREDICATES,
    PINNED_EVIDENCE_SCHEMA_VERSION,
    TREATMENT_GAP,
    normalize_pinned_evidence_manifest,
)

SCHEMA_VERSION = PINNED_EVIDENCE_SCHEMA_VERSION
ALLOWED_PREDICATES = PINNED_EVIDENCE_PREDICATES


def _text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


def _normalized(value: str) -> str:
    return " ".join(value.casefold().split())


class PinnedEvidenceAdapter:
    """Query a validated, source-pinned evidence manifest by exact identities."""

    def __init__(self, manifest: Mapping[str, Any]):
        value = normalize_pinned_evidence_manifest(manifest)
        self.records = tuple(value["records"])

    @classmethod
    def from_json(cls, path: str | Path) -> PinnedEvidenceAdapter:
        source = Path(path)
        try:
            manifest = json.loads(source.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(
                f"could not load pinned evidence manifest: {source}"
            ) from exc
        return cls(manifest)

    @staticmethod
    def _matches(record: Mapping[str, Any], **identities: str) -> bool:
        context = record["biological_context"]
        return all(
            isinstance(context.get(key), str)
            and _normalized(context[key]) == _normalized(value)
            for key, value in identities.items()
        )

    def _profile(
        self,
        *,
        query: Mapping[str, str],
        required: Mapping[str, Mapping[str, str]],
    ) -> dict[str, Any]:
        selected: list[dict[str, Any]] = []
        missing: list[str] = []
        duplicates: list[str] = []
        for predicate, identities in required.items():
            matches = [
                record
                for record in self.records
                if record["predicate"] == predicate
                and self._matches(record, **dict(identities))
            ]
            if not matches:
                missing.append(predicate)
            elif len(matches) > 1:
                duplicates.append(predicate)
                selected.extend(matches)
            else:
                selected.append(matches[0])
        status = "resolved"
        if duplicates:
            status = "ambiguous"
        elif missing:
            status = "incomplete"
        return {
            "schema_version": SCHEMA_VERSION,
            "status": status,
            "query": dict(query),
            "required_predicates": list(required),
            "missing_predicates": missing,
            "duplicate_predicates": duplicates,
            "records": selected,
        }

    def disease_unmet_need(self, disease_id: str) -> dict[str, Any]:
        disease_id = _text(disease_id, "disease_id")
        return self._profile(
            query={"disease_id": disease_id},
            required={
                DISEASE_BURDEN: {"disease_id": disease_id},
                TREATMENT_GAP: {"disease_id": disease_id},
            },
        )

    def candidate_functional_effect(
        self,
        candidate_id: str,
        target_id: str,
        disease_id: str,
    ) -> dict[str, Any]:
        candidate_id = _text(candidate_id, "candidate_id")
        target_id = _text(target_id, "target_id")
        disease_id = _text(disease_id, "disease_id")
        return self._profile(
            query={
                "candidate_id": candidate_id,
                "target_id": target_id,
                "disease_id": disease_id,
            },
            required={
                CANDIDATE_TARGET_FUNCTION: {
                    "candidate_id": candidate_id,
                    "target_id": target_id,
                },
                DISEASE_MODEL_EFFECT: {
                    "candidate_id": candidate_id,
                    "disease_id": disease_id,
                },
            },
        )

    def clinical_trial_design(
        self,
        candidate_id: str,
        disease_id: str,
        trial_id: str,
    ) -> dict[str, Any]:
        candidate_id = _text(candidate_id, "candidate_id")
        disease_id = _text(disease_id, "disease_id")
        trial_id = _text(trial_id, "trial_id")
        query = {
            "candidate_id": candidate_id,
            "disease_id": disease_id,
            "trial_id": trial_id,
        }
        return self._profile(
            query=query,
            required={CLINICAL_TRIAL_DESIGN: query},
        )

    def clinical_trial_disposition(
        self,
        candidate_id: str,
        disease_id: str,
        trial_id: str,
    ) -> dict[str, Any]:
        candidate_id = _text(candidate_id, "candidate_id")
        disease_id = _text(disease_id, "disease_id")
        trial_id = _text(trial_id, "trial_id")
        query = {
            "candidate_id": candidate_id,
            "disease_id": disease_id,
            "trial_id": trial_id,
        }
        return self._profile(
            query=query,
            required={
                CLINICAL_TRIAL_TERMINATION: query,
                CLINICAL_PRIMARY_ENDPOINT_NOT_MET: query,
            },
        )

    def stats(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "record_count": len(self.records),
            "predicates": sorted({record["predicate"] for record in self.records}),
        }
