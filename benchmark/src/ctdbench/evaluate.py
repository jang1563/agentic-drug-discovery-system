"""Scoring for the clinical-trial decision benchmark.

The task is a *decision*, not a probability: for each trial the model emits `advance`, `stop`, `verify`, or
abstains (predicts nothing / ``None``). Because the classes are imbalanced (~60% `stop`), the headline metric
is **balanced accuracy** (macro-recall) and the always-majority baseline is reported alongside so a score is
only meaningful once it clears the trivial floor. Abstention is first-class: a model may decline to predict,
and ``coverage`` (fraction of gold-labelled trials it acted on) is reported so selective policies are visible.
"""
from collections import Counter
from math import ceil

# labels that count as a real decision; anything else (None, "", "abstain", "null") is an abstention
_ABSTAIN = {None, "", "abstain", "null", "none", "defer"}


def _prf(pred, gold, keys):
    tp, fp, fn = Counter(), Counter(), Counter()
    for k in keys:
        g, p = gold[k], pred[k]
        if p == g:
            tp[g] += 1
        else:
            fp[p] += 1
            fn[g] += 1
    classes = [c for c in sorted(set(gold[k] for k in keys)) if (tp[c] + fn[c]) > 0]
    recall = {c: tp[c] / (tp[c] + fn[c]) for c in classes}
    prec = {c: (tp[c] / (tp[c] + fp[c]) if (tp[c] + fp[c]) else 0.0) for c in classes}
    f1 = {c: (2 * prec[c] * recall[c] / (prec[c] + recall[c]) if (prec[c] + recall[c]) else 0.0) for c in classes}
    return recall, f1, classes


def evaluate(predictions, gold):
    """Score ``predictions`` against ``gold``.

    Args:
        predictions: ``{nct_id: decision}``. A missing key or an abstain value means the model declined.
        gold: ``{nct_id: label}`` for the confidently-labelled trials (abstained rows are excluded upstream).

    Returns a dict with n_gold, n_scored, coverage, accuracy, balanced_accuracy, macro_f1, per_class_f1,
    and the always-majority balanced-accuracy floor for context.
    """
    gold = {k: v for k, v in gold.items() if v not in _ABSTAIN}
    n_gold = len(gold)
    scored = [k for k in gold if predictions.get(k) not in _ABSTAIN]
    n = len(scored)
    if n == 0:
        return {"n_gold": n_gold, "n_scored": 0, "coverage": 0.0,
                "note": "model abstained on every gold-labelled trial"}
    pred = {k: predictions[k] for k in scored}
    goldS = {k: gold[k] for k in scored}
    correct = sum(pred[k] == goldS[k] for k in scored)
    recall, f1, classes = _prf(pred, goldS, scored)
    # always-majority balanced-accuracy floor (1 / n_classes for a constant predictor)
    n_classes = len(set(gold.values()))
    return {
        "n_gold": n_gold,
        "n_scored": n,
        "coverage": round(n / n_gold, 4),
        "accuracy": round(correct / n, 4),
        "balanced_accuracy": round(sum(recall.values()) / len(recall), 4),
        "macro_f1": round(sum(f1.values()) / len(f1), 4),
        "per_class_f1": {c: round(f1[c], 3) for c in classes},
        "per_class_recall": {c: round(recall[c], 3) for c in classes},
        "trivial_floor_balanced_accuracy": round(1.0 / n_classes, 4),
    }


def risk_coverage(predictions, gold, confidences):
    """Risk–coverage curve for a model that emits a per-trial confidence.

    Args:
        predictions, gold: as in :func:`evaluate`.
        confidences: ``{nct_id: float}``; higher = more confident. The curve accepts the most-confident
            fraction at each coverage level and reports the error rate (risk) among accepted trials.
    Returns unique ``{"coverage", "conditional_coverage", "risk", "n"}``
    points at 10% steps. ``coverage`` is relative to all scored gold rows;
    ``conditional_coverage`` is relative only to non-abstaining predictions that
    have confidence values. Returns an empty list when that ranked set is empty.
    """
    gold = {k: v for k, v in gold.items() if v not in _ABSTAIN}
    ranked = sorted((k for k in gold if k in confidences and predictions.get(k) not in _ABSTAIN),
                    key=lambda k: -confidences[k])
    m = len(ranked)
    if m == 0:
        return []
    out = []
    last_take = 0
    for step in range(1, 11):
        cov = step / 10.0
        take = min(m, max(1, ceil(cov * m)))
        if take == last_take:
            continue
        last_take = take
        acc = ranked[:take]
        wrong = sum(predictions[k] != gold[k] for k in acc)
        out.append({
            "coverage": round(len(acc) / len(gold), 3),
            "conditional_coverage": round(len(acc) / m, 3),
            "risk": round(wrong / len(acc), 3),
            "n": len(acc),
        })
    return out
