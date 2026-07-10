"""Offline smoke tests for the scorer — no network, no Hub."""
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
    # abstaining on everything is reported, not a crash
    assert evaluate({}, gold)["n_scored"] == 0


def test_risk_coverage_monotone_ids():
    gold = {"a": "advance", "b": "stop", "c": "stop", "d": "verify"}
    preds = {"a": "advance", "b": "stop", "c": "advance", "d": "verify"}  # one wrong (c)
    conf = {"a": 0.9, "b": 0.8, "c": 0.2, "d": 0.7}                       # wrong one is least confident
    curve = risk_coverage(preds, gold, conf)
    assert curve[-1]["coverage"] == 1.0
    # accepting only the most-confident should carry zero risk
    assert curve[0]["risk"] == 0.0


def test_abstain_labels_excluded_from_gold():
    gold = {"a": "advance", "x": None, "y": "abstain"}
    r = evaluate({"a": "advance"}, gold)
    assert r["n_gold"] == 1  # None / "abstain" gold rows are not scored
