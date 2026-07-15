#!/usr/bin/env python3
"""Boltz-2 SFM adapter (callable stage-2/compound-design tool) - predicted binding affinity
+ structure confidence for a target-ligand pair.

Boltz-2 real inference needs a configured GPU service - it does NOT run in this local
env. So this adapter is honest and tiered:
  1. If BOLTZ_ENDPOINT is set -> POST {target, ligand} to a real Boltz-2 service.
  2. Else if the ligand is a KNOWN ChEMBL molecule (max_phase>=1) -> return a ChEMBL
     development-stage/mechanism metadata proxy, noting it is NOT a Boltz prediction
     and does not validate target engagement.
  3. Else (de-novo candidate) -> return unavailable with the GPU requirement, so the flow
     degrades gracefully and an agent knows to defer / route to compute.

This wires the SFM into the flow architecture; swap in a live Boltz-2 endpoint to activate it.
"""

from __future__ import annotations

import json
import os
import urllib.request

ENDPOINT = os.environ.get("BOLTZ_ENDPOINT")  # e.g. a Boltz-2 service endpoint


class BoltzAdapter:
    name = "boltz2"

    def __init__(self, chembl=None):
        self.chembl = chembl
        self.endpoint = ENDPOINT

    def predict_binding_record(self, spec):
        """Return a structured prediction status without exposing endpoint errors."""

        target, _, ligand = (spec or "").partition("|")
        target, ligand = target.strip(), ligand.strip()
        if not target or not ligand:
            return {
                "status": "invalid_input",
                "reason": "expected_target_ligand",
            }

        # 1) real Boltz-2 service
        if self.endpoint:
            try:
                req = urllib.request.Request(
                    self.endpoint,
                    headers={"content-type": "application/json"},
                    data=json.dumps({"target": target, "ligand": ligand}).encode(),
                )
                r = json.loads(urllib.request.urlopen(req, timeout=120).read())
                return {
                    "status": "predicted",
                    "target": target,
                    "ligand": ligand,
                    "affinity": r.get("affinity"),
                    "affinity_units": r.get("affinity_units") or r.get("units"),
                    "confidence": r.get("confidence"),
                    "iptm": r.get("iptm"),
                    "source_kind": "boltz2_live",
                }

            except Exception:
                return {"status": "endpoint_error"}

        # 2) known-drug experimental proxy via ChEMBL
        if self.chembl:
            m = self.chembl.molecule(
                chembl_id=ligand if ligand.upper().startswith("CHEMBL") else None,
                name=None if ligand.upper().startswith("CHEMBL") else ligand,
            )
            if m and m.get("found") and (m.get("max_phase") or 0):
                mech = (
                    self.chembl.mechanism(m.get("chembl_id"))
                    if m.get("chembl_id")
                    else []
                )
                return {
                    "status": "proxy_only",
                    "reason": "gpu_required",
                    "target": target,
                    "ligand": ligand,
                    "chembl_id": m.get("chembl_id"),
                    "name": m.get("name"),
                    "max_phase": m.get("max_phase"),
                    "mechanism_count": len(mech),
                }

        # 3) de-novo candidate -> route to compute
        return {
            "status": "unavailable",
            "reason": "gpu_required",
            "target": target,
            "ligand": ligand,
        }

    def predict_binding(self, spec):
        """Render the structured result for legacy flow callers."""

        record = self.predict_binding_record(spec)
        status = record["status"]
        if status == "predicted":
            units = record.get("affinity_units") or "service-defined units"
            return (
                f"Boltz-2 [{record['target']} + {record['ligand']}]: service-defined "
                f"affinity {record.get('affinity')} {units} "
                f"(confidence {record.get('confidence')}); ipTM {record.get('iptm')}. "
                "source=boltz2_live"
            )
        if status == "proxy_only":
            return (
                "boltz2 UNAVAILABLE locally (needs GPU). PROXY: "
                f"{record.get('name')} has ChEMBL development-stage/mechanism metadata "
                f"(max_phase {record.get('max_phase')}, mechanism_count "
                f"{record.get('mechanism_count')}). This is not a Boltz prediction and "
                "does not validate target engagement."
            )
        if status == "invalid_input":
            return "boltz2: expected 'TARGET|LIGAND' (ligand = SMILES, ChEMBL id, or drug name)"
        if status == "endpoint_error":
            return "boltz2: endpoint error (details redacted)"
        return (
            "boltz2 UNAVAILABLE: de-novo binding-affinity/structure requires Boltz-2 "
            "on a GPU backend or a configured BOLTZ_ENDPOINT. Degrade: defer or route "
            "to compute."
        )


if __name__ == "__main__":
    import sys

    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from adapters.chembl_adapter import ChemblAdapter

    b = BoltzAdapter(ChemblAdapter())
    print("known drug:", b.predict_binding("HBB|voxelotor"))
    print("de-novo:", b.predict_binding("HBB|CC(=O)Nc1ccc(O)cc1"))
    print("endpoint set?", bool(ENDPOINT))
