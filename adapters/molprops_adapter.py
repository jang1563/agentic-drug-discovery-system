#!/usr/bin/env python3
"""Local molecular-property adapter for the compound-design stage.

`MolPropsAdapter.properties(spec)` accepts a SMILES string, ChEMBL identifier, or
drug name. When RDKit is installed, it returns QED, molecular weight, logP,
H-bond donor/acceptor counts, Lipinski violations, and a coarse druglikeness
verdict. Name and ChEMBL-id inputs are resolved through the public ChEMBL API.

The adapter is intentionally a property screen, not a binding-affinity model.
Use `boltz2` for GPU-backed structural/binding predictions.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from urllib.parse import quote
from urllib.request import urlopen


CHEMBL_API = "https://www.ebi.ac.uk/chembl/api/data"
DEFAULT_TIMEOUT_SECONDS = 25


def _read_json(url: str, timeout: int = DEFAULT_TIMEOUT_SECONDS) -> dict:
    with urlopen(url, timeout=timeout) as response:  # noqa: S310 - public ChEMBL endpoint.
        return json.loads(response.read())


def _smiles_from_chembl(spec: str) -> str | None:
    """Resolve a ChEMBL id or drug name to canonical SMILES."""

    query = spec.strip()
    if not query:
        return None
    try:
        if query.upper().startswith("CHEMBL"):
            data = _read_json(f"{CHEMBL_API}/molecule/{quote(query)}?format=json")
        else:
            search = _read_json(f"{CHEMBL_API}/molecule/search?q={quote(query)}&format=json")
            data = (search.get("molecules") or [None])[0] or {}
        return ((data or {}).get("molecule_structures") or {}).get("canonical_smiles")
    except Exception:
        return None


@dataclass(frozen=True)
class MolPropsResult:
    smiles: str
    qed: float
    molecular_weight: float
    logp: float
    hbd: int
    hba: int
    lipinski_violations: int
    verdict: str

    def render(self) -> str:
        clipped = self.smiles[:40]
        return (
            f"molprops [{clipped}]: QED={self.qed:.2f} MW={self.molecular_weight:.0f} "
            f"logP={self.logp:.2f} HBD={self.hbd} HBA={self.hba} "
            f"Lipinski_violations={self.lipinski_violations} -> {self.verdict} "
            "(RDKit, local CPU; NOT binding affinity - use boltz2 for that)"
        )


class MolPropsAdapter:
    """RDKit-backed local property screen with a fail-closed unavailable mode."""

    name = "molprops"

    def __init__(self, chembl=None):
        self.chembl = chembl
        try:
            from rdkit import Chem, RDLogger  # noqa: F401

            RDLogger.DisableLog("rdApp.*")
            self.ok = True
        except Exception:
            self.ok = False

    def properties(self, spec: str) -> str:
        result = self.compute(spec)
        return result.render() if result else self._unavailable_message(spec)

    def compute(self, spec: str) -> MolPropsResult | None:
        if not self.ok:
            return None

        from rdkit import Chem
        from rdkit.Chem import Descriptors, Lipinski, QED

        query = (spec or "").strip()
        mol = Chem.MolFromSmiles(query)
        smiles = query
        if mol is None:
            smiles = _smiles_from_chembl(query) or ""
            mol = Chem.MolFromSmiles(smiles) if smiles else None
        if mol is None:
            return None

        molecular_weight = Descriptors.MolWt(mol)
        logp = Descriptors.MolLogP(mol)
        hbd = Lipinski.NumHDonors(mol)
        hba = Lipinski.NumHAcceptors(mol)
        violations = sum([molecular_weight > 500, logp > 5, hbd > 5, hba > 10])
        qed = QED.qed(mol)
        if qed >= 0.5 and violations <= 1:
            verdict = "drug-like"
        elif violations <= 1:
            verdict = "borderline"
        else:
            verdict = "poor druglikeness"

        return MolPropsResult(
            smiles=smiles,
            qed=qed,
            molecular_weight=molecular_weight,
            logp=logp,
            hbd=hbd,
            hba=hba,
            lipinski_violations=violations,
            verdict=verdict,
        )

    def _unavailable_message(self, spec: str) -> str:
        query = (spec or "").strip()
        if not self.ok:
            return "molprops UNAVAILABLE: RDKit not installed"
        return f"molprops: could not resolve '{query}' to a structure (give a SMILES or ChEMBL id)"


def main(argv: list[str]) -> int:
    adapter = MolPropsAdapter()
    examples = argv[1:] or ["CC(=O)Nc1ccc(O)cc1", "voxelotor", "CHEMBL4101807"]
    for example in examples:
        print(adapter.properties(example))
    return 0


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    raise SystemExit(main(sys.argv))
