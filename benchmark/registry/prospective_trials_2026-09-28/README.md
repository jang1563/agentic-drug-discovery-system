# Prospective CTDBench trial registry: public commitment

Registered 2026-09-28; cutoff 2026-09-28.

This folder commits to model predictions about 400 phase 2 and phase 3 drug trials that had finished enrolling
and expected primary completion between 2026-10-01 and 2027-03-31. None of them had read out at registration. The
cohort, the registry records as fetched, the cutoff-safe evidence packets and the predictions of seven models
stay private until the outcomes resolve. This commit publishes only their hashes and the pre-registration, so the
predictions can later be shown to be unchanged.

**Combined SHA-256:** `3fef2dd85011751589f3a34db980a9d35ba97e6d0147b1840482cbf2ce54d3fc`

- `MANIFEST.json` lists the SHA-256 of every file in the frozen registry: the cohort, 400 ClinicalTrials.gov
  records, the fetch caches, the packets, the predictions, a descriptive summary and a snapshot of the code.
- `PREREGISTRATION.md` is a byte-identical copy of the frozen pre-registration; its hash appears in the manifest.

## Question and resolution

For each trial, each model decided whether the sponsor should advance or stop the program in this indication once
the trial reads out, with a stated confidence, both with the evidence packet and without it. The gold label is the
CTDBench v2 event-anchored label, computed with the frozen code from ClinicalTrials.gov and Drugs@FDA at two reads:

- interim read on 2028-06-01;
- final read on 2031-06-01, with the full rule set including four-year non-progression.

Rules, cohort definition and scoring are in `PREREGISTRATION.md`.

## Verifying the released registry

Once the registry folder is released, recompute the SHA-256 of each file, compare it with `MANIFEST.json`, and
recompute the combined hash from the sorted `path:sha256` lines of all files other than `MANIFEST.json`:

```python
import glob, hashlib, os
root = "registry/2026-09-28"  # the released folder
files = sorted(os.path.relpath(p, root) for p in glob.glob(f"{root}/**/*", recursive=True)
               if os.path.isfile(p) and not p.endswith("MANIFEST.json"))
lines = [f"{f}:{hashlib.sha256(open(os.path.join(root, f), 'rb').read()).hexdigest()}" for f in files]
print(hashlib.sha256("\n".join(lines).encode()).hexdigest())
```
