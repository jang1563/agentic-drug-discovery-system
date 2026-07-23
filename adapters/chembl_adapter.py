#!/usr/bin/env python3
"""ChEMBL adapter (callable stage-2 tool).

molecule(chembl_id | name) -> {name, max_phase, type, first_approval}
mechanism(chembl_id)       -> [mechanism_of_action, target]
target(target_id)          -> normalized target identity profile
target_activity_count(target_id) -> int
The first-class tool the discovery flow calls at stage 2 (compound-target evidence).
Cache-first (data/adapter_cache), live REST fallback.
"""
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, "experiments/local/track_b/slice_scd/data/adapter_cache")
os.makedirs(CACHE, exist_ok=True)
BASE = "https://www.ebi.ac.uk/chembl/api/data"
UA = {"User-Agent": "adds/0.1", "Accept": "application/json"}


def _get(url, timeout=30):
    return json.loads(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout).read())


def _cached(key, fn):
    fp = os.path.join(CACHE, f"chembl_{key}.json")
    if os.path.exists(fp):
        try:
            with open(fp) as handle:
                return json.load(handle)
        except Exception:
            pass
    try:
        obj = fn()
        with open(fp, "w") as handle:
            json.dump(obj, handle)
        return obj
    except Exception:
        return None


class ChemblAdapter:
    def molecule(self, chembl_id=None, name=None):
        if chembl_id:
            d = _cached(f"mol_{chembl_id}", lambda: _get(f"{BASE}/molecule/{chembl_id}?format=json"))
        elif name:
            s = _cached(f"molsearch_{name}", lambda: _get(f"{BASE}/molecule/search?q={urllib.parse.quote(name)}&format=json"))
            d = (s.get("molecules") or [None])[0] if s else None
        else:
            return {}
        if not d:
            return {"found": False}
        return {"found": True, "chembl_id": d.get("molecule_chembl_id"), "name": d.get("pref_name"),
                "max_phase": d.get("max_phase"), "type": d.get("molecule_type"),
                "first_approval": d.get("first_approval")}

    def mechanism(self, chembl_id):
        d = _cached(f"mech_{chembl_id}", lambda: _get(f"{BASE}/mechanism?molecule_chembl_id={chembl_id}&format=json"))
        try:
            return [{"moa": m.get("mechanism_of_action"), "target": m.get("target_chembl_id"),
                     "action": m.get("action_type")} for m in d.get("mechanisms", [])]
        except Exception:
            return []

    def target(self, target_id):
        d = _cached(
            f"target_{target_id}",
            lambda: _get(f"{BASE}/target/{target_id}?format=json"),
        )
        if not d:
            return {"found": False, "target_id": target_id}
        gene_symbols = set()
        accessions = set()
        for component in d.get("target_components") or []:
            accession = component.get("accession")
            if isinstance(accession, str) and accession.strip():
                accessions.add(accession.strip())
            for synonym in component.get("component_synonyms") or []:
                if synonym.get("syn_type") != "GENE_SYMBOL":
                    continue
                symbol = synonym.get("component_synonym")
                if isinstance(symbol, str) and symbol.strip():
                    gene_symbols.add(symbol.strip())
        return {
            "found": True,
            "target_id": d.get("target_chembl_id"),
            "preferred_name": d.get("pref_name"),
            "target_type": d.get("target_type"),
            "organism": d.get("organism"),
            "gene_symbols": sorted(gene_symbols),
            "accessions": sorted(accessions),
        }

    def target_activity_count(self, target_id):
        d = _cached(f"actcount_{target_id}",
                    lambda: _get(f"{BASE}/activity?target_chembl_id={target_id}&limit=1&format=json"))
        try:
            return d.get("page_meta", {}).get("total_count")
        except Exception:
            return None


if __name__ == "__main__":
    c = ChemblAdapter()
    print("voxelotor:", c.molecule("CHEMBL4101807"))
    print("mechanism:", c.mechanism("CHEMBL4101807"))
    print("HbA activities:", c.target_activity_count("CHEMBL2095168"))
    print("crizanlizumab (by name):", c.molecule(name="crizanlizumab"))
