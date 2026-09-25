#!/usr/bin/env python3
"""Build event-anchored (tier 1) labels for a list of ClinicalTrials.gov trials from public sources.

Stages (all resumable, all cached under --workdir):
  fetch        one CT.gov API v2 study JSON per trial (ctgov/<nct>.json, with a snapshot timestamp)
  search       CT.gov intervention searches per drug name (search_cache.json, 200 most recent studies)
  drugsfda     download the Drugs@FDA bulk export and build the name index (drugsfda_index.json)
  indications  openFDA label indications for drugs first approved after their trial (label_cache.json)
  compose      apply ctdbench.events and write event_labels.{parquet,jsonl} + a markdown report

Example:
  python build_event_labels.py --ncts ncts.json --workdir ./v2 all
"""
import argparse
import datetime
import glob
import json
import os
import sys
import time
import urllib.parse
import urllib.request
import zipfile
from collections import Counter

from ctdbench import events

API = "https://clinicaltrials.gov/api/v2/studies"
LABEL_API = "https://api.fda.gov/drug/label.json"
DRUGSFDA_URL = "https://download.open.fda.gov/drug/drugsfda/drug-drugsfda-0001-of-0001.json.zip"
UA = {"User-Agent": "ctdbench/0.3 (research; github.com/jang1563/agentic-drug-discovery-system)"}


def _now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def _get_json(url, timeout=60):
    return json.loads(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout).read())


def stage_fetch(a):
    out = os.path.join(a.workdir, "ctgov")
    os.makedirs(out, exist_ok=True)
    ncts = json.load(open(a.ncts))
    done = {f[:-5] for f in os.listdir(out) if f.endswith(".json")}
    todo = [n for n in ncts if n not in done]
    print(f"fetch: {len(ncts)} trials, {len(done)} cached, {len(todo)} to fetch", flush=True)
    for i, nct in enumerate(todo, 1):
        url = f"{API}/{nct}?format=json"
        for attempt in range(3):
            try:
                j = _get_json(url)
                j["_snapshot"] = {"fetched_at": _now(), "url": url}
                json.dump(j, open(os.path.join(out, nct + ".json"), "w"))
                break
            except Exception as e:
                if attempt == 2:
                    print(f"  FAIL {nct}: {type(e).__name__}", flush=True)
                time.sleep(2 * (attempt + 1))
        time.sleep(a.sleep)
        if i % 100 == 0:
            print(f"  {i}/{len(todo)}", flush=True)


def _studies(a):
    for f in sorted(glob.glob(os.path.join(a.workdir, "ctgov", "*.json"))):
        yield json.load(open(f))


def ctgov_search(q, pages=2):
    hits, token = [], None
    for _ in range(pages):
        params = {"query.intr": q, "fields": "NCTId,Phase,StartDate,OverallStatus,Condition,StudyType",
                  "pageSize": "100", "sort": "StartDate:desc", "format": "json"}
        if token:
            params["pageToken"] = token
        d = _get_json(API + "?" + urllib.parse.urlencode(params))
        for s in d.get("studies", []):
            ps = s.get("protocolSection") or {}
            hits.append({"nct_id": (ps.get("identificationModule") or {}).get("nctId"),
                         "phases": (ps.get("designModule") or {}).get("phases") or [],
                         "study_type": (ps.get("designModule") or {}).get("studyType"),
                         "start_date": ((ps.get("statusModule") or {}).get("startDateStruct") or {}).get("date"),
                         "status": (ps.get("statusModule") or {}).get("overallStatus"),
                         "conditions": (ps.get("conditionsModule") or {}).get("conditions") or []})
        token = d.get("nextPageToken")
        if not token:
            break
    return hits


def stage_search(a):
    path = os.path.join(a.workdir, "search_cache.json")
    cache = json.load(open(path)) if os.path.exists(path) else {}
    names = set()
    for st in _studies(a):
        for drug in events.trial_meta(st)["drug_interventions"]:
            q, _ = events.drug_query_name(drug)
            if q:
                names.add(q)
    todo = sorted(n for n in names if n not in cache)
    print(f"search: {len(names)} drug names, {len(cache)} cached, {len(todo)} to search", flush=True)
    for i, q in enumerate(todo, 1):
        for attempt in range(3):
            try:
                cache[q] = {"fetched_at": _now(), "hits": ctgov_search(q)}
                break
            except Exception as e:
                if attempt == 2:
                    print(f"  FAIL {q!r}: {type(e).__name__}", flush=True)
                time.sleep(3 * (attempt + 1))
        time.sleep(a.sleep)
        if i % 25 == 0:
            json.dump(cache, open(path, "w"))
            print(f"  {i}/{len(todo)}", flush=True)
    json.dump(cache, open(path, "w"))


def stage_drugsfda(a):
    idx_path = os.path.join(a.workdir, "drugsfda_index.json")
    if os.path.exists(idx_path):
        print("drugsfda: index present")
        return
    zpath = os.path.join(a.workdir, "drugsfda.zip")
    if not os.path.exists(zpath):
        urllib.request.urlretrieve(DRUGSFDA_URL, zpath)
    with zipfile.ZipFile(zpath) as z:
        name = [n for n in z.namelist() if n.endswith(".json")][0]
        recs = json.loads(z.read(name))["results"]
    idx = events.build_drugsfda_index(recs)
    json.dump({k: {**v, "applications": sorted(v["applications"]), "marketing_status": sorted(v["marketing_status"])}
               for k, v in idx.items()}, open(idx_path, "w"))
    print(f"drugsfda: {len(idx)} names indexed")


