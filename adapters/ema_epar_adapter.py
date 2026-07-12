#!/usr/bin/env python3
"""EMA EPAR adapter (callable stage-4 tool) — real EU dataset, replaces the curated ledger.

Downloads the EMA "Medicines output" master table (all centrally authorised / withdrawn /
refused / suspended / revoked human medicines), parses it once (cached), and looks up an
asset by brand / INN / active substance -> {status, ma_date, revocation/suspension, url}.

There is NO per-asset EMA API: bulk-download-then-filter. `Medicine status` is authoritative
for matched rows (date cells can be blank). A no-match is not proof that no EU filing exists;
aliases, parser drift, or an unavailable/stale table can also cause it.
"""
from __future__ import annotations
import os, json, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, "experiments/local/track_b/slice_scd/data/adapter_cache")
os.makedirs(CACHE, exist_ok=True)
PARSED = os.path.join(CACHE, "ema_epar_human.json")
XLSX = os.path.join(CACHE, "ema_epar.xlsx")
URL = "https://www.ema.europa.eu/en/documents/report/medicines-output-medicines-report_en.xlsx"


def _find(cols, *needles):
    for c in cols:
        cl = str(c).lower()
        if all(n in cl for n in needles):
            return c
    return None


def _build_cache(live):
    if not live:
        return []
    try:
        import pandas as pd
    except Exception:
        return []
    try:
        if not os.path.exists(XLSX):
            data = urllib.request.urlopen(urllib.request.Request(URL, headers={"User-Agent": "adds/0.1"}), timeout=60).read()
            open(XLSX, "wb").write(data)
        df = pd.read_excel(XLSX, sheet_name="Medicine", skiprows=8)
        cols = list(df.columns)
        cmap = {
            "name": _find(cols, "name of medicine") or _find(cols, "medicine", "name"),
            "inn": _find(cols, "inn") or _find(cols, "non-proprietary"),
            "sub": _find(cols, "active substance"),
            "status": _find(cols, "medicine status") or _find(cols, "status"),
            "cat": _find(cols, "category"),
            "ma": _find(cols, "marketing authorisation date"),
            "wd": _find(cols, "withdrawal", "revocation") or _find(cols, "withdrawal"),
            "susp": _find(cols, "suspension"),
            "url": _find(cols, "url"),
        }
        rows = []
        for _, r in df.iterrows():
            if cmap["cat"] and str(r.get(cmap["cat"], "")).strip().lower().startswith("vet"):
                continue
            def g(k):
                c = cmap.get(k)
                v = r.get(c) if c else None
                return None if (v is None or str(v) == "nan") else str(v).strip()
            rows.append({"name": g("name"), "inn": g("inn"), "sub": g("sub"), "status": g("status"),
                         "ma_date": g("ma"), "withdrawal_revocation_date": g("wd"),
                         "suspension_date": g("susp"), "url": g("url")})
        json.dump(rows, open(PARSED, "w"))
        return rows
    except Exception:
        return []


class EmaEparAdapter:
    def __init__(self, live=True):
        self.rows = []
        if os.path.exists(PARSED):
            try: self.rows = json.load(open(PARSED))
            except Exception: self.rows = []
        if not self.rows:
            self.rows = _build_cache(live)

    def lookup(self, query):
        q = (query or "").lower().strip()
        if not q:
            return {"found": False, "query": query, "evidence_status": "invalid_query",
                    "note": "empty EMA/EPAR lookup; filing status unresolved"}
        if not self.rows:
            return {"found": False, "query": query, "evidence_status": "dataset_unavailable",
                    "note": "EMA table unavailable or empty; filing status unresolved"}
        for r in self.rows:
            hay = " ; ".join(str(r.get(k) or "") for k in ("name", "inn", "sub")).lower()
            if q in hay:
                return {"found": True, "asset": r.get("name"), "inn": r.get("inn"),
                        "status": r.get("status"), "ma_date": r.get("ma_date"),
                        "withdrawal_revocation_date": r.get("withdrawal_revocation_date"),
                        "suspension_date": r.get("suspension_date"), "url": r.get("url")}
        return {"found": False, "query": query, "evidence_status": "not_found_in_loaded_table",
                "note": "no match in the loaded EMA table; filing status unresolved (check aliases and source freshness)"}


if __name__ == "__main__":
    a = EmaEparAdapter()
    print("rows:", len(a.rows))
    for q in ("crizanlizumab", "voxelotor", "exagamglogene", "lovotibeglogene", "hydroxycarbamide"):
        print(f"  {q}:", a.lookup(q))
