"""Deterministic, event-anchored label signals for the clinical-trial decision benchmark (v2).

Every function is a pure function over public records: a ClinicalTrials.gov API v2 study JSON,
ClinicalTrials.gov search hits, the Drugs@FDA bulk export, and openFDA label indications. No LLM is
involved. Each signal is kept as its own column group so that the composition rule in
:func:`compose` can be re-derived, ablated, or replaced. ``scripts/build_event_labels.py`` in the
repository runs the whole pipeline from the public APIs; the dataset card documents the schema.
"""
import re

# --- shared helpers -----------------------------------------------------------------------------
_P = re.compile(r"^\s*([<>]=?)?\s*([0-9]*\.?[0-9]+)")
NONSUP = re.compile(r"non[- ]?inferior|equivalen|noninferior|safety|tolerab|adverse|pharmacokinet|bioequivalen", re.I)
PLACEBO = re.compile(r"placebo|saline|vehicle|sham|standard (of )?care|usual care|no treatment|control|dummy|matching", re.I)
STOP_W = set("oral injection tablet tablets capsule capsules placebo device standard therapy mg iv the a of for and with plus dose low high daily weekly".split())
PHASE_RANK = {"EARLY_PHASE1": 0.5, "PHASE1": 1.0, "PHASE2": 2.0, "PHASE3": 3.0, "PHASE4": 4.0}
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


def _date(s):
    """Normalise CT.gov 'YYYY-MM' / 'YYYY-MM-DD' to a sortable 'YYYY-MM-DD' (month → first day)."""
    if not s:
        return None
    s = str(s)
    return s if len(s) == 10 else (s + "-01" if len(s) == 7 else (s + "-01-01" if len(s) == 4 else s))


def phase_rank(phases):
    ranks = [PHASE_RANK[p] for p in (phases or []) if p in PHASE_RANK]
    return max(ranks) if ranks else None


def _tokens(text):
    return {w for w in re.split(r"[^a-z0-9]+", (text or "").lower()) if len(w) > 4}


def drug_query_name(name):
    """A search key for an intervention name: the full lower-cased name minus dose/route words,
    plus its first informative token (for fuzzy matching against Drugs@FDA)."""
    base = re.sub(r"\(.*?\)", " ", name or "").lower()
    toks = [w for w in re.split(r"[^a-z0-9-]+", base) if len(w) > 3 and w not in STOP_W and not re.match(r"^\d", w)]
    return (" ".join(toks[:3]).strip() or None), (toks[0] if toks else None)


# --- per-study metadata --------------------------------------------------------------------------
def trial_meta(study):
    ps = study.get("protocolSection") or {}
    st = ps.get("statusModule") or {}
    dm = ps.get("designModule") or {}
    im = ps.get("armsInterventionsModule") or {}
    cm = ps.get("conditionsModule") or {}
    ds = study.get("derivedSection") or {}
    mesh = [m.get("term") for m in ((ds.get("conditionBrowseModule") or {}).get("meshes") or [])]
    ivs = []
    for i in im.get("interventions") or []:
        t = (i.get("type") or "").upper()
        n = i.get("name") or ""
        if t in ("DRUG", "BIOLOGICAL") and not PLACEBO.search(n):
            ivs.append(n)
    return {
        "nct_id": (ps.get("identificationModule") or {}).get("nctId"),
        "status": st.get("overallStatus"),
        "why_stopped": st.get("whyStopped"),
        "start_date": _date((st.get("startDateStruct") or {}).get("date")),
        "primary_completion_date": _date((st.get("primaryCompletionDateStruct") or {}).get("date")),
        "completion_date": _date((st.get("completionDateStruct") or {}).get("date")),
        "results_first_post_date": _date((st.get("resultsFirstPostDateStruct") or {}).get("date")),
        "last_update_post_date": _date((st.get("lastUpdatePostDateStruct") or {}).get("date")),
        "phases": dm.get("phases") or [],
        "phase_rank": phase_rank(dm.get("phases")),
        "conditions": cm.get("conditions") or [],
        "mesh_terms": mesh,
        "drug_interventions": ivs,
        "n_interventions": len(im.get("interventions") or []),
        "snapshot": (study.get("_snapshot") or {}).get("fetched_at"),
    }


