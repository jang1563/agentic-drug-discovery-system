# Preregistered Endpoint/Estimand Review Preflight

## Research Question

Can an end-to-end drug-discovery agent convert exact registry representation provenance into a
bounded endpoint/estimand review queue without treating missing analyses as numerical
incompatibility, silently excluding pairs, or approving semantic equivalence?

This increment implements that preflight. It binds the complete cross-trial candidate graph, the
aggregate structural-presence report, and every exact source-bound presence sidecar. The output
retains pair and source-record identities, typed blocker and context-gap codes, review routes, and
five unresolved estimand dimensions. It does not retain endpoint titles, population text, source
arrays, or source payloads.

The five fixed dimensions follow the [ICH E9(R1) estimand
framework](https://database.ich.org/sites/default/files/E9-R1_Step4_Guideline_2019_1203.pdf):

1. treatment condition
2. population
3. variable
4. intercurrent-event strategy
5. population-level summary

Every dimension remains unresolved until human review. A preflight-ready pair is therefore ready
to be reviewed, not approved.

## Preregistered Routing

The compiler assigns exactly one route per pair:

| Route | Trigger | Meaning |
| --- | --- | --- |
| `source_completion_required` | Missing critical endpoint fields; absent/null/empty `analyses`; or absent/null/empty analysis `groupIds` | Required source structure is incomplete. The pair is retained and not automatically excluded. |
| `endpoint_identity_reconciliation_required` | Posted endpoint has unmatched or ambiguous exact protocol linkage, with no higher-priority source blocker | Endpoint identity must be reconciled before estimand review. |
| `ready_for_endpoint_estimand_review` | No fixed source or identity blocker | Five-part human estimand review may begin; no equivalence is implied. |

Missing `dispersion_type` is intentionally a **nonblocking context gap**. Dispersion is relevant to
reported estimator uncertainty but is not one of the five estimand-defining dimensions. Treating
it as a hard blocker initially routed 34 of 35 RA pairs to source completion; the exact execution
exposed that design error before publication. The final policy preserves the gap without allowing
it to control the estimand-review route.

## Exact 2026-08-27 Execution

ClinicalTrials.gov reports that its API dataset is refreshed on weekdays and exposes the current
`dataTimestamp` through `/api/v2/version`. The four raw responses retrieved on 2026-08-27 had
different SHA-256 values from the 2026-08-25 snapshots used in the preceding presence analysis.
The older and newer source identities are never mixed. This execution uses a new, fully bound
2026-08-27 cohort snapshot; each public packet records the exact source locator, version, retrieval
time, raw content hash, inventory hash, and sidecar hash. See the
[official API documentation](https://clinicaltrials.gov/data-about-studies/learn-about-api).

| Cohort | Pairs | Source completion | Identity reconciliation | Review-ready | Pairs with missing analyses | Nonblocking context-gap pairs |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| RA olokizumab MTX-IR | 35 | 0 | 0 | 35 | 0 | 34 |
| UC ozanimod | 110 | 96 | 0 | 14 | 96 | 110 |

For RA, all 35 pairs pass the fixed source and protocol-link preflight. Thirty-four pairs still
carry at least one missing-dispersion context gap. All five estimand dimensions remain unresolved
for every pair.

For UC, 96 of 110 pairs involve at least one endpoint whose exact source has an absent `analyses`
array. There are 33 left-side and 90 right-side blocker incidences; these overlap within 27 pairs,
so the unique blocked-pair count is 96 rather than 123. The remaining 14 pairs are eligible to
enter five-part review. All 110 pairs carry at least one nonblocking missing-dispersion gap.

| Artifact | SHA-256 |
| --- | --- |
| RA spec | `1ac0a657241c1df5fd4b72f1c7744f0e6bf251ceffbf5bee4186f2a37cdedc46` |
| RA packet | `e95e836704cd13931e0260fe02c81d39b320afac97e6a807914522261d9154b9` |
| UC spec | `b4c9730e3563966fb7ff89a58cc90a65c9a17f59a1f45d8e86a653cf563e8047` |
| UC packet | `525e50a83a6098ea95f0bce4f210a6dbe9a65b686d3b42dd18c213afe80ba0a1` |

Packet integrity fingerprints:

- RA: `5cbcbce0ea91616de8512fcb5e58b808577db383d7fffa89ba2d6adf9e4c82b3`
- UC: `0af8e92339cc2d1657695f1f7f7b1b6bd8229e9dc865101bc1cd6755e7356640`

## Replay

The generic exact-cohort audit performs inventory, complete candidate enumeration, diagnostics,
structural decomposition, source-presence resolution, and endpoint/estimand preflight in one
fail-closed path. Raw source files remain outside Git.

```bash
PYTHONPATH=. python scripts/audit/compile_clinicaltrials_gov_endpoint_estimand_preflight.py \
  --cohort-id olokizumab-mtx-ir \
  --registry-version 2026-08-27 \
  --retrieved-at 2026-08-27T23:40:58+00:00 \
  --study NCT02760368=/path/to/NCT02760368.json \
  --study NCT02760407=/path/to/NCT02760407.json \
  --source-sha256 NCT02760368=d1c5b7f19aa2f06f3247ba92ec2f09aa0bf39d7bd2aafd4e58646f4a561d31d1 \
  --source-sha256 NCT02760407=1adc07342f9a7e3b93c985769d151f89022032d8ffe794656985fb3c897d295d \
  --max-source-bytes 1048576 \
  --max-pair-count 1000 \
  --spec-output /tmp/ra-preflight-spec.json \
  --packet-output /tmp/ra-preflight-packet.json
```

The reusable package CLI consumes already-compiled exact artifacts:

```bash
adds-pinned-ingestion compile-clinicaltrials-gov-endpoint-estimand-preflight \
  --spec preflight-spec.json \
  --candidate-packet candidates.json \
  --presence-report presence-report.json \
  --sidecar trial-a-presence.json \
  --sidecar trial-b-presence.json \
  --output preflight-packet.json
```

Both paths enforce strict duplicate-safe JSON readers, independent byte and work bounds, exact
input fingerprints, canonical ordering, atomic output, and deterministic replay.

## Interpretation Boundary

This is a source and identity preflight, not an endpoint mapping and not an estimand adjudication.
The 35 RA and 14 UC review-ready pairs are not 49 equivalent pairs. No human review was performed;
endpoint identity, treatment condition, population, variable, intercurrent-event strategy,
population-level summary, safety window, and clinical comparability all remain unresolved.

The next research priority is an evidence-acquisition packet that binds registry records to exact
protocol and statistical-analysis-plan sections for those five dimensions. That stage should
extract reviewable claims and contradictions while preserving a hard separation between machine
evidence assembly and human approval.
