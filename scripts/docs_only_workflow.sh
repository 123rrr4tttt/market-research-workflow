#!/usr/bin/env bash
set -euo pipefail

TARGET_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATE_TAG="$(date +%Y-%m-%d)"
PKG_NAME="${DATE_TAG}-target-project-init-r1-docs-only"
PROJECT_ID="$(basename "$TARGET_ROOT")"
OPENCLAW_ROOT_DEFAULT="/Users/wangyiliang/Desktop/openclaw"
OPENCLAW_ROOT="${OPENCLAW_ROOT:-$OPENCLAW_ROOT_DEFAULT}"

usage() {
  cat <<USAGE
usage: $0 [--package-name <name>] [--openclaw-root <path>]

Generate docs-only workflow with split workspaces:
- L1/L2 docs -> openclaw workspace
- L3/L4 docs (plan/atomic/subagent/report) -> target project workspace
- no runtime dispatch/gate/atomic execution
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --package-name) PKG_NAME="$2"; shift 2 ;;
    --openclaw-root) OPENCLAW_ROOT="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown arg: $1" >&2; exit 1 ;;
  esac
done

[[ -d "$OPENCLAW_ROOT" ]] || { echo "openclaw root not found: $OPENCLAW_ROOT" >&2; exit 2; }

L12_DIR="$OPENCLAW_ROOT/docs/implementation/projects/$PROJECT_ID/${DATE_TAG}-l1l2-docs-only"
L34_DIR="$TARGET_ROOT/development/latest-dev-docs/development-plans/CURRENT_DEV/$PKG_NAME"

mkdir -p "$L12_DIR" "$L34_DIR"
TS="$(date '+%Y-%m-%d %H:%M:%S %Z')"
L34_DOC_STYLE="target-project-dev-doc-v2-l2l3-simplified"
TARGET_REMOTE="$(git -C "$TARGET_ROOT" remote get-url origin 2>/dev/null || echo "N/A")"
OPENCLAW_REMOTE="$(git -C "$OPENCLAW_ROOT" remote get-url origin 2>/dev/null || echo "N/A")"
TARGET_BRANCH="$(git -C "$TARGET_ROOT" rev-parse --abbrev-ref HEAD 2>/dev/null || echo "N/A")"
TARGET_HEAD="$(git -C "$TARGET_ROOT" rev-parse --short HEAD 2>/dev/null || echo "N/A")"
TARGET_DIRTY_COUNT="$(git -C "$TARGET_ROOT" status --porcelain 2>/dev/null | wc -l | tr -d ' ')"
WORKFLOW_SAMPLE="$(cd "$TARGET_ROOT" && rg --files | rg '(workflow|ingest|graph)' | head -n 10 | sed 's/^/- /' || true)"
API_SAMPLE="$(cd "$TARGET_ROOT" && rg --files | rg '^main/backend/app/api/' | head -n 8 | sed 's/^/- /' || true)"

# Cleanup stale files from previous same-day template variants.
rm -f \
  "$L12_DIR/02_r1-doc-package-${DATE_TAG}.md" \
  "$L12_DIR/03_research-report-${DATE_TAG}.md" \
  "$L12_DIR/04_atomic-task-list-${DATE_TAG}.md" \
  "$L34_DIR/06_l3-to-l2-summary-${DATE_TAG}.md" \
  "$L34_DIR/L4_EXECUTION_REPORT.md"

# L1/L2 in openclaw
cat > "$L12_DIR/01_initialization-baseline-and-scope-${DATE_TAG}.md" <<DOC
# Initialization Baseline and Scope (L1)

- generated_at: $TS
- workspace: openclaw
- target_project: $TARGET_ROOT
- stage: L1
- mode: docs-only

## Goal
- Establish split-workspace baseline for docs-only workflow.

## Scope
- Included: L1/L2 docs in openclaw, L3 docs in target project.
- Excluded: runtime dispatch, gate enforcement, production execution.