def _fda_index(a):
    raw = json.load(open(os.path.join(a.workdir, "drugsfda_index.json")))
    return {k: {**v, "applications": set(v["applications"]), "marketing_status": set(v["marketing_status"])} for k, v in raw.items()}


def _label_indications(name):
    for field in ("generic_name", "brand_name", "substance_name"):
        url = f"{LABEL_API}?search=openfda.{field}:%22{urllib.parse.quote(name)}%22&limit=1"
        try:
            r = _get_json(url, timeout=30)["results"][0]
            return " ".join(r.get("indications_and_usage") or []), field
        except Exception:
            continue
    return None, None


def stage_indications(a):
    path = os.path.join(a.workdir, "label_cache.json")
    cache = json.load(open(path)) if os.path.exists(path) else {}
    idx = _fda_index(a)
    names = set()
    for st in _studies(a):
        m = events.trial_meta(st)
        e5 = events.e5_regulatory(m, idx)
        for drug in e5["e5_first_approval_after_trial"]:
            q, tok = events.drug_query_name(drug)
            names.add(q or tok)
    todo = sorted(n for n in names if n and n not in cache)
    print(f"indications: {len(names)} drugs, {len(cache)} cached, {len(todo)} to fetch", flush=True)
    for i, n in enumerate(todo, 1):
        text, field = _label_indications(n)
        if text is None and " " in n:
            text, field = _label_indications(n.split()[0])
        cache[n] = {"indications": (text or "")[:4000], "field": field, "fetched_at": _now()}
        time.sleep(1.6)  # openFDA allows 40 requests per minute without a key
        if i % 20 == 0:
            json.dump(cache, open(path, "w"))
    json.dump(cache, open(path, "w"))


def stage_compose(a):
    import pyarrow as pa
    import pyarrow.parquet as pq
    sc = os.path.join(a.workdir, "search_cache.json")
    lc = os.path.join(a.workdir, "label_cache.json")
    hits = {k: v["hits"] for k, v in (json.load(open(sc)) if os.path.exists(sc) else {}).items()}
    labels = json.load(open(lc)) if os.path.exists(lc) else {}
    idx = _fda_index(a)
    rows = []
    for st in _studies(a):
        m = events.trial_meta(st)
        e1 = events.e1_primary_significance(st)
        e2 = events.e2_raw_stats(st)
        e3 = events.e3_status(m)
        e5 = events.e5_regulatory(m, idx)
        e5.update(events.e5_indication_gate(m, e5, labels))
        e4 = events.e4_phase_progression(m, hits, exclude_drugs=e5["e5_approved_before_trial"])
        e6 = events.e6_keyword_direction(st, m["drug_interventions"])
        label, tier, reasons, conflict = events.compose(m, e1, e2, e3, e4, e5, e6)
        rows.append({**{k: m[k] for k in ("nct_id", "status", "start_date", "primary_completion_date", "phase_rank", "snapshot")},
                     "phases": ",".join(m["phases"]), **e1, **e2, **e3, **e6,
                     "e4_n_hits": e4["e4_n_hits"], "e4_searchable": e4["e4_searchable"],
                     "e4_later_higher_same_condition": ",".join(e4["e4_later_higher_same_condition"]),
                     "e4_later_higher_same_condition_loose_n": len(e4["e4_later_higher_same_condition_loose"]),
                     "e5_drugs_matched_n": len(e5["e5_drugs_matched"]),
                     "e5_first_approval_after_trial": ",".join(e5["e5_first_approval_after_trial"]),
                     "e5_indication_match": ",".join(e5.get("e5_indication_match", [])),
                     "e5_approved_before_trial": ",".join(e5["e5_approved_before_trial"]),
                     "event_label": label, "event_tier": tier, "event_reasons": "; ".join(reasons), "event_conflict": conflict})
    pq.write_table(pa.Table.from_pylist(rows), os.path.join(a.workdir, "event_labels.parquet"))
    with open(os.path.join(a.workdir, "event_labels.jsonl"), "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    n = len(rows)
    lab = Counter(r["event_label"] for r in rows)
    lines = [f"# Event-anchored labels ({n} trials)", "", "| label | n | share |", "| --- | ---: | ---: |"]
    for k in ("advance", "stop", "verify", None):
        lines.append(f"| {k or 'abstain'} | {lab[k]} | {lab[k] / n:.1%} |")
    tiers = Counter((r["event_label"], r["event_tier"]) for r in rows if r["event_label"])
    lines += ["", "| label | tier | n |", "| --- | --- | ---: |"] + [f"| {k} | {t} | {v} |" for (k, t), v in sorted(tiers.items(), key=lambda x: -x[1])]
    open(os.path.join(a.workdir, "EVENT_LABELS_REPORT.md"), "w").write("\n".join(lines) + "\n")
    print("\n".join(lines))


STAGES = {"fetch": stage_fetch, "search": stage_search, "drugsfda": stage_drugsfda,
          "indications": stage_indications, "compose": stage_compose}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("stage", choices=list(STAGES) + ["all"])
    p.add_argument("--ncts", help="JSON list of NCT ids (required for fetch)")
    p.add_argument("--workdir", default="event_labels_work")
    p.add_argument("--sleep", type=float, default=0.3, help="seconds between ClinicalTrials.gov requests")
    a = p.parse_args(argv)
    os.makedirs(a.workdir, exist_ok=True)
    for name in (list(STAGES) if a.stage == "all" else [a.stage]):
        if name == "fetch" and not a.ncts:
            sys.exit("--ncts is required for the fetch stage")
        STAGES[name](a)


if __name__ == "__main__":
    main()
