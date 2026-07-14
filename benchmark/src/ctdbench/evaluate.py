"""Scoring for the clinical-trial decision benchmark.

The task is a *decision*, not a probability: for each trial the model emits
``advance``, ``stop``, ``verify``, or abstains. Metrics keep selective
performance separate from coverage. ``balanced_accuracy`` averages recall over
every class present in the full gold split, so abstaining on an entire class
cannot silently remove that class from the score. ``coverage_adjusted_balanced_accuracy``
also counts abstained gold rows as misses within each class.
"""
from collections import Counter
from collections.abc import Mapping
from math import ceil, isfinite

DECISION_LABELS = ("advance", "stop", "verify")
_ABSTAIN = {None, "", "abstain", "null", "none", "defer"}


def _is_abstention(value):
    return value is None or (isinstance(value, str) and value in _ABSTAIN)


def _validate_inputs(predictions, gold):
    if not isinstance(predictions, Mapping) or not isinstance(gold, Mapping):
        raise TypeError("predictions and gold must be mappings keyed by trial id")

    filtered_gold = {k: v for k, v in gold.items() if not _is_abstention(v)}
    invalid_gold = sorted({repr(v) for v in filtered_gold.values() if v not in DECISION_LABELS})
    if invalid_gold:
        raise ValueError(f"gold contains unsupported decision labels: {', '.join(invalid_gold)}")

    invalid_predictions = sorted({
        repr(predictions[k])
        for k in filtered_gold
        if k in predictions
        and not _is_abstention(predictions[k])
        and predictions[k] not in DECISION_LABELS
    })
    if invalid_predictions:
        raise ValueError(
            "predictions contain unsupported decision labels: "
            + ", ".join(invalid_predictions)
        )
    return filtered_gold


def _prf(pred, gold, keys, classes):
    tp, fp, fn = Counter(), Counter(), Counter()
    for k in keys:
        g, p = gold[k], pred[k]
        if p == g:
            tp[g] += 1
        else:
            fp[p] += 1
            fn[g] += 1
    recall = {
        c: (tp[c] / (tp[c] + fn[c]) if (tp[c] + fn[c]) else 0.0)
        for c in classes
    }
    prec = {c: (tp[c] / (tp[c] + fp[c]) if (tp[c] + fp[c]) else 0.0) for c in classes}
    f1 = {c: (2 * prec[c] * recall[c] / (prec[c] + recall[c]) if (prec[c] + recall[c]) else 0.0) for c in classes}
    return recall, f1, tp


def evaluate(predictions, gold):
    """Score ``predictions`` against ``gold``.

    Args:
        predictions: ``{nct_id: decision}``. A missing key or an abstain value means the model declined.
        gold: ``{nct_id: label}`` for the confidently-labelled trials (abstained rows are excluded upstream).

    ``balanced_accuracy`` is macro-recall over all classes present in ``gold``;
    a class with no acted-on predictions receives recall 0. The explicitly
    diagnostic ``conditional_balanced_accuracy`` reproduces macro-recall only
    over classes represented in the acted subset. The coverage-adjusted metric
    treats every abstained gold row as a miss.
    """
    gold = _validate_inputs(predictions, gold)
    n_gold = len(gold)
    classes = [c for c in DECISION_LABELS if c in set(gold.values())]
    n_classes = len(classes)
    scored = [k for k in gold if not _is_abstention(predictions.get(k))]
    n = len(scored)

    if n == 0:
        zeros = {c: 0.0 for c in classes}
        return {
            "n_gold": n_gold,
            "n_scored": 0,
            "coverage": 0.0,
            "accuracy": 0.0,
            "balanced_accuracy": 0.0,
            "conditional_balanced_accuracy": None,
            "coverage_adjusted_balanced_accuracy": 0.0,
            "macro_f1": 0.0,
            "per_class_f1": dict(zeros),
            "per_class_recall": dict(zeros),
            "per_class_coverage": dict(zeros),
            "trivial_floor_balanced_accuracy": (
                round(1.0 / n_classes, 4) if n_classes else None
            ),
            "note": "model abstained on every gold-labelled trial",
        }

    pred = {k: predictions[k] for k in scored}
    goldS = {k: gold[k] for k in scored}
    correct = sum(pred[k] == goldS[k] for k in scored)
    recall, f1, tp = _prf(pred, goldS, scored, classes)
    gold_support = Counter(gold.values())
    acted_support = Counter(goldS.values())
    represented_classes = [c for c in classes if acted_support[c]]
    per_class_coverage = {c: acted_support[c] / gold_support[c] for c in classes}
    coverage_adjusted_recall = {c: tp[c] / gold_support[c] for c in classes}

    return {
        "n_gold": n_gold,
        "n_scored": n,
        "coverage": round(n / n_gold, 4),
        "accuracy": round(correct / n, 4),
        "balanced_accuracy": round(sum(recall.values()) / n_classes, 4),
        "conditional_balanced_accuracy": round(
            sum(recall[c] for c in represented_classes) / len(represented_classes), 4
        ),
        "coverage_adjusted_balanced_accuracy": round(
            sum(coverage_adjusted_recall.values()) / n_classes, 4
        ),
        "macro_f1": round(sum(f1.values()) / n_classes, 4),
        "per_class_f1": {c: round(f1[c], 3) for c in classes},
        "per_class_recall": {c: round(recall[c], 3) for c in classes},
        "per_class_coverage": {c: round(per_class_coverage[c], 3) for c in classes},
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
    gold = _validate_inputs(predictions, gold)
    ranked_ids = [
        k for k in gold
        if k in confidences and not _is_abstention(predictions.get(k))
    ]
    invalid_confidences = sorted({
        repr(confidences[k])
        for k in ranked_ids
        if isinstance(confidences[k], bool)
        or not isinstance(confidences[k], (int, float))
        or not isfinite(float(confidences[k]))
    })
    if invalid_confidences:
        raise ValueError("confidences must be finite numbers: " + ", ".join(invalid_confidences))

    ranked = sorted(ranked_ids,
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
