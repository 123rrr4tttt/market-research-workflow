<!-- docs-root-migration: content moved -->
> Status: content moved; target authoritative after Wave31 archive-closed batch.
> Previous compatibility source: `development/latest-dev-docs/development-plans/ARCHIVE_CLOSED/2026-03-04-r8-c-minimal-slice/README.md`
> Authoritative target: `docs/development/development-plans/ARCHIVE_CLOSED/2026-03-04-r8-c-minimal-slice/README.md`
> Migration batch: `development-plans-archive-closed-wave31-batch`
> Date: 2026-05-23

# R8 C-Line Minimal Slice (2026-03-04)

## Scope
- Track a low-risk kickoff slice for R8 in project C.
- Restrict this slice to workflow governance documentation only.
- Avoid backend/frontend logic changes in this commit.

## This Slice
- Add a standalone R8 kickoff note under `development/latest-dev-docs/development-plans/CURRENT_DEV/`.
- Define a strict next-batch trigger based on repository cleanliness and artifact readiness.

## Rollback
- Safe rollback target: revert this single-file commit.

## Next Batch Trigger
- Trigger when all conditions are met:
  - Current repository changes are triaged into explicit include/exclude sets.
  - Pre-release scripts/docs touched in previous rounds are mapped to owners.
  - A minimal executable task list (<=3 atomic tasks) is confirmed for R8 batch-2.
