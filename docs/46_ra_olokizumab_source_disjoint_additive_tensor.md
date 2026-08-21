# Olokizumab RA Source-Disjoint Additive Evidence Tensor

Date: 2026-08-20  
Status: completed public-source workflow replication; not a pooled efficacy or safety conclusion

## Research Question

Can two phase 3 rheumatoid-arthritis trials for the same candidate and Week-12 ACR20 endpoint be
compiled into a provenance-preserving additive benefit-risk tensor without pooling or silently
assuming that their populations are exchangeable?

The selected pair is
[NCT02760407](https://clinicaltrials.gov/study/NCT02760407?tab=results) and
[NCT02760433](https://clinicaltrials.gov/study/NCT02760433?tab=results). Candidate identity is
bound to [ChEMBL CHEMBL1743050](https://www.ebi.ac.uk/chembl/explore/compound/CHEMBL1743050),
with the ChEMBL mechanism record linking olokizumab to human IL-6.

## Why This Pair

An official ClinicalTrials.gov API screen examined 615 completed interventional rheumatoid-
arthritis records with posted results. Thirteen trials contained 21 primary risk-difference
analyses. The selected records satisfy one narrow harmonization contract:

- the same ChEMBL candidate, olokizumab;
- olokizumab 64 mg every four weeks versus placebo;
- phase 3 rheumatoid arthritis;
- posted primary ACR20 response at Week 12;
- candidate-first source-reported `Risk Difference (RD)`;
- exact endpoint and posted serious-event arm identities;
- pairwise-disjoint source captures.

The populations are intentionally not collapsed. `NCT02760407` enrolled participants inadequately
controlled by methotrexate, whereas `NCT02760433` enrolled participants inadequately controlled by
a TNF-alpha inhibitor. The mapping declares endpoint-family equivalence only. It does not declare
population homogeneity, exchangeability, or a pooled estimand.

## Scale Contract

ClinicalTrials.gov reports these ACR20 arm values as participant counts and the risk differences as
proportions. The implementation now distinguishes this representation from a source that reports
percentage-point arm values:

| Source endpoint unit | Retained effect scale | Decision precision scale |
| --- | --- | --- |
| Bounded percent unit | percentage points | percentage points |
| Binary count unit such as `Participants` | proportion in `[-1, 1]` | percentage points after multiplying CI width by 100 |

Raw source estimates and confidence limits are never rescaled in the synthesis record. Only the
decision precision metric is normalized to percentage points. Count-valued endpoints must contain
integer arm measurements between zero and their declared denominators.

## Executed Tensor

| Trial | Population context | Week-12 ACR20 | Source RD (97.5% CI) | CI width | Serious events |
| --- | --- | --- | --- | --- | --- |
| `NCT02760407` | MTX inadequate response | 342/479 vs 108/243 | 0.270 (0.183 to 0.352) | 16.9 pp | 20/477 vs 12/243 |
| `NCT02760433` | TNF-inhibitor inadequate response | 96/161 vs 28/69 | 0.190 (0.030 to 0.337) | 30.7 pp | 6/160 vs 0/69 |

Both source-pinned provider runs committed and promoted independently. A reviewer-declared mapping
then bound the two exact endpoint and safety ledgers, and the production synthesis compiler emitted
two non-pooled study cells with two distinct source hashes. Exact decision-package replay returned
zero validation errors.

The policy requires two independent trials, no risk-difference CI wider than 35 percentage points,
and at least 60 safety participants per arm. Both benefit intervals and both exposure checks meet
those workflow thresholds. The observed serious-event direction is lower in `NCT02760407` and
higher in `NCT02760433`. The compiler emits the stronger blocking
`higher_observed_serious_event_risk` gap rather than adding a redundant direction-conflict gap, so
the bounded next-action plan is `HOLD` with one source-disjoint safety follow-up action.

## Provenance

The public machine snapshot is
`docs/ra_olokizumab_additive_tensor_validation_snapshot.json`. It retains bounded aggregates,
source and artifact hashes, typed decisions, and explicit negative claims. Source bytes, review
jobs, manifests, full program states, and the decision package remain outside Git and Hugging Face.

| Artifact | SHA-256 |
| --- | --- |
| `NCT02760407` source | `62415b71d08c8d5ccbe0b03be45bad4ad8bd734d43de461be52278314fbb59d8` |
| `NCT02760433` source | `b087ef355db040907d7ae81c34b34fec7f9b4743df7414c8f519eee6e3abc051` |
| Mapped state | `04c803c75f49f229d0d81bb153909bd6a5ef1596e6e567ab4d5bfd66cc94ccde` |
| Synthesized state | `68855c37f10ad4892206c7537eac6e037da1ae017f293ed0aa39b02f0bf09874` |
| Decision package | `6d8d20000e7fe6c78254bc3e16152817b154261e9cd5a762eb49cb937d5188d9` |
| Run summary | `ea0da4f3408496ab4504fc7b1d0b7ec70bae8267886f64fb030570214bef2ed0` |

## Interpretation Boundary

This is the project's first real source-disjoint additive multi-trial tensor. It demonstrates
identity continuity, source-scale preservation, endpoint harmonization, non-pooling, typed safety
gaps, and deterministic replay. It does not reproduce participant-level analyses, estimate a
combined effect, establish comparative efficacy or safety, validate population transportability,
infer clinical acceptability, or recommend treatment.
