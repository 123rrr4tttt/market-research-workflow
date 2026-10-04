import { expect, test, type Page, type Route } from '@playwright/test'

type CuratedDraftRequest = {
  actor_id?: string
  dsl?: {
    nodes?: unknown[]
    edges?: unknown[]
  }
}

type CuratedSubmitRequest = {
  actor_id?: string
  base_revision?: number
  object_scope?: string
}

type CuratedRollbackRequest = {
  actor_id?: string
  base_revision?: number
  target_version_id?: string
  reason?: string
}

type CuratedReportingHandoffRequest = {
  topic?: string
  selected_node_ids?: string[]
}

type WorkflowDryRunRequest = {
  dry_run?: boolean
  project_key?: string
  params?: Record<string, unknown>
}

type WorkflowTemplateRequest = {
  template_id?: string
  name?: string
  dsl?: { nodes?: unknown[]; edges?: unknown[] }
  version_id?: string
  stage?: string
  from_stage?: string
  to_stage?: string
  target_stage?: string
  target_version?: number
  reason?: string
}

async function setupGraphPageMocks(page: Page, options: { curatedSubmitConflict?: boolean; workflowTemplate?: boolean } = {}) {
  let graphConfigHit = 0
  let marketGraphHit = 0
  let policyGraphHit = 0
  let contentGraphHit = 0
  let curatedDraftHit = 0
  let curatedSubmitHit = 0
  let curatedAuditHit = 0
  let curatedRollbackHit = 0
  let curatedReportingHandoffHit = 0
  let handoffReplayHit = 0
  let workflowDryRunHit = 0
  let workflowTemplateCreateHit = 0
  let workflowTemplateRenameHit = 0
  let workflowTemplateDeleteHit = 0
  let workflowTemplateVersionSaveHit = 0
  let workflowTemplateVersionLoadHit = 0
  let workflowTemplateVersionActivateHit = 0
  let workflowTemplateStageSaveHit = 0
  let workflowTemplateStagePromoteHit = 0
  let workflowTemplateRollbackPreviewHit = 0
  let workflowTemplateRollbackApplyHit = 0
  let workflowTemplateDiffHit = 0
  let workflowTemplateStageAuditHit = 0
  let lastCuratedDraftBody: CuratedDraftRequest | null = null
  let lastCuratedSubmitBody: CuratedSubmitRequest | null = null
  let lastCuratedRollbackBody: CuratedRollbackRequest | null = null
  let lastCuratedReportingHandoffBody: CuratedReportingHandoffRequest | null = null
  let lastWorkflowDryRunBody: WorkflowDryRunRequest | null = null
  let lastWorkflowTemplateBody: WorkflowTemplateRequest | null = null
  const createdTemplateNames: string[] = []
  let savedTemplateVersion = false
  let promotedToStaging = false
  let appliedRollback = false

  const fulfillKernelRuntime = async (route: Route, data: unknown) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ status: 'ok', data }),
    })
  }

  await page.route(/\/api\/v1\/health(?=\?|$)/, async (route) => {
    await fulfillKernelRuntime(route, { status: 'ok', provider: 'mock', env: 'graphpage-e2e' })
  })
  await page.route(/\/api\/v1\/config\/env(?=\?|$)/, async (route) => {
    await fulfillKernelRuntime(route, {
      DATABASE_URL: 'postgresql://graphpage-e2e.example/mrw',
      OPENAI_API_KEY: 'configured-for-graphpage-e2e',
      SERPAPI_KEY: '',
      NEWS_API_KEY: '',
    })
  })
  await page.route(/\/api\/v1\/projects(?=\?|$)/, async (route) => {
    await fulfillKernelRuntime(route, {
      items: [{ project_key: 'default', name: 'Default', enabled: true, is_active: true }],
      total: 1,
    })
  })
  await page.route(/\/api\/v1\/codex-auth\/status(?=\?|$)/, async (route) => {
    await fulfillKernelRuntime(route, {
      authenticated: false,
      token_sink_authenticated: false,
      codex_oauth_enabled: true,
    })
  })
  await page.route(/\/api\/v1\/information-topology\/topologies(?=\?|$)/, async (route) => {
    await fulfillKernelRuntime(route, { items: [], total: 0 })
  })

  await page.route(/\/api\/v1\/information-topology\/topologies\/read(?=\?|$)/, async (route) => {
    await route.fulfill({
      status: 404,
      contentType: 'application/json',
      body: JSON.stringify({
        detail: {
          status: 'error',
          error: { code: 'NOT_FOUND', message: 'topology state was not found' },
        },
      }),
    })
  })

  await page.route('**/api/v1/project-customization/graph-config**', async (route) => {
    graphConfigHit += 1
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        status: 'ok',
        data: {
          graph_node_types: {
            market: ['product', 'company'],
          },
          graph_node_labels: {
            product: '商品',
            company: '公司',
          },
          graph_relation_labels: {
            related_to: '关联',
          },
        },
      }),
    })
  })

  await page.route('**/api/v1/admin/market-graph**', async (route) => {
    marketGraphHit += 1
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        status: 'ok',
        data: {
          nodes: [
            { id: 'n1', type: 'product', name: '示例商品A' },
            { id: 'n2', type: 'company', name: '示例公司B' },
          ],
          edges: [
            {
              type: 'related_to',
              from: { type: 'product', id: 'n1' },
              to: { type: 'company', id: 'n2' },
            },
          ],
        },
      }),
    })
  })

  await page.route('**/api/v1/admin/policy-graph**', async (route) => {
    policyGraphHit += 1
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ status: 'ok', data: { nodes: [], edges: [] } }),
    })
  })

  await page.route('**/api/v1/admin/content-graph**', async (route) => {
    contentGraphHit += 1
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ status: 'ok', data: { nodes: [], edges: [] } }),
    })
  })

  const fulfillWorkflowTemplateList = async (route: Route) => {
    if (route.request().method() === 'POST') {
      workflowTemplateCreateHit += 1
      lastWorkflowTemplateBody = route.request().postDataJSON() as WorkflowTemplateRequest
      if (lastWorkflowTemplateBody.name) createdTemplateNames.push(lastWorkflowTemplateBody.name)
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ status: 'ok', data: { template_id: lastWorkflowTemplateBody.template_id, created: true } }),
      })
      return
    }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        status: 'ok',
        data: {
          items: options.workflowTemplate
            ? [
                { template_id: 'gp-workflow-template', name: 'GraphPage Workflow Template', active_version_id: 'v-active' },
                ...createdTemplateNames.map((name) => ({ template_id: name.replace(/\s+/g, '_'), name })),
              ]
            : createdTemplateNames.map((name) => ({ template_id: name.replace(/\s+/g, '_'), name })),
          total: options.workflowTemplate ? 1 + createdTemplateNames.length : createdTemplateNames.length,
        },
      }),
    })
  }

  await page.route('**/api/v1/workflow-graph/templates', fulfillWorkflowTemplateList)
  await page.route('**/api/v1/workflow-graph/templates?**', fulfillWorkflowTemplateList)

  await page.route('**/api/v1/workflow-graph/templates/gp-workflow-template**', async (route) => {
    const method = route.request().method()
    if (method === 'PATCH') {
      workflowTemplateRenameHit += 1
      lastWorkflowTemplateBody = route.request().postDataJSON() as WorkflowTemplateRequest
    }
    if (method === 'DELETE') workflowTemplateDeleteHit += 1
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ status: 'ok', data: { template_id: 'gp-workflow-template', updated: method === 'PATCH', deleted: method === 'DELETE' } }),
    })
  })

  await page.route('**/api/v1/workflow-graph/templates/gp-workflow-template/versions**', async (route) => {
    const url = new URL(route.request().url())
    const method = route.request().method()
    if (method === 'POST' && url.pathname.endsWith('/versions')) {
      workflowTemplateVersionSaveHit += 1
      lastWorkflowTemplateBody = route.request().postDataJSON() as WorkflowTemplateRequest
      savedTemplateVersion = true
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ status: 'ok', data: { template_id: 'gp-workflow-template', version_id: lastWorkflowTemplateBody.version_id, created: true } }),
      })
      return
    }
    if (method === 'GET' && url.pathname.endsWith('/versions/v-e2e')) {
      workflowTemplateVersionLoadHit += 1
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          status: 'ok',
          data: {
            template_id: 'gp-workflow-template',
            version_id: 'v-e2e',
            version: {
              version_id: 'v-e2e',
              dsl: { nodes: [{ id: 'loaded-node', type: 'product', name: '版本读回节点' }], edges: [] },
            },
          },
        }),
      })
      return
    }
    if (method === 'POST' && url.pathname.endsWith('/activate')) {
      workflowTemplateVersionActivateHit += 1
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ status: 'ok', data: { template_id: 'gp-workflow-template', version_id: 'v-e2e', activated: true } }),
      })
      return
    }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        status: 'ok',
        data: {
          active_version_id: savedTemplateVersion ? 'v-e2e' : 'v-active',
          items: [
            ...(savedTemplateVersion ? [{ version_id: 'v-e2e', version_name: 'E2E version', activated: true }] : []),
            { version_id: 'v-active', version_name: 'Active version', activated: !savedTemplateVersion },
          ],
          total: savedTemplateVersion ? 2 : 1,
        },
      }),
    })
  })

  await page.route('**/api/v1/project-customization/workflows/gp-workflow-template/template/versions**', async (route) => {
    if (route.request().method() === 'POST') {
      workflowTemplateStageSaveHit += 1
      lastWorkflowTemplateBody = route.request().postDataJSON() as WorkflowTemplateRequest
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          status: 'ok',
          data: {
            workflow_name: 'gp-workflow-template',
            current_version: 42,
            next_version: 43,
            version_summary: { stage: 'draft', draft_version: 43, active_version: 42, requires_publish: true },
          },
        }),
      })
      return
    }
    workflowTemplateStageAuditHit += 1
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        status: 'ok',
        data: {
          workflow_name: 'gp-workflow-template',
          items: [
            { stage: promotedToStaging ? 'staging' : 'draft', version: 43, steps: [{ name: 'collect' }], requires_publish: true },
            { stage: 'active', version: 42, steps: [{ name: 'collect' }, { name: 'publish' }], requires_publish: false },
          ],
          stage_summary: { active_version: 42, draft_version: 43, requires_publish: true },
        },
      }),
    })
  })

  await page.route('**/api/v1/workflow-graph/templates/E2E_Created_Template/versions**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ status: 'ok', data: { items: [], total: 0 } }),
    })
  })

  await page.route('**/api/v1/project-customization/workflows/E2E_Created_Template/template/versions**', async (route) => {
    workflowTemplateStageAuditHit += 1
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ status: 'ok', data: { workflow_name: 'E2E_Created_Template', items: [], stage_summary: {} } }),
    })
  })

  await page.route('**/api/v1/project-customization/workflows/gp-workflow-template/template/stage**', async (route) => {
    workflowTemplateStageSaveHit += 1
    lastWorkflowTemplateBody = route.request().postDataJSON() as WorkflowTemplateRequest
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        status: 'ok',
        data: {
          workflow_name: 'gp-workflow-template',
          current_version: 42,
          next_version: 43,
          version_summary: { stage: 'draft', draft_version: 43, active_version: 42, requires_publish: true },
        },
      }),
    })
  })

  await page.route('**/api/v1/project-customization/workflows/gp-workflow-template/template/promote**', async (route) => {
    workflowTemplateStagePromoteHit += 1
    lastWorkflowTemplateBody = route.request().postDataJSON() as WorkflowTemplateRequest
    promotedToStaging = lastWorkflowTemplateBody.to_stage === 'staging'
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        status: 'ok',
        data: {
          workflow_name: 'gp-workflow-template',
          promoted: true,
          current_version: 42,
          next_version: 43,
          version_summary: {
            stage: promotedToStaging ? 'staging' : 'active',
            staging_version: 43,
            active_version: promotedToStaging ? 42 : 43,
            requires_publish: promotedToStaging,
          },
        },
      }),
    })
  })

  await page.route('**/api/v1/project-customization/workflows/gp-workflow-template/template/diff**', async (route) => {
    workflowTemplateDiffHit += 1
    lastWorkflowTemplateBody = route.request().postDataJSON() as WorkflowTemplateRequest
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        status: 'ok',
        data: {
          current_version: 42,
          next_version: 43,
          version_summary: { stage: 'draft', active_version: 42, draft_version: 43, will_mutate: false, requires_publish: true },
          diff: {
            board_layout_changed: true,
            steps: [{
              index: 1,
              change_type: 'changed',
              before: { handler: 'collect' },
              after: { handler: 'product', name: '示例商品A', enabled: true },
            }],
            step_count_before: 2,
            step_count_after: 2,
          },
          reason_code: 'BOARD_LAYOUT_CHANGED',
          risk_level: 'medium',
          affected_areas: ['board_layout'],
          policy_change: { changed: false, requires_publish: true, stage: 'draft' },
        },
      }),
    })
  })

  await page.route('**/api/v1/project-customization/workflows/gp-workflow-template/template/rollback/preview**', async (route) => {
    workflowTemplateRollbackPreviewHit += 1
    lastWorkflowTemplateBody = route.request().postDataJSON() as WorkflowTemplateRequest
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        status: 'ok',
        data: {
          workflow_name: 'gp-workflow-template',
          rollback_preview: true,
          rollback_plan: {
            mode: 'preview_only',
            can_execute: true,
            will_mutate: false,
            target_stage: 'draft',
            target_version: 41,
            from_stage: 'active',
            to_stage: 'draft',
            target_stage_record: { steps: [{ name: 'collect' }] },
            requires_explicit_apply: true,
          },
          audit: { action: 'rollback.preview', actor: 'graph-ui', from_stage: 'active', to_stage: 'draft', trace_id: 'graph-ui-rollback-preview' },
          history: [{ action: 'rollback.preview' }],
        },
      }),
    })
  })

  await page.route(/\/api\/v1\/project-customization\/workflows\/gp-workflow-template\/template\/rollback(?:\?.*)?$/, async (route) => {
    workflowTemplateRollbackApplyHit += 1
    lastWorkflowTemplateBody = route.request().postDataJSON() as WorkflowTemplateRequest
    appliedRollback = true
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        status: 'ok',
        data: {
          workflow_name: 'gp-workflow-template',
          rolled_back: true,
          current_version: 44,
          next_version: 44,
          rollback_plan: {
            mode: 'apply',
            can_execute: true,
            will_mutate: true,
            target_stage: 'draft',
            target_version: 41,
            from_stage: 'active',
            to_stage: 'draft',
            target_stage_record: { steps: [{ name: 'collect' }] },
          },
          audit: { action: 'rollback.apply', actor: 'graph-ui', applied_by: 'graph-ui', from_stage: 'active', to_stage: 'draft', trace_id: 'graph-ui-rollback-apply' },
          version_summary: { stage: 'draft', draft_version: 44, active_version: 42, requires_publish: true },
          history: [{ action: 'rollback.preview' }, { action: 'rollback.apply' }],
        },
      }),
    })
  })

  await page.route('**/api/v1/project-customization/workflows/gp-workflow-template/run**', async (route) => {
    workflowDryRunHit += 1
    lastWorkflowDryRunBody = route.request().postDataJSON() as WorkflowDryRunRequest
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        status: 'ok',
        data: {
          workflow_name: 'gp-workflow-template',
          dry_run: true,
          status: 'planned',
          config_version: 42,
          readiness: 'ready',
          will_execute: false,
          writes_blocked: true,
          requires_publish: true,
          steps: [
            { step: 'collect', status: 'ready', will_execute: false, writes_blocked: true },
            { step: 'publish', status: 'blocked', will_execute: false, writes_blocked: true },
          ],
        },
      }),
    })
  })

  await page.route('**/workflow-graph/curated/**/draft**', async (route) => {
    curatedDraftHit += 1
    lastCuratedDraftBody = route.request().postDataJSON() as CuratedDraftRequest
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        status: 'ok',
        data: {
          graph_id: 'cg-graphpage-e2e',
          sync_status: 'draft_saved',
          revision: 0,
          base_version: 1,
        },
      }),
    })
  })

  await page.route('**/workflow-graph/curated/**/submit**', async (route) => {
    curatedSubmitHit += 1
    lastCuratedSubmitBody = route.request().postDataJSON() as CuratedSubmitRequest
    if (options.curatedSubmitConflict) {
      await route.fulfill({
        status: 400,
        contentType: 'application/json',
        body: JSON.stringify({
          status: 'error',
          data: null,
          error: {
            code: 'INVALID_INPUT',
            message: 'conflict: revision mismatch expected=0 actual=1',
            details: {
              category: 'version_conflict',
              expected_revision: 0,
              actual_revision: 1,
            },
          },
        }),
      })
      return
    }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        status: 'ok',
        data: {
          graph_id: 'cg-graphpage-e2e',
          submit_status: 'submitted',
          revision: 1,
          active_version_id: 'cver_graphpage_e2e',
          audit_id: 'audit_graphpage_e2e',
        },
      }),
    })
  })

  await page.route('**/workflow-graph/curated/**/audit**', async (route) => {
    curatedAuditHit += 1
    const items = curatedRollbackHit > 0
      ? [
          {
            audit_id: 'audit_rollback_graphpage_e2e',
            action: 'rollback',
            version_id: 'cver_rollback_graphpage_e2e',
            rollback_from_version_id: 'cver_graphpage_e2e',
            to_revision: 2,
          },
          {
            audit_id: 'audit_graphpage_e2e',
            action: 'submit',
            version_id: 'cver_graphpage_e2e',
            to_revision: 1,
          },
        ]
      : [
          {
            audit_id: 'audit_graphpage_e2e',
            action: 'submit',
            version_id: 'cver_graphpage_e2e',
            to_revision: 1,
          },
        ]
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        status: 'ok',
        data: {
          graph_id: 'cg-graphpage-e2e',
          items,
          total: items.length,
          base_version: 2,
        },
      }),
    })
  })

  await page.route('**/workflow-graph/curated/**/rollback**', async (route) => {
    curatedRollbackHit += 1
    lastCuratedRollbackBody = route.request().postDataJSON() as CuratedRollbackRequest
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        status: 'ok',
        data: {
          graph_id: 'cg-graphpage-e2e',
          rollback_status: 'succeeded',
          revision: 2,
          active_version_id: 'cver_rollback_graphpage_e2e',
          rollback_from_version_id: lastCuratedRollbackBody?.target_version_id,
          audit_id: 'audit_rollback_graphpage_e2e',
          rollback_contract: {
            contract_version: 'workflow_graph.rollback.v1',
            target_version_id: lastCuratedRollbackBody?.target_version_id,
          },
        },
      }),
    })
  })

  await page.route('**/workflow-graph/curated/**/handoff/reporting**', async (route) => {
    curatedReportingHandoffHit += 1
    lastCuratedReportingHandoffBody = route.request().postDataJSON() as CuratedReportingHandoffRequest
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        status: 'ok',
        data: {
          contract_version: 'graph_handoff.v1',
          handoff_id: 'h-report-graphpage-e2e',
          owner: 'workflow_graph.backend_bridge',
          producer: 'workflow_graph.backend_bridge',
          handoff_mode: 'pull_prepared_evidence',
          consumer: 'llm_report.generate',
          report_generate_request: {
            topic: lastCuratedReportingHandoffBody?.topic,
            sources: [
              {
                id: 'GRAPHNODE-n1',
                title: '示例商品A',
                url: 'https://example.com/graph-node-n1',
                publisher: 'graph:product',
                evidence: 'Graph node n1 selected from curated graph.',
              },
            ],
            section_titles: [],
          },
          evidence_pack: {
            contract_version: 'graph_evidence_pack.v1',
            pack_id: 'gep-graphpage-e2e',
            graph_id: 'cg-graphpage-e2e',
            graph_scope: 'curated_business_graph',
            selected_nodes: [{ node_id: 'n1', node_type: 'product' }],
            relations: [],
            provenance: { source: 'workflow_graph.curated' },
          },
          persistence: {
            contract_version: 'workflow_graph.handoff.v1',
            run_id: 'run-report-graphpage-e2e',
            handoff_id: 'h-report-graphpage-e2e',
            backend_marker: 'workflow_graph.run_store',
          },
        },
      }),
    })
  })

  await page.route('**/workflow-graph/runs/**/handoff/**/replay**', async (route) => {
    handoffReplayHit += 1
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        status: 'ok',
        data: {
          contract_version: 'workflow_graph.handoff.v1',
          run_id: 'run-report-graphpage-e2e',
          handoff_id: 'h-report-graphpage-e2e',
          events: [
            { seq: 1, type: 'handoff.persisted' },
            { seq: 2, type: 'handoff.replayed' },
          ],
          result: {
            handoff_id: 'h-report-graphpage-e2e',
            producer: 'workflow_graph.backend_bridge',
          },
        },
      }),
    })
  })

  return {
    get graphConfigHit() {
      return graphConfigHit
    },
    get marketGraphHit() {
      return marketGraphHit
    },
    get policyGraphHit() {
      return policyGraphHit
    },
    get contentGraphHit() {
      return contentGraphHit
    },
    get curatedDraftHit() {
      return curatedDraftHit
    },
    get curatedSubmitHit() {
      return curatedSubmitHit
    },
    get curatedAuditHit() {
      return curatedAuditHit
    },
    get curatedRollbackHit() {
      return curatedRollbackHit
    },
    get curatedReportingHandoffHit() {
      return curatedReportingHandoffHit
    },
    get handoffReplayHit() {
      return handoffReplayHit
    },
    get workflowDryRunHit() {
      return workflowDryRunHit
    },
    get workflowTemplateCreateHit() {
      return workflowTemplateCreateHit
    },
    get workflowTemplateRenameHit() {
      return workflowTemplateRenameHit
    },
    get workflowTemplateDeleteHit() {
      return workflowTemplateDeleteHit
    },
    get workflowTemplateVersionSaveHit() {
      return workflowTemplateVersionSaveHit
    },
    get workflowTemplateVersionLoadHit() {
      return workflowTemplateVersionLoadHit
    },
    get workflowTemplateVersionActivateHit() {
      return workflowTemplateVersionActivateHit
    },
    get workflowTemplateStageSaveHit() {
      return workflowTemplateStageSaveHit
    },
    get workflowTemplateStagePromoteHit() {
      return workflowTemplateStagePromoteHit
    },
    get workflowTemplateRollbackPreviewHit() {
      return workflowTemplateRollbackPreviewHit
    },
    get workflowTemplateRollbackApplyHit() {
      return workflowTemplateRollbackApplyHit
    },
    get workflowTemplateDiffHit() {
      return workflowTemplateDiffHit
    },
    get workflowTemplateStageAuditHit() {
      return workflowTemplateStageAuditHit
    },
    get lastCuratedDraftBody() {
      return lastCuratedDraftBody
    },
    get lastCuratedSubmitBody() {
      return lastCuratedSubmitBody
    },
    get lastCuratedRollbackBody() {
      return lastCuratedRollbackBody
    },
    get lastCuratedReportingHandoffBody() {
      return lastCuratedReportingHandoffBody
    },
    get lastWorkflowDryRunBody() {
      return lastWorkflowDryRunBody
    },
    get lastWorkflowTemplateBody() {
      return lastWorkflowTemplateBody
    },
    get appliedRollback() {
      return appliedRollback
    },
  }
}

