# ClinicalTrials.gov Provider Ingestion

Status: implemented and externally validated on 2026-07-15

Scope: exact ClinicalTrials.gov study snapshot to atomic trial, arm, population, endpoint, and
posted serious-adverse-event identity

Public payload policy: source bytes, reviewer-selected source text, and reviewer jobs remain external

## What Changed

Clinical strategy now has two deliberately different evidence paths:

1. `ctgov/search_trials` remains a cache/search observation path. It can preserve contextual trial
   observations, but it cannot satisfy the default clinical `ADVANCE` gate.
2. `pinned_evidence/clinical_trial_design` reads a reviewed manifest compiled from one exact
   ClinicalTrials.gov study snapshot. It can promote a complete `TrialDesignRecord` only when the
   source receipt, NCT, registry version, candidate, condition, selected arms, population, posted
   primary endpoint, measurements, denominator counts, statistical analysis, and selected-arm
   serious-adverse-event summaries all agree.

This closes the previous gap where shaped `significant` and `direction` flags could recommend
advance without canonical arm, population, endpoint, or posted safety-summary identity.

## Atomic Identity Graph

```text
DiseaseRecord -> TargetRecord -> CandidateRecord
                                  -> InterventionRecord
                                     -> TrialRecord
                                        -> TrialDesignRecord
                                           |- TrialArmRecord (candidate)
                                           |- TrialArmRecord (comparator)
                                           |- TrialPopulationRecord
                                           |- TrialEndpointRecord
                                           `- TrialSafetyRecord
                                              |- TrialSafetyArmRecord (candidate)
                                              `- TrialSafetyArmRecord (comparator)
```

Each arm carries a typed `candidate` or `comparator` role. One `trial_design_update` carries all
nested records. Safety arms explicitly map the endpoint arm id to a distinct adverse-event group
id. A mismatch rejects or defers the complete promotion; no arm, endpoint, safety summary, trial,
intervention, claim, or evidence fragment is committed alone.

## Provider Contract

The reviewer job schema is
`rl_env/specs/clinicaltrials_gov_ingestion_job.schema.json`; the synthetic executable example is
`rl_env/specs/clinicaltrials_gov_ingestion_job.example.json`.

The extractor verifies:

1. Exact HTTPS locator `https://clinicaltrials.gov/api/v2/studies/{NCT}` with no query, fragment,
   credentials, or alternate host.
2. Receipt id, canonical source id, byte SHA-256, NCT, and
   `clinicaltrials-gov-{NCT}-version-{versionHolder}` source version.
3. `INTERVENTIONAL`, one declared phase, completed status, condition, primary completion date, and
   results-first-post date.
4. Candidate name and aliases against the source intervention names.
5. Two reviewer-selected protocol arms against exact protocol labels, types, intervention names,
   posted outcome group ids, titles, measurements, and participant denominators.
6. Enrollment and bounded eligibility fields: analysis population description, count/type, sex,
   age bounds, and healthy-volunteer status.
7. One posted primary endpoint against both protocol and results modules.
8. Exact registry analysis group order, typed candidate/comparator roles, p-value comparator,
   statistical method, analysis parameter, estimate, confidence interval percentage, and bounds.
9. The posted adverse-event time frame, optional description, and exact serious-event term count.
10. Two selected adverse-event groups against exact `EG...` ids, bounded title equivalence, arm
    roles, affected participant counts, and positive at-risk participant counts.

Duplicate JSON keys, non-finite values, malformed source receipts, source drift, index drift, arm
swaps, result-group swaps, adverse-event-group swaps, and typed value mismatches fail closed.
During promotion, every source candidate alias must also resolve through the accepted
`CandidateRecord` id, name, or pre-approved `attributes.identity_aliases`; mixed canonical and
unapproved aliases are rejected. A source condition must intersect the accepted disease name or
its pre-approved identity aliases.