# --- E1: structured primary-endpoint significance --------------------------------------------------
def e1_primary_significance(study):
    rs = study.get("resultsSection") or {}
    oms = ((rs.get("outcomeMeasuresModule") or {}).get("outcomeMeasures") or [])
    prim = [o for o in oms if (o.get("type") or "").upper() == "PRIMARY"]
    flags, dirs, designs = [], [], set()
    for o in prim:
        if NONSUP.search(o.get("title") or ""):
            designs.add("title_non_superiority")
        for a in (o.get("analyses") or []):
            nit = (a.get("nonInferiorityType") or "").upper()
            if nit and nit != "SUPERIORITY":
                designs.add(nit.lower())
            p, op = _pf(a.get("pValue"))
            s = _sig(p, op)
            if s is None:
                continue
            flags.append(bool(s))
            if s:
                dirs.append(_direction(o.get("title"), a.get("paramType"), a.get("paramValue")))
    non_sup = any(d for d in designs if "non_inferiority" in d or "equivalence" in d or d == "title_non_superiority" or d == "other")
    if not flags:
        return {"e1_n_primary": len(prim), "e1_n_p": 0, "e1_frac_sig": None, "e1_any_sig": None,
                "e1_all_nonsig": None, "e1_direction": None, "e1_non_superiority_design": non_sup}
    frac = sum(flags) / len(flags)
    direction = "benefit" if "benefit" in dirs else ("harm" if "harm" in dirs else ("unresolved" if dirs else None))
    return {"e1_n_primary": len(prim), "e1_n_p": len(flags), "e1_frac_sig": round(frac, 3),
            "e1_any_sig": frac > 0, "e1_all_nonsig": frac == 0, "e1_direction": direction,
            "e1_non_superiority_design": non_sup}


# --- E2: raw between-arm statistics on the first primary outcome -----------------------------------
def e2_raw_stats(study):
    rs = study.get("resultsSection") or {}
    oms = ((rs.get("outcomeMeasuresModule") or {}).get("outcomeMeasures") or [])
    prim = [o for o in oms if (o.get("type") or "").upper() == "PRIMARY"]
    out = {"e2_z": None, "e2_sig": None, "e2_n_arms": None, "e2_non_superiority_design": None}
    if not prim:
        return out
    o = prim[0]
    out["e2_non_superiority_design"] = bool(NONSUP.search(o.get("title") or ""))
    disp = o.get("dispersionType") or ""
    denoms = {}
    for dn in (o.get("denoms") or []):
        for c in dn.get("counts") or []:
            try:
                denoms[c["groupId"]] = float(c["value"])
            except Exception:
                pass
    classes = o.get("classes") or []
    cats = (classes[0].get("categories") or []) if classes else []
    pts = []
    for m in ((cats[0].get("measurements") or []) if cats else []):
        try:
            v = float(m["value"])
            sp = m.get("spread")
            if sp is None:
                continue
            sp = float(sp)
            n = denoms.get(m["groupId"])
            se = sp if "Error" in disp else (sp / (n ** 0.5) if n else None)
            if se is not None:
                pts.append((v, se))
        except Exception:
            continue
    out["e2_n_arms"] = len(pts)
    if len(pts) != 2:
        return out
    (v1, se1), (v2, se2) = pts
    d = (se1 ** 2 + se2 ** 2) ** 0.5
    if d == 0:
        return out
    z = abs(v1 - v2) / d
    out["e2_z"] = round(z, 2)
    out["e2_sig"] = z >= 1.96
    return out


# --- E3: status / termination reason --------------------------------------------------------------
_WHY = [
    ("efficacy_failure", re.compile(r"futil|lack of efficacy|no efficacy|inefficac|did not (meet|show|demonstrate)|failed to", re.I)),
    ("safety", re.compile(r"safety|adverse|toxic|side effect|death", re.I)),
    ("enrollment", re.compile(r"enrol|recruit|accrual|participants", re.I)),
    ("business", re.compile(r"sponsor|business|fund|financ|strateg|commercial|portfolio|company", re.I)),
]


