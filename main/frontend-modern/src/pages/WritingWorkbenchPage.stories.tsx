import type { Meta, StoryObj } from '@storybook/react-vite'
import { expect, mocked } from 'storybook/test'
import * as api from '../lib/api'
import * as selectionLookupModule from '../components/writing/useSelectionLookup'
import WritingWorkbenchPage from './WritingWorkbenchPage'
import { StorybookKernelShell } from './storybookKernelUtils'
import { pageDecorators, pageParameters } from './storybookPageUtils'

function applyWritingMocks(mode: 'ready' | 'empty' | 'selection-loading' | 'selection-error' | 'longform') {
  if (mode === 'ready' || mode === 'longform') {
    mocked(selectionLookupModule.useSelectionLookup).mockReturnValue({
      data: {
        cards: [
          {
            card_id: 'card-1',
            source_type: 'document',
            title: '储能需求跟踪',
            snippet: '储能招标与并网节奏持续抬升。',
            score: 0.91,
            publisher: '内部索引',
            relevance_tags: ['储能', '招标'],
            quick_actions: ['加入引用'],
            extra: {},
          },
          ...(mode === 'longform'
            ? [
                {
                  card_id: 'card-2',
                  source_type: 'news',
                  title: '锂盐价格跟踪',
                  snippet: '锂盐价格在二季度出现阶段性回调，影响电池成本曲线。',
                  score: 0.82,
                  publisher: '行业数据库',
                  relevance_tags: ['锂盐', '成本'],
                  quick_actions: ['插入正文'],
                  extra: {},
                },
              ]
            : []),
        ],
        suggestItems: [
          { kind: 'material', id: 's1', label: '储能并网政策', extra: {} },
          { kind: 'keyword', id: 's2', label: '锂盐现货价格', extra: {} },
          ...(mode === 'longform' ? [{ kind: 'material', id: 's3', label: '电池出口跟踪', extra: {} }] : []),
        ],
      },
      error: null,
      status: 'success',
      selectionHash: 'sel_demo1234',
    })

    mocked(api.listWritingDocuments).mockResolvedValue([
      {
        id: 11,
        project_key: 'demo-proj',
        title: '市场周报',
        body_md: '# 市场周报\n\n- 储能\n- 电池',
        status: 'draft',
        version: 3,
        etag: 'etag-11',
        metadata_json: {},
        updated_at: '2026-04-02T18:00:00Z',
      },
      {
        id: 12,
        project_key: 'demo-proj',
        title: '政策简报',
        body_md: '# 政策简报',
        status: 'published',
        version: 2,
        etag: 'etag-12',
        metadata_json: {},
        updated_at: '2026-04-01T10:00:00Z',
      },
    ] as never)
    mocked(api.getWritingDocument).mockResolvedValue({
      id: 11,
      project_key: 'demo-proj',
      title: '市场周报',
      body_md: '# 市场周报\n\n## 核心结论\n\n- 储能招标加快\n- 锂盐价格波动',
      status: 'draft',
      version: 3,
      etag: 'etag-11',
      metadata_json: {},
      updated_at: '2026-04-02T18:00:00Z',
    } as never)
    mocked(api.listWritingCitations).mockResolvedValue([
      {
        id: 1,
        doc_id: 11,
        source_title: '新能源周报',
        source_uri: 'https://example.com/report',
        quote_text: '储能电芯出口在一季度延续高增长。',
        card_id: 'card-1',
      },
    ] as never)
    mocked(api.listWritingTemplates).mockResolvedValue([
      {
        template_key: 'weekly-report',
        label: 'Weekly Report',
        description: '市场周报模板',
        template_content: '# Weekly Report',
      },
      {
        template_key: 'policy-brief',
        label: 'Policy Brief',
        description: '政策简报模板',
        template_content: '# Policy Brief',
      },
    ] as never)
    if (mode === 'longform') {
      mocked(api.listWritingLlmActionHistory).mockResolvedValue([
        {
          job_id: 101,
          job_type: 'llm_action',
          status: 'completed',
          action_id: 'outline_generate',
          template_key: 'weekly-report',
          request_meta: {},
          result_summary: {},
          trace_id: 'trace-101',
          created_at: '2026-04-02T18:10:00Z',
          duration_ms: 820,
        },
        {
          job_id: 102,
          job_type: 'llm_action',
          status: 'completed',
          action_id: 'expand_section',
          template_key: 'weekly-report',
          request_meta: {},
          result_summary: {},
          trace_id: 'trace-102',
          created_at: '2026-04-02T18:15:00Z',
          duration_ms: 960,
        },
      ] as never)
    } else {
      mocked(api.listWritingLlmActionHistory).mockResolvedValue([
        {
          job_id: 101,
          job_type: 'llm_action',
          status: 'completed',
          action_id: 'outline_generate',
          template_key: 'weekly-report',
          request_meta: {},
          result_summary: {},
          trace_id: 'trace-101',
          created_at: '2026-04-02T18:10:00Z',
          duration_ms: 820,
        },
      ] as never)
    }
    mocked(api.getWritingLlmActionDetail).mockResolvedValue({
      job_id: 101,
      job_type: 'llm_action',
      status: 'completed',
      action_id: 'outline_generate',
      template_key: 'weekly-report',
      template_version: 'v1',
      request_meta: {},
      result_summary: {},
      trace_id: 'trace-101',
      created_at: '2026-04-02T18:10:00Z',
      duration_ms: 820,
    } as never)
    mocked(api.previewWritingKeywordCard).mockResolvedValue({
      card_id: 'card-1',
      title: '储能需求跟踪',
      url: 'https://example.com/report',
      publisher: '内部索引',
      snippet: '储能招标与并网节奏持续抬升。',
      score: 0.91,
      source_type: 'document',
      quick_actions: ['加入引用'],
    } as never)
    mocked(api.getWritingCardDetail).mockResolvedValue({
      card_id: 'card-1',
      title: '储能需求跟踪',
      url: 'https://example.com/report',
      score: 0.91,
      evidence: '储能系统招标量与电池出口需求呈同步增长。',
      publisher: '内部索引',
      published_at: '2026-03-30',
      retrieved_at: '2026-04-02',
      normalized_query: 'energy storage demand',
      dedupe_trace: [],
      provenance: { source: 'internal-index' },
      selection_matches: { overlap: 0.72 },
      source_type: 'document',
    } as never)
  } else if (mode === 'selection-loading') {
    mocked(selectionLookupModule.useSelectionLookup).mockReturnValue({
      data: { cards: [], suggestItems: [] },
      error: null,
      status: 'loading',
      selectionHash: 'sel_loading',
    })
    mocked(api.listWritingDocuments).mockResolvedValue([
      {
        id: 11,
        project_key: 'demo-proj',
        title: '市场周报',
        body_md: '# 市场周报',
        status: 'draft',
        version: 3,
        etag: 'etag-11',
        metadata_json: {},
        updated_at: '2026-04-02T18:00:00Z',
      },
    ] as never)
    mocked(api.getWritingDocument).mockResolvedValue({
      id: 11,
      project_key: 'demo-proj',
      title: '市场周报',
      body_md: '# 市场周报',
      status: 'draft',
      version: 3,
      etag: 'etag-11',
      metadata_json: {},
      updated_at: '2026-04-02T18:00:00Z',
    } as never)
    mocked(api.listWritingCitations).mockResolvedValue([] as never)
    mocked(api.listWritingTemplates).mockResolvedValue([] as never)
    mocked(api.listWritingLlmActionHistory).mockResolvedValue([] as never)
    mocked(api.getWritingLlmActionDetail).mockResolvedValue(null as never)
    mocked(api.previewWritingKeywordCard).mockResolvedValue(null as never)
    mocked(api.getWritingCardDetail).mockResolvedValue(null as never)
  } else if (mode === 'selection-error') {
    mocked(selectionLookupModule.useSelectionLookup).mockReturnValue({
      data: { cards: [], suggestItems: [] },
      error: 'selection lookup unavailable',
      status: 'error',
      selectionHash: 'sel_error',
    })
    mocked(api.listWritingDocuments).mockResolvedValue([
      {
        id: 11,
        project_key: 'demo-proj',
        title: '市场周报',
        body_md: '# 市场周报',
        status: 'draft',
        version: 3,
        etag: 'etag-11',
        metadata_json: {},
        updated_at: '2026-04-02T18:00:00Z',
      },
    ] as never)
    mocked(api.getWritingDocument).mockResolvedValue({
      id: 11,
      project_key: 'demo-proj',
      title: '市场周报',
      body_md: '# 市场周报',
      status: 'draft',
      version: 3,
      etag: 'etag-11',
      metadata_json: {},
      updated_at: '2026-04-02T18:00:00Z',
    } as never)
    mocked(api.listWritingCitations).mockResolvedValue([] as never)
    mocked(api.listWritingTemplates).mockResolvedValue([] as never)
    mocked(api.listWritingLlmActionHistory).mockResolvedValue([] as never)
    mocked(api.getWritingLlmActionDetail).mockResolvedValue(null as never)
    mocked(api.previewWritingKeywordCard).mockResolvedValue(null as never)
    mocked(api.getWritingCardDetail).mockResolvedValue(null as never)
  } else {
    mocked(selectionLookupModule.useSelectionLookup).mockReturnValue({
      data: { cards: [], suggestItems: [] },
      error: null,
      status: 'success',
      selectionHash: 'sel_empty',
    })
    mocked(api.listWritingDocuments).mockResolvedValue([] as never)
    mocked(api.getWritingDocument).mockResolvedValue(null as never)
    mocked(api.listWritingCitations).mockResolvedValue([] as never)
    mocked(api.listWritingTemplates).mockResolvedValue([] as never)
    mocked(api.listWritingLlmActionHistory).mockResolvedValue([] as never)
    mocked(api.getWritingLlmActionDetail).mockResolvedValue(null as never)
    mocked(api.previewWritingKeywordCard).mockResolvedValue(null as never)
    mocked(api.getWritingCardDetail).mockResolvedValue(null as never)
  }

  mocked(api.createWritingDocument).mockResolvedValue({
    id: 99,
    project_key: 'demo-proj',
    title: 'Untitled report',
    body_md: '',
    status: 'draft',
    version: 1,
    etag: 'etag-99',
    metadata_json: {},
  } as never)
  mocked(api.updateWritingDocument).mockResolvedValue({
    id: 11,
    project_key: 'demo-proj',
    title: '市场周报',
    body_md: '# 市场周报',
    status: 'draft',
    version: 4,
    etag: 'etag-11-next',
    metadata_json: {},
  } as never)
  mocked(api.autosaveWritingDraft).mockResolvedValue({
    id: 201,
    doc_id: 11,
    project_key: 'demo-proj',
    draft_body_md: '# draft',
    base_version: 3,
    autosave_token: 'writing-11',
  } as never)
  mocked(api.exportWritingMarkdown).mockResolvedValue({
    filename: 'weekly-report.md',
    content: '# Weekly Report',
    mime_type: 'text/markdown',
  } as never)
  mocked(api.upsertWritingCitations).mockResolvedValue([
    {
      id: 1,
      doc_id: 11,
      source_title: '新能源周报',
      source_uri: 'https://example.com/report',
      quote_text: '储能电芯出口在一季度延续高增长。',
      card_id: 'card-1',
    },
  ] as never)
  mocked(api.runWritingLlmAction).mockResolvedValue({
    content: '1. 储能招标升温\n2. 价格链条分化\n3. 政策支持增强',
    sources: [],
    mode: 'sync',
    warnings: [],
    trace_id: 'trace-run',
    job_id: 101,
    status: 'completed',
    observability: {},
  } as never)
  mocked(api.validateWritingTemplate).mockResolvedValue({
    valid: true,
    errors: [],
    warnings: [],
    normalized_template: {},
    rules: {},
    observability: {},
  } as never)
}