## Inputs
- target_root: $TARGET_ROOT
- openclaw_root: $OPENCLAW_ROOT
- package_name: $PKG_NAME
- target_branch: $TARGET_BRANCH
- target_head: $TARGET_HEAD
- target_dirty_files: $TARGET_DIRTY_COUNT

## Acceptance
- L1/L2 package exists under openclaw path.
- L3 package exists under target project path.
- Cross-workspace pointers are present.
DOC

cat > "$L12_DIR/02_l2-to-l3-task-brief-${DATE_TAG}.md" <<DOC
# L2 to L3 Task Brief (${DATE_TAG})

- generated_at: $TS
- workspace: openclaw
- stage: L2
- mode: docs-only

## L2 Responsibility (Simplified)
- L2 only provides completion targets for L3.
- L2 does not author development plan directly.
- L2 does not execute sub-agents directly.

## L3 Required Outputs
1. Development plan document.
2. Atomic task list document.
3. Sub-agent dispatch and return-field spec document.
4. L4 execution report document (docs-only envelope).

## L2 Post-L3 Responsibility
- L2 receives L3 feedback and project changes.
- L2 writes controller return + workspace record directly.

## L3 Must Read Norms
- $TARGET_ROOT/development/latest-dev-docs/README.md
- $TARGET_ROOT/codex_settings/AGENTS.md

## Runtime Snapshot
- target_branch: $TARGET_BRANCH
- target_head: $TARGET_HEAD
- dirty_file_count: $TARGET_DIRTY_COUNT
DOC

cat > "$L12_DIR/03_l2-controller-sync-template-${DATE_TAG}.md" <<DOC
# L2 Controller Sync Template (${DATE_TAG})

- generated_at: $TS
- workspace: openclaw
- stage: L2
- mode: docs-only

## Inputs From L3
- $L34_DIR/03_l3-development-plan-${DATE_TAG}.md
- $L34_DIR/04_l3-atomic-task-list-${DATE_TAG}.md
- $L34_DIR/05_l3-subagent-dispatch-record-${DATE_TAG}.md
- $L34_DIR/L4_EXECUTION_REPORT.md

## L2 Return To Main Controller
- project_version_folder: <to-fill>
- delivered_tasks: <to-fill>
- changed_docs: <to-fill>
- residual_risks: <to-fill>
- next_action: <to-fill>
DOC

# Prompt-first canonical docs (L1/L2)
cat > "$L12_DIR/L1_MASTER_PLAN.md" <<DOC
# L1_MASTER_PLAN

- generated_at: $TS
- authoring_layer: L1
- workspace: openclaw
- result: docs-initialized
- decision: continue

## goal
- Establish split workspace docs workflow and initialization baseline.

## scope
- include: L1/L2 docs in openclaw, L3/L4 docs in target project.
- exclude: runtime execution and production write operations.

## forbidden
- Cross-repo code mutation.
- Runtime dispatch execution in docs-only mode.

## acceptance
- Required docs are generated in both workspaces.
- Pointers between L1/L2 and L3/L4 docs are valid.

## rollback_ref
- remove generated package folders for this run.
DOC

cat > "$L12_DIR/L1_CONTROL_PACK.yaml" <<DOC
generated_at: "$TS"
authoring_layer: "L1"
project_id: "$PROJECT_ID"
target_root: "$TARGET_ROOT"
openclaw_root: "$OPENCLAW_ROOT"
goal: "Initialize prompt-first docs workflow"
scope:
  include:
    - "L1/L2 docs in openclaw"
    - "L3/L4 docs in target project"
  exclude:
    - "runtime dispatch"
    - "atomic execution"
forbidden:
  - "cross-workspace code mutation"
  - "direct codex runtime execution"
acceptance:
  - "all required docs generated"
  - "cross-workspace references valid"
