"""ctdbench — runner + scorer for the clinical-trial decision benchmark.

    from ctdbench import load_gold, evaluate
    gold = load_gold(split="test")                 # {nct_id: advance/stop}; verify excluded by default
    preds = {nct: my_agent(nct) for nct in gold}   # your model's decisions (may abstain)
    print(evaluate(preds, gold))                    # balanced accuracy, macro-F1, coverage, ...
"""
from .evaluate import DECISION_LABELS, evaluate, risk_coverage
from .data import DEFAULT_REVISION, DECISIVE_LABELS, REPO_ID, SPLITS, load_gold, load_provenance, load_records
from .probe import format_markdown, probe_columns

__version__ = "0.3.0"
__all__ = [
    "DECISION_LABELS",
    "DECISIVE_LABELS",
    "DEFAULT_REVISION",
    "REPO_ID",
    "SPLITS",
    "evaluate",
    "risk_coverage",
    "load_records",
    "load_gold",
    "load_provenance",
    "probe_columns",
    "format_markdown",
]