Bounded title equivalence removes punctuation, numeric dose expressions (`mg`, `milligram`, or
`milligrams`), phase qualifiers, the `intervention` label, and the exact `on-treatment` qualifier
before requiring token-set equality. It does
not accept arbitrary extra cohort or treatment descriptors. Serious-event term statistics may omit
`numAffected` only for nonselected groups whose posted `numAtRisk` is zero; selected safety groups
must retain complete nonnegative affected counts and positive at-risk counts.

## Bounded Effect-Evidence Rule

Version 3 preserves structurally valid posted primary effect evidence before making a decision. It
supports frozen hazard-ratio, odds-ratio, and risk-ratio aliases plus bounded percentage-point
`risk_difference` aliases. Ratio intervals must be positive and are classified against null 1.
Risk differences are classified against null 0 and additionally require a bounded participant-,
patient-, or subject-proportion percent unit (or bare percent unit), endpoint-declared favorable
direction, and candidate-then-comparator analysis-group order. Continuous percent-change units are
not accepted. Every measure requires an ordered finite confidence interval containing the estimate,
a typed p-value between 0 and 1, and exact source agreement. The interval is classified as
`benefit`, `harm`, or
`null_or_uncertain` under the shared effect contract.

The extractor no longer discards valid harm or uncertain results. A promoted `benefit` recommends
`ADVANCE`; `harm` or `null_or_uncertain` recommends `HOLD`, retaining the evidence and design in the
ledger. Descriptive arm measurements remain source-pinned and typed, but they are not used to
override the reported analysis interval. Registry analysis-group order is preserved. For additive
risk differences, it must also bind candidate before comparator so the sign cannot be silently
reversed; ratio records retain their measure-specific fixed direction.

Endpoint and safety selections carry the same required `treatment_phase`: `induction`,
`maintenance`, or `not_applicable`. Mismatch or source phase conflict fails closed. Anything
outside the bounded structural contract returns
`pinned_clinical_design_endpoint_not_supportive` and `DEFER`.

For phase-bound induction or maintenance records, extraction also derives one exact
`population_alignment` object: study enrollment, selected endpoint denominator total, selected
safety at-risk total, role-wise count equality, and an invariant
`same_participants_inferred=false`. Promotion recomputes it from typed arms, and every committed
design, population, endpoint, and safety layer carries the same phase and alignment. Matching
aggregate counts never establish participant identity.

An approved missing descriptive arm summary does not disappear downstream. The promoted endpoint
evidence retains the raw marker, synthesis serializes the numeric field as `null`, and the evidence
tensor emits `missing_descriptive_arm_measurement`.

The safety contract separately proves only that posted aggregate serious-adverse-event participant
counts were resolved for the same candidate and comparator arms. It does not infer attribution,
comparative safety, acceptability, or benefit-risk. `event_term_count` counts reported terms, not
participants or event occurrences.

The cross-disease UC execution and its payload-free hashes are documented in
`docs/42_uc_provider_validation.md` and
`docs/uc_clinical_provider_validation_snapshot.json`.
The independent primary-maintenance percentage-point replication is documented in
`docs/44_uc_maintenance_risk_difference_replication.md` and
`docs/uc_maintenance_risk_difference_validation_snapshot.json`.

## Stage Gate

Clinical `ADVANCE` now requires all of the following from the current packet:

- supported `clinical_evidence_assessed` and `clinical_safety_assessed` claims;
- both required evidence predicates from at least one exact source-pinned study with a valid
  SHA-256;
- one qualifying intervention and one linked ClinicalTrials.gov trial;
- one qualifying atomic trial design with candidate and comparator roles, a candidate-linked arm,
  a population, a posted endpoint, and a posted serious-adverse-event record linked to those exact
  arm and population ids.

The machine failure labels remain inspectable. Missing design identity reports
`trial_design_identity_missing`; continuity failures report broken design, arm, population, and
endpoint, safety-record, and safety-arm ids under `clinical_identity_continuity_invalid`.

## External Validation Snapshot

The payload-free machine record is `docs/clinical_provider_validation_snapshot.json`.