rollback_ref: "delete generated package directories"
handoff_to_l2: "$L12_DIR/L2_ORCHESTRATION_PLAN.md"
DOC

cat > "$L12_DIR/L2_ORCHESTRATION_PLAN.md" <<DOC
# L2_ORCHESTRATION_PLAN

- generated_at: $TS
- authoring_layer: L2
- workspace: openclaw
- result: orchestration-pack-ready
- decision: handoff_to_l3

## task_objectives
1. L3 writes development plan from norms.
2. L3 writes atomic task list.
3. L3 writes sub-agent dispatch package.
4. L4 docs-only execution report is generated.

## dependencies
- L1_CONTROL_PACK.yaml
- 02_l2-to-l3-task-brief-${DATE_TAG}.md

## doc_norm_reference
- $TARGET_ROOT/development/latest-dev-docs/README.md
- $TARGET_ROOT/codex_settings/AGENTS.md

## quality_bar
- Fields complete: result/changed_files/verification/risks/decision.
- Include authoring_layer/artifact_manifest/doc_delta in L3/L4 outputs.

## rollback_ref
- remove generated files under:
  - $L12_DIR
  - $L34_DIR
DOC

cat > "$L12_DIR/L2_ORCHESTRATION_PACK.yaml" <<DOC
generated_at: "$TS"
authoring_layer: "L2"
project_id: "$PROJECT_ID"
task_objectives:
  - "Write development plan"
  - "Write atomic task list"
  - "Write sub-agent dispatch record"
  - "Generate docs-only execution report"
dependencies:
  - "$L12_DIR/L1_CONTROL_PACK.yaml"
  - "$L12_DIR/02_l2-to-l3-task-brief-${DATE_TAG}.md"
doc_norm_reference:
  - "$TARGET_ROOT/development/latest-dev-docs/README.md"
  - "$TARGET_ROOT/codex_settings/AGENTS.md"
quality_bar:
  - "mandatory fields complete"
  - "prompt-first schema alignment"
handoff_to_l3: "$L34_DIR/L3_DEVELOPMENT_PLAN.md"
DOC

reference_files=(
  "research_note.md" "reference_pack.md" "dedup_diff.md" "codex_handoff.md"
  "line_direction_proposal.md" "line_isolation_report.md" "industrial_gap_map.md"
  "innovation_guard_report.md" "interface_envelope_alignment.md" "line_sync_leveling.md"
  "cross_line_conflict_matrix.md" "AB-envelope.md" "CD-envelope.md" "EF-envelope.md"
  "interface-consistency-r41-r40-autodispatch.md"
  "residual_backlog.md" "structural_inconsistency_patch.md" "af_repo_dedup_report.md"
  "risk_gate_summary.md" "source_repo_urls.txt" "INDEX.md"
)

for f in "${reference_files[@]}"; do
  case "$f" in
    "INDEX.md")
      cat > "$L12_DIR/$f" <<DOC
# INDEX.md

- generated_at: $TS
- workspace: openclaw
- stage: L2 research/reference
- mode: docs-only

## File Index
- 01_initialization-baseline-and-scope-${DATE_TAG}.md
- 02_l2-to-l3-task-brief-${DATE_TAG}.md
- 03_l2-controller-sync-template-${DATE_TAG}.md
- L1_MASTER_PLAN.md
- L1_CONTROL_PACK.yaml
- L2_ORCHESTRATION_PLAN.md
- L2_ORCHESTRATION_PACK.yaml
- research_note.md
- reference_pack.md
- dedup_diff.md
- codex_handoff.md
- line_direction_proposal.md
- line_isolation_report.md
- industrial_gap_map.md
- innovation_guard_report.md
- interface_envelope_alignment.md
- line_sync_leveling.md
- residual_backlog.md
- structural_inconsistency_patch.md
- af_repo_dedup_report.md
- risk_gate_summary.md
- source_repo_urls.txt
DOC
      ;;
    "source_repo_urls.txt")
      cat > "$L12_DIR/$f" <<DOC