test('graph page smoke test loads with mocked graph APIs', async ({ page }) => {
  const hits = await setupGraphPageMocks(page)

  const response = await page.goto('/#graph.html?type=market')
  expect(response?.ok()).toBeTruthy()

  await expect(page.getByRole('heading', { level: 1, name: '市场图谱', exact: true })).toBeVisible()

  await expect(page.getByRole('button', { name: '3D模式', exact: true })).toBeVisible()

  expect(hits.graphConfigHit).toBeGreaterThan(0)
  expect(hits.marketGraphHit).toBeGreaterThan(0)
})

test('graph page can switch 2D/3D mode and interact with key slider', async ({ page }) => {
  await setupGraphPageMocks(page)

  const response = await page.goto('/#graph.html?type=market')
  expect(response?.ok()).toBeTruthy()

  await expect(page.getByRole('heading', { level: 1, name: '市场图谱', exact: true })).toBeVisible()

  const renderModeToggle = page.locator('button[title="轻量3D模型模式（中心锁定，非相机视角）"]').first()
  await expect(renderModeToggle).toHaveText('3D模式')
  await renderModeToggle.click()
  await expect(renderModeToggle).toHaveText('回到2D')

  const repulsionSlider = page.getByRole('slider', { name: /^斥力/ }).first()
  await expect(repulsionSlider).toBeVisible()

  const initial = Number(await repulsionSlider.inputValue())
  await repulsionSlider.focus()
  await repulsionSlider.press('ArrowRight')
  const updated = Number(await repulsionSlider.inputValue())
  expect(updated).not.toBe(initial)
})

