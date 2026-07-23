# Cross-Trial Benefit-Risk Synthesis

## Purpose

The executable v1 path aligns selected posted primary endpoints and aggregate serious-adverse-event
summaries across at least two source-disjoint trials. It preserves every trial-level value and source
hash. It does not perform a meta-analysis, calculate a benefit-risk score, or infer that an
intervention is clinically acceptable.

## Supported Contract

| Dimension | v1 contract |
| --- | --- |
| Execution stage | `regulatory_postmarket` |
| Endpoint selection | Exact ordered bindings from a committed `ClinicalEndpointMappingRecord` |
| Endpoint family | Reviewer-approved canonical family and ontology identity; no name-based automatic mapping |
| Effect measure | Hazard ratio with `lower_is_better` direction |
| Safety measure | Candidate minus comparator serious-adverse-event participant risk |
| Minimum studies | Two distinct trials, designs, endpoints, and safety records |
| Source rule | Study source-content SHA-256 sets must be pairwise disjoint |
| Pooling | Prohibited; every estimate remains trial-level |
| Clinical judgment | `clinical_acceptability_inferred=false` |

The machine input contract is
`rl_env/specs/clinical_benefit_risk_synthesis.schema.json`. Its `endpoint_mapping_id` is mandatory.
It contains only identities, harmonization declarations, and review metadata. Source measurements
cannot be supplied through the selection spec. The preceding portfolio and mapping contracts are in
`docs/23_clinical_portfolio_endpoint_mapping.md`.

## Execution Path

```text
committed reviewer-approved endpoint mapping
  -> exact mapping replay and binding-set check
  -> reviewed synthesis selection spec with endpoint_mapping_id
  -> ClinicalSynthesisAdapter strict normalization
  -> clinical_benefit_risk_synthesis_v1 semantic mapper
  -> compile_benefit_risk_synthesis(state, spec)
  -> StudyBenefitRiskRecord[] + BenefitRiskSynthesisRecord
  -> ClinicalSynthesisContinuityVerifier
  -> DecisionPacket + committed state + exact replay
```

The adapter is local and deterministic. Its tool-output SHA-256 supports only the claim that the
synthesis is available and reproducible. The compiler first recompiles the mapping ledger, then reads
scientific measurements again from the committed `TrialDesignRecord` ledger. Upstream evidence IDs,
source-content hashes, and the mapping id remain attached to the output.

## Trial-Level Output

Each `StudyBenefitRiskRecord` retains:

- exact trial, design, endpoint, and safety IDs;
- endpoint family, hazard ratio, confidence level, and confidence interval;
- candidate and comparator source measurements and unit;
- candidate and comparator serious-event affected and at-risk counts;
- both observed serious-event risks and their unadjusted absolute difference;
- bounded direction labels derived from the confidence interval and observed risk difference;
- every source evidence ID and source-content SHA-256;
- endpoint and safety fingerprints calculated from the committed typed records.

The serious-event risk difference is descriptive:

```text
candidate affected / candidate at risk
  - comparator affected / comparator at risk
```

It is not adjusted for follow-up, censoring, exposure time, competing risks, population differences,
or cross-trial confounding.

## Synthesis-Level Output

`BenefitRiskSynthesisRecord` is append-only and records:

- the complete ordered study records;
- the immutable `endpoint_mapping_id` and reviewer-declared ontology identity;
- canonical unions of source evidence IDs and source hashes;
- whether benefit and observed safety directions agree across studies;
- whether endpoint, safety, and measurement time frames or units are identical;
- `pooling_method=none` and `pooling_performed=false`;
- `cross_trial_comparability_inferred=false`;
- `population_homogeneity_inferred=false`;
- `benefit_risk_score_computed=false`;
- `clinical_acceptability_inferred=false`.

These fields make absence of inference machine-readable instead of leaving it to prose.

## Fail-Closed Behavior

The synthesis is not promoted when the approved mapping is absent, fails replay, changes dimensions,
or does not exactly equal the ordered selection set. It also abstains when any selected identity is
missing, rebound, duplicated, after the program cutoff, unsupported, or unpinned; the endpoint is not
a posted primary hazard-ratio result; the safety record is not a posted serious-event summary; or
source hashes overlap across selected trials.

Key promotion and verifier codes:

| Code | Meaning |
| --- | --- |
| `clinical_synthesis_spec_invalid` | Tool input violates the strict selection schema. |
| `clinical_synthesis_payload_mismatch` | Normalized output differs from the reviewed request. |
| `clinical_synthesis_context_mismatch` | Candidate, intervention, disease, mapping, or synthesis identity changed. |
| `clinical_synthesis_not_harmonizable` | Selected ledger records do not satisfy the v1 contract. |
| `clinical_synthesis_continuity_invalid` | A committed or proposed synthesis does not recompile exactly. |
| `benefit_risk_synthesis_missing` | A configured stage gate requires a synthesis but none qualifies. |

An abstained required call produces `DEFER` with no synthesis, claim, or evidence addition. A committed
synthesis cannot be removed or changed without failing committed-history replay.

## Verification

`tests/test_clinical_benefit_risk_synthesis.py` builds two independent synthetic
ClinicalTrials.gov source bundles, extracts and promotes each exact trial design, commits and replays
a reviewer-approved endpoint mapping, then runs the synthesis through the real tool, mapper,
transition, serialization, and replay path. Controls cover missing mapping, endpoint-ID mismatch,
overlapping source hashes, attempted automatic pooling, forged harmonized values, direct mapping and
synthesis commit bypass, unrelated derived support, and removal from committed history.

## Current Limitations

- v1 supports only explicitly selected hazard-ratio endpoints.
- Serious-event data are posted aggregate participant counts, not adjudicated event-level causality.
- Ontology identities are reviewer-declared and ledger-preserved; live ontology-authority lookup,
  synonym resolution, and terminology-version validation are not implemented.
- No fixed-effect, random-effects, Bayesian, network, or participant-level pooling is implemented.
- No quality weighting, risk-of-bias adjustment, multiplicity correction, or treatment recommendation
  is produced.
