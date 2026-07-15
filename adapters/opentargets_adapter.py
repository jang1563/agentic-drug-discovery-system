#!/usr/bin/env python3
"""Open Targets Platform adapter (callable stage-1 tool).

disease_profile(disease_efo) -> resolved disease identity and page-load metadata.
target_disease_association(symbol, disease_efo) -> target identity plus association
{score, datatypes, rank} or an
explicit unresolved/not-in-loaded-page record. Cache-first: fetches a large associatedTargets page
for the disease once (cached), then symbol lookups are free. This is the first-class tool
the discovery flow calls at stage 1 (replaces reading pre-baked raw).
"""
from __future__ import annotations

import json
import os
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, "experiments/local/track_b/slice_scd/data/adapter_cache")
os.makedirs(CACHE, exist_ok=True)
API = "https://api.platform.opentargets.org/api/v4/graphql"
UA = {"User-Agent": "adds/0.1", "content-type": "application/json"}

_Q = ('{disease(efoId:"%s"){id name associatedTargets(page:{index:0,size:%d}){count '
      'rows{target{id approvedSymbol} score datatypeScores{id score}}}}}')


class OpenTargetsAdapter:
    def __init__(self, disease_efo="MONDO_0011382", size=500, live=True):
        self.efo, self.live = disease_efo, live
        self.map, self.disease_name = {}, disease_efo
        self.loaded, self.total_count, self.loaded_count = False, None, 0
        fp = os.path.join(CACHE, f"ot_assoc_{disease_efo}.json")
        data = None
        if os.path.exists(fp):
            try:
                with open(fp) as handle:
                    data = json.load(handle)
            except Exception:
                data = None
        if data is None and live:
            try:
                req = urllib.request.Request(API, headers=UA,
                    data=json.dumps({"query": _Q % (disease_efo, size)}).encode())
                data = json.loads(urllib.request.urlopen(req, timeout=30).read())
                json.dump(data, open(fp, "w"))
            except Exception:
                data = None
        try:
            dd = data["data"]["disease"]
            self.disease_name = dd["name"]
            association_page = dd["associatedTargets"]
            rows = association_page["rows"]
            self.total_count = association_page.get("count")
            self.loaded_count = len(rows)
            self.loaded = True
            for i, r in enumerate(rows, 1):
                self.map[r["target"]["approvedSymbol"].upper()] = {
                    "target_id": r["target"]["id"],
                    "symbol": r["target"]["approvedSymbol"],
                    "score": round(r["score"], 3), "rank": i,
                    "datatypes": {x["id"]: round(x["score"], 3) for x in (r.get("datatypeScores") or [])}}
        except Exception:
            pass

    def disease_profile(self, disease_efo=None):
        requested_efo = disease_efo or self.efo
        if requested_efo != self.efo:
            return {
                "disease_efo": requested_efo,
                "initialized_disease_efo": self.efo,
                "disease": self.disease_name,
                "resolved": False,
                "evidence_status": "adapter_disease_mismatch",
                "note": "Requested disease does not match the initialized adapter dataset",
            }
        if not self.loaded:
            return {
                "disease_efo": self.efo,
                "disease": self.disease_name,
                "resolved": False,
                "evidence_status": "dataset_unavailable",
                "loaded_targets": 0,
                "total_associated_targets": self.total_count,
                "page_complete": False,
                "note": "Open Targets disease data unavailable; context remains unresolved",
            }
        page_complete = (
            self.total_count is not None and self.total_count <= self.loaded_count
        )
        return {
            "disease_efo": self.efo,
            "disease": self.disease_name,
            "resolved": True,
            "evidence_status": "resolved",
            "loaded_targets": self.loaded_count,
            "total_associated_targets": self.total_count,
            "page_complete": page_complete,
        }

    def target_disease_association(self, symbol, disease_efo=None):
        if disease_efo is not None and disease_efo != self.efo:
            return {
                "target": symbol,
                "disease": self.disease_name,
                "found": False,
                "score": None,
                "evidence_status": "adapter_disease_mismatch",
                "requested_disease_efo": disease_efo,
                "initialized_disease_efo": self.efo,
                "conclusive_absence": False,
                "note": "Requested disease does not match the initialized adapter dataset",
            }
        rec = self.map.get((symbol or "").upper())
        if rec:
            return {
                "target": rec["symbol"],
                "target_id": rec["target_id"],
                "disease": self.disease_name,
                "disease_efo": self.efo,
                "organism": "Homo sapiens",
                "found": True,
                "score": rec["score"],
                "rank": rec["rank"],
                "datatypes": rec["datatypes"],
            }
        if not self.loaded:
            return {"target": symbol, "disease": self.disease_name,
                    "disease_efo": self.efo, "organism": "Homo sapiens", "found": False,
                    "score": None, "evidence_status": "dataset_unavailable",
                    "conclusive_absence": False,
                    "note": "Open Targets data unavailable; association status unresolved"}
        page_complete = self.total_count is not None and self.total_count <= self.loaded_count
        return {"target": symbol, "disease": self.disease_name,
                "disease_efo": self.efo, "organism": "Homo sapiens", "found": False,
                "score": None, "evidence_status": "not_found_in_loaded_page",
                "conclusive_absence": False, "loaded_targets": self.loaded_count,
                "total_associated_targets": self.total_count, "page_complete": page_complete,
                "note": (f"{symbol} was not found in the loaded Open Targets association page; "
                         "do not infer weak/absent evidence without checking pagination and source freshness")}


if __name__ == "__main__":
    a = OpenTargetsAdapter()
    print("disease:", a.disease_name, "| targets loaded:", len(a.map))
    for s in ("HBB", "SELP", "BCL11A", "KCNN4", "SELPLG", "SELE"):
        r = a.target_disease_association(s)
        print(f"  {s}: score={r['score']} found={r['found']} {r.get('datatypes','')}")
