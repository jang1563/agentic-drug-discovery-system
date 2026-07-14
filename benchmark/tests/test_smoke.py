"""Offline smoke tests for the scorer — no network, no Hub."""
import pytest

from ctdbench import evaluate, risk_coverage


def test_perfect_and_floor():
    gold = {"a": "advance", "b": "stop", "c": "stop", "d": "verify"}
    perfect = evaluate(dict(gold), gold)
    assert perfect["balanced_accuracy"] == 1.0
    assert perfect["coverage"] == 1.0
    assert perfect["n_scored"] == 4
    # always-majority ("stop") must sit at the trivial floor, not above it
    floor = evaluate({k: "stop" for k in gold}, gold)
    assert floor["balanced_accuracy"] == floor["trivial_floor_balanced_accuracy"]


def test_abstention_and_coverage():
    gold = {"a": "advance", "b": "stop", "c": "stop", "d": "verify"}
    # model acts on 2 of 4, both correct -> coverage 0.5, accuracy 1.0
    r = evaluate({"a": "advance", "b": "stop"}, gold)
    assert r["coverage"] == 0.5
    assert r["n_scored"] == 2
    assert r["accuracy"] == 1.0
    assert r["balanced_accuracy"] == 0.6667
    assert r["conditional_balanced_accuracy"] == 1.0
    assert r["coverage_adjusted_balanced_accuracy"] == 0.5
    # abstaining on everything is reported, not a crash
    all_abstain = evaluate({}, gold)
    assert all_abstain["n_scored"] == 0
    assert all_abstain["balanced_accuracy"] == 0.0
    assert all_abstain["conditional_balanced_accuracy"] is None


def test_class_selective_abstention_is_not_a_perfect_balanced_score():
    gold = {"a": "advance", "b": "stop", "c": "stop", "d": "verify"}
    r = evaluate({"a": "advance"}, gold)
    assert r["coverage"] == 0.25
    assert r["balanced_accuracy"] == 0.3333
    assert r["conditional_balanced_accuracy"] == 1.0
    assert r["coverage_adjusted_balanced_accuracy"] == 0.3333
    assert r["per_class_coverage"] == {"advance": 1.0, "stop": 0.0, "verify": 0.0}


def test_invalid_decision_labels_fail_closed():
    gold = {"a": "advance", "b": "stop"}
    with pytest.raises(ValueError, match="unsupported decision labels"):
        evaluate({"a": "banana"}, gold)
    with pytest.raises(ValueError, match="unsupported decision labels"):
        evaluate({"a": "advance"}, {"a": "success"})


def test_risk_coverage_monotone_ids():
    gold = {"a": "advance", "b": "stop", "c": "stop", "d": "verify"}
    preds = {"a": "advance", "b": "stop", "c": "advance", "d": "verify"}  # one wrong (c)
    conf = {"a": 0.9, "b": 0.8, "c": 0.2, "d": 0.7}                       # wrong one is least confident
    curve = risk_coverage(preds, gold, conf)
    assert curve[-1]["coverage"] == 1.0
    # accepting only the most-confident should carry zero risk
    assert curve[0]["risk"] == 0.0


def test_risk_coverage_all_abstain_is_empty():
    gold = {"a": "advance", "b": "stop"}
    assert risk_coverage({}, gold, {}) == []
    assert risk_coverage({"a": "defer"}, gold, {"a": 0.9}) == []


def test_risk_coverage_uses_all_gold_as_coverage_denominator():
    gold = {"a": "advance", "b": "stop", "c": "stop", "d": "verify"}
    curve = risk_coverage({"a": "advance"}, gold, {"a": 0.9})
    assert curve[-1]["coverage"] == 0.25
    assert curve[-1]["conditional_coverage"] == 1.0


def test_risk_coverage_rejects_nonfinite_confidence():
    with pytest.raises(ValueError, match="finite numbers"):
        risk_coverage({"a": "advance"}, {"a": "advance"}, {"a": float("nan")})


def test_abstain_labels_excluded_from_gold():
    gold = {"a": "advance", "x": None, "y": "abstain"}
    r = evaluate({"a": "advance"}, gold)
    assert r["n_gold"] == 1  # None / "abstain" gold rows are not scored
