import type { Meta, StoryObj } from '@storybook/react-vite'
import { expect, mocked } from 'storybook/test'
import * as api from '../lib/api'
import SettingsPage, { SettingsPageView, type SettingsPageViewProps } from './SettingsPage'
import { StorybookKernelShell } from './storybookKernelUtils'
import { pageDecorators, pageParameters } from './storybookPageUtils'

const pendingSettingsResult = new Promise<never>(() => undefined)

const readyEnv = {
  DATABASE_URL: 'postgres://storybook/demo',
  OPENAI_API_KEY: 'sk-storybook',
  OPENAI_API_BASE: 'https://api.openai.com/v1',
  SERPAPI_KEY: 'serp-storybook',
  NEWS_API_KEY: 'news-storybook',
}

const readyTemplates = {
  items: [
    {
      id: 1,
      service_name: 'market_outline',
      description: 'Market outline generation',
      model: 'gpt-4.1',
      temperature: 0.2,
      max_tokens: 1200,
      enabled: true,
      updated_at: '2026-04-02T18:00:00Z',
      system_prompt: 'Outline the report with evidence-aware sections.',
      user_prompt_template: 'Summarize the latest signals for {{topic}}',
      top_p: 1,
      presence_penalty: 0,
      frequency_penalty: 0,
    },
    {
      id: 2,
      service_name: 'policy_brief',
      description: 'Policy briefing template',
      model: 'gpt-4.1-mini',
      temperature: 0.1,
      max_tokens: 900,
      enabled: true,
      updated_at: '2026-04-01T10:30:00Z',
      system_prompt: 'Write a concise policy brief.',
      user_prompt_template: 'Explain impact and next actions for {{policy_name}}',
      top_p: 1,
      presence_penalty: 0,
      frequency_penalty: 0,
    },
  ],
}

function applySettingsMocks(mode: 'ready' | 'empty' | 'error' | 'loading') {
  if (mode === 'ready') {
    mocked(api.getEnvSettings).mockResolvedValue(readyEnv as never)
    mocked(api.listProjectLlmTemplates).mockResolvedValue(readyTemplates as never)
  } else if (mode === 'empty') {
    mocked(api.getEnvSettings).mockResolvedValue({} as never)
    mocked(api.listProjectLlmTemplates).mockResolvedValue({ items: [] } as never)
  } else if (mode === 'loading') {
    mocked(api.getEnvSettings).mockImplementation(() => pendingSettingsResult as never)
    mocked(api.listProjectLlmTemplates).mockImplementation(() => pendingSettingsResult as never)
  } else {
    mocked(api.getEnvSettings).mockRejectedValue(new Error('settings unavailable'))
    mocked(api.listProjectLlmTemplates).mockRejectedValue(new Error('templates unavailable'))
  }

  mocked(api.updateEnvSettings).mockResolvedValue({ ok: true } as never)
  mocked(api.updateProjectLlmTemplate).mockResolvedValue({ ok: true } as never)
  mocked(api.copyProjectLlmTemplates).mockResolvedValue({ copied: 2, skipped: 0 } as never)
}

function createSettingsViewProps(overrides: Partial<SettingsPageViewProps> = {}): SettingsPageViewProps {
  return {
    projectKey: 'demo-proj',
    variant: 'settings',
    locale: 'zh-CN',
    appTheme: 'dark',
    themeLabelByValue: {
      light: 'Light',
      dark: 'Dark',
      brand: 'Brand',
    },
    localeLabelByValue: {
      'zh-CN': 'Simplified Chinese',
      'en-US': 'English',
    },
    effectiveEnvDraft: readyEnv,
    templateItems: readyTemplates.items,
    envSettingsFetching: false,
    envSettingsError: false,
    llmTemplatesFetching: false,
    llmTemplatesError: false,
    envSavePending: false,
    templateSavePending: false,
    copyTemplatesPending: false,
    hasAnyEnvValue: true,
    saveMessage: '',
    templateMessage: '',
    copyMessage: '',
    copySourceProjectKey: 'template-proj',
    copyOverwrite: false,
    expandedService: null,
    savingService: null,
    guideType: null,
    focusField: '',
    envSnippet: '',
    templateDrafts: {},
    onLocaleChange: () => undefined,
    onThemeChange: () => undefined,
    onRefreshEnv: () => undefined,
    onCopySnippet: () => undefined,
    onDismissGuide: () => undefined,
    onNavigateCrawler: () => undefined,
    onEnvDraftChange: () => undefined,
    onSaveEnv: () => undefined,
    onRefreshTemplates: () => undefined,
    onCopySourceProjectKeyChange: () => undefined,
    onCopyOverwriteChange: () => undefined,
    onCopyTemplates: () => undefined,
    onExpandedServiceChange: () => undefined,
    onTemplateDraftChange: () => undefined,
    onSaveTemplate: () => undefined,
    ...overrides,
  }
}

