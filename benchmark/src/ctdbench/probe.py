"""Out-of-sample metadata probe: can any single released column recover the label?

For every column other than ``label`` and ``abstained`` the probe fits a majority-label lookup
on the ``train`` split (one key per distinct value, or per train-quartile bin for numeric and
identifier columns) and scores that lookup on the ``test`` split with :func:`ctdbench.evaluate`.
A column whose lookup scores far above the trivial floor is a shortcut: a model given that column
does not need the trial's evidence. The v1.0 release shipped ``label_source``, which encodes the
labeling rule and recovers the labels almost exactly; v1.1 moves it to a provenance file. The
probe is kept in the package so that the check is reproducible from the public data alone.
"""
import random
from collections import Counter

from .evaluate import DECISION_LABELS, evaluate

_SKIP = ("label", "abstained")


def _train_majority(rows):
    counts = Counter(r["label"] for r in rows if r.get("label") in DECISION_LABELS)
    return counts.most_common(1)[0][0] if counts else "stop"


def _quartile_edges(values):
    vals = sorted(v for v in values if v is not None)
    if not vals:
        return []
    return [vals[min(len(vals) - 1, int(len(vals) * q))] for q in (0.25, 0.5, 0.75)]


def _bin(value, edges):
    if value is None:
        return "missing"
    for i, edge in enumerate(edges):
        if value < edge:
            return f"q{i + 1}"
    return f"q{len(edges) + 1}"


def _keyer(column, train_rows):
    """Return (kind, key_function) for one column, fitted on train rows."""
    sample = [r.get(column) for r in train_rows if r.get(column) is not None]
    if column == "nct_id":
        edges = _quartile_edges([int(str(v)[3:]) for v in sample if str(v)[3:].isdigit()])
        return "identifier quartile", lambda r: _bin(
            int(str(r.get("nct_id"))[3:]) if str(r.get("nct_id", ""))[3:].isdigit() else None, edges
        )
    if column == "primary_completion_date":
        return "year", lambda r: (str(r.get(column))[:4] if r.get(column) else "missing")
    if sample and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in sample):
        edges = _quartile_edges(sample)
        return "numeric quartile", lambda r: _bin(r.get(column), edges)
    return "value", lambda r: ("missing" if r.get(column) is None else str(r.get(column)))


def _decisive(gold):
    return {k: v for k, v in gold.items() if v in ("advance", "stop")}


def _permutation_p(pred, gold, observed, permutations, seed):
    if permutations <= 0 or not gold:
        return None
    rng = random.Random(seed)
    ids = list(gold)
    labels = [gold[k] for k in ids]
    hits = 0
    for _ in range(permutations):
        rng.shuffle(labels)
        shuffled = dict(zip(ids, labels))
        if evaluate(pred, shuffled)["balanced_accuracy"] >= observed:
            hits += 1
    return round((hits + 1) / (permutations + 1), 4)


def probe_columns(train_rows, test_rows, columns=None, permutations=1000, seed=0):
    """Score a train-fitted majority lookup for each column on the test rows.

    Returns a list of dicts sorted by decisive balanced accuracy, descending. ``gold`` rows are
    the non-abstained test rows; ``balanced_accuracy_3class`` keeps ``verify`` in the gold set,
    ``balanced_accuracy_decisive`` drops it. ``permutation_p`` is a one-sided label-permutation
    p-value for the decisive score (``None`` when ``permutations`` is 0).
    """
    train = [r for r in train_rows if not r.get("abstained") and r.get("label") in DECISION_LABELS]
    test_gold = {r["nct_id"]: r["label"] for r in test_rows
                 if not r.get("abstained") and r.get("label") in DECISION_LABELS}
    decisive_gold = _decisive(test_gold)
    fallback = _train_majority(train)
    if columns is None:
        columns = [c for c in (train_rows[0].keys() if train_rows else []) if c not in _SKIP]

    floor3 = round(1.0 / len({v for v in test_gold.values()}), 4) if test_gold else None
    results = []
    for column in columns:
        kind, key = _keyer(column, train)
        table = {}
        for r in train:
            table.setdefault(key(r), Counter())[r["label"]] += 1
        lookup = {k: c.most_common(1)[0][0] for k, c in table.items()}
        pred = {r["nct_id"]: lookup.get(key(r), fallback) for r in test_rows if r["nct_id"] in test_gold}
        score3 = evaluate(pred, test_gold)["balanced_accuracy"] if test_gold else None
        scored = evaluate(pred, decisive_gold)["balanced_accuracy"] if decisive_gold else None
        results.append({
            "column": column,
            "key": kind,
            "n_keys": len(lookup),
            "balanced_accuracy_3class": score3,
            "balanced_accuracy_decisive": scored,
            "permutation_p_decisive": _permutation_p(
                {k: pred[k] for k in decisive_gold}, decisive_gold, scored, permutations, seed
            ) if decisive_gold else None,
        })
    results.sort(key=lambda d: -(d["balanced_accuracy_decisive"] or 0.0))
    return {
        "n_train": len(train),
        "n_test_gold": len(test_gold),
        "n_test_decisive": len(decisive_gold),
        "trivial_floor_3class": floor3,
        "trivial_floor_decisive": 0.5 if decisive_gold else None,
        "permutations": permutations,
        "columns": results,
    }


def format_markdown(report):
    lines = [
        "| column | key | keys | BA 3-class | BA decisive | perm. p |",
        "| --- | --- | ---: | ---: | ---: | ---: |",
    ]
    for c in report["columns"]:
        p = "" if c["permutation_p_decisive"] is None else f"{c['permutation_p_decisive']:.3f}"
        lines.append(
            f"| `{c['column']}` | {c['key']} | {c['n_keys']} | "
            f"{c['balanced_accuracy_3class']:.3f} | {c['balanced_accuracy_decisive']:.3f} | {p} |"
        )
    lines.append(
        f"| always-`stop` floor | | | {report['trivial_floor_3class']:.3f} | "
        f"{report['trivial_floor_decisive']:.3f} | |"
    )
    return "\n".join(lines)
