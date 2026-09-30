"""Offline tests for the 0.5.0 scoring conventions: decision-first ranking, evidence value, the structured baseline."""
import json
import math

import pytest

from ctdbench import (
    FEATURE_NAMES, baseline_decision, baseline_probability, discrimination, evidence_value, packet_features,
    rank_score,
)
from ctdbench.cli import main
from ctdbench.evaluate import stated_probability

GOLD = {"a": "advance", "b": "advance", "c": "stop", "d": "stop"}


def test_rank_score_is_decision_first():
    assert rank_score("advance", 0.9) > rank_score("advance", 0.6) > rank_score("verify", 0.99) == 0.5
    assert rank_score("stop", 0.6) > rank_score("stop", 0.9)
    # a confidence below 0.5 for a forced answer stays on that answer's side
    assert rank_score("stop", 0.2) < 0.5 < rank_score("advance", 0.2)
    assert stated_probability("stop", 0.2) == pytest.approx(0.8)  # the older mapping flips it
    # unusable confidences carry no ordering information
    assert rank_score("advance", None) == rank_score("advance", "high") == rank_score("advance", float("nan")) == 0.75
    assert rank_score(None, 0.9) == rank_score("abstain", 0.9) == 0.5
    assert rank_score("advance", 7) == 1.0  # clipped


def test_discrimination_counts_incoherent_confidences():
    preds = {"a": "advance", "b": "advance", "c": "stop", "d": "stop"}
    coherent = {"a": 0.9, "b": 0.7, "c": 0.8, "d": 0.6}
    r = discrimination(preds, GOLD, coherent)
    assert r["auroc"] == 1.0 and r["auroc_stated"] == 1.0 and r["n_confidence_below_half"] == 0
    assert r["n_advance"] == 2 and r["n_stop"] == 2
    # the same decisions with a "weak guess" confidence on the stops: ranking unchanged, stated mapping inverted
    weak = {"a": 0.9, "b": 0.7, "c": 0.05, "d": 0.02}
    r = discrimination(preds, GOLD, weak)
    assert r["auroc"] == 1.0
    assert r["auroc_stated"] == 0.0  # 1 - 0.05 and 1 - 0.02 now outrank every advance
    assert r["n_confidence_below_half"] == 2
    assert r["brier"] == pytest.approx((0.01 + 0.09 + 0.95 ** 2 + 0.98 ** 2) / 4, abs=1e-4)


def test_discrimination_ignores_verify_gold_and_handles_one_class():
    gold = dict(GOLD, e="verify")
    r = discrimination({"a": "advance", "e": "verify"}, gold, {"a": 0.9})
    assert (r["n_advance"], r["n_stop"]) == (2, 2)  # verify rows do not enter
    one = discrimination({"a": "advance"}, {"a": "advance", "b": "advance"}, {"a": 0.9})
    assert one["auroc"] is None and one["n_stop"] == 0


def test_evidence_value_is_paired_and_forced():
    with_ev = {"a": "advance", "b": "advance", "c": "stop", "d": "stop"}
    without = {"a": "advance", "b": "stop", "c": "stop", "d": "advance"}
    r = evidence_value(with_ev, without, GOLD, bootstrap=200, seed=1)
    assert r["balanced_accuracy_with"] == 1.0 and r["balanced_accuracy_without"] == 0.5
    assert r["evidence_value"] == 0.5
    lo, hi = r["evidence_value_ci95"]
    assert lo <= 0.5 <= hi
    # an abstention or a verify on a decisive trial is a miss on either side
    r = evidence_value({"a": "advance", "c": "stop"}, {"a": "advance", "b": "verify", "c": "stop", "d": "stop"}, GOLD, bootstrap=0)
    assert r["balanced_accuracy_with"] == 0.5 and r["balanced_accuracy_without"] == 0.75
    assert "evidence_value_ci95" not in r


def _packet(**over):
    p = {
        "nct_id": "NCT00000001", "cutoff_date": "2024-06-30",
        "protocol": {"start_date": "2021-01-15", "brief_title": "A study of drug X in breast cancer",
                     "conditions": ["Breast Cancer"], "phases": ["PHASE2", "PHASE3"],
                     "design": {"allocation": "RANDOMIZED", "primaryPurpose": "TREATMENT"}, "masking": "DOUBLE",
                     "enrollment": {"count": 99}, "arms": [{"type": "EXPERIMENTAL", "label": "X"}, {"type": "PLACEBO_COMPARATOR", "label": "Placebo"}],
                     "primary_outcomes": [{"measure": "PFS"}], "sponsor": {"class": "INDUSTRY"}},
        "prior_trials": [
            {"phases": ["PHASE2"], "same_condition": True, "results_posted_before_cutoff": True,
             "posted_result": {"verdict": "primary endpoint(s) significant", "direction": "benefit"}},
            {"phases": ["PHASE1"], "same_condition": False, "results_posted_before_cutoff": True,
             "posted_result": {"verdict": "mixed: 25% of primary analyses significant", "direction": None}},
            {"phases": ["PHASE2"], "same_condition": True, "results_posted_before_cutoff": False, "posted_result": None},
        ],
        "literature": [{"pmid": "1"}, {"pmid": "2"}],
        "regulatory": [{"status_at_cutoff": "no FDA approval on record as of the cutoff"}],
    }
    p.update(over)
    return p


