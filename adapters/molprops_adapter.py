#!/usr/bin/env python3
"""Molecular-property adapter (callable compound-design tool) — a REAL, locally-runnable
SFM-ish signal via RDKit (no GPU needed). Gives the compound-design stage a computable
druglikeness read (QED, MW, logP, H-bond donors/acceptors, Lipinski violations) so the SFM
leg is not entirely a stub while Boltz-2 (binding affinity / structure) stays GPU-gated.

properties(spec): spec is a SMILES, or a ChEMBL id / drug name (resolved to canonical SMILES
via ChEMBL). Returns a druglikeness verdict + the values.
"""
from __future__ import annotations
import os, json, urllib.request, urllib.parse

CHEMBL = "https://www.ebi.ac.uk/chembl/api/data"


def _smiles_from_chembl(spec):
    try:
        if spec.upper().startswith("CHEMBL"):
            url = f"{CHEMBL}/molecule/{spec}?format=json"
            d = json.loads(urllib.request.urlopen(url, timeout=25).read())
        else:
            url = f"{CHEMBL}/molecule/search?q={urllib.parse.quote(spec)}&format=json"
            d = (json.loads(urllib.request.urlopen(url, timeout=25).read()).get("molecules") or [None])[0]
        return ((d or {}).get("molecule_structures") or {}).get("canonical_smiles")
    except Exception:
        return None


class MolPropsAdapter:
    name = "molprops"

    def __init__(self, chembl=None):
        self.chembl = chembl
        try:
            from rdkit import Chem, RDLogger  # noqa
            RDLogger.DisableLog("rdApp.*")  # silence expected parse warnings on name->SMILES fallback
            self.ok = True
        except Exception:
            self.ok = False

    def properties(self, spec):
        if not self.ok:
            return "molprops UNAVAILABLE: RDKit not installed"
        from rdkit import Chem
        from rdkit.Chem import QED, Descriptors, Lipinski
        spec = (spec or "").strip()
        mol = Chem.MolFromSmiles(spec)
        smiles = spec
        if mol is None:  # not a SMILES -> resolve a ChEMBL id / drug name
            smiles = _smiles_from_chembl(spec)
            mol = Chem.MolFromSmiles(smiles) if smiles else None
        if mol is None:
            return f"molprops: could not resolve '{spec}' to a structure (give a SMILES or ChEMBL id)"
        qed = QED.qed(mol)
        mw, logp = Descriptors.MolWt(mol), Descriptors.MolLogP(mol)
        hbd, hba = Lipinski.NumHDonors(mol), Lipinski.NumHAcceptors(mol)
        viol = sum([mw > 500, logp > 5, hbd > 5, hba > 10])
        verdict = "drug-like" if (qed >= 0.5 and viol <= 1) else ("borderline" if viol <= 1 else "poor druglikeness")
        return (f"molprops [{smiles[:40]}]: QED={qed:.2f} MW={mw:.0f} logP={logp:.2f} HBD={hbd} HBA={hba} "
                f"Lipinski_violations={viol} -> {verdict} (RDKit, local CPU; NOT binding affinity — use boltz2 for that)")


if __name__ == "__main__":
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    a = MolPropsAdapter()
    print(a.properties("CC(=O)Nc1ccc(O)cc1"))     # acetaminophen (SMILES)
    print(a.properties("voxelotor"))               # by name -> ChEMBL SMILES
    print(a.properties("CHEMBL4101807"))           # by ChEMBL id
