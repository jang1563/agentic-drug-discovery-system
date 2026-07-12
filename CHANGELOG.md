# Changelog

All notable public-surface changes to this repository will be documented here.

## Unreleased

- Added public release boundary documentation, release manifest, security policy, contribution guide, citation metadata, license, and archive metadata.
- Added callable tool/database adapters (Open Targets, ChEMBL, ClinicalTrials.gov, openFDA, EMA EPAR) and multi-stage flow orchestrators (discovery_flow, episode_flow) for the first public decision-environment surface.
- Added a local RDKit-based molecular-property adapter (QED, MW, logP, H-bond donors/acceptors, Lipinski) giving the compound-design stage a computable, no-GPU druglikeness signal.
- Added `docs/12_scd_vertical_slice.md` documenting the audited end-to-end sickle cell disease (SCD) retrospective benchmark slice and prospective decision-support demo.
- Added `docs/13_target_id_governance_node.md` and
  `docs/public_evidence_summary.json` as small-N, aggregate-only scientific claim
  anchors with explicit provenance limits.
- Added the installable `benchmark/` scorer and tests for the separately hosted
  clinical-trial decision dataset; the external dataset's Croissant metadata is
  intentionally excluded from this artifact mirror.
- Added `scripts/audit/validate_vertical_slice_doc.py` to keep public benchmark numbers caveats-first and small-N scoped.
- Added `docs/release_trust_report.md` and a commit-object-based
  `scripts/audit/build_hf_release_package.py` so each Hugging Face payload is
  tied to an exact source commit/tree with per-file SHA-256 and byte sizes.
- Disambiguated stopped/withdrawn/revoked programs from serious safety signals
  on still-approved assets in both decision prompts.
- Strengthened local and CI release-audit gates for sensitive content, generated artifacts, machine-specific breadcrumbs, and public metadata completeness.
