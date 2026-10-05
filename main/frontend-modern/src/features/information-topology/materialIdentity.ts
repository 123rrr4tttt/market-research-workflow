import type { BoundRef, ElementRef } from './types'

/** Stored document references are read aliases for the same material identity. */
export function normalizeMaterialRef(ref: ElementRef): ElementRef {
  if (ref.module_id !== 'documents' || ref.namespace !== 'documents' || ref.type_id !== 'document') return ref
  return { ...ref, module_id: 'materials', namespace: 'materials', type_id: 'material' }
}

export function normalizeMaterialBoundRef(bound: BoundRef): BoundRef {
  return { ...bound, ref: normalizeMaterialRef(bound.ref) }
}

export function isCanonicalMaterialRef(value: unknown): value is ElementRef {
  if (!value || typeof value !== 'object') return false
  const ref = normalizeMaterialRef(value as ElementRef)
  return ref.module_id === 'materials' && ref.namespace === 'materials' && ref.type_id === 'material'
    && typeof ref.project_key === 'string' && typeof ref.local_id === 'string'
}

/** Graph IDs persist complete bound-ref tuples, including revision and digest. */
export function normalizeMaterialGraphId<T extends string | number>(id: T): T | string {
  if (typeof id !== 'string' || !id.startsWith('[')) return id
  try {
    const parts: unknown = JSON.parse(id)
    if (!Array.isArray(parts) || parts.length !== 7) return id
    if (parts[1] !== 'documents' || parts[2] !== 'documents' || parts[3] !== 'document') return id
    return JSON.stringify([parts[0], 'materials', 'materials', 'material', ...parts.slice(4)])
  } catch {
    return id
  }
}
