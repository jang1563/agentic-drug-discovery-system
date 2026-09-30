"""Structured features of a decide-at-cutoff evidence packet, and a frozen transparent baseline.

A packet holds what was knowable about a trial at its cutoff (the primary completion date): the
results-free protocol, prior trials of the same drug that started before the cutoff (with a compact
posted-result summary only when the results were posted before the cutoff), PubMed records on or
before the cutoff, and the Drugs@FDA status of each intervention at the cutoff. :func:`packet_features`
reads 23 numbers from it. None uses the trial's own results, and none reads free text beyond a fixed
oncology keyword list.

Packet schema (JSON object per trial; only the fields read here are listed)::

    {"nct_id": str, "cutoff_date": "YYYY-MM-DD",
     "protocol": {"start_date": str, "brief_title": str, "conditions": [str], "phases": ["PHASE2", ...],
                  "design": {"allocation": str, "primaryPurpose": str}, "masking": str,
                  "enrollment": {"count": int}, "arms": [{"type": str, "label": str}],
                  "primary_outcomes": [...], "sponsor": {"class": str}},
     "prior_trials": [{"phases": [str], "same_condition": bool, "results_posted_before_cutoff": bool,
                       "posted_result": {"verdict": str, "direction": str} | null}],
     "literature": [...],
     "regulatory": [{"status_at_cutoff": str}]}

:func:`baseline_probability` applies a logistic regression whose coefficients are frozen in this
module. It was fitted on the 186 decisive trials of the CTDBench v2 ``train`` split (primary
completion 2009–2019), so the released ``test`` split stays out of sample. On a separate cohort of
631 decisive trials completed 2023–2025 it scored balanced accuracy 0.645 and AUROC 0.701 out of
time. It is the transparent reference a model has to beat to show that it extracts more from the
evidence than structured facts.
"""
import datetime
import math
import re

FEATURE_NAMES = (
    "phase_rank", "industry", "log_enrollment", "randomized", "masking", "n_arms", "placebo_arm",
    "treatment_purpose", "n_primary_outcomes", "years_start_to_cutoff", "oncology", "n_prior",
    "n_prior_same_condition", "max_prior_phase", "n_prior_results", "prior_positive", "prior_negative",
    "prior_positive_same", "prior_negative_same", "prior_harm", "prior_benefit", "approved_at_cutoff",
    "n_literature",
)
_ONCOLOGY = re.compile(
    r"cancer|tumou?r|carcinoma|lymphoma|leuka?emia|myeloma|neoplasm|sarcoma|glioma|melanoma|glioblastoma", re.I
)
_MASKING = {"NONE": 0, "SINGLE": 1, "DOUBLE": 2, "TRIPLE": 3, "QUADRUPLE": 3}


def _phase_rank(phases):
    nums = [int(p[-1]) for p in phases or [] if isinstance(p, str) and re.fullmatch(r"PHASE[1-4]", p)]
    return sum(nums) / len(nums) if nums else 0.0


def _date(d):
    if not isinstance(d, str) or not d:
        return None
    if len(d) == 7:
        d += "-15"
    elif len(d) == 4:
        d += "-07-01"
    try:
        return datetime.date.fromisoformat(d)
    except ValueError:
        return None


def _verdict_sign(verdict):
    """+1 for a positive posted primary result, -1 for a negative one, 0 when not machine-readable."""
    v = (verdict or "").lower()
    m = re.match(r"mixed: (\d+)%", v)
    if m:
        return 1 if int(m.group(1)) >= 50 else -1
    if v.startswith("primary endpoint(s) significant") or v.startswith("two-arm separation"):
        return 1
    if v.startswith("primary endpoint(s) not significant") or v.startswith("no two-arm separation"):
        return -1
    return 0


