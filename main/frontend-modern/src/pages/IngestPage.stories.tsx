import { useState } from 'react'
import type { Meta, StoryObj } from '@storybook/react-vite'
import { expect, mocked, userEvent } from 'storybook/test'
import * as api from '../lib/api'
import type { IngestFormState } from '../lib/types'
import IngestPage, { IngestPageView, type IngestPageViewProps } from './IngestPage'
import { StorybookKernelShell } from './storybookKernelUtils'
import { pageDecorators, pageParameters } from './storybookPageUtils'

const pendingIngestResult = new Promise<never>(() => undefined)

function createIngestViewProps(overrides: Partial<IngestPageViewProps> = {}): IngestPageViewProps {
  const form: IngestFormState = {
    queryTerms: 'California gas price, refinery outage, retail margin',
    topicFocus: '',
    languages: ['zh', 'en'],
    provider: 'serpapi',
    maxItems: 24,
    startOffset: '1',
    daysBack: '14',
    enableExtraction: true,
    asyncMode: true,
    socialPlatform: 'reddit',
    baseSubreddits: 'MachineLearning, robotics, singularity',
    enableSubredditDiscovery: true,
    commodityLimit: 30,
    ecomLimit: 100,
    sourceItemKey: '',
    sourceHandlerKey: '',
    singleUrl: 'https://example.com/article',
    singleUrlStrictMode: false,
    singleUrlSearchExpand: true,
    singleUrlSearchExpandLimit: 3,
    singleUrlSearchProvider: 'auto',
    singleUrlSearchFallbackProvider: 'ddg_html',
    singleUrlFallbackOnInsufficient: true,
    singleUrlAllowSearchSummaryWrite: false,
    singleUrlMinResultsRequired: 6,
    singleUrlTargetCandidates: 6,
    singleUrlDecodeRedirectWrappers: true,
    singleUrlFilterLowValueCandidates: true,
    singleUrlLightFilterEnabled: true,
    singleUrlLightFilterMinScore: 30,
    singleUrlLightFilterRejectStaticAssets: true,
    singleUrlLightFilterRejectSearchNoiseDomain: true,
  }

  return {
    variant: 'ingest',
    pageTitle: '采集',
    pageScopeLabel: 'execution + agent-batch',
    form,
    setForm: (() => undefined) as IngestPageViewProps['setForm'],
    actionPending: false,
    actionMessage: '准备执行采集任务',
    sourceItemList: [
      {
        item_key: 'market_monitor',
        name: '市场监控',
        description: '跟踪储能和电池关键来源',
        params: { provider: 'serpapi' },
      },
    ],
    selectedSourceItem: null,
    handlerGroupedByEntryType: {
      search: { count: 6 },
      news: { count: 3 },
    },
    handlerKeys: ['news', 'search'],
    historyRows: [
      {
        id: 1,
        task_id: 'ingest-001',
        task_name: 'market_ingest',
        status: 'completed',
        started_at: '2026-04-02T16:00:00Z',
        finished_at: '2026-04-02T16:04:00Z',
        params: { rejected_count: 0, degradation_flags: [] },
      },
    ],
    agentBatchJobId: 'batch-101',
    agentBatchJob: {
      job_id: 'batch-101',
      status: 'running',
      progress: { total: 4, succeeded: 2, failed: 1, queued: 1 },
    },
    agentBatchItems: [
      {
        item_id: 'market-1',
        task_id: 'task-001',
        status: 'completed',
        error: null,
      },
      {
        item_id: 'market-2',
        task_id: 'task-002',
        status: 'failed',
        error: 'provider timeout',
      },
    ],
    agentBatchEvents: [
      {
        id: 'evt-1',
        ts: '2026-04-02T16:02:00Z',
        event_type: 'item.completed',
        item_id: 'market-1',
        message: 'completed',
      },
      {
        id: 'evt-2',
        ts: '2026-04-02T16:03:00Z',
        event_type: 'item.failed',
        item_id: 'market-2',
        message: 'provider timeout',
      },
    ],
    agentBatchRejectedReasonCodes: ['quota_exceeded'],
    onSourceItemChange: () => undefined,
    onSuggestKeywords: () => undefined,
    onSyncSourceLibrary: () => undefined,
    onRunSourceLibrary: () => undefined,
    onIngestSingleUrl: () => undefined,
    onIngestPolicyRegulation: () => undefined,
    onIngestMarket: () => undefined,
    onIngestDataApi: () => undefined,
    onIngestCommodity: () => undefined,
    onIngestEcom: () => undefined,
    onSubmitAgentBatch: () => undefined,
    onSubmitNlAgentBatch: () => undefined,
    onRefreshBatchStatus: () => undefined,
    onRetryBatchItem: () => undefined,
    onRefreshHistory: () => undefined,
    ...overrides,
  }
}

function IngestViewStory(props: Partial<IngestPageViewProps>) {
  const initialProps = createIngestViewProps(props)
  const [form, setForm] = useState(initialProps.form)
  return <IngestPageView {...initialProps} form={form} setForm={setForm} />
}

