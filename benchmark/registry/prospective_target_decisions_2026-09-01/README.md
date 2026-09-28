# Prospective target-decision registry: public commitment

Registered 2026-09-28, data cutoff 2026-09-01.

This folder commits to a set of model predictions about 149 live phase 2 programs on novel drug targets whose
outcomes are not yet known. The cohort, the cutoff-safe evidence packets, the predictions of seven models and the
count-feature baselines stay private until the outcomes resolve; this commit publishes only their hashes and the
pre-registration, so that the predictions can later be shown to be unchanged.

**Combined SHA-256:** `005413f80162a857fd8452e244e0e1ad2d3ba6035ca38fc222260d05a7e73b4d`

- `MANIFEST.json` lists the SHA-256 of every file in the frozen registry (cohort, packets, predictions, baselines,
  a snapshot of the code that built them, and the pre-registration).
- `PREREGISTRATION.md` is a byte-identical copy of the frozen pre-registration; its hash appears in the manifest.

## Questions and resolution

1. Phase 3 progression (primary): will a drug acting on the target start a phase 3 or phase 2/3 trial in the disease
   between 2026-09-01 and 2028-09-01? Read no earlier than 2028-12-01.
2. Approval (secondary): will a drug acting on the target be approved by the FDA, EMA or PMDA for the disease or a
   subtype by 2036-09-01?

Rules, cohort definition and scoring are in `PREREGISTRATION.md`.

## Verifying the released registry

Once the registry folder is released, recompute the SHA-256 of each file, compare it with `MANIFEST.json`, and
recompute the combined hash from the sorted `path:sha256` lines of all files other than `MANIFEST.json`:

```python
import glob, hashlib, os
root = "registry/2026-09-01"  # the released folder
files = sorted(os.path.relpath(p, root) for p in glob.glob(f"{root}/**/*", recursive=True)
               if os.path.isfile(p) and not p.endswith("MANIFEST.json"))
lines = [f"{f}:{hashlib.sha256(open(os.path.join(root, f), 'rb').read()).hexdigest()}" for f in files]
print(hashlib.sha256("\n".join(lines).encode()).hexdigest())
```
