# 2026-03-03 Version A Doc Normalization - Dev Doc

## 1. Research（联网+本地）
### 1.1 Local
- Checked current target files and baseline structure under `development/latest-dev-docs/development-plans/`.
- Confirmed task boundary: only two markdown files are in scope.

### 1.2 Online
- CommonMark spec reference for fenced code blocks and structural markdown behavior.
- markdownlint official rule set reference for heading/list/code fence quality checks.

### 1.3 Research conclusion
- Use phase-first structure and explicit acceptance criteria.
- Keep command blocks runnable without project runtime dependencies.

## 2. Task Doc
- Rewrote `01_task_doc.md` with objective/scope/acceptance/risk controls.
- Made mandatory sequence explicit: `Research -> Task Doc -> Atomic Plan -> Build -> Verify`.

## 3. Atomic Plan
- Added executable atomic task table in `01_task_doc.md`.
- Added required columns: dependency, gate, owner, deliverable.
- Added gate definitions `G0` to `G4` for closure traceability.

## 4. Build（实施）
### 4.1 Changes implemented
- Updated `01_task_doc.md` to normalized project-spec level.
- Updated `02_dev_doc.md` with implementation + verification procedure and closure package.

### 4.2 Implementation boundaries
- No business code changes.
- No edits outside the two target files.
- No workspace memory notes were created.

## 5. Verify（命令、预期结果、实际结果）

### 5.1 File existence check
Command:
```bash
test -f development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-03-version-A-doc-normalization/01_task_doc.md && echo "PASS: 01 exists"
test -f development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-03-version-A-doc-normalization/02_dev_doc.md && echo "PASS: 02 exists"
```
Expected:
- Both commands print `PASS` lines.

Actual:
- `PASS: 01 exists`
- `PASS: 02 exists`

### 5.2 Forbidden-term check
Command:
```bash
if perl -ne 'if(/\x{5165}\x{6C60}|\x{7D22}\x{5F15}|\x{5F52}\x{6863}|\x{6CBB}\x{7406}/){print "$ARGV:$.:$_"; $f=1} END{exit($f?0:1)}' development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-03-version-A-doc-normalization/01_task_doc.md development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-03-version-A-doc-normalization/02_dev_doc.md; then
  echo "FAIL: forbidden terms found"
else
  echo "PASS: forbidden terms not found"
fi
```
Expected:
- Output contains `PASS: forbidden terms not found`.

Actual:
- `PASS: forbidden terms not found`

### 5.3 Mandatory-sequence check
Command:
```bash
awk '
/^## 1\. Research（联网\+本地）$/ {r=NR}
/^## 2\. Task Doc$/ {t=NR}
/^## 3\. Atomic Plan$/ {a=NR}
/^## 4\. Build（实施）$/ {b=NR}
/^## 5\. Verify（命令、预期结果、实际结果）$/ {v=NR}
END {
  if (r && t && a && b && v && r<t && t<a && a<b && b<v) {
    print "PASS: sequence order is valid"
  } else {
    print "FAIL: sequence order is invalid"
    exit 1
  }
}
' development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-03-version-A-doc-normalization/02_dev_doc.md
```
Expected:
- Output: `PASS: sequence order is valid`.

Actual:
- `PASS: sequence order is valid`

### 5.4 Scope-limited diff check
Command:
```bash
git status --short -- development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-03-version-A-doc-normalization/01_task_doc.md development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-03-version-A-doc-normalization/02_dev_doc.md
```
Expected:
- Output only contains two target file paths (e.g., `??` for untracked in this round).

Actual:
- `?? development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-03-version-A-doc-normalization/01_task_doc.md`
- `?? development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-03-version-A-doc-normalization/02_dev_doc.md`

## 6. References
- CommonMark Spec: https://spec.commonmark.org/
- markdownlint (official): https://github.com/DavidAnson/markdownlint
