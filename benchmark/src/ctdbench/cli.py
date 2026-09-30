"""Command-line interface: ``ctdbench evaluate``, ``baseline``, ``probe`` and ``info``."""
import argparse
import json
import sys

from .data import DEFAULT_REVISION, SPLITS, load_gold, load_records
from .evaluate import discrimination, evaluate, evidence_value
from .features import baseline_decision
from .probe import format_markdown, probe_columns


def _read_predictions(path):
    """Return ``(decisions, confidences)`` from a JSON file of ``{nct_id: decision}`` or
    ``{nct_id: {"decision": ..., "confidence": ...}}`` (confidence optional)."""
    with open(path) as f:
        raw = json.load(f)
    if not isinstance(raw, dict):
        sys.exit("predictions file must be a JSON object keyed by nct_id")
    decisions, confidences = {}, {}
    for k, v in raw.items():
        if isinstance(v, dict):
            decisions[k] = v.get("decision")
            if "confidence" in v:
                confidences[k] = v["confidence"]
        else:
            decisions[k] = v
    return decisions, confidences


def _cmd_evaluate(a):
    preds, confs = _read_predictions(a.predictions)
    gold = load_gold(
        split=a.split, local_dir=a.local_dir, revision=a.revision,
        decisive_only=not a.include_verify, config=a.config,
    )
    result = evaluate(preds, gold)
    if confs:
        result["discrimination"] = discrimination(preds, gold, confs)
    if a.title_only:
        without, _ = _read_predictions(a.title_only)
        result["evidence_value"] = evidence_value(preds, without, gold, bootstrap=a.bootstrap)
    print(json.dumps(result, indent=2))


def _cmd_baseline(a):
    out = {}
    with open(a.packets) as f:
        for line in f:
            if line.strip():
                packet = json.loads(line)
                out[packet["nct_id"]] = baseline_decision(packet)
    if a.out:
        with open(a.out, "w") as f:
            json.dump(out, f, indent=1)
        print(f"wrote {len(out)} baseline decisions to {a.out}")
    else:
        print(json.dumps(out, indent=1))


def _cmd_info(a):
    recs = load_records(split=a.split, local_dir=a.local_dir, revision=a.revision, config=a.config)
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
    train = load_records(split="train", local_dir=a.local_dir, revision=a.revision, config=a.config)
    test = load_records(split="test", local_dir=a.local_dir, revision=a.revision, config=a.config)
    report = probe_columns(train, test, permutations=a.permutations, seed=a.seed)
    if a.format == "json":
        print(json.dumps(report, indent=2))
    else:
        print(format_markdown(report))


def main(argv=None):
    p = argparse.ArgumentParser(prog="ctdbench", description="Clinical-trial decision benchmark runner.")
    p.add_argument("--local-dir", default=None, help="load splits from a local Parquet dir instead of the Hub")
    p.add_argument("--config", default="default", choices=("default", "v2"),
                   help="gold to load: default = v1.1 source-derived labels, v2 = event-anchored labels")
    p.add_argument(
        "--revision",
        default=DEFAULT_REVISION,
        help="Hub commit or tag; defaults to the package-pinned revision",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    pe = sub.add_parser("evaluate", help="score a predictions file against a split")
    pe.add_argument(
        "--predictions", required=True,
        help="JSON {nct_id: advance|stop|verify} or {nct_id: {decision, confidence}}; omit/abstain to decline",
    )
    pe.add_argument("--split", default="test", choices=SPLITS)
    pe.add_argument(
        "--include-verify", action="store_true",
        help="keep the small verify class in the gold set (default: decisive advance/stop only)",
    )
    pe.add_argument(
        "--title-only", default=None, metavar="PATH",
        help="the same model's predictions from the trial id and title alone; adds the paired evidence value",
    )
    pe.add_argument("--bootstrap", type=int, default=2000, help="resamples for the evidence-value interval")
    pe.set_defaults(func=_cmd_evaluate)

    pb = sub.add_parser(
        "baseline",
        help="decisions of the frozen structured-feature baseline for a JSONL file of evidence packets",
    )
    pb.add_argument("--packets", required=True, help="JSONL, one packet per line (schema: ctdbench.features)")
    pb.add_argument("--out", default=None, help="write {nct_id: {decision, confidence}} here instead of stdout")
    pb.set_defaults(func=_cmd_baseline)

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
