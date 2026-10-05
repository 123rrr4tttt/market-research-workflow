import { expect, test } from '@playwright/test'
import { classifyReference } from '../../src/features/information-topology/referenceStatus'
import { normalizeMaterialRef } from '../../src/features/information-topology/materialIdentity'
import { materialReaderId, normalizeMaterialGraph } from '../../src/pages/graph/realizer/materialGraph'
import { applyProjectGraphView, normalizeProjectGraphViewSpec } from '../../src/pages/graph/realizer/projectGraphView'
import { projectInformationTopologies } from '../../src/pages/graph/realizer/topologyProjection'
import type { BoundRef, CurrentTopologyItem } from '../../src/features/information-topology/types'
import { endpoints } from '../../src/lib/api/endpoints'
import { toDraggedCardPayload, toDraggedCardPreview } from '../../src/components/writing/dragPayload'

const legacyRef = { project_key: 'p', module_id: 'documents', namespace: 'documents', type_id: 'document', local_id: '12' }
const canonicalRef = normalizeMaterialRef(legacyRef)
const legacyId = JSON.stringify(['p', 'documents', 'documents', 'document', '12', 'r1', 'digest'])
const canonicalId = JSON.stringify(['p', 'materials', 'materials', 'material', '12', 'r1', 'digest'])

test('reference comparison transports identity while retaining revision and digest checks', () => {
  const previous: BoundRef = { ref: legacyRef, observed_revision: 'r1', content_digest: 'digest' }
  expect(classifyReference(previous, [{ ...previous, ref: canonicalRef }]).status).toBe('resolved')
  expect(classifyReference(previous, [{ ...previous, ref: canonicalRef, observed_revision: 'r2' }]).status).toBe('stale')
  expect(classifyReference(previous, [{ ...previous, ref: canonicalRef, content_digest: 'other' }]).status).toBe('stale')
  expect(normalizeMaterialRef({ ...legacyRef, module_id: 'writing' }).module_id).toBe('writing')
})

test('legacy graph keys, selections and endpoints transport together into saved material views', () => {
  const graph = normalizeMaterialGraph({ nodes: [
    { id: legacyId, type: 'document', document_id: 12, topology_ref: legacyRef },
    { id: 'evidence-1', type: 'evidence' },
  ], edges: [{ from: { id: 'evidence-1', type: 'evidence' }, to: { id: legacyId, type: 'document' } }] })
  const spec = normalizeProjectGraphViewSpec({
    schema: 'project-graph-view/v1', mode: 'selection', nodeKeys: [`document:${legacyId}`, 'evidence:evidence-1'],
    hiddenNodeTypes: [], hiddenEdgeKinds: [], additionalNodes: [],
    additionalEdges: [{ type: 'reverse', from: { id: legacyId, type: 'document' }, to: { id: 'evidence-1', type: 'evidence' } }],
  })!
  expect(spec.nodeKeys[0]).toBe(`material:${canonicalId}`)
  const result = applyProjectGraphView(graph.nodes, graph.edges, spec)
  expect(result.nodes).toHaveLength(2)
  expect(result.edges).toHaveLength(2)
  expect(result.edges[0].to).toEqual({ id: canonicalId, type: 'material' })
  expect(result.edges[1].from).toEqual({ id: canonicalId, type: 'material' })
  expect(materialReaderId(result.nodes[0])).toBe(12)
  expect(materialReaderId({ id: 'missing', type: 'material' })).toBeNull()
  expect(materialReaderId({ id: 12, type: 'document' })).toBe(12)
  expect(materialReaderId({ id: 12, type: 'material', topology_ref: { ...canonicalRef, module_id: 'retrieval' } })).toBeNull()
  expect(endpoints.admin.materialById(12)).toBe(endpoints.admin.documentById(12))
  expect(endpoints.admin.materialById(12)).toContain('/admin/materials/12')
})

test('canonical placement and native material coalesce without changing incidence endpoint type', () => {
  const bound: BoundRef = { ref: canonicalRef, observed_revision: 'r1', content_digest: null }
  const placement: BoundRef = { ref: { ...canonicalRef, module_id: 'retrieval', namespace: 'n', local_id: 'placement' }, observed_revision: 's1' }
  const item: CurrentTopologyItem = {
    topology_ref: { module_id: 'retrieval', namespace: 'n', state_id: 's' }, profile_id: 'retrieval.domain.test',
    profile_version: '3', revision: 1, digest: 'd', element_count: 2,
    topology: { profile_id: 'retrieval.domain.test', profile_version: '3', elements: [
      { ref: placement, attributes: { material_ref: canonicalRef, material_id: 12, material_revision: 'r1', title: 'Title' },
        endpoints: [{ role: 'self', target: bound }] },
      { ref: bound, attributes: { title: 'Title' }, endpoints: [] },
    ] },
  }
  const graph = projectInformationTopologies([item])
  expect(graph.nodes).toHaveLength(1)
  expect(graph.edges[0].from).toEqual(graph.edges[0].to)
  expect(graph.edges[0].from.type).toBe('material')
  expect(materialReaderId(graph.nodes[0])).toBe(12)
  const reversed = { ...item, topology: { ...item.topology, elements: [...item.topology.elements].reverse() } }
  expect(projectInformationTopologies([reversed]).nodes[0].placement_ref).toEqual(placement.ref)
})