generated_at=$TS
workspace=openclaw
target_project_path=$TARGET_ROOT
openclaw_path=$OPENCLAW_ROOT
target_repo_origin=$TARGET_REMOTE
openclaw_repo_origin=$OPENCLAW_REMOTE
DOC
      ;;
    "AB-envelope.md"|"CD-envelope.md"|"EF-envelope.md")
      cat > "$L12_DIR/$f" <<DOC
# $f

- generated_at: $TS
- workspace: openclaw
- stage: L2 research/reference
- mode: docs-only
- authoring_layer: L2

## envelope
- contract_scope: $(echo "$f" | cut -d- -f1)
- compatibility_target: previous_batch_interface_contract
- rollback_pointer: interface-consistency-r41-r40-autodispatch.md

## must
- Keep schema-first and stable field naming.
- Keep backward compatibility for consuming layer.

## do_not
- Introduce breaking field rename without migration.
DOC
      ;;
    "cross_line_conflict_matrix.md")
      cat > "$L12_DIR/$f" <<DOC
# cross_line_conflict_matrix.md

- generated_at: $TS
- workspace: openclaw
- stage: L2 research/reference
- mode: docs-only

## touchpoints_overlap
- A/B: medium
- C/D: low
- E/F: medium

## contract_semantic_conflict
- none blocking in docs-only run

## gate_name_conflict
- none blocking in docs-only run

## mitigation_or_split_plan
- Keep conflicting updates in separate atomic tasks.
- Use interface envelope alignment before merge.
DOC
      ;;
    "interface-consistency-r41-r40-autodispatch.md")
      cat > "$L12_DIR/$f" <<DOC
# interface-consistency-r41-r40-autodispatch.md

- generated_at: $TS
- workspace: openclaw
- stage: L2 research/reference
- mode: docs-only

## comparison
- baseline_round: r40
- current_round: r41
- consistency_status: pass-with-warn

## warning
- runtime evidence is not available in docs-only mode.

## rollback_pointer
- Use AB/CD/EF envelope docs as contract lock.
DOC
      ;;
    *)
      cat > "$L12_DIR/$f" <<DOC
# $f

- generated_at: $TS
- workspace: openclaw
- stage: L2 research/reference
- mode: docs-only

## Observed Signals
- target_branch: $TARGET_BRANCH
- target_head: $TARGET_HEAD
- target_dirty_files: $TARGET_DIRTY_COUNT

## Sample Workflow Paths
$WORKFLOW_SAMPLE

## Sample API Paths
$API_SAMPLE

## Next Action Stub
- Replace with project-specific conclusion and risk list.
DOC
      ;;
  esac
done

cat > "$L12_DIR/README.md" <<DOC
# L1/L2 Docs-Only Package

- generated_at: $TS
- project_id: $PROJECT_ID
- workspace: openclaw

## Documents
- 01_initialization-baseline-and-scope-${DATE_TAG}.md
- 02_l2-to-l3-task-brief-${DATE_TAG}.md
- 03_l2-controller-sync-template-${DATE_TAG}.md
- L1_MASTER_PLAN.md
- L1_CONTROL_PACK.yaml
- L2_ORCHESTRATION_PLAN.md
- L2_ORCHESTRATION_PACK.yaml

## Research/Reference Bundle
DOC
for f in "${reference_files[@]}"; do echo "- $f" >> "$L12_DIR/README.md"; done

# L3 in target
cat > "$L34_DIR/00_l3-doc-style-contract-${DATE_TAG}.md" <<DOC
# L3 Documentation Style Contract (Initialization Locked)

- generated_at: $TS
- workspace: target project
- stage: L3
- style_id: $L34_DOC_STYLE
- lock_at: initialization

## Required Section Skeleton
1. 目标
2. 原子任务
3. 实现变更
4. 验证命令与结果
5. 风险
6. 回滚点

