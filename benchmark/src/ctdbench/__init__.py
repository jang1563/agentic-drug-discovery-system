"""ctdbench — runner + scorer for the clinical-trial decision benchmark.

    from ctdbench import load_gold, evaluate
    gold = load_gold(split="test")                 # {nct_id: advance/stop}; verify excluded by default
    preds = {nct: my_agent(nct) for nct in gold}   # your model's decisions (may abstain)
    print(evaluate(preds, gold))                    # balanced accuracy, macro-F1, coverage, ...
"""
from .evaluate import DECISION_LABELS, discrimination, evaluate, evidence_value, rank_score, risk_coverage
from .features import FEATURE_NAMES, baseline_decision, baseline_probability, packet_features
from .data import CONFIGS, DEFAULT_REVISION, DECISIVE_LABELS, REPO_ID, SPLITS, load_events, load_gold, load_provenance, load_records
from .probe import format_markdown, probe_columns

__version__ = "0.5.0"
__all__ = [
    "CONFIGS",
    "DECISION_LABELS",
    "FEATURE_NAMES",
    "DECISIVE_LABELS",
    "DEFAULT_REVISION",
    "REPO_ID",
    "SPLITS",
    "evaluate",
    "discrimination",
    "evidence_value",
    "rank_score",
    "baseline_decision",
    "baseline_probability",
    "packet_features",
    "risk_coverage",
    "load_records",
    "load_gold",
    "load_provenance",
    "load_events",
    "probe_columns",
    "format_markdown",
]
