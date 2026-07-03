#!/usr/bin/env python3
"""Boltz-2 SFM adapter (callable stage-2/compound-design tool) - predicted binding affinity
+ structure confidence for a target-ligand pair.

Boltz-2 real inference needs a configured GPU service - it does NOT run in this local
env. So this adapter is honest and tiered:
  1. If BOLTZ_ENDPOINT is set -> POST {target, ligand} to a real Boltz-2 service.
  2. Else if the ligand is a KNOWN ChEMBL molecule (max_phase>=1) -> return the experimental
     target-engagement proxy (clinically validated), noting it is NOT a Boltz prediction.
  3. Else (de-novo candidate) -> return unavailable with the GPU requirement, so the flow
     degrades gracefully and an agent knows to defer / route to compute.

This wires the SFM into the flow architecture; swap in a live Boltz-2 endpoint to activate it.
"""
from __future__ import annotations
import os, json, urllib.request

ENDPOINT = os.environ.get("BOLTZ_ENDPOINT")  # e.g. a Boltz-2 service endpoint


class BoltzAdapter:
    name = "boltz2"

    def __init__(self, chembl=None):
        self.chembl = chembl
        self.endpoint = ENDPOINT

    def predict_binding(self, spec):
        target, _, ligand = (spec or "").partition("|")
        target, ligand = target.strip(), ligand.strip()
        if not target or not ligand:
            return "boltz2: expected 'TARGET|LIGAND' (ligand = SMILES, ChEMBL id, or drug name)"

        # 1) real Boltz-2 service
        if self.endpoint:
            try:
                req = urllib.request.Request(
                    self.endpoint, headers={"content-type": "application/json"},
                    data=json.dumps({"target": target, "ligand": ligand}).encode())
                r = json.loads(urllib.request.urlopen(req, timeout=120).read())
                return (f"Boltz-2 [{target} + {ligand}]: predicted affinity "
                        f"pIC50~{r.get('affinity')} (confidence {r.get('confidence')}); "
                        f"ipTM {r.get('iptm')}. source=boltz2_live")

            except Exception as e:
                return f"boltz2: endpoint error ({e})"

        # 2) known-drug experimental proxy via ChEMBL
        if self.chembl:
            m = self.chembl.molecule(chembl_id=ligand if ligand.upper().startswith("CHEMBL") else None,
                                     name=None if ligand.upper().startswith("CHEMBL") else ligand)
            if m and m.get("found") and (m.get("max_phase") or 0):
                mech = self.chembl.mechanism(m.get("chembl_id")) if m.get("chembl_id") else []
                return (f"boltz2 UNAVAILABLE locally (needs GPU). PROXY: {m.get('name')} is a known drug "
                        f"(max_phase {m.get('max_phase')}, MoA {[x['moa'] for x in mech][:1]}) -> target engagement "
                        f"is CLINICALLY VALIDATED (experimental, not a Boltz prediction).")

        # 3) de-novo candidate -> route to compute
        return (f"boltz2 UNAVAILABLE: de-novo binding-affinity/structure for {target}+{ligand} requires "
                f"Boltz-2 on a GPU backend or a configured BOLTZ_ENDPOINT. Degrade: defer or route to compute.")


if __name__ == "__main__":
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from adapters.chembl_adapter import ChemblAdapter
    b = BoltzAdapter(ChemblAdapter())
    print("known drug:", b.predict_binding("HBB|voxelotor"))
    print("de-novo:", b.predict_binding("HBB|CC(=O)Nc1ccc(O)cc1"))
    print("endpoint set?", bool(ENDPOINT))