## L2-L3 Interaction Rule
- L2 only sends completion targets.
- L3 reads norms and writes plan/atomic list.
- L3 then prepares sub-agent dispatch docs.
DOC

cat > "$L34_DIR/03_l3-development-plan-${DATE_TAG}.md" <<DOC
# L3 Development Plan (${DATE_TAG})

- generated_at: $TS
- authoring_layer: L3
- artifact_manifest:
  - path: $L34_DIR/03_l3-development-plan-${DATE_TAG}.md
    layer_owner: L3
    summary: development plan
- doc_delta:
  - created: 03_l3-development-plan-${DATE_TAG}.md
  - updated: none

## 目标
- Consume L2 brief and produce a development plan in target workspace.

## 原子任务
- L3-P1: Read development documentation norms.
- L3-P2: Produce development plan milestones.
- L3-P3: Define boundaries for atomic decomposition.

## 实现变更
- output: 03_l3-development-plan-${DATE_TAG}.md
- l2_brief: $L12_DIR/02_l2-to-l3-task-brief-${DATE_TAG}.md
- norms:
  - $TARGET_ROOT/development/latest-dev-docs/README.md
  - $TARGET_ROOT/codex_settings/AGENTS.md

## 验证命令与结果
- test -f "$L34_DIR/03_l3-development-plan-${DATE_TAG}.md"
- result: PASS

## 风险
- Skipping norms may cause format drift and poor downstream consumption.

## decision
- handoff_to_atomic

## 回滚点
- remove $L34_DIR/03_l3-development-plan-${DATE_TAG}.md
DOC

cat > "$L34_DIR/04_l3-atomic-task-list-${DATE_TAG}.md" <<DOC
# L3 Atomic Task List (${DATE_TAG})

- generated_at: $TS
- authoring_layer: L3
- artifact_manifest:
  - path: $L34_DIR/04_l3-atomic-task-list-${DATE_TAG}.md
    layer_owner: L3
    summary: atomic task list
- doc_delta:
  - created: 04_l3-atomic-task-list-${DATE_TAG}.md
  - updated: none

## 目标
- Translate development plan into executable atomic tasks.

## 原子任务
- L3-A1: Define task input/output/acceptance.
- L3-A2: Mark parallel groups and serial dependencies.
- L3-A3: Attach minimal validation commands.

## 实现变更
- output: 04_l3-atomic-task-list-${DATE_TAG}.md
- input_plan: $L34_DIR/03_l3-development-plan-${DATE_TAG}.md

## 验证命令与结果
- test -f "$L34_DIR/04_l3-atomic-task-list-${DATE_TAG}.md"
- result: PASS

## 风险
- Bad decomposition leads to sub-agent overlap and rework.

## decision
- handoff_to_dispatch

## 回滚点
- remove $L34_DIR/04_l3-atomic-task-list-${DATE_TAG}.md
DOC

cat > "$L34_DIR/05_l3-subagent-dispatch-record-${DATE_TAG}.md" <<DOC
# L3 Sub-Agent Dispatch Record (${DATE_TAG})

- generated_at: $TS
- authoring_layer: L3
- artifact_manifest:
  - path: $L34_DIR/05_l3-subagent-dispatch-record-${DATE_TAG}.md
    layer_owner: L3
    summary: sub-agent dispatch strategy
- doc_delta:
  - created: 05_l3-subagent-dispatch-record-${DATE_TAG}.md
  - updated: none

## 目标
- Define how L3 dispatches sub-agents based on atomic task list (docs-only).

## 原子任务
- L3-D1: Create dispatch packet template per atomic task.
- L3-D2: Define retry/timeout/failure isolation policy.
- L3-D3: Standardize return fields (result/files/verification/risk).

## 实现变更
- output: 05_l3-subagent-dispatch-record-${DATE_TAG}.md
- input_atomic: $L34_DIR/04_l3-atomic-task-list-${DATE_TAG}.md
- execution_mode: docs-only (no real dispatch)

