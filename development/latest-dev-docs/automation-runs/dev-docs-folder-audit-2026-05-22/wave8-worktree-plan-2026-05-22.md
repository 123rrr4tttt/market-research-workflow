# Wave8 Worktree Plan And Current-Dev Audit Gate

Run date: 2026-05-22 PST

Status: support lane seeded. This file is a low-conflict Wave8 supervisor handoff artifact. It does not edit shared navigation indexes and does not claim implementation closure for any worker lane.

## Scope Rules

- Integration branch: `codex/devdocs-wave8-integration-2026-05-22`.
- Support branch: `codex/devdocs-wave8-current-dev-audit`.
- Worktree root: `/Users/wangyiliang/market-research-workflow.worktrees`.
- Each Wave8 worker returns `result`, `changed files`, `validation status`, and `risk`.
- Shared indexes are supervisor-owned for Wave8 integration. Worker branches must not edit:
  - `development/latest-dev-docs/development-plans/CURRENT_DEV/INDEX.md`
  - `development/latest-dev-docs/development-plans/INDEX.md`
  - `development/latest-dev-docs/README.md`
  - `development/latest-dev-docs/MERGED_OVERVIEW.md`
- This support lane may add only standalone evidence under this audit run and the read-only checker script.
- `scripts/check_current_dev_wave8_plan.py` is expected to pass both on the support branch and after merge into the Wave8 integration branch.

## Wave8 Branch Matrix

| Lane | Branch | Target topic | Expected output | Shared-index rule | Minimum validation |
|---|---|---|---|---|---|
| A | `codex/devdocs-wave8-crawler-external-closure` | External crawler/runtime closure evidence for crawler provider handoff and public probe readiness. | Evidence package or status note that separates runtime proof from network/policy blockers. | Do not edit shared indexes. | Lane-specific crawler/provider gate plus `git diff --check`. |
| B | `codex/devdocs-wave8-fetch-router-cluster` | Broader fetch-router and high-JS/browser-render coverage left by ingest/frontdoor lanes. | Evidence or blocker note for browser/crawler-first routing, dashboard tri-state, and API adapter maturity. | Do not edit shared indexes. | Focused ingest/source_library tests or router smoke plus `git diff --check`. |
| C | `codex/devdocs-wave8-frontend-topology-i18n` | Frontend topology, platform shell, theme, and i18n status. | Runtime/static evidence that distinguishes desktop coverage from remaining mobile or localization gaps. | Do not edit shared indexes. | Frontend topology/visual/lint gate as applicable plus `git diff --check`. |
| D | `codex/devdocs-wave8-graph-rollout` | Graph editing/reporting rollout and GraphPage handoff UI evidence. | Evidence or blocker note for user-facing handoff actions beyond the builder consumer. | Do not edit shared indexes. | GraphPage e2e or focused graph smoke plus `git diff --check`. |
| E | `codex/devdocs-wave8-search-vectorization` | Local index vectorization, hybrid routing, and search provider evidence. | Evidence that separates vector runtime proof from semantic-quality and provider replay blockers. | Do not edit shared indexes. | Local index/search targeted pytest or benchmark smoke plus `git diff --check`. |
| F | `codex/devdocs-wave8-source-library-adapter` | Source-library adapter capability, fallback behavior, and public replay readiness. | Evidence or blocker note for adapter capability assertions, live probes, and replay classifications. | Do not edit shared indexes. | Source-library targeted pytest or skip-safe replay gate plus `git diff --check`. |
| G | `codex/devdocs-wave8-time-semantics-density` | Time semantics density merged plan, overlap gates, and OPE closure criteria. | Closure or blocker note for remaining target-overlap and OPE gates. | Do not edit shared indexes. | Docs/status check plus any relevant targeted gate and `git diff --check`. |
| H | `codex/devdocs-wave8-writing-typed-knowledge` | Writing workbench typed knowledge, handoff, and document/card evidence. | Evidence or blocker note for typed knowledge surfaces and writing/reporting handoff status. | Do not edit shared indexes. | Writing/workflow targeted tests or docs status check plus `git diff --check`. |
| I | `codex/devdocs-wave8-current-dev-audit` | Wave8 support audit and machine-readable supervisor merge gate. | This plan file plus `scripts/check_current_dev_wave8_plan.py`. | Must not edit shared indexes. | `python3 scripts/check_current_dev_wave8_plan.py` and `git diff --check`. |

