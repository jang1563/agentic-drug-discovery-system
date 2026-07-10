"""ctdbench — runner + scorer for the clinical-trial decision benchmark.

    from ctdbench import load_gold, evaluate
    gold = load_gold(split="test")                 # {nct_id: advance/stop/verify}
    preds = {nct: my_agent(nct) for nct in gold}   # your model's decisions (may abstain)
    print(evaluate(preds, gold))                    # balanced accuracy, macro-F1, coverage, ...
"""
from .evaluate import evaluate, risk_coverage
from .data import load_records, load_gold, REPO_ID, SPLITS

__version__ = "0.1.0"
__all__ = ["evaluate", "risk_coverage", "load_records", "load_gold", "REPO_ID", "SPLITS"]