## 验证命令与结果
- test -f "$L34_DIR/05_l3-subagent-dispatch-record-${DATE_TAG}.md"
- result: PASS

## 风险
- No real execution evidence in docs-only mode.

## decision
- handoff_to_l4_report

## 回滚点
- remove $L34_DIR/05_l3-subagent-dispatch-record-${DATE_TAG}.md
DOC

cat > "$L34_DIR/L4_EXECUTION_REPORT.md" <<DOC
# L4_EXECUTION_REPORT

- generated_at: $TS
- authoring_layer: L4
- result: docs-only-placeholder
- changed_files:
  - $L34_DIR/03_l3-development-plan-${DATE_TAG}.md
  - $L34_DIR/04_l3-atomic-task-list-${DATE_TAG}.md
  - $L34_DIR/05_l3-subagent-dispatch-record-${DATE_TAG}.md
- verification:
  - test -f "$L34_DIR/03_l3-development-plan-${DATE_TAG}.md" => PASS
  - test -f "$L34_DIR/04_l3-atomic-task-list-${DATE_TAG}.md" => PASS
  - test -f "$L34_DIR/05_l3-subagent-dispatch-record-${DATE_TAG}.md" => PASS
- risks:
  - docs-only mode has no runtime execution evidence
- decision: return_to_l2
- artifact_manifest:
  - path: $L34_DIR/L4_EXECUTION_REPORT.md
    layer_owner: L4
    summary: docs-only execution envelope
- doc_delta:
  - created: L4_EXECUTION_REPORT.md
  - updated: none
- rollback_ref: remove $L34_DIR/L4_EXECUTION_REPORT.md
- control-resume-trigger: 请总控开启下一任务
DOC

# Canonical prompt-first aliases
cp "$L34_DIR/03_l3-development-plan-${DATE_TAG}.md" "$L34_DIR/L3_DEVELOPMENT_PLAN.md"
cp "$L34_DIR/04_l3-atomic-task-list-${DATE_TAG}.md" "$L34_DIR/L3_ATOMIC_TASK_LIST.md"
cp "$L34_DIR/05_l3-subagent-dispatch-record-${DATE_TAG}.md" "$L34_DIR/L3_SUBAGENT_DISPATCH.md"

# Target-side R40/R41 consumption mirror docs
cat > "$L34_DIR/research_note.md" <<DOC
# research_note.md

- generated_at: $TS
- workspace: target project
- mode: docs-only
- source: $L12_DIR/research_note.md
DOC

cat > "$L34_DIR/reference_pack.md" <<DOC
# reference_pack.md

- generated_at: $TS
- workspace: target project
- mode: docs-only
- source: $L12_DIR/reference_pack.md
DOC

cat > "$L34_DIR/codex_handoff.md" <<DOC
# codex_handoff.md

- generated_at: $TS
- workspace: target project
- mode: docs-only
- source: $L12_DIR/codex_handoff.md
DOC

cat > "$L34_DIR/dedup_diff.md" <<DOC
# dedup_diff.md

- generated_at: $TS
- workspace: target project
- mode: docs-only
- source: $L12_DIR/dedup_diff.md
DOC

cat > "$L34_DIR/AB-envelope.md" <<DOC
# AB-envelope.md

- generated_at: $TS
- workspace: target project
- mode: docs-only
- source: $L12_DIR/AB-envelope.md
DOC

cat > "$L34_DIR/interface-consistency-r41-r40-autodispatch.md" <<DOC
# interface-consistency-r41-r40-autodispatch.md

- generated_at: $TS
- workspace: target project
- mode: docs-only
- source: $L12_DIR/interface-consistency-r41-r40-autodispatch.md
DOC

cat > "$L34_DIR/INDEX.md" <<DOC
# INDEX.md

- generated_at: $TS
- workspace: target project
- mode: docs-only

