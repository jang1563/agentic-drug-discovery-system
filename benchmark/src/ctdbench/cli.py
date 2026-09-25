"""Command-line interface: ``ctdbench evaluate`` and ``ctdbench info``."""
import argparse
import json
import sys

from .data import DEFAULT_REVISION, SPLITS, load_gold, load_records
from .evaluate import evaluate
from .probe import format_markdown, probe_columns


def _cmd_evaluate(a):
    with open(a.predictions) as f:
        preds = json.load(f)
    if not isinstance(preds, dict):
        sys.exit("predictions file must be a JSON object {nct_id: decision}")
    gold = load_gold(
        split=a.split, local_dir=a.local_dir, revision=a.revision,
        decisive_only=not a.include_verify,
    )
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


def _cmd_probe(a):
    train = load_records(split="train", local_dir=a.local_dir, revision=a.revision)
    test = load_records(split="test", local_dir=a.local_dir, revision=a.revision)
    report = probe_columns(train, test, permutations=a.permutations, seed=a.seed)
    if a.format == "json":
        print(json.dumps(report, indent=2))
    else:
        print(format_markdown(report))


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
    pe.add_argument(
        "--include-verify", action="store_true",
        help="keep the small verify class in the gold set (default: decisive advance/stop only)",
    )
    pe.set_defaults(func=_cmd_evaluate)

    pp = sub.add_parser(
        "probe",
        help="out-of-sample metadata probe: score a train-fitted majority lookup per column on test",
    )
    pp.add_argument("--permutations", type=int, default=1000, help="label permutations for p-values (0 = skip)")
    pp.add_argument("--seed", type=int, default=0)
    pp.add_argument("--format", default="markdown", choices=("markdown", "json"))
    pp.set_defaults(func=_cmd_probe)

    pi = sub.add_parser("info", help="print split statistics")
    pi.add_argument("--split", default="test", choices=SPLITS)
    pi.set_defaults(func=_cmd_info)

    a = p.parse_args(argv)
    a.func(a)


if __name__ == "__main__":
    main()
