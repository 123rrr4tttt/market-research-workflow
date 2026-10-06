import { expect, test, type Page } from '@playwright/test'
import type { BoundRef, CurrentTopologyItem } from '../../src/features/information-topology/types'

type GraphSnapshot = {
  nodes: Array<{
    id: string
    entry_id?: string
    type: string
    observed_revision?: string
    content_digest?: string | null
    topology_ref?: Record<string, unknown>
    topology_attributes?: Record<string, unknown>
  }>
  edges: Array<{
    id?: string
    type: string
    relation_token?: string
    topology_relation_revision?: string
    from: { id: string; type: string }
    to: { id: string; type: string }
  }>
}

const PROJECT_KEY = 'completion_test'

function boundRef(typeId: string, localId: string, revision: string): BoundRef {
  return {
    ref: {
      project_key: PROJECT_KEY,
      module_id: 'graph',
      namespace: 'graph',
      type_id: typeId,
      local_id: localId,
    },
    observed_revision: revision,
    content_digest: `${localId}-digest`,
  }
}

function topologyItem(revision: string): CurrentTopologyItem {
  const first = boundRef('graph_node', 'n1', revision)
  const second = boundRef('graph_node', 'n2', revision)
  const relation = boundRef('graph_relation', 'related-to', revision)
  const annotation = boundRef('domain_vocabulary', 'vocabulary', revision)
  return {
    topology_ref: { module_id: 'graph', namespace: 'graph', state_id: 'current' },
    profile_id: 'retrieval.domain.graph',
    profile_version: '2',
    revision: revision === 'graph-v1' ? 1 : 2,
    digest: `${revision}-digest`,
    element_count: 4,
    topology: {
      profile_id: 'retrieval.domain.graph',
      profile_version: '2',
      elements: [
        {
          ref: annotation,
          attributes: { structural_role: 'annotation', name: 'Native graph vocabulary' },
          endpoints: [],
        },
        {
          ref: first,
          attributes: { structural_role: 'element', name: 'Native node A', origin_ref: `market_graph:n1@${revision}` },
          endpoints: [],
        },
        {
          ref: second,
          attributes: { structural_role: 'element', name: 'Native node B', origin_ref: `market_graph:n2@${revision}` },
          endpoints: [],
        },
        {
          ref: relation,
          attributes: {
            structural_role: 'relation',
            relation_axis: ['from', 'to'],
            relation_token: 'related_to',
            origin_ref: `market_graph:n1->n2@${revision}`,
          },
          endpoints: [
            { role: 'from', target: first },
            { role: 'to', target: second },
          ],
        },
      ],
    },
  }
}

function identity(typeId: string, localId: string, revision: string): string {
  return JSON.stringify([
    PROJECT_KEY,
    'graph',
    'graph',
    typeId,
    localId,
    revision,
    `${localId}-digest`,
  ])
}

async function readGraphSnapshot(page: Page): Promise<GraphSnapshot | undefined> {
  return page.evaluate(() => {
    const graphPage = window as Window & {
      __graphPageE2E?: { getGraphSnapshot: () => GraphSnapshot }
    }
    return graphPage.__graphPageE2E?.getGraphSnapshot()
  })
}

test('native project topology projects bound identity and reloads without topology writes', async ({ page }) => {
  let sourceReads = 0
  let patchWrites = 0
  let materialReads = 0
  let domainGraphReads = 0
  let sourceRevision = 'graph-v1'

  await page.addInitScript(() => {
    localStorage.setItem('market_project_key', 'completion_test')
    localStorage.setItem('app_locale_v1', 'en-US')
  })
  await page.route('**/api/v1/**', async (route) => {
    const request = route.request()
    const path = new URL(request.url()).pathname
    const ok = (data: unknown) => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ status: 'ok', data }),
    })

    if (path === '/api/v1/information-topology/topologies') {
      sourceReads += 1
      return ok({ items: [topologyItem(sourceRevision)], total: 1 })
    }
    if (path === '/api/v1/information-topology/patches') {
      patchWrites += 1
      return ok({})
    }
    if (path === '/api/v1/admin/materials/list') {
      materialReads += 1
      return ok({ items: [], total: 0, page: 1, page_size: 100 })
    }
    if (/\/api\/v1\/admin\/(market|policy|content|social)-graph$/.test(path)) {
      domainGraphReads += 1
      return ok({ nodes: [], edges: [] })
    }
    if (path === '/api/v1/project-customization/graph-config') {
      return ok({
        graph_node_types: { market: ['graph_node'] },
        graph_node_labels: { graph_node: 'Native graph node' },
        graph_relation_labels: { related_to: 'Related to' },
      })
    }
    if (path === '/api/v1/projects') {
      return ok({ items: [{ project_key: PROJECT_KEY, name: 'Completion test', enabled: true }] })
    }
    return ok({ items: [], total: 0 })
  })

  const response = await page.goto('/#/visual/graph/market')
  expect(response?.ok()).toBeTruthy()
  await expect.poll(async () => (await readGraphSnapshot(page))?.nodes.length ?? -1).toBe(2)
  const initial = await readGraphSnapshot(page)
  expect(initial).toBeDefined()
  const initialNodeIds = [
    identity('graph_node', 'n1', 'graph-v1'),
    identity('graph_node', 'n2', 'graph-v1'),
  ]
  expect(initial!.nodes.map((node) => node.id).sort()).toEqual(initialNodeIds.sort())
  expect(initial!.nodes).toEqual(expect.arrayContaining([
    expect.objectContaining({
      entry_id: 'n1',
      observed_revision: 'graph-v1',
      content_digest: 'n1-digest',
      topology_attributes: expect.objectContaining({ origin_ref: 'market_graph:n1@graph-v1' }),
    }),
  ]))
  expect(initial!.edges).toEqual([expect.objectContaining({
    id: `relation:${identity('graph_relation', 'related-to', 'graph-v1')}`,
    type: 'topology_relation',
    relation_token: 'related_to',
    topology_relation_revision: 'graph-v1',
    from: { id: initialNodeIds[0], type: 'graph_node' },
    to: { id: initialNodeIds[1], type: 'graph_node' },
  })])
  await expect(page.getByTestId('graph-topology-panel')).toHaveCount(0)

  const readsBeforeRefresh = sourceReads
  sourceRevision = 'graph-v2'
  await page.getByRole('button', { name: 'Refresh', exact: true }).click()
  await expect.poll(() => sourceReads).toBeGreaterThan(readsBeforeRefresh)
  const refreshedNodeIds = [
    identity('graph_node', 'n1', 'graph-v2'),
    identity('graph_node', 'n2', 'graph-v2'),
  ]
  await expect.poll(async () => (await readGraphSnapshot(page))?.nodes.map((node) => node.id).sort())
    .toEqual(refreshedNodeIds.sort())

  const readsBeforeReload = sourceReads
  await page.reload()
  await expect.poll(() => sourceReads).toBeGreaterThan(readsBeforeReload)
  const reloaded = await readGraphSnapshot(page)
  expect(reloaded?.nodes.map((node) => node.id).sort()).toEqual(refreshedNodeIds.sort())
  expect(reloaded?.edges).toHaveLength(1)
  expect(patchWrites).toBe(0)
  expect(materialReads).toBe(0)
  expect(domainGraphReads).toBe(0)
})