def e3_status(meta):
    why = meta.get("why_stopped") or ""
    cat = None
    if meta.get("status") in ("TERMINATED", "WITHDRAWN", "SUSPENDED"):
        cat = "other"
        for name, rx in _WHY:
            if rx.search(why):
                cat = name
                break
    return {"e3_status": meta.get("status"), "e3_stop_category": cat}


# --- E4: later, higher-phase trial of the same investigational drug (phase progression) ----------
GENERIC_COND_TOKENS = {"cancer", "carcinoma", "disease", "diseases", "disorder", "disorders", "syndrome", "chronic",
                       "acute", "malignant", "neoplasm", "neoplasms", "advanced", "metastatic", "recurrent",
                       "refractory", "relapsed", "tumor", "tumour", "tumors", "infection", "infections", "adult",
                       "pediatric", "healthy", "volunteers", "patients", "stage", "severe", "moderate", "mild",
                       "primary", "secondary", "other", "unspecified", "solid", "locally"}


def _cond_tokens(conditions):
    toks = set()
    for c in conditions or []:
        toks |= {w for w in re.split(r"[^a-z0-9]+", c.lower()) if len(w) > 3 and w not in GENERIC_COND_TOKENS}
    return toks


def e4_phase_progression(meta, hits_by_drug, exclude_drugs=()):
    """hits_by_drug: {query_name: [hit dicts]}. ``exclude_drugs`` are interventions that were already
    approved before the trial (from E5): later trials of an approved drug are not development
    progression. Phase 4 hits and non-interventional studies are ignored for the same reason."""
    pcd = meta.get("primary_completion_date")
    own = meta.get("phase_rank")
    snapshot_date = (meta.get("snapshot") or "")[:10] or None
    cond_tok = _cond_tokens(meta.get("conditions"))
    strict, loose, same_phase = [], [], []
    n_hits = 0
    for drug in meta.get("drug_interventions") or []:
        q, _ = drug_query_name(drug)
        investigational = drug not in set(exclude_drugs)
        for h in hits_by_drug.get(q or "", []):
            if h["nct_id"] == meta["nct_id"]:
                continue
            n_hits += 1
            if (h.get("study_type") or "INTERVENTIONAL") != "INTERVENTIONAL":
                continue
            if (h.get("status") or "") in ("WITHDRAWN", "NOT_YET_RECRUITING"):
                continue  # never started: not evidence that the program advanced
            sd = _date(h.get("start_date"))
            if not (pcd and sd and sd > pcd) or (snapshot_date and sd > snapshot_date):
                continue
            hr = phase_rank(h.get("phases"))
            if hr is None or hr >= 4:
                continue
            same = bool(cond_tok & _cond_tokens(h.get("conditions")))
            if own is not None and hr > own and same:
                loose.append(h["nct_id"])
                if investigational:
                    strict.append(h["nct_id"])
            elif own is not None and hr == own and same and investigational:
                same_phase.append(h["nct_id"])
    return {"e4_n_hits": n_hits, "e4_later_higher_same_condition": sorted(set(strict)),
            "e4_later_higher_same_condition_loose": sorted(set(loose)),
            "e4_later_same_phase_same_condition": sorted(set(same_phase)),
            "e4_searchable": bool(meta.get("drug_interventions")) and own is not None}


def approx_year_from_application(app):
    """Latest plausible approval year implied by an FDA application number (numbers are roughly
    chronological). Used as an upper bound: if even the latest plausible year precedes a trial,
    the drug was on the market before it, whatever the truncated Drugs@FDA history says."""
    m = re.match(r"^(NDA|ANDA|BLA)(\d+)$", app or "")
    if not m:
        return None
    kind, num = m.group(1), int(m.group(2))
    tables = {
        "NDA": [(16000, 1970), (18000, 1982), (20000, 1992), (21000, 2000), (22000, 2008), (200000, 2012),
                (203000, 2013), (205000, 2015), (207000, 2016), (209000, 2018), (210000, 2019), (213000, 2021),
                (216000, 2023), (220000, 2025)],
        "BLA": [(103000, 2002), (125000, 2005), (125300, 2010), (125500, 2015), (125600, 2017), (125700, 2019),
                (761000, 2021), (761100, 2018), (761200, 2021), (761300, 2023)],
        "ANDA": [(70000, 1990), (75000, 1998), (78000, 2006), (80000, 2010), (90000, 2009), (200000, 2012),
                 (205000, 2016), (210000, 2019), (213000, 2021), (216000, 2023)],
    }
    for limit, year in tables[kind]:
        if num < limit:
            return year
    return 2026


