import type { Meta, StoryObj } from '@storybook/react-vite'
import { expect, mocked } from 'storybook/test'
import * as api from '../lib/api'
import ResourcePage from './ResourcePage'
import { pageDecorators, pageParameters } from './storybookPageUtils'

function applyResourceMocks() {
  mocked(api.listSourceLibraryItemsWithScope).mockResolvedValue([
    {
      item_key: 'market.news.system',
      name: 'Market News Cluster',
      channel_key: 'handler.cluster',
      scope: 'effective',
      enabled: true,
      item_type: 'service_aggregated',
      managed_by: 'system',
      capability_summary: {
        capability_id: 'source_library.collect',
        execution_mode: 'handler_cluster',
        entry_type: 'search_template',
        runner_ref: 'handler.cluster.search_template',
        source_mode: 'site_search',
        enabled: true,
      },
      execution_plan: {
        contract_version: 'source_library.item_execution_plan.v1',
        execution_mode: 'handler_cluster',
        runner_key: 'handler.cluster.search_template',
        source_mode: 'site_search',
        expected_entry_type: 'search_template',
      },
      params: {
        source_mode: 'site_search',
        site_entries: ['https://example.com/search?q={query}'],
      },
    },
    {
      item_key: 'analyst.manual',
      name: 'Analyst Manual Sources',
      channel_key: 'generic_web.rss',
      scope: 'project',
      enabled: true,
      extra: {
        item_type: 'user_defined',
        managed_by: 'user',
        capability_summary: {
          capability_id: 'source_library.collect',
          execution_mode: 'manual_review',
          entry_type: 'rss',
          runner_ref: 'generic_web.rss',
        },
        expected_entry_type: 'rss',
      },
      params: {
        source_mode: 'rss',
        site_entries: ['https://example.com/feed.xml'],
      },
    },
  ] as never)
  mocked(api.listSourceLibraryItemsGrouped).mockResolvedValue({
    by_handler: {
      search_template: [
        {
          item_key: 'market.news.system',
          name: 'Market News Cluster',
          channel_key: 'handler.cluster',
          enabled: true,
          item_type: 'service_aggregated',
          managed_by: 'system',
          capability_summary: 'source_library.collect | handler_cluster | search_template',
          execution_plan: {
            contract_version: 'source_library.item_execution_plan.v1',
            execution_mode: 'handler_cluster',
            runner_key: 'handler.cluster.search_template',
            source_mode: 'site_search',
            expected_entry_type: 'search_template',
          },
        },
      ],
    },
  } as never)
  mocked(api.listSourceLibraryChannels).mockResolvedValue([
    { channel_key: 'handler.cluster', name: 'Handler Cluster', enabled: true },
    { channel_key: 'generic_web.rss', name: 'RSS', enabled: true },
  ] as never)
  mocked(api.listResourcePoolUrlsWithFilters).mockResolvedValue([
    {
      id: 1,
      url: 'https://example.com/news/1',
      domain: 'example.com',
      source: 'source_library',
      created_at: '2026-05-24T12:00:00Z',
    },
  ] as never)
  mocked(api.listSiteEntriesWithFilters).mockResolvedValue([
    {
      id: 1,
      site_url: 'https://example.com/search?q={query}',
      domain: 'example.com',
      entry_type: 'search_template',
      source: 'source_library',
      enabled: true,
      scope: 'project',
      lifecycle_state: 'needs_review',
      lifecycle_summary: {
        state: 'needs_review',
        enabled: true,
        scope: 'project',
        entry_type: 'search_template',
        source: 'source_library',
        state_source: 'extra.lifecycle_state',
      },
      execution_plan_preview: {
        contract_version: 'source_library.item_execution_plan.v1',
        site_entry_urls: ['https://example.com/search?q={query}'],
        expected_entry_type: 'search_template',
        route_bucket_counts: { total: 1, search_template: 1, site_entries: 1 },
        plan_meta: { preview_source: 'resource_pool.site_entry', route_bucket: 'search_template' },
      },
      review_closure: {
        status: 'needs_review',
        state: 'needs_review',
        executable: false,
        report_source_ref: 'resource_pool:site_entry:example.com',
        next_actions: [
          {
            action: 'collect_source_library_run',
            enabled: false,
            blocked: true,
            block_reason: 'requires_acceptance',
          },
        ],
      },
    },
  ] as never)
  mocked(api.extractResourcePoolFromDocuments).mockResolvedValue({ task_id: 'extract-1' } as never)
  mocked(api.discoverSiteEntriesAdvanced).mockResolvedValue({ task_id: 'discover-1' } as never)
  mocked(api.simplifySiteEntries).mockResolvedValue({ updated: 1 } as never)
  mocked(api.bindSiteEntry).mockResolvedValue({ ok: true } as never)
  mocked(api.recommendSiteEntry).mockResolvedValue({ entry_type: 'search_template', source: 'llm', validated: true } as never)
  mocked(api.recommendSiteEntriesBatch).mockResolvedValue({ count: 0, items: [] } as never)
  mocked(api.registerExternalProject).mockResolvedValue({ ok: true, persisted: false } as never)
  mocked(api.syncSourceLibraryHandlerClusters).mockResolvedValue({ ok: true, handler_count: 1 } as never)
  mocked(api.upsertSourceLibraryItem).mockResolvedValue({ ok: true } as never)
  mocked(api.upsertSiteEntry).mockResolvedValue({ ok: true } as never)
  mocked(api.refreshSourceLibraryItem).mockResolvedValue({ ok: true } as never)
}

const meta = {
  title: 'Pages/ResourcePage',
  component: ResourcePage,
  parameters: pageParameters,
  decorators: pageDecorators,
  args: {
    projectKey: 'demo-proj',
    variant: 'resource',
  },
  beforeEach: async () => {
    applyResourceMocks()
  },
} satisfies Meta<typeof ResourcePage>

export default meta

type Story = StoryObj<typeof meta>

export const Default: Story = {
  play: async ({ canvas }) => {
    await expect(canvas.getAllByText(/managed_by:system/)[0]).toBeInTheDocument()
    await expect(canvas.getAllByText(/item_type:service_aggregated/)[0]).toBeInTheDocument()
    await expect(canvas.getAllByText(/capability:source_library.collect/)[0]).toBeInTheDocument()
    await expect(canvas.getAllByText('contract_version')[0]).toBeInTheDocument()
    await expect(canvas.getAllByText('execution_mode')[0]).toBeInTheDocument()
    await expect(canvas.getAllByText('runner')[0]).toBeInTheDocument()
    await expect(canvas.getByText('expected_entry_type')).toBeInTheDocument()
    await expect(canvas.getByText('route_bucket')).toBeInTheDocument()
    await expect(canvas.getByText(/total:1/)).toBeInTheDocument()
    await expect(canvas.getByText('lifecycle:needs_review')).toBeInTheDocument()
    await expect(canvas.getByText(/expected:search_template/)).toBeInTheDocument()
    await expect(canvas.getByRole('button', { name: 'Accept' })).toBeInTheDocument()
    await expect(canvas.getByRole('button', { name: 'Reject' })).toBeInTheDocument()
    await expect(canvas.getByRole('button', { name: 'Needs Review' })).toBeInTheDocument()
    await expect(canvas.getByRole('button', { name: 'Disable' })).toBeInTheDocument()
  },
}