const meta = {
  title: 'Pages/Management/SettingsPage',
  component: SettingsPage,
  parameters: {
    ...pageParameters,
    docs: {
      description: {
        component: 'Agent-facing settings surface with isolated state stories and a kernel shell story for MCP consumers.',
      },
    },
  },
  args: {
    projectKey: 'demo-proj',
    variant: 'settings',
  },
  argTypes: {
    projectKey: { control: 'text' },
    variant: { control: 'radio', options: ['settings', 'llm'] },
  },
  beforeEach: async () => {
    applySettingsMocks('ready')
  },
} satisfies Meta<typeof SettingsPage>

export default meta

type Story = StoryObj<typeof meta>

export const ContainerDefault: Story = {
  decorators: pageDecorators,
  play: async ({ canvas }) => {
    await expect(canvas.getByText('系统设置视图')).toBeInTheDocument()
    await expect(canvas.getByText('项目级 LLM 模板')).toBeInTheDocument()
  },
}

export const ViewDefault: Story = {
  decorators: pageDecorators,
  render: () => <SettingsPageView {...createSettingsViewProps()} />,
  play: async ({ canvas }) => {
    await expect(canvas.getByText('系统设置视图')).toBeInTheDocument()
    await expect(canvas.getByText('项目级 LLM 模板')).toBeInTheDocument()
  },
}

export const ContainerLoadingState: Story = {
  decorators: pageDecorators,
  beforeEach: async () => {
    applySettingsMocks('loading')
  },
  play: async ({ canvas }) => {
    const refreshingButtons = canvas.getAllByText('刷新中...')
    await expect(refreshingButtons[0]).toBeInTheDocument()
  },
}

export const ContainerEmptyState: Story = {
  decorators: pageDecorators,
  beforeEach: async () => {
    applySettingsMocks('empty')
  },
  play: async ({ canvas }) => {
    await expect(canvas.getByText('暂无项目级 LLM 模板')).toBeInTheDocument()
  },
}

export const ContainerErrorState: Story = {
  decorators: pageDecorators,
  beforeEach: async () => {
    applySettingsMocks('error')
  },
  play: async ({ canvas }) => {
    await expect(canvas.getByText('环境配置加载失败，请稍后重试')).toBeInTheDocument()
    await expect(canvas.getByText('项目级 LLM 模板加载失败，请稍后重试')).toBeInTheDocument()
  },
}

export const ContainerLlmFocus: Story = {
  decorators: pageDecorators,
  args: {
    variant: 'llm',
  },
  play: async ({ canvas }) => {
    await expect(canvas.getByText('LLM 配置视图')).toBeInTheDocument()
  },
}

export const ShellSettings: Story = {
  render: (args) => <StorybookKernelShell moduleKey="sysSettings" projectKey={args.projectKey} />,
  play: async ({ canvas }) => {
    await expect(canvas.getByText('系统设置视图')).toBeInTheDocument()
  },
}

export const ShellLlm: Story = {
  render: (args) => <StorybookKernelShell moduleKey="sysLlm" projectKey={args.projectKey} />,
  play: async ({ canvas }) => {
    await expect(canvas.getByText('LLM 配置视图')).toBeInTheDocument()
  },
}