# --- E5: Drugs@FDA approval events ---------------------------------------------------------------
def build_drugsfda_index(records):
    """Map lower-cased generic/brand/substance names to approval facts."""
    idx = {}
    for r in records:
        of = r.get("openfda") or {}
        names = set()
        for k in ("generic_name", "brand_name", "substance_name"):
            for n in of.get(k) or []:
                names.add(n.lower())
        for p in r.get("products") or []:
            if p.get("brand_name"):
                names.add(p["brand_name"].lower())
        dates = sorted(s.get("submission_status_date") for s in (r.get("submissions") or [])
                       if s.get("submission_type") == "ORIG" and s.get("submission_status") == "AP" and s.get("submission_status_date"))
        first = dates[0] if dates else None
        any_dates = sorted(s.get("submission_status_date") for s in (r.get("submissions") or []) if s.get("submission_status_date"))
        earliest_any = any_dates[0] if any_dates else None
        statuses = {p.get("marketing_status") for p in (r.get("products") or [])}
        app = r.get("application_number") or ""
        for n in names:
            cur = idx.setdefault(n, {"applications": set(), "first_approval": None, "earliest_any_submission": None,
                                     "marketing_status": set(), "has_anda": False, "earliest_anda_submission": None,
                                     "approx_year_lower_bound": None})
            cur["applications"].add(app)
            ay = approx_year_from_application(app)  # latest plausible approval year for this application
            if ay is not None and (cur["approx_year_lower_bound"] is None or ay < cur["approx_year_lower_bound"]):
                cur["approx_year_lower_bound"] = ay  # earliest application's upper bound = drug age bound
            cur["has_anda"] = cur["has_anda"] or app.startswith("ANDA")
            if app.startswith("ANDA") and earliest_any and (cur["earliest_anda_submission"] is None or earliest_any < cur["earliest_anda_submission"]):
                cur["earliest_anda_submission"] = earliest_any
            cur["marketing_status"] |= {s for s in statuses if s}
            if first and (cur["first_approval"] is None or first < cur["first_approval"]):
                cur["first_approval"] = first
            if earliest_any and (cur["earliest_any_submission"] is None or earliest_any < cur["earliest_any_submission"]):
                cur["earliest_any_submission"] = earliest_any
    return idx


def _fda_candidates(fda_index, q, tok):
    """All index names that plausibly denote the same active ingredient as the query: the exact
    name, names that extend it with a salt or combination partner, and, for one-token queries, any
    name whose first word is the token. Hyphenated formulation prefixes (nab-paclitaxel) fall back
    to their longest part."""
    keys = set()
    if tok and "-" in tok and not any(ch.isdigit() for ch in tok):
        parts = sorted((p for p in tok.split("-") if len(p) > 4), key=len, reverse=True)
        if parts and (parts[0] in fda_index or any(k.split()[0] == parts[0] for k in fda_index)):
            q, tok = parts[0], parts[0]
    if q and q in fda_index:
        keys.add(q)
    if q:
        for k in fda_index:
            if k.startswith(q + " ") or k.startswith(q + ";") or k.startswith(q + ","):
                keys.add(k)
    if tok and len(tok) > 4 and (not q or " " not in q):
        for k in fda_index:
            if k == tok or k.split()[0] == tok or k.split(";")[0].strip() == tok:
                keys.add(k)
    return keys


