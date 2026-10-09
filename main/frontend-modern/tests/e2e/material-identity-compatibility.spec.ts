import { expect, test } from '@playwright/test'
import { toDraggedCardPayload, toDraggedCardPreview } from '../../src/components/writing/dragPayload'
import { isCanonicalMaterialRef } from '../../src/features/information-topology/materialIdentity'
import { classifyReference } from '../../src/features/information-topology/referenceStatus'
import type { BoundRef, CurrentTopologyItem } from '../../src/features/information-topology/types'
import { endpoints } from '../../src/lib/api/endpoints'
import { materialReaderId, normalizeMaterialGraph, projectAdminMaterials } from '../../src/pages/graph/realizer/materialGraph'
import { normalizeProjectGraphViewSpec } from '../../src/pages/graph/realizer/projectGraphView'
import { projectInformationTopologies } from '../../src/pages/graph/realizer/topologyProjection'

const canonicalRef = {
  project_key: 'p',
  module_id: 'materials',
  namespace: 'materials',
  type_id: 'material',
  local_id: '12',
}
const legacyRef = {
  project_key: 'p',
  module_id: 'documents',
  namespace: 'documents',
  type_id: 'document',
  local_id: '12',
}

test('reference comparison requires the current exact material identity', () => {
  const current: BoundRef = { ref: canonicalRef, observed_revision: 'r1', content_digest: 'digest' }
  expect(classifyReference(current, [current]).status).toBe('resolved')
  expect(classifyReference(current, [{ ...current, observed_revision: 'r2' }]).status).toBe('stale')
  expect(classifyReference(current, [{ ...current, content_digest: 'other' }]).status).toBe('stale')
  expect(classifyReference({ ...current, ref: legacyRef }, [current]).status).toBe('unresolvable')
  expect(isCanonicalMaterialRef(canonicalRef)).toBe(true)
  expect(isCanonicalMaterialRef(legacyRef)).toBe(false)
})

test('admin material rows project canonical material nodes without invented relations', () => {
  const graph = projectAdminMaterials([{
    material_id: 12,
    title: 'Crawler material',
    material_type: 'news',
    uri: 'https://example.test/source',
    created_at: '2026-10-06T10:00:00Z',
  }], 'p')

  expect(graph.source_kind).toBe('admin_materials')
  expect(graph.edges).toEqual([])
  expect(graph.nodes).toEqual([expect.objectContaining({
    id: '12',
    type: 'material',
    material_id: 12,
    material_type: 'news',
    title: 'Crawler material',
    material_ref: canonicalRef,
    topology_ref: canonicalRef,
  })])
})

test('graph reader identity comes only from an exact material_ref', () => {
  expect(materialReaderId({ id: '12', type: 'material', material_id: 12, material_ref: canonicalRef })).toBe(12)
  expect(materialReaderId({ id: '12', type: 'material', material_id: 13, material_ref: canonicalRef })).toBeNull()
  expect(materialReaderId({ id: '12', type: 'material', material_id: 12, topology_ref: canonicalRef })).toBeNull()
  expect(materialReaderId({ id: '12', type: 'document', material_id: 12, material_ref: legacyRef })).toBeNull()
  expect(materialReaderId({ id: 'missing', type: 'material' })).toBeNull()

  const graph = normalizeMaterialGraph({
    nodes: [{ id: 'legacy', type: 'document', document_id: 12, topology_ref: legacyRef }],
    edges: [],
  })
  expect(graph.nodes[0].type).toBe('document')
  expect(graph.nodes[0].material_ref).toBeUndefined()
  expect(graph.nodes[0].material_id).toBeUndefined()
})

test('canonical topology placements share one material node and preserve incidence', () => {
  const placement = (localId: string): BoundRef => ({
    ref: { project_key: 'p', module_id: 'retrieval', namespace: 'n', type_id: 'material', local_id: localId },
    observed_revision: 's1',
  })
  const topology: CurrentTopologyItem = {
    topology_ref: { module_id: 'retrieval', namespace: 'n', state_id: 's' },
    profile_id: 'retrieval.domain.test',
    profile_version: '3+test',
    revision: 1,
    digest: 'd',
    element_count: 3,
    topology: {
      profile_id: 'retrieval.domain.test',
      profile_version: '3+test',
      elements: [
        { ref: placement('source-a'), attributes: { material_ref: canonicalRef, material_id: 12, material_revision: 'r1', title: 'Title' }, endpoints: [] },
        { ref: placement('source-b'), attributes: { material_ref: canonicalRef, material_id: 12, material_revision: 'r1', title: 'Title' }, endpoints: [] },
        { ref: placement('candidate'), attributes: {}, endpoints: [
          { role: 'source', target: placement('source-a') },
          { role: 'source', target: placement('source-b') },
        ] },
      ],
    },
  }

  const graph = projectInformationTopologies([topology])
  const materials = graph.nodes.filter((node) => node.type === 'material' && node.material_ref)
  expect(materials).toHaveLength(1)
  expect(materials[0].material_ref).toEqual(canonicalRef)
  expect(materialReaderId(materials[0])).toBe(12)
  expect(graph.edges).toHaveLength(2)
  expect(graph.edges.every((edge) => edge.to.id === materials[0].id)).toBe(true)
})

test('saved graph views retain canonical material identity and reject raw duplicates', () => {
  const node = { id: '12', type: 'material', material_id: 12, material_ref: canonicalRef }
  const input = {
    schema: 'project-graph-view/v1',
    mode: 'selection',
    nodeKeys: ['material:12'],
    hiddenNodeTypes: ['material'],
    hiddenEdgeKinds: [],
    additionalNodes: [node],
    additionalEdges: [],
    declaredNodeTypes: ['material'],
    declaredRelationTypes: [{ sourceType: 'material', targetType: 'evidence', relation: 'supports' }],
  }
  expect(normalizeProjectGraphViewSpec(input)).toMatchObject(input)
  expect(normalizeProjectGraphViewSpec({ ...input, nodeKeys: ['material:12', 'material:12'] })).toBeNull()
  expect(normalizeProjectGraphViewSpec({ ...input, additionalNodes: [node, node] })).toBeNull()
})

test('writing cards and admin endpoints expose canonical material names only', () => {
  const payload = toDraggedCardPayload({
    card_id: 'material:12',
    title: 'Source',
    snippet: '',
    score: 1,
    source_type: 'material',
    quick_actions: [],
  })
  expect(payload.sourceType).toBe('material')
  expect(toDraggedCardPreview(payload)).toMatchObject({ card_id: 'material:12', source_type: 'material' })
  expect(endpoints.admin.materialById(12)).toContain('/admin/materials/12')
  expect('documentById' in endpoints.admin).toBe(false)
})
