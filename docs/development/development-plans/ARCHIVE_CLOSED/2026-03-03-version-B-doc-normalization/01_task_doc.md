<!-- docs-root-migration: content moved -->
> Status: content moved; target authoritative after Wave31 archive-closed batch.
> Previous compatibility source: `development/latest-dev-docs/development-plans/ARCHIVE_CLOSED/2026-03-03-version-B-doc-normalization/01_task_doc.md`
> Authoritative target: `docs/development/development-plans/ARCHIVE_CLOSED/2026-03-03-version-B-doc-normalization/01_task_doc.md`
> Migration batch: `development-plans-archive-closed-wave31-batch`
> Date: 2026-05-23

# 01 Task Doc - 2026-03-03 Version B Doc Normalization

## 1. Research
### 1.1 Online research
- Source A: Google Developer Documentation Style Guide (`https://developers.google.com/style`)
  - Takeaway: Technical docs should be clear, consistent, and project style takes precedence.
- Source B: Google Style Guide - Procedures (`https://developers.google.com/style/procedures`)
  - Takeaway: Execution steps should be numbered, action-oriented, and verifiable.
- Source C: `markdownlint-cli2` README (`https://github.com/DavidAnson/markdownlint-cli2`)
  - Takeaway: Markdown structure can be validated with direct CLI commands.

### 1.2 Local research
- Checked current folder status and baseline docs under:
  - `development/latest-dev-docs/development-plans/CURRENT_DEV/`
  - `development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-03-version-B-atomic-plan/`
- Confirmed this round is limited to two files in:
  - `development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-03-version-B-doc-normalization/`

### 1.3 Research conclusion
- Enforce one deterministic sequence: `Research -> Task Doc -> Atomic Plan -> Build -> Verify`.
- Keep outputs executable and testable.
- Keep scope strictly within the two target documents.

## 2. Task Doc
### 2.1 Objective
Normalize Version B documentation to project-grade quality with explicit execution path, atomic tasks, and reproducible verification evidence.

### 2.2 Scope
- In scope:
  - `development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-03-version-B-doc-normalization/01_task_doc.md`
  - `development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-03-version-B-doc-normalization/02_dev_doc.md`
- Out of scope:
  - Any business code, test logic, scripts, or non-target documents.

### 2.3 Constraints
- Work only in current project directory.
- Modify only the two target files.
- No knowledge-pool management actions in content.
- Sequence is mandatory and must be visible in final docs.

### 2.4 Acceptance criteria
- Both files contain a full closed loop: `Research -> Task Doc -> Atomic Plan -> Build -> Verify`.
- `01_task_doc.md` contains atomic task table with: dependency, gate, owner, artifact.
- `02_dev_doc.md` contains executable verification commands with expected and actual results.
- No file changes outside the two target files.

## 3. Atomic Plan

| Task ID | Goal | Input | Output | Dependency | Gate | Owner | Artifact |
|---|---|---|---|---|---|---|---|
| DN-01 | Complete online and local research capture | User constraints, existing two docs, baseline docs | Research section updated in both docs | None | Research evidence is concrete and source-backed | Doc Executor | Updated Research sections |
| DN-02 | Rewrite task document to normalized project format | DN-01 output | Normalized `01_task_doc.md` | DN-01 | Includes objective/scope/constraints/acceptance and mandatory sequence | Doc Executor | `01_task_doc.md` |
| DN-03 | Build atomic task table for execution governance | DN-02 output | Atomic task table with required columns | DN-02 | Table contains dependency/gate/owner/artifact for every task | Doc Executor | Atomic task table in `01_task_doc.md` |
| DN-04 | Rewrite development document with implementation and verification details | DN-01, DN-03 outputs | Normalized `02_dev_doc.md` | DN-01, DN-03 | Contains Build and Verify chapters with runnable commands and expected results | Doc Executor | `02_dev_doc.md` |
| DN-05 | Run minimal document validation and backfill evidence | DN-04 output | Command logs and pass/fail conclusions recorded | DN-04 | Commands execute successfully and results are written to `02_dev_doc.md` | Doc Executor | Verify section evidence |

## 4. Build
### 4.1 Build method
- Apply minimal edits to two target files only.
- Keep language precise and action-oriented.
- Use deterministic headings and tables for repeatability.

### 4.2 Build deliverables
- A normalized task document with atomic breakdown.
- A normalized development document with execution and verification evidence.

## 5. Verify
### 5.1 Verification policy
- Only document/structure checks.
- No business logic execution.

### 5.2 Minimum checks
1. File existence checks for two target files.
2. Mandatory section and sequence checks.
3. Change scope checks limited to two files.

### 5.3 Expected result
- All checks pass.
- Evidence is recorded in `02_dev_doc.md`.

## 6. Risks and boundaries
- Risk: Over-expanding scope to non-target files.
- Boundary control: Run file-scoped verification commands and keep edits in place only.

## 7. Definition of done
- Two documents are normalized, executable, and verifiable.
- Sequence and evidence are complete.
- Scope control is preserved.
