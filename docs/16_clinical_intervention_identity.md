# Clinical Intervention And Trial-Design Identity Continuity

Status: implemented in the 0.3.0.dev0 candidate

Scope: candidate-to-intervention-to-trial-to-design continuity across clinical strategy and
regulatory review

Evidence posture: synthetic contract fixtures plus payload-free validation of one exact public
ClinicalTrials.gov snapshot; no clinical or regulatory recommendation

## Why This Contract Exists

A candidate name in a request does not establish that a returned registry row, arm, population, or
endpoint belongs to the same intervention and disease. Search context can be correct while a source
record names a different asset, condition, result group, analysis population, or endpoint. The
clinical identity chain is therefore immutable program state, not mapper-local text.

The implemented graph is:

```text
DiseaseRecord -> TargetRecord -> CandidateRecord
                                  -> InterventionRecord
                                     -> TrialRecord
                                        -> TrialDesignRecord
                                           |- TrialArmRecord (candidate)
                                           |- TrialArmRecord (comparator)
                                           |- TrialPopulationRecord
                                           `- TrialEndpointRecord
                                     -> EMA namespace/status extension
```

`PromotionContext` constrains a request, but it is not an identity authority. Promotion must
reconcile request arguments, accepted ledgers, source-returned identities, and a pinned source
receipt before records can enter state.

## Typed Ledgers

| Record | Canonical key | Stable identity fields | Required evidence link |
| --- | --- | --- | --- |
| `InterventionRecord` | `intervention_id` | name, candidate, disease, modality, namespaces | ClinicalTrials.gov or EMA evidence with the same intervention, candidate, and disease context. |
| `TrialRecord` | `trial_id` | registry, intervention, disease, NCT namespaces | Clinical trial identity or endpoint evidence with the same NCT and parent identities. |
| `TrialDesignRecord` | `design_id` | trial, intervention, disease, nested record set | Source-pinned design evidence carrying the same design, trial, intervention, candidate, and disease ids. |
| `TrialArmRecord` | `arm_id` | trial, label, type, typed candidate/comparator role, intervention binding, source group | Exact arm identity evidence for the same design and trial. |
| `TrialPopulationRecord` | `population_id` | trial, disease, population and eligibility fields | Exact population identity evidence for the same design and trial. |
| `TrialEndpointRecord` | `endpoint_id` | trial, population, arm set, endpoint fields | Both endpoint identity evidence and assessed clinical evidence for the same design links. |

One candidate may own at most one accepted intervention. Every trial is a `ClinicalTrials.gov`
record with an `NCT[0-9]{8}` canonical id. A `trial_design_update` projects its arms, populations,
and endpoints atomically; partial nested updates do not exist.

The strict machine contract and executable synthetic example are:

- `rl_env/specs/clinical_intervention_identity.schema.json`
- `rl_env/specs/clinical_intervention_identity.example.json`

## ClinicalTrials.gov Paths

The two ClinicalTrials.gov paths have intentionally different trust levels.

### Context Search

`ctgov/search_trials` is a shaped cache/search adapter. It checks request and returned candidate,
condition, intervention, and NCT text, but it is not source pinned. A valid match may preserve
contextual observations; it cannot satisfy the default clinical `ADVANCE` gate. Identity mismatch
returns `ctgov_source_identity_mismatch`, malformed or duplicate NCT identity returns
`ctgov_trial_identity_invalid`, and no partial records are added.

### Source-Pinned Design

`pinned_evidence/clinical_trial_design` consumes a reviewed, payload-free manifest compiled from an
exact ClinicalTrials.gov API study snapshot. The provider verifies receipt SHA-256, HTTPS locator,
NCT, registry version, candidate aliases, condition, protocol arms, posted result groups,
population, endpoint measurements, denominators, statistical analysis, and posted serious-adverse-
event arm summaries. Promotion succeeds only when every parent and nested identity agrees.
Every source-level candidate alias must be the canonical candidate id/name or appear in the
candidate's pre-approved `attributes.identity_aliases`; adding a canonical name alongside an
unapproved alias does not authorize the latter. At least one source condition must likewise match
the canonical disease name or a pre-approved disease identity alias.

Version 2 supports one bounded endpoint shape: a posted primary time-to-event endpoint with
`higher_is_better` measurements, a candidate-first hazard ratio, upper confidence bound below one,
and p-value bound at most 0.05. It additionally requires exact posted serious-adverse-event
affected/at-risk counts for the same two arms, without inferring safety acceptability. Other shapes
or missing safety defer without artifacts. Full provider rules, external validation hashes, and
the matched missing-safety control are in
`docs/21_clinical_provider_ingestion.md` and
`docs/clinical_provider_validation_snapshot.json`.

## EMA Promotion

`ema/lookup` requires an accepted intervention linked to the requested candidate and disease. The
request query and at least one source-returned asset or INN must match that intervention. Accepted
EMA identifiers extend the intervention namespace; existing bindings cannot be rebound.

Withdrawal, revocation, or refusal may recommend `KILL`; suspension may recommend `HOLD`;
authorization may recommend `ADVANCE`; negated or unresolved authorization remains `DEFER`. These
are deterministic control semantics, not clinical advice.

## Stage Requirements

The default clinical `ADVANCE` gate requires all of the following from the current packet:

1. Supported `clinical_evidence_assessed` and `clinical_safety_assessed` claims and current-stage
   evidence.
2. Both evidence predicates from at least one exact source-pinned study with a valid SHA-256.
3. One qualifying intervention and linked ClinicalTrials.gov trial.
4. One qualifying atomic design with typed candidate and comparator roles, a candidate-linked arm,
   a population, a posted endpoint, and a posted serious-adverse-event record linked to those exact
   arm and population ids.
5. Existing chronology, claim, candidate, disease, target, contradiction, budget, and evidence
   reference gates.

The legacy search adapter cannot meet items 2 or 4. Readiness reports
`intervention_identity_missing`, `trial_identity_missing`, and `trial_design_identity_missing`
separately. Regulatory review can extend the accepted intervention namespace while preserving the
clinical trial and design ledgers.

## Fail-Closed Invariants

`ClinicalIdentityContinuityVerifier` blocks:

- removal or core-field rebinding of an intervention, trial, design, arm, population, endpoint,
  safety record, or safety-arm summary;
- removal or rebinding of accepted namespace and supporting-evidence links;
- multiple interventions claiming one candidate or namespace collisions across like records;
- packet records stamped with the wrong stage or trial-arm role rebinding;
- links to unknown candidates, diseases, interventions, trials, populations, or arms;
- noncanonical NCT, design, source-group, population, endpoint, or safety namespaces;
- arm-to-intervention drift, population-to-disease drift, or endpoint arm/population rebinding;
- support evidence whose predicate or biological context does not resolve the same canonical graph;
- endpoints that do not carry both identity and assessed clinical support;
- safety records that do not cover every design arm with both identity and assessed safety support.

Failures use `clinical_identity_continuity_invalid` and expose specific failure labels,
conflicting bindings, and broken record ids in verifier details.

## Serialization And Replay

All eight clinical identity record types participate in strict parsing, decision-packet updates,
immutable state ledgers, semantic promotion, projection, committed-history validation, replay
bundles, and exact final-state equality. Unknown fields, duplicate keys, missing evidence,
unsupported relations, nested identity drift, and replay drift fail closed.

## Coverage

- `tests/test_clinical_identity_continuity.py` validates the machine schema and strict parsers, then
  exercises intervention rebinding, trial namespace collision, unknown-intervention linkage, and
  support removal.
- `tests/test_clinicaltrials_gov_ingestion.py` exercises strict extraction, source/NCT/arm/analysis/
  safety mismatch rejection, payload removal, exact design promotion, atomic missing-safety defer,
  arm-role rebinding, endpoint/safety-support removal, snapshot-to-report consistency, and the matched
  `ADVANCE`/`DEFER` contract.
- `tests/test_semantic_mappings.py` verifies that the legacy search path is contextual only and that
  EMA source identity mismatches cannot terminate a program.

The one-pair balanced accuracy of 1.0 is a deterministic contract regression, not an estimate of
clinical prediction or discovery performance.

## Current Boundary

The source-pinned path establishes byte identity and a bounded registry-to-ledger transformation.
It does not certify registry truth or completeness, include source bytes in Git, reanalyze
participant-level data, adjudicate endpoint validity, generalize beyond the implemented endpoint
shape, establish safety or efficacy, compare a full clinical program, or make a regulatory
recommendation. Exact external replay requires the source bundle and reviewer job matching the
published hashes.

Run the relevant checks with:

```bash
python -m unittest tests.test_clinical_identity_continuity \
  tests.test_clinicaltrials_gov_ingestion tests.test_semantic_mappings -v
python -m unittest discover -s tests -v
```