def packet_features(packet):
    """Return ``{feature_name: float}`` for one packet (see the module docstring for the schema)."""
    pr = packet.get("protocol") or {}
    design = pr.get("design") or {}
    arms = pr.get("arms") or []
    count = (pr.get("enrollment") or {}).get("count")
    start, cutoff = _date(pr.get("start_date")), _date(packet.get("cutoff_date"))
    prior = packet.get("prior_trials") or []
    posted = [
        (_verdict_sign((t.get("posted_result") or {}).get("verdict")), bool(t.get("same_condition")),
         (t.get("posted_result") or {}).get("direction"))
        for t in prior if t.get("posted_result")
    ]
    text = " ".join(pr.get("conditions") or []) + " " + (pr.get("brief_title") or "")
    return {
        "phase_rank": _phase_rank(pr.get("phases")),
        "industry": float((pr.get("sponsor") or {}).get("class") == "INDUSTRY"),
        "log_enrollment": math.log10(count + 1) if isinstance(count, (int, float)) and count >= 0 else 0.0,
        "randomized": float(design.get("allocation") == "RANDOMIZED"),
        "masking": float(_MASKING.get(pr.get("masking"), 0)),
        "n_arms": float(len(arms)),
        "placebo_arm": float(any(
            a.get("type") in ("PLACEBO_COMPARATOR", "SHAM_COMPARATOR") or "placebo" in (a.get("label") or "").lower()
            for a in arms
        )),
        "treatment_purpose": float(design.get("primaryPurpose") == "TREATMENT"),
        "n_primary_outcomes": float(len(pr.get("primary_outcomes") or [])),
        "years_start_to_cutoff": ((cutoff - start).days / 365.25) if (start and cutoff) else 0.0,
        "oncology": float(bool(_ONCOLOGY.search(text))),
        "n_prior": float(len(prior)),
        "n_prior_same_condition": float(sum(1 for t in prior if t.get("same_condition"))),
        "max_prior_phase": max([_phase_rank(t.get("phases")) for t in prior] or [0.0]),
        "n_prior_results": float(sum(1 for t in prior if t.get("results_posted_before_cutoff"))),
        "prior_positive": float(sum(1 for s, _, _ in posted if s > 0)),
        "prior_negative": float(sum(1 for s, _, _ in posted if s < 0)),
        "prior_positive_same": float(sum(1 for s, same, _ in posted if s > 0 and same)),
        "prior_negative_same": float(sum(1 for s, same, _ in posted if s < 0 and same)),
        "prior_harm": float(sum(1 for _, _, d in posted if d == "harm")),
        "prior_benefit": float(sum(1 for _, _, d in posted if d == "benefit")),
        "approved_at_cutoff": float(any(
            str(r.get("status_at_cutoff", "")).startswith("FDA-approved") for r in packet.get("regulatory") or []
        )),
        "n_literature": float(len(packet.get("literature") or [])),
    }


# Frozen L2 logistic regression (C = 1, balanced class weights) on standardized features:
# feature -> (training mean, training scale, coefficient). Fitted 2026-09-30 on the v2 train split.
_FROZEN = {
    "fitted": "2026-09-30",
    "intercept": -0.031143651058,
    "terms": {
        "phase_rank": (2.096774193548, 0.728668193424, -0.395118244259),
        "industry": (0.741935483871, 0.437569676331, 0.400815619461),
        "log_enrollment": (1.977808020326, 0.583985098523, 0.17414506519),
        "randomized": (0.704301075269, 0.456356297912, 0.245251450083),
        "masking": (1.306451612903, 1.314788216448, 0.259084770418),
        "n_arms": (2.505376344086, 1.817617818955, 0.01642820155),
        "placebo_arm": (0.39247311828, 0.488301105577, -0.035669763752),
        "treatment_purpose": (0.854838709677, 0.352263381739, 0.410512486295),
        "n_primary_outcomes": (2.043010752688, 2.683738279047, 0.054160441669),
        "years_start_to_cutoff": (2.505207068365, 2.38913703364, -0.038980960673),
        "oncology": (0.241935483871, 0.428255420882, -0.00775135697),
        "n_prior": (10.860215053763, 5.619840807927, 0.407942868933),
        "n_prior_same_condition": (7.290322580645, 6.404099233516, 1.463022673065),
        "max_prior_phase": (2.956989247312, 1.174678894533, -0.027733344766),
        "n_prior_results": (0.704301075269, 1.528820894908, -0.268452006574),
        "prior_positive": (0.145161290323, 0.513687099654, 0.147055970885),
        "prior_negative": (0.150537634409, 0.47397283528, -0.16759167548),
        "prior_positive_same": (0.112903225806, 0.431483015639, -0.304957558131),
        "prior_negative_same": (0.129032258065, 0.445426132843, -0.304023611435),
        "prior_harm": (0.037634408602, 0.190310430327, -0.403360380991),
        "prior_benefit": (0.064516129032, 0.321503578231, 0.147506205891),
        "approved_at_cutoff": (0.322580645161, 0.467463766006, -0.707852306394),
        "n_literature": (6.854838709677, 5.215300404322, -0.287186598055),
    },
}


def baseline_probability(packet):
    """P(advance) from the frozen structured logistic regression, for one packet."""
    x = packet_features(packet)
    z = _FROZEN["intercept"]
    for name, (mean, scale, coef) in _FROZEN["terms"].items():
        z += coef * (x[name] - mean) / scale
    return 1.0 / (1.0 + math.exp(-z))


def baseline_decision(packet):
    """``{"decision", "confidence"}`` of the frozen baseline: advance when P(advance) >= 0.5."""
    p = baseline_probability(packet)
    return {"decision": "advance" if p >= 0.5 else "stop", "confidence": round(max(p, 1.0 - p), 4)}