test('graph page renders force3d canvas backed by graph scene nodes', async ({ page }) => {
  await setupGraphPageMocks(page)

  const response = await page.goto('/#graph.html?type=market')
  expect(response?.ok()).toBeTruthy()

  await expect(page.getByRole('heading', { level: 1, name: '市场图谱', exact: true })).toBeVisible()

  const renderModeToggle = page.locator('button[title="轻量3D模型模式（中心锁定，非相机视角）"]').first()
  await expect(renderModeToggle).toHaveText('3D模式')
  await renderModeToggle.click()
  await expect(renderModeToggle).toHaveText('回到2D')

  const engineSelect = page.locator('label.gv2-control-chip', { hasText: '3D引擎' }).locator('select')
  await expect(engineSelect).toBeVisible()

  const outcomeHandle = await page.waitForFunction(() => {
    type Graph3DStats = {
      dataNodes: number
      sceneNodeObjects: number
    }
    const debugWindow = window as Window & {
      __graph3dDebug?: {
        getVisibilityStats: () => Graph3DStats
      }
    }
    const canvas = document.querySelector('[data-testid="graph-force3d-canvas-host"] canvas') as HTMLCanvasElement | null
    const stats = debugWindow.__graph3dDebug?.getVisibilityStats()
    if (canvas && canvas.width > 0 && canvas.height > 0 && stats && stats.dataNodes === 2 && stats.sceneNodeObjects >= 2) {
      return { mode: 'force3d', stats }
    }
    const fallbackText = Array.from(document.querySelectorAll('.gv2-loading'))
      .map((node) => node.textContent || '')
      .join('\n')
    const engineValue = Array.from(document.querySelectorAll('label.gv2-control-chip'))
      .find((node) => (node.textContent || '').includes('3D引擎'))
      ?.querySelector<HTMLSelectElement>('select')
      ?.value || ''
    if (fallbackText.includes('已自动降级到 legacy-projection') && engineValue === 'legacy') {
      return { mode: 'fallback', fallbackText, engineValue }
    }
    return false
  }, null, { timeout: 20000 })

  const outcome = await outcomeHandle.jsonValue() as
    | { mode: 'force3d'; stats: { dataNodes: number; sceneNodeObjects: number } }
    | { mode: 'fallback'; fallbackText: string; engineValue: string }

  await expect(page.getByRole('heading', { level: 1, name: '市场图谱', exact: true })).toBeVisible()
  if (outcome.mode === 'force3d') {
    await expect(page.getByTestId('graph-force3d-canvas-host')).toBeVisible()
    expect(outcome.stats.dataNodes).toBe(2)
    expect(outcome.stats.sceneNodeObjects).toBeGreaterThanOrEqual(2)
  } else {
    expect(outcome.fallbackText).toContain('3D引擎渲染失败')
    expect(outcome.engineValue).toBe('legacy')
  }
})