The exact external source was ClinicalTrials.gov `NCT01844505`, registry version `2026-07-14`.
The selected posted primary PFS comparison was Nivolumab (`OG000`) versus Ipilimumab (`OG002`) in
all randomized participants. The source reports median PFS `6.87` versus `2.89` months and a hazard
ratio of `0.57` with `99.5%` confidence interval `0.43` to `0.76`, p-value `<0.0001`.
The same snapshot creates safety identity
`NCT01844505:safety:serious-adverse-events`, maps candidate arm `OG000` to safety group `EG000`
with `187/313` participants affected/at risk, and maps comparator arm `OG002` to `EG002` with
`205/311`. These values are registry aggregates and are not interpreted as a comparative safety
conclusion.

| Artifact | SHA-256 |
| --- | --- |
| Exact source JSON | `6b5b6e01ae2997b22de529849a49fc10a22965a969d88f83cdb5256c634e3fb3` |
| External reviewer job | `829676f4d5c9a1cfe7c2cd63b9f5bd8d8ff20ed7246b5a7e509419a7d41d0db3` |
| Sanitized provider output | `6c4b8c181fc6b89ccb9371e765f010f331c3b68dff174121aae272d52f834ba6` |
| Compiled manifest | `11f5549b91cfe0fac6bcb9c7f545c0fb3c00711cd8d4680d9f1f276d8ceec89c` |
| Compile review | `aae9722c6e2d494d3f407171b5c993b6d98845d0c3eb7f918a9850cc47268a7f` |

The live validation produced `pinned_clinical_trial_design_promoted`, eight clinical evidence
events, one trial, one atomic design, two arms, one population, one endpoint, one safety record,
and two safety-arm summaries. Committed-history validation passed and the state advanced to
`regulatory_postmarket`.

## Matched Failure Control

The live controlled pair removes only `metadata.safety` from the otherwise exact manifest.

| Arm | Promotion | Decision | New clinical evidence | Partial identity state |
| --- | --- | --- | ---: | --- |
| Exact identity | `pinned_clinical_trial_design_promoted` | `ADVANCE` | 8 | Complete atomic design |
| Missing safety | `pinned_clinical_design_metadata_invalid` | `DEFER` | 0 | None |

Balanced accuracy is `1.0` for this one deterministic pair. This is a contract regression, not an
estimate of clinical prediction or drug-discovery performance.

## Commands

Capture the exact study snapshot outside Git:

```bash
python -m agentic_drug_discovery.ingestion_cli capture \
  --url https://clinicaltrials.gov/api/v2/studies/NCT01844505 \
  --receipt-id ctgov-NCT01844505-20260714 \
  --source-id clinicaltrials-gov-NCT01844505 \
  --source-version clinicaltrials-gov-NCT01844505-version-2026-07-14 \
  --output /external/review/ctgov-NCT01844505
```

Verify the reviewer job and compile a payload-free manifest:

```bash
python -m agentic_drug_discovery.ingestion_cli extract-clinicaltrials-gov \
  --job /external/review/clinicaltrials-gov-job.json \
  --bundle /external/review/ctgov-NCT01844505 \
  --output /external/review/clinicaltrials-gov-extracted.json

python -m agentic_drug_discovery.ingestion_cli compile \
  --job /external/review/clinicaltrials-gov-extracted.json \
  --bundle /external/review/ctgov-NCT01844505 \
  --manifest-out /external/review/clinical-manifest.json \
  --review-out /external/review/clinical-review.json
```

Run the public contract tests:

```bash
python -m unittest tests.test_clinicaltrials_gov_ingestion -v
python -m unittest discover -s tests -v
```

## Interpretation Boundary

The hashes establish byte and artifact identity, not source authority or independent correctness.
The provider verifies registry structure, one bounded endpoint comparison, and posted aggregate
serious-adverse-event counts; it does not reanalyze participant-level data, adjudicate endpoints or
events, establish general efficacy or safety, compare the full clinical program, or make a
regulatory recommendation. `ADVANCE` means the configured evidence-governance gate passed under
this explicit contract.