function applyIngestMocks(mode: 'ready' | 'empty' | 'market-error' | 'loading') {
  if (mode === 'ready' || mode === 'market-error') {
    mocked(api.listSourceItems).mockResolvedValue([
      {
        item_key: 'market_monitor',
        name: '市场监控',
        description: '跟踪储能和电池关键来源',
        params: { provider: 'serpapi' },
      },
    ] as never)
    mocked(api.listSiteEntryGrouped).mockResolvedValue({
      by_entry_type: {
        search: { count: 6 },
        news: { count: 3 },
      },
    } as never)
    mocked(api.listIngestHistory).mockResolvedValue([
      {
        id: 1,
        task_id: 'ingest-001',
        task_name: 'market_ingest',
        status: 'completed',
        started_at: '2026-04-02T16:00:00Z',
        finished_at: '2026-04-02T16:04:00Z',
      },
    ] as never)
  } else if (mode === 'empty') {
    mocked(api.listSourceItems).mockResolvedValue([] as never)
    mocked(api.listSiteEntryGrouped).mockResolvedValue({ by_entry_type: {} } as never)
    mocked(api.listIngestHistory).mockResolvedValue([] as never)
  } else {
    mocked(api.listSourceItems).mockImplementation(() => pendingIngestResult as never)
    mocked(api.listSiteEntryGrouped).mockImplementation(() => pendingIngestResult as never)
    mocked(api.listIngestHistory).mockImplementation(() => pendingIngestResult as never)
  }

  mocked(api.syncSourceLibrary).mockResolvedValue({ ok: true } as never)
  mocked(api.runSourceLibrary).mockResolvedValue({ ok: true } as never)
  mocked(api.ingestPolicyRegulation).mockResolvedValue({ status: 'completed' } as never)
  mocked(api.ingestDataApi).mockResolvedValue({ status: 'completed' } as never)
  mocked(api.ingestCommodity).mockResolvedValue({ status: 'completed' } as never)
  mocked(api.ingestEcom).mockResolvedValue({ status: 'completed' } as never)
  mocked(api.ingestSingleUrl).mockResolvedValue({ status: 'completed' } as never)
  mocked(api.submitAgentBatchJob).mockResolvedValue({ job_id: 'batch-101' } as never)
  mocked(api.getAgentBatchJob).mockResolvedValue({ status: 'queued', progress: {} } as never)
  mocked(api.listAgentBatchItems).mockResolvedValue({ items: [] } as never)
  mocked(api.getAgentBatchEvents).mockResolvedValue({ events: [] } as never)
  mocked(api.retryAgentBatchJob).mockResolvedValue({ ok: true } as never)
  mocked(api.runAgentBatchNlCommand).mockResolvedValue({ job_id: 'batch-nl-001' } as never)
  mocked(api.validateAgentBatchRuleSet).mockResolvedValue({ valid: true } as never)
  mocked(api.generateKeywords).mockResolvedValue({ keywords: ['储能', '电池'], provider: 'storybook' } as never)
  mocked(api.ingestMarket).mockImplementation(() => {
    if (mode === 'market-error') return Promise.reject(new Error('provider unavailable')) as never
    return Promise.resolve({ status: 'completed' }) as never
  })
}

const meta = {
  title: 'Pages/Workbench/IngestPage',
  component: IngestPage,
  parameters: {
    ...pageParameters,
    docs: {
      description: {
        component: 'Ingest control stories for MCP with shell framing, isolated states, and one interactive failure path.',
      },
    },
  },
  args: {
    projectKey: 'demo-proj',
    variant: 'ingest',
  },
  argTypes: {
    projectKey: { control: 'text' },
    variant: { control: 'radio', options: ['ingest', 'specialized'] },
  },
  beforeEach: async () => {
    applyIngestMocks('ready')
  },
} satisfies Meta<typeof IngestPage>

export default meta

type Story = StoryObj<typeof meta>

export const ContainerDefault: Story = {
  decorators: pageDecorators,
  play: async ({ canvas }) => {
    await expect(canvas.getByText('Agent 批量采集')).toBeInTheDocument()
    await expect(canvas.getByText('最近任务状态')).toBeInTheDocument()
  },
}

export const ViewDefault: Story = {
  render: () => <IngestViewStory />,
  play: async ({ canvas }) => {
    await expect(canvas.getByText('采集 / execution + agent-batch')).toBeInTheDocument()
    await expect(canvas.getByText('状态 running')).toBeInTheDocument()
  },
}

export const ContainerLoadingState: Story = {
  decorators: pageDecorators,
  beforeEach: async () => {
    applyIngestMocks('loading')
  },
  play: async ({ canvas }) => {
    await expect(canvas.getByText('Agent 批量采集')).toBeInTheDocument()
  },
}

export const ContainerEmptyState: Story = {
  decorators: pageDecorators,
  beforeEach: async () => {
    applyIngestMocks('empty')
  },
  play: async ({ canvas }) => {
    await expect(canvas.getByText('暂无任务记录')).toBeInTheDocument()
  },
}

export const ContainerActionError: Story = {
  decorators: pageDecorators,
  beforeEach: async () => {
    applyIngestMocks('market-error')
  },
  play: async ({ canvas }) => {
    await userEvent.click(canvas.getByRole('button', { name: '市场采集' }))
    await expect(canvas.getByText('市场采集 失败: provider unavailable')).toBeInTheDocument()
  },
}

export const ContainerSpecializedMode: Story = {
  decorators: pageDecorators,
  args: {
    variant: 'specialized',
  },
  play: async ({ canvas }) => {
    await expect(canvas.getByText('特化采集')).toBeInTheDocument()
  },
}

export const ShellIngest: Story = {
  render: (args) => <StorybookKernelShell moduleKey="flowIngest" projectKey={args.projectKey} />,
  play: async ({ canvas }) => {
    await expect(canvas.getByText('Agent 批量采集')).toBeInTheDocument()
  },
}

export const ShellSpecialized: Story = {
  render: (args) => <StorybookKernelShell moduleKey="flowSpecialized" projectKey={args.projectKey} />,
  play: async ({ canvas }) => {
    await expect(canvas.getByText('特化采集')).toBeInTheDocument()
  },
}