test('market subgraph tabs reuse one total graph while rescheduling an isolated 3D display resource', async ({ page }) => {
  const hits = await setupGraphPageMocks(page)
  const response = await page.goto('/#graph.html?type=market')
  expect(response?.ok()).toBeTruthy()
  await expect(page.getByRole('tablist', { name: '图谱' })).toBeVisible()

  const renderModeToggle = page.locator('button[title="轻量3D模型模式（中心锁定，非相机视角）"]').first()
  await renderModeToggle.click()
  const canvasHost = page.getByTestId('graph-force3d-canvas-host')
  await expect(canvasHost).toBeVisible({ timeout: 20000 })
  await expect.poll(async () => page.evaluate(() => {
    const host = document.querySelector('[data-testid="graph-force3d-canvas-host"]') as HTMLElement | null
    const canvas = host?.querySelector('canvas') as HTMLCanvasElement | null
    const stats = (window as Window & { __graph3dDebug?: { getVisibilityStats: () => { dataNodes: number; sceneNodeObjects: number } } })
      .__graph3dDebug?.getVisibilityStats()
    return Boolean(host && canvas && canvas.width > 0 && canvas.height > 0 && stats && stats.dataNodes > 0 && stats.sceneNodeObjects >= stats.dataNodes)
  }), { timeout: 20000 }).toBe(true)
  const sourceReadCount = hits.marketGraphHit

  for (const projectionId of ['graphDeep', 'graphCompany', 'graphProduct', 'graphOperation', 'graphMarket']) {
    const tab = page.getByTestId(`graph-workspace-tab-${projectionId}`)
    await tab.click()
    await expect(tab).toHaveAttribute('aria-selected', 'true')
    await expect.poll(async () => page.evaluate(() => {
      const host = document.querySelector('[data-testid="graph-force3d-canvas-host"]') as HTMLElement | null
      const canvas = host?.querySelector('canvas') as HTMLCanvasElement | null
      const stats = (window as Window & { __graph3dDebug?: { getVisibilityStats: () => { dataNodes: number; sceneNodeObjects: number } } })
        .__graph3dDebug?.getVisibilityStats()
      return Boolean(host && canvas && canvas.width > 0 && canvas.height > 0 && stats && stats.dataNodes > 0 && stats.sceneNodeObjects >= stats.dataNodes)
    }), { timeout: 20000 }).toBe(true)
  }

  expect(hits.marketGraphHit).toBe(sourceReadCount)

  const policyTab = page.getByTestId('graph-workspace-tab-graphPolicy')
  await policyTab.click()
  await expect(policyTab).toHaveAttribute('aria-selected', 'true')
  await expect(page).toHaveURL(/#\/visual\/graph\/policy$/)
  await expect(page.getByRole('heading', { level: 1, name: '政策图谱', exact: true })).toBeVisible()
})

test('graph page survives rapid 3D engine switch with viewport evidence or fallback', async ({ page }) => {
  await setupGraphPageMocks(page)

  const response = await page.goto('/#graph.html?type=market')
  expect(response?.ok()).toBeTruthy()

  await expect(page.getByRole('heading', { level: 1, name: '市场图谱', exact: true })).toBeVisible()

  const renderModeToggle = page.locator('button[title="轻量3D模型模式（中心锁定，非相机视角）"]').first()
  await expect(renderModeToggle).toHaveText('3D模式')
  await renderModeToggle.click()
  await expect(renderModeToggle).toHaveText('回到2D')

  const engineSelect = page.locator('label.gv2-control-chip', { hasText: '3D引擎' }).locator('select')
  await expect(engineSelect).toBeVisible()

  await engineSelect.selectOption('legacy')
  await page.waitForTimeout(40)
  await engineSelect.selectOption('force3d')
  await page.waitForTimeout(40)
  await engineSelect.selectOption('legacy')
  await page.waitForTimeout(40)
  await engineSelect.selectOption('force3d')

  const outcomeHandle = await page.waitForFunction(() => {
    type Graph3DStats = {
      dataNodes: number
      sceneNodeObjects: number
    }
    const debugWindow = window as Window & {
      __graph3dDebug?: {
        getVisibilityStats: () => Graph3DStats
      }
    }
    const host = document.querySelector('[data-testid="graph-force3d-canvas-host"]') as HTMLElement | null
    const canvas = host?.querySelector('canvas') as HTMLCanvasElement | null
    const hostRect = host?.getBoundingClientRect()
    const stats = debugWindow.__graph3dDebug?.getVisibilityStats()
    if (
      canvas &&
      hostRect &&
      hostRect.width >= 300 &&
      hostRect.height >= 300 &&
      canvas.width >= 300 &&
      canvas.height >= 300 &&
      stats &&
      stats.dataNodes === 2 &&
      stats.sceneNodeObjects >= 2
    ) {
      return {
        mode: 'force3d',
        stats,
        canvasWidth: canvas.width,
        canvasHeight: canvas.height,
        hostWidth: Math.round(hostRect.width),
        hostHeight: Math.round(hostRect.height),
      }
    }
    const fallbackText = Array.from(document.querySelectorAll('.gv2-loading'))
      .map((node) => node.textContent || '')
      .join('\n')
    const engineValue = Array.from(document.querySelectorAll('label.gv2-control-chip'))
      .find((node) => (node.textContent || '').includes('3D引擎'))
      ?.querySelector<HTMLSelectElement>('select')
      ?.value || ''
    const legacyChart = document.querySelector('.gv2-chart:not(.gv2-chart--force3d)') as HTMLElement | null
    const legacyChartRect = legacyChart?.getBoundingClientRect()
    if (engineValue === 'legacy' && legacyChartRect && legacyChartRect.width >= 300 && legacyChartRect.height >= 300) {
      return {
        mode: fallbackText.includes('已自动降级到 legacy-projection') ? 'fallback' : 'legacy',
        fallbackText,
        engineValue,
        chartWidth: Math.round(legacyChartRect.width),
        chartHeight: Math.round(legacyChartRect.height),
      }
    }
    return false
  }, null, { timeout: 20000 })

  const outcome = await outcomeHandle.jsonValue() as
    | {
      mode: 'force3d'
      stats: { dataNodes: number; sceneNodeObjects: number }
      canvasWidth: number
      canvasHeight: number
      hostWidth: number
      hostHeight: number
    }
    | {
      mode: 'fallback' | 'legacy'
      fallbackText: string
      engineValue: string
      chartWidth: number
      chartHeight: number
    }

  await expect(page.getByRole('heading', { level: 1, name: '市场图谱', exact: true })).toBeVisible()
  await expect(engineSelect).toBeVisible()
  if (outcome.mode === 'force3d') {
    await expect(page.getByTestId('graph-force3d-canvas-host')).toBeVisible()
    expect(outcome.stats.dataNodes).toBe(2)
    expect(outcome.stats.sceneNodeObjects).toBeGreaterThanOrEqual(2)
    expect(Math.abs(outcome.canvasWidth - outcome.hostWidth)).toBeLessThanOrEqual(4)
    expect(Math.abs(outcome.canvasHeight - outcome.hostHeight)).toBeLessThanOrEqual(4)
  } else {
    if (outcome.mode === 'fallback') {
      expect(outcome.fallbackText).toContain('3D引擎渲染失败')
    }
    expect(outcome.engineValue).toBe('legacy')
    expect(outcome.chartWidth).toBeGreaterThanOrEqual(300)
    expect(outcome.chartHeight).toBeGreaterThanOrEqual(300)
  }
})

test('graph builder submits local draft to curated workflow graph API', async ({ page }) => {
  const hits = await setupGraphPageMocks(page)

  const response = await page.goto('/#graph-template-new.html')
  expect(response?.ok()).toBeTruthy()

  await expect(page.getByRole('heading', { level: 1, name: '新建图谱', exact: true })).toBeVisible()
  await expect(page.getByTestId('graph-curated-panel')).toBeVisible()

  await page.getByTestId('graph-curated-graph-id').fill('cg-graphpage-e2e')
  await expect(page.getByText(/Draft: nodes=2 edges=1/)).toBeVisible()

  await page.getByTestId('graph-curated-submit').click()
  await expect(page.getByTestId('graph-curated-status')).toContainText('submitted r1')

  await page.getByTestId('graph-curated-audit').click()
  await expect(page.getByTestId('graph-curated-status')).toContainText('audit_readback items=1')
  await expect(page.getByTestId('graph-curated-audit-list')).toContainText('submit#cver_graphpage_e2e')
  await expect(page.getByTestId('graph-curated-rollback-version')).toHaveValue('cver_graphpage_e2e')

  await page.getByTestId('graph-curated-rollback-reason').fill('restore graphpage e2e version')
  await page.getByTestId('graph-curated-rollback').click()
  await expect(page.getByTestId('graph-curated-status')).toContainText('rollback_succeeded r2 audits=2')
  await expect(page.getByTestId('graph-curated-audit-list')).toContainText('rollback#cver_rollback_graphpage_e2e')

  await page.getByTestId('graph-curated-reporting-topic').fill('robotics reporting')
  await page.getByTestId('graph-curated-reporting-handoff').click()
  await expect(page.getByTestId('graph-curated-status')).toContainText('report_handoff_ready sources=1')
  await page.getByTestId('graph-curated-handoff-replay').click()
  await expect(page.getByTestId('graph-curated-status')).toContainText('handoff_replay_ready events=2')

  expect(hits.policyGraphHit).toBeGreaterThan(0)
  expect(hits.contentGraphHit).toBeGreaterThan(0)
  expect(hits.marketGraphHit).toBeGreaterThan(0)
  expect(hits.curatedDraftHit).toBe(1)
  expect(hits.curatedSubmitHit).toBe(1)
  expect(hits.curatedAuditHit).toBe(2)
  expect(hits.curatedRollbackHit).toBe(1)
  expect(hits.curatedReportingHandoffHit).toBe(1)
  expect(hits.handoffReplayHit).toBe(1)

  expect(hits.lastCuratedDraftBody?.actor_id).toBe('graphpage.curated-consumer')
  expect(hits.lastCuratedDraftBody?.dsl?.nodes).toEqual([
    expect.objectContaining({ id: 'n1', type: 'product', node_id: 'n1', node_type: 'product', title: '示例商品A' }),
    expect.objectContaining({ id: 'n2', type: 'company', node_id: 'n2', node_type: 'company', title: '示例公司B' }),
  ])
  expect(hits.lastCuratedDraftBody?.dsl?.edges).toEqual([
    expect.objectContaining({
      from_node_id: 'n1',
      to_node_id: 'n2',
      edge_type: 'related_to',
      from: { id: 'n1', type: 'product' },
      to: { id: 'n2', type: 'company' },
    }),
  ])
  expect(hits.lastCuratedSubmitBody).toEqual(expect.objectContaining({
    actor_id: 'graphpage.curated-consumer',
    base_revision: 0,
    object_scope: 'curated_business_graph',
  }))
  expect(hits.lastCuratedRollbackBody).toEqual(expect.objectContaining({
    actor_id: 'graphpage.curated-consumer',
    base_revision: 1,
    target_version_id: 'cver_graphpage_e2e',
    reason: 'restore graphpage e2e version',
  }))
  expect(hits.lastCuratedReportingHandoffBody).toEqual(expect.objectContaining({
    topic: 'robotics reporting',
  }))
})

test('graph builder dry-runs workflow template without writes', async ({ page }) => {
  const hits = await setupGraphPageMocks(page, { workflowTemplate: true })

  const response = await page.goto('/#graph-template-new.html')
  expect(response?.ok()).toBeTruthy()

  await expect(page.getByRole('heading', { level: 1, name: '新建图谱', exact: true })).toBeVisible()
  await expect(page.getByTestId('graph-template-dry-run')).toBeEnabled()

  await page.getByTestId('graph-template-dry-run').click()
  await expect(page.getByTestId('graph-template-dry-run-result')).toContainText('config_version=42')
  await expect(page.getByTestId('graph-template-dry-run-result')).toContainText('readiness=ready')
  await expect(page.getByTestId('graph-template-dry-run-result')).toContainText('writes_blocked=true')
  await expect(page.getByTestId('graph-template-dry-run-result')).toContainText('requires_publish=true')
  await expect(page.getByTestId('graph-template-dry-run-result')).toContainText('#1 collect: status=ready')
  await expect(page.getByTestId('graph-template-dry-run-result')).toContainText('#2 publish: status=blocked')

  expect(hits.workflowDryRunHit).toBe(1)
  expect(hits.lastWorkflowDryRunBody).toEqual(expect.objectContaining({
    dry_run: true,
    params: {},
  }))
})

test('graph builder controls complete template lifecycle with staging and rollback evidence', async ({ page }) => {
  const hits = await setupGraphPageMocks(page, { workflowTemplate: true })

  const response = await page.goto('/#graph-template-new.html')
  expect(response?.ok()).toBeTruthy()

  await expect(page.getByRole('heading', { level: 1, name: '新建图谱', exact: true })).toBeVisible()
  await expect(page.getByTestId('graph-template-select')).toHaveValue('gp-workflow-template')
  await expect(page.getByText(/draft/).first()).toBeVisible()

  await page.getByTestId('graph-template-stage-audit-refresh').click()
  await expect.poll(() => hits.workflowTemplateStageAuditHit).toBeGreaterThanOrEqual(2)

  await page.getByTestId('graph-template-diff').click()
  await expect(page.getByTestId('graph-template-diff-result')).toContainText('current=42')
  await expect(page.getByTestId('graph-template-diff-result')).toContainText('next=43')
  await expect(page.getByTestId('graph-template-diff-result')).toContainText('changes=1')
  expect(hits.workflowTemplateDiffHit).toBe(1)

  await page.getByTestId('graph-template-stage-save').click()
  await expect.poll(() => hits.workflowTemplateStageSaveHit).toBe(1)
  await expect(page.getByText(/draft/).first()).toBeVisible()

  await page.getByTestId('graph-template-stage-promote').click()
  await expect.poll(() => hits.workflowTemplateStagePromoteHit).toBe(1)
  await page.getByTestId('graph-template-stage-apply').click()
  await expect.poll(() => hits.workflowTemplateStagePromoteHit).toBe(2)

  await page.getByTestId('graph-template-rollback-stage').selectOption('draft')
  await page.getByTestId('graph-template-rollback-version').fill('41')
  await page.getByTestId('graph-template-rollback-reason').fill('restore draft for graph e2e')
  await page.getByTestId('graph-template-rollback-preview').click()
  await expect(page.getByTestId('graph-template-rollback-preview')).toBeEnabled()
  await expect(page.getByTestId('graph-template-rollback-result')).toContainText('mode=preview_only')
  await expect(page.getByTestId('graph-template-rollback-result')).toContainText('will_mutate=false')
  expect(hits.workflowTemplateRollbackPreviewHit).toBe(1)

  await page.getByTestId('graph-template-rollback-apply').click()
  await expect(page.getByTestId('graph-template-rollback-result')).toContainText('mode=apply')
  await expect(page.getByTestId('graph-template-rollback-result')).toContainText('action=rollback.apply')
  await expect.poll(() => hits.workflowTemplateRollbackApplyHit).toBe(1)
  expect(hits.appliedRollback).toBe(true)

  await page.getByTestId('graph-template-version-name').fill('v-e2e')
  await page.getByTestId('graph-template-version-save').click()
  await expect.poll(() => hits.workflowTemplateVersionSaveHit).toBe(1)
  expect(hits.lastWorkflowTemplateBody).toEqual(expect.objectContaining({
    version_id: 'v-e2e',
    dsl: expect.objectContaining({ nodes: expect.any(Array), edges: expect.any(Array) }),
  }))

  await page.getByTestId('graph-template-version-select').selectOption('v-e2e')
  await page.getByTestId('graph-template-version-load').click()
  await expect.poll(() => hits.workflowTemplateVersionLoadHit).toBe(1)
  await expect(page.getByText(/Draft: nodes=1 edges=0/)).toBeVisible()

  await page.getByTestId('graph-template-version-activate').click()
  await expect.poll(() => hits.workflowTemplateVersionActivateHit).toBe(1)

  await page.getByTestId('graph-template-create-name').fill('E2E Created Template')
  await page.getByTestId('graph-template-create').click()
  await expect.poll(() => hits.workflowTemplateCreateHit).toBe(1)
  expect(hits.lastWorkflowTemplateBody).toEqual(expect.objectContaining({
    template_id: 'E2E_Created_Template',
    name: 'E2E Created Template',
  }))

  await page.getByTestId('graph-template-select').selectOption('gp-workflow-template')
  await page.getByTestId('graph-template-rename-name').fill('Renamed Graph Template')
  await page.getByTestId('graph-template-rename').click()
  await expect.poll(() => hits.workflowTemplateRenameHit).toBe(1)
  expect(hits.lastWorkflowTemplateBody).toEqual(expect.objectContaining({ name: 'Renamed Graph Template' }))

  await page.getByTestId('graph-template-delete').click()
  await expect.poll(() => hits.workflowTemplateDeleteHit).toBe(1)
})

test('graph builder surfaces curated submit conflict without retrying destructively', async ({ page }) => {
  const hits = await setupGraphPageMocks(page, { curatedSubmitConflict: true })
  page.on('dialog', (dialog) => {
    void dialog.dismiss()
  })

  const response = await page.goto('/#graph-template-new.html')
  expect(response?.ok()).toBeTruthy()

  await expect(page.getByRole('heading', { level: 1, name: '新建图谱', exact: true })).toBeVisible()
  await expect(page.getByTestId('graph-curated-panel')).toBeVisible()

  await page.getByTestId('graph-curated-graph-id').fill('cg-graphpage-e2e')
  await page.getByTestId('graph-curated-submit').click()
  await expect(page.getByTestId('graph-curated-status')).toContainText('submit_conflict: version_conflict')
  await expect(page.getByTestId('graph-curated-status')).toContainText('expected=0 actual=1')

  expect(hits.curatedDraftHit).toBe(1)
  expect(hits.curatedSubmitHit).toBe(1)
  expect(hits.lastCuratedSubmitBody).toEqual(expect.objectContaining({
    actor_id: 'graphpage.curated-consumer',
    base_revision: 0,
    object_scope: 'curated_business_graph',
  }))
})
