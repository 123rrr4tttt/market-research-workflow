import type { ElementRef } from './types'

export function isCanonicalMaterialRef(value: unknown): value is ElementRef {
  if (!value || typeof value !== 'object') return false
  const ref = value as ElementRef
  return ref.module_id === 'materials' && ref.namespace === 'materials' && ref.type_id === 'material'
    && typeof ref.project_key === 'string' && typeof ref.local_id === 'string'
}
