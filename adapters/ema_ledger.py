#!/usr/bin/env python3
"""EMA regulatory-event ledger adapter (callable stage-4 supplement).

EMA has no openFDA-style public API, so this reads a curated, source-verified event
ledger. It fills the gap where an asset is FDA-approved but EMA-reversed (e.g.
crizanlizumab), which openFDA alone cannot surface. Honest: curated, not live.
"""
from __future__ import annotations
import os, json

LEDGER = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "experiments/local/track_b/slice_scd/ema_events.json")


class EmaLedger:
    def __init__(self):
        try:
            self.events = json.load(open(LEDGER))
        except Exception:
            self.events = {}

    def event(self, asset_key):
        e = self.events.get(asset_key)
        return e if isinstance(e, dict) else None


if __name__ == "__main__":
    l = EmaLedger()
    for k in ("crizanlizumab", "voxelotor", "exacel", "senicapoc"):
        print(k, "->", l.event(k))