def test_packet_features_read_the_documented_fields():
    x = packet_features(_packet())
    assert tuple(x) == FEATURE_NAMES
    assert x["phase_rank"] == 2.5 and x["industry"] == 1.0 and x["randomized"] == 1.0 and x["masking"] == 2.0
    assert x["log_enrollment"] == pytest.approx(2.0)
    assert x["n_arms"] == 2.0 and x["placebo_arm"] == 1.0 and x["treatment_purpose"] == 1.0
    assert x["years_start_to_cutoff"] == pytest.approx(3.46, abs=0.01)
    assert x["oncology"] == 1.0
    assert x["n_prior"] == 3.0 and x["n_prior_same_condition"] == 2.0 and x["max_prior_phase"] == 2.0
    assert x["n_prior_results"] == 2.0
    assert (x["prior_positive"], x["prior_negative"], x["prior_positive_same"], x["prior_negative_same"]) == (1.0, 1.0, 1.0, 0.0)
    assert (x["prior_harm"], x["prior_benefit"]) == (0.0, 1.0)
    assert x["approved_at_cutoff"] == 0.0 and x["n_literature"] == 2.0
    # an empty packet is all zeros rather than an error
    assert all(v == 0.0 for v in packet_features({"nct_id": "x"}).values())


def test_baseline_is_a_coherent_probability_with_the_frozen_signs():
    p = _packet()
    prob = baseline_probability(p)
    assert 0.0 < prob < 1.0
    d = baseline_decision(p)
    assert d["decision"] in ("advance", "stop") and d["confidence"] >= 0.5
    assert d["confidence"] == pytest.approx(max(prob, 1 - prob), abs=1e-4)
    # more prior trials in the same condition push towards advance; an approved drug pushes towards stop
    more_same = _packet(prior_trials=p["prior_trials"] + [{"phases": ["PHASE2"], "same_condition": True} for _ in range(5)])
    assert baseline_probability(more_same) > prob
    approved = _packet(regulatory=[{"status_at_cutoff": "FDA-approved product on record (first original approval 2010-01-01)"}])
    assert baseline_probability(approved) < prob


def test_cli_baseline_and_evaluate_with_objects(tmp_path, capsys):
    packets = tmp_path / "packets.jsonl"
    packets.write_text("\n".join(json.dumps(_packet(nct_id=f"NCT{i:08d}")) for i in range(3)) + "\n")
    out = tmp_path / "base.json"
    main(["baseline", "--packets", str(packets), "--out", str(out)])
    assert "wrote 3 baseline decisions" in capsys.readouterr().out
    base = json.loads(out.read_text())
    assert set(base) == {"NCT00000000", "NCT00000001", "NCT00000002"}
    assert all(v["decision"] in ("advance", "stop") and v["confidence"] >= 0.5 for v in base.values())
    # evaluate accepts {nct_id: {decision, confidence}} and a title-only file, against a local parquet dir
    import pyarrow as pa
    import pyarrow.parquet as pq
    gold = {"NCT00000000": "advance", "NCT00000001": "stop", "NCT00000002": "stop"}
    pq.write_table(pa.table({"nct_id": list(gold), "label": list(gold.values()), "abstained": [False] * 3}), tmp_path / "test.parquet")
    preds = tmp_path / "preds.json"
    preds.write_text(json.dumps({k: {"decision": v, "confidence": 0.8} for k, v in gold.items()}))
    title = tmp_path / "title.json"
    title.write_text(json.dumps({k: "advance" for k in gold}))
    main(["--local-dir", str(tmp_path), "evaluate", "--predictions", str(preds), "--title-only", str(title), "--bootstrap", "50"])
    r = json.loads(capsys.readouterr().out)
    assert r["balanced_accuracy"] == 1.0
    assert r["discrimination"]["auroc"] == 1.0 and r["discrimination"]["n_confidence_below_half"] == 0
    assert r["evidence_value"]["evidence_value"] == 0.5
    assert math.isfinite(r["evidence_value"]["evidence_value_ci95"][0])
