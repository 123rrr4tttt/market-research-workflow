import { expect, test } from '@playwright/test'
import type { BoundRef, TopologyState } from '../../src/features/information-topology/types'

test('图谱抽象结构以只读投影展示来源引用并可刷新读回', async ({ page }) => {
  let reads = 0
  let patchWrites = 0

  const boundRef = (typeId: string, localId: string, revision = 'graph-v1'): BoundRef => ({
    ref: {
      project_key: 'default',
      module_id: 'graph',
      namespace: 'graph',
      type_id: typeId,
      local_id: localId,
    },
    observed_revision: revision,
  })

  const topology: TopologyState = {
    profile_id: 'graph.view',
    profile_version: '1',
    elements: [
      {
        ref: boundRef('graph_node', 'n1'),
        attributes: { origin_ref: 'market_graph:n1' },
        endpoints: [],
      },
      {
        ref: boundRef('graph_relation', 'related_to:graph:n1->graph:n2'),
        attributes: { origin_ref: 'market_graph:n1->n2' },
        endpoints: [
          { role: 'from', target: boundRef('graph_node', 'n1') },
          { role: 'to', target: boundRef('graph_node', 'n2') },
        ],
      },
    ],
  }

  await page.route('**/api/v1/**', async (route) => {
    const url = new URL(route.request().url())
    const path = url.pathname
    const ok = (data: unknown) => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ status: 'ok', data }),
    })

    if (path.endsWith('/project-customization/graph-config')) {
      return ok({ graph_node_types: { market: ['product', 'company'] }, graph_node_labels: {}, graph_relation_labels: {} })
    }
    if (path.endsWith('/admin/market-graph')) {
      return ok({
        nodes: [
          { id: 'n1', type: 'product', name: '示例商品A' },
          { id: 'n2', type: 'company', name: '示例公司B' },
        ],
        edges: [{ type: 'related_to', from: { type: 'product', id: 'n1' }, to: { type: 'company', id: 'n2' } }],
      })
    }
    if (path.endsWith('/information-topology/topologies/read')) {
      reads += 1
      return ok({ topology, revision: 2, digest: 'digest-2' })
    }
    if (path.endsWith('/information-topology/patches')) {
      patchWrites += 1
    }
    return ok({ items: [], total: 0 })
  })

  const response = await page.goto('/#graph.html?type=market')
  expect(response?.ok()).toBeTruthy()
  await expect(page.getByRole('heading', { level: 1, name: '市场图谱', exact: true })).toBeVisible()
  await expect(page.getByTestId('graph-topology-status')).toContainText('已读回版本 2')
  await expect(page.getByTestId('graph-topology-panel')).toContainText('graph:graph_node/n1@graph-v1')
  await expect(page.getByTestId('graph-topology-panel')).toContainText('origin_ref')
  await expect(page.getByTestId('graph-topology-panel')).toContainText('graph:graph_relation/related_to:graph:n1->graph:n2@graph-v1')
  await expect(page.getByRole('button', { name: '创建图谱结构' })).toHaveCount(0)

  await page.getByRole('button', { name: '重新读取' }).click()
  await expect(page.getByTestId('graph-topology-status')).toContainText('已读回版本 2')
  await expect(reads).toBeGreaterThanOrEqual(2)

  await page.reload()
  await expect(page.getByTestId('graph-topology-status')).toContainText('已读回版本 2')
  await expect(page.getByTestId('graph-topology-panel')).toContainText('origin_ref')
  expect(reads).toBeGreaterThanOrEqual(3)
  expect(patchWrites).toBe(0)
})