def _aggregate(fda_index, keys):
    agg = {"first_approval": None, "earliest_any_submission": None, "earliest_anda_submission": None,
           "approx_year_lower_bound": None, "n_keys": len(keys)}
    for k in keys:
        h = fda_index[k]
        for f in ("first_approval", "earliest_any_submission", "earliest_anda_submission", "approx_year_lower_bound"):
            v = h.get(f)
            if v is not None and (agg[f] is None or v < agg[f]):
                agg[f] = v
    return agg


def e5_regulatory(meta, fda_index):
    pcd = meta.get("primary_completion_date")
    start = meta.get("start_date")
    matched, first_dates, after, before = [], [], [], []
    for drug in meta.get("drug_interventions") or []:
        q, tok = drug_query_name(drug)
        keys = _fda_candidates(fda_index, q, tok)
        if not keys:
            continue
        hit = _aggregate(fda_index, keys)
        matched.append(drug)
        fa = hit.get("first_approval")
        ea = hit.get("earliest_any_submission")
        if not fa:
            # No original approval date on record (truncated history): the drug still counts as on the
            # market before the trial when any listed submission or the application-number age bound
            # predates the trial start.
            ea_iso = f"{ea[:4]}-{ea[4:6]}-{ea[6:]}" if ea else None
            ay = hit.get("approx_year_lower_bound")
            if (start and ea_iso and ea_iso < start) or (start and ay is not None and ay < int(start[:4]) - 1):
                before.append(drug)
            continue
        if fa:
            fa_iso = f"{fa[:4]}-{fa[4:6]}-{fa[6:]}"
            ea_iso = f"{ea[:4]}-{ea[4:6]}-{ea[6:]}" if ea else fa_iso
            first_dates.append(fa_iso)
            # Drugs@FDA submission history is truncated for old products, so a late "first ORIG
            # approval" is trusted as a forward event only when nothing in the record (earliest
            # submission, earliest generic ANDA, or the application-number age bound) predates the trial.
            anda = hit.get("earliest_anda_submission")
            anda_iso = f"{anda[:4]}-{anda[4:6]}-{anda[6:]}" if anda else None
            ay = hit.get("approx_year_lower_bound")
            old_by_number = bool(start and ay is not None and ay < int(start[:4]) - 1)
            on_market_before = (bool(start and ea_iso < start) or bool(pcd and fa_iso <= pcd)
                                or bool(start and anda_iso and anda_iso < start) or old_by_number)
            if pcd and fa_iso > pcd and not on_market_before:
                after.append(drug)
            elif on_market_before:
                before.append(drug)
    return {"e5_drugs_matched": matched, "e5_first_approval_dates": first_dates,
            "e5_first_approval_after_trial": after, "e5_approved_before_trial": before}



# --- E6: deterministic endpoint-direction resolver (keyword tables, no LLM) ------------------------
LOWER_BETTER = ("mortalit", "death", "died", "incidence of", "rate of infection", "infection rate", "hba1c",
                "fasting glucose", "plasma glucose", "blood glucose", "ldl", "cholesterol", "triglycerid", "blood pressure", "systolic", "diastolic", "bmi",
                "waist", "length of stay", "hospital stay", "duration of", "adverse",
                "nausea", "vomiting", "pain", "vas ", "nrs", "anxiety", "depress", "hamd", "madrs", "phq", "symptom",
                "severity", "disability", "fatigue", "viral load", "crp", "c-reactive", "inflammat", "recurrence",
                "relapse", "exacerbation", "hospitaliz", "readmission", "complication", "bleeding", "consumption",
                "intake", "craving", "number of episodes", "frequency of", "attack", "seizure", "migraine",
                "itch", "pruritus", "eczema", "easi", "pasi", "dlqi", "oswestry", "womac", "koos pain", "stiffness",
                "tumor size", "tumour size", "lesion", "plaque", "colony", "bacterial load", "parasit", "burden",
                "errors", "time to first", "onset time", "delirium", "agitation", "distress", "stress", "insomnia",
                "sleep latency", "wake after", "il-6", "tnf", "creatinine", "proteinuria", "albuminuria",
                "iop", "intraocular pressure", "lipid", "uric acid", "ferritin", "transfusion", "opioid", "morphine",
                "analgesic", "dropout", "withdrawal", "failure rate", "mace", "stroke", "myocardial infarction",
                "cardiovascular event", "fracture", "fall", "ulcer", "wound area", "scar", "edema", "oedema")
