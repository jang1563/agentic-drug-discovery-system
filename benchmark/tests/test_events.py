"""Deterministic label signals: each rule on a small synthetic study record."""
from ctdbench import events


def _study(nct="NCT00000001", phases=("PHASE2",), analyses=None, outcome_title="Overall Survival",
           measurements=None, groups=None, status="COMPLETED", why=None, interventions=("Drugx",),
           conditions=("Multiple Myeloma",), start="2015-01-01", pcd="2017-06-01", unit="months"):
    groups = groups or [{"id": "OG000", "title": "Drugx"}, {"id": "OG001", "title": "Placebo"}]
    measurements = measurements or [{"groupId": "OG000", "value": "10", "spread": "2"},
                                    {"groupId": "OG001", "value": "5", "spread": "2"}]
    return {
        "protocolSection": {
            "identificationModule": {"nctId": nct},
            "statusModule": {"overallStatus": status, "whyStopped": why,
                             "startDateStruct": {"date": start}, "primaryCompletionDateStruct": {"date": pcd}},
            "designModule": {"phases": list(phases)},
            "conditionsModule": {"conditions": list(conditions)},
            "armsInterventionsModule": {"interventions": [{"type": "DRUG", "name": n} for n in interventions]
                                        + [{"type": "DRUG", "name": "Placebo"}]},
        },
        "resultsSection": {"outcomeMeasuresModule": {"outcomeMeasures": [{
            "type": "PRIMARY", "title": outcome_title, "unitOfMeasure": unit, "dispersionType": "Standard Deviation",
            "groups": groups, "denoms": [{"counts": [{"groupId": "OG000", "value": "50"}, {"groupId": "OG001", "value": "50"}]}],
            "classes": [{"categories": [{"measurements": measurements}]}],
            "analyses": analyses or [],
        }]}},
        "_snapshot": {"fetched_at": "2026-09-25T00:00:00+00:00"},
    }


def test_e1_parses_p_values_and_direction():
    st = _study(analyses=[{"pValue": "<0.001", "paramType": "Hazard Ratio", "paramValue": "0.6"}])
    e1 = events.e1_primary_significance(st)
    assert e1["e1_any_sig"] and e1["e1_direction"] == "benefit" and not e1["e1_non_superiority_design"]
    st = _study(analyses=[{"pValue": "0.42"}])
    assert events.e1_primary_significance(st)["e1_all_nonsig"] is True


def test_e1_non_inferiority_designs_are_flagged():
    st = _study(analyses=[{"pValue": "0.6", "nonInferiorityType": "NON_INFERIORITY"}])
    assert events.e1_primary_significance(st)["e1_non_superiority_design"] is True
    st = _study(outcome_title="Safety and Tolerability", analyses=[{"pValue": "0.6"}])
    assert events.e1_primary_significance(st)["e1_non_superiority_design"] is True


def test_e2_two_arm_z():
    e2 = events.e2_raw_stats(_study())
    assert e2["e2_n_arms"] == 2 and e2["e2_sig"] is True and e2["e2_z"] > 1.96
    e2 = events.e2_raw_stats(_study(measurements=[{"groupId": "OG000", "value": "5.1", "spread": "2"},
                                                  {"groupId": "OG001", "value": "5.0", "spread": "2"}]))
    assert e2["e2_sig"] is False


def test_e3_termination_class():
    m = events.trial_meta(_study(status="TERMINATED", why="Stopped for futility at interim analysis"))
    assert events.e3_status(m)["e3_stop_category"] == "efficacy_failure"
    assert events.e3_status(events.trial_meta(_study()))["e3_stop_category"] is None


def test_e4_requires_later_higher_phase_same_condition_investigational_drug():
    m = events.trial_meta(_study())
    hits = {"drugx": [
        {"nct_id": "NCT00000002", "phases": ["PHASE3"], "start_date": "2018-03-01", "status": "COMPLETED",
         "study_type": "INTERVENTIONAL", "conditions": ["Multiple Myeloma"]},
        {"nct_id": "NCT00000003", "phases": ["PHASE3"], "start_date": "2016-03-01", "status": "COMPLETED",
         "study_type": "INTERVENTIONAL", "conditions": ["Multiple Myeloma"]},          # started before completion
        {"nct_id": "NCT00000004", "phases": ["PHASE4"], "start_date": "2019-03-01", "status": "COMPLETED",
         "study_type": "INTERVENTIONAL", "conditions": ["Multiple Myeloma"]},          # phase 4 ignored
        {"nct_id": "NCT00000005", "phases": ["PHASE3"], "start_date": "2019-03-01", "status": "WITHDRAWN",
         "study_type": "INTERVENTIONAL", "conditions": ["Multiple Myeloma"]},          # never started
        {"nct_id": "NCT00000006", "phases": ["PHASE3"], "start_date": "2019-03-01", "status": "COMPLETED",
         "study_type": "INTERVENTIONAL", "conditions": ["Breast Cancer"]},              # other condition
    ]}
    e4 = events.e4_phase_progression(m, hits)
    assert e4["e4_later_higher_same_condition"] == ["NCT00000002"]
    e4 = events.e4_phase_progression(m, hits, exclude_drugs=["Drugx"])
    assert e4["e4_later_higher_same_condition"] == [] and e4["e4_later_higher_same_condition_loose"] == ["NCT00000002"]


