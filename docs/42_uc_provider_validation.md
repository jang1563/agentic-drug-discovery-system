# Ulcerative Colitis Provider Validation

Status: externally executed on 2026-08-20 against public ClinicalTrials.gov records

Scope: two source-pinned ozanimod/RPC1063 induction endpoints in ulcerative colitis
(`MONDO:0005101`), with exact arm, analysis, and serious-adverse-event identities

Machine snapshot: `docs/uc_clinical_provider_validation_snapshot.json`

## Research Question

Can the clinical provider path retain a structurally valid but uncertain result instead of
selecting only favorable evidence, while still allowing a clearly favorable result to advance?

The executable answer is yes. Both studies pass the same extraction and promotion contract. The
effect interval determines the decision after promotion: `benefit` recommends `ADVANCE`, while
`null_or_uncertain` and `harm` recommend `HOLD`. A hold commits the evidence and atomic trial
design; it does not erase the study.

## External Runs

| Field | Phase 2 | Phase 3 |
| --- | --- | --- |
| Trial | `NCT01647516` | `NCT02435992` |
| Registry `versionHolder` | `2026-08-20` | `2026-08-20` |
| Candidate identity | `Ozanimod` -> `OZANIMOD` | `RPC1063` -> `OZANIMOD` |
| Treatment phase | Induction, Week 8 | Induction, Week 10 |
| Source analysis groups | `OG000`, `OG002` | `OG000`, `OG001` |
| Odds ratio | `3.262` | `3.586` |
| 95% confidence interval | `0.969` to `10.984` | `1.938` to `6.636` |
| P-value | `= 0.0482` | `= 0.0001` |
| Computed direction | `null_or_uncertain` | `benefit` |
| Accepted decision | `HOLD` | `ADVANCE` |
| Final stage | `clinical_strategy` | `regulatory_postmarket` |
| Trial design retained | Yes | Yes |
| New clinical evidence | 8 events | 8 events |

The Phase 2 source lists placebo (`OG000`) before ozanimod 1 mg (`OG002`). The provider preserves
that registry order and resolves candidate/comparator semantics from typed roles rather than
assuming that array position defines the contrast. Its p-value is below 0.05, but the confidence
interval crosses 1; the interval therefore remains `null_or_uncertain` and the program is held.

The Phase 3 interval lies fully above 1 under the preregistered odds-ratio
`higher_is_better` contract. That result is classified as `benefit` and satisfies the configured
clinical advance gate. This is a gate-execution result, not an independent efficacy conclusion.

## Safety Identity

The Phase 2 induction safety selection maps placebo `EG000` (`4/65` participants with serious
adverse events) and ozanimod 1 mg `EG002` (`2/67`). The Phase 3 induction selection maps RPC1063
`EG000` (`17/429`) and placebo `EG001` (`11/216`). These are posted aggregate participant counts.
The provider does not infer event attribution, comparative safety, safety acceptability, or a
benefit-risk verdict from them.

Endpoint and safety records now carry the same required `treatment_phase`, limited to
`induction`, `maintenance`, or `not_applicable`. A phase mismatch fails before promotion. Bounded
title normalization removes only phase qualifiers, dose-unit words, the exact `on-treatment`
qualifier, and the `HCl`/`hydrochloride` spelling difference; exact source group ids, roles,
counts, and selected source titles remain pinned.

## Artifact Identity

Raw source bytes and reviewer jobs remain outside Git. The public snapshot stores only canonical
hashes and bounded selected values.

| Artifact | `NCT01647516` SHA-256 | `NCT02435992` SHA-256 |
| --- | --- | --- |
| Exact source JSON | `ce2687e2ebf865d850ed90d58375773c1cdfadb60109771db94c6bccd88d66ff` | `fa48160bf981705439b8c3a759a2a17fbedead3d77cb3ee484afaeef16dd533c` |
| Canonical reviewer job | `b8810042afc1c18ebb0fdc7753c486befffae22ed6783b9cc2996d3d6368ad6f` | `9e0ba1fd2c422f068014774836780f12e23afb7275aee60579f4eb6f874cf1bd` |
| Canonical extracted job | `e82bdc1c09f4bafab3493cc7df0999a27853af1c7a9ebd395ab709de46167672` | `7a1d3b7103793a7c4bb99d83c4ddba7128f798ffb4eb3a2ca4355377505efbc8` |
| Canonical manifest | `cc6db22feffac8ade299d906cafb05fbbbe91dd1320746e238d2ca70d11a8624` | `75a7e76d802a051a013fb95a726d5be032382af479ecb124bbd67f59f10f3f95` |

## Harmonization Boundary

This run does not pool the two odds ratios. The trials differ in phase, endpoint time, population
wording, registry arm order, and safety follow-up. `NCT02435992` also contains a maintenance
endpoint after re-randomization; that population and its maintenance safety groups are not treated
as interchangeable with induction participants in this validation. A separate phase-bound run is
documented in `docs/43_uc_phase_population_alignment.md` and remains non-pooled.

The result establishes four implemented properties:

1. Valid uncertain evidence survives ingestion and promotion.
2. Decision direction is computed from the pinned interval, not a reviewer-authored significance
   label or arm order.
3. Endpoint and safety treatment phases cannot silently cross.
4. Public artifacts remain payload-free and require external bytes and jobs for exact replay.

It does not establish pooled efficacy, safety acceptability, participant-level validity,
cross-trial exchangeability, regulatory readiness, clinical utility, or prospective discovery
performance.