HIGHER_BETTER = ("survival", "response rate", "overall response", "objective response", "remission", "cure",
                 "clearance rate", "eradicat", "success rate", "successful", "healing", "improvement", "improved",
                 "function", "quality of life", "qol", "sf-36", "eq-5d", "6-minute walk", "6mwd", "walk distance",
                 "walking distance", "fev1", "fvc", "vo2", "strength", "adherence", "satisfaction", "abstinence",
                 "quit rate", "seroconversion", "titer", "titre", "antibody", "immunogenic", "cd4", "bone mineral",
                 "bmd", "hemoglobin", "haemoglobin", "ejection fraction", "mobility", "knowledge", "completion rate",
                 "vaccination rate", "uptake", "pregnancy rate", "live birth", "ovulation", "sperm", "engraftment",
                 "patency", "graft survival", "recovery", "return of", "muscle mass", "lean mass", "height",
                 "growth velocity", "cognitive", "mmse", "moca", "memory", "attention", "iq", "visual acuity",
                 "bcva", "letters", "hearing", "sensitivity", "range of motion", "grip", "gait speed", "balance",
                 "self-efficacy", "efficacy", "conception", "implantation", "attendance", "retention", "glycemic control",
                 "time in range", "target range", "in range", "time in target", "sustained virolog", "svr", "negative conversion", "sputum conversion")
AMBIGUOUS = ("change from baseline", "change in", "score", "level", "concentration", "time to", "rate")
CONTROL_ARM = re.compile(r"placebo|control|sham|standard|usual care|no treatment|vehicle|comparator|conventional|routine|waitlist|wait-list|observation", re.I)


def endpoint_polarity(title, unit=""):
    t = f" {(title or '').lower()} {(unit or '').lower()} "
    lo = any(k in t for k in LOWER_BETTER)
    hi = any(k in t for k in HIGHER_BETTER)
    if lo and not hi:
        return "lower"
    if hi and not lo:
        return "higher"
    return None


def _arm_values(prim):
    groups = {g.get("id"): (g.get("title") or "", g.get("description") or "") for g in (prim.get("groups") or [])}
    classes = prim.get("classes") or []
    cats = (classes[0].get("categories") or []) if classes else []
    vals = []
    for m in ((cats[0].get("measurements") or []) if cats else []):
        try:
            vals.append((groups.get(m.get("groupId"), ("", ""))[0], groups.get(m.get("groupId"), ("", ""))[1], float(m["value"])))
        except Exception:
            continue
    return vals


def e6_keyword_direction(study, drug_names):
    """Resolve the direction of the first primary outcome's two-arm difference with keyword tables.

    Returns e6_polarity (higher/lower/None), e6_control_arm (title or None) and e6_direction
    (benefit/harm/unresolved/None). Only two-arm, control-identifiable, unambiguous endpoints resolve.
    """
    rs = study.get("resultsSection") or {}
    oms = ((rs.get("outcomeMeasuresModule") or {}).get("outcomeMeasures") or [])
    prim = [o for o in oms if (o.get("type") or "").upper() == "PRIMARY"]
    out = {"e6_polarity": None, "e6_control_arm": None, "e6_direction": None}
    if not prim:
        return out
    o = prim[0]
    pol = endpoint_polarity(o.get("title"), o.get("unitOfMeasure"))
    out["e6_polarity"] = pol
    vals = _arm_values(o)
    if len(vals) != 2:
        return out
    ctrl = [i for i, (t, d, _) in enumerate(vals) if CONTROL_ARM.search(t) or CONTROL_ARM.search(d[:80])]
    if len(ctrl) != 1:
        toks = {events_tok for n in (drug_names or []) for events_tok in re.split(r"[^a-z0-9]+", n.lower()) if len(events_tok) > 3}
        exp = [i for i, (t, d, _) in enumerate(vals) if any(tok in t.lower() for tok in toks)]
        if len(exp) == 1:
            ctrl = [1 - exp[0]]
    if len(ctrl) != 1:
        return out
    c = ctrl[0]
    e = 1 - c
    out["e6_control_arm"] = vals[c][0]
    if pol is None:
        out["e6_direction"] = "unresolved"
        return out
    diff = vals[e][2] - vals[c][2]
    if diff == 0:
        out["e6_direction"] = "unresolved"
        return out
    better = diff > 0 if pol == "higher" else diff < 0
    out["e6_direction"] = "benefit" if better else "harm"
    return out



