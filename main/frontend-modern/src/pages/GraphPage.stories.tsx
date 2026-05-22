import type { Meta, StoryObj } from '@storybook/react-vite'
import { expect, mocked } from 'storybook/test'
import * as api from '../lib/api'
import GraphPage from './GraphPage'
import { StorybookKernelShell } from './storybookKernelUtils'
import { pageDecorators, pageParameters } from './storybookPageUtils'

const pendingGraphResult = new Promise<never>(() => undefined)

function applyGraphMocks(mode: 'ready' | 'error' | 'loading') {
  mocked(api.getGraphConfig).mockResolvedValue({
    graph_node_types: {
      market: ['MarketData', 'CompanyEntity'],
    },
    graph_node_labels: {
      MarketData: '市场数据',
      CompanyEntity: '公司实体',
    },
    graph_relation_labels: {
      related_to: '关联',
    },
    graph_doc_types: {
      market: ['MarketData'],
    },
  } as never)

  const marketPayload =
    mode === 'loading'
      ? pendingGraphResult
      : mode === 'error'
        ? Promise.reject(new Error('graph backend unavailable'))
        : Promise.resolve({
          nodes: [
            { id: 'market-1', type: 'MarketData', title: '储能需求' },
            { id: 'company-1', type: 'CompanyEntity', title: '宁德时代' },
          ],
          edges: [
            {
              type: 'related_to',
              from: { id: 'market-1', type: 'MarketData' },
              to: { id: 'company-1', type: 'CompanyEntity' },
            },
          ],
          })

  mocked(api.getMarketGraph).mockImplementation(() => marketPayload as never)
  mocked(api.getPolicyGraph).mockResolvedValue({ nodes: [], edges: [] } as never)
  mocked(api.getSocialGraph).mockResolvedValue({ nodes: [], edges: [] } as never)
  mocked(api.listSourceItems).mockResolvedValue([] as never)
  mocked(api.submitGraphStructuredSearchTasks).mockResolvedValue({ task_id: 'graph-structured-1' } as never)
}

const meta = {
  title: 'Pages/Visualization/GraphPage',
  component: GraphPage,
  parameters: {
    ...pageParameters,
    docs: {
      description: {
        component: 'Visualization graph stories with shell fidelity and isolated data/error states for MCP consumers.',
      },
    },
  },
  args: {
    projectKey: 'demo-proj',
    variant: 'graphMarket',
  },
  argTypes: {
    projectKey: { control: 'text' },
    variant: {
      control: 'radio',
      options: ['graphMarket', 'graphPolicy', 'graphSocial', 'graphCompany', 'graphProduct', 'graphOperation', 'graphDeep'],
    },
    templateBuilder: { control: 'boolean' },
  },
  beforeEach: async () => {
    applyGraphMocks('ready')
  },
} satisfies Meta<typeof GraphPage>

export default meta

type Story = StoryObj<typeof meta>

export const ContainerDefault: Story = {
  decorators: pageDecorators,
  play: async ({ canvas }) => {
    await expect(canvas.getByText('市场图谱')).toBeInTheDocument()
  },
}

export const ContainerLoadingState: Story = {
  decorators: pageDecorators,
  beforeEach: async () => {
    applyGraphMocks('loading')
  },
  play: async ({ canvas }) => {
    await expect(canvas.getByText('加载中...')).toBeInTheDocument()
  },
}

export const ContainerErrorState: Story = {
  decorators: pageDecorators,
  beforeEach: async () => {
    applyGraphMocks('error')
  },
  play: async ({ canvas }) => {
    await expect(canvas.getByText('加载失败：graph backend unavailable')).toBeInTheDocument()
  },
}

export const ContainerCompanyFocus: Story = {
  decorators: pageDecorators,
  args: {
    variant: 'graphCompany',
  },
  play: async ({ canvas }) => {
    await expect(canvas.getByText('公司图谱')).toBeInTheDocument()
  },
}

export const ShellMarket: Story = {
  render: (args) => <StorybookKernelShell moduleKey="graphMarket" projectKey={args.projectKey} />,
  play: async ({ canvas }) => {
    await expect(canvas.getByText('市场图谱')).toBeInTheDocument()
  },
}

export const ShellTemplateBuilder: Story = {
  render: (args) => <StorybookKernelShell moduleKey="graphBuilder" projectKey={args.projectKey} />,
  play: async ({ canvas }) => {
    await expect(await canvas.findByRole('button', { name: /编辑模式/i })).toBeInTheDocument()
  },
}
