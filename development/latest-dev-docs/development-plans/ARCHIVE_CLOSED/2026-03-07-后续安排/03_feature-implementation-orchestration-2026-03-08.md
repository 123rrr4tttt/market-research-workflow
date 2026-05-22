# Feature Implementation Orchestration (2026-03-08)

## Purpose

This runbook is for feature delivery execution, not for documentation normalization.
It converts current topic plans into an implementation order with explicit gates.

## Layered Delivery Order

- L0 (serial): implementation scope freeze and dependency freeze.
- L1 (parallel): backend/core contract foundations by theme.
- L2 (parallel): frontend/domain integration by theme.
- L3 (serial-dominant): cross-theme contract merge and conflict resolution.
- L4 (serial): end-to-end regression gate and release handoff.

## Feature Waves by Theme

### Wave-A Foundations (can run in parallel)

- `crawler-source-expansion`: `A1 -> (A2,A3)`
- `ingest-digestion-and-long-cycle-automation`: `A1 -> (A2,A4)`
- `typed-knowledge-organization`: `K1 -> K2`
- `llm-service-and-agent-platformization`: `A1 -> (A2,A3,A4)`
- `graph-editing-and-reporting`: `A1 -> A2`
- `dual-frontend-workbench-topology`: `A1 -> A2`
- `frontend-i18n-theme-modularization`: `A1 -> (A2,A3,A4)`
- `writing-workbench-evolution`: `E1 -> E2`

### Wave-B Core Buildout (parallel with file locks)

- `crawler`: `(A4,A5) -> A6`
- `ingest`: `(A3,A5) -> A6`
- `typed-knowledge`: `(K3,K4,K5) -> K6`
- `llm-platform`: `A5 -> A6`
- `graph`: `(A3,A5) -> (A4,A6)`
- `dual-topology`: `(A3,A5) -> A4 -> A6`
- `i18n-theme`: `A5 -> (A6,A7,A8)`
- `writing-evolution`: `(E3,E4,E5,E6)`

### Wave-C Cross-Theme Merge (serial-dominant)

- hard dependency merge:
  - `writing E3` after/with `graph A5` and aligned with `graph A6`.
  - `writing E6` aligned with `llm A2/A4/A6`.
  - `writing E8` is the mandatory cross-theme merge gate.
- closure preconditions:
  - graph at least through `A6`
  - llm-platform at least through `A6`
  - i18n-theme at least through `A8`
  - dual-topology at least through `A7`

### Wave-D Closure

- `crawler`: `A7`
- `ingest`: `A7 -> A8`
- `typed-knowledge`: `K7 -> K8`
- `llm-platform`: `A7 -> A8`
- `graph`: `A7`
- `dual-topology`: `A8`
- `i18n-theme`: `A9 -> A10`
- `writing-evolution`: `E7 -> E8 -> E9`

## Parallel Dispatch Policy

- max workers by layer:
  - L0: `1`
  - L1: `8`
  - L2: `10`
  - L3: `6`
  - L4: `2`
- strict file locks:
  - `main/frontend-modern/src/app/shell/AppShell.tsx`
  - `main/frontend-modern/src/app/navigation/index.ts`
  - `main/frontend-modern/src/components/FigmaSideNav.tsx`
  - `main/frontend-modern/src/pages/SettingsPage.tsx`
  - `main/frontend-modern/src/index.css`
- conflict rule:
  - same file == serial execution; no same-wave co-edit.
- adaptive throttle rule:
  - if locked-file queue length >= 3, reduce active workers by 30% for that layer;
  - restore full workers after queue length <= 1 for two consecutive scheduling cycles.
- backend/frontend lane split:
  - reserve at least 40% workers for backend-heavy themes (`crawler`, `ingest`, `typed`, `llm`, `graph`);
  - reserve at least 40% workers for frontend-heavy themes (`dual-topology`, `i18n-theme`, `writing` surface tasks);
  - keep 20% floating workers for unblock and dependency-fix tasks.

## Gate Checklist (Feature-Facing)

- Gate-G0: theme scope and non-goals are frozen.
- Gate-G1: each theme has a verified baseline and task ownership.
- Gate-G2: each theme produced a runnable core slice.
- Gate-G3: cross-theme contracts merged (`writing E8` passed).
- Gate-G4: regression pack passed and release handoff prepared.

## Week-1 Execution Cadence

- Day-1: L0 freeze + Wave-A start.
- Day-2: finish Wave-A, start Wave-B.
- Day-3: continue Wave-B with lock-aware scheduling.
- Day-4: finish Wave-B and start Wave-C alignment.
- Day-5: complete Wave-C merge gate.
- Day-6: run Wave-D closures and regression prep.
- Day-7: regression gate, risk review, release handoff.