test('writing card consumers normalize material sources while preserving saved citation card IDs', () => {
  const payload = toDraggedCardPayload({ card_id: 'doc:12', title: 'Source', snippet: '', score: 1, source_type: 'document', quick_actions: [] })
  expect(payload.sourceType).toBe('material')
  expect(toDraggedCardPreview(payload)).toMatchObject({ card_id: 'doc:12', source_type: 'material' })
})

test('duplicate legacy and canonical graph nodes preserve complementary hydration in either order', () => {
  const legacy = {
    id: legacyId, type: 'document', document_id: 12, topology_ref: legacyRef,
    material_ref: { ...canonicalRef, module_id: 'retrieval', namespace: 'n', local_id: 'placement' },
    title: 'Legacy title', content: 'Hydrated body', evidence: 'Evidence excerpt',
    topology_attributes: { title: 'Legacy title', original_excerpt: 'Original evidence', chapter: '1' },
    extracted_data: { author: 'Author', summary: 'Summary' },
  }
  const canonical = {
    id: canonicalId, type: 'material', material_id: 12, material_ref: canonicalRef,
    title: 'Canonical title', content: '', evidence: undefined,
    topology_attributes: { title: 'Canonical title', original_excerpt: undefined, uri: 'https://example.test/material' },
    extracted_data: { author: null, date: '2026-10-05' },
  }
  const forward = normalizeMaterialGraph({ nodes: [legacy, canonical], edges: [] })
  const reverse = normalizeMaterialGraph({ nodes: [canonical, legacy], edges: [] })
  expect(forward).toEqual(reverse)
  expect(forward.nodes).toHaveLength(1)
  expect(forward.nodes[0]).toMatchObject({
    title: 'Canonical title', content: 'Hydrated body', evidence: 'Evidence excerpt',
    placement_ref: legacy.material_ref, material_ref: canonicalRef,
    topology_attributes: { title: 'Canonical title', original_excerpt: 'Original evidence', chapter: '1', uri: 'https://example.test/material' },
    extracted_data: { author: 'Author', summary: 'Summary', date: '2026-10-05' },
  })
})

test('non-numeric and unsafe material references do not project a reader ID', () => {
  for (const localId of ['missing', '9007199254740992']) {
    const ref = { ...canonicalRef, local_id: localId }
    const item: CurrentTopologyItem = {
      topology_ref: { module_id: 'materials', namespace: 'materials', state_id: 's' },
      profile_id: 'native.material', profile_version: '1', revision: 1, digest: 'd', element_count: 1,
      topology: { profile_id: 'native.material', profile_version: '1', elements: [
        { ref: { ref, observed_revision: 'r1' }, attributes: {}, endpoints: [] },
      ] },
    }
    const graph = projectInformationTopologies([item])
    expect(graph.nodes[0].material_id).toBeUndefined()
    expect(materialReaderId(graph.nodes[0])).toBeNull()
  }
})

test('old view alias collisions collapse while raw duplicates remain invalid', () => {
  const legacyNode = { id: legacyId, type: 'document', content: 'Body', topology_ref: legacyRef }
  const canonicalNode = { id: canonicalId, type: 'material', title: 'Title', topology_ref: canonicalRef }
  const legacyRelation = { sourceType: 'document', targetType: 'evidence', relation: 'supports' }
  const canonicalRelation = { ...legacyRelation, sourceType: 'material' }
  const input = {
    schema: 'project-graph-view/v1', mode: 'selection',
    nodeKeys: [`document:${legacyId}`, `material:${canonicalId}`],
    hiddenNodeTypes: ['document', 'material'], hiddenEdgeKinds: [],
    additionalNodes: [legacyNode, canonicalNode], additionalEdges: [],
    declaredNodeTypes: ['document', 'material'],
    declaredRelationTypes: [legacyRelation, canonicalRelation],
  }
  const result = normalizeProjectGraphViewSpec(input)!
  expect(result).not.toBeNull()
  expect(result.nodeKeys).toEqual([`material:${canonicalId}`])
  expect(result.hiddenNodeTypes).toEqual(['material'])
  expect(result.declaredNodeTypes).toEqual(['material'])
  expect(result.declaredRelationTypes).toEqual([canonicalRelation])
  expect(result.additionalNodes).toHaveLength(1)
  expect(result.additionalNodes[0]).toMatchObject({ title: 'Title', content: 'Body' })
  expect(normalizeProjectGraphViewSpec({ ...input, additionalNodes: [canonicalNode, legacyNode] })).toEqual(result)
  for (const repeated of [
    { nodeKeys: [input.nodeKeys[0], input.nodeKeys[0]] },
    { hiddenNodeTypes: ['document', 'document'] },
    { declaredNodeTypes: ['material', 'material'] },
    { additionalNodes: [legacyNode, legacyNode] },
    { declaredRelationTypes: [legacyRelation, legacyRelation] },
  ]) expect(normalizeProjectGraphViewSpec({ ...input, ...repeated })).toBeNull()
  expect(normalizeProjectGraphViewSpec({ ...input, additionalNodes: [
    { id: '1', type: 'product' }, { id: '1', type: 'ProductEntity' },
  ] })).toBeNull()
})