## Machine-Readable Manifest

```json
{
  "wave": "wave8",
  "run_date": "2026-05-22",
  "integration_branch": "codex/devdocs-wave8-integration-2026-05-22",
  "support_branch": "codex/devdocs-wave8-current-dev-audit",
  "forbidden_shared_indexes": [
    "development/latest-dev-docs/development-plans/CURRENT_DEV/INDEX.md",
    "development/latest-dev-docs/development-plans/INDEX.md",
    "development/latest-dev-docs/README.md",
    "development/latest-dev-docs/MERGED_OVERVIEW.md"
  ],
  "branches": [
    {
      "branch": "codex/devdocs-wave8-crawler-external-closure",
      "target_topic": "crawler provider handoff and external crawler runtime closure",
      "minimum_validation": "crawler/provider focused gate plus git diff --check"
    },
    {
      "branch": "codex/devdocs-wave8-fetch-router-cluster",
      "target_topic": "fetch-router high-JS browser-render coverage and ingest/frontdoor residuals",
      "minimum_validation": "ingest/source_library focused gate or router smoke plus git diff --check"
    },
    {
      "branch": "codex/devdocs-wave8-frontend-topology-i18n",
      "target_topic": "frontend topology platform shell theme and i18n status",
      "minimum_validation": "frontend topology visual or lint gate plus git diff --check"
    },
    {
      "branch": "codex/devdocs-wave8-graph-rollout",
      "target_topic": "graph editing reporting rollout and handoff UI evidence",
      "minimum_validation": "GraphPage e2e or focused graph smoke plus git diff --check"
    },
    {
      "branch": "codex/devdocs-wave8-search-vectorization",
      "target_topic": "local index vectorization hybrid routing and search provider evidence",
      "minimum_validation": "local_index/search targeted pytest or benchmark smoke plus git diff --check"
    },
    {
      "branch": "codex/devdocs-wave8-source-library-adapter",
      "target_topic": "source_library adapter capability fallback and public replay readiness",
      "minimum_validation": "source_library targeted pytest or skip-safe replay plus git diff --check"
    },
    {
      "branch": "codex/devdocs-wave8-time-semantics-density",
      "target_topic": "time semantics density overlap and OPE closure criteria",
      "minimum_validation": "docs/status check plus relevant targeted gate and git diff --check"
    },
    {
      "branch": "codex/devdocs-wave8-writing-typed-knowledge",
      "target_topic": "writing workbench typed knowledge and reporting handoff evidence",
      "minimum_validation": "writing/workflow targeted tests or docs status check plus git diff --check"
    },
    {
      "branch": "codex/devdocs-wave8-current-dev-audit",
      "target_topic": "Wave8 plan status evidence and shared-index guardrail",
      "minimum_validation": "python3 scripts/check_current_dev_wave8_plan.py plus git diff --check"
    }
  ]
}
```

## Supervisor Merge Notes

1. Merge worker lanes only after each branch reports `result`, `changed files`, `validation status`, and `risk`.
2. Before integrating a worker lane, check its changed-file list against the shared-index denylist above.
3. Use this support lane only as a guardrail and status manifest; it is not implementation evidence for the other eight lanes.
4. Regenerate shared navigation indexes only in the supervisor integration branch after accepted worker evidence has landed.

## Minimum Validation Commands

```bash
python3 scripts/check_current_dev_wave8_plan.py
git diff --check
```
