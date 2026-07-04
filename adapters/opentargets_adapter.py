#!/usr/bin/env python3
"""Open Targets Platform adapter (callable stage-1 tool).

target_disease_association(symbol, disease_efo) -> {score, datatypes, rank} or a
'no significant association' record. Cache-first: fetches a large associatedTargets page
for the disease once (cached), then symbol lookups are free. This is the first-class tool
the discovery flow calls at stage 1 (replaces reading pre-baked raw).
"""
from __future__ import annotations
import os, json, urllib.request

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
        fp = os.path.join(CACHE, f"ot_assoc_{disease_efo}.json")
        data = None
        if os.path.exists(fp):
            try: data = json.load(open(fp))
            except Exception: data = None
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
            for i, r in enumerate(dd["associatedTargets"]["rows"], 1):
                self.map[r["target"]["approvedSymbol"].upper()] = {
                    "score": round(r["score"], 3), "rank": i,
                    "datatypes": {x["id"]: round(x["score"], 3) for x in (r.get("datatypeScores") or [])}}
        except Exception:
            pass

    def target_disease_association(self, symbol, disease_efo=None):
        rec = self.map.get((symbol or "").upper())
        if rec:
            return {"target": symbol, "disease": self.disease_name, "found": True, **rec}
        return {"target": symbol, "disease": self.disease_name, "found": False, "score": 0.0,
                "note": f"{symbol} is not among the top associated targets for {self.disease_name} (weak/absent human genetic-disease evidence)"}


if __name__ == "__main__":
    a = OpenTargetsAdapter()
    print("disease:", a.disease_name, "| targets loaded:", len(a.map))
    for s in ("HBB", "SELP", "BCL11A", "KCNN4", "SELPLG", "SELE"):
        r = a.target_disease_association(s)
        print(f"  {s}: score={r['score']} found={r['found']} {r.get('datatypes','')}")
