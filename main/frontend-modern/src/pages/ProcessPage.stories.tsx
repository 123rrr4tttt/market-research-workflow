import type { Meta, StoryObj } from '@storybook/react-vite'
import { expect, userEvent } from 'storybook/test'
import { mocked } from 'storybook/test'
import * as api from '../lib/api'
import ProcessPage, { ProcessPageView, type ProcessPageViewProps } from './ProcessPage'
import { StorybookKernelShell } from './storybookKernelUtils'
import { pageDecorators, pageParameters } from './storybookPageUtils'

const pendingProcessResult = new Promise<never>(() => undefined)

function applyProcessMocks(mode: 'ready' | 'empty' | 'loading' | 'log-error') {
  if (mode === 'ready') {
    mocked(api.getProcessStats).mockResolvedValue({
      total_running: 4,
      active_tasks: 2,
      scheduled_tasks: 1,
      reserved_tasks: 1,
      workers: 3,
      worker_names: ['worker.ingest', 'worker.writer'],
    } as never)
    mocked(api.listProcessTasks).mockResolvedValue({
      tasks: [
        {
          task_id: 'job-123',
          name: 'market_ingest',
          status: 'active',
          worker: 'worker.ingest',
          started_at: '2026-04-02T18:00:00Z',
          updated_at: '2026-04-02T18:05:00Z',
          kwargs: { topic: '储能' },
          progress: { stage: 'crawl', percent: 62 },
          display_meta: { inserted: 12, rejected_count: 1 },
        },
      ],
      stats: {
        total_tasks: 4,
        pending_tasks: 1,
      },
    } as never)
    mocked(api.listProcessHistory).mockResolvedValue({
      history: [
        {
          id: 91,
          task_id: 'job-099',
          task_name: 'policy_refresh',
          status: 'completed',
          params: { topic: '光伏' },
          started_at: '2026-04-01T08:00:00Z',
          finished_at: '2026-04-01T08:06:00Z',
          duration_seconds: 360,
          source: 'history',
        },
      ],
    } as never)
    mocked(api.getProcessTaskDetail).mockResolvedValue({
      task_id: 'job-123',
      status: 'active',
      worker: 'worker.ingest',
      started_at: '2026-04-02T18:00:00Z',
      kwargs: { topic: '储能' },
      progress: { stage: 'crawl', percent: 62 },
      result: { inserted: 12 },
      display_meta: { inserted: 12, rejected_count: 1 },
    } as never)
    mocked(api.getProcessTaskLogs).mockResolvedValue({
      text: 'worker.ingest: fetch queue -> parse queue -> persist',
    } as never)
  } else if (mode === 'empty') {
    mocked(api.getProcessStats).mockResolvedValue({
      total_running: 0,
      active_tasks: 0,
      scheduled_tasks: 0,
      reserved_tasks: 0,
      workers: 0,
      worker_names: [],
    } as never)
    mocked(api.listProcessTasks).mockResolvedValue({
      tasks: [],
      stats: {
        total_tasks: 0,
        pending_tasks: 0,
      },
    } as never)
    mocked(api.listProcessHistory).mockResolvedValue({
      history: [],
    } as never)
    mocked(api.getProcessTaskDetail).mockResolvedValue({} as never)
    mocked(api.getProcessTaskLogs).mockResolvedValue({ text: '' } as never)
  } else if (mode === 'loading') {
    mocked(api.getProcessStats).mockImplementation(() => pendingProcessResult as never)
    mocked(api.listProcessTasks).mockImplementation(() => pendingProcessResult as never)
    mocked(api.listProcessHistory).mockImplementation(() => pendingProcessResult as never)
    mocked(api.getProcessTaskDetail).mockImplementation(() => pendingProcessResult as never)
    mocked(api.getProcessTaskLogs).mockImplementation(() => pendingProcessResult as never)
  } else {
    applyProcessMocks('ready')
    mocked(api.getProcessTaskLogs).mockRejectedValue(new Error('log stream unavailable'))
  }

  mocked(api.cancelTask).mockResolvedValue({ ok: true } as never)
}

