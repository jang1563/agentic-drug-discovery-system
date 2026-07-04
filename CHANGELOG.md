# Changelog

All notable public-surface changes to this repository will be documented here.

## Unreleased

- Added public release boundary documentation, release manifest, security policy, contribution guide, citation metadata, license, and archive metadata.
- Added callable tool/database adapters (Open Targets, ChEMBL, ClinicalTrials.gov, openFDA, EMA EPAR) and multi-stage flow orchestrators (discovery_flow, episode_flow) for the first public decision-environment surface.
- Added a local RDKit-based molecular-property adapter (QED, MW, logP, H-bond donors/acceptors, Lipinski) giving the compound-design stage a computable, no-GPU druglikeness signal.
- Added `docs/12_scd_vertical_slice.md` documenting the validated end-to-end sickle cell disease (SCD) retrospective benchmark slice and prospective decision-support demo.
- Added `scripts/audit/validate_vertical_slice_doc.py` to keep public benchmark numbers caveats-first and small-N scoped.
- Added `docs/release_trust_report.md` and `scripts/audit/build_hf_release_package.py` to make the public trust surface and Hugging Face mirror build path easier to audit.
- Strengthened local and CI release-audit gates for sensitive content, generated artifacts, machine-specific breadcrumbs, and public metadata completeness.
