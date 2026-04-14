import type { InteractionSurface } from './surfaces'

export type RubricDimensionId =
  | 'interactionDensity'
  | 'contextContinuity'
  | 'panelCoordination'
  | 'stateCoupling'
  | 'primaryOutcome'

export type RubricSignal = InteractionSurface

export type RubricDimension = {
  id: RubricDimensionId
  label: string
  managementSignal: string
  workbenchSignal: string
}

export type RubricSignalProfile = Record<RubricDimensionId, RubricSignal>

export const CLASSIFICATION_RUBRIC: readonly RubricDimension[] = [
  {
    id: 'interactionDensity',
    label: 'Interaction Density',
    managementSignal: 'single-thread form/list actions and low-frequency edits',
    workbenchSignal: 'high-frequency manipulation with continuous UI feedback',
  },
  {
    id: 'contextContinuity',
    label: 'Context Continuity',
    managementSignal: 'task completion in isolated screens',
    workbenchSignal: 'ongoing session context with iterative refinement',
  },
  {
    id: 'panelCoordination',
    label: 'Panel Coordination',
    managementSignal: 'one primary panel with optional secondary helpers',
    workbenchSignal: 'multiple coordinated panels with linked intent',
  },
  {
    id: 'stateCoupling',
    label: 'State Coupling',
    managementSignal: 'page-local state with low cross-panel coupling',
    workbenchSignal: 'shared transient state across panels and controls',
  },
  {
    id: 'primaryOutcome',
    label: 'Primary Outcome',
    managementSignal: 'configuration, governance, inventory, or monitoring',
    workbenchSignal: 'creation, design, synthesis, or analysis iteration',
  },
] as const

export const AMBIGUOUS_PLACEMENT_RULE =
  'When signals are mixed, choose the surface matching primaryOutcome and contextContinuity. If still tied, place in management for phase-1 and record a revisit note.'

export function classifyByRubric(profile: RubricSignalProfile): InteractionSurface {
  let managementScore = 0
  let workbenchScore = 0
  for (const dimension of CLASSIFICATION_RUBRIC) {
    const signal = profile[dimension.id]
    if (signal === 'workbench') workbenchScore += 1
    else managementScore += 1
  }
  if (workbenchScore > managementScore) return 'workbench'
  return 'management'
}

export function hasMixedSignals(profile: RubricSignalProfile): boolean {
  const first = profile[CLASSIFICATION_RUBRIC[0].id]
  return CLASSIFICATION_RUBRIC.some((dimension) => profile[dimension.id] !== first)
}
