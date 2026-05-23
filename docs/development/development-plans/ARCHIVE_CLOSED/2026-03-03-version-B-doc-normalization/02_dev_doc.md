<!-- docs-root-migration: content moved -->
> Status: content moved; target authoritative after Wave31 archive-closed batch.
> Previous compatibility source: `development/latest-dev-docs/development-plans/ARCHIVE_CLOSED/2026-03-03-version-B-doc-normalization/02_dev_doc.md`
> Authoritative target: `docs/development/development-plans/ARCHIVE_CLOSED/2026-03-03-version-B-doc-normalization/02_dev_doc.md`
> Migration batch: `development-plans-archive-closed-wave31-batch`
> Date: 2026-05-23

# 02 Dev Doc - 2026-03-03 Version B Doc Normalization

## 1. Research
### 1.1 Online research evidence
- `https://developers.google.com/style`
  - Used for clarity and consistency baseline.
- `https://developers.google.com/style/procedures`
  - Used for step-by-step executable procedure structure.
- `https://github.com/DavidAnson/markdownlint-cli2`
  - Used as command-level reference for Markdown verification options.

### 1.2 Local research evidence
- Read existing documents in:
  - `development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-03-version-B-doc-normalization/`
  - `development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-03-version-B-atomic-plan/`
- Confirmed working scope for this round is only:
  - `01_task_doc.md`
  - `02_dev_doc.md`

### 1.3 Research output
- Standardized execution order locked as: `Research -> Task Doc -> Atomic Plan -> Build -> Verify`.
- Verification must be runnable, minimal, and reproducible.

## 2. Task Doc
- Synced with `01_task_doc.md` objective, scope, constraints, and acceptance.
- Explicitly maintained strict scope control to two files.
- Included mandatory anti-overreach boundary and minimal-change rule.

## 3. Atomic Plan

| Task ID | Status | Dependency | Gate | Result |
|---|---|---|---|---|
| DN-01 | Completed | None | Research evidence complete | Completed with online + local evidence |
| DN-02 | Completed | DN-01 | Task structure normalized | `01_task_doc.md` rewritten |
| DN-03 | Completed | DN-02 | Atomic table mandatory columns complete | Atomic table added in `01_task_doc.md` |
| DN-04 | Completed | DN-01, DN-03 | Build and Verify chapters executable | `02_dev_doc.md` rewritten |
| DN-05 | Completed | DN-04 | Verification commands executed and logged | Minimal checks executed and evidence recorded |

## 4. Build
### 4.1 Implementation
- Reorganized both files into deterministic lifecycle sections.
- Added mandatory atomic task governance fields.
- Added runnable verification command set with expected outputs.

### 4.2 Implementation boundaries
- No business code changes.
- No non-target file edits.

## 5. Verify
### 5.1 Commands (runnable)
```bash
# V1: file existence
test -f development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-03-version-B-doc-normalization/01_task_doc.md

test -f development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-03-version-B-doc-normalization/02_dev_doc.md

# V2: mandatory sequence presence in both docs
rg -n "Research|Task Doc|Atomic Plan|Build|Verify" \
  development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-03-version-B-doc-normalization/01_task_doc.md \
  development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-03-version-B-doc-normalization/02_dev_doc.md

# V3: sequence order check in 01_task_doc.md
awk '/^## 1\. Research/{a=NR}/^## 2\. Task Doc/{b=NR}/^## 3\. Atomic Plan/{c=NR}/^## 4\. Build/{d=NR}/^## 5\. Verify/{e=NR} END{exit !(a<b && b<c && c<d && d<e)}' \
  development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-03-version-B-doc-normalization/01_task_doc.md

# V4: change scope check for target files only
git diff --name-only -- \
  development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-03-version-B-doc-normalization/01_task_doc.md \
  development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-03-version-B-doc-normalization/02_dev_doc.md

# V4b: untracked/modified scope visibility
git status --short -- \
  development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-03-version-B-doc-normalization
```

### 5.2 Expected results
- V1: exit code `0` for both file checks.
- V2: both files return matched lines covering all required stage keywords.
- V3: exit code `0`, confirming ordered stage sequence.
- V4: if files are tracked, output includes only the two target file paths.
- V4b: output only includes the target folder status lines.

### 5.3 Actual results
- V1:
  - `test -f .../01_task_doc.md` -> `exit=0`
  - `test -f .../02_dev_doc.md` -> `exit=0`
- V2:
  - `rg` returned matched lines for both files, covering `Research/Task Doc/Atomic Plan/Build/Verify`.
- V3:
  - `awk` output: `ordered=1` and command exited `0`.
- V4:
  - `git diff --name-only -- <file1> <file2>` returned empty output in this run (files are currently untracked in repository state).
- V4b:
  - `git status --short -- <target-folder>` output: `?? development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-03-version-B-doc-normalization/`

## 6. Risks and boundaries
- Risk: accidental wording drift into non-actionable narrative.
- Control: keep sections command-driven and acceptance-driven.
- Boundary: no edits outside the two target files.

## 7. Dedup / Diff Statement
- Dedup: removed duplicated narrative and merged into single lifecycle path.
- Diff: upgraded from descriptive notes to executable, evidence-driven doc flow.

## 8. Next Round Draft
1. If approved, add markdown lint command based on repository toolchain.
2. If approved, add CI-friendly check snippet for the two-file gate.
3. Keep all future updates in the same five-stage lifecycle pattern.