## mirror_docs
- research_note.md
- reference_pack.md
- codex_handoff.md
- dedup_diff.md
- AB-envelope.md
- interface-consistency-r41-r40-autodispatch.md
DOC

cat > "$L34_DIR/README.md" <<DOC
# Target Project L3 Docs Package (Docs-Only)

- generated_at: $TS
- workspace: target project
- split_rule: L1/L2 -> openclaw, L3 docs -> target project

## L3 Documents
- 00_l3-doc-style-contract-${DATE_TAG}.md
- 03_l3-development-plan-${DATE_TAG}.md
- 04_l3-atomic-task-list-${DATE_TAG}.md
- 05_l3-subagent-dispatch-record-${DATE_TAG}.md
- L3_DEVELOPMENT_PLAN.md
- L3_ATOMIC_TASK_LIST.md
- L3_SUBAGENT_DISPATCH.md

## L4 Documents
- L4_EXECUTION_REPORT.md

## Target Consumption Mirror
- INDEX.md
- research_note.md
- reference_pack.md
- codex_handoff.md
- dedup_diff.md
- AB-envelope.md
- interface-consistency-r41-r40-autodispatch.md

## L1/L2 Package Location
- $L12_DIR
DOC

# index wiring target
CURR_INDEX="$TARGET_ROOT/development/latest-dev-docs/development-plans/CURRENT_DEV/INDEX.md"
PLAN_INDEX="$TARGET_ROOT/development/latest-dev-docs/development-plans/INDEX.md"
TOP_README="$TARGET_ROOT/development/latest-dev-docs/README.md"
MERGED_OVERVIEW="$TARGET_ROOT/development/latest-dev-docs/MERGED_OVERVIEW.md"
entry_curr="- [$PKG_NAME](./$PKG_NAME/README.md)"
entry_plan="- [CURRENT_DEV/$PKG_NAME/README.md](./CURRENT_DEV/$PKG_NAME/README.md)"
entry_top="  - [$PKG_NAME/README.md](./development-plans/CURRENT_DEV/$PKG_NAME/README.md)"

grep -Fq -- "$entry_curr" "$CURR_INDEX" || sed -i '' "2i\\
$entry_curr" "$CURR_INDEX"
grep -Fq -- "$entry_plan" "$PLAN_INDEX" || sed -i '' "30i\\
$entry_plan" "$PLAN_INDEX"
grep -Fq -- "$entry_top" "$TOP_README" || sed -i '' "28i\\
$entry_top" "$TOP_README"
grep -Fq -- "$entry_top" "$MERGED_OVERVIEW" || sed -i '' "24i\\
$entry_top" "$MERGED_OVERVIEW"

# index wiring openclaw
OC_PROJ_INDEX="$OPENCLAW_ROOT/docs/implementation/projects/INDEX.md"
OC_PROJECT_DIR="$OPENCLAW_ROOT/docs/implementation/projects/$PROJECT_ID"
mkdir -p "$OC_PROJECT_DIR"
OC_PROJECT_README="$OC_PROJECT_DIR/README.md"
if [[ ! -f "$OC_PROJECT_README" ]]; then
  cat > "$OC_PROJECT_README" <<DOC
# $PROJECT_ID

Project-level implementation documents stored in openclaw workspace.
DOC
fi
oc_entry="- ${DATE_TAG}-l1l2-docs-only/"
grep -Fq -- "$oc_entry" "$OC_PROJECT_README" || echo "$oc_entry" >> "$OC_PROJECT_README"
grep -Fq -- "$PROJECT_ID/" "$OC_PROJ_INDEX" || echo "- $PROJECT_ID/" >> "$OC_PROJ_INDEX"

echo "DOCS_ONLY_WORKFLOW_OK"
echo "l12_dir=$L12_DIR"
echo "l34_dir=$L34_DIR"
echo "reference_bundle_count=${#reference_files[@]}"