function createProcessViewProps(overrides: Partial<ProcessPageViewProps> = {}): ProcessPageViewProps {
  return {
    variant: 'process',
    autoRefreshEnabled: true,
    refreshIntervalSec: 8,
    processStats: {
      total_running: 4,
      active_tasks: 2,
      scheduled_tasks: 1,
      reserved_tasks: 1,
      workers: 3,
      worker_names: ['worker.ingest', 'worker.writer'],
    },
    processList: {
      tasks: [
        {
          task_id: 'job-123',
          name: 'market_ingest',
          status: 'active',
          worker: 'worker.ingest',
          started_at: '2026-04-02T18:00:00Z',
          kwargs: { topic: '储能' },
          progress: { stage: 'crawl', percent: 62 },
          display_meta: { inserted: 12, rejected_count: 1 },
        },
      ],
      stats: {
        total_tasks: 4,
        pending_tasks: 1,
      },
    },
    processHistory: {
      history: [
        {
          id: 91,
          task_id: 'job-099',
          task_name: 'policy_refresh',
          status: 'completed',
          params: { topic: '光伏' },
          started_at: '2026-04-01T08:00:00Z',
          finished_at: '2026-04-01T08:06:00Z',
          duration_seconds: 360,
          source: 'history',
        },
      ],
    },
    taskDetail: {
      task_id: 'job-123',
      name: 'market_ingest',
      status: 'active',
      worker: 'worker.ingest',
      started_at: '2026-04-02T18:00:00Z',
      kwargs: { topic: '储能' },
      progress: { stage: 'crawl', percent: 62 },
      result: { inserted: 12 },
      display_meta: { inserted: 12, rejected_count: 1 },
    },
    taskLogsText: 'worker.ingest: fetch queue -> parse queue -> persist',
    taskLogsError: false,
    cancelPending: false,
    isRefreshing: false,
    selectedTask: undefined,
    selectedHistoryTask: undefined,
    selectedCurrent: false,
    selectedTaskId: null,
    selectedHistoryId: null,
    selectedTaskIds: [],
    selectedMeta: null,
    selectedSourceKind: 'worker',
    selectedResultSummary: '-',
    selectedRejectionView: {
      insertedValid: 12,
      rejectedCount: 1,
      rejectionBreakdown: { low_quality: 1 },
      topReason: 'low_quality (1)',
    },
    selectedLightFilterView: {
      decision: '-',
      reason: '-',
      score: null,
      keep: '-',
    },
    cancellableSelectedTaskIds: [],
    onAutoRefreshEnabledChange: () => undefined,
    onRefreshIntervalChange: () => undefined,
    onRefreshAll: () => undefined,
    onSelectAllCancellable: () => undefined,
    onClearSelectedTasks: () => undefined,
    onCancelSelectedTasks: () => undefined,
    onToggleTaskSelect: () => undefined,
    onToggleCurrentTaskDetail: () => undefined,
    onToggleHistoryDetail: () => undefined,
    onCancelTask: () => undefined,
    onCloseDetail: () => undefined,
    onRefreshSelectedTask: () => undefined,
    onRefreshHistory: () => undefined,
    ...overrides,
  }
}

const meta = {
  title: 'Pages/Management/ProcessPage',
  component: ProcessPage,
  parameters: {
    ...pageParameters,
    docs: {
      description: {
        component: 'Process monitoring stories for MCP: isolated task-state variants plus a management shell entry.',
      },
    },
  },
  args: {
    projectKey: 'demo-proj',
    variant: 'process',
  },
  argTypes: {
    projectKey: { control: 'text' },
    variant: { control: 'radio', options: ['process', 'processing'] },
  },
  beforeEach: async () => {
    applyProcessMocks('ready')
  },
} satisfies Meta<typeof ProcessPage>

export default meta

type Story = StoryObj<typeof meta>

export const ContainerDefault: Story = {
  decorators: pageDecorators,
  play: async ({ canvas }) => {
    await expect(canvas.getByText('任务调度视图')).toBeInTheDocument()
    await userEvent.click(canvas.getByRole('button', { name: '详情' }))
    await expect(canvas.getByText(/任务详情 job-123/)).toBeInTheDocument()
  },
}

export const ViewDefault: Story = {
  decorators: pageDecorators,
  render: () => <ProcessPageView {...createProcessViewProps()} />,
  play: async ({ canvas }) => {
    await expect(canvas.getByText('任务调度视图')).toBeInTheDocument()
    await expect(canvas.getByText('market_ingest')).toBeInTheDocument()
  },
}

export const ContainerLoadingState: Story = {
  decorators: pageDecorators,
  beforeEach: async () => {
    applyProcessMocks('loading')
  },
  play: async ({ canvas }) => {
    const refreshingButtons = canvas.getAllByText('刷新中...')
    await expect(refreshingButtons[0]).toBeInTheDocument()
  },
}

export const ContainerEmptyState: Story = {
  decorators: pageDecorators,
  beforeEach: async () => {
    applyProcessMocks('empty')
  },
  play: async ({ canvas }) => {
    await expect(canvas.getByText('暂无运行中任务')).toBeInTheDocument()
    await expect(canvas.getByText('暂无历史数据')).toBeInTheDocument()
  },
}

export const ContainerLogErrorState: Story = {
  decorators: pageDecorators,
  beforeEach: async () => {
    applyProcessMocks('log-error')
  },
  play: async ({ canvas }) => {
    await userEvent.click(canvas.getByRole('button', { name: '详情' }))
    await expect(canvas.getByText('日志加载失败')).toBeInTheDocument()
  },
}

export const ContainerProcessingFocus: Story = {
  decorators: pageDecorators,
  args: {
    variant: 'processing',
  },
  play: async ({ canvas }) => {
    await expect(canvas.getByText('数据处理任务视图')).toBeInTheDocument()
  },
}

export const ShellProcessMonitoring: Story = {
  render: (args) => <StorybookKernelShell moduleKey="overviewTasks" projectKey={args.projectKey} />,
  play: async ({ canvas }) => {
    await expect(canvas.getByText('任务调度视图')).toBeInTheDocument()
  },
}

export const ShellProcessingFlow: Story = {
  render: (args) => <StorybookKernelShell moduleKey="flowProcessing" projectKey={args.projectKey} />,
  play: async ({ canvas }) => {
    await expect(canvas.getByText('数据处理任务视图')).toBeInTheDocument()
  },
}