def test_e5_first_approval_after_trial_with_age_guards():
    records = [
        {"application_number": "NDA209999", "openfda": {"generic_name": ["DRUGX"]},
         "submissions": [{"submission_type": "ORIG", "submission_status": "AP", "submission_status_date": "20180115"}],
         "products": [{"brand_name": "DRUGX", "marketing_status": "Prescription"}]},
        {"application_number": "NDA020357", "openfda": {"generic_name": ["OLDDRUG HYDROCHLORIDE"]},
         "submissions": [{"submission_type": "SUPPL", "submission_status": "AP", "submission_status_date": "20120801"}],
         "products": [{"brand_name": "OLDBRAND", "marketing_status": "Prescription"}]},
    ]
    idx = events.build_drugsfda_index(records)
    m = events.trial_meta(_study(interventions=("Drugx",)))
    e5 = events.e5_regulatory(m, idx)
    assert e5["e5_first_approval_after_trial"] == ["Drugx"]
    m = events.trial_meta(_study(interventions=("Olddrug",), start="2015-01-01", pcd="2016-01-01"))
    e5 = events.e5_regulatory(m, idx)
    assert e5["e5_approved_before_trial"] == ["Olddrug"] and e5["e5_first_approval_after_trial"] == []
    gate = events.e5_indication_gate(m, {"e5_first_approval_after_trial": ["Olddrug"]},
                                     {"olddrug": {"indications": "indicated for multiple myeloma"}})
    assert gate["e5_indication_match"] == ["Olddrug"]


def test_e6_keyword_direction_and_control_arm():
    st = _study(outcome_title="Pain Score (VAS)", unit="mm",
                measurements=[{"groupId": "OG000", "value": "20", "spread": "5"}, {"groupId": "OG001", "value": "40", "spread": "5"}])
    e6 = events.e6_keyword_direction(st, ["Drugx"])
    assert e6["e6_polarity"] == "lower" and e6["e6_control_arm"] == "Placebo" and e6["e6_direction"] == "benefit"
    st = _study(outcome_title="Mean Change From Baseline in Body Weight")
    assert events.e6_keyword_direction(st, ["Drugx"])["e6_direction"] == "unresolved"


def test_compose_paths():
    st = _study(analyses=[{"pValue": "<0.001", "paramType": "Hazard Ratio", "paramValue": "0.6"}])
    m = events.trial_meta(st)
    e1 = events.e1_primary_significance(st)
    e2 = events.e2_raw_stats(st)
    e3 = events.e3_status(m)
    e4 = {"e4_later_higher_same_condition": []}
    e5 = {"e5_first_approval_after_trial": [], "e5_indication_match": []}
    assert events.compose(m, e1, e2, e3, e4, e5)[0:2] == ("advance", "tier1b")
    e4f = {"e4_later_higher_same_condition": ["NCT00000002"]}
    assert events.compose(m, e1, e2, e3, e4f, e5)[0:2] == ("advance", "tier1a")
    st = _study(analyses=[{"pValue": "0.7"}])
    e1 = events.e1_primary_significance(st)
    label, tier, reasons, conflict = events.compose(m, e1, e2, e3, e4, e5)
    assert (label, tier, conflict) == ("stop", "tier1b", False)
    label, tier, reasons, conflict = events.compose(m, e1, e2, e3, e4f, e5)
    assert (label, conflict) == ("verify", True)
    st = _study(outcome_title="Safety and Tolerability", analyses=[{"pValue": "0.7"}])
    e1 = events.e1_primary_significance(st)
    e2 = events.e2_raw_stats(st)
    assert events.compose(m, e1, e2, e3, e4, e5)[0] is None


def test_e4_no_progression_requires_window_and_absence_of_later_trials():
    m = events.trial_meta(_study(pcd="2017-06-01"))  # snapshot 2026-09-25 -> 9 years
    hits = {"drugx": []}
    out = events.e4_no_progression(m, hits)
    assert out["e4_no_progression_eligible"] and out["e4_no_progression"] is True
    later = {"drugx": [{"nct_id": "NCT00000009", "phases": ["PHASE2"], "start_date": "2019-01-01", "status": "COMPLETED",
                        "study_type": "INTERVENTIONAL", "conditions": ["Multiple Myeloma"]}]}
    assert events.e4_no_progression(m, later)["e4_no_progression"] is False
    recent = events.trial_meta(_study(pcd="2025-01-01"))
    assert events.e4_no_progression(recent, hits)["e4_no_progression_eligible"] is False
    assert events.e4_no_progression(m, hits, has_significant_result=True)["e4_no_progression_eligible"] is False
    assert events.e4_no_progression(m, hits, exclude_drugs=["Drugx"])["e4_no_progression_eligible"] is False
