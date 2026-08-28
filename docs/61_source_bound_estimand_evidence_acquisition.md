# Source-Bound Estimand Evidence Acquisition

Date: 2026-08-27
Status: implemented public research artifact; no human estimand review performed

## Research Question

Can the 49 endpoint pairs that passed structural preflight be converted into a reproducible,
source-bound review queue without treating them as equivalent endpoints?

The answer is yes for evidence retrieval, and no for semantic adjudication. This increment binds
the exact candidate graph and preflight packet to the complete protocol/SAP inventory declared in
the same ClinicalTrials.gov source records. It extracts bounded candidate page locations for the
five preregistered estimand dimensions while withholding PDF text and preserving every human gate.

## Contract

The compiler accepts:

1. An exact cross-trial endpoint candidate graph.
2. Its exact endpoint/estimand preflight packet.
3. The exact ClinicalTrials.gov registry bytes for every trial.
4. Every protocol or SAP declared by those registry records.
5. Preregistered document SHA-256 values and a maximum of five page cues per endpoint-dimension.

It then verifies the registry source hash, NCT identity, complete protocol/SAP inventory, document
role, filename, label, document date, upload date, byte size, PDF signature, PDF parse, page count,
and PDF SHA-256. Any mismatch stops compilation before output.

For each unique endpoint appearing in a `ready_for_endpoint_estimand_review` pair, the compiler
creates one record for each fixed dimension:

- `treatment_condition`
- `population`
- `variable`
- `intercurrent_event_strategy`
- `population_level_summary`

Candidate pages are ranked by fixed lexical anchors. Variable retrieval can additionally use an
exact endpoint-title cue, a bounded distinctive-title-token cue, and an exact time-frame cue. A
public page reference contains only document identity, PDF hash, page number, normalized page-text
hash, retrieval rank, and matched anchor IDs. It contains no page text or excerpt.

## Exact Source Documents

| Trial | Document | Role | Document date | Bytes | Pages | Text pages | SHA-256 |
|---|---|---|---:|---:|---:|---:|---|
| NCT02760368 | `Prot_SAP_000.pdf` | protocol + SAP | 2018-03-30 | 1,887,599 | 181 | 181 | `f44519001749ffe648c79e6d2e66474e9f2779025b2085726def415ef899a2e7` |
| NCT02760407 | `Prot_SAP_000.pdf` | protocol + SAP | 2018-05-28 | 1,247,478 | 173 | 172 | `1b9287681119f071323663b32533fa5eff0195da50bece3fb5e057d71b11cd35` |
| NCT01647516 | `Prot_000.pdf` | protocol | 2019-05-03 | 872,936 | 90 | 82 | `e8d22817a7019ded0b8998c9d8578e444ec91af75355592108b5a6b72f10cbc3` |
| NCT01647516 | `SAP_001.pdf` | SAP | 2014-09-23 | 672,972 | 47 | 43 | `6a646ff761268b9cc00b6762529f91d4ea93c7b39af5e4f2b152b46f52a2d47b` |
| NCT02435992 | `Prot_000.pdf` | protocol | 2019-07-26 | 8,976,663 | 117 | 39 | `25fb525e264e73aa5ce0f5d0eda4830aee67a883cc4e09573ff76acd7fed3746` |
| NCT02435992 | `SAP_001.pdf` | SAP | 2019-06-18 | 7,714,787 | 85 | 46 | `e40013524156e92f73046380c68ebd9d6bd4f1ce87eaddeca64afab819cfe4d0` |

The six PDFs total 693 pages and 21,372,435 bytes. They remain external to Git and Hugging Face;
the public packets contain only provenance metadata and page hashes.

## Exact Results

| Cohort | All pairs | Preflight-ready | Preflight-blocked | Unique ready endpoints | Evidence records | Page cues |
|---|---:|---:|---:|---:|---:|---:|
| RA olokizumab MTX-IR | 35 | 35 | 0 | 12 | 60 | 300 |
| UC ozanimod | 110 | 14 | 96 | 9 | 45 | 209 |
| Total | 145 | 49 | 96 | 21 | 105 | 509 |

All 105 endpoint-dimension records had at least one lexical candidate page. This is retrieval
coverage, not evidence sufficiency. RA reached the five-page cap for every record. UC produced 45
cues each for treatment condition, population, and intercurrent-event strategy, and 37 each for
variable and population-level summary. The lower UC counts mean some records had fewer than five
candidate pages, not that their estimands were resolved or disproved.

The UC source-completion boundary is unchanged: 96 pairs remain `preflight_blocked`, receive no
endpoint evidence records, and are neither excluded nor promoted. The 49 ready pairs reference ten
normalized evidence IDs each, one for every left/right endpoint and estimand dimension.

Packet integrity SHA-256:

- RA: `5c490580d7fada91c2646d2167a1ea950bde5da2e7d69aeba2a5620804c5db42`
- UC: `f4197c53faa2cf6eadaf9e1d69b4e145b44af8bf5a8dfdfed719453ede8ceceb`

## Artifacts

- `agentic_drug_discovery/clinicaltrials_gov_estimand_evidence_acquisition.py`
- `scripts/audit/compile_clinicaltrials_gov_estimand_evidence_acquisition.py`
- `rl_env/specs/clinicaltrials_gov_estimand_evidence_acquisition_spec.schema.json`
- `rl_env/specs/clinicaltrials_gov_estimand_evidence_acquisition_packet.schema.json`
- `rl_env/specs/clinicaltrials_gov_estimand_evidence_acquisition_spec.example.json`
- `docs/ra_olokizumab_mtx_ir_estimand_evidence_acquisition_spec.json`
- `docs/ra_olokizumab_mtx_ir_estimand_evidence_acquisition_packet.json`
- `docs/uc_ozanimod_estimand_evidence_acquisition_spec.json`
- `docs/uc_ozanimod_estimand_evidence_acquisition_packet.json`

Run `python scripts/audit/compile_clinicaltrials_gov_estimand_evidence_acquisition.py --help`
for the exact-source CLI. Registry JSON and PDF paths are repeated assignments; every source also
requires an expected SHA-256. Outputs are written only after full compile and independent replay.

## Interpretation Boundary

`candidate_pages_found` means that a fixed lexical retrieval rule found a page worth inspection.
It does not mean the page contains sufficient evidence, the evidence agrees across sources, or the
endpoint pair is equivalent. Endpoint text, PDF text, excerpts, semantic sufficiency, reviewer
approval, endpoint equivalence, estimand equivalence, benefit-risk synthesis, and treatment choice
all remain absent or false.

## Next Research Step

The next machine-executable stage should compile contradiction-aware claims from the local page
queue. Each claim should preserve document, page, and excerpt hashes; distinguish explicit,
implicit, absent, and conflicting evidence; and require a reviewer decision for every dimension.
Without human review, the productive next experiment is adversarial claim extraction and
cross-document contradiction detection, not automatic pair approval.