const meta = {
  title: 'Pages/Workbench/WritingWorkbenchPage',
  component: WritingWorkbenchPage,
  parameters: {
    ...pageParameters,
    docs: {
      description: {
        component: 'Writing workbench stories for MCP with a realistic document-rich state, an empty state, and a shell-integrated workbench entry.',
      },
    },
  },
  args: {
    projectKey: 'demo-proj',
    standalone: true,
  },
  argTypes: {
    projectKey: { control: 'text' },
    standalone: { control: 'boolean' },
  },
  beforeEach: async () => {
    applyWritingMocks('ready')
  },
} satisfies Meta<typeof WritingWorkbenchPage>

export default meta

type Story = StoryObj<typeof meta>

export const ContainerDefault: Story = {
  decorators: pageDecorators,
  play: async ({ canvas }) => {
    await expect(canvas.getByText('市场周报')).toBeInTheDocument()
  },
}

export const ContainerSelectionLoading: Story = {
  decorators: pageDecorators,
  beforeEach: async () => {
    applyWritingMocks('selection-loading')
  },
  play: async ({ canvas }) => {
    await expect(canvas.getByText('loading')).toBeInTheDocument()
  },
}

export const ContainerEmptyState: Story = {
  decorators: pageDecorators,
  beforeEach: async () => {
    applyWritingMocks('empty')
  },
  play: async ({ canvas }) => {
    await expect(canvas.getByText('暂无已保存文档，先创建一篇。')).toBeInTheDocument()
  },
}

export const ContainerSelectionError: Story = {
  decorators: pageDecorators,
  beforeEach: async () => {
    applyWritingMocks('selection-error')
  },
  play: async ({ canvas }) => {
    await expect(canvas.getByText('selection lookup unavailable')).toBeInTheDocument()
  },
}

export const ContainerLongformResearch: Story = {
  decorators: pageDecorators,
  beforeEach: async () => {
    applyWritingMocks('longform')
  },
  play: async ({ canvas }) => {
    await expect(canvas.getByText('锂盐价格跟踪')).toBeInTheDocument()
    await expect(canvas.getByText('电池出口跟踪')).toBeInTheDocument()
  },
}

export const ContainerEmbeddedLayout: Story = {
  decorators: pageDecorators,
  args: {
    standalone: false,
  },
  play: async ({ canvas }) => {
    await expect(canvas.getByText('文档列表')).toBeInTheDocument()
  },
}

export const ShellWorkbench: Story = {
  render: (args) => <StorybookKernelShell moduleKey="flowWriting" projectKey={args.projectKey} />,
  play: async ({ canvas }) => {
    await expect(canvas.getByText('市场周报')).toBeInTheDocument()
  },
}