def e5_indication_gate(meta, e5, label_cache):
    """Keep a drug-level approval as a forward event only when the label's indications mention the
    trial's condition (non-generic condition tokens). Missing labels leave the event unconfirmed."""
    cond_tok = _cond_tokens(meta.get("conditions"))
    matched, status = [], None
    for drug in e5.get("e5_first_approval_after_trial") or []:
        q, tok = drug_query_name(drug)
        entry = label_cache.get(q or tok) or {}
        text = (entry.get("indications") or "").lower()
        if not text:
            status = status or "label_unavailable"
            continue
        ind_tok = {w for w in re.split(r"[^a-z0-9]+", text) if len(w) > 3 and w not in GENERIC_COND_TOKENS}
        if cond_tok & ind_tok:
            matched.append(drug)
            status = "matched"
        else:
            status = status or "not_matched"
    return {"e5_indication_match": matched, "e5_indication_status": status}


# --- composition -----------------------------------------------------------------------------------
def compose(meta, e1, e2, e3, e4, e5, e6=None):
    """Draft v2 rule. Returns (label, tier, reasons, conflict)."""
    e6 = e6 or {}
    reasons = []
    forward_specific = bool(e4["e4_later_higher_same_condition"])
    forward_drug = bool(e5.get("e5_indication_match"))  # approval after the trial AND label indication matches
    forward = forward_specific or forward_drug
    if forward_specific:
        reasons.append("later higher-phase trial, same condition (E4)")
    if forward_drug:
        reasons.append("first FDA approval after trial completion, indication matches (E5)")

    efficacy_design = not (e1.get("e1_non_superiority_design") or e2.get("e2_non_superiority_design"))
    failure = False
    if efficacy_design:
        if e1["e1_all_nonsig"] is True:
            failure = True
            reasons.append("all primary analyses non-significant (E1)")
        elif e1["e1_n_p"] == 0 and e2["e2_sig"] is False:
            failure = True
            reasons.append("no between-arm separation on the primary outcome (E2)")
    if e3["e3_stop_category"] in ("efficacy_failure", "safety"):
        failure = True
        reasons.append(f"terminated: {e3['e3_stop_category']} (E3)")

    significant = efficacy_design and (e1["e1_any_sig"] is True or (e1["e1_n_p"] == 0 and e2["e2_sig"] is True))
    direction = None
    if significant:
        if e1["e1_any_sig"] is True and e1["e1_direction"] in ("benefit", "harm"):
            direction = e1["e1_direction"]
            basis = "E1 parameter rule"
        elif e6.get("e6_direction") in ("benefit", "harm"):
            direction = e6["e6_direction"]
            basis = "E6 keyword rule"
    success_sig = significant and direction == "benefit"
    harm_sig = significant and direction == "harm"
    sig_unresolved = significant and direction is None

    conflict = failure and forward
    if harm_sig and not forward:
        return "stop", "tier1b", reasons + [f"significant primary effect in the harmful direction ({basis})"], conflict
    if forward and not failure:
        return "advance", "tier1a", reasons, conflict
    if success_sig and not failure:
        return "advance", "tier1b", reasons + [f"significant primary benefit ({basis})"], conflict
    if failure and not forward:
        return "stop", "tier1a" if e3["e3_stop_category"] in ("efficacy_failure", "safety") else "tier1b", reasons, conflict
    if conflict:
        return "verify", "tier1a", reasons + ["trial-internal failure but a forward event exists"], conflict
    if sig_unresolved:
        return "verify", "tier1b", reasons + ["significant separation, direction unresolved"], conflict
    return None, None, reasons, conflict
