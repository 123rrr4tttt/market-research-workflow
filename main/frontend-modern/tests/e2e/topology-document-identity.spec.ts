import { expect, test } from '@playwright/test'
import type { CurrentTopologyItem, BoundRef } from '../../src/features/information-topology/types'
import { projectInformationTopologies } from '../../src/pages/graph/realizer/topologyProjection'

test('material placements share the canonical Document node and preserve incidence', () => {
  const ref = (id: string, type = 'material'): BoundRef => ({
    ref: { project_key: 'p', module_id: 'retrieval', namespace: 'n', type_id: type, local_id: id },
    observed_revision: 'source-r1',
  })
  const document = { project_key: 'p', module_id: 'documents', namespace: 'documents', type_id: 'document', local_id: '12' }
  const material = (id: string) => ({
    ref: ref(id), endpoints: [],
    attributes: { document_ref: document, document_id: 12, document_revision: 'doc-r2', title: 'Owner title' },
  })
  const topology = {
    topology_ref: { module_id: 'retrieval', namespace: 'n', state_id: 's' },
    profile_id: 'retrieval.domain.test', profile_version: '2+test', revision: 1, digest: 'test',
    element_count: 3,
    topology: { profile_id: 'retrieval.domain.test', profile_version: '2+test', elements: [
      material('source-a'), material('source-b'),
      { ref: ref('candidate', 'candidate'), attributes: {}, endpoints: [
        { role: 'source', target: ref('source-a') }, { role: 'source', target: ref('source-b') },
      ] },
    ] },
  } satisfies CurrentTopologyItem
  const graph = projectInformationTopologies([topology])
  const documents = graph.nodes.filter(node => node.type === 'document')
  expect(documents).toHaveLength(1)
  expect(documents[0].entry_id).toBe('12')
  expect(documents[0].title).toBe('Owner title')
  expect(graph.edges).toHaveLength(2)
  expect(graph.edges.every(edge => edge.to.id === documents[0].id)).toBe(true)
})

test('unresolved materials do not claim a canonical Document', () => {
  const ref: BoundRef = {
    ref: { project_key: 'p', module_id: 'retrieval', namespace: 'n', type_id: 'material', local_id: 'missing' },
    observed_revision: 'r1',
  }
  const graph = projectInformationTopologies([{
    topology_ref: { module_id: 'retrieval', namespace: 'n', state_id: 's' },
    profile_id: 'retrieval.domain.test', profile_version: '2+test', revision: 1, digest: 'test', element_count: 1,
    topology: { profile_id: 'retrieval.domain.test', profile_version: '2+test', elements: [
      { ref, attributes: { reference_status: 'unresolved_reference' }, endpoints: [] },
    ] },
  }])
  expect(graph.nodes).toHaveLength(1)
  expect(graph.nodes[0].type).toBe('material')
  expect(graph.nodes[0].document_id).toBeUndefined()
})
