"""Command-line interface: ``ctdbench evaluate`` and ``ctdbench info``."""
import argparse
import json
import sys

from .data import DEFAULT_REVISION, SPLITS, load_gold, load_records
from .evaluate import evaluate


def _cmd_evaluate(a):
    with open(a.predictions) as f:
        preds = json.load(f)
    if not isinstance(preds, dict):
        sys.exit("predictions file must be a JSON object {nct_id: decision}")
    gold = load_gold(split=a.split, local_dir=a.local_dir, revision=a.revision)
    result = evaluate(preds, gold)
    print(json.dumps(result, indent=2))


def _cmd_info(a):
    recs = load_records(split=a.split, local_dir=a.local_dir, revision=a.revision)
    from collections import Counter
    labels = Counter(r.get("label") for r in recs)
    abstained = sum(1 for r in recs if r.get("abstained") is True)
    print(json.dumps({
        "split": a.split,
        "n": len(recs),
        "labels": dict(labels),
        "abstained": abstained,
        "confident": len(recs) - abstained,
    }, indent=2))


def main(argv=None):
    p = argparse.ArgumentParser(prog="ctdbench", description="Clinical-trial decision benchmark runner.")
    p.add_argument("--local-dir", default=None, help="load splits from a local Parquet dir instead of the Hub")
    p.add_argument(
        "--revision",
        default=DEFAULT_REVISION,
        help="Hub commit or tag; defaults to the package-pinned revision",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    pe = sub.add_parser("evaluate", help="score a predictions file against a split")
    pe.add_argument("--predictions", required=True, help="JSON {nct_id: advance|stop|verify}; omit/abstain to decline")
    pe.add_argument("--split", default="test", choices=SPLITS)
    pe.set_defaults(func=_cmd_evaluate)

    pi = sub.add_parser("info", help="print split statistics")
    pi.add_argument("--split", default="test", choices=SPLITS)
    pi.set_defaults(func=_cmd_info)

    a = p.parse_args(argv)
    a.func(a)


if __name__ == "__main__":
    main()
