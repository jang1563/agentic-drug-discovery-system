#!/usr/bin/env python3
"""Cache-first ClinicalTrials.gov tool adapter (Track B).

A tool the agent policy calls. Backed by the project's cached CT.gov study JSONs
(offline, deterministic). Exposes a small tool surface:

  search_trials(drug, condition) -> [ {nct, significant, direction, has_results} ]
  search_asset(drug)             -> [ nct, ... ]   (drug in ANY condition)
  primary_significance(nct)      -> {significant, direction, has_results}
  check_value_plausibility(records, rule) -> [ {field, value, out_of_range}, ... ]

No family labels or gold are consulted — this is real retrieval over cached
study records, so an agent must reason from the returned evidence.
"""
from __future__ import annotations

import glob
import json
import os
import re
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CT_GLOB = os.path.join(ROOT, "case_banks/clinical_regulatory_v0/source_snapshots/raw/clinicaltrials_gov_api/**/*.json")
SEARCH_CACHE_FP = os.path.join(ROOT, "experiments/local/track_b/ctgov_search_cache.json")
API = "https://clinicaltrials.gov/api/v2/studies"

_P = re.compile(r"^\s*([<>]=?)?\s*([0-9]*\.?[0-9]+)")
_SURV = ("survival", "progression", "pfs", " os", "dfs", "ttp", "relapse", "recurrence",
         "mortalit", "death", "event-free", "hospitaliz", "exacerbation")
_RESP = ("response", "orr", "remission", "cure", "clearance", "eradicat", "seroconver",
         "success", "resolution", "healing", "achiev")


def _pf(v):
    if v is None:
        return None, None
    m = _P.match(str(v).strip())
    if not m:
        return None, None
    try:
        return float(m.group(2)), (m.group(1) or "=")
    except ValueError:
        return None, None


def _sig(p, op):
    if p is None:
        return None
    if op in ("<", "<="):
        return p <= 0.05
    if op in (">", ">="):
        return False if p >= 0.05 else None
    return p < 0.05


def _direction(title, ptype, val):
    t = f" {(title or '').lower()} "
    pt = (ptype or "").lower()
    try:
        v = float(str(val).replace(",", ""))
    except (TypeError, ValueError):
        v = None
    surv = any(k in t for k in _SURV)
    resp = any(k in t for k in _RESP)
    if "hazard ratio" in pt and v is not None:
        return "benefit" if v < 1 else ("harm" if v > 1 else "unresolved")
    if ("odds ratio" in pt or "risk ratio" in pt or "relative risk" in pt) and v is not None:
        if resp:
            return "benefit" if v > 1 else ("harm" if v < 1 else "unresolved")
        if surv:
            return "benefit" if v < 1 else ("harm" if v > 1 else "unresolved")
    if "vaccine efficacy" in pt and v is not None:
        return "benefit" if v > 0 else "harm"
    return "unresolved"


def _significance(rs):
    oms = ((rs or {}).get("outcomeMeasuresModule", {}) or {}).get("outcomeMeasures", []) or []
    prim = [o for o in oms if (o.get("type") or "").upper() == "PRIMARY"]
    flags, dirs = [], []
    for o in prim:
        for a in (o.get("analyses") or []):
            p, op = _pf(a.get("pValue"))
            s = _sig(p, op)
            if s is None:
                continue
            flags.append(bool(s))
            if s:
                dirs.append(_direction(o.get("title"), a.get("paramType"), a.get("paramValue")))
    if not flags:
        return {"significant": None, "direction": "unknown", "n_primary": len(prim), "mixed_within": False}
    frac = sum(flags) / len(flags)
    direction = "benefit" if "benefit" in dirs else ("harm" if "harm" in dirs else "unresolved")
    return {"significant": frac >= 0.5, "direction": direction, "n_primary": len(prim),
            "mixed_within": 0 < frac < 1}  # some primary endpoints met, some not, in one trial


class CtgovAdapter:
    def __init__(self):
        self.by_nct, self.index = {}, []
        for fp in glob.glob(CT_GLOB, recursive=True):
            try:
                j = json.load(open(fp))
            except Exception:
                continue
            ps = j.get("protocolSection")
            if not ps:
                continue
            nct = (ps.get("identificationModule", {}) or {}).get("nctId") or os.path.basename(fp)[:-5]
            interventions = " ".join((i.get("name") or "") for i in
                                     (ps.get("armsInterventionsModule", {}) or {}).get("interventions", []) or []).lower()
            conditions = " ".join((ps.get("conditionsModule", {}) or {}).get("conditions", []) or []).lower()
            sig = _significance(j.get("resultsSection", {}))
            sig["has_results"] = bool(j.get("hasResults"))
            rec = {"nct": nct, "interventions": interventions, "conditions": conditions, **sig}
            self.by_nct[nct] = rec
            self.index.append(rec)
        self.live = os.environ.get("CTGOV_LIVE") == "1"  # opt-in live API fallback
        self.search_cache = json.load(open(SEARCH_CACHE_FP)) if os.path.exists(SEARCH_CACHE_FP) else {}

    @staticmethod
    def _tok(s):
        return [w for w in re.split(r"[^a-z0-9]+", (s or "").lower()) if len(w) > 3]

    def _live_intr_search(self, drug):
        """Live CT.gov intervention-only search -> NCTs of the drug across ALL conditions (cached)."""
        key = (drug or "").lower().strip()
        if not key:
            return []
        if key in self.search_cache:
            return self.search_cache[key]
        try:
            url = API + "?" + urllib.parse.urlencode(
                {"query.intr": drug, "fields": "NCTId", "pageSize": 50, "format": "json"})
            data = json.load(urllib.request.urlopen(url, timeout=20))
            ncts = [s.get("protocolSection", {}).get("identificationModule", {}).get("nctId")
                    for s in data.get("studies", [])]
            ncts = [n for n in ncts if n]
        except Exception:
            ncts = []
        self.search_cache[key] = ncts
        try:
            json.dump(self.search_cache, open(SEARCH_CACHE_FP, "w"))
        except Exception:
            pass
        return ncts

    def search_trials(self, drug, condition):
        dts, cts = self._tok(drug), self._tok(condition)
        hits = []
        for r in self.index:
            if dts and any(t in r["interventions"] for t in dts) and \
               cts and any(t in r["conditions"] for t in cts):
                hits.append(
                    {
                        k: r[k]
                        for k in (
                            "nct",
                            "interventions",
                            "conditions",
                            "significant",
                            "direction",
                            "has_results",
                            "mixed_within",
                        )
                    }
                )
        return hits

    def search_asset(self, drug):
        if self.live:  # authoritative: query the drug across all conditions live
            return self._live_intr_search(drug)
        dts = self._tok(drug)
        return [r["nct"] for r in self.index if dts and any(t in r["interventions"] for t in dts)]

    def primary_significance(self, nct):
        r = self.by_nct.get(nct)
        return None if r is None else {k: r[k] for k in ("significant", "direction", "has_results", "mixed_within")}

    @staticmethod
    def check_value_plausibility(records, rule):
        out, fld = [], (rule or {}).get("field")
        lo, hi = (rule or {}).get("numeric_min"), (rule or {}).get("numeric_max")
        for r in records or []:
            try:
                v = float(r.get(fld))
            except (TypeError, ValueError):
                continue
            out.append({"field": fld, "value": v,
                        "out_of_range": (lo is not None and v < lo) or (hi is not None and v > hi)})
        return out

    def stats(self):
        return {"indexed_studies": len(self.index),
                "with_results": sum(1 for r in self.index if r["has_results"])}
